# The Analytics Questions

27 queries: the brief's 25 questions plus two companions (`22b`, `25b`) where one question needs two result shapes. Each lives in `sql/queries/` as one file whose header states the question, the assumptions and the data caveats. Run any of them with `python -m services.query_runner <number>` (add `--plan` for the execution plan, `--all` for a summary) or from the **SQL Analytics** page.

| # | Level | Question |
|---|---|---|
| Q1 | Beginner | Find all players who represent India. |
| Q2 | Beginner | Show all cricket matches played in the last 30 days. |
| Q3 | Beginner | Top 10 highest run scorers in ODI cricket. |
| Q4 | Beginner | Venues with a seating capacity of more than 50,000. |
| Q5 | Beginner | How many matches has each team won? |
| Q6 | Beginner | Count the players in each playing role. |
| Q7 | Beginner | Highest individual batting score in each format. |
| Q8 | Beginner | Cricket series that started in 2024. |
| Q9 | Intermediate | All-rounders with more than 1000 runs AND more than 50 wickets. |
| Q10 | Intermediate | The last 20 completed matches. |
| Q11 | Intermediate | Compare each player's runs across formats. |
| Q12 | Intermediate | Home versus away performance of international teams. |
| Q13 | Intermediate | Partnerships of 100+ runs between consecutive batsmen. |
| Q14 | Intermediate | Bowling performance at different venues. |
| Q15 | Intermediate | Players who do well in close matches. |
| Q16 | Intermediate | How batting changes year by year (matches since 2020). |
| Q17 | Advanced | Does winning the toss help? |
| Q18 | Advanced | Most economical bowlers in limited-overs cricket (ODI and T20). |
| Q19 | Advanced | Which batsmen are the most consistent? |
| Q20 | Advanced | Matches played and batting average in each format. |
| Q21 | Advanced | A weighted performance ranking, top 10 per format. |
| Q22 | Advanced | Head-to-head record of team pairs (matches in the last 3 years). |
| Q22b | Advanced | the same team pairs, venue by venue. |
| Q23 | Advanced | Recent form from each player's last 10 batting performances. |
| Q24 | Advanced | The most successful pairs of consecutive batsmen. |
| Q25 | Advanced | Career trajectory of each player over the last 3 years. |
| Q25b | Advanced | the quarter-by-quarter numbers. |

## Details and assumptions

### Q1 - Find all players who represent India.
*Beginner* - file `sql/queries/q01_indian_players.sql`

Show full name, playing role, batting style and bowling style.

Business use: squad lookup for commentary teams and fantasy platforms.
Notes: players.country holds the national team ("India"). Roles and styles can
be unknown for some players, so blanks are shown as text instead of NULL.

### Q2 - Show all cricket matches played in the last 30 days.
*Beginner* - file `sql/queries/q02_recent_matches.sql`

Include match description, both team names, venue name with city and the
match date. Most recent matches first.

Business use: a daily "what just happened" feed for broadcasters.
"Played" = state Complete. date('now') is UTC, so results do not depend on the
computer's time zone. A missing venue or city shows as 'Unknown venue'.

### Q3 - Top 10 highest run scorers in ODI cricket.
*Beginner* - file `sql/queries/q03_top_odi_run_scorers.sql`

Show player name, total runs, batting average and number of centuries.

Business use: leaderboards for broadcasters and fantasy platforms.
Source: career statistics (one row per player and format), not match rows, so
the totals cover whole careers. Ties on runs are broken by name for a stable order.

### Q4 - Venues with a seating capacity of more than 50,000.
*Beginner* - file `sql/queries/q04_large_venues.sql`

Show venue name, city, country and capacity, largest first.

Business use: planning, ticketing and "biggest grounds" features.
Capacity comes from the API where it exists and from data/venues_extra.csv
(approximate public figures) for well-known stadiums. Unknown capacity (NULL)
never passes the > test, so those venues are simply left out.

### Q5 - How many matches has each team won?
*Beginner* - file `sql/queries/q05_wins_per_team.sql`

Show team name and total wins, most wins first.

Matches with no winner (draw, tie, no result, abandoned) have winner_id NULL
and are not counted. Only teams with at least one win appear; to list every
team, start from teams and LEFT JOIN matches instead.
Grouped by team_id (not just the name) because team names are not unique.

### Q6 - Count the players in each playing role.
*Beginner* - file `sql/queries/q06_players_per_role.sql`

Show the role and the number of players with that role.

Many players come from scorecards, where the API gives no role; they are
counted under 'Unknown' instead of being hidden, so the totals add up to the
number of players in the database.

### Q7 - Highest individual batting score in each format.
*Beginner* - file `sql/queries/q07_highest_score_per_format.sql`

Show the format and the highest score (and who scored it).

Source: career statistics, which store each player's highest score per format.
The subquery finds the best score of each format; the join then names every
player who holds it (a tie shows both). T20 in our tables means T20 Internationals.

### Q8 - Cricket series that started in 2024.
*Beginner* - file `sql/queries/q08_series_started_2024.sql`

Show series name, host country, match type, start date and planned matches.

The series archive gives only a name and dates. Host country and match type are
filled from the name when it says so (see data/enrich.py), otherwise they show
'Not stated'. The planned number of matches is not in the archive data, so it
stays empty (NULL) unless we have loaded that series' matches.
Dates are ISO text, so a half-open range selects exactly the calendar year.

### Q9 - All-rounders with more than 1000 runs AND more than 50 wickets.
*Intermediate* - file `sql/queries/q09_allrounders.sql`

Show player name, total runs, total wickets and the format.

One row per player and format (career statistics are stored per format).
Roles are spelled 'Allrounder', 'Batting Allrounder', 'Bowling Allrounder' (or
'All-rounder' if typed by hand), so the filter looks for the common part 'rounder'.
Both thresholds are strict (> 1000, > 50), as the question says.

### Q10 - The last 20 completed matches.
*Intermediate* - file `sql/queries/q10_last_20_completed_matches.sql`

Show description, both teams, winning team, victory margin, victory type
(runs / wickets) and venue. Most recent first.

A match with no winner (draw, tie, no result) is still listed; its winner shows
'No winner' and the type says why ('draw', 'tie', ...). LIMIT comes after the
sort, so these really are the 20 newest.

### Q11 - Compare each player's runs across formats.
*Intermediate* - file `sql/queries/q11_player_formats.sql`

For players who played at least 2 formats, show runs in Test, ODI and T20I and
the overall batting average across all formats.

"Played a format" = matches_played > 0 in that format's career row.
Overall average = total runs / total dismissals, where dismissals = innings -
not outs. That is a weighted average (a plain mean of the three averages would
treat 5 T20 innings like 100 Test innings). It needs not-outs for every counted
format; if one is missing the average is left empty instead of being wrong.
A blank format column means the player has no row for that format.

### Q12 - Home versus away performance of international teams.
*Intermediate* - file `sql/queries/q12_home_vs_away.sql`

A team plays "at home" when the venue's country equals the team's country; any
other venue counts as away. Show matches and wins for both conditions.

Each match is seen from both teams' sides (UNION ALL of team1 and team2), then
counted per team. Matches with an unknown venue country or a team without a
country are left out because home/away cannot be decided. Draws and ties count
as matches but not as wins. The two country names must be spelled identically.

### Q13 - Partnerships of 100+ runs between consecutive batsmen.
*Intermediate* - file `sql/queries/q13_big_consecutive_partnerships.sql`

"Consecutive" = batting positions next to each other (for example #3 and #4).
Show both players, the partnership runs and the innings.

v_partnership_detail (views.sql) joins each partnership to both batters'
positions and sets is_consecutive = 1 when they differ by exactly 1. A
partnership between #1 and #3 (after #2 was out) is NOT consecutive, as the
question defines it. Exactly 100 runs qualifies (100 or more).

### Q14 - Bowling performance at different venues.
*Intermediate* - file `sql/queries/q14_bowling_by_venue.sql`

For bowlers with at least 3 matches at the same venue, show matches played,
total wickets and average economy rate at that venue. Only spells of at least
4 overs (24 balls) count, as the question asks.

Each row is one bowling spell (one innings of one match). Short spells are
filtered out BEFORE counting matches, so "3 matches" means three matches with a
full 4-over spell. Average economy = mean of the spells' economy rates.

### Q15 - Players who do well in close matches.
*Intermediate* - file `sql/queries/q15_close_match_batters.sql`

A close match is decided by fewer than 50 runs OR fewer than 5 wickets (the
question's own definition). Show each player's average runs, the number of close
matches played and how many of those their team won while they batted.

A player needs at least 3 close matches to be listed, so a single lucky innings
cannot top the table (the question sets no minimum; change the 3 if you like).
Matches won "by an innings" are never close and are not selected.

### Q16 - How batting changes year by year (matches since 2020).
*Intermediate* - file `sql/queries/q16_yearly_batting_trend.sql`

Show each player's average runs per match and average strike rate for each year,
only for players with at least 5 matches in that year.

Runs per match = total runs / number of matches (a Test player batting twice in
a match counts once). Strike rate is averaged over innings where at least one
ball was faced, so a 0-ball innings does not drag it down.

### Q17 - Does winning the toss help?
*Advanced* - file `sql/queries/q17_toss_advantage.sql`

Percentage of matches won by the toss winner, split by what they chose (bat or
bowl), plus an overall line.

Only matches with a known toss AND a winner are used: draws, ties and no-results
have no winner, so they cannot say anything about the toss.

### Q18 - Most economical bowlers in limited-overs cricket (ODI and T20).
*Advanced* - file `sql/queries/q18_economical_bowlers.sql`

Show overall economy rate and total wickets for bowlers who bowled in at least
10 matches and averaged at least 2 overs per match.

Economy = runs conceded x 6 / balls bowled over ALL their spells (a weighted
figure, so a 1-over cameo cannot distort it). Overs are shown in cricket
notation (245.3 = 245 overs and 3 balls). Top 20, lowest economy first.

### Q19 - Which batsmen are the most consistent?
*Advanced* - file `sql/queries/q19_consistent_batsmen.sql`

Average runs and standard deviation of runs per player. Only innings where the
batsman faced at least 10 balls, and only matches since 2022. A LOWER standard
deviation means steadier scoring.

SQLite has no STDDEV, so it is built from basic maths: variance = average of
the squares minus the square of the average; standard deviation = its square
root (population version: every innings is the whole data, not a sample).
A player needs at least 10 such innings; with fewer, the figure means little.

### Q20 - Matches played and batting average in each format.
*Advanced* - file `sql/queries/q20_matches_and_average_per_format.sql`

Test / ODI / T20 match counts with the average in each, for players with at
least 20 matches in total across all formats.

One row per player: each format's figures sit in their own columns (a pivot
built with SUM(CASE ...); there is one career row per player and format, so
SUM just picks that row's value). Blank = no career row for that format.

### Q21 - A weighted performance ranking, top 10 per format.
*Advanced* - file `sql/queries/q21_performance_ranking.sql`

batting  = runs x 0.01 + average x 0.5 + strike rate x 0.3
bowling  = wickets x 2 + (50 - bowling average) x 0.5 + (6 - economy) x 2
fielding = catches x 3 + stumpings x 5

Everything is computed from match-by-match records, so all three parts use the
same source and the same format. Assumptions (the question does not say):
* batting points need at least 5 innings and 1 dismissal, otherwise 0;
* bowling points need at least 10 overs (60 balls) and 1 wicket, otherwise 0;
(a bowling average or economy is meaningless without those);
* average = runs / dismissals, strike rate = runs x 100 / balls faced,
bowling average = runs conceded / wickets, economy = runs x 6 / balls.
Players tied on points share a rank (RANK). T20 here means T20 matches.

### Q22 - Head-to-head record of team pairs (matches in the last 3 years).
*Advanced* - file `sql/queries/q22_head_to_head.sql`

Only pairs that met at least 5 times. For each pair: matches, wins for each side,
win percentages, the average margin of each side's wins, and how often the side
batting first won. (The same pairs broken down by venue: see Q22b.)

A pair is stored once (smaller team id first), so A v B and B v A are the same
pair. Margins are averaged separately for wins by runs and wins by wickets,
because "30 runs" and "5 wickets" cannot be averaged together. Win percentage =
wins / all matches of the pair (draws and ties count as matches, not as wins).
"Batting first" comes from the toss (toss winner's choice); matches with no
toss record are left out of the batting-first columns only.

### Q22b - the same team pairs, venue by venue.
*Advanced* - file `sql/queries/q22b_head_to_head_by_venue.sql`

For each team against each opponent at each venue: matches and wins when
batting first, and matches and wins when bowling first.

Pairs are those with at least 5 meetings in the last 3 years (as in Q22). Each
match is seen from both sides (UNION ALL, like Q12). Matches without a toss
record cannot say who batted first and are not counted.

### Q23 - Recent form from each player's last 10 batting performances.
*Advanced* - file `sql/queries/q23_recent_form.sql`

Average runs in the last 5 vs the last 10, strike-rate trend, number of 50+
scores, a consistency score from the standard deviation, and a form label.

ROW_NUMBER() numbers each player's innings newest-first, so rn 1-5 are the last
five and rn 1-10 the last ten. Only players with 10 such innings are rated, so
the two averages compare like with like. An innings counts if the batsman faced
at least one ball. Strike-rate trend = average of the last 5 minus the average
of the 5 before them (positive = scoring faster lately).
Consistency score = 100 - 100 x (standard deviation / average runs), floored at 0:
100 = identical scores every time, 0 = very erratic.
Form labels (our assumption; the question does not give thresholds), judged on
the last 5 innings and the 50+ count of the last 10:
Excellent: average >= 40 and at least 3 scores of 50+
Good:      average >= 30 and at least 2 scores of 50+
Average:   average >= 20
Poor:      anything lower

### Q24 - The most successful pairs of consecutive batsmen.
*Advanced* - file `sql/queries/q24_best_partnership_pairs.sql`

Pairs who batted together at consecutive positions (positions differ by 1) in at
least 5 partnerships: average runs, number of partnerships over 50, highest
partnership and success rate (share of partnerships over 50). Ranked by success
rate, then average runs.

(A, B) and (B, A) are the same pair, so each pair is stored with the smaller
player id first. "Exceeded 50" means more than 50 runs, as the question says.
Tied pairs share a rank (RANK).

### Q25 - Career trajectory of each player over the last 3 years.
*Advanced* - file `sql/queries/q25_career_trajectory.sql`

Quarterly batting averages are compared quarter to quarter and fitted with a
trend line to label each career phase: Ascending, Declining or Stable.

Rules (the question's thresholds, plus two of our own marked *):
* a quarter counts only if the player batted in at least 3 matches in it;
* a player is analysed only with at least 6 such quarters;
* a quarter is "improving" / "declining" when its average runs per match moved
more than 10% against the previous counted quarter, else "stable"; *
* the career trend is the slope of a least-squares line through the quarterly
averages. Phase = Ascending if the line gains >= 1% of the player's mean per
quarter, Declining if it loses >= 1%, otherwise Stable. *
Slope = (n*Sum(xy) - Sum(x)*Sum(y)) / (n*Sum(x^2) - Sum(x)^2), x = quarter number.
Q25b lists the same quarters one by one.

### Q25b - the quarter-by-quarter numbers.
*Advanced* - file `sql/queries/q25b_quarterly_detail.sql`

For every counted quarter (>= 3 matches, player with >= 6 such quarters, last 3
years): matches, average runs per match, average strike rate, the change in
average runs against the previous counted quarter, and a trend label.

LAG() looks at the previous counted quarter of the same player. Trend:
Improving if runs per match rose by more than 10%, Declining if they fell by more
than 10%, otherwise Stable. The first quarter has nothing to compare with.
