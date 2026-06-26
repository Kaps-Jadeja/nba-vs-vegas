"""Pull team-level box scores for the configured seasons from stats.nba.com via nba_api.

Output: data/games_raw.csv  (two rows per game, one per team).
Politely rate-limited so stats.nba.com doesn't throttle us.
"""
import time
import sys
import pandas as pd
from nba_api.stats.endpoints import leaguegamefinder
import config

KEEP = [
    "SEASON_ID", "TEAM_ID", "TEAM_ABBREVIATION", "TEAM_NAME", "GAME_ID",
    "GAME_DATE", "MATCHUP", "WL", "PTS", "FGM", "FGA", "FG3M", "FG3A",
    "FTM", "FTA", "OREB", "DREB", "REB", "AST", "STL", "BLK", "TOV", "PF",
    "PLUS_MINUS",
]


def pull_season(season: str, tries: int = 4) -> pd.DataFrame:
    for attempt in range(1, tries + 1):
        try:
            gf = leaguegamefinder.LeagueGameFinder(
                league_id_nullable="00",
                season_nullable=season,
                season_type_nullable="Regular Season",
                timeout=60,
            )
            df = gf.get_data_frames()[0]
            df = df[[c for c in KEEP if c in df.columns]].copy()
            df["SEASON"] = season
            print(f"  {season}: {len(df)} team-rows")
            return df
        except Exception as e:
            wait = 5 * attempt
            print(f"  {season}: attempt {attempt} failed ({type(e).__name__}); retry in {wait}s")
            time.sleep(wait)
    print(f"  {season}: GAVE UP", file=sys.stderr)
    return pd.DataFrame()


def main():
    frames = []
    for season in config.season_strings():
        frames.append(pull_season(season))
        time.sleep(2)  # be polite between seasons
    out = pd.concat([f for f in frames if not f.empty], ignore_index=True)
    config.GAMES_CSV.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(config.GAMES_CSV, index=False)
    print(f"\nWrote {len(out)} rows -> {config.GAMES_CSV}")


if __name__ == "__main__":
    main()
