"""Phase 2: modeling with TIME-AWARE validation.

Trains models on earlier seasons and tests on the most recent ones (never
shuffling across time -- the cardinal sin of sports ML). It then compares the
models not just on accuracy but on whether they produce any edge against the
Vegas closing line, which is the actual research question.

Models:
  - Logistic regression  -> home-win probability
  - Linear regression    -> predicted home margin (-> vs the spread)
  - XGBoost (clf + reg)  -> stronger benchmark
Benchmarks:
  - "Elo favorite" naive pick
  - Vegas closing line

Outputs: reports/metrics.csv, reports/ats.csv, and figures in reports/figures/.
Crucially: market columns (spread/total/moneyline) are NEVER used as model
inputs -- otherwise the model would just read back the market's answer.
"""
import json
import warnings
import numpy as np
import pandas as pd
import duckdb
from sklearn.linear_model import LogisticRegression, LinearRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import (accuracy_score, roc_auc_score, brier_score_loss,
                             log_loss, mean_absolute_error)
from sklearn.calibration import calibration_curve
from xgboost import XGBClassifier, XGBRegressor
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import config

warnings.filterwarnings("ignore")
FIG = config.ROOT / "reports" / "figures"
FIG.mkdir(parents=True, exist_ok=True)

# Team-only features. NO market columns here (no leakage of the line).
FEATURES = [
    "d_elo", "d_margin", "d_off", "d_def", "d_efg", "d_winpct", "d_rest",
    "home_elo_pre", "away_elo_pre",
    "h_off", "h_def", "h_winpct", "h_pace", "h_rest",
    "a_off", "a_def", "a_winpct", "a_pace", "a_rest",
]
TEST_SEASONS = ("2024-25", "2025-26")     # hold out the two most recent seasons
VIG_PAYOUT = 100.0 / 110.0                 # win returns 0.909 units at -110


def load():
    con = duckdb.connect(str(config.DB_PATH), read_only=True)
    df = con.execute("""
        SELECT * FROM model_data
        WHERE h_prior >= 10 AND a_prior >= 10
          AND home_covered IS NOT NULL
    """).df()
    con.close()
    for c in ("h_b2b", "a_b2b"):
        df[c] = df[c].astype(int)
    df = df.dropna(subset=FEATURES + ["home_win", "home_margin", "home_spread"])
    return df


def ats_eval(name, pick_home_cover, df):
    """pick_home_cover: bool array, True = bet home to cover. Returns metrics dict."""
    covered = df["home_covered"].values            # 1 home covered, 0 away covered
    win = np.where(pick_home_cover, covered == 1, covered == 0)
    n = len(win)
    hit = win.mean()
    roi = (win * VIG_PAYOUT - (~win) * 1.0).mean()
    return {"strategy": name, "bets": n, "ats_hit_pct": round(100 * hit, 2),
            "roi_pct": round(100 * roi, 2)}


def main():
    df = load()
    train = df[~df["season"].isin(TEST_SEASONS)].copy()
    test = df[df["season"].isin(TEST_SEASONS)].copy()
    print(f"train: {len(train)} games ({train.season.min()}..)  "
          f"test: {len(test)} games ({sorted(test.season.unique())})")

    Xtr, Xte = train[FEATURES], test[FEATURES]
    y_win_tr, y_win_te = train["home_win"].astype(int), test["home_win"].astype(int)
    y_mar_tr, y_mar_te = train["home_margin"], test["home_margin"]

    # market predicted margin = -spread; covered target for ATS
    vegas_pred_margin = -test["home_spread"].values

    metrics = []
    calib = {}

    # ---------- WIN PROBABILITY ----------
    logit = make_pipeline(StandardScaler(), LogisticRegression(max_iter=1000))
    logit.fit(Xtr, y_win_tr)
    p_logit = logit.predict_proba(Xte)[:, 1]

    xgbc = XGBClassifier(n_estimators=300, max_depth=4, learning_rate=0.05,
                         subsample=0.8, colsample_bytree=0.8, eval_metric="logloss")
    xgbc.fit(Xtr, y_win_tr)
    p_xgb = xgbc.predict_proba(Xte)[:, 1]

    # Vegas implied home win prob FROM THE SPREAD (moneylines are absent post-2021).
    # Home margin ~ Normal(mean = -spread, sd = sigma); P(home win) = P(margin > 0).
    from scipy.stats import norm
    sigma = float(y_mar_tr.std())                   # ~12-13 pts, learned from train
    p_vegas = norm.cdf(-test["home_spread"].values / sigma)

    for name, p in [("logistic", p_logit), ("xgboost", p_xgb), ("vegas_spread", p_vegas)]:
        ok = np.isfinite(p)                          # vegas_ml has a few missing moneylines
        yy, pp = y_win_te.values[ok], p[ok]
        metrics.append({
            "model": name, "target": "home_win", "n": int(ok.sum()),
            "accuracy": round(accuracy_score(yy, pp > 0.5), 4),
            "roc_auc": round(roc_auc_score(yy, pp), 4),
            "brier": round(brier_score_loss(yy, pp), 4),
            "log_loss": round(log_loss(yy, pp), 4),
        })
        frac_pos, mean_pred = calibration_curve(yy, pp, n_bins=10, strategy="quantile")
        calib[name] = (mean_pred, frac_pos)

    # ---------- MARGIN / SPREAD ----------
    lin = make_pipeline(StandardScaler(), LinearRegression())
    lin.fit(Xtr, y_mar_tr)
    m_lin = lin.predict(Xte)

    xgbr = XGBRegressor(n_estimators=300, max_depth=4, learning_rate=0.05,
                        subsample=0.8, colsample_bytree=0.8)
    xgbr.fit(Xtr, y_mar_tr)
    m_xgb = xgbr.predict(Xte)

    for name, m in [("linear", m_lin), ("xgboost", m_xgb), ("vegas_line", vegas_pred_margin)]:
        metrics.append({
            "model": name, "target": "home_margin",
            "mae": round(mean_absolute_error(y_mar_te, m), 3),
        })

    pd.DataFrame(metrics).to_csv(config.ROOT / "reports" / "metrics.csv", index=False)
    print("\n=== ACCURACY / ERROR (test set) ===")
    print(pd.DataFrame(metrics).to_string(index=False))

    # ---------- AGAINST THE SPREAD (the real question) ----------
    spread = test["home_spread"].values
    ats = []
    # model bets home to cover when its predicted margin beats the line
    ats.append(ats_eval("linear_vs_spread", m_lin > -spread, test))
    ats.append(ats_eval("xgboost_vs_spread", m_xgb > -spread, test))
    # logistic: bet home cover when win prob high enough to imply beating spread (proxy: p>0.5 & home favored)
    ats.append(ats_eval("elo_favorite", test["d_elo"].values > 0, test))
    ats.append(ats_eval("always_home", np.ones(len(test), dtype=bool), test))
    # selective: only bet when model disagrees with line by >= 3 pts
    edge = m_xgb - (-spread)
    mask = np.abs(edge) >= 3
    if mask.sum() > 0:
        sel = ats_eval(f"xgboost_edge>=3pts (n={int(mask.sum())})",
                       (edge > 0)[mask], test[mask])
        ats.append(sel)

    ats_df = pd.DataFrame(ats)
    ats_df.to_csv(config.ROOT / "reports" / "ats.csv", index=False)
    print("\n=== AGAINST-THE-SPREAD RESULTS (52.4% = breakeven after vig) ===")
    print(ats_df.to_string(index=False))

    # ---------- FIGURES ----------
    # calibration
    plt.figure(figsize=(5, 5))
    plt.plot([0, 1], [0, 1], "k--", lw=1, label="perfect")
    for name, (mp, fp) in calib.items():
        plt.plot(mp, fp, marker="o", label=name)
    plt.xlabel("predicted home-win prob"); plt.ylabel("observed frequency")
    plt.title("Calibration: model vs Vegas"); plt.legend(); plt.tight_layout()
    plt.savefig(FIG / "calibration.png", dpi=120); plt.close()

    # ATS hit rate bar
    plt.figure(figsize=(7, 4))
    bars = ats_df.set_index("strategy")["ats_hit_pct"]
    bars.plot(kind="barh")
    plt.axvline(52.4, color="red", ls="--", label="52.4% breakeven")
    plt.axvline(50, color="gray", ls=":", label="coin flip")
    plt.xlabel("ATS hit %"); plt.title("Nobody clears the vig"); plt.legend()
    plt.tight_layout(); plt.savefig(FIG / "ats_hit.png", dpi=120); plt.close()

    # feature importance
    plt.figure(figsize=(6, 5))
    imp = pd.Series(xgbc.feature_importances_, index=FEATURES).sort_values()
    imp.plot(kind="barh"); plt.title("XGBoost feature importance (win model)")
    plt.tight_layout(); plt.savefig(FIG / "feature_importance.png", dpi=120); plt.close()

    print(f"\nFigures saved to {FIG}")
    print("Saved reports/metrics.csv and reports/ats.csv")


if __name__ == "__main__":
    main()
