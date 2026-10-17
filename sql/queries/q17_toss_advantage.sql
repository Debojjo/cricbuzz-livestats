-- Q17 (Advanced): Does winning the toss help?
-- Percentage of matches won by the toss winner, split by what they chose (bat or
-- bowl), plus an overall line.
--
-- Only matches with a known toss AND a winner are used: draws, ties and no-results
-- have no winner, so they cannot say anything about the toss.

WITH decided AS (
    SELECT
        toss_decision,
        CASE WHEN winner_id = toss_winner_id THEN 1 ELSE 0 END AS toss_winner_won
    FROM matches
    WHERE toss_winner_id IS NOT NULL
      AND toss_decision  IS NOT NULL
      AND winner_id      IS NOT NULL
),
summary AS (
    SELECT toss_decision AS choice,
           COUNT(*)                                            AS matches,
           SUM(toss_winner_won)                                AS toss_winner_won,
           ROUND(100.0 * SUM(toss_winner_won) / COUNT(*), 1)   AS toss_winner_win_pct,
           CASE toss_decision WHEN 'bat' THEN 1 ELSE 2 END     AS sort_key
    FROM decided
    GROUP BY toss_decision
    UNION ALL
    SELECT 'overall',
           COUNT(*),
           SUM(toss_winner_won),
           ROUND(100.0 * SUM(toss_winner_won) / COUNT(*), 1),
           3
    FROM decided
    HAVING COUNT(*) > 0
)
SELECT choice AS toss_decision, matches, toss_winner_won, toss_winner_win_pct
FROM summary
ORDER BY sort_key;
