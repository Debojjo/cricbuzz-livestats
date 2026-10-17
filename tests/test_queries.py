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


# --------------------------------------------------------------- Q3 - Q8 ----
def _player(conn, pid, name, **extra):
    repo.upsert_player(conn, {"player_id": pid, "full_name": name, **extra})


def test_q3_top_ten_odi_scorers_only(db):
    with transaction(db) as conn:
        for i in range(1, 13):
            _player(conn, i, f"Batter {i:02d}")
            repo.upsert_career_stats(
                conn,
                {"player_id": i, "format": "ODI", "runs": 1000 * i,
                 "batting_avg": 40.0 + i, "centuries": i},
            )  # fmt: skip
        repo.upsert_career_stats(conn, {"player_id": 1, "format": "T20", "runs": 99999})
        repo.upsert_career_stats(conn, {"player_id": 2, "format": "ODI", "runs": 0})
        # a tie for 10th place is broken by name, so the result is repeatable
        _player(conn, 20, "Aaron Tie")
        repo.upsert_career_stats(conn, {"player_id": 20, "format": "ODI", "runs": 3000})
    result = query_runner.run_query(3, db)
    names = [r[0] for r in result["rows"]]
    assert len(names) == 10
    assert names[:3] == ["Batter 12", "Batter 11", "Batter 10"]
    # two players tie on 3000 runs for the last place: the name decides, so the
    # answer is the same every time
    assert names[-1] == "Aaron Tie" and "Batter 03" not in names
    assert "Batter 01" not in names  # its T20 total must not leak in
    assert result["columns"] == [
        "player_name",
        "total_runs",
        "batting_avg",
        "centuries",
    ]


def test_q3_keeps_players_whose_average_is_unknown(db):
    with transaction(db) as conn:
        _player(conn, 1, "No Average")
        repo.upsert_career_stats(conn, {"player_id": 1, "format": "ODI", "runs": 500})
    assert query_runner.run_query(3, db)["rows"] == [("No Average", 500, None, None)]


def test_q4_only_venues_strictly_above_50000_largest_first(db):
    with transaction(db) as conn:
        for vid, name, cap in [
            (1, "Big", 132000), (2, "Edge", 50000), (3, "Mid", 50001),
            (4, "Small", 20000), (5, "Unknown", None),
        ]:  # fmt: skip
            repo.upsert_venue(
                conn,
                {"venue_id": vid, "venue_name": name, "city": "C", "country": "X",
                 "capacity": cap},
            )  # fmt: skip
    rows = query_runner.run_query(4, db)["rows"]
    assert [r[0] for r in rows] == ["Big", "Mid"]
    assert rows[0] == ("Big", "C", "X", 132000)


def test_q5_counts_wins_per_team_ignoring_matches_without_a_winner(db):
    with transaction(db) as conn:
        for tid, name in [(1, "India"), (2, "Wales"), (3, "Idle"), (4, "India")]:
            repo.upsert_team(conn, {"team_id": tid, "team_name": name})
        plan = [(1, 1, 2, 1), (2, 1, 2, 1), (3, 2, 1, 2), (4, 1, 2, None), (5, 4, 2, 4)]
        for mid, a, b, winner in plan:
            repo.upsert_match(
                conn,
                {"match_id": mid, "format": "T20", "team1_id": a, "team2_id": b,
                 "winner_id": winner},
            )  # fmt: skip
    rows = query_runner.run_query(5, db)["rows"]
    assert rows == [("India", 2), ("India", 1), ("Wales", 1)]  # two different Indias
    assert all(r[0] != "Idle" for r in rows)


def test_q6_counts_roles_and_shows_unknown_instead_of_hiding_it(db):
    with transaction(db) as conn:
        roles = ["Batsman", "Batsman", "Bowler", None, None, None]
        for i, role in enumerate(roles, start=1):
            _player(conn, i, f"P{i}", playing_role=role)
    rows = query_runner.run_query(6, db)["rows"]
    assert rows == [("Unknown", 3), ("Batsman", 2), ("Bowler", 1)]
    assert sum(r[1] for r in rows) == 6  # totals add up to all players


def test_q7_best_score_per_format_with_ties_and_labels(db):
    with transaction(db) as conn:
        for pid, name in [(1, "Alpha"), (2, "Beta"), (3, "Gamma")]:
            _player(conn, pid, name)
        data = [
            (1, "TEST", 400), (2, "TEST", 380), (1, "ODI", 264), (2, "ODI", 264),
            (3, "T20", 172), (1, "T20", 100),
        ]  # fmt: skip
        for pid, fmt, score in data:
            repo.upsert_career_stats(
                conn, {"player_id": pid, "format": fmt, "highest_score": score}
            )
    assert query_runner.run_query(7, db)["rows"] == [
        ("Test", 400, "Alpha"),
        ("ODI", 264, "Alpha"),
        ("ODI", 264, "Beta"),  # tie: both named
        ("T20I", 172, "Gamma"),
    ]


def test_q8_selects_exactly_the_calendar_year_2024(db):
    with transaction(db) as conn:
        rows = [
            (1, "Ended 2023", "2023-12-31", None),
            (2, "Opens 2024", "2024-01-01", "India"),
            (3, "Closes 2024", "2024-12-31", None),
            (4, "Starts 2025", "2025-01-01", None),
            (5, "No date", None, None),
        ]
        for sid, name, start, host in rows:
            repo.upsert_series(
                conn,
                {"series_id": sid, "series_name": name, "start_date": start,
                 "host_country": host},
            )  # fmt: skip
    rows = query_runner.run_query(8, db)["rows"]
    assert [r[0] for r in rows] == ["Opens 2024", "Closes 2024"]
    assert rows[0][1] == "India" and rows[1][1] == "Not stated"
    assert rows[1][2] == "Not stated" and rows[1][4] is None


def test_beginner_queries_use_their_indexes(db):
    assert "idx_career_format" in " ".join(query_runner.explain(3, db))
    assert "idx_venues_capacity" in " ".join(query_runner.explain(4, db))
    assert "idx_series_start" in " ".join(query_runner.explain(8, db))


def test_run_all_reports_every_query(db):
    results = query_runner.run_all(db)
    assert [r[0] for r in results][:8] == list(range(1, 9))
    assert all(r[1] >= 0 for r in results)  # no query raised an error
