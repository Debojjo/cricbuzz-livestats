-- Q15 (Intermediate): Players who do well in close matches.
-- A close match is decided by fewer than 50 runs OR fewer than 5 wickets (the
-- question's own definition). Show each player's average runs, the number of close
-- matches played and how many of those their team won while they batted.
--
-- A player needs at least 3 close matches to be listed, so a single lucky innings
-- cannot top the table (the question sets no minimum; change the 3 if you like).
-- Matches won "by an innings" are never close and are not selected.

SELECT
    player_name,
    ROUND(AVG(runs), 2)                                         AS avg_runs,
    COUNT(DISTINCT match_id)                                    AS close_matches_played,
    COUNT(DISTINCT CASE WHEN team_won = 1 THEN match_id END)    AS close_matches_won
FROM v_batting_detail
WHERE (victory_type = 'runs'    AND victory_margin < 50)
   OR (victory_type = 'wickets' AND victory_margin < 5)
GROUP BY player_id, player_name
HAVING COUNT(DISTINCT match_id) >= 3
ORDER BY avg_runs DESC, close_matches_played DESC, player_name
LIMIT 25;
