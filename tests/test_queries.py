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
                "INSERT INTO partnerships (match_id, innings_no, wicket_no, bat1_id,"
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
