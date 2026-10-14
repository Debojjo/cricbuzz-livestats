-- =============================================================================
-- Views: saved joins that make the 25 analytics queries shorter and safer.
-- They are dropped and recreated on every init, so editing them is easy.
-- =============================================================================

-- One row per match with every id replaced by a readable name.
DROP VIEW IF EXISTS v_match_results;
CREATE VIEW v_match_results AS
SELECT
    m.match_id,
    m.match_desc,
    m.format,
    m.match_category,
    m.match_date,
    m.state,
    m.status,
    m.victory_type,
    m.victory_margin,
    m.toss_decision,
    m.is_sample,
    s.series_id,
    s.series_name,
    t1.team_id      AS team1_id,
    t1.team_name    AS team1_name,
    t1.country      AS team1_country,
    t2.team_id      AS team2_id,
    t2.team_name    AS team2_name,
    t2.country      AS team2_country,
    w.team_name     AS winner_name,
    m.winner_id,
    tw.team_name    AS toss_winner_name,
    m.toss_winner_id,
    v.venue_id,
    v.venue_name,
    v.city          AS venue_city,
    v.country       AS venue_country
FROM matches m
JOIN teams t1        ON t1.team_id = m.team1_id
JOIN teams t2        ON t2.team_id = m.team2_id
LEFT JOIN teams w    ON w.team_id  = m.winner_id
LEFT JOIN teams tw   ON tw.team_id = m.toss_winner_id
LEFT JOIN venues v   ON v.venue_id = m.venue_id
LEFT JOIN series s   ON s.series_id = m.series_id;

-- One row per batting innings with player, match date, year/quarter, opponent
-- and whether the batter's team won (used by Q15-Q19, Q23, Q25).
DROP VIEW IF EXISTS v_batting_detail;
CREATE VIEW v_batting_detail AS
SELECT
    bp.performance_id,
    bp.match_id,
    bp.innings_no,
    bp.player_id,
    p.full_name       AS player_name,
    bp.team_id,
    t.team_name,
    CASE WHEN bp.team_id = m.team1_id THEN m.team2_id
         ELSE m.team1_id END                AS opponent_id,
    bp.batting_position,
    bp.runs,
    bp.balls_faced,
    bp.fours,
    bp.sixes,
    bp.strike_rate,
    bp.is_not_out,
    bp.out_desc,
    m.format,
    m.match_date,
    CAST(strftime('%Y', m.match_date) AS INTEGER)                 AS match_year,
    (CAST(strftime('%m', m.match_date) AS INTEGER) - 1) / 3 + 1   AS match_quarter,
    m.venue_id,
    m.victory_type,
    m.victory_margin,
    CASE WHEN m.winner_id IS NULL THEN NULL
         WHEN m.winner_id = bp.team_id THEN 1
         ELSE 0 END                          AS team_won,
    bp.is_sample
FROM batting_performances bp
JOIN players p ON p.player_id = bp.player_id
JOIN teams t   ON t.team_id   = bp.team_id
JOIN matches m ON m.match_id  = bp.match_id;

-- One row per bowling spell. economy_calc is recomputed from balls so it is
-- consistent even when the API's own economy figure is rounded or missing.
DROP VIEW IF EXISTS v_bowling_detail;
CREATE VIEW v_bowling_detail AS
SELECT
    bw.performance_id,
    bw.match_id,
    bw.innings_no,
    bw.player_id,
    p.full_name       AS player_name,
    bw.team_id,
    t.team_name,
    bw.overs,
    bw.balls,
    bw.maidens,
    bw.runs_conceded,
    bw.wickets,
    bw.economy,
    CASE WHEN bw.balls > 0
         THEN ROUND(bw.runs_conceded * 6.0 / bw.balls, 2) END     AS economy_calc,
    m.format,
    m.match_date,
    CAST(strftime('%Y', m.match_date) AS INTEGER)                 AS match_year,
    m.venue_id,
    v.venue_name,
    bw.is_sample
FROM bowling_performances bw
JOIN players p     ON p.player_id = bw.player_id
JOIN teams t       ON t.team_id   = bw.team_id
JOIN matches m     ON m.match_id  = bw.match_id
LEFT JOIN venues v ON v.venue_id  = m.venue_id;

-- One row per partnership, with both batters' names and batting positions.
-- is_consecutive = 1 when the two positions differ by exactly 1 (Q13, Q24).
DROP VIEW IF EXISTS v_partnership_detail;
CREATE VIEW v_partnership_detail AS
SELECT
    pt.partnership_id,
    pt.match_id,
    pt.innings_no,
    pt.wicket_no,
    pt.bat1_id,
    p1.full_name     AS bat1_name,
    b1.batting_position AS bat1_position,
    pt.bat2_id,
    p2.full_name     AS bat2_name,
    b2.batting_position AS bat2_position,
    pt.runs,
    pt.balls,
    CASE WHEN b1.batting_position IS NOT NULL
          AND b2.batting_position IS NOT NULL
          AND ABS(b1.batting_position - b2.batting_position) = 1
         THEN 1 ELSE 0 END                                        AS is_consecutive,
    m.format,
    m.match_date,
    pt.is_sample
FROM partnerships pt
JOIN players p1 ON p1.player_id = pt.bat1_id
JOIN players p2 ON p2.player_id = pt.bat2_id
JOIN matches m  ON m.match_id   = pt.match_id
LEFT JOIN batting_performances b1
       ON b1.match_id = pt.match_id AND b1.innings_no = pt.innings_no
      AND b1.player_id = pt.bat1_id
LEFT JOIN batting_performances b2
       ON b2.match_id = pt.match_id AND b2.innings_no = pt.innings_no
      AND b2.player_id = pt.bat2_id;
