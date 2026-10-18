"""Leaderboards for the Top Players page, from stored career statistics."""

import pandas as pd

from api import endpoints
from api.cricbuzz_client import CricbuzzClient
from data import ingest
from utils.db_connection import fetch_all, transaction

# label -> (column, sort direction, filter). All text here is ours, never user input.
CATEGORIES = {
    "Most runs": ("runs", "DESC", "runs > 0"),
    "Highest score": ("highest_score", "DESC", "highest_score IS NOT NULL"),
    "Best batting average (min 1,000 runs)": (
        "batting_avg", "DESC", "runs >= 1000 AND batting_avg IS NOT NULL",
    ),  # fmt: skip
    "Most centuries": ("centuries", "DESC", "centuries IS NOT NULL AND centuries > 0"),
    "Best strike rate (min 1,000 runs)": (
        "strike_rate", "DESC", "runs >= 1000 AND strike_rate IS NOT NULL",
    ),  # fmt: skip
    "Most wickets": ("wickets", "DESC", "wickets > 0"),
    "Best bowling average (min 50 wickets)": (
        "bowling_avg", "ASC", "wickets >= 50 AND bowling_avg > 0",
    ),  # fmt: skip
    "Best economy (min 50 wickets)": (
        "economy_rate", "ASC", "wickets >= 50 AND economy_rate > 0",
    ),  # fmt: skip
}
FORMATS = {"Test": "TEST", "ODI": "ODI", "T20I": "T20"}
# Leaderboards the API can refresh, with the statsType it expects.
REFRESHABLE = {"Most runs": "mostRuns", "Highest score": "highestScore"}
MATCH_TYPE_IDS = {"TEST": "1", "ODI": "2", "T20": "3"}


def top_players(category: str, format_label: str, limit: int = 10, db_path=None):
    """Top players for one category and format: DataFrame(rank, player, value, ...)."""
    if category not in CATEGORIES:
        raise ValueError(f"unknown category: {category}")
    if format_label not in FORMATS:
        raise ValueError(f"unknown format: {format_label}")
    column, direction, condition = CATEGORIES[category]
    rows = fetch_all(
        f"""
        SELECT p.full_name AS player, c.{column} AS value,
               c.matches_played AS matches, c.innings
        FROM player_career_stats AS c
        JOIN players AS p ON p.player_id = c.player_id
        WHERE c.format = ? AND {condition}
        ORDER BY c.{column} {direction}, p.full_name
        LIMIT ?
        """,
        (FORMATS[format_label], max(1, min(int(limit), 50))),
        db_path=db_path,
    )
    df = pd.DataFrame(rows)
    if not df.empty:
        df.insert(0, "rank", range(1, len(df) + 1))
    return df


def players_with_stats(db_path=None) -> int:
    """How many players have career statistics stored."""
    return fetch_all(
        "SELECT COUNT(DISTINCT player_id) AS n FROM player_career_stats",
        db_path=db_path,
    )[0]["n"]


def refresh_from_api(
    client: CricbuzzClient, category: str, format_label: str, db_path=None
) -> dict:
    """Fetch a leaderboard from the API (cached) and merge it into the database."""
    stats_type = REFRESHABLE.get(category)
    if stats_type is None:
        raise ValueError(f"{category!r} cannot be refreshed from the API")
    match_type = MATCH_TYPE_IDS[FORMATS[format_label]]
    payload = client.get(
        endpoints.RECORDS,
        {"id": 0, "statsType": stats_type, "matchType": match_type},
    )
    with transaction(db_path) as conn:
        parsed = ingest.load_records_stats(conn, payload, stats_type, match_type)
    return {"players": len(parsed["rows"]), "columns": parsed["recognized"]}


__all__ = [
    "CATEGORIES",
    "FORMATS",
    "REFRESHABLE",
    "top_players",
    "players_with_stats",
    "refresh_from_api",
]
