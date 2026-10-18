-- Q25 (Advanced): Career trajectory of each player over the last 3 years.
-- Quarterly batting averages are compared quarter to quarter and fitted with a
-- trend line to label each career phase: Ascending, Declining or Stable.
--
-- Rules (the question's thresholds, plus two of our own marked *):
--   * a quarter counts only if the player batted in at least 3 matches in it;
--   * a player is analysed only with at least 6 such quarters;
--   * a quarter is "improving" / "declining" when its average runs per match moved
--     more than 10% against the previous counted quarter, else "stable"; *
--   * the career trend is the slope of a least-squares line through the quarterly
--     averages. Phase = Ascending if the line gains >= 1% of the player's mean per
--     quarter, Declining if it loses >= 1%, otherwise Stable. *
-- Slope = (n*Sum(xy) - Sum(x)*Sum(y)) / (n*Sum(x^2) - Sum(x)^2), x = quarter number.
-- Q25b lists the same quarters one by one.

WITH quarterly AS (
    SELECT
        player_id,
        player_name,
        match_year * 4 + match_quarter - 1                      AS q_index,
        COUNT(DISTINCT match_id)                                AS matches,
        SUM(runs) * 1.0 / COUNT(DISTINCT match_id)              AS avg_runs
    FROM v_batting_detail
    WHERE match_date >= date('now', '-3 years')
      AND match_date <= date('now')
    GROUP BY player_id, player_name, match_year, match_quarter
    HAVING COUNT(DISTINCT match_id) >= 3
),
eligible AS (
    SELECT player_id FROM quarterly GROUP BY player_id HAVING COUNT(*) >= 6
),
series AS (
    SELECT
        q.player_id,
        q.player_name,
        q.avg_runs,
        q.q_index - MIN(q.q_index) OVER (PARTITION BY q.player_id)      AS x,
        LAG(q.avg_runs) OVER (PARTITION BY q.player_id ORDER BY q.q_index) AS prev_avg
    FROM quarterly AS q
    JOIN eligible  AS e ON e.player_id = q.player_id
),
stats AS (
    SELECT
        player_id,
        player_name,
        COUNT(*)                                  AS n,
        AVG(avg_runs)                             AS mean_runs,
        SUM(x * 1.0)                              AS sx,
        SUM(avg_runs)                             AS sy,
        SUM(x * avg_runs)                         AS sxy,
        SUM(x * x * 1.0)                          AS sxx,
        SUM(CASE WHEN (avg_runs - prev_avg) / NULLIF(prev_avg, 0) >  0.10 THEN 1 ELSE 0 END) AS improving,
        SUM(CASE WHEN (avg_runs - prev_avg) / NULLIF(prev_avg, 0) < -0.10 THEN 1 ELSE 0 END) AS declining,
        SUM(CASE WHEN prev_avg IS NOT NULL
                  AND ABS((avg_runs - prev_avg) / NULLIF(prev_avg, 0)) <= 0.10 THEN 1 ELSE 0 END) AS stable
    FROM series
    GROUP BY player_id, player_name
),
slopes AS (
    SELECT *, (n * sxy - sx * sy) / NULLIF(n * sxx - sx * sx, 0) AS slope FROM stats
)
SELECT
    player_name,
    n                                   AS quarters_analysed,
    ROUND(mean_runs, 1)                 AS avg_runs_per_match,
    ROUND(slope, 2)                     AS runs_change_per_quarter,
    improving                           AS improving_quarters,
    declining                           AS declining_quarters,
    stable                              AS stable_quarters,
    CASE
        WHEN slope / NULLIF(mean_runs, 0) >=  0.01 THEN 'Career Ascending'
        WHEN slope / NULLIF(mean_runs, 0) <= -0.01 THEN 'Career Declining'
        ELSE 'Career Stable'
    END                                 AS career_phase
FROM slopes
ORDER BY slope / NULLIF(mean_runs, 0) DESC, player_name;
