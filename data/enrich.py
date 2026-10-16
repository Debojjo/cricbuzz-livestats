"""Fill gaps the API cannot: big stadiums (Q4) and series details (Q8).

No API calls. Run once after loading::

    python -m data.enrich

* ``data/venues_extra.csv`` holds well-known stadiums with approximate public
  capacities. They are marked is_sample = 1, meaning "not from the API".
* Series rows from the archive have only a name and dates. Host country and
  match type are derived from the name ("X tour of Y" -> host Y) only where the
  name says so, and left empty otherwise. Nothing is guessed.
"""

import csv
import re
from pathlib import Path

import config
from database import repositories as repo
from database.init_db import init_db
from utils.db_connection import transaction

VENUES_CSV = config.BASE_DIR / "data" / "venues_extra.csv"
_HOST_PATTERNS = (
    re.compile(r"\btour of (?P<host>[^,0-9]+?)(?:,|\s+\d{4}|$)"),
    re.compile(r"\bin (?P<host>[^,0-9]+?)(?:,|\s+\d{4}|$)"),
)


def host_country_from_name(name: str):
    """'West Indies tour of India, 2026' -> 'India'; no pattern -> None."""
    for pattern in _HOST_PATTERNS:
        match = pattern.search(name or "")
        if match:
            return match["host"].strip()
    return None


def match_type_from_name(name: str):
    """Only when the series name says the format: 'ICC Men's T20 World Cup' -> 'T20'."""
    text = name or ""
    if re.search(r"\bTest\b", text):
        return "Test"
    if re.search(r"\bODI\b|One[- ]Day", text):
        return "ODI"
    if re.search(r"T20", text):
        return "T20"
    return None


def load_venues_extra(conn, csv_path: Path = VENUES_CSV) -> int:
    """Insert the manual venue list (safe to repeat)."""
    count = 0
    with open(csv_path, newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            repo.upsert_venue(
                conn,
                {
                    "venue_id": int(row["venue_id"]),
                    "venue_name": row["venue_name"],
                    "city": row["city"],
                    "country": row["country"],
                    "capacity": int(row["capacity"]),
                    "is_sample": 1,
                },
            )
            count += 1
    return count


def enrich_series(conn) -> dict:
    """Fill empty host_country / match_type / total_matches on real series."""
    filled = {"host_country": 0, "match_type": 0, "total_matches": 0}
    rows = conn.execute(
        "SELECT series_id, series_name, host_country, match_type, total_matches "
        "FROM series WHERE is_sample = 0"
    ).fetchall()
    for row in rows:
        changes = {}
        if row["host_country"] is None:
            changes["host_country"] = host_country_from_name(row["series_name"])
        if row["match_type"] is None:
            kind = match_type_from_name(row["series_name"])
            if kind is None:
                formats = conn.execute(
                    "SELECT DISTINCT format FROM matches WHERE series_id = ?",
                    (row["series_id"],),
                ).fetchall()
                if len(formats) == 1:
                    kind = (
                        formats[0][0].title()
                        if formats[0][0] == "TEST"
                        else formats[0][0]
                    )
            changes["match_type"] = kind
        if row["total_matches"] is None:
            n = conn.execute(
                "SELECT COUNT(*) FROM matches WHERE series_id = ?", (row["series_id"],)
            ).fetchone()[0]
            changes["total_matches"] = n or None
        updated = repo.update_row(
            conn, "series", {"series_id": row["series_id"]}, changes
        )
        if updated:
            for key, value in changes.items():
                if value is not None:
                    filled[key] += 1
    return filled


def main() -> None:
    """Command-line entry point."""
    init_db()
    with transaction() as conn:
        venues = load_venues_extra(conn)
        filled = enrich_series(conn)
    print(f"\nManual venues loaded: {venues}")
    print(f"Series fields filled: {filled}")


if __name__ == "__main__":
    main()
