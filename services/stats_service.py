"""Numbers for the Home and Settings pages: data volume and API quota."""

from pathlib import Path
from typing import Optional

import config
from api.cricbuzz_client import CricbuzzClient
from utils.db_connection import fetch_all

_COUNTED = (
    ("matches", "Matches"),
    ("teams", "Teams"),
    ("players", "Players"),
    ("venues", "Venues"),
    ("series", "Series"),
    ("batting_performances", "Batting entries"),
    ("bowling_performances", "Bowling entries"),
    ("partnerships", "Partnerships"),
    ("player_career_stats", "Career-stat rows"),
)


def data_overview(db_path: Optional[Path] = None) -> list:
    """[{'name', 'real', 'sample'}] for each main table."""
    rows = []
    for table, label in _COUNTED:
        result = fetch_all(
            f"SELECT SUM(is_sample = 0) AS real, SUM(is_sample = 1) AS sample "
            f"FROM {table}",
            db_path=db_path,
        )[0]
        rows.append(
            {
                "name": label,
                "real": result["real"] or 0,
                "sample": result["sample"] or 0,
            }
        )
    return rows


def date_range(db_path: Optional[Path] = None) -> dict:
    """Earliest and latest real match dates."""
    row = fetch_all(
        "SELECT MIN(match_date) AS first, MAX(match_date) AS last "
        "FROM matches WHERE is_sample = 0",
        db_path=db_path,
    )[0]
    return {"first": row["first"], "last": row["last"]}


def quota_status(client: Optional[CricbuzzClient] = None, db_path=None) -> dict:
    """API quota: used, remaining, limit and the safety reserve."""
    client = client or CricbuzzClient(db_path=db_path)
    used = client.calls_used()
    return {
        "used": used,
        "remaining": config.API_MONTHLY_LIMIT - used,
        "limit": config.API_MONTHLY_LIMIT,
        "reserve": config.API_SAFETY_RESERVE,
    }


def cache_summary(raw_dir: Optional[Path] = None) -> dict:
    """How many saved API responses exist and how big they are."""
    folder = Path(raw_dir) if raw_dir else config.RAW_DIR
    files = list(folder.glob("*.json")) if folder.exists() else []
    return {
        "files": len(files),
        "megabytes": round(sum(f.stat().st_size for f in files) / 1_000_000, 2),
    }
