"""Phase 8 verification: does the database enforce the rules we designed?

Each test builds a fresh temporary database, so nothing here touches your real
data file. Run with:  python -m pytest tests/test_db_schema.py -v
"""

import sqlite3

import pytest

from database.init_db import describe_db, init_db
from utils.db_connection import fetch_all, get_connection

EXPECTED_TABLES = {
    "teams",
    "players",
    "venues",
    "series",
    "matches",
    "batting_performances",
    "bowling_performances",
    "fielding_performances",
    "partnerships",
    "player_career_stats",
    "api_call_log",
}
EXPECTED_VIEWS = {
    "v_match_results",
    "v_batting_detail",
    "v_bowling_detail",
    "v_partnership_detail",
}


@pytest.fixture()
def db_path(tmp_path):
    """A freshly built, empty database."""
    return init_db(tmp_path / "test.db")


@pytest.fixture()
def conn(db_path):
    """Connection to the fresh database, closed automatically after the test."""
    connection = get_connection(db_path)
    yield connection
    connection.close()


def add_basics(conn):
    """Insert the minimum rows other tables need (2 teams, venue, 2 players)."""
    conn.executemany(
        "INSERT INTO teams(team_id, team_name, country) VALUES (?, ?, ?)",
        [(2, "India", "India"), (10, "West Indies", "West Indies")],
    )
    conn.execute(
        "INSERT INTO venues(venue_id, venue_name, city, country) "
        "VALUES (152, 'Holkar Stadium', 'Indore', 'India')"
    )
    conn.executemany(
        "INSERT INTO players(player_id, full_name) VALUES (?, ?)",
        [(1, "Player One"), (2, "Player Two")],
    )
    conn.commit()


def add_match(conn, match_id=100, **overrides):
    """Insert a valid match, with optional column overrides."""
    row = {
        "match_id": match_id,
        "format": "T20",
        "match_date": "2026-10-09",
        "venue_id": 152,
        "team1_id": 2,
        "team2_id": 10,
        "toss_winner_id": 10,
        "toss_decision": "bowl",
        "winner_id": 2,
        "victory_type": "runs",
        "victory_margin": 14,
    }
    row.update(overrides)
    cols = ", ".join(row)
    marks = ", ".join("?" for _ in row)
    conn.execute(f"INSERT INTO matches({cols}) VALUES ({marks})", list(row.values()))
    conn.commit()


# ------------------------------------------------------------- structure ----
def test_all_tables_and_views_exist(db_path):
    summary = describe_db(db_path)
    assert EXPECTED_TABLES <= set(summary["table"])
    assert EXPECTED_VIEWS <= set(summary["view"])
    assert len(summary["index"]) >= 20


def test_init_is_idempotent(db_path):
    init_db(db_path)  # second run must not fail or lose tables
    assert EXPECTED_TABLES <= set(describe_db(db_path)["table"])


def test_foreign_keys_are_switched_on(conn):
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1


# ----------------------------------------------------------- constraints ----
def test_match_with_unknown_team_is_rejected(conn):
    with pytest.raises(sqlite3.IntegrityError):
        add_match(conn)  # teams 2 and 10 do not exist yet


def test_invalid_format_is_rejected(conn):
    add_basics(conn)
    with pytest.raises(sqlite3.IntegrityError):
        add_match(conn, format="T20I")


def test_team_cannot_play_itself(conn):
    add_basics(conn)
    with pytest.raises(sqlite3.IntegrityError):
        add_match(conn, team2_id=2, winner_id=None, toss_winner_id=None)


def test_winner_must_be_one_of_the_two_teams(conn):
    add_basics(conn)
    conn.execute("INSERT INTO teams(team_id, team_name) VALUES (99,'Other')")
    with pytest.raises(sqlite3.IntegrityError):
        add_match(conn, winner_id=99)


def test_negative_runs_are_rejected(conn):
    add_basics(conn)
    add_match(conn)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO batting_performances(match_id, innings_no, player_id,"
            " team_id, runs) VALUES (100, 1, 1, 2, -5)"
        )


def test_duplicate_batting_row_is_rejected(conn):
    add_basics(conn)
    add_match(conn)
    sql = (
        "INSERT INTO batting_performances(match_id, innings_no, player_id,"
        " team_id, runs) VALUES (100, 1, 1, 2, 10)"
    )
    conn.execute(sql)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(sql)


def test_cannot_delete_a_team_that_has_matches(conn):
    add_basics(conn)
    add_match(conn)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("DELETE FROM teams WHERE team_id = 2")


def test_partnership_needs_two_different_batters(conn):
    add_basics(conn)
    add_match(conn)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO partnerships(match_id, innings_no, wicket_no, bat1_id,"
            " bat2_id, runs) VALUES (100, 1, 1, 1, 1, 20)"
        )


# ----------------------------------------------------------------- views ----
def test_views_return_expected_values(db_path):
    conn = get_connection(db_path)
    try:
        add_basics(conn)
        add_match(conn)
        conn.execute(
            "INSERT INTO batting_performances(match_id, innings_no, player_id,"
            " team_id, batting_position, runs, balls_faced) VALUES"
            " (100, 1, 1, 2, 1, 60, 30), (100, 1, 2, 2, 2, 45, 25)"
        )
        conn.execute(
            "INSERT INTO bowling_performances(match_id, innings_no, player_id,"
            " team_id, overs, balls, runs_conceded, wickets) VALUES"
            " (100, 2, 2, 10, 3.5, 23, 33, 3)"
        )
        conn.execute(
            "INSERT INTO partnerships(match_id, innings_no, wicket_no, bat1_id,"
            " bat2_id, runs, balls) VALUES (100, 1, 1, 1, 2, 105, 55)"
        )
        conn.commit()
    finally:
        conn.close()

    match = fetch_all("SELECT * FROM v_match_results", db_path=db_path)[0]
    assert match["winner_name"] == "India"
    assert match["venue_city"] == "Indore"
    assert match["toss_winner_name"] == "West Indies"

    bat = fetch_all(
        "SELECT * FROM v_batting_detail WHERE player_id = 1", db_path=db_path
    )[0]
    assert bat["team_won"] == 1
    assert bat["opponent_id"] == 10
    assert bat["match_year"] == 2026
    assert bat["match_quarter"] == 4  # October is in Q4

    bowl = fetch_all("SELECT * FROM v_bowling_detail", db_path=db_path)[0]
    assert bowl["economy_calc"] == pytest.approx(8.61, abs=0.01)  # 33*6/23

    pair = fetch_all("SELECT * FROM v_partnership_detail", db_path=db_path)[0]
    assert pair["is_consecutive"] == 1
    assert pair["bat1_name"] == "Player One"


# ------------------------------------------------------------- read-only ----
def test_read_only_connection_blocks_writes(db_path):
    conn = get_connection(db_path, read_only=True)
    try:
        with pytest.raises(sqlite3.OperationalError):
            conn.execute("INSERT INTO teams(team_id, team_name) VALUES (1,'X')")
    finally:
        conn.close()
