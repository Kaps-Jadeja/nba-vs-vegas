"""Phase 4 prep: export clean, dashboard-ready CSVs for Power BI.

Refits the models on the training seasons, scores the held-out test seasons, and
writes flat CSVs with predictions, betting outcomes, profit, and ready-made
segment dimensions. Flags are pre-computed as 0/1 / +profit so Power BI measures
are simple AVERAGE / SUM -- no complex DAX required.

Outputs (powerbi/exports/):
  games.csv          one row per test game: predictions, outcomes, dims, profit
  win_metrics.csv    accuracy / ROC-AUC / Brier for logistic, xgboost, vegas
  margin_mae.csv     MAE for linear, xgboost, vegas
  ats_segments.csv   ATS hit% + ROI by segment
  calibration.csv    predicted vs observed win prob, per model
"""
import numpy as np
import pandas as pd
import duckdb
from scipy.stats import norm
from sklearn.linear_model import LogisticRegression, LinearRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import (accuracy_score, roc_auc_score, brier_score_loss,
                             mean_absolute_error)
from sklearn.calibration import calibration_curve
from xgboost import XGBClassifier, XGBRegressor
import config

OUT = config.ROOT / "powerbi" / "exports"
OUT.mkdir(parents=True, exist_ok=True)
VIG = 100.0 / 110.0
TEST = ("2024-25", "2025-26")
FEATURES = [
    "d_elo", "d_margin", "d_off", "d_def", "d_efg", "d_winpct", "d_rest",
    "home_elo_pre", "away_elo_pre",
    "h_off", "h_def", "h_winpct", "h_pace", "h_rest",
    "a_off", "a_def", "a_winpct", "a_pace", "a_rest",
]


def main():
    con = duckdb.connect(str(config.DB_PATH), read_only=True)
    df = con.execute("""SELECT * FROM model_data
        WHERE h_prior>=10 AND a_prior>=10 AND home_covered IS NOT NULL""").df()
    con.close()
    for c in ("h_b2b", "a_b2b"):
        df[c] = df[c].astype(int)
    df = df.dropna(subset=FEATURES + ["home_margin", "home_spread", "total"])
    train, test = df[~df.season.isin(TEST)].copy(), df[df.season.isin(TEST)].copy()

    # ---- fit ----
    Xtr, Xte = train[FEATURES], test[FEATURES]
    logit = make_pipeline(StandardScaler(), LogisticRegression(max_iter=1000)).fit(Xtr, train.home_win.astype(int))
    xgbc = XGBClassifier(n_estimators=300, max_depth=4, learning_rate=0.05,
                         subsample=0.8, colsample_bytree=0.8, eval_metric="logloss").fit(Xtr, train.home_win.astype(int))
    lin = make_pipeline(StandardScaler(), LinearRegression()).fit(Xtr, train.home_margin)
    xgbr = XGBRegressor(n_estimators=300, max_depth=4, learning_rate=0.05,
                        subsample=0.8, colsample_bytree=0.8).fit(Xtr, train.home_margin)

    sigma = float(train.home_margin.std())
    t = test.reset_index(drop=True)
    p_logit = logit.predict_proba(Xte)[:, 1]
    p_xgb = xgbc.predict_proba(Xte)[:, 1]
    p_vegas = norm.cdf(-t.home_spread.values / sigma)
    m_lin = lin.predict(Xte)
    m_xgb = xgbr.predict(Xte)
    v_margin = -t.home_spread.values

    # ---- games fact table ----
    pick_home = m_xgb > -t.home_spread.values
    cov = t.home_covered.values
    ats_win = np.where(pick_home, cov == 1, cov == 0)
    g = pd.DataFrame({
        "game_id": t.game_id, "season": t.season, "game_date": t.game_date,
        "home_team": t.home_abbr, "away_team": t.away_abbr,
        "matchup": t.away_abbr + " @ " + t.home_abbr,
        "home_spread": t.home_spread, "total_line": t.total,
        "home_margin": t.home_margin, "total_points": t.total_points,
        "home_win": t.home_win.astype(int),
        "home_covered": cov.astype(int),
        "over_hit": t.over_hit,
        # model outputs
        "model_win_prob": p_logit.round(4),
        "model_pred_margin": m_xgb.round(2),
        "vegas_win_prob": p_vegas.round(4),
        "vegas_pred_margin": v_margin,
        # correctness flags (0/1 -> AVERAGE = accuracy)
        "model_win_correct": ((p_logit > 0.5).astype(int) == t.home_win.astype(int)).astype(int),
        "vegas_win_correct": ((p_vegas > 0.5).astype(int) == t.home_win.astype(int)).astype(int),
        # ATS betting outcome + profit (SUM = P&L, AVERAGE of ats_win = hit rate)
        "model_ats_pick": np.where(pick_home, "Home", "Away"),
        "model_ats_win": ats_win.astype(int),
        "unit_profit": np.where(ats_win, VIG, -1.0).round(4),
        "abs_err_model": np.abs(t.home_margin.values - m_xgb).round(2),
        "abs_err_vegas": np.abs(t.home_margin.values - v_margin).round(2),
        # dimensions for slicers / bar charts
        "favorite_side": np.where(t.home_spread < 0, "Home favored", "Away favored"),
        "spread_bucket": pd.cut(t.home_spread.abs(), [-0.1, 3, 7, 11, 100],
                                labels=["Pick'em (0-3)", "Small (3-7)", "Mid (7-11)", "Big (11+)"]),
        "season_stage": pd.cut(t.h_prior, [9, 20, 45, 100],
                               labels=["Early", "Mid", "Late"]),
        "b2b_status": np.select(
            [(t.h_b2b == 1) & (t.a_b2b == 0), (t.a_b2b == 1) & (t.h_b2b == 0)],
            ["Home on B2B", "Away on B2B"], default="Neither/Both"),
    })
    g.to_csv(OUT / "games.csv", index=False)

    # ---- win metrics ----
    rows = []
    for name, p in [("Logistic", p_logit), ("XGBoost", p_xgb), ("Vegas line", p_vegas)]:
        y = t.home_win.astype(int)
        rows.append({"model": name,
                     "accuracy": round(accuracy_score(y, p > 0.5), 4),
                     "roc_auc": round(roc_auc_score(y, p), 4),
                     "brier": round(brier_score_loss(y, p), 4)})
    pd.DataFrame(rows).to_csv(OUT / "win_metrics.csv", index=False)

    # ---- margin mae ----
    pd.DataFrame([
        {"model": "Linear", "mae": round(mean_absolute_error(t.home_margin, m_lin), 3)},
        {"model": "XGBoost", "mae": round(mean_absolute_error(t.home_margin, m_xgb), 3)},
        {"model": "Vegas line", "mae": round(mean_absolute_error(t.home_margin, v_margin), 3)},
    ]).to_csv(OUT / "margin_mae.csv", index=False)

    # ---- ATS by segment (tidy/long for a single bar chart with a slicer) ----
    segs = []
    for grp, col in [("Spread size", "spread_bucket"), ("Favorite", "favorite_side"),
                     ("Season stage", "season_stage"), ("Back-to-back", "b2b_status")]:
        s = g.groupby(col, observed=True).agg(
            games=("model_ats_win", "size"),
            ats_hit_pct=("model_ats_win", lambda x: round(100 * x.mean(), 1)),
            roi_pct=("unit_profit", lambda x: round(100 * x.mean(), 1)),
        ).reset_index().rename(columns={col: "segment"})
        s.insert(0, "seg_group", grp)
        segs.append(s)
    pd.concat(segs, ignore_index=True).to_csv(OUT / "ats_segments.csv", index=False)

    # ---- calibration ----
    crows = []
    for name, p in [("Logistic", p_logit), ("XGBoost", p_xgb), ("Vegas line", p_vegas)]:
        frac_pos, mean_pred = calibration_curve(t.home_win.astype(int), p, n_bins=10, strategy="quantile")
        for mp, fp in zip(mean_pred, frac_pos):
            crows.append({"model": name, "predicted": round(mp, 4), "observed": round(fp, 4)})
    pd.DataFrame(crows).to_csv(OUT / "calibration.csv", index=False)

    print(f"Exported {len(g)} games + 4 summary tables to {OUT}")
    for f in sorted(OUT.glob("*.csv")):
        print(" -", f.name)


if __name__ == "__main__":
    main()
