-- Q24 (Advanced): The most successful pairs of consecutive batsmen.
-- Pairs who batted together at consecutive positions (positions differ by 1) in at
-- least 5 partnerships: average runs, number of partnerships over 50, highest
-- partnership and success rate (share of partnerships over 50). Ranked by success
-- rate, then average runs.
--
-- (A, B) and (B, A) are the same pair, so each pair is stored with the smaller
-- player id first. "Exceeded 50" means more than 50 runs, as the question says.
-- Tied pairs share a rank (RANK).

WITH pairs AS (
    SELECT
        MIN(bat1_id, bat2_id)                              AS player_a,
        MAX(bat1_id, bat2_id)                              AS player_b,
        COUNT(*)                                           AS partnerships,
        ROUND(AVG(runs), 1)                                AS avg_runs,
        SUM(CASE WHEN runs > 50 THEN 1 ELSE 0 END)         AS over_50,
        MAX(runs)                                          AS highest,
        ROUND(100.0 * SUM(CASE WHEN runs > 50 THEN 1 ELSE 0 END) / COUNT(*), 1)
                                                           AS success_rate_pct
    FROM v_partnership_detail
    WHERE is_consecutive = 1
    GROUP BY MIN(bat1_id, bat2_id), MAX(bat1_id, bat2_id)
    HAVING COUNT(*) >= 5
)
SELECT
    RANK() OVER (ORDER BY pr.success_rate_pct DESC, pr.avg_runs DESC) AS rank,
    pa.full_name  AS player_1,
    pb.full_name  AS player_2,
    pr.partnerships,
    pr.avg_runs,
    pr.over_50,
    pr.highest,
    pr.success_rate_pct
FROM pairs AS pr
JOIN players AS pa ON pa.player_id = pr.player_a
JOIN players AS pb ON pb.player_id = pr.player_b
ORDER BY rank, pr.partnerships DESC, player_1
LIMIT 25;
