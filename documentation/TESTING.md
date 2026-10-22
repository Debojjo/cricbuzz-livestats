# Testing

```
python -m pytest -q                       # everything (about a minute on a slow disk)
python -m pytest -q tests/test_queries.py # the 27 queries only: fast
```

| File | What it proves |
|---|---|
| `test_db_schema.py` | tables, views and constraints reject bad data (foreign keys, CHECKs, UNIQUE) |
| `test_parsers.py` | every parser, run against **real saved API responses** in `tests/fixtures/` |
| `test_client.py` | cache, budget guard, retries, 403/429 handling (fake network) |
| `test_live_steps.py`, `test_ingest_fixtures.py` | dry run, fail-fast, upserts, idempotent loading |
| `test_reload_cache.py` | rebuilding from saved responses repairs data without API calls |
| `test_seed.py` | sample data is consistent (partnership runs = runs conceded, wickets = dismissals) |
| `test_enrich.py`, `test_coverage_report.py` | stadium list, series details, data coverage report |
| `test_crud.py` | validation, protection rules, transactions, injection safety |
| `test_queries.py` | each query on small hand-made data, including boundary cases |
| `test_services.py` | sample-data switch, safe custom SQL, services behind the pages |
| `test_app_pages.py` | every page loaded headlessly with Streamlit's AppTest, with clicks and forms |
| `test_bootstrap.py` | first-start setup and snapshots for hosted deployment |
| `test_docs.py` | the documentation lists every query and the required sections |

Style: `black .` and `flake8 .` (configuration in `pyproject.toml` and `.flake8`).

Manual check before a demo: start the app, open every page, flip the sample-data switch
on SQL Analytics, try `DROP TABLE players` in the custom box, add and delete a player.
