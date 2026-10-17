-- Q5 (Beginner): How many matches has each team won?
-- Show team name and total wins, most wins first.
--
-- Matches with no winner (draw, tie, no result, abandoned) have winner_id NULL
-- and are not counted. Only teams with at least one win appear; to list every
-- team, start from teams and LEFT JOIN matches instead.
-- Grouped by team_id (not just the name) because team names are not unique.

SELECT
    t.team_name,
    COUNT(*) AS total_wins
FROM matches AS m
JOIN teams AS t ON t.team_id = m.winner_id
GROUP BY t.team_id, t.team_name
ORDER BY total_wins DESC, t.team_name;
