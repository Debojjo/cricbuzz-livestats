"""Load Cricbuzz JSON into the database.

Part A (this file, today): load from saved JSON files. It makes **zero** API
calls, so it is safe to run as often as you like::

    python -m data.ingest --fixtures

Part B (next step) adds a mode that fetches new data through the cached,
budget-guarded client and feeds it through the same ``load_*`` functions.
"""

import argparse
import json
from pathlib import Path
from typing import Optional

import config
from api import parsers
from database import repositories as repo
from database.init_db import init_db
from utils.db_connection import transaction
from utils.logger import get_logger

logger = get_logger(__name__)
FIXTURE_DIR = config.BASE_DIR / "tests" / "fixtures"


def _read(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_teams_list(conn, payload: dict) -> int:
    """teams/list -> teams table."""
    teams = parsers.parse_teams_list(payload)
    for team in teams:
        repo.upsert_team(conn, team)
    return len(teams)


def load_recent_matches(conn, payload: dict) -> dict:
    """matches/recent (or live / upcoming) -> teams, venues, series, matches."""
    items = parsers.parse_recent_matches(payload)
    for item in items:
        for team in item["teams"]:
            repo.upsert_team(conn, team)
        if item["venue"]:
            repo.upsert_venue(conn, item["venue"])
        if item["series"]:
            repo.upsert_series(conn, item["series"])
        repo.upsert_match(conn, item["match"])
    return {"matches": len(items)}


def load_match_info(conn, payload: dict) -> None:
    """matches/get-info -> fills toss, winner and venue details on a stored match."""
    info = parsers.parse_match_info(payload)
    if info["venue"]:
        repo.upsert_venue(conn, info["venue"])
    changed = repo.update_row(
        conn,
        "matches",
        {"match_id": info["match_id"]},
        {
            "toss_winner_id": info["toss_winner_id"],
            "toss_decision": info["toss_decision"],
            "winner_id": info["winner_id"],
        },
    )
    if not changed:
        logger.info("get-info for match %s changed nothing", info["match_id"])


def load_records(conn, payload: dict) -> int:
    """stats/get-records -> a minimal player row for every leaderboard entry."""
    rows = parsers.parse_records(payload)
    for row in rows:
        repo.ensure_player(conn, row["player_id"], row["name"])
    return len(rows)


def load_player_info(conn, payload: dict) -> int:
    """players/get-info -> full player profile. Returns the player id."""
    player = parsers.parse_player_info(payload)
    repo.upsert_player(conn, player)
    return player["player_id"]


def load_career_batting(conn, payload: dict, player_id: int) -> int:
    """players/get-batting -> player_career_stats rows."""
    rows = parsers.parse_career_batting(payload, player_id)
    for row in rows:
        repo.upsert_career_stats(conn, row)
    return len(rows)


def load_scorecard(conn, payload: dict, match_id: int) -> dict:
    """matches/get-scorecard-v2 -> batting, bowling, fielding, partnerships.

    The match must already be stored (its header comes from matches/recent).
    """
    teams = repo.match_teams(conn, match_id)
    if len(teams) != 2:
        raise parsers.ParseError(f"match {match_id} is not in the database yet")
    parsed = parsers.parse_scorecard(payload, match_id, teams)
    counts = repo.save_scorecard(conn, parsed)
    if parsed["unresolved_fielders"]:
        logger.info("fielders not matched: %s", parsed["unresolved_fielders"])
    return counts


def load_fixtures(db_path: Optional[Path] = None, fixture_dir: Path = FIXTURE_DIR):
    """Load every sample file in tests/fixtures (no API calls). Returns a summary."""
    fixture_dir = Path(fixture_dir)
    summary: dict = {}
    with transaction(db_path) as conn:
        summary["teams"] = load_teams_list(conn, _read(fixture_dir / "teams_list.json"))
        summary["players_from_records"] = load_records(
            conn, _read(fixture_dir / "stats_get-records_t20.json")
        )
        player_id = load_player_info(
            conn, _read(fixture_dir / "players_get-info_6635.json")
        )
        summary["player_profiles"] = 1
        summary["career_rows"] = load_career_batting(
            conn, _read(fixture_dir / "players_get-batting_8733.json"), 8733
        )
        summary.update(
            load_recent_matches(conn, _read(fixture_dir / "matches_recent.json"))
        )
        load_match_info(conn, _read(fixture_dir / "matches_get-info_151587.json"))
        summary["profile_player_id"] = player_id
    return summary


def main() -> None:
    """Command-line entry point."""
    parser = argparse.ArgumentParser(description="Load JSON into the database.")
    parser.add_argument(
        "--fixtures", action="store_true", help="load saved samples (no API calls)"
    )
    args = parser.parse_args()
    if not args.fixtures:
        parser.error("choose a mode: --fixtures (live fetching arrives in Part B)")

    init_db()
    summary = load_fixtures()
    print("\nLoaded from tests/fixtures (0 API calls):")
    for key, value in summary.items():
        print(f"  {key}: {value}")


if __name__ == "__main__":
    main()
