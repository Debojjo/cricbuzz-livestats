-- Q25b (Advanced, companion to Q25): the quarter-by-quarter numbers.
-- For every counted quarter (>= 3 matches, player with >= 6 such quarters, last 3
-- years): matches, average runs per match, average strike rate, the change in
-- average runs against the previous counted quarter, and a trend label.
--
-- LAG() looks at the previous counted quarter of the same player. Trend:
-- Improving if runs per match rose by more than 10%, Declining if they fell by more
-- than 10%, otherwise Stable. The first quarter has nothing to compare with.

WITH quarterly AS (
    SELECT
        player_id,
        player_name,
        match_year,
        match_quarter,
        match_year * 4 + match_quarter - 1                                 AS q_index,
        COUNT(DISTINCT match_id)                                           AS matches,
        SUM(runs) * 1.0 / COUNT(DISTINCT match_id)                         AS avg_runs,
        AVG(CASE WHEN balls_faced > 0 THEN strike_rate END)                AS avg_sr
    FROM v_batting_detail
    WHERE match_date >= date('now', '-3 years')
      AND match_date <= date('now')
    GROUP BY player_id, player_name, match_year, match_quarter
    HAVING COUNT(DISTINCT match_id) >= 3
),
eligible AS (
    SELECT player_id FROM quarterly GROUP BY player_id HAVING COUNT(*) >= 6
),
compared AS (
    SELECT
        q.*,
        LAG(q.avg_runs) OVER (PARTITION BY q.player_id ORDER BY q.q_index) AS prev_avg
    FROM quarterly AS q
    JOIN eligible  AS e ON e.player_id = q.player_id
)
SELECT
    player_name,
    match_year                                         AS year,
    match_quarter                                      AS quarter,
    matches,
    ROUND(avg_runs, 1)                                 AS avg_runs_per_match,
    ROUND(avg_sr, 1)                                   AS avg_strike_rate,
    ROUND(100.0 * (avg_runs - prev_avg) / NULLIF(prev_avg, 0), 1) AS change_vs_previous_pct,
    CASE
        WHEN prev_avg IS NULL                                        THEN 'First quarter'
        WHEN (avg_runs - prev_avg) / NULLIF(prev_avg, 0) >  0.10    THEN 'Improving'
        WHEN (avg_runs - prev_avg) / NULLIF(prev_avg, 0) < -0.10    THEN 'Declining'
        ELSE 'Stable'
    END                                                AS trend
FROM compared
ORDER BY player_name, match_year, match_quarter;
