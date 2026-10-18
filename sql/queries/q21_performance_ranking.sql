-- Q21 (Advanced): A weighted performance ranking, top 10 per format.
-- batting  = runs x 0.01 + average x 0.5 + strike rate x 0.3
-- bowling  = wickets x 2 + (50 - bowling average) x 0.5 + (6 - economy) x 2
-- fielding = catches x 3 + stumpings x 5
--
-- Everything is computed from match-by-match records, so all three parts use the
-- same source and the same format. Assumptions (the question does not say):
--   * batting points need at least 5 innings and 1 dismissal, otherwise 0;
--   * bowling points need at least 10 overs (60 balls) and 1 wicket, otherwise 0;
--     (a bowling average or economy is meaningless without those);
--   * average = runs / dismissals, strike rate = runs x 100 / balls faced,
--     bowling average = runs conceded / wickets, economy = runs x 6 / balls.
-- Players tied on points share a rank (RANK). T20 here means T20 matches.

WITH bat AS (
    SELECT bp.player_id, m.format,
           COUNT(*)                                          AS innings,
           SUM(bp.runs)                                      AS runs,
           SUM(CASE WHEN bp.is_not_out = 0 THEN 1 ELSE 0 END) AS dismissals,
           SUM(bp.balls_faced)                               AS balls
    FROM batting_performances AS bp
    JOIN matches AS m ON m.match_id = bp.match_id
    GROUP BY bp.player_id, m.format
),
bowl AS (
    SELECT bw.player_id, m.format,
           SUM(bw.balls)         AS balls,
           SUM(bw.runs_conceded) AS runs_conceded,
           SUM(bw.wickets)       AS wickets
    FROM bowling_performances AS bw
    JOIN matches AS m ON m.match_id = bw.match_id
    GROUP BY bw.player_id, m.format
),
field AS (
    SELECT f.player_id, m.format,
           SUM(f.catches)   AS catches,
           SUM(f.stumpings) AS stumpings
    FROM fielding_performances AS f
    JOIN matches AS m ON m.match_id = f.match_id
    GROUP BY f.player_id, m.format
),
base AS (
    SELECT player_id, format FROM bat
    UNION SELECT player_id, format FROM bowl
    UNION SELECT player_id, format FROM field
),
scored AS (
    SELECT
        b.player_id,
        b.format,
        CASE WHEN bat.innings >= 5 AND bat.dismissals >= 1 AND bat.balls > 0 THEN
                 bat.runs * 0.01
               + (bat.runs * 1.0 / bat.dismissals) * 0.5
               + (bat.runs * 100.0 / bat.balls) * 0.3
             ELSE 0 END                                              AS batting_points,
        CASE WHEN bowl.balls >= 60 AND bowl.wickets >= 1 THEN
                 bowl.wickets * 2
               + (50 - bowl.runs_conceded * 1.0 / bowl.wickets) * 0.5
               + (6  - bowl.runs_conceded * 6.0 / bowl.balls) * 2
             ELSE 0 END                                              AS bowling_points,
        COALESCE(field.catches, 0) * 3 + COALESCE(field.stumpings, 0) * 5
                                                                     AS fielding_points
    FROM base AS b
    LEFT JOIN bat   ON bat.player_id   = b.player_id AND bat.format   = b.format
    LEFT JOIN bowl  ON bowl.player_id  = b.player_id AND bowl.format  = b.format
    LEFT JOIN field ON field.player_id = b.player_id AND field.format = b.format
),
ranked AS (
    SELECT *,
           batting_points + bowling_points + fielding_points AS total_points,
           RANK() OVER (
               PARTITION BY format
               ORDER BY batting_points + bowling_points + fielding_points DESC
           ) AS rank_in_format
    FROM scored
)
SELECT
    CASE r.format WHEN 'TEST' THEN 'Test' WHEN 'ODI' THEN 'ODI' ELSE 'T20' END AS format,
    r.rank_in_format                  AS rank,
    p.full_name                       AS player_name,
    ROUND(r.batting_points, 1)        AS batting_points,
    ROUND(r.bowling_points, 1)        AS bowling_points,
    r.fielding_points,
    ROUND(r.total_points, 1)          AS total_points
FROM ranked AS r
JOIN players AS p ON p.player_id = r.player_id
WHERE r.rank_in_format <= 10
ORDER BY CASE r.format WHEN 'TEST' THEN 1 WHEN 'ODI' THEN 2 ELSE 3 END,
         r.rank_in_format, p.full_name;
