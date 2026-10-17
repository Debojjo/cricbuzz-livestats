"""Tests for the numbered analytics queries."""

import sqlite3

import pytest

from database import repositories as repo
from database.init_db import init_db
from services import query_runner
from utils.db_connection import transaction


@pytest.fixture()
def db(tmp_path):
    return init_db(tmp_path / "q.db")


def test_every_query_file_is_valid_sql_on_an_empty_database(db):
    """Guards all 25 queries: a typo in any file fails here, not in the app."""
    files = sorted(query_runner.QUERY_DIR.glob("q*.sql"))
    assert files, "no query files found"
    for path in files:
        number = int(path.name[1:3])
        result = query_runner.run_query(number, db)
        assert result["rows"] == [] or isinstance(result["rows"], list)
        assert query_runner.explain(number, db)


def test_query_runner_is_read_only(db):
    conn = sqlite3.connect(db)
    conn.close()
    path = query_runner.QUERY_DIR / "q99_bad.sql"
    path.write_text("DELETE FROM players;", encoding="utf-8")
    try:
        with pytest.raises(sqlite3.Error):
            query_runner.run_query(99, db)
    finally:
        path.unlink()


# ------------------------------------------------------------------- Q1 ----
def test_q1_lists_only_indian_players_in_name_order(db):
    with transaction(db) as conn:
        repo.upsert_player(conn, {"player_id": 1, "full_name": "Virat Kohli",
                                  "country": "India", "playing_role": "Batsman",
                                  "batting_style": "Right-hand bat",
                                  "bowling_style": "Right-arm medium"})  # fmt: skip
        repo.upsert_player(
            conn, {"player_id": 2, "full_name": "Axar Patel", "country": "India"}
        )  # role and styles unknown
        repo.upsert_player(
            conn, {"player_id": 3, "full_name": "Babar Azam", "country": "Pakistan"}
        )
        repo.upsert_player(conn, {"player_id": 4, "full_name": "Sample Alpha Player 01",
                                  "country": "Alphaland", "is_sample": 1})  # fmt: skip
    result = query_runner.run_query(1, db)
    assert result["columns"] == [
        "player_name", "playing_role", "batting_style", "bowling_style",
    ]  # fmt: skip
    assert result["rows"] == [
        ("Axar Patel", "Unknown", "Not listed", "Not listed"),
        ("Virat Kohli", "Batsman", "Right-hand bat", "Right-arm medium"),
    ]


def test_q1_uses_the_country_index(db):
    plan = " ".join(query_runner.explain(1, db))
    assert "idx_players_country" in plan


def test_format_table_aligns_and_shows_blanks():
    text = query_runner.format_table(["a", "bb"], [(1, None), (22, "x")])
    assert text.splitlines()[0].startswith("a ")
    assert "22" in text


# ------------------------------------------------------------------- Q2 ----
def _days_ago(n):
    from datetime import date, timedelta

    return (date.today() - timedelta(days=n)).isoformat()


def _q2_world(db):
    with transaction(db) as conn:
        repo.upsert_team(conn, {"team_id": 1, "team_name": "India"})
        repo.upsert_team(conn, {"team_id": 2, "team_name": "Wales"})
        repo.upsert_venue(
            conn, {"venue_id": 1, "venue_name": "Holkar Stadium", "city": "Indore"}
        )
        repo.upsert_venue(conn, {"venue_id": 2, "venue_name": "Nowhere Oval"})
        base = {"format": "T20", "team1_id": 1, "team2_id": 2, "state": "Complete"}
        rows = [
            (1, "yesterday", _days_ago(1), 1, "Complete"),
            (2, "ten days ago", _days_ago(10), 2, "Complete"),
            (3, "exactly 30 days", _days_ago(30), 1, "Complete"),
            (4, "too old", _days_ago(31), 1, "Complete"),
            (5, "future fixture", _days_ago(-3), 1, "Complete"),
            (6, "still live", _days_ago(0), 1, "In Progress"),
            (7, "no venue", _days_ago(5), None, "Complete"),
        ]
        for match_id, desc, day, venue, state in rows:
            repo.upsert_match(
                conn,
                {**base, "match_id": match_id, "match_desc": desc,
                 "match_date": day, "venue_id": venue, "state": state},
            )  # fmt: skip


def test_q2_returns_only_played_matches_from_the_last_30_days(db):
    _q2_world(db)
    descs = [row[0] for row in query_runner.run_query(2, db)["rows"]]
    assert descs == ["yesterday", "no venue", "ten days ago", "exactly 30 days"]


def test_q2_venue_text_and_missing_venue(db):
    _q2_world(db)
    rows = {r[0]: r for r in query_runner.run_query(2, db)["rows"]}
    assert rows["yesterday"][3] == "Holkar Stadium, Indore"
    assert rows["ten days ago"][3] == "Nowhere Oval"  # no city -> no dangling comma
    assert rows["no venue"][3] == "Unknown venue"


def test_q2_is_newest_first_and_uses_the_date_index(db):
    _q2_world(db)
    dates = [row[4] for row in query_runner.run_query(2, db)["rows"]]
    assert dates == sorted(dates, reverse=True)
    assert "idx_matches_date" in " ".join(query_runner.explain(2, db))
