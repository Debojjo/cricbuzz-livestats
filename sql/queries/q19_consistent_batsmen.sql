-- Q19 (Advanced): Which batsmen are the most consistent?
-- Average runs and standard deviation of runs per player. Only innings where the
-- batsman faced at least 10 balls, and only matches since 2022. A LOWER standard
-- deviation means steadier scoring.
--
-- SQLite has no STDDEV, so it is built from basic maths: variance = average of
-- the squares minus the square of the average; standard deviation = its square
-- root (population version: every innings is the whole data, not a sample).
-- A player needs at least 10 such innings; with fewer, the figure means little.

SELECT
    player_name,
    COUNT(*)                                                       AS innings,
    ROUND(AVG(runs), 2)                                            AS avg_runs,
    ROUND(SQRT(AVG(runs * runs * 1.0) - AVG(runs) * AVG(runs)), 2) AS std_dev_runs
FROM v_batting_detail
WHERE balls_faced >= 10
  AND match_year  >= 2022
GROUP BY player_id, player_name
HAVING COUNT(*) >= 10
ORDER BY std_dev_runs, avg_runs DESC, player_name
LIMIT 25;
