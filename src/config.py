"""Shared config: season scope, paths, and the odds<->nba_api team-code map."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
DB_PATH = ROOT / "nba.duckdb"

ODDS_CSV = DATA / "odds_current" / "nba_2008-2026.csv"
GAMES_CSV = DATA / "games_raw.csv"

# Season scope. nba_api "season" is "2015-16"; odds file "season" is the END year (2016).
START_SEASON_END = 2016   # 2015-16
END_SEASON_END = 2026     # 2025-26

def season_strings():
    """nba_api season labels, e.g. ['2015-16', ..., '2025-26']."""
    out = []
    for end in range(START_SEASON_END, END_SEASON_END + 1):
        out.append(f"{end-1}-{str(end)[2:]}")
    return out

# Odds file lowercase codes -> standard nba_api 3-letter abbreviations.
ODDS_TO_ABBR = {
    "atl": "ATL", "bkn": "BKN", "bos": "BOS", "cha": "CHA", "chi": "CHI",
    "cle": "CLE", "dal": "DAL", "den": "DEN", "det": "DET", "gs": "GSW",
    "hou": "HOU", "ind": "IND", "lac": "LAC", "lal": "LAL", "mem": "MEM",
    "mia": "MIA", "mil": "MIL", "min": "MIN", "no": "NOP", "ny": "NYK",
    "okc": "OKC", "orl": "ORL", "phi": "PHI", "phx": "PHX", "por": "POR",
    "sa": "SAS", "sac": "SAC", "tor": "TOR", "utah": "UTA", "wsh": "WAS",
}
