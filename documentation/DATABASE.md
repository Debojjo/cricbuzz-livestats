# Database

SQLite, 11 tables, 4 views, 25 indexes. The schema is in `database/schema.sql` and
`database/views.sql`; SQLite-specific details are confined to those files and to
`utils/db_connection.py`, so moving to PostgreSQL means changing only those.

## Entity relationships

```
 series 1──N matches N──1 venues
                │  │
   team1/team2  │  │ toss_winner / winner
        (N:1)   │  │ (N:1)
              teams
                │ 1
   ┌────────────┼──────────────────┬─────────────────┐
   │ N          │ N                │ N               │ N
batting_      bowling_         fielding_        partnerships
performances  performances     performances          │
   │ N:1        │ N:1             │ N:1              │ N:1 (two batters)
   └──────── players ─────────────┴──────────────────┘
                │ 1
                │ N
        player_career_stats           api_call_log (stand-alone)
```

## Tables

| Table | One row per | Key columns |
|---|---|---|
| `teams` | team | `team_id` (Cricbuzz id), `team_name`, `short_name`, `country`, `team_type` |
| `players` | player | `player_id`, `full_name`, `country`, `playing_role`, `batting_style`, `bowling_style`, `date_of_birth` |
| `venues` | ground | `venue_id`, `venue_name`, `city`, `country`, `capacity` |
| `series` | series | `series_id`, `series_name`, `host_country`, `match_type`, `start_date`, `end_date`, `total_matches` |
| `matches` | match | `match_id`, `format` (TEST/ODI/T20), `match_date`, `team1_id`, `team2_id`, toss and result columns |
| `batting_performances` | batter per innings | runs, balls, fours, sixes, `batting_position`, `out_desc` |
| `bowling_performances` | bowler per innings | `balls` (derived from overs), maidens, runs, wickets |
| `fielding_performances` | fielder per match | catches, stumpings (read from dismissal text) |
| `partnerships` | partnership | `wicket_no`, `bat1_id`, `bat2_id`, runs, balls |
| `player_career_stats` | player and format | runs, averages, centuries, wickets, economy |
| `api_call_log` | API request or cache hit | endpoint, parameters, status, `from_cache` |

## Views

| View | Purpose |
|---|---|
| `v_match_results` | a match with every id replaced by a name |
| `v_batting_detail` | batting rows with player, year, quarter, opponent, `team_won` |
| `v_bowling_detail` | bowling rows with `economy_calc` recomputed from balls |
| `v_partnership_detail` | partnerships with both batters' positions and `is_consecutive` |

## Conventions and constraints

- Primary keys reuse Cricbuzz ids, so reloading updates rows instead of duplicating them.
- Dates are ISO text (`YYYY-MM-DD`). Format codes are `TEST`, `ODI`, `T20` everywhere
  (in career stats, `T20` holds the T20 International column).
- `is_sample`: `0` real API data, `1` generated sample data or manual entry.
- CHECK constraints: valid formats, toss decisions and victory types; no negative runs;
  a match cannot name a winner outside its two teams; a team cannot play itself.
- UNIQUE constraints stop duplicate performance rows. Foreign keys are enforced on every
  connection (SQLite ignores them otherwise).
- Normalisation: 3NF, with one deliberate exception: `player_career_stats` stores
  aggregates because the API supplies them and our match rows never cover whole careers.
