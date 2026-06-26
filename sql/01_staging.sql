-- Staging layer: clean the two raw sources into tidy tables.
-- Inputs (materialized by 02_build_db.py): games_raw, odds_raw, team_map.

-- Cleaned team-level box scores (two rows per game, one per team).
CREATE OR REPLACE TABLE box AS
SELECT
    GAME_ID                                  AS game_id,
    SEASON                                   AS season,        -- e.g. '2015-16'
    CAST(GAME_DATE AS DATE)                  AS game_date,
    TEAM_ID                                  AS team_id,
    TEAM_ABBREVIATION                        AS abbr,
    TEAM_NAME                                AS team_name,
    MATCHUP                                  AS matchup,
    MATCHUP LIKE '%vs.%'                     AS is_home,       -- 'vs.' = home, '@' = away
    WL = 'W'                                 AS win,
    PTS, FGM, FGA, FG3M, FG3A, FTM, FTA,
    OREB, DREB, REB, AST, STL, BLK, TOV, PF,
    PLUS_MINUS                               AS plus_minus
FROM games_raw;

-- Cleaned, home-oriented betting lines with abbreviations mapped to nba_api codes.
-- Spread is stored from the HOME team's perspective (favorite = negative).
CREATE OR REPLACE TABLE odds AS
SELECT
    o.season                                 AS season_end,    -- 2016 == season '2015-16'
    CAST(o.date AS DATE)                     AS game_date,
    hm.abbr                                  AS home_abbr,
    am.abbr                                  AS away_abbr,
    o.score_home,
    o.score_away,
    CASE WHEN o.whos_favored = 'home' THEN -o.spread ELSE o.spread END AS home_spread,
    o.total,
    o.moneyline_home                         AS ml_home,
    o.moneyline_away                         AS ml_away
FROM odds_raw o
JOIN team_map hm ON o.home = hm.odds_code
JOIN team_map am ON o.away = am.odds_code
WHERE o.regular = TRUE;
