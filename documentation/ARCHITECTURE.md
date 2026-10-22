# Architecture

## Layers

```
                    ┌─────────────────────────────────────────┐
                    │  STREAMLIT PAGES (main.py, views/, pages/)│
                    │  Home · Live Matches · Top Players ·    │
                    │  SQL Analytics · CRUD · Settings        │
                    └───────────────────┬─────────────────────┘
                                        │ function calls only (no SQL, no HTTP)
                    ┌───────────────────▼─────────────────────┐
                    │          SERVICES  (services/)          │
                    │ analytics · match · player · stats ·    │
                    │ crud · query_runner                     │
                    └───────┬─────────────────────┬───────────┘
                            │                     │
          ┌─────────────────▼───────┐   ┌─────────▼────────────────┐
          │  API LAYER  (api/)      │   │  DATA LAYER  (database/) │
          │  cricbuzz_client        │   │  schema · views ·        │
          │  (cache + budget guard) │   │  repositories            │
          │  parsers · endpoints    │   └─────────▲────────────────┘
          └────────────┬────────────┘             │
                       │ HTTPS + key              │ upserts
          ┌────────────▼────────────┐   ┌─────────┴────────────────┐
          │  CRICBUZZ API (RapidAPI)│──▶│  SQLITE  data/cricbuzz.db │
          └─────────────────────────┘   └──────────────────────────┘
                 ingestion: data/ingest.py (command line, never from the UI)
```

Dependencies point downwards only: `pages → services → (api | database) → utils / config`.
Nothing below a layer imports from above it.

## Data flow

1. **Ingestion** (command line): `data.ingest --live <step> --confirm` asks the client for
   an endpoint. The client returns a saved copy if one exists (free) or spends one API
   request, saves the response in `data/raw/`, and logs the call. Parsers turn the JSON
   into clean rows and repositories upsert them (re-running never duplicates).
2. **Sample data**: `data.seed_sample_data` plays out fictional teams ball by ball and
   writes rows flagged `is_sample = 1`.
3. **Analytics**: a service opens a *read-only* connection, optionally hiding sample rows,
   runs a stored query and hands a DataFrame to the page.
4. **Live pages**: only a button press calls the API; the answer is cached on disk.
5. **CRUD**: forms → validators → one transaction → database constraints as the last
   defence. Real API rows are protected.

## Cross-cutting rules

| Concern | Where | Rule |
|---|---|---|
| Secrets | `.env`, `config.py` | never committed; hosted apps use platform secrets |
| Connections | `utils/db_connection.py` | the only place connections are made; foreign keys on |
| API quota | `api/cricbuzz_client.py` | cache first, budget guard, no automatic retries on 403/429 |
| Provenance | `is_sample` column | 0 = from the API, 1 = generated or typed by hand |
| Errors | services and pages | readable messages, never a stack trace in the UI |
