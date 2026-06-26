-- Assemble the final modeling table: one row per game with home/away pre-game
-- features, Elo (from elo_pre, built in src/03_features.py), feature diffs, and
-- all betting targets. Only games with a matched closing line are kept.

CREATE OR REPLACE TABLE model_data AS
SELECT
    g.game_id,
    g.season,
    g.game_date,
    g.home_abbr,
    g.away_abbr,

    -- ===== targets =====
    g.home_win,
    g.home_margin,
    g.home_covered,
    g.over_hit,

    -- ===== market (also used as benchmark) =====
    g.home_spread,
    g.total,
    g.ml_home,
    g.ml_away,
    g.total_points,

    -- ===== home pre-game form =====
    h.prior_games          AS h_prior,
    h.roll_margin          AS h_margin,
    h.roll_off_rtg         AS h_off,
    h.roll_def_rtg         AS h_def,
    h.roll_efg             AS h_efg,
    h.roll_pace            AS h_pace,
    h.roll_winpct          AS h_winpct,
    h.rest_days            AS h_rest,
    (h.rest_days = 1)      AS h_b2b,

    -- ===== away pre-game form =====
    a.prior_games          AS a_prior,
    a.roll_margin          AS a_margin,
    a.roll_off_rtg         AS a_off,
    a.roll_def_rtg         AS a_def,
    a.roll_efg             AS a_efg,
    a.roll_pace            AS a_pace,
    a.roll_winpct          AS a_winpct,
    a.rest_days            AS a_rest,
    (a.rest_days = 1)      AS a_b2b,

    -- ===== Elo (pre-game) =====
    e.home_elo_pre,
    e.away_elo_pre,

    -- ===== home-minus-away diffs (what models actually lean on) =====
    h.roll_margin  - a.roll_margin  AS d_margin,
    h.roll_off_rtg - a.roll_off_rtg AS d_off,
    h.roll_def_rtg - a.roll_def_rtg AS d_def,
    h.roll_efg     - a.roll_efg     AS d_efg,
    h.roll_winpct  - a.roll_winpct  AS d_winpct,
    h.rest_days    - a.rest_days    AS d_rest,
    e.home_elo_pre - e.away_elo_pre AS d_elo
FROM game g
JOIN team_pregame h ON g.game_id = h.game_id AND h.abbr = g.home_abbr
JOIN team_pregame a ON g.game_id = a.game_id AND a.abbr = g.away_abbr
LEFT JOIN elo_pre e ON g.game_id = e.game_id
WHERE g.home_spread IS NOT NULL;
