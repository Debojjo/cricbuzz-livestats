-- Q14 (Intermediate): Bowling performance at different venues.
-- For bowlers with at least 3 matches at the same venue, show matches played,
-- total wickets and average economy rate at that venue. Only spells of at least
-- 4 overs (24 balls) count, as the question asks.
--
-- Each row is one bowling spell (one innings of one match). Short spells are
-- filtered out BEFORE counting matches, so "3 matches" means three matches with a
-- full 4-over spell. Average economy = mean of the spells' economy rates.

SELECT
    player_name                          AS bowler,
    venue_name                           AS venue,
    COUNT(DISTINCT match_id)             AS matches_played,
    SUM(wickets)                         AS total_wickets,
    ROUND(AVG(economy_calc), 2)          AS avg_economy
FROM v_bowling_detail
WHERE venue_id IS NOT NULL
  AND balls >= 24
GROUP BY player_id, venue_id, player_name, venue_name
HAVING COUNT(DISTINCT match_id) >= 3
ORDER BY matches_played DESC, avg_economy, bowler;
