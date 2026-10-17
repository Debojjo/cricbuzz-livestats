-- Q9 (Intermediate): All-rounders with more than 1000 runs AND more than 50 wickets.
-- Show player name, total runs, total wickets and the format.
--
-- One row per player and format (career statistics are stored per format).
-- Roles are spelled 'Allrounder', 'Batting Allrounder', 'Bowling Allrounder' (or
-- 'All-rounder' if typed by hand), so the filter looks for the common part 'rounder'.
-- Both thresholds are strict (> 1000, > 50), as the question says.

SELECT
    p.full_name  AS player_name,
    c.runs       AS total_runs,
    c.wickets    AS total_wickets,
    CASE c.format WHEN 'TEST' THEN 'Test'
                  WHEN 'ODI'  THEN 'ODI'
                  ELSE 'T20I' END AS format
FROM player_career_stats AS c
JOIN players AS p ON p.player_id = c.player_id
WHERE p.playing_role LIKE '%rounder%'
  AND c.runs    > 1000
  AND c.wickets > 50
ORDER BY CASE c.format WHEN 'TEST' THEN 1 WHEN 'ODI' THEN 2 ELSE 3 END,
         c.runs DESC, p.full_name;
