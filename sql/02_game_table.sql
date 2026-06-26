-- Pivot the team-level box scores into one row per game and join the betting line.
-- Produces the analytical base table `game` with modeling targets pre-computed.

CREATE OR REPLACE TABLE game AS
WITH h AS (SELECT * FROM box WHERE is_home),
     a AS (SELECT * FROM box WHERE NOT is_home)
SELECT
    h.game_id,
    h.season,
    h.game_date,
    h.abbr               AS home_abbr,
    a.abbr               AS away_abbr,
    h.team_name          AS home_team,
    a.team_name          AS away_team,
    h.PTS                AS home_pts,
    a.PTS                AS away_pts,
    h.PTS - a.PTS        AS home_margin,
    h.win                AS home_win,

    -- home box stats
    h.FGM AS h_fgm, h.FGA AS h_fga, h.FG3M AS h_fg3m, h.FG3A AS h_fg3a,
    h.FTM AS h_ftm, h.FTA AS h_fta, h.OREB AS h_oreb, h.DREB AS h_dreb,
    h.REB AS h_reb, h.AST AS h_ast, h.STL AS h_stl, h.BLK AS h_blk,
    h.TOV AS h_tov, h.PF AS h_pf,

    -- away box stats
    a.FGM AS a_fgm, a.FGA AS a_fga, a.FG3M AS a_fg3m, a.FG3A AS a_fg3a,
    a.FTM AS a_ftm, a.FTA AS a_fta, a.OREB AS a_oreb, a.DREB AS a_dreb,
    a.REB AS a_reb, a.AST AS a_ast, a.STL AS a_stl, a.BLK AS a_blk,
    a.TOV AS a_tov, a.PF AS a_pf,

    -- betting line (home perspective)
    o.home_spread,
    o.total,
    o.ml_home,
    o.ml_away,

    -- modeling targets
    (h.PTS - a.PTS) + o.home_spread AS home_cover_margin,        -- >0 home covers
    CASE WHEN (h.PTS - a.PTS) + o.home_spread > 0 THEN 1
         WHEN (h.PTS - a.PTS) + o.home_spread < 0 THEN 0
         ELSE NULL END             AS home_covered,              -- NULL = push
    (h.PTS + a.PTS)                AS total_points,
    CASE WHEN (h.PTS + a.PTS) > o.total THEN 1
         WHEN (h.PTS + a.PTS) < o.total THEN 0
         ELSE NULL END             AS over_hit
FROM h
JOIN a  ON h.game_id = a.game_id
LEFT JOIN odds o
       ON o.game_date = h.game_date
      AND o.home_abbr = h.abbr
      AND o.away_abbr = a.abbr;
