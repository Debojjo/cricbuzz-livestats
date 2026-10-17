-- Q7 (Beginner): Highest individual batting score in each format.
-- Show the format and the highest score (and who scored it).
--
-- Source: career statistics, which store each player's highest score per format.
-- The subquery finds the best score of each format; the join then names every
-- player who holds it (a tie shows both). T20 in our tables means T20 Internationals.

SELECT
    CASE c.format WHEN 'TEST' THEN 'Test'
                  WHEN 'ODI'  THEN 'ODI'
                  ELSE 'T20I' END AS format,
    c.highest_score,
    p.full_name                   AS player_name
FROM player_career_stats AS c
JOIN players AS p ON p.player_id = c.player_id
WHERE c.highest_score = (
        SELECT MAX(c2.highest_score)
        FROM player_career_stats AS c2
        WHERE c2.format = c.format
      )
ORDER BY CASE c.format WHEN 'TEST' THEN 1 WHEN 'ODI' THEN 2 ELSE 3 END,
         p.full_name;
