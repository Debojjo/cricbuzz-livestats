# API mapping

Provider: *Cricbuzz Cricket* on RapidAPI. All requests are `GET` with the headers
`X-RapidAPI-Key` and `X-RapidAPI-Host`. Plan: Basic, **200 requests per month (hard
limit)**. URL templates live in `api/endpoints.py`.

| Endpoint (template) | Fills | Notes |
|---|---|---|
| `matches/v1/recent` | matches, teams, venues (partial), series | result text parsed into winner, type, margin |
| `matches/v1/live` | Live page only | URL pattern assumed from `recent`; not stored |
| `mcenter/v1/{matchId}` | toss, venue country | lower-case keys; toss text such as "X opt to bowl" |
| `mcenter/v1/{matchId}/scard` | batting, bowling, fielding, partnerships | bowler `balls` field is really overs x 10, so balls are derived from overs |
| `stats/v1/player/{playerId}` | player profile | `DoBFormat`, role, styles |
| `stats/v1/player/{playerId}/batting` | career stats (transposed table) | `T20` column = T20I; `IPL` column ignored |
| `stats/v1/player/{playerId}/bowling` | career wickets, average, economy | |
| `stats/v1/topstats/{id}?statsType&matchType` | leaderboards | innings-level lists (`highestScore`) keep each player's best row only |
| `venues/v1/{venueId}` | capacity, country | no id in the response body |
| `teams/v1/international` | teams | section header rows have no id |
| `teams/v1/{teamId}/players` | squad roles and styles | role comes from the section header |
| `series/v1/archives/{type}?year` | series list | only name and dates |

## Quota strategy

1. **Cache first.** Every response is saved in `data/raw/`; a repeat request is free.
2. **Budget guard.** Each real request is logged in `api_call_log`; the client refuses to
   run once only the 20-request reserve is left.
3. **Dry run by default.** `data.ingest --live <step>` prints the plan and its cost; it
   spends nothing until `--confirm` is added.
4. **Fail fast.** A response that does not parse stops a step after 3 errors, so a wrong
   URL costs 3 calls, not 50.
5. **No automatic calls.** The UI calls the API only after a button press.
6. **Rebuild without the API.** `python -m data.reload_cache` re-reads every saved response
   (0 calls), so parser fixes never cost quota.

## Quirks handled in `api/parsers.py`

Key casing differs per endpoint; numbers arrive as strings (`"11,600"`, `"199*"`); career
tables are transposed; one batting style has two spellings; overs `3.5` mean 23 balls;
leaderboards can list one player several times; substitutes appear in dismissal text.
