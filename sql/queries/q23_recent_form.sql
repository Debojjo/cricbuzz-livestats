-- Q23 (Advanced): Recent form from each player's last 10 batting performances.
-- Average runs in the last 5 vs the last 10, strike-rate trend, number of 50+
-- scores, a consistency score from the standard deviation, and a form label.
--
-- ROW_NUMBER() numbers each player's innings newest-first, so rn 1-5 are the last
-- five and rn 1-10 the last ten. Only players with 10 such innings are rated, so
-- the two averages compare like with like. An innings counts if the batsman faced
-- at least one ball. Strike-rate trend = average of the last 5 minus the average
-- of the 5 before them (positive = scoring faster lately).
-- Consistency score = 100 - 100 x (standard deviation / average runs), floored at 0:
-- 100 = identical scores every time, 0 = very erratic.
-- Form labels (our assumption; the question does not give thresholds), judged on
-- the last 5 innings and the 50+ count of the last 10:
--   Excellent: average >= 40 and at least 3 scores of 50+
--   Good:      average >= 30 and at least 2 scores of 50+
--   Average:   average >= 20
--   Poor:      anything lower

WITH numbered AS (
    SELECT
        player_id,
        player_name,
        runs,
        strike_rate,
        ROW_NUMBER() OVER (
            PARTITION BY player_id
            ORDER BY match_date DESC, match_id DESC, innings_no DESC
        ) AS rn
    FROM v_batting_detail
    WHERE balls_faced > 0
),
last10 AS (
    SELECT
        player_id,
        player_name,
        COUNT(*)                                                       AS innings,
        AVG(CASE WHEN rn <= 5 THEN runs END)                           AS avg_last_5,
        AVG(runs)                                                      AS avg_last_10,
        AVG(CASE WHEN rn <= 5 THEN strike_rate END)                    AS sr_last_5,
        AVG(CASE WHEN rn >  5 THEN strike_rate END)                    AS sr_previous_5,
        SUM(CASE WHEN runs >= 50 THEN 1 ELSE 0 END)                    AS scores_50_plus,
        SQRT(AVG(runs * runs * 1.0) - AVG(runs) * AVG(runs))           AS std_dev
    FROM numbered
    WHERE rn <= 10
    GROUP BY player_id, player_name
    HAVING COUNT(*) = 10
)
SELECT
    player_name,
    ROUND(avg_last_5, 1)                                              AS avg_last_5,
    ROUND(avg_last_10, 1)                                             AS avg_last_10,
    ROUND(sr_last_5 - sr_previous_5, 1)                               AS strike_rate_trend,
    scores_50_plus,
    ROUND(MAX(0, 100 - 100.0 * std_dev / NULLIF(avg_last_10, 0)), 1)  AS consistency_score,
    CASE
        WHEN avg_last_5 >= 40 AND scores_50_plus >= 3 THEN 'Excellent Form'
        WHEN avg_last_5 >= 30 AND scores_50_plus >= 2 THEN 'Good Form'
        WHEN avg_last_5 >= 20                         THEN 'Average Form'
        ELSE 'Poor Form'
    END                                                               AS form
FROM last10
ORDER BY avg_last_5 DESC, scores_50_plus DESC, player_name;
