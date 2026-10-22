# Demo video script (about 8 minutes)

## Before you record (10 minutes)

- Run `python -m pytest -q` once: all green.
- `python -m data.coverage_report` and `python -m services.query_runner --all`: all queries run.
- Check the API quota on the **Settings** page. Keep at least 25 requests for the demo.
- Close other tabs and notifications; browser zoom 100%, window wide, sidebar open.
- Have two terminals ready: one running `streamlit run main.py`, one in the project folder.
- Record at 1080p. Speak slowly; pause after each click so viewers can read.

## Timeline

| Time | Show | Say (in your own words) |
|---|---|---|
| 0:00 | Home page | The problem: cricket data is scattered, live, and needs history. This dashboard joins the Cricbuzz API with a SQL database. Name the five pages. |
| 0:45 | README / architecture diagram | Layers: pages → services → API client and database. No SQL in pages. Dependencies point downwards. |
| 1:30 | Terminal: `python -m data.ingest --live recent` (dry run) | The API plan allows 200 requests a month, so every load is a **dry run** until `--confirm`. Responses are cached, a budget guard keeps a reserve, a parse failure stops after 3 calls. |
| 2:15 | Settings page | Quota meter and the real-vs-sample table. Explain the sample data: the free plan gives days of history, so years-long questions use **fictional, flagged** teams; real data is never mixed with invented numbers under real names. |
| 3:00 | Live Matches | Recent results tab: pick a match, show the scorecard. Live tab: explain the button, the 15-minute cache, and the friendly message when there is no key or quota. |
| 3:45 | Top Players | Most runs, ODI, chart. Switch to Highest score. Mention the leaderboard bug you found (innings-level rows overwrote each other) and the free repair with `reload_cache`. |
| 4:30 | SQL Analytics | Q3, then Q12 (home vs away, CTE), Q21 (window function ranking), Q23 (form with ROW_NUMBER), Q25 (trend). Open *SQL* and *Execution plan* on one. Flip the **sample switch** on Q5 to show real-only results. |
| 6:00 | Custom query box | Run a SELECT. Type `DROP TABLE players`: refused. Explain the two locks: validator plus read-only connection. |
| 6:40 | CRUD | Add a player, edit the role, delete it. Try to edit Virat Kohli: protected, with a clear message. Show a validation error (empty name). Explain transactions. |
| 7:20 | Terminal: `pytest -q` | The test suite: real API samples as fixtures, boundary cases, pages tested headlessly. |
| 7:45 | Close | Known limitations (history, roles), what you would add (paid plan, PostgreSQL, predictions). Thank the viewer. |

## Tips

- If something fails on camera, say what you expect and move on; do not restart.
- Do not show your API key: keep `.env` closed, and avoid the terminal history.
- Keep the video under 10 minutes.
