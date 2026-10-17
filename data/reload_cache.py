"""Re-read every saved API response in data/raw into the database. 0 API calls.

Use it after a parser fix: the raw files are the truth, the database is rebuilt
from them. Leaderboards are loaded first and personal career tables last, so
the more reliable career data always has the final word.

    python -m data.reload_cache
"""

import json
import re
from pathlib import Path
from typing import Optional

import config
from data import ingest
from database.init_db import init_db
from utils.db_connection import transaction
from utils.logger import get_logger

logger = get_logger(__name__)
_RECORDS = re.compile(r"stats_v1_topstats_0_(\d)_(\w+)\.json$")
_BATTING = re.compile(r"stats_v1_player_batting_(\d+)\.json$")


def reload_cache(
    db_path: Optional[Path] = None, raw_dir: Optional[Path] = None
) -> dict:
    """Reload cached leaderboards, then cached career batting tables."""
    raw = Path(raw_dir) if raw_dir else config.RAW_DIR
    counts = {"leaderboards": 0, "career_tables": 0, "skipped": 0}
    for path in sorted(raw.glob("stats_v1_topstats_*.json")):
        match = _RECORDS.search(path.name)
        if not match:
            counts["skipped"] += 1
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        with transaction(db_path) as conn:
            ingest.load_records_stats(conn, payload, match[2], match[1])
        counts["leaderboards"] += 1
    for path in sorted(raw.glob("stats_v1_player_batting_*.json")):
        match = _BATTING.search(path.name)
        payload = json.loads(path.read_text(encoding="utf-8"))
        with transaction(db_path) as conn:
            ingest.load_career_batting(conn, payload, int(match[1]))
        counts["career_tables"] += 1
    return counts


def main() -> None:
    """Command-line entry point."""
    init_db()
    counts = reload_cache()
    print(f"\nReloaded from data/raw (0 API calls): {counts}")


if __name__ == "__main__":
    main()
