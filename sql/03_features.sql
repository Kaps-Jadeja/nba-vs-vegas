-- Feature engineering layer.
-- CRITICAL: every feature for a game uses ONLY games that finished BEFORE it.
-- Rolling windows use the frame "N PRECEDING AND 1 PRECEDING" so the current
-- game is excluded -> no look-ahead / target leakage.

-- 1) Long team-game table with per-game advanced stats (one row per team per game).
CREATE OR REPLACE TABLE team_game AS
SELECT
    b.game_id,
    b.season,
    b.game_date,
    b.team_id,
    b.abbr,
    o.abbr                                   AS opp_abbr,
    b.is_home,
    b.win,
    b.PTS                                    AS pts,
    o.PTS                                    AS opp_pts,
    b.PTS - o.PTS                            AS margin,
    -- possessions estimate (Dean Oliver) and four-factors-style rates
    (b.FGA - b.OREB + b.TOV + 0.44 * b.FTA)              AS poss,
    (b.FGM + 0.5 * b.FG3M) / NULLIF(b.FGA, 0)            AS efg,
    100.0 * b.PTS / NULLIF(b.FGA - b.OREB + b.TOV + 0.44 * b.FTA, 0) AS off_rtg,
    100.0 * o.PTS / NULLIF(b.FGA - b.OREB + b.TOV + 0.44 * b.FTA, 0) AS def_rtg
FROM box b
JOIN box o
  ON b.game_id = o.game_id
 AND b.team_id <> o.team_id;

-- 2) Pre-game rolling form + rest, computed per team within a season.
--    prior_games tells us how "warmed up" the rolling window is (for filtering).
CREATE OR REPLACE TABLE team_pregame AS
SELECT
    game_id,
    season,
    game_date,
    abbr,
    is_home,
    COUNT(*)                                   OVER w_all  AS prior_games,
    AVG(margin)                                OVER w_roll AS roll_margin,
    AVG(off_rtg)                               OVER w_roll AS roll_off_rtg,
    AVG(def_rtg)                               OVER w_roll AS roll_def_rtg,
    AVG(efg)                                   OVER w_roll AS roll_efg,
    AVG(poss)                                  OVER w_roll AS roll_pace,
    AVG(CASE WHEN win THEN 1.0 ELSE 0.0 END)   OVER w_roll AS roll_winpct,
    date_diff('day', LAG(game_date) OVER w_ord, game_date) AS rest_days
FROM team_game
WINDOW
    w_ord  AS (PARTITION BY abbr, season ORDER BY game_date, game_id),
    w_all  AS (PARTITION BY abbr, season ORDER BY game_date, game_id
               ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING),
    w_roll AS (PARTITION BY abbr, season ORDER BY game_date, game_id
               ROWS BETWEEN 10 PRECEDING AND 1 PRECEDING);
