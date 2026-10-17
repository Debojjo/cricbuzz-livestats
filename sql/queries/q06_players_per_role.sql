-- Q6 (Beginner): Count the players in each playing role.
-- Show the role and the number of players with that role.
--
-- Many players come from scorecards, where the API gives no role; they are
-- counted under 'Unknown' instead of being hidden, so the totals add up to the
-- number of players in the database.

SELECT
    COALESCE(playing_role, 'Unknown') AS playing_role,
    COUNT(*)                          AS player_count
FROM players
GROUP BY COALESCE(playing_role, 'Unknown')
ORDER BY player_count DESC, playing_role;
