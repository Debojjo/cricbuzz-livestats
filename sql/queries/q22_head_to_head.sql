-- Q22 (Advanced): Head-to-head record of team pairs (matches in the last 3 years).
-- Only pairs that met at least 5 times. For each pair: matches, wins for each side,
-- win percentages, the average margin of each side's wins, and how often the side
-- batting first won. (The same pairs broken down by venue: see Q22b.)
--
-- A pair is stored once (smaller team id first), so A v B and B v A are the same
-- pair. Margins are averaged separately for wins by runs and wins by wickets,
-- because "30 runs" and "5 wickets" cannot be averaged together. Win percentage =
-- wins / all matches of the pair (draws and ties count as matches, not as wins).
-- "Batting first" comes from the toss (toss winner's choice); matches with no
-- toss record are left out of the batting-first columns only.

WITH recent AS (
    SELECT
        m.match_id,
        MIN(m.team1_id, m.team2_id) AS team_a,
        MAX(m.team1_id, m.team2_id) AS team_b,
        m.winner_id,
        m.victory_type,
        m.victory_margin,
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
    SELECT
        team_a,
        team_b,
        COUNT(*)                                                       AS matches,
        SUM(CASE WHEN winner_id = team_a THEN 1 ELSE 0 END)            AS a_wins,
        SUM(CASE WHEN winner_id = team_b THEN 1 ELSE 0 END)            AS b_wins,
        AVG(CASE WHEN winner_id = team_a AND victory_type = 'runs'    THEN victory_margin END) AS a_runs,
        AVG(CASE WHEN winner_id = team_a AND victory_type = 'wickets' THEN victory_margin END) AS a_wkts,
        AVG(CASE WHEN winner_id = team_b AND victory_type = 'runs'    THEN victory_margin END) AS b_runs,
        AVG(CASE WHEN winner_id = team_b AND victory_type = 'wickets' THEN victory_margin END) AS b_wkts,
        SUM(CASE WHEN batting_first_id IS NOT NULL
                  AND winner_id = batting_first_id THEN 1 ELSE 0 END)  AS bat_first_wins,
        SUM(CASE WHEN batting_first_id IS NOT NULL AND winner_id IS NOT NULL
                  AND winner_id <> batting_first_id THEN 1 ELSE 0 END) AS bowl_first_wins
    FROM recent
    GROUP BY team_a, team_b
    HAVING COUNT(*) >= 5
)
SELECT
    ta.team_name                                  AS team_a,
    tb.team_name                                  AS team_b,
    p.matches,
    p.a_wins,
    p.b_wins,
    ROUND(100.0 * p.a_wins / p.matches, 1)        AS a_win_pct,
    ROUND(100.0 * p.b_wins / p.matches, 1)        AS b_win_pct,
    ROUND(p.a_runs, 1)                            AS a_avg_runs_margin,
    ROUND(p.a_wkts, 1)                            AS a_avg_wkts_margin,
    ROUND(p.b_runs, 1)                            AS b_avg_runs_margin,
    ROUND(p.b_wkts, 1)                            AS b_avg_wkts_margin,
    p.bat_first_wins,
    p.bowl_first_wins
FROM pairs AS p
JOIN teams AS ta ON ta.team_id = p.team_a
JOIN teams AS tb ON tb.team_id = p.team_b
ORDER BY p.matches DESC, ta.team_name, tb.team_name;
