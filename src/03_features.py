"""Phase 1 feature engineering.

Runs the SQL feature layer (rolling form + rest via window functions), then
computes a pre-game Elo rating in Python -- Elo is sequential (each game updates
ratings used by the next), which is awkward in pure SQL, so it lives here. The
key invariant is the same as the SQL: features use only pre-game information.

Output table: model_data  (one row per game, features + targets).
"""
import duckdb
import pandas as pd
import config

# Elo parameters (538-style).
K = 20.0
HOME_ADV = 100.0          # rating points of home-court edge
MEAN_ELO = 1505.0
SEASON_REGRESS = 0.25     # fraction pulled back to the mean each new season


def compute_elo(games: pd.DataFrame) -> pd.DataFrame:
    """games: one row per game, chronological. Returns pre-game Elo per game."""
    elo = {}
    last_season = {}
    rows = []
    for g in games.itertuples(index=False):
        home, away = g.home_abbr, g.away_abbr
        for team in (home, away):
            if team not in elo:
                elo[team] = MEAN_ELO
            elif last_season.get(team) != g.season:
                elo[team] = (1 - SEASON_REGRESS) * elo[team] + SEASON_REGRESS * MEAN_ELO
            last_season[team] = g.season

        rh, ra = elo[home], elo[away]
        rows.append((g.game_id, rh, ra))

        exp_home = 1.0 / (1.0 + 10 ** ((ra - rh - HOME_ADV) / 400.0))
        actual_home = 1.0 if g.home_win else 0.0
        delta = K * (actual_home - exp_home)
        elo[home] = rh + delta
        elo[away] = ra - delta

    return pd.DataFrame(rows, columns=["game_id", "home_elo_pre", "away_elo_pre"])


def main():
    con = duckdb.connect(str(config.DB_PATH))

    # 1) rolling-form + rest features (pure SQL).
    con.execute((config.ROOT / "sql" / "03_features.sql").read_text())
    print("ran 03_features.sql (team_game, team_pregame)")

    # 2) Elo in Python, chronological over the game table.
    games = con.execute("""
        SELECT game_id, season, game_date, home_abbr, away_abbr, home_win
        FROM game ORDER BY game_date, game_id
    """).df()
    elo_pre = compute_elo(games)
    con.execute("CREATE OR REPLACE TABLE elo_pre AS SELECT * FROM elo_pre")
    print(f"computed Elo for {len(elo_pre)} games")

    # 3) assemble final modeling table (SQL).
    con.execute((config.ROOT / "sql" / "04_model_data.sql").read_text())
    print("ran 04_model_data.sql (model_data)")

    # ---- report ----
    n = con.execute("SELECT COUNT(*) FROM model_data").fetchone()[0]
    n_ready = con.execute(
        "SELECT COUNT(*) FROM model_data WHERE h_prior >= 10 AND a_prior >= 10"
    ).fetchone()[0]
    print(f"\nmodel_data rows: {n}")
    print(f"rows with full 10-game windows for both teams: {n_ready} "
          f"({100*n_ready/n:.1f}%)")

    print("\nElo sanity - does higher pre-game Elo diff predict home wins?")
    print(con.execute("""
        SELECT CASE
                 WHEN d_elo > 100 THEN '4. home much stronger (>100)'
                 WHEN d_elo > 0   THEN '3. home stronger (0..100)'
                 WHEN d_elo > -100 THEN '2. away stronger (-100..0)'
                 ELSE '1. away much stronger (<-100)'
               END AS elo_bucket,
               COUNT(*) AS games,
               ROUND(100.0*AVG(CASE WHEN home_win THEN 1 ELSE 0 END),1) AS home_win_pct,
               ROUND(100.0*AVG(home_covered),1) AS home_cover_pct
        FROM model_data WHERE d_elo IS NOT NULL
        GROUP BY elo_bucket ORDER BY elo_bucket
    """).df().to_string(index=False))

    print("\nDoes our form/Elo edge predict ATS cover? (the key question)")
    print(con.execute("""
        SELECT CASE WHEN d_elo > 0 THEN 'home Elo favorite' ELSE 'away Elo favorite' END AS side,
               COUNT(*) AS games,
               ROUND(100.0*AVG(home_covered),1) AS home_cover_pct
        FROM model_data WHERE d_elo IS NOT NULL GROUP BY side
    """).df().to_string(index=False))

    con.close()


if __name__ == "__main__":
    main()
