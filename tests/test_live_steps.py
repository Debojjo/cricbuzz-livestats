"""Live-step tests. A fake client replays saved files, so no network is used."""

import json

import pytest

import config
from api import endpoints
from api.cricbuzz_client import ApiError, BudgetExceeded
from config import BASE_DIR
from data import live_steps as steps
from database import repositories as repo
from database.init_db import init_db
from utils.db_connection import fetch_all, transaction

FX = BASE_DIR / "tests" / "fixtures"


def fixture(name):
    return json.loads((FX / name).read_text(encoding="utf-8"))


class FakeClient:
    """Stands in for CricbuzzClient: returns canned payloads, counts 'calls'."""

    def __init__(self, replies=None, cached=(), remaining=150, fail=None):
        self.replies = replies or {}
        self.cached = set(cached)
        self.remaining = remaining
        self.fail = fail
        self.calls = []

    def key(self, endpoint, params):
        return (endpoint, tuple(sorted(params.items())))

    def is_cached(self, endpoint, params=None):
        return self.key(endpoint, params or {}) in self.cached

    def calls_remaining(self):
        return self.remaining - len(self.calls)

    def cache_path(self, endpoint, params=None):
        return f"data/raw/{endpoint}"

    def get(self, endpoint, params=None, max_age=None):
        if self.fail:
            raise self.fail
        self.calls.append((endpoint, params))
        return self.replies[endpoint]


@pytest.fixture()
def db(tmp_path):
    return init_db(tmp_path / "live.db")


def count(db, table):
    return fetch_all(f"SELECT COUNT(*) AS n FROM {table}", db_path=db)[0]["n"]


def add_ire_usa_match(db, match_id=40381, state="Complete"):
    with transaction(db) as conn:
        repo.upsert_team(
            conn, {"team_id": 27, "team_name": "Ireland", "short_name": "IRE"}
        )
        repo.upsert_team(
            conn,
            {
                "team_id": 15,
                "team_name": "United States of America",
                "short_name": "USA",
            },
        )
        repo.upsert_match(
            conn,
            {
                "match_id": match_id,
                "format": "T20",
                "match_category": "international",
                "match_date": "2021-03-22",
                "team1_id": 15,
                "team2_id": 27,
                "winner_id": 27,
                "victory_type": "runs",
                "victory_margin": 9,
                "state": state,
            },
        )


# ------------------------------------------------------------- dry run ----
def test_dry_run_spends_nothing_and_changes_nothing(db):
    client = FakeClient({endpoints.MATCHES_RECENT: fixture("matches_recent.json")})
    summary = steps.run_tasks(client, db, steps.plan_recent(), confirm=False)
    assert summary["new_calls"] == 1 and summary["done"] == 0
    assert client.calls == []
    assert count(db, "matches") == 0


def test_recent_step_loads_matches(db):
    client = FakeClient({endpoint: None for endpoint in []})
    client.replies[endpoints.MATCHES_RECENT] = fixture("matches_recent.json")
    summary = steps.run_tasks(client, db, steps.plan_recent(), confirm=True)
    assert summary["done"] == 1 and len(client.calls) == 1
    assert count(db, "matches") == 1
    assert count(db, "teams") == 2


def test_series_step_stores_series(db):
    client = FakeClient(
        {endpoints.SERIES_ARCHIVES: fixture("series_archives_sample.json")}
    )
    tasks = steps.plan_series(2024)
    assert tasks[0].params == {"type": "international", "year": 2024}
    steps.run_tasks(client, db, tasks, confirm=True)
    assert count(db, "series") == 3


# ----------------------------------------------------------- scorecards ----
def test_scorecard_step_picks_only_matches_without_scorecards(db):
    add_ire_usa_match(db)
    tasks = steps.plan_scorecards(db, limit=5)
    assert [t.params["matchId"] for t in tasks] == [40381]

    client = FakeClient({endpoints.SCORECARD: fixture("scorecard_v2_sample.json")})
    steps.run_tasks(client, db, tasks, confirm=True)
    assert count(db, "batting_performances") == 20
    assert steps.plan_scorecards(db, limit=5) == []  # nothing left to fetch


def test_scorecard_step_ignores_unfinished_and_abandoned_matches(db):
    add_ire_usa_match(db, 1, state="In Progress")
    assert steps.plan_scorecards(db, limit=5) == []


def test_wrong_shape_stops_after_three_errors(db):
    for match_id in range(1, 7):
        add_ire_usa_match(db, match_id)
    client = FakeClient({endpoints.SCORECARD: {"scoreCard": [{"unexpected": True}]}})
    tasks = steps.plan_scorecards(db, limit=6)
    summary = steps.run_tasks(client, db, tasks, confirm=True)
    assert len(client.calls) == steps.MAX_ERRORS  # 3 calls wasted, not 6
    assert "did not match" in summary["stopped"]
    assert count(db, "batting_performances") == 0


def test_budget_error_stops_cleanly(db):
    add_ire_usa_match(db)
    client = FakeClient(fail=BudgetExceeded("only 19 calls left"))
    summary = steps.run_tasks(client, db, steps.plan_scorecards(db, 5), confirm=True)
    assert "19 calls left" in summary["stopped"]


def test_api_error_stops_the_step(db):
    add_ire_usa_match(db)
    client = FakeClient(fail=ApiError("HTTP 403"))
    summary = steps.run_tasks(client, db, steps.plan_scorecards(db, 5), confirm=True)
    assert "403" in summary["stopped"]


def test_plan_larger_than_budget_is_refused(db):
    add_ire_usa_match(db)
    client = FakeClient(remaining=config.API_SAFETY_RESERVE)  # nothing usable
    summary = steps.run_tasks(client, db, steps.plan_scorecards(db, 5), confirm=True)
    assert summary["done"] == 0 and client.calls == []
    assert "budget" in summary["stopped"]


# ------------------------------------------------- info / venues / players ----
def test_match_info_step_skips_cached_and_fills_toss(db):
    with transaction(db) as conn:
        for item_file in ("matches_recent.json",):
            from data.ingest import load_recent_matches

            load_recent_matches(conn, fixture(item_file))
    client = FakeClient({endpoints.MATCH_INFO: fixture("matches_get-info_151587.json")})
    tasks = steps.plan_match_info(db, client, limit=3)
    assert [t.params["matchId"] for t in tasks] == [151587]
    steps.run_tasks(client, db, tasks, confirm=True)
    row = fetch_all("SELECT * FROM matches WHERE match_id = 151587", db_path=db)[0]
    assert (row["toss_winner_id"], row["toss_decision"]) == (10, "bowl")

    cached = FakeClient(cached={client.key(endpoints.MATCH_INFO, {"matchId": 151587})})
    with transaction(db) as conn:
        conn.execute("UPDATE matches SET toss_winner_id = NULL")
    assert steps.plan_match_info(db, cached, limit=3) == []  # cached: never re-fetched


def test_venue_step_fills_country_and_capacity(db):
    with transaction(db) as conn:
        repo.upsert_venue(conn, {"venue_id": 45, "venue_name": "Basin Reserve"})
    client = FakeClient(
        {endpoints.VENUE_INFO: fixture("venues_get-info_basin-reserve.json")}
    )
    tasks = steps.plan_venues(db, client, limit=2)
    steps.run_tasks(client, db, tasks, confirm=True)
    row = fetch_all("SELECT * FROM venues WHERE venue_id = 45", db_path=db)[0]
    assert row["country"] == "New Zealand" and row["capacity"] == 11600


def test_player_step_uses_priority_order_and_three_calls_each(db):
    with transaction(db) as conn:
        for pid in (999, 1413, 576):
            repo.ensure_player(conn, pid, f"P{pid}")
    tasks = steps.plan_players(db, limit=2)
    ids = [t.params["playerId"] for t in tasks]
    assert ids == [576, 576, 576, 1413, 1413, 1413]  # leaderboard stars first
    assert len(steps.plan_players(db, limit=2, with_bowling=False)) == 4
    assert [t.params["playerId"] for t in steps.plan_players(db, 5, ids=[999])][
        0
    ] == 999


def test_unrecognised_bowling_table_is_reported_not_silently_ignored(db):
    with transaction(db) as conn:
        repo.ensure_player(conn, 8733, "KL Rahul")
    odd = {"headers": ["ROWHEADER", "Test"], "values": [{"values": ["Mystery", "5"]}]}
    client = FakeClient({endpoints.PLAYER_BOWLING: odd})
    task = steps.plan_players(db, 1, ids=[8733])[2]
    summary = steps.run_tasks(client, db, [task], confirm=True)
    assert summary["errors"] and "no recognised rows" in summary["errors"][0]


# --------------------------------------------------------------- records ----
def test_records_step_writes_career_rows_for_the_right_format(db):
    client = FakeClient({endpoints.RECORDS: fixture("stats_get-records_t20.json")})
    tasks = steps.plan_records("mostRuns", "3")
    assert tasks[0].params == {"id": 0, "statsType": "mostRuns", "matchType": "3"}
    steps.run_tasks(client, db, tasks, confirm=True)
    row = fetch_all(
        "SELECT * FROM player_career_stats WHERE player_id = 8359 AND format = 'T20'",
        db_path=db,
    )[0]
    assert row["runs"] == 4596 and row["matches_played"] == 144


def test_records_for_the_wrong_match_type_are_refused(db):
    client = FakeClient({endpoints.RECORDS: fixture("stats_get-records_t20.json")})
    tasks = steps.plan_records("mostRuns", "2")  # asked for ODI, reply says T20
    summary = steps.run_tasks(client, db, tasks, confirm=True)
    assert summary["errors"] and "expected 'odi'" in summary["errors"][0]
    assert count(db, "player_career_stats") == 0


def test_top_batters_step_targets_biggest_scorers_missing_an_average(db):
    client = FakeClient({endpoints.RECORDS: fixture("stats_get-records_t20.json")})
    steps.run_tasks(client, db, steps.plan_records("mostRuns", "3"), confirm=True)
    tasks = steps.plan_top_batters(db, limit=3, match_type="3")
    assert [t.params["playerId"] for t in tasks] == [8359, 2258, 576]  # by runs
    assert all(t.endpoint == endpoints.PLAYER_BATTING for t in tasks)
    with pytest.raises(ValueError):
        steps.plan_top_batters(db, limit=3, match_type="9")
