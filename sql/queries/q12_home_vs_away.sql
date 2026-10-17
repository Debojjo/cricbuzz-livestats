-- Q12 (Intermediate): Home versus away performance of international teams.
-- A team plays "at home" when the venue's country equals the team's country; any
-- other venue counts as away. Show matches and wins for both conditions.
--
-- Each match is seen from both teams' sides (UNION ALL of team1 and team2), then
-- counted per team. Matches with an unknown venue country or a team without a
-- country are left out because home/away cannot be decided. Draws and ties count
-- as matches but not as wins. The two country names must be spelled identically.

WITH team_matches AS (
    SELECT m.match_id, m.team1_id AS team_id, m.winner_id, v.country AS venue_country
    FROM matches AS m
    JOIN venues AS v ON v.venue_id = m.venue_id
    WHERE m.match_category = 'international' AND m.state = 'Complete'
    UNION ALL
    SELECT m.match_id, m.team2_id AS team_id, m.winner_id, v.country AS venue_country
    FROM matches AS m
    JOIN venues AS v ON v.venue_id = m.venue_id
    WHERE m.match_category = 'international' AND m.state = 'Complete'
),
summary AS (
    SELECT
        t.team_id,
        t.team_name,
        SUM(CASE WHEN tm.venue_country = t.country THEN 1 ELSE 0 END) AS home_matches,
        SUM(CASE WHEN tm.venue_country = t.country
                  AND tm.winner_id = tm.team_id THEN 1 ELSE 0 END)    AS home_wins,
        SUM(CASE WHEN tm.venue_country <> t.country THEN 1 ELSE 0 END) AS away_matches,
        SUM(CASE WHEN tm.venue_country <> t.country
                  AND tm.winner_id = tm.team_id THEN 1 ELSE 0 END)    AS away_wins
    FROM team_matches AS tm
    JOIN teams AS t ON t.team_id = tm.team_id
    WHERE t.country IS NOT NULL
      AND tm.venue_country IS NOT NULL
    GROUP BY t.team_id, t.team_name
)
SELECT
    team_name,
    home_matches,
    home_wins,
    ROUND(100.0 * home_wins / NULLIF(home_matches, 0), 1) AS home_win_pct,
    away_matches,
    away_wins,
    ROUND(100.0 * away_wins / NULLIF(away_matches, 0), 1) AS away_win_pct
FROM summary
ORDER BY home_wins + away_wins DESC, team_name;
