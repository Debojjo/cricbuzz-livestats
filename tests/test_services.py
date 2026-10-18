"""Tests for the services behind the pages (no Streamlit needed)."""

import json

import pytest

import config
from api import endpoints
from config import BASE_DIR
from data import ingest, seed_sample_data
from database import repositories as repo
from database.init_db import init_db
from services import analytics_service, match_service, player_service, stats_service
from utils.db_connection import get_connection, transaction

FX = BASE_DIR / "tests" / "fixtures"


def fixture(name):
    return json.loads((FX / name).read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def world(tmp_path_factory):
    """Real fixtures plus a small fictional history, in one database."""
    db = init_db(tmp_path_factory.mktemp("svc") / "svc.db")
    ingest.load_fixtures(db)
    with transaction(db) as conn:
        seed_sample_data.generate(conn, matches=120, seed=3)
    return db


# ---------------------------------------------------------- sample switch ----
def test_hiding_sample_rows_leaves_only_real_data(world):
    everything = get_connection(world, read_only=True)
    real_only = get_connection(world, read_only=True, include_sample=False)
    try:
        total = everything.execute("SELECT COUNT(*) FROM matches").fetchone()[0]
        real = real_only.execute("SELECT COUNT(*) FROM matches").fetchone()[0]
        via_view = real_only.execute("SELECT COUNT(*) FROM v_match_results").fetchone()[
            0
        ]
    finally:
        everything.close()
        real_only.close()
    assert total == 121 and real == 1 and via_view == 1  # views follow the switch


def test_the_sample_switch_cannot_be_used_for_writing(world):
    with pytest.raises(ValueError):
        get_connection(world, include_sample=False)
    conn = get_connection(world, read_only=True, include_sample=False)
    try:
        with pytest.raises(Exception):
            conn.execute("INSERT INTO teams (team_id, team_name) VALUES (1, 'x')")
    finally:
        conn.close()


def test_numbered_query_results_change_with_the_switch(world):
    with_sample = analytics_service.run_numbered(5, include_sample=True, db_path=world)
    real_only = analytics_service.run_numbered(5, include_sample=False, db_path=world)
    assert len(with_sample["df"]) > len(real_only["df"])
    assert real_only["df"]["team_name"].str.startswith("Sample").sum() == 0


# -------------------------------------------------------------- analytics ----
def test_all_queries_are_listed_with_titles_and_levels():
    queries = analytics_service.list_queries()
    labels = [q["label"] for q in queries]
    assert labels[:3] == ["1", "2", "3"] and "22b" in labels and "25b" in labels
    assert len(queries) == 27
    first = queries[0]
    assert first["level"] == "Beginner" and "India" in first["title"]
    assert all(q["title"] for q in queries)


def test_describe_returns_the_header_comment():
    text = analytics_service.describe("7")
    assert "Highest individual batting score" in text and "SELECT" not in text


@pytest.mark.parametrize(
    "sql",
    [
        "",
        "   ",
        "DROP TABLE players",
        "DELETE FROM players",
        "INSERT INTO teams VALUES (1)",
        "PRAGMA table_info(players)",
        "SELECT 1; DROP TABLE players",
        "ATTACH DATABASE 'x.db' AS x",
    ],
)
def test_validator_rejects_everything_but_one_select(sql):
    with pytest.raises(ValueError):
        analytics_service.validate_select(sql)


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT 1",
        "select 1;",
        "-- a comment\nSELECT 1",
        "/* block */ WITH x AS (SELECT 1 AS a) SELECT a FROM x",
    ],
)
def test_validator_accepts_selects_and_with_queries(sql):
    assert analytics_service.validate_select(sql)


def test_custom_query_runs_and_limits_rows(world):
    out = analytics_service.run_custom(
        "SELECT * FROM batting_performances", max_rows=50, db_path=world
    )
    assert len(out["df"]) == 50 and out["truncated"] is True
    small = analytics_service.run_custom("SELECT 1 AS one", db_path=world)
    assert small["truncated"] is False and small["df"].iloc[0, 0] == 1


def test_custom_query_cannot_change_data_even_through_with(world):
    sneaky = "WITH x AS (SELECT 1) DELETE FROM teams"
    with pytest.raises(ValueError, match="SQL error"):
        analytics_service.run_custom(sneaky, db_path=world)
    conn = get_connection(world, read_only=True)
    try:
        assert conn.execute("SELECT COUNT(*) FROM teams").fetchone()[0] > 0
    finally:
        conn.close()


def test_custom_query_stops_when_it_runs_too_long(world):
    forever = (
        "WITH RECURSIVE r(n) AS (SELECT 1 UNION ALL SELECT n + 1 FROM r) "
        "SELECT COUNT(*) FROM r"
    )
    with pytest.raises(ValueError, match="longer than"):
        analytics_service.run_custom(forever, timeout=0.3, db_path=world)


def test_custom_query_reports_sql_mistakes_readably(world):
    with pytest.raises(ValueError, match="SQL error"):
        analytics_service.run_custom("SELECT nonsense FROM players", db_path=world)


def test_custom_query_respects_the_sample_switch(world):
    sql = "SELECT COUNT(*) AS n FROM matches"
    assert analytics_service.run_custom(sql, True, db_path=world)["df"].n[0] == 121
    assert analytics_service.run_custom(sql, False, db_path=world)["df"].n[0] == 1


def test_schema_overview_lists_tables_and_views(world):
    overview = analytics_service.schema_overview(world)
    assert "players" in overview and "v_batting_detail" in overview
    assert "full_name" in overview["players"]


# ------------------------------------------------------------------ matches ----
def test_recent_results_are_real_by_default_and_newest_first(world):
    real = match_service.recent_results(db_path=world)
    both = match_service.recent_results(limit=500, include_sample=True, db_path=world)
    assert [r["match_id"] for r in real] == [151587]
    assert len(both) == 121
    dates = [r["match_date"] for r in both]
    assert dates == sorted(dates, reverse=True)


def test_stored_scorecard_returns_three_tables_for_a_sample_match(world):
    sample = match_service.recent_results(limit=1, include_sample=True, db_path=world)[
        0
    ]
    card = match_service.stored_scorecard(sample["match_id"], True, db_path=world)
    assert not card["batting"].empty and not card["bowling"].empty
    assert list(card["batting"].columns)[:4] == ["innings", "team", "pos", "batsman"]
    hidden = match_service.stored_scorecard(sample["match_id"], False, db_path=world)
    assert hidden["batting"].empty  # sample match is invisible when sample is off


class FakeClient:
    def __init__(self, payloads):
        self.payloads, self.calls = payloads, []

    def get(self, endpoint, params=None, max_age=None):
        self.calls.append((endpoint, params, max_age))
        return self.payloads[endpoint]


def test_live_matches_use_the_short_cache_window():
    client = FakeClient({endpoints.MATCHES_LIVE: fixture("matches_recent.json")})
    items = match_service.live_matches(client)
    assert len(items) == 1 and items[0]["match"]["match_id"] == 151587
    assert client.calls[0][2] == match_service.LIVE_CACHE_SECONDS
    assert "India v West Indies" in match_service.describe_live(items[0])


def test_live_scorecard_builds_named_tables():
    item = {
        "match": {"match_id": 40381},
        "teams": [
            {"team_id": 27, "team_name": "Ireland", "short_name": "IRE"},
            {
                "team_id": 15,
                "team_name": "United States of America",
                "short_name": "USA",
            },
        ],
    }
    client = FakeClient({endpoints.SCORECARD: fixture("scorecard_v2_sample.json")})
    card = match_service.live_scorecard(client, item)
    assert len(card["batting"]) == 20 and len(card["bowling"]) == 12
    assert "Lorcan Tucker" in set(card["batting"]["batsman"])
    assert client.calls[0][2] == match_service.SCORECARD_CACHE_SECONDS


def test_match_choices_filter_by_text(world):
    assert len(match_service.match_choices(limit=10, db_path=world)) == 10
    found = match_service.match_choices(search="West Indies", db_path=world)
    assert [m["match_id"] for m in found] == [151587]
    assert "#151587" in found[0]["label"]


# ------------------------------------------------------------------ players ----
def test_top_players_by_category_and_format(tmp_path):
    db = init_db(tmp_path / "p.db")
    with transaction(db) as conn:
        for pid, name, runs, avg, hs in [
            (1, "Ann", 9000, 55.0, 200),
            (2, "Bea", 12000, 45.0, 150),
            (3, "Cy", 500, 80.0, 99),
        ]:
            repo.upsert_player(conn, {"player_id": pid, "full_name": name})
            repo.upsert_career_stats(
                conn,
                {
                    "player_id": pid,
                    "format": "ODI",
                    "runs": runs,
                    "batting_avg": avg,
                    "highest_score": hs,
                    "matches_played": 10,
                    "innings": 10,
                },
            )
    runs = player_service.top_players("Most runs", "ODI", 10, db_path=db)
    assert list(runs["player"]) == ["Bea", "Ann", "Cy"] and list(runs["rank"]) == [
        1,
        2,
        3,
    ]
    best_avg = player_service.top_players(
        "Best batting average (min 1,000 runs)", "ODI", db_path=db
    )
    assert list(best_avg["player"]) == ["Ann", "Bea"]  # Cy has too few runs to qualify
    assert player_service.top_players("Most runs", "Test", db_path=db).empty
    with pytest.raises(ValueError):
        player_service.top_players("Most dancing", "ODI", db_path=db)
    assert player_service.players_with_stats(db) == 3


def test_leaderboard_refresh_loads_players_and_reports_columns(tmp_path):
    db = init_db(tmp_path / "r.db")
    client = FakeClient({endpoints.RECORDS: fixture("stats_get-records_t20.json")})
    outcome = player_service.refresh_from_api(client, "Most runs", "T20I", db_path=db)
    assert outcome["players"] == 50 and "R" in outcome["columns"]
    assert client.calls[0][1] == {"id": 0, "statsType": "mostRuns", "matchType": "3"}
    with pytest.raises(ValueError):
        player_service.refresh_from_api(client, "Most centuries", "ODI", db_path=db)


# -------------------------------------------------------------------- stats ----
def test_overview_counts_real_and_sample_separately(world):
    rows = {r["name"]: r for r in stats_service.data_overview(world)}
    assert rows["Matches"]["real"] == 1 and rows["Matches"]["sample"] == 120
    assert stats_service.date_range(world)["first"] == "2026-10-11"


def test_quota_status_uses_the_dashboard_offset(world, monkeypatch):
    monkeypatch.setattr(config, "API_CALLS_OFFSET", 40)
    quota = stats_service.quota_status(db_path=world)
    assert quota["used"] >= 40 and quota["remaining"] == 200 - quota["used"]


def test_cache_summary_counts_files(tmp_path):
    (tmp_path / "a.json").write_text("{}")
    (tmp_path / "b.json").write_text("{" + " " * 10 + "}")
    assert stats_service.cache_summary(tmp_path)["files"] == 2
    assert stats_service.cache_summary(tmp_path / "missing")["files"] == 0
