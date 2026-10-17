-- Q18 (Advanced): Most economical bowlers in limited-overs cricket (ODI and T20).
-- Show overall economy rate and total wickets for bowlers who bowled in at least
-- 10 matches and averaged at least 2 overs per match.
--
-- Economy = runs conceded x 6 / balls bowled over ALL their spells (a weighted
-- figure, so a 1-over cameo cannot distort it). Overs are shown in cricket
-- notation (245.3 = 245 overs and 3 balls). Top 20, lowest economy first.

SELECT
    player_name                                       AS bowler,
    COUNT(DISTINCT match_id)                          AS matches_played,
    (SUM(balls) / 6) || '.' || (SUM(balls) % 6)       AS overs_bowled,
    ROUND(SUM(runs_conceded) * 6.0 / SUM(balls), 2)   AS economy_rate,
    SUM(wickets)                                      AS total_wickets
FROM v_bowling_detail
WHERE format IN ('ODI', 'T20')
  AND balls > 0
GROUP BY player_id, player_name
HAVING COUNT(DISTINCT match_id) >= 10
   AND SUM(balls) >= 12 * COUNT(DISTINCT match_id)
ORDER BY economy_rate, total_wickets DESC, bowler
LIMIT 20;
