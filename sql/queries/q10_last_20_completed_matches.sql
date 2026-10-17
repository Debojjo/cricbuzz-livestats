-- Q10 (Intermediate): The last 20 completed matches.
-- Show description, both teams, winning team, victory margin, victory type
-- (runs / wickets) and venue. Most recent first.
--
-- A match with no winner (draw, tie, no result) is still listed; its winner shows
-- 'No winner' and the type says why ('draw', 'tie', ...). LIMIT comes after the
-- sort, so these really are the 20 newest.

SELECT
    m.match_desc                              AS match_description,
    t1.team_name                              AS team_1,
    t2.team_name                              AS team_2,
    COALESCE(w.team_name, 'No winner')        AS winning_team,
    m.victory_margin,
    COALESCE(m.victory_type, 'n/a')           AS victory_type,
    COALESCE(v.venue_name, 'Unknown venue')   AS venue
FROM matches AS m
JOIN teams AS t1 ON t1.team_id = m.team1_id
JOIN teams AS t2 ON t2.team_id = m.team2_id
LEFT JOIN teams  AS w ON w.team_id = m.winner_id
LEFT JOIN venues AS v ON v.venue_id = m.venue_id
WHERE m.state = 'Complete'
ORDER BY m.match_date DESC, m.match_id DESC
LIMIT 20;
