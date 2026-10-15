"""Live loading steps: choose what to fetch, fetch it (cached), store it.

Every step first builds a *plan* (a list of tasks). Without ``confirm`` it only
prints the plan and the quota cost, so nothing is ever spent by accident. With
``confirm`` it runs the tasks one by one:

* cached responses cost nothing (they are read from ``data/raw``),
* a response that does not parse stops the step after a few errors, so a wrong
  URL or an unexpected shape costs 1-3 calls, never 50,
* database writes are short and happen *between* calls (SQLite allows one
  writer at a time, so we never hold a write open while waiting for the API).
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

import config
from api import endpoints, parsers
from api.cricbuzz_client import ApiError, BudgetExceeded
from data import ingest
from database import repositories as repo
from utils.db_connection import fetch_all, transaction
from utils.logger import get_logger

logger = get_logger(__name__)
MAX_ERRORS = 3

# Well-known batters from the T20 leaderboard, so --limit N spends calls on the
# players who matter most for Q3 / Q9 / Q11 / Q20 / Q21 and the Top Players page.
PRIORITY_PLAYER_IDS = [
    8359, 2258, 576, 1413, 1114, 1457, 9468, 1739, 7915, 9354, 1643, 8520,
    7662, 6349, 6326, 544, 3007, 9647, 9406, 8733,
]  # fmt: skip


@dataclass
class Task:
    """One API request plus what to do with the answer."""

    endpoint: str
    params: dict
    handler: Callable  # handler(db_path, payload, params)
    label: str


def _ids(rows: list, key: str) -> list:
    return [row[key] for row in rows]


# ---------------------------------------------------------------- planning ----
def plan_recent() -> list:
    """matches/recent: 1 call."""
    return [
        Task(
            endpoints.MATCHES_RECENT,
            {},
            lambda db, payload, params: _load(db, ingest.load_recent_matches, payload),
            "matches/recent",
        )
    ]


def plan_series(year: int, series_type: str = "international") -> list:
    """series/archives for one year: 1 call."""

    def handler(db, payload, params):
        with transaction(db) as conn:
            for series in parsers.parse_series_archives(payload):
                repo.upsert_series(conn, series)

    return [
        Task(
            endpoints.SERIES_ARCHIVES,
            {"type": series_type, "year": year},
            handler,
            f"series/archives {series_type} {year}",
        )
    ]


def plan_scorecards(db, limit: int) -> list:
    """Scorecards for completed matches that have none yet (international first)."""
    rows = fetch_all(
        """
        SELECT m.match_id FROM matches m
        WHERE m.state = 'Complete' AND m.is_sample = 0
          AND (m.victory_type IS NULL
               OR m.victory_type NOT IN ('abandoned', 'no result', 'forfeit'))
          AND NOT EXISTS (SELECT 1 FROM batting_performances b
                          WHERE b.match_id = m.match_id)
        ORDER BY (m.match_category = 'international') DESC, m.match_date DESC
        LIMIT ?
        """,
        (limit,),
        db_path=db,
    )

    def handler(db_path, payload, params):
        with transaction(db_path) as conn:
            ingest.load_scorecard(conn, payload, params["matchId"])

    return [
        Task(endpoints.SCORECARD, {"matchId": mid}, handler, f"scorecard {mid}")
        for mid in _ids(rows, "match_id")
    ]


def plan_match_info(db, client, limit: int) -> list:
    """matches/get-info for matches still missing a toss (skips cached ones)."""
    rows = fetch_all(
        """
        SELECT match_id FROM matches
        WHERE state = 'Complete' AND toss_winner_id IS NULL AND is_sample = 0
        ORDER BY (match_category = 'international') DESC, match_date DESC
        LIMIT ?
        """,
        (limit * 4,),
        db_path=db,
    )
    chosen = [
        mid
        for mid in _ids(rows, "match_id")
        if not client.is_cached(endpoints.MATCH_INFO, {"matchId": mid})
    ][:limit]

    def handler(db_path, payload, params):
        with transaction(db_path) as conn:
            ingest.load_match_info(conn, payload)

    return [
        Task(endpoints.MATCH_INFO, {"matchId": mid}, handler, f"match info {mid}")
        for mid in chosen
    ]


def plan_venues(db, client, limit: int) -> list:
    """venues/get-info for venues still missing a country (skips cached ones)."""
    rows = fetch_all(
        """
        SELECT v.venue_id FROM venues v
        WHERE v.country IS NULL AND v.is_sample = 0
        ORDER BY (SELECT COUNT(*) FROM matches m WHERE m.venue_id = v.venue_id) DESC
        LIMIT ?
        """,
        (limit * 4,),
        db_path=db,
    )
    chosen = [
        vid
        for vid in _ids(rows, "venue_id")
        if not client.is_cached(endpoints.VENUE_INFO, {"venueId": vid})
    ][:limit]

    def handler(db_path, payload, params):
        with transaction(db_path) as conn:
            venue = parsers.parse_venue_info(payload, params["venueId"])
            repo.upsert_venue(conn, venue)

    return [
        Task(endpoints.VENUE_INFO, {"venueId": vid}, handler, f"venue {vid}")
        for vid in chosen
    ]


def plan_players(
    db, limit: int, ids: Optional[list] = None, with_bowling: bool = True
) -> list:
    """Profile + career batting (+ bowling) for ``limit`` players (3 calls each)."""
    if ids:
        chosen = ids[:limit]
    else:
        rows = fetch_all(
            "SELECT player_id FROM players WHERE country IS NULL AND is_sample = 0",
            db_path=db,
        )
        waiting = set(_ids(rows, "player_id"))
        ordered = [pid for pid in PRIORITY_PLAYER_IDS if pid in waiting]
        ordered += sorted(waiting - set(ordered))
        chosen = ordered[:limit]

    def info(db_path, payload, params):
        with transaction(db_path) as conn:
            ingest.load_player_info(conn, payload)

    def batting(db_path, payload, params):
        with transaction(db_path) as conn:
            ingest.load_career_batting(conn, payload, params["playerId"])

    def bowling(db_path, payload, params):
        rows = parsers.parse_career_bowling(payload, params["playerId"])
        if not rows:
            raise parsers.ParseError(
                f"bowling table for player {params['playerId']} has no recognised "
                "rows (labels unverified) - send me the saved file in data/raw"
            )
        with transaction(db_path) as conn:
            for row in rows:
                repo.upsert_career_stats(conn, row)

    tasks = []
    for pid in chosen:
        params = {"playerId": pid}
        tasks.append(Task(endpoints.PLAYER_INFO, params, info, f"player info {pid}"))
        tasks.append(Task(endpoints.PLAYER_BATTING, params, batting, f"batting {pid}"))
        if with_bowling:
            tasks.append(
                Task(endpoints.PLAYER_BOWLING, params, bowling, f"bowling {pid}")
            )
    return tasks


def plan_records(stats_type: str, match_type: str) -> list:
    """One leaderboard (e.g. mostRuns for ODI = matchType 2): 1 call."""

    def handler(db_path, payload, params):
        parsed = parsers.parse_records_stats(payload, stats_type, match_type)
        logger.info(
            "records columns used: %s | ignored: %s",
            parsed["recognized"],
            parsed["ignored"],
        )
        with transaction(db_path) as conn:
            for pid, name in parsed["names"].items():
                repo.ensure_player(conn, pid, name)
            for row in parsed["rows"]:
                repo.upsert_career_stats(conn, row)

    return [
        Task(
            endpoints.RECORDS,
            {"id": 0, "statsType": stats_type, "matchType": match_type},
            handler,
            f"records {stats_type} matchType={match_type}",
        )
    ]


def _load(db_path, loader, payload) -> None:
    with transaction(db_path) as conn:
        loader(conn, payload)


# ----------------------------------------------------------------- running ----
def run_tasks(client, db_path: Path, tasks: list, confirm: bool) -> dict:
    """Show the plan; with ``confirm`` also execute it. Returns a summary."""
    cached = [t for t in tasks if client.is_cached(t.endpoint, t.params)]
    new_calls = len(tasks) - len(cached)
    remaining = client.calls_remaining()
    usable = remaining - config.API_SAFETY_RESERVE
    summary = {
        "tasks": len(tasks),
        "cached": len(cached),
        "new_calls": new_calls,
        "done": 0,
        "errors": [],
        "stopped": None,
    }
    print(
        f"\nPlan: {len(tasks)} request(s) | {len(cached)} already cached (free) | "
        f"{new_calls} will use quota"
    )
    print(
        f"Quota: {remaining} calls left, {usable} usable above the "
        f"{config.API_SAFETY_RESERVE}-call reserve"
    )
    for task in tasks[:8]:
        mark = "cached" if task in cached else "CALL  "
        print(f"  [{mark}] {task.label}")
    if len(tasks) > 8:
        print(f"  ... and {len(tasks) - 8} more")

    if not confirm:
        print("\nDry run only - nothing was fetched. Add --confirm to run it.")
        return summary
    if new_calls > usable:
        summary["stopped"] = "plan needs more calls than the budget allows"
        print(f"\nStopped: {summary['stopped']}. Lower --limit.")
        return summary

    for task in tasks:
        try:
            payload = client.get(task.endpoint, task.params)
            task.handler(db_path, payload, task.params)
            summary["done"] += 1
        except BudgetExceeded as exc:
            summary["stopped"] = str(exc)
            break
        except ApiError as exc:
            summary["stopped"] = str(exc)
            break
        except (parsers.ParseError, KeyError, TypeError, ValueError) as exc:
            summary["errors"].append(f"{task.label}: {exc}")
            print(f"  ! {task.label}: could not read response ({exc})")
            print(f"    saved at {client.cache_path(task.endpoint, task.params)}")
            if len(summary["errors"]) >= MAX_ERRORS:
                summary["stopped"] = (
                    f"{MAX_ERRORS} responses did not match the expected shape"
                )
                break
    print(
        f"\nDone {summary['done']}/{len(tasks)}. "
        f"Quota left: {client.calls_remaining()}"
    )
    if summary["stopped"]:
        print(f"Stopped early: {summary['stopped']}")
    return summary
