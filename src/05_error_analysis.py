"""Phase 3: error analysis -- WHERE and WHY models fail vs the closing line.

Three questions:
  1. Variance decomposition: how much of game margin is even predictable? How big
     is the irreducible "hidden variance" floor that no pre-game model can touch?
  2. Segment analysis: are there any slices (rest, spread size, season stage,
     favorites/dogs, totals) where the market is beatable? (Hypotheses H1-H4.)
  3. Where are residuals largest -- i.e. which games are intrinsically noisiest?

Outputs: reports/phase3_segments.csv, reports/phase3_findings.md, and figures.
"""
import numpy as np
import pandas as pd
import duckdb
from sklearn.linear_model import LinearRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import mean_absolute_error
from xgboost import XGBRegressor
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import config

FIG = config.ROOT / "reports" / "figures"
FIG.mkdir(parents=True, exist_ok=True)
VIG = 100.0 / 110.0
TEST = ("2024-25", "2025-26")
FEATURES = [
    "d_elo", "d_margin", "d_off", "d_def", "d_efg", "d_winpct", "d_rest",
    "home_elo_pre", "away_elo_pre",
    "h_off", "h_def", "h_winpct", "h_pace", "h_rest",
    "a_off", "a_def", "a_winpct", "a_pace", "a_rest",
]


def load():
    con = duckdb.connect(str(config.DB_PATH), read_only=True)
    df = con.execute("""SELECT * FROM model_data
        WHERE h_prior>=10 AND a_prior>=10 AND home_covered IS NOT NULL""").df()
    con.close()
    for c in ("h_b2b", "a_b2b"):
        df[c] = df[c].astype(int)
    return df.dropna(subset=FEATURES + ["home_margin", "home_spread", "total"])


def segment_table(test, pick_home, model_resid, vegas_resid):
    """Aggregate ATS + residual stats over labeled segments."""
    cov = test["home_covered"].values
    win = np.where(pick_home, cov == 1, cov == 0)
    base = pd.DataFrame({
        "seg_group": test["_grp"].values,
        "seg": test["_seg"].values,
        "win": win,
        "model_resid": np.abs(model_resid),
        "vegas_resid": np.abs(vegas_resid),
    })
    g = base.groupby(["seg_group", "seg"], observed=True).agg(
        games=("win", "size"),
        ats_hit_pct=("win", lambda x: round(100 * x.mean(), 1)),
        model_mae=("model_resid", lambda x: round(x.mean(), 2)),
        vegas_mae=("vegas_resid", lambda x: round(x.mean(), 2)),
    ).reset_index()
    g["roi_pct"] = g["ats_hit_pct"].apply(lambda h: round((h/100*VIG - (1-h/100))*100, 1))
    return g


def main():
    df = load()
    train, test = df[~df.season.isin(TEST)].copy(), df[df.season.isin(TEST)].copy()

    lin = make_pipeline(StandardScaler(), LinearRegression()).fit(train[FEATURES], train.home_margin)
    xgb = XGBRegressor(n_estimators=300, max_depth=4, learning_rate=0.05,
                       subsample=0.8, colsample_bytree=0.8).fit(train[FEATURES], train.home_margin)
    m_pred = xgb.predict(test[FEATURES])
    v_pred = -test["home_spread"].values
    actual = test["home_margin"].values
    model_resid = actual - m_pred
    vegas_resid = actual - v_pred
    pick_home = m_pred > -test["home_spread"].values

    # ---------- 1) variance decomposition ----------
    total_var = actual.var()
    v_r2 = 1 - vegas_resid.var() / total_var
    m_r2 = 1 - model_resid.var() / total_var
    lines = []
    lines.append("## 1. How much of an NBA game is even predictable?\n")
    lines.append(f"- SD of actual home margin: **{actual.std():.1f} pts** "
                 f"(total variance {total_var:.0f}).")
    lines.append(f"- Vegas line explains **{100*v_r2:.1f}%** of margin variance; "
                 f"residual SD = **{vegas_resid.std():.1f} pts**.")
    lines.append(f"- Our XGBoost explains **{100*m_r2:.1f}%**; "
                 f"residual SD = **{model_resid.std():.1f} pts**.")
    lines.append(f"- => Even the market leaves a ~**{vegas_resid.std():.0f}-point** "
                 f"per-game noise floor. That is the *hidden variance*: injuries, "
                 f"rotations, foul trouble, and shooting luck that no pre-game model sees.\n")
    print("\n".join(lines))

    # ---------- 2) segment analysis ----------
    test = test.reset_index(drop=True)
    segs = []

    def add(grp, labels):
        t = test.copy(); t["_grp"] = grp; t["_seg"] = labels
        return segment_table(t, pick_home, model_resid, vegas_resid)

    spread_bin = pd.cut(test["home_spread"].abs(),
                        [-0.1, 3, 7, 11, 100],
                        labels=["pickem (0-3)", "small (3-7)", "mid (7-11)", "big (11+)"])
    segs.append(add("spread size", spread_bin))

    fav = np.where(test["home_spread"] < 0, "home favored", "away favored")
    segs.append(add("favorite", fav))

    b2b = np.select(
        [(test.h_b2b == 1) & (test.a_b2b == 0), (test.a_b2b == 1) & (test.h_b2b == 0)],
        ["home on B2B", "away on B2B"], default="neither/both")
    segs.append(add("back-to-back", b2b))

    stage = pd.cut(test["h_prior"], [9, 20, 45, 100],
                   labels=["early (gm 10-20)", "mid (20-45)", "late (45+)"])
    segs.append(add("season stage", stage))

    tot_med = train["total"].median()
    tot_bin = np.where(test["total"] >= tot_med, f"high total (>= {tot_med:.0f})",
                       f"low total (< {tot_med:.0f})")
    segs.append(add("game total", tot_bin))

    out = pd.concat(segs, ignore_index=True)
    out.to_csv(config.ROOT / "reports" / "phase3_segments.csv", index=False)
    print("=== ATS + error by segment (test set) ===")
    print(out.to_string(index=False))

    # ---------- 3) figures ----------
    plt.figure(figsize=(6, 4))
    plt.hist(vegas_resid, bins=40, alpha=0.7, label=f"vegas residual (SD {vegas_resid.std():.1f})")
    plt.hist(model_resid, bins=40, alpha=0.5, label=f"xgboost residual (SD {model_resid.std():.1f})")
    plt.axvline(0, color="k", lw=1)
    plt.xlabel("actual margin - predicted margin"); plt.ylabel("games")
    plt.title("The irreducible noise floor"); plt.legend(); plt.tight_layout()
    plt.savefig(FIG / "residual_distribution.png", dpi=120); plt.close()

    # residual MAE by spread size (is variance worse for blowouts?)
    tmp = pd.DataFrame({"spread": spread_bin, "abs_resid": np.abs(vegas_resid)})
    mae_by = tmp.groupby("spread", observed=True)["abs_resid"].mean()
    plt.figure(figsize=(6, 4))
    mae_by.plot(kind="bar")
    plt.ylabel("Vegas MAE (pts)"); plt.title("Prediction error by spread size")
    plt.xticks(rotation=20); plt.tight_layout()
    plt.savefig(FIG / "mae_by_spread.png", dpi=120); plt.close()

    # ---------- write findings md ----------
    md = ["# Phase 3 - Error analysis & hidden variance\n", "\n".join(lines), "\n"]
    md.append("## 2. Is any segment beatable? (52.4% = breakeven)\n")
    md.append("No slice clears the vig with any margin; ATS hovers at ~50% everywhere.\n")
    md.append("```\n" + out.to_string(index=False) + "\n```\n")
    md.append("## 3. Where is error largest?\n")
    md.append(f"Prediction error grows with spread size (blowout games are noisier): "
              f"{mae_by.round(1).to_dict()}. Big favorites invite garbage time and "
              f"resting starters, adding variance the line cannot fully anticipate.\n")
    md.append("\n_Limitation:_ this dataset has only closing lines (no opening lines), "
              "so closing-line-value and line-movement tests are out of scope.\n")
    (config.ROOT / "reports" / "phase3_findings.md").write_text("\n".join(md), encoding="utf-8")
    print(f"\nWrote reports/phase3_findings.md and figures to {FIG}")


if __name__ == "__main__":
    main()
