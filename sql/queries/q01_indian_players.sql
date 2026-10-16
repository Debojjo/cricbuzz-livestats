-- Q1 (Beginner): Find all players who represent India.
-- Show full name, playing role, batting style and bowling style.
--
-- Business use: squad lookup for commentary teams and fantasy platforms.
-- Notes: players.country holds the national team ("India"). Roles and styles can
-- be unknown for some players, so blanks are shown as text instead of NULL.

SELECT
    full_name                             AS player_name,
    COALESCE(playing_role,  'Unknown')    AS playing_role,
    COALESCE(batting_style, 'Not listed') AS batting_style,
    COALESCE(bowling_style, 'Not listed') AS bowling_style
FROM players
WHERE country = 'India'
ORDER BY full_name;
