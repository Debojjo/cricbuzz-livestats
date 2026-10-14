# Cricbuzz LiveStats

Real-time cricket insights and SQL-based analytics (Python, Streamlit, SQLite,
Cricbuzz RapidAPI). Full documentation is written in the final phase.

## Quick start (so far)

    python -m venv venv
    venv\Scripts\activate
    pip install -r requirements-dev.txt
    copy .env.example .env
    python -m database.init_db
    python -m pytest -v
