-- Q16 (Intermediate): How batting changes year by year (matches since 2020).
-- Show each player's average runs per match and average strike rate for each year,
-- only for players with at least 5 matches in that year.
--
-- Runs per match = total runs / number of matches (a Test player batting twice in
-- a match counts once). Strike rate is averaged over innings where at least one
-- ball was faced, so a 0-ball innings does not drag it down.

SELECT
    player_name,
    match_year                                                       AS year,
    COUNT(DISTINCT match_id)                                         AS matches_played,
    ROUND(SUM(runs) * 1.0 / COUNT(DISTINCT match_id), 2)             AS avg_runs_per_match,
    ROUND(AVG(CASE WHEN balls_faced > 0 THEN strike_rate END), 2)    AS avg_strike_rate
FROM v_batting_detail
WHERE match_year >= 2020
GROUP BY player_id, player_name, match_year
HAVING COUNT(DISTINCT match_id) >= 5
ORDER BY player_name, match_year;
