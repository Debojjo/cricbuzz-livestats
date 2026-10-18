-- Q22b (Advanced, companion to Q22): the same team pairs, venue by venue.
-- For each team against each opponent at each venue: matches and wins when
-- batting first, and matches and wins when bowling first.
--
-- Pairs are those with at least 5 meetings in the last 3 years (as in Q22). Each
-- match is seen from both sides (UNION ALL, like Q12). Matches without a toss
-- record cannot say who batted first and are not counted.

WITH recent AS (
    SELECT
        m.match_id, m.venue_id, m.winner_id,
        MIN(m.team1_id, m.team2_id) AS team_a,
        MAX(m.team1_id, m.team2_id) AS team_b,
        CASE m.toss_decision
            WHEN 'bat'  THEN m.toss_winner_id
            WHEN 'bowl' THEN CASE WHEN m.toss_winner_id = m.team1_id
                                  THEN m.team2_id ELSE m.team1_id END
        END AS batting_first_id
    FROM matches AS m
    WHERE m.state = 'Complete'
      AND m.match_date >= date('now', '-3 years')
      AND m.match_date <= date('now')
),
pairs AS (
    SELECT team_a, team_b FROM recent GROUP BY team_a, team_b HAVING COUNT(*) >= 5
),
sides AS (
    SELECT r.team_a AS team_id, r.team_b AS opponent_id, r.venue_id,
           r.batting_first_id, r.winner_id
    FROM recent AS r JOIN pairs AS p ON p.team_a = r.team_a AND p.team_b = r.team_b
    UNION ALL
    SELECT r.team_b, r.team_a, r.venue_id, r.batting_first_id, r.winner_id
    FROM recent AS r JOIN pairs AS p ON p.team_a = r.team_a AND p.team_b = r.team_b
)
SELECT
    t.team_name                                   AS team,
    o.team_name                                   AS opponent,
    COALESCE(v.venue_name, 'Unknown venue')       AS venue,
    SUM(CASE WHEN s.batting_first_id = s.team_id THEN 1 ELSE 0 END)           AS matches_batting_first,
    SUM(CASE WHEN s.batting_first_id = s.team_id
              AND s.winner_id = s.team_id THEN 1 ELSE 0 END)                  AS wins_batting_first,
    SUM(CASE WHEN s.batting_first_id IS NOT NULL
              AND s.batting_first_id <> s.team_id THEN 1 ELSE 0 END)          AS matches_bowling_first,
    SUM(CASE WHEN s.batting_first_id IS NOT NULL
              AND s.batting_first_id <> s.team_id
              AND s.winner_id = s.team_id THEN 1 ELSE 0 END)                  AS wins_bowling_first
FROM sides AS s
JOIN teams AS t ON t.team_id = s.team_id
JOIN teams AS o ON o.team_id = s.opponent_id
LEFT JOIN venues AS v ON v.venue_id = s.venue_id
GROUP BY s.team_id, s.opponent_id, s.venue_id, t.team_name, o.team_name, v.venue_name
ORDER BY t.team_name, o.team_name, venue;
