-- Q11 (Intermediate): Compare each player's runs across formats.
-- For players who played at least 2 formats, show runs in Test, ODI and T20I and
-- the overall batting average across all formats.
--
-- "Played a format" = matches_played > 0 in that format's career row.
-- Overall average = total runs / total dismissals, where dismissals = innings -
-- not outs. That is a weighted average (a plain mean of the three averages would
-- treat 5 T20 innings like 100 Test innings). It needs not-outs for every counted
-- format; if one is missing the average is left empty instead of being wrong.
-- A blank format column means the player has no row for that format.

SELECT
    p.full_name                                                AS player_name,
    SUM(CASE WHEN c.format = 'TEST' THEN c.runs END)           AS test_runs,
    SUM(CASE WHEN c.format = 'ODI'  THEN c.runs END)           AS odi_runs,
    SUM(CASE WHEN c.format = 'T20'  THEN c.runs END)           AS t20i_runs,
    CASE WHEN COUNT(c.not_outs) = COUNT(*)
         THEN ROUND(SUM(c.runs) * 1.0
                    / NULLIF(SUM(c.innings - c.not_outs), 0), 2)
    END                                                        AS overall_batting_avg,
    COUNT(*)                                                   AS formats_played
FROM player_career_stats AS c
JOIN players AS p ON p.player_id = c.player_id
WHERE c.matches_played > 0
GROUP BY p.player_id, p.full_name
HAVING COUNT(*) >= 2
ORDER BY SUM(c.runs) DESC, p.full_name;
