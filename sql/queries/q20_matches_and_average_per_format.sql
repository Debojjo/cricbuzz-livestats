-- Q20 (Advanced): Matches played and batting average in each format.
-- Test / ODI / T20 match counts with the average in each, for players with at
-- least 20 matches in total across all formats.
--
-- One row per player: each format's figures sit in their own columns (a pivot
-- built with SUM(CASE ...); there is one career row per player and format, so
-- SUM just picks that row's value). Blank = no career row for that format.

SELECT
    p.full_name                                                       AS player_name,
    SUM(CASE WHEN c.format = 'TEST' THEN c.matches_played END)        AS test_matches,
    SUM(CASE WHEN c.format = 'TEST' THEN c.batting_avg END)           AS test_avg,
    SUM(CASE WHEN c.format = 'ODI'  THEN c.matches_played END)        AS odi_matches,
    SUM(CASE WHEN c.format = 'ODI'  THEN c.batting_avg END)           AS odi_avg,
    SUM(CASE WHEN c.format = 'T20'  THEN c.matches_played END)        AS t20_matches,
    SUM(CASE WHEN c.format = 'T20'  THEN c.batting_avg END)           AS t20_avg,
    SUM(c.matches_played)                                             AS total_matches
FROM player_career_stats AS c
JOIN players AS p ON p.player_id = c.player_id
GROUP BY p.player_id, p.full_name
HAVING SUM(c.matches_played) >= 20
ORDER BY total_matches DESC, player_name;
