"""Central configuration.

Everything that can change between machines (keys, paths) comes from the
environment / a local ``.env`` file. Nothing secret is hardcoded here.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


def _resolve_path(value: str) -> Path:
    """Turn a (possibly relative) path from the environment into an absolute one."""
    path = Path(value)
    return path if path.is_absolute() else BASE_DIR / path


# --- Database ---------------------------------------------------------------
DB_PATH = _resolve_path(os.getenv("DB_PATH", "data/cricbuzz.db"))
SCHEMA_FILE = BASE_DIR / "database" / "schema.sql"
VIEWS_FILE = BASE_DIR / "database" / "views.sql"

# --- CRUD safety ---------------------------------------------------------------
# Real API rows (is_sample = 0) are read-only in the CRUD module unless this is
# switched on. Rows created by hand or by the sample generator can be edited.
CRUD_ALLOW_EDIT_REAL = os.getenv("CRUD_ALLOW_EDIT_REAL", "0") == "1"
MANUAL_ID_START = 9_000_001

# --- Cricbuzz API (RapidAPI) -------------------------------------------------
RAPIDAPI_KEY = os.getenv("RAPIDAPI_KEY", "")
RAPIDAPI_HOST = os.getenv("RAPIDAPI_HOST", "cricbuzz-cricket.p.rapidapi.com")
API_BASE_URL = f"https://{RAPIDAPI_HOST}"
API_TIMEOUT_SECONDS = 15
API_MAX_RETRIES = 2

# Basic plan: 200 requests/month, hard limit. The client refuses to go past
# (limit - reserve) so a bug can never burn the whole quota.
API_MONTHLY_LIMIT = 200
API_SAFETY_RESERVE = 20
# Requests already used before call logging started (read it from the RapidAPI
# dashboard: percent used x 200). Counted on top of the calls we log ourselves.
API_CALLS_OFFSET = int(os.getenv("API_CALLS_OFFSET", "14"))

# --- Caching -----------------------------------------------------------------
RAW_DIR = BASE_DIR / "data" / "raw"
LIVE_CACHE_TTL_SECONDS = 15 * 60
SCORECARD_CACHE_TTL_SECONDS = 60 * 60

# --- Logging -----------------------------------------------------------------
LOG_DIR = BASE_DIR / "logs"
