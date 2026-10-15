"""End-to-end offline load: fixtures -> parsers -> repositories -> database."""

import json

import pytest

from api import parsers
from config import BASE_DIR
from data.ingest import load_fixtures, load_scorecard
from database import repositories as repo
from database.init_db import init_db
from utils.db_connection import fetch_all, get_connection, transaction

FX = BASE_DIR / "tests" / "fixtures"


@pytest.fixture()
def loaded_db(tmp_path):
    db = init_db(tmp_path / "ingest.db")
    summary = load_fixtures(db)
    return db, summary


def test_fixture_load_fills_the_tables(loaded_db):
    db, summary = loaded_db
    assert summary["teams"] == 38

    def count(table):
        sql = f"SELECT COUNT(*) AS n FROM {table}"
        return fetch_all(sql, db_path=db)[0]["n"]

    assert count("teams") == 38
    assert count("players") >= 50
    assert count("matches") == 1
    assert count("player_career_stats") == 3


def test_match_has_result_and_toss_after_load(loaded_db):
    db, _ = loaded_db
    row = fetch_all("SELECT * FROM v_match_results", db_path=db)[0]
    assert row["winner_name"] == "India"
    assert row["victory_type"] == "runs" and row["victory_margin"] == 14
    assert row["toss_winner_name"] == "West Indies"
    assert row["toss_decision"] == "bowl"
    assert row["venue_city"] == "Indore"
    assert row["venue_country"] == "India"  # filled in by matches/get-info


def test_player_profile_and_career_rows(loaded_db):
    db, _ = loaded_db
    khawaja = fetch_all("SELECT * FROM players WHERE player_id = 6635", db_path=db)[0]
    assert khawaja["date_of_birth"] == "1986-12-18"
    rahul = fetch_all(
        "SELECT * FROM player_career_stats WHERE player_id = 8733 AND format = 'ODI'",
        db_path=db,
    )[0]
    assert rahul["runs"] == 3541 and rahul["centuries"] == 9


def test_loading_twice_creates_no_duplicates(loaded_db):
    db, _ = loaded_db
    load_fixtures(db)
    n = fetch_all("SELECT COUNT(*) AS n FROM matches", db_path=db)[0]["n"]
    assert n == 1
    n = fetch_all("SELECT COUNT(*) AS n FROM player_career_stats", db_path=db)[0]["n"]
    assert n == 3


def test_a_blank_response_never_erases_stored_data(loaded_db):
    db, _ = loaded_db
    with transaction(db) as conn:
        repo.upsert_venue(
            conn, {"venue_id": 152, "venue_name": "Holkar Stadium", "country": None}
        )
        repo.update_row(conn, "matches", {"match_id": 151587}, {"toss_winner_id": None})
    venue = fetch_all("SELECT * FROM venues WHERE venue_id = 152", db_path=db)[0]
    assert venue["country"] == "India"
    match = fetch_all("SELECT * FROM matches WHERE match_id = 151587", db_path=db)[0]
    assert match["toss_winner_id"] == 10


def test_scorecard_loads_into_a_hand_built_match(tmp_path):
    """The only scorecard we have is Ireland v USA (match 40381, 2021)."""
    db = init_db(tmp_path / "sc.db")
    payload = json.loads((FX / "scorecard_v2_sample.json").read_text())
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
                "match_id": 40381,
                "format": "T20",
                "match_date": "2021-03-22",
                "team1_id": 15,
                "team2_id": 27,
                "winner_id": 27,
                "victory_type": "runs",
                "victory_margin": 9,
            },
        )
        counts = load_scorecard(conn, payload, 40381)
    assert counts == {"batting": 20, "bowling": 12, "fielding": 8, "partnerships": 18}

    conn = get_connection(db)
    try:
        # re-loading is safe
        load_scorecard(conn, payload, 40381)
        conn.commit()
    finally:
        conn.close()
    rows = fetch_all("SELECT COUNT(*) AS n FROM batting_performances", db_path=db)[0][
        "n"
    ]
    assert rows == 20

    tucker = fetch_all(
        "SELECT * FROM v_batting_detail WHERE player_id = 11131", db_path=db
    )[0]
    assert tucker["runs"] == 84 and tucker["team_won"] == 1
    pairs = fetch_all(
        "SELECT * FROM v_partnership_detail WHERE is_consecutive = 1 AND runs >= 20",
        db_path=db,
    )
    assert pairs  # Q13/Q24 views work on real scorecard data


def test_scorecard_for_unknown_match_is_rejected(tmp_path):
    db = init_db(tmp_path / "x.db")
    payload = json.loads((FX / "scorecard_v2_sample.json").read_text())
    with transaction(db) as conn:
        with pytest.raises(parsers.ParseError):
            load_scorecard(conn, payload, 999)
