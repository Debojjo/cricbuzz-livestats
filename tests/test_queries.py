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
        label = query_runner.label_of(path)
        result = query_runner.run_query(label, db)
        assert result["rows"] == [] or isinstance(result["rows"], list)
        assert query_runner.explain(label, db)


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
    assert query_runner.label_of(query_runner.QUERY_DIR / "q22b_x.sql") == "22b"
    assert all(r[1] >= 0 for r in results)  # no query raised an error
    labels = [r[0] for r in results]
    assert len(labels) == len(set(labels))  # each query listed exactly once
    assert "22b" in labels and "25b" in labels  # companions are separate entries
    assert labels.index(22) + 1 == labels.index("22b")


# -------------------------------------------------------------- Q9 - Q13 ----
def _career(conn, pid, fmt, **kw):
    repo.upsert_career_stats(conn, {"player_id": pid, "format": fmt, **kw})


def test_q9_allrounders_over_both_thresholds_with_strict_comparisons(db):
    with transaction(db) as conn:
        cases = [
            (1, "Batting Allrounder", 5000, 100),  # qualifies
            (2, "Allrounder", 1001, 51),  # just over both
            (3, "All-rounder", 2000, 80),  # hand-typed spelling
            (4, "Allrounder", 1000, 90),  # exactly 1000 runs: not more than
            (5, "Allrounder", 3000, 50),  # exactly 50 wickets: not more than
            (6, "Bowler", 4000, 200),  # wrong role
            (7, None, 4000, 200),  # no role known
        ]
        for pid, role, runs, wkts in cases:
            _player(conn, pid, f"P{pid}", playing_role=role)
            _career(conn, pid, "ODI", runs=runs, wickets=wkts)
        _career(conn, 1, "TEST", runs=1500, wickets=60)  # same player, second format
    rows = query_runner.run_query(9, db)["rows"]
    assert rows == [
        ("P1", 1500, 60, "Test"),
        ("P1", 5000, 100, "ODI"),
        ("P3", 2000, 80, "ODI"),
        ("P2", 1001, 51, "ODI"),
    ]


def _twenty_five_matches(conn):
    repo.upsert_team(conn, {"team_id": 1, "team_name": "A"})
    repo.upsert_team(conn, {"team_id": 2, "team_name": "B"})
    repo.upsert_venue(conn, {"venue_id": 1, "venue_name": "Oval"})
    for i in range(1, 26):
        winner = None if i == 25 else (1 if i % 2 else 2)
        repo.upsert_match(
            conn,
            {"match_id": i, "match_desc": f"M{i:02d}", "format": "ODI",
             "match_date": f"2026-09-{i:02d}", "team1_id": 1, "team2_id": 2,
             "venue_id": 1, "winner_id": winner, "state": "Complete",
             "victory_type": "runs" if winner else "draw",
             "victory_margin": 10 if winner else None},
        )  # fmt: skip
    repo.upsert_match(
        conn,
        {"match_id": 99, "match_desc": "LIVE", "format": "ODI",
         "match_date": "2026-10-01", "team1_id": 1, "team2_id": 2,
         "state": "In Progress"},
    )  # fmt: skip


def test_q10_exactly_the_20_newest_completed_matches(db):
    with transaction(db) as conn:
        _twenty_five_matches(conn)
    result = query_runner.run_query(10, db)
    descs = [r[0] for r in result["rows"]]
    assert len(descs) == 20
    assert descs[0] == "M25" and descs[-1] == "M06"  # newest first, M01-M05 cut
    assert "LIVE" not in descs  # unfinished matches are not 'completed'
    first = result["rows"][0]  # the draw
    assert first[3] == "No winner" and first[5] == "draw"
    assert result["rows"][1][3] in ("A", "B") and result["rows"][1][5] == "runs"
    assert result["rows"][1][6] == "Oval"


def test_q11_cross_format_runs_and_weighted_average(db):
    with transaction(db) as conn:
        _player(conn, 1, "Both Formats")
        _career(conn, 1, "TEST", matches_played=70, runs=4288, innings=122, not_outs=5)
        _career(conn, 1, "ODI", matches_played=101, runs=3541, innings=91, not_outs=22)
        _player(conn, 2, "One Format")
        _career(conn, 2, "ODI", matches_played=50, runs=2000, innings=50, not_outs=2)
        _player(conn, 3, "Second Row Is Empty")
        _career(conn, 3, "ODI", matches_played=50, runs=900, innings=50, not_outs=2)
        _career(conn, 3, "T20", matches_played=0, runs=0)  # never played T20
        _player(conn, 4, "Missing Not Outs")
        _career(conn, 4, "ODI", matches_played=10, runs=500, innings=10, not_outs=1)
        _career(
            conn, 4, "T20", matches_played=10, runs=300, innings=10
        )  # not_outs unknown
    rows = {r[0]: r for r in query_runner.run_query(11, db)["rows"]}
    assert set(rows) == {"Both Formats", "Missing Not Outs"}
    both = rows["Both Formats"]
    assert (both[1], both[2], both[3]) == (4288, 3541, None)  # no T20 row -> blank
    assert both[4] == pytest.approx((4288 + 3541) / ((122 - 5) + (91 - 22)), abs=0.01)
    assert both[5] == 2
    assert rows["Missing Not Outs"][4] is None  # unknown beats wrong


def test_q12_home_and_away_records(db):
    with transaction(db) as conn:
        for tid, name, country in [
            (1, "A", "Aland"),
            (2, "B", "Bland"),
            (3, "C", "Cland"),
        ]:
            repo.upsert_team(
                conn, {"team_id": tid, "team_name": name, "country": country}
            )
        repo.upsert_team(conn, {"team_id": 4, "team_name": "Club"})  # no country
        for vid, country in [(1, "Aland"), (2, "Bland"), (3, "Zland"), (4, None)]:
            repo.upsert_venue(
                conn, {"venue_id": vid, "venue_name": f"V{vid}", "country": country}
            )
        games = [  # id, venue, team1, team2, winner, category
            (1, 1, 1, 2, 1, "international"),
            (2, 1, 1, 2, 2, "international"),
            (3, 2, 1, 2, 1, "international"),
            (4, 3, 1, 3, 3, "international"),
            (5, 1, 1, 2, None, "international"),  # draw at A's home
            (6, 1, 1, 2, 1, "domestic"),  # not international
            (7, 4, 1, 2, 1, "international"),  # venue country unknown
            (8, 1, 1, 4, 1, "international"),  # Club has no country
        ]
        for mid, vid, a, b, win, cat in games:
            repo.upsert_match(
                conn,
                {"match_id": mid, "format": "T20", "venue_id": vid, "team1_id": a,
                 "team2_id": b, "winner_id": win, "match_category": cat,
                 "state": "Complete"},
            )  # fmt: skip
    rows = {r[0]: r[1:] for r in query_runner.run_query(12, db)["rows"]}
    #            home: m, w, %      away: m, w, %
    assert rows["A"] == (4, 2, 50.0, 2, 1, 50.0)  # draw counts as a match, not a win
    assert rows["B"] == (1, 0, 0.0, 3, 1, 33.3)
    assert rows["C"] == (0, 0, None, 1, 1, 100.0)  # never played at home: no percentage
    assert "Club" not in rows  # a team without a country is left out, not an error


def test_q12_teams_without_country_are_excluded(db):
    with transaction(db) as conn:
        repo.upsert_team(conn, {"team_id": 1, "team_name": "A", "country": "Aland"})
        repo.upsert_team(conn, {"team_id": 2, "team_name": "Club"})
        repo.upsert_venue(conn, {"venue_id": 1, "venue_name": "V", "country": "Aland"})
        repo.upsert_match(
            conn,
            {"match_id": 1, "format": "T20", "venue_id": 1, "team1_id": 1,
             "team2_id": 2, "winner_id": 1, "match_category": "international",
             "state": "Complete"},
        )  # fmt: skip
    assert [r[0] for r in query_runner.run_query(12, db)["rows"]] == ["A"]


def test_q13_only_consecutive_partnerships_of_100_or_more(db):
    with transaction(db) as conn:
        repo.upsert_team(conn, {"team_id": 1, "team_name": "A"})
        repo.upsert_team(conn, {"team_id": 2, "team_name": "B"})
        repo.upsert_match(
            conn,
            {"match_id": 1, "format": "ODI", "match_date": "2026-01-01",
             "team1_id": 1, "team2_id": 2},
        )  # fmt: skip
        for pid in range(1, 8):
            _player(conn, pid, f"Bat{pid}")
            conn.execute(
                "INSERT INTO batting_performances (match_id, innings_no, player_id,"
                " team_id, batting_position, runs) VALUES (1, 1, ?, 1, ?, 10)",
                (pid, pid),
            )
        pairs = [  # wicket, bat1, bat2, runs
            (1, 1, 2, 120),  # positions 1-2, consecutive, qualifies
            (2, 3, 4, 100),  # exactly 100, consecutive, qualifies
            (3, 5, 6, 99),  # consecutive but too small
            (4, 1, 3, 150),  # positions 1 and 3: NOT consecutive
        ]
        for wicket, a, b, runs in pairs:
            conn.execute(
                "INSERT INTO partnerships (match_id, innings_no, wicket_no,"
                " bat1_id,"
                " bat2_id, runs) VALUES (1, 1, ?, ?, ?, ?)",
                (wicket, a, b, runs),
            )
    rows = query_runner.run_query(13, db)["rows"]
    assert [(r[0], r[1], r[2], r[3]) for r in rows] == [
        ("Bat1", "Bat2", 120, 1),
        ("Bat3", "Bat4", 100, 1),
    ]


def test_q10_reads_the_date_index_instead_of_sorting_everything(db):
    plan = " ".join(query_runner.explain(10, db))
    assert "idx_matches_date" in plan
    assert "TEMP B-TREE FOR ORDER BY" not in plan  # index order is reused


# ------------------------------------------------------------- Q14 - Q18 ----
def _basics(conn, players=()):
    repo.upsert_team(conn, {"team_id": 1, "team_name": "A"})
    repo.upsert_team(conn, {"team_id": 2, "team_name": "B"})
    repo.upsert_venue(conn, {"venue_id": 1, "venue_name": "Oval"})
    repo.upsert_venue(conn, {"venue_id": 2, "venue_name": "Park"})
    for pid in players:
        _player(conn, pid, f"P{pid}")


def _match(conn, mid, date="2026-01-01", fmt="ODI", venue=1, **kw):
    repo.upsert_match(
        conn,
        {"match_id": mid, "format": fmt, "match_date": date, "venue_id": venue,
         "team1_id": 1, "team2_id": 2, "state": "Complete", **kw},
    )  # fmt: skip


def _spell(conn, mid, pid, balls, runs, wickets=0):
    conn.execute(
        "INSERT INTO bowling_performances (match_id, innings_no, player_id, team_id,"
        " overs, balls, runs_conceded, wickets) VALUES (?, 1, ?, 2, ?, ?, ?, ?)",
        (mid, pid, balls / 6, balls, runs, wickets),
    )


def _bat(conn, mid, pid, runs, balls=30, sr=None, innings=1, team=1):
    conn.execute(
        "INSERT INTO batting_performances (match_id, innings_no, player_id, team_id,"
        " runs, balls_faced, strike_rate) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (mid, innings, pid, team, runs, balls, sr),
    )


def test_q14_needs_three_matches_with_full_four_over_spells(db):
    with transaction(db) as conn:
        _basics(conn, players=[1, 2, 3])
        for mid in range(1, 5):
            _match(conn, mid, venue=1)
        _match(conn, 5, venue=2)
        # P1: four full spells at the Oval (economies 6.0, 7.5, 9.0, 2.5) and one at
        # the Park, which must not be added to the Oval figures.
        for mid, runs, wkts in [(1, 24, 1), (2, 30, 2), (3, 36, 3), (4, 10, 0)]:
            _spell(conn, mid, 1, 24, runs, wkts)
        _spell(conn, 5, 1, 24, 10)
        # P2: match 3 is only a 3-over spell, so just 2 qualifying matches remain.
        for mid in (1, 2, 3):
            _spell(conn, mid, 2, 24 if mid != 3 else 18, 20)
        # P3: four spells of 5 overs at the Oval, economy 5.0.
        for mid in (1, 2, 3, 4):
            _spell(conn, mid, 3, 30, 25, 1)
    rows = query_runner.run_query(14, db)["rows"]
    assert rows == [
        ("P3", "Oval", 4, 4, 5.0),
        ("P1", "Oval", 4, 6, 6.25),  # equal matches: the lower economy ranks first
    ]


def _close_world(conn):
    _basics(conn, players=[1, 2])
    specs = [  # id, type, margin, winner
        (1, "runs", 10, 1), (2, "wickets", 3, 2), (6, "runs", 49, 1),
        (7, "runs", 50, 1), (3, "runs", 80, 1), (4, "wickets", 7, 1),
    ]  # fmt: skip
    for mid, vtype, margin, winner in specs:
        _match(conn, mid, victory_type=vtype, victory_margin=margin, winner_id=winner)
    for mid, runs in [(1, 50), (2, 30), (6, 70), (7, 400), (3, 200), (4, 150)]:
        _bat(conn, mid, 1, runs)
    for mid, runs in [(1, 10), (2, 10)]:
        _bat(conn, mid, 2, runs)  # only 2 close matches: below the minimum of 3


def test_q15_close_match_definition_minimum_and_wins(db):
    with transaction(db) as conn:
        _close_world(conn)
    rows = query_runner.run_query(15, db)["rows"]
    assert rows == [("P1", 50.0, 3, 2)]  # avg of 50, 30, 70; won matches 1 and 6
    # margin 50 runs (not < 50), 80 runs, 7 wickets and everyone's other innings
    # are not close; P2 has just 2 close matches


def test_q16_yearly_trend_filters_year_and_match_count(db):
    with transaction(db) as conn:
        _basics(conn, players=[1])
        years = {2025: 5, 2024: 4, 2019: 6}  # only 2025 qualifies
        mid = 0
        for year, n in years.items():
            for k in range(n):
                mid += 1
                _match(conn, mid, date=f"{year}-0{k + 1}-10")
                _bat(conn, mid, 1, 10 * (k + 1), sr=100 + 20 * k)
    rows = query_runner.run_query(16, db)["rows"]
    assert rows == [("P1", 2025, 5, 30.0, 140.0)]


def test_q16_zero_ball_innings_do_not_drag_down_the_strike_rate(db):
    with transaction(db) as conn:
        _basics(conn, players=[1])
        for k in range(5):
            _match(conn, k + 1, date=f"2025-0{k + 1}-10")
            _bat(
                conn,
                k + 1,
                1,
                10,
                balls=0 if k == 0 else 10,
                sr=0.0 if k == 0 else 100.0,
            )
    assert query_runner.run_query(16, db)["rows"][0][4] == 100.0


def test_q17_toss_advantage_by_decision_with_overall(db):
    with transaction(db) as conn:
        _basics(conn)
        games = [  # toss winner, decision, winner
            (1, "bat", 1),
            (1, "bat", 1),
            (2, "bat", 1),
            (1, "bat", 1),  # bat: 3 of 4
            (1, "bowl", 1),
            (2, "bowl", 1),  # bowl: 1 of 2
            (1, "bat", None),  # draw: ignored
        ]
        for i, (toss, decision, winner) in enumerate(games, start=1):
            _match(
                conn, i, toss_winner_id=toss, toss_decision=decision, winner_id=winner
            )
        _match(conn, 50, winner_id=1)  # no toss recorded: ignored
    assert query_runner.run_query(17, db)["rows"] == [
        ("bat", 4, 3, 75.0),
        ("bowl", 2, 1, 50.0),
        ("overall", 6, 4, 66.7),
    ]


def test_q17_returns_nothing_instead_of_dividing_by_zero_when_no_data(db):
    assert query_runner.run_query(17, db)["rows"] == []


def test_q18_economy_thresholds_formats_and_weighting(db):
    with transaction(db) as conn:
        _basics(conn, players=[1, 2, 3, 4, 5])
        for mid in range(1, 21):
            _match(conn, mid, fmt="T20" if mid % 2 else "ODI")
        for mid in range(1, 11):
            _spell(conn, mid, 1, 12, 12, 1)  # P1: 10 matches x 2 overs, economy 6.0
        for mid in range(1, 10):
            _spell(conn, mid, 2, 24, 12)  # P2: only 9 matches
        for mid in range(1, 11):
            _spell(conn, mid, 3, 6, 6)  # P3: 1 over per match: below 2 on average
        for mid in range(1, 13):
            _spell(conn, mid, 4, 24, 18, 2)  # P4: 12 matches, economy 4.5
        for mid in range(1, 21):
            _match(conn, 100 + mid, fmt="TEST")
            _spell(conn, 100 + mid, 5, 60, 20)  # P5: Tests only
    rows = query_runner.run_query(18, db)["rows"]
    assert rows == [
        ("P4", 12, "48.0", 4.5, 24),
        ("P1", 10, "20.0", 6.0, 10),
    ]


def test_q18_shows_overs_in_cricket_notation(db):
    with transaction(db) as conn:
        _basics(conn, players=[1])
        for mid in range(1, 11):
            _match(conn, mid, fmt="ODI")
            _spell(conn, mid, 1, 23, 30)  # 3.5 overs each
    assert query_runner.run_query(18, db)["rows"][0][2] == "38.2"  # 230 balls


# ------------------------------------------------------------- Q19 - Q25 ----
def _innings(conn, mid, pid, runs, date, balls=30, sr=100.0, team=1, innings=1):
    _match(conn, mid, date=date)
    _bat(conn, mid, pid, runs, balls=balls, sr=sr, innings=innings, team=team)


def test_q19_standard_deviation_filters_and_order(db):
    with transaction(db) as conn:
        _basics(conn, players=[1, 2, 3, 4, 5])
        mid = 0
        plans = {
            1: [30] * 10,  # perfectly steady: sd 0
            2: [10, 50] * 5,  # mean 30, sd 20
            3: [30] * 9,  # only 9 innings
            4: [30] * 10,  # steady, but 3 extra short innings must be ignored
            5: [30] * 5,  # 5 recent innings + 5 from 2021 (too old)
        }
        for pid, runs_list in plans.items():
            for i, runs in enumerate(runs_list):
                mid += 1
                old = pid == 5 and i >= 5
                _innings(conn, mid, pid, runs, "2021-06-01" if old else "2024-06-01")
        for k in range(3):
            mid += 1
            _innings(conn, mid, 4, 0, "2024-06-02", balls=5)  # under 10 balls faced
    rows = query_runner.run_query(19, db)["rows"]
    assert [(r[0], r[1], r[2], r[3]) for r in rows] == [
        ("P1", 10, 30.0, 0.0),
        ("P4", 10, 30.0, 0.0),
        ("P2", 10, 30.0, 20.0),
    ]


def test_q20_pivot_and_the_20_match_minimum(db):
    with transaction(db) as conn:
        _player(conn, 1, "Two Formats")
        _career(conn, 1, "TEST", matches_played=70, batting_avg=36.65)
        _career(conn, 1, "ODI", matches_played=101, batting_avg=51.32)
        _player(conn, 2, "Too Few")
        _career(conn, 2, "ODI", matches_played=19, batting_avg=40.0)
        _player(conn, 3, "T20 Only")
        _career(conn, 3, "T20", matches_played=25, batting_avg=30.5)
    assert query_runner.run_query(20, db)["rows"] == [
        ("Two Formats", 70, 36.65, 101, 51.32, None, None, 171),
        ("T20 Only", None, None, None, None, 25, 30.5, 25),
    ]


def test_q21_applies_the_formula_exactly_and_ranks_per_format(db):
    with transaction(db) as conn:
        _basics(conn, players=[1, 2, 3])
        for mid in range(1, 7):
            _match(conn, mid, fmt="ODI")
        _match(conn, 7, fmt="TEST")
        # P1 ODI batting: 5 innings, 100 runs, 4 dismissals, 125 balls
        for mid, (runs, balls, out) in enumerate(
            [(20, 25, 0), (30, 25, 0), (10, 25, 0), (40, 25, 0), (0, 25, 1)], start=1
        ):
            conn.execute(
                "INSERT INTO batting_performances (match_id, innings_no, player_id,"
                " team_id, runs, balls_faced, is_not_out) VALUES (?, 1, 1, 1, ?, ?, ?)",
                (mid, runs, balls, out),
            )
        # P1 ODI bowling: 60 balls, 60 runs, 3 wickets; fielding 2 catches, 1 stumping
        _spell(conn, 1, 1, 60, 60, 3)
        conn.execute(
            "INSERT INTO fielding_performances"
            " (match_id, player_id, catches, stumpings)"
            " VALUES (1, 1, 2, 1)"
        )
        # P2: only 4 innings, so no batting points; 3 catches = 9 points
        for mid in range(1, 5):
            _bat(conn, mid, 2, 100, balls=50)
        conn.execute(
            "INSERT INTO fielding_performances"
            " (match_id, player_id, catches, stumpings)"
            " VALUES (2, 2, 3, 0)"
        )
        conn.execute(  # a Test appearance must be ranked in its own format
            "INSERT INTO fielding_performances"
            " (match_id, player_id, catches, stumpings)"
            " VALUES (7, 3, 1, 0)"
        )
    rows = query_runner.run_query(21, db)["rows"]
    odi = [r for r in rows if r[0] == "ODI"]
    # batting 100*.01 + 25*.5 + 80*.3 = 37.5 ; bowling 6 + 30*.5 + 0 = 21 ; fielding 6+5
    assert odi[0] == ("ODI", 1, "P1", 37.5, 21.0, 11, 69.5)
    assert odi[1] == ("ODI", 2, "P2", 0.0, 0.0, 9, 9.0)
    assert [r for r in rows if r[0] == "Test"] == [("Test", 1, "P3", 0.0, 0.0, 3, 3.0)]


def _days_back(n):
    from datetime import date, timedelta

    return (date.today() - timedelta(days=n)).isoformat()


def _pair_world(conn):
    for tid, name in [(1, "A"), (2, "B"), (3, "C")]:
        repo.upsert_team(conn, {"team_id": tid, "team_name": name})
    repo.upsert_venue(conn, {"venue_id": 1, "venue_name": "V1"})
    repo.upsert_venue(conn, {"venue_id": 2, "venue_name": "V2"})
    games = [  # id, venue, team1, team2, toss team, toss choice, winner, type, margin
        (1, 1, 1, 2, 1, "bat", 1, "runs", 10),
        (2, 1, 2, 1, 2, "bowl", 1, "wickets", 4),
        (3, 1, 1, 2, 1, "bat", 2, "wickets", 6),
        (4, 2, 1, 2, 2, "bat", 2, "runs", 30),
        (5, 1, 1, 2, None, None, None, "draw", None),
        (6, 2, 1, 2, 1, "bowl", 1, "wickets", 3),
        (7, 1, 1, 2, 1, "bat", 1, "runs", 99),  # 4 years ago: outside the window
        (8, 1, 1, 3, 1, "bat", 1, "runs", 5),  # only 1 match for pair A-C
    ]
    for mid, venue, t1, t2, toss, choice, winner, vtype, margin in games:
        _match(
            conn, mid, date=_days_back(1500 if mid == 7 else 10 + mid), venue=venue,
            team1_id=t1, team2_id=t2, toss_winner_id=toss, toss_decision=choice,
            winner_id=winner, victory_type=vtype, victory_margin=margin,
        )  # fmt: skip


def test_q22_head_to_head_summary_for_the_qualifying_pair(db):
    with transaction(db) as conn:
        _pair_world(conn)
    rows = query_runner.run_query(22, db)["rows"]
    assert len(rows) == 1  # A-C met once, and the 4-year-old match is ignored
    #      A  B  matches a_w b_w  a%   b%   a_runs a_wkts b_runs b_wkts bat1 bowl1
    assert rows[0] == ("A", "B", 6, 3, 2, 50.0, 33.3, 10.0, 3.5, 30.0, 6.0, 3, 2)


def test_q22b_batting_first_vs_bowling_first_by_venue(db):
    with transaction(db) as conn:
        _pair_world(conn)
    rows = {(r[0], r[2]): r[3:] for r in query_runner.run_query("22b", db)["rows"]}
    #                 bat_m bat_w bowl_m bowl_w
    assert rows[("A", "V1")] == (3, 2, 0, 0)
    assert rows[("B", "V1")] == (0, 0, 3, 1)
    assert rows[("A", "V2")] == (0, 0, 2, 1)
    assert rows[("B", "V2")] == (2, 1, 0, 0)
    assert len(rows) == 4


def _form_innings(conn, base_mid, pid, runs_oldest_first, srs, start_days=100):
    for i, (runs, sr) in enumerate(zip(runs_oldest_first, srs)):
        mid = base_mid + i
        _match(conn, mid, date=_days_back(start_days - i * 5))
        _bat(conn, mid, pid, runs, balls=20, sr=sr)


def test_q23_form_metrics_and_labels(db):
    with transaction(db) as conn:
        _basics(conn, players=[1, 2, 3, 4])
        # P1: oldest five score 10 each (SR 100); newest five score 40-60 (SR 140)
        _form_innings(
            conn, 100, 1, [10] * 5 + [40, 60, 50, 50, 60], [100] * 5 + [140] * 5
        )
        # P2: steady 5 per innings -> poor form
        _form_innings(conn, 200, 2, [5] * 10, [80] * 10)
        # P3: only 9 innings -> not rated
        _form_innings(conn, 300, 3, [50] * 9, [100] * 9)
        # P4: 10 normal innings plus a newer 0-ball innings, which must be ignored
        _form_innings(conn, 400, 4, [25] * 10, [90] * 10)
        _match(conn, 450, date=_days_back(1))
        _bat(conn, 450, 4, 0, balls=0, sr=0.0)
    rows = {r[0]: r for r in query_runner.run_query(23, db)["rows"]}
    assert set(rows) == {"P1", "P2", "P4"}
    p1 = rows["P1"]
    assert p1[1] == 52.0 and p1[2] == 31.0  # avg of last 5 and of last 10
    assert p1[3] == 40.0  # strike rate 140 now vs 100 before
    assert p1[4] == 4  # four scores of 50+ in the last ten
    assert p1[5] == 30.1  # 100 - 100 * 21.66 / 31
    assert p1[6] == "Excellent Form"
    assert rows["P2"][6] == "Poor Form" and rows["P2"][5] == 100.0  # identical scores
    assert rows["P4"][6] == "Average Form"  # 25 per innings, no 50s


def test_q24_pair_statistics_and_rank(db):
    with transaction(db) as conn:
        _basics(conn, players=[1, 2, 3, 4, 5, 6])
        plan = {  # wicket_no -> (bat1, bat2, [runs per match])
            1: (1, 2, [60, 40, 55, 20, 100]),
            2: (3, 4, [10, 20, 30, 40, 50]),
            3: (5, 6, [90, 90, 90, 90]),  # only 4 partnerships
            4: (1, 3, [200] * 5),  # positions 1 and 3: not consecutive
        }
        for mid in range(1, 6):
            _match(conn, mid)
            for pid in range(1, 7):
                conn.execute(
                    "INSERT INTO batting_performances (match_id, innings_no, player_id,"
                    " team_id, batting_position, runs) VALUES (?, 1, ?, 1, ?, 10)",
                    (mid, pid, pid),
                )
        for wicket, (a, b, runs_list) in plan.items():
            for mid, runs in enumerate(runs_list, start=1):
                conn.execute(
                    "INSERT INTO partnerships (match_id, innings_no, wicket_no,"
                    " bat1_id,"
                    " bat2_id, runs) VALUES (?, 1, ?, ?, ?, ?)",
                    (mid, wicket, a, b, runs),
                )
    rows = query_runner.run_query(24, db)["rows"]
    assert rows == [
        (1, "P1", "P2", 5, 55.0, 3, 100, 60.0),
        (2, "P3", "P4", 5, 30.0, 0, 50, 0.0),  # exactly 50 does not exceed 50
    ]


def _quarter_start(back):
    """A date in the calendar quarter `back` quarters before the previous one."""
    from datetime import date

    today = date.today()
    quarter = (today.month - 1) // 3  # 0-3
    index = today.year * 4 + quarter - 1 - back
    year, q = divmod(index, 4)
    return f"{year}-{q * 3 + 2:02d}-15"


def _quarters(conn, base_mid, pid, averages, matches=3):
    mid = base_mid
    for i, avg in enumerate(averages):  # first value = oldest quarter
        for _ in range(matches):
            mid += 1
            _match(conn, mid, date=_quarter_start(len(averages) - 1 - i))
            _bat(conn, mid, pid, avg, balls=20, sr=100.0)


def test_q25_career_phase_from_the_trend(db):
    with transaction(db) as conn:
        _basics(conn, players=[1, 2, 3, 4, 5])
        _quarters(conn, 100, 1, [10, 15, 20, 25, 30, 35, 40, 45])  # climbing
        _quarters(conn, 200, 2, [45, 40, 35, 30, 25, 20, 15, 10])  # falling
        _quarters(conn, 300, 3, [30, 31, 30, 29, 30, 31, 30, 29])  # flat
        _quarters(conn, 400, 4, [30] * 5)  # only 5 quarters
        _quarters(conn, 500, 5, [30] * 6, matches=2)  # quarters too thin
    rows = {r[0]: r for r in query_runner.run_query(25, db)["rows"]}
    assert set(rows) == {"P1", "P2", "P3"}
    assert rows["P1"][1] == 8 and rows["P1"][3] == 5.0  # +5 runs per quarter
    assert rows["P1"][7] == "Career Ascending"
    assert rows["P2"][3] == -5.0 and rows["P2"][7] == "Career Declining"
    assert rows["P3"][7] == "Career Stable"
    assert rows["P1"][4] == 7 and rows["P1"][5] == 0  # 7 improving steps of >10%


def test_q25b_quarter_by_quarter_labels(db):
    with transaction(db) as conn:
        _basics(conn, players=[1])
        _quarters(conn, 100, 1, [20, 30, 30, 25, 25, 10])
    rows = query_runner.run_query("25b", db)["rows"]
    assert [r[7] for r in rows] == [
        "First quarter", "Improving", "Stable", "Declining", "Stable", "Declining",
    ]  # fmt: skip
    assert rows[1][6] == 50.0 and rows[5][6] == -60.0
    assert [r[3] for r in rows] == [3] * 6
