# Interview and viva preparation

50 questions with answers about *this* project, grouped by topic. Rephrase the answers in your own words and be ready to open the code behind each one.

## PROJECT AND VIVA

### 1. What problem does the project solve?
Cricket data is spread across live feeds and historic tables, and few tools join them. The dashboard loads data from the Cricbuzz API into a SQL database and offers live pages, leaderboards, 25 analytical questions and data management in one app. It serves media teams, fantasy platforms, analysts and students, the use cases in the brief.

### 2. Walk me through the architecture.
Streamlit pages call services; services call either the API layer (a cached, budget-guarded client plus parsers) or the data layer (schema, views, repositories); both sit on utils and config. Pages contain no SQL or HTTP, and dependencies point only downwards. Ingestion is a command-line job, never part of a page load.

### 3. Why SQLite, and could you move to PostgreSQL?
SQLite needs no server, ships with Python and makes the project easy to run and review. The brief asks for a database-agnostic design, so connection handling is centralised in `utils/db_connection.py` and SQLite-specific syntax lives only there and in `schema.sql`. For several simultaneous editors I would move to PostgreSQL, because SQLite allows one writer at a time.

### 4. How does data get from the API to the dashboard?
An ingestion step asks the client for an endpoint; the client returns a saved copy or spends one request and saves the answer. A parser turns the JSON into clean rows, and repositories upsert them into SQLite. Pages then read through services. Live pages call the API only after a button press.

### 5. How did you handle the 200-requests-a-month limit?
Five layers: a disk cache so nothing is fetched twice, a budget guard that logs every call and keeps a 20-request reserve, dry-run-by-default ingestion that prints the cost first, fail-fast probing so a wrong URL costs 3 calls rather than 50, and a reload-from-cache tool so parser fixes cost nothing.

### 6. Why is there sample data, and is it honest?
The free plan returns only a few days of history, but questions like Q16 or Q25 need years. I generate fictional teams ('Sample XI ...') ball by ball, so every number is internally consistent, and flag every row with `is_sample = 1`. The Analytics page can hide it, the Home and Settings pages say it openly, and no real team or player name is ever attached to invented numbers.

### 7. What was the hardest bug?
The leaderboard loader. The 'highest scores' list contains one row per innings, so a player appears several times, and my upsert let the last (lowest) row overwrite the best one. Q7 showed Hayden's 380 instead of Lara's 400. It also saved an innings' strike rate as a career strike rate. I fixed the parser, added tests that reproduce the bug, and repaired the database from the saved responses with no API calls.

### 8. How do you ensure data quality?
Layers: parsers normalise quirks (string numbers, key casing, two spellings of batting hand), constraints reject impossible rows (negative runs, a winner outside the match), tests cross-check endpoints (a player's career row matches the leaderboard), and a coverage report shows which questions have enough real data and where NULLs remain.

### 9. What would you do with more time or a paid API plan?
Replace sample history with real multi-year data, schedule refresh jobs, add live auto-refresh, move to PostgreSQL, and build match-prediction models from the head-to-head and form queries. I would also add an audit log for CRUD edits.

### 10. How did you test the project?
About 260 automated tests: parsers against real saved API responses, the client with a fake network, every query on hand-made data with boundary cases, constraint tests on the schema, CRUD rules, and every Streamlit page loaded headlessly with AppTest including clicks and forms. Style is checked with black and flake8.

## TECHNICAL

### 11. What is an idempotent load, and how did you achieve it?
Running it twice leaves the same result. Primary keys are Cricbuzz ids and every write is an upsert (`INSERT ... ON CONFLICT DO UPDATE`), so reloading updates rows instead of duplicating them. A test loads the fixtures twice and checks the counts.

### 12. Why parse overs as balls?
Overs `3.5` mean 3 overs and 5 balls, which is 23 balls, not 3.5 x 6 = 21. The API's own `balls` field is overs x 10, which is wrong as balls. Economy and the 2-overs-per-match rule are computed from balls derived from the overs text.

### 13. How do you protect secrets?
The API key lives in `.env`, which is git-ignored; `.env.example` has empty values. Hosted apps use platform secrets. I recommend not putting the key in a public app, because anyone could spend the quota. A check of the Git history for the key name should print nothing.

### 14. What is a view, and why use them here?
A saved query that behaves like a table. `v_batting_detail` joins batting rows with player, year, quarter, opponent and whether the team won, so Q15 to Q25 stay short and consistent. `v_partnership_detail` computes whether two batters were consecutive.

### 15. Explain the layered design and the dependency rule.
Pages call services; services call the API or data layer; those use utils and config. Nothing imports upwards. It makes each part testable alone (services are tested without Streamlit) and lets me change the database or the API client without touching the pages.

### 16. How does the custom SQL box stay safe?
Two locks. A validator accepts only one SELECT or WITH statement. The connection is also opened read-only and set to `query_only`, so even `WITH x AS (SELECT 1) DELETE ...`, which passes the validator, is refused by the database. Results are limited to 1,000 rows and queries stop after 5 seconds with a progress handler.

### 17. How does the 'include sample data' switch work?
On a read-only connection I create temporary views with the same names as the tables, each filtering `is_sample = 0`, and re-create the saved views as temporary views. SQLite resolves unqualified names to temporary objects first, so every query silently sees only real rows. Nothing is written to the file.

### 18. What is a transaction and where did you use one?
A group of writes that all succeed or all roll back. `transaction()` commits on success and rolls back on any exception. The CRUD module uses it, and `create_batting_rows` saves a batch all-or-nothing, which a test proves.

## SQL

### 19. What is the difference between WHERE and HAVING?
WHERE filters rows before grouping; HAVING filters groups after aggregation. In Q14 `balls >= 24` is a WHERE (which spells count), and `COUNT(DISTINCT match_id) >= 3` is a HAVING (which bowler-venue groups qualify).

### 20. When did you need LEFT JOIN instead of JOIN?
Whenever the other side is optional. In Q10 the winner uses LEFT JOIN because draws and ties have no winner; a plain JOIN would silently drop those matches. In Q2 the venue is a LEFT JOIN so matches without a venue still appear.

### 21. SQLite has no STDDEV. How did you compute it?
Variance = AVG(x*x) - AVG(x)^2, and the standard deviation is its square root, registered as a SQL function on every connection for portability. I used the population version because every innings is the whole data. Q19 and Q23 use it.

### 22. Which window functions did you use and why?
`RANK() OVER (PARTITION BY format ORDER BY points DESC)` in Q21 ranks within each format; `ROW_NUMBER()` in Q23 numbers each player's innings newest-first so rn 1-5 are the last five; `LAG()` in Q25 compares each quarter with the previous one; `MIN() OVER` centres the quarter index for the regression.

### 23. What is a CTE and why use it in Q12 and Q17?
A named temporary result defined with WITH. In Q12 `team_matches` sees each match from both teams' sides with UNION ALL, so home and away can be counted per team. In Q17 the `decided` CTE is reused for the per-decision rows and the overall row.

### 24. How does conditional aggregation pivot rows into columns (Q11, Q20)?
`SUM(CASE WHEN format = 'TEST' THEN runs END)` adds only Test rows, putting each format in its own column. A format the player never played gives NULL (blank), which is different from 0 runs.

### 25. Why GROUP BY team_id and not only the name (Q5)?
Team names are not unique: domestic and national teams can share one. Grouping by id keeps them separate, and a test creates two different teams both called 'India'.

### 26. How do indexes help? Give an example.
Q2 filters by date, and `idx_matches_date` lets SQLite jump to the 30-day range instead of scanning every match; the plan shows `SEARCH m USING INDEX idx_matches_date`. Q10 even avoids sorting, because it reads the date index newest-first and stops after 20 rows.

### 27. What does EXPLAIN QUERY PLAN show, and what is a covering index?
How SQLite will execute a query: SEARCH (index lookup) vs SCAN (read everything), join order, temporary sort structures. A covering index contains every column the query needs, so SQLite never opens the table. Q5 counts wins using `idx_matches_winner` alone.

### 28. Correlated subquery or join in Q7?
Q7 keeps rows whose score equals the maximum of their own format, using a correlated subquery that runs per row; it also keeps ties. At about 150 rows it costs nothing; at millions I would compute the maximum once per format in a grouped subquery and join to it.

## PYTHON

### 29. What is a context manager and where do you use it?
An object used with `with` that sets something up and always cleans it up. `transaction()` (built with `@contextmanager`) opens a connection, commits on success, rolls back on error and always closes it.

### 30. Why are SQL values passed as `?` parameters, never in f-strings?
Parameters separate data from code, which prevents SQL injection and handles quoting. Table and column names cannot be parameters, so the few that are dynamic come from our own constants and are checked against the real schema. A test searches for `'; DROP TABLE players; --` and the table survives.

### 31. How does the API client handle errors and retries?
Network errors and 5xx replies are retried with exponential backoff; 401/403 and 429 stop immediately with a readable message, because retrying a bad key or a rate limit only wastes quota. Invalid JSON raises an error, and every attempt is logged.

### 32. How do you keep Python code consistent?
PEP 8 enforced with `black` (formatting) and `flake8` (lint), docstrings on every function, type hints on public functions, small modules with one responsibility, and tests for each module.

### 33. What is a fake (test double) and where do you use one?
A stand-in that replaces something slow or external. `FakeSession` replays queued HTTP responses so the client tests spend no quota, and `FakeClient` feeds saved JSON into the live-step and page-service tests.

### 34. How do you read messy API numbers safely?
`to_int` and `to_float` accept strings like `'11,600'` and `'199*'` and return None for `''` or `'-'` instead of crashing. Parsers use `.get()` with defaults, so a missing key never raises.

## STREAMLIT

### 35. How does Streamlit's execution model affect your design?
The whole script reruns on every interaction. So expensive or quota-costing work is behind a button or a disk cache, state that must survive a rerun is kept in `st.session_state`, and database reads are fast enough to run on each rerun.

### 36. How are multiple pages organised?
`main.py` is the entry point and every file in `pages/` becomes a sidebar page, ordered by its number prefix. A stray `__init__.py` there would appear as a page, so a test checks the folder.

### 37. When do you use st.form?
For the CRUD forms, so typing in several fields does not rerun the script until the user presses submit. Validation errors are then shown together.

### 38. How did you test the Streamlit pages?
With Streamlit's `AppTest`: each page runs headlessly against a temporary database, with clicks, form submissions and the sample-data toggle. The tests assert there is no exception and that the visible results are right (for example that switching the toggle reduces the row count).

### 39. How do you protect the API quota inside the UI?
The UI never calls the API on load. Live data needs a button press, responses are cached on disk for 15 minutes to an hour, the budget guard refuses calls near the limit, and the Settings page shows the quota.

## API

### 40. What do you need to authenticate against the Cricbuzz API?
Two headers on every request: `X-RapidAPI-Key` (your subscription key) and `X-RapidAPI-Host`. The key is read from the environment, never hard-coded.

### 41. What are HTTP 403 and 429 and how do you react?
403 means the key is wrong or you are not subscribed; 429 means a rate limit was hit. Both stop the step at once with a clear message, because retrying wastes quota.

### 42. Why did parsers need so many fixes for the JSON?
The endpoints are inconsistent: some use camelCase and some lower-case keys, numbers are strings, career tables are transposed, section headers sit inside lists, and leaderboards can list a player several times. All of that is isolated in `api/parsers.py` and covered by tests on real responses.

### 43. What caching strategy did you use and why?
A disk cache keyed by endpoint and parameters: historical data is kept forever, live data for 15 minutes and scorecards for an hour. It saves quota, makes the tests deterministic, and lets me rebuild the database without the API.

### 44. How would you handle pagination or very large responses?
The endpoints I used return a single page, but `series/archives` has a `lastId` parameter for paging. I would loop with the last id until empty, caching each page, and keep the budget guard in the loop.

## SYSTEM DESIGN

### 45. How would the system scale to millions of matches?
Move to PostgreSQL with proper partitioning by year, keep the same indexes, pre-compute heavy analytics (Q21 to Q25) into summary tables refreshed by a scheduled job, and serve pages from those. Add a read replica for dashboards.

### 46. How would you support real-time scores for many users?
Poll the API once on the server (not per user), store the latest payload in a shared cache such as Redis for a few seconds, and push updates to browsers via websockets or server-sent events, so thousands of viewers cost one upstream request.

### 47. What breaks with several people editing data at once?
SQLite allows one writer at a time, so writes queue and can time out. A multi-user version needs PostgreSQL, row-level locking or optimistic version checks, user accounts and an audit log.

### 48. How would you deploy and monitor it?
A Docker image on a managed platform with the database as a managed service, secrets in the platform's secret store, health checks, structured logs, and alerts on API errors and on quota use (the `api_call_log` table already records every call).

### 49. How would you keep data fresh without overspending the API?
A scheduled job that fetches only what changed (recent matches, then scorecards for new completed matches), uses the same cache and budget guard, and refreshes live matches on a short interval only while a match is in progress.

### 50. What are the risks of relying on a third-party API?
Quota or price changes, shape changes, outages and licensing limits. Mitigations: a cache and local database so the app works without the API, parsers tolerant of missing fields, tests on saved real responses, and a single place (`endpoints.py`) to repoint URLs.
