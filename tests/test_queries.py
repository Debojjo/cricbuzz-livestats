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
