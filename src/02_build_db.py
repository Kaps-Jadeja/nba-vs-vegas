"""Load raw CSVs into DuckDB and run the SQL layer to build the `game` table.

Usage:  python 02_build_db.py
Output: nba.duckdb  with tables: games_raw, odds_raw, team_map, box, odds, game.
"""
import duckdb
import pandas as pd
import config

SQL_FILES = ["01_staging.sql", "02_game_table.sql"]


def main():
    games = pd.read_csv(config.GAMES_CSV)
    odds = pd.read_csv(config.ODDS_CSV)
    team_map = pd.DataFrame(
        list(config.ODDS_TO_ABBR.items()), columns=["odds_code", "abbr"]
    )

    con = duckdb.connect(str(config.DB_PATH))
    # Materialize raw inputs as persistent tables so the .sql files can reference them.
    con.execute("CREATE OR REPLACE TABLE games_raw AS SELECT * FROM games")
    con.execute("CREATE OR REPLACE TABLE odds_raw AS SELECT * FROM odds")
    con.execute("CREATE OR REPLACE TABLE team_map AS SELECT * FROM team_map")

    for f in SQL_FILES:
        sql = (config.ROOT / "sql" / f).read_text()
        con.execute(sql)
        print(f"ran {f}")

    # Quick sanity / coverage report.
    n_games = con.execute("SELECT COUNT(*) FROM game").fetchone()[0]
    n_with_odds = con.execute(
        "SELECT COUNT(*) FROM game WHERE home_spread IS NOT NULL"
    ).fetchone()[0]
    print(f"\ngames: {n_games}")
    print(f"games with odds matched: {n_with_odds} "
          f"({100*n_with_odds/n_games:.1f}%)")
    print("\nby season:")
    print(con.execute("""
        SELECT season,
               COUNT(*) AS games,
               SUM(CASE WHEN home_spread IS NOT NULL THEN 1 ELSE 0 END) AS with_odds
        FROM game GROUP BY season ORDER BY season
    """).df().to_string(index=False))
    con.close()


if __name__ == "__main__":
    main()
