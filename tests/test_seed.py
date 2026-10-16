"""Seed generator tests: consistency, honesty (flags) and safety (real rows)."""

from datetime import date

import pytest

from data import coverage_report, seed_sample_data as seed
from database import repositories as repo
from database.init_db import init_db
from utils.db_connection import fetch_all, transaction

TODAY = date(2026, 10, 15)


def q(db, sql):
    return fetch_all(sql, db_path=db)


@pytest.fixture(scope="module")
def seeded(tmp_path_factory):
    db = init_db(tmp_path_factory.mktemp("seed") / "seed.db")
    with transaction(db) as conn:
        summary = seed.generate(conn, matches=700, seed=2026, today=TODAY)
    return db, summary


def test_counts_and_flags(seeded):
    db, summary = seeded
    assert summary["matches"] == 700 and summary["teams"] == 8
    for table in ("teams", "players", "venues", "matches", "batting_performances"):
        total = q(db, f"SELECT COUNT(*) n FROM {table}")[0]["n"]
        flagged = q(db, f"SELECT COUNT(*) n FROM {table} WHERE is_sample = 1")[0]["n"]
        assert total == flagged > 0, table


def test_only_fictional_names_are_used(seeded):
    db, _ = seeded
    names = q(db, "SELECT team_name FROM teams UNION SELECT full_name FROM players")
    assert all(n["team_name"].startswith("Sample") for n in names)


def test_partnerships_add_up_to_what_bowlers_conceded(seeded):
    db, _ = seeded
    bad = q(
        db,
        """SELECT COUNT(*) n FROM
           (SELECT match_id, innings_no, SUM(runs_conceded) rc FROM bowling_performances GROUP BY 1,2) a
           JOIN (SELECT match_id, innings_no, SUM(runs) pr FROM partnerships GROUP BY 1,2) b
           USING (match_id, innings_no) WHERE rc != pr""",
    )[0]["n"]
    assert bad == 0


def test_bowler_wickets_match_the_dismissals(seeded):
    db, _ = seeded
    bad = q(
        db,
        """SELECT COUNT(*) n FROM
           (SELECT match_id, innings_no, SUM(wickets) w FROM bowling_performances GROUP BY 1,2) a
           JOIN (SELECT match_id, innings_no, COUNT(*) k FROM batting_performances
                 WHERE is_not_out = 0 AND out_desc NOT LIKE 'run out%' GROUP BY 1,2) b
           USING (match_id, innings_no) WHERE w != k""",
    )[0]["n"]
    assert bad == 0


def test_results_are_consistent_with_the_scores(seeded):
    db, _ = seeded
    rows = q(
        db,
        """SELECT m.match_id, m.winner_id, m.victory_type, m.victory_margin,
                  (SELECT SUM(runs) FROM partnerships p WHERE p.match_id=m.match_id AND p.innings_no=1) r1,
                  (SELECT SUM(runs) FROM partnerships p WHERE p.match_id=m.match_id AND p.innings_no=2) r2
           FROM matches m WHERE m.victory_type = 'runs'""",
    )
    assert rows and all(r["victory_margin"] == r["r1"] - r["r2"] for r in rows)


def test_realistic_scoring_levels(seeded):
    db, _ = seeded
    t20 = q(
        db,
        """SELECT AVG(s) a FROM (SELECT SUM(runs) s FROM partnerships p JOIN matches m USING(match_id)
           WHERE m.format='T20' AND p.innings_no=1 GROUP BY p.match_id)""",
    )[0]["a"]
    odi = q(
        db,
        """SELECT AVG(s) a FROM (SELECT SUM(runs) s FROM partnerships p JOIN matches m USING(match_id)
           WHERE m.format='ODI' AND p.innings_no=1 GROUP BY p.match_id)""",
    )[0]["a"]
    assert 120 < t20 < 190 and 200 < odi < 320


def test_dates_stay_in_the_past_and_span_the_years(seeded):
    db, _ = seeded
    row = q(db, "SELECT MIN(match_date) lo, MAX(match_date) hi FROM matches")[0]
    assert row["lo"] >= "2020-01-15" and row["hi"] < TODAY.isoformat()


def test_seeding_fills_the_history_questions(seeded):
    db, _ = seeded
    report = {r[0]: r[4].strip() for r in coverage_report.coverage(db)}
    for question in ("Q16", "Q18", "Q19", "Q22", "Q23", "Q24", "Q25", "Q14", "Q17"):
        assert report[question] in ("OK", "THIN"), question
    assert report["Q16"] == report["Q19"] == report["Q23"] == "OK"


def test_same_seed_gives_the_same_data(tmp_path):
    totals = []
    for name in ("a.db", "b.db"):
        db = init_db(tmp_path / name)
        with transaction(db) as conn:
            seed.generate(conn, matches=40, seed=5, today=TODAY)
        totals.append(
            q(db, "SELECT SUM(runs) s, COUNT(*) n FROM batting_performances")[0]
        )
    assert totals[0] == totals[1]


def test_rerunning_replaces_sample_rows_and_never_touches_real_ones(tmp_path):
    db = init_db(tmp_path / "r.db")
    with transaction(db) as conn:
        repo.upsert_team(
            conn, {"team_id": 2, "team_name": "India", "short_name": "IND"}
        )
        seed.generate(conn, matches=30, seed=1, today=TODAY)
    with transaction(db) as conn:
        seed.generate(conn, matches=30, seed=2, today=TODAY)
    assert q(db, "SELECT COUNT(*) n FROM matches")[0]["n"] == 30  # not 60
    real = q(db, "SELECT * FROM teams WHERE is_sample = 0")
    assert [r["team_name"] for r in real] == ["India"]
