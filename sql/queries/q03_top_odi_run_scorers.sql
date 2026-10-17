-- Q3 (Beginner): Top 10 highest run scorers in ODI cricket.
-- Show player name, total runs, batting average and number of centuries.
--
-- Business use: leaderboards for broadcasters and fantasy platforms.
-- Source: career statistics (one row per player and format), not match rows, so
-- the totals cover whole careers. Ties on runs are broken by name for a stable order.

SELECT
    p.full_name  AS player_name,
    c.runs       AS total_runs,
    c.batting_avg,
    c.centuries
FROM player_career_stats AS c
JOIN players AS p ON p.player_id = c.player_id
WHERE c.format = 'ODI'
  AND c.runs > 0
ORDER BY c.runs DESC, p.full_name
LIMIT 10;
