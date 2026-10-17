-- Q2 (Beginner): Show all cricket matches played in the last 30 days.
-- Include match description, both team names, venue name with city and the
-- match date. Most recent matches first.
--
-- Business use: a daily "what just happened" feed for broadcasters.
-- "Played" = state Complete. date('now') is UTC, so results do not depend on the
-- computer's time zone. A missing venue or city shows as 'Unknown venue'.

SELECT
    m.match_desc                                     AS match_description,
    t1.team_name                                     AS team_1,
    t2.team_name                                     AS team_2,
    COALESCE(v.venue_name, 'Unknown venue')
        || COALESCE(', ' || v.city, '')              AS venue,
    m.match_date
FROM matches AS m
JOIN teams AS t1 ON t1.team_id = m.team1_id
JOIN teams AS t2 ON t2.team_id = m.team2_id
LEFT JOIN venues AS v ON v.venue_id = m.venue_id
WHERE m.state = 'Complete'
  AND m.match_date >= date('now', '-30 days')
  AND m.match_date <= date('now')
ORDER BY m.match_date DESC, m.match_id DESC;
