"""CRUD tests: validation, protection rules, transactions and injection safety."""

import pytest

import config
from database import repositories as repo
from database.init_db import init_db
from services import crud_service as crud
from utils.db_connection import fetch_all, transaction
from utils.validators import ValidationError, validate_batting, validate_player


@pytest.fixture()
def db(tmp_path):
    path = init_db(tmp_path / "crud.db")
    with transaction(path) as conn:
        repo.upsert_team(
            conn, {"team_id": 2, "team_name": "India", "short_name": "IND"}
        )
        repo.upsert_team(
            conn, {"team_id": 10, "team_name": "West Indies", "short_name": "WI"}
        )
        repo.upsert_team(
            conn, {"team_id": 3, "team_name": "Pakistan", "short_name": "PAK"}
        )
        repo.upsert_match(
            conn,
            {"match_id": 100, "format": "T20", "match_date": "2026-10-09",
             "team1_id": 2, "team2_id": 10, "state": "Complete"},
        )  # fmt: skip
        repo.upsert_player(
            conn,
            {"player_id": 1413, "full_name": "Virat Kohli", "country": "India",
             "playing_role": "Batsman"},
        )  # fmt: skip
        conn.execute(
            "INSERT INTO batting_performances "
            "(match_id, innings_no, player_id, team_id, runs, balls_faced, is_sample) "
            "VALUES (100, 1, 1413, 2, 70, 40, 0)"
        )
    return path


def count(db, table):
    return fetch_all(f"SELECT COUNT(*) n FROM {table}", db_path=db)[0]["n"]


# --------------------------------------------------------------- validation ----
def test_player_validation_reports_every_problem_at_once():
    with pytest.raises(ValidationError) as caught:
        validate_player(
            {
                "full_name": " ",
                "playing_role": "Astronaut",
                "date_of_birth": "2999-01-01",
            }
        )
    assert set(caught.value.errors) == {"full_name", "playing_role", "date_of_birth"}


def test_player_validation_cleans_and_accepts_dates():
    from datetime import date

    clean = validate_player(
        {"full_name": "  Asha Rao ", "date_of_birth": date(1999, 3, 4), "country": ""}
    )
    assert clean["full_name"] == "Asha Rao"
    assert clean["date_of_birth"] == "1999-03-04"
    assert clean["country"] is None


@pytest.mark.parametrize(
    "bad, field",
    [
        ({"runs": -1}, "runs"),
        ({"runs": 20, "fours": 6}, "runs"),  # 24 runs from fours alone
        ({"runs": 50, "balls_faced": 3, "fours": 2, "sixes": 2}, "balls_faced"),
        ({"runs": 10.5}, "runs"),
        ({"runs": "abc"}, "runs"),
        ({"innings_no": 9}, "innings_no"),
        ({"batting_position": 12}, "batting_position"),
        ({"is_not_out": "maybe"}, "is_not_out"),
        ({"nonsense": 1}, "nonsense"),
    ],
)
def test_batting_validation_rules(bad, field):
    base = {"match_id": 100, "innings_no": 1, "player_id": 1, "team_id": 2, "runs": 10}
    with pytest.raises(ValidationError) as caught:
        validate_batting({**base, **bad})
    assert field in caught.value.errors


# ------------------------------------------------------------------ players ----
def test_create_read_update_delete_a_manual_player(db):
    pid = crud.create_player({"full_name": "Asha Rao", "playing_role": "Batsman"}, db)
    assert pid >= config.MANUAL_ID_START
    row = crud.get_player(pid, db)
    assert row["is_sample"] == 1 and row["source"] == "manual/sample"

    updated = crud.update_player(pid, {"playing_role": "Bowler", "country": ""}, db)
    assert updated["playing_role"] == "Bowler" and updated["country"] is None

    crud.delete_player(pid, db)
    assert crud.get_player(pid, db) is None


def test_ids_are_sequential_and_do_not_collide(db):
    first = crud.create_player({"full_name": "Player One"}, db)
    second = crud.create_player({"full_name": "Player Two"}, db)
    assert second == first + 1


def test_invalid_player_is_not_saved(db):
    before = count(db, "players")
    with pytest.raises(ValidationError):
        crud.create_player({"full_name": "X", "playing_role": "Wizard"}, db)
    assert count(db, "players") == before


def test_real_api_players_are_protected(db):
    with pytest.raises(crud.CrudError, match="protected"):
        crud.update_player(1413, {"country": "Mars"}, db)
    with pytest.raises(crud.CrudError, match="protected"):
        crud.delete_player(1413, db)
    assert crud.get_player(1413, db)["country"] == "India"


def test_protection_can_be_switched_off(db, monkeypatch):
    monkeypatch.setattr(config, "CRUD_ALLOW_EDIT_REAL", True)
    assert crud.update_player(1413, {"country": "Bharat"}, db)["country"] == "Bharat"


def test_player_with_history_cannot_be_deleted(db):
    pid = crud.create_player({"full_name": "Asha Rao"}, db)
    crud.create_batting({"match_id": 100, "innings_no": 1, "player_id": pid,
                         "team_id": 2, "runs": 12, "balls_faced": 9}, db)  # fmt: skip
    with pytest.raises(crud.CrudError, match="1 batting"):
        crud.delete_player(pid, db)
    assert crud.get_player(pid, db) is not None


def test_unknown_player_gives_a_friendly_error(db):
    with pytest.raises(crud.CrudError, match="does not exist"):
        crud.update_player(424242, {"country": "X"}, db)
    with pytest.raises(crud.CrudError, match="does not exist"):
        crud.delete_player(424242, db)


def test_search_filter_and_paging(db):
    for name in ("Asha Rao", "Asha Menon", "Bela Rao"):
        crud.create_player({"full_name": name, "country": "Demoland"}, db)
    assert crud.list_players(search="asha", db_path=db)["total"] == 2
    assert crud.list_players(country="Demoland", db_path=db)["total"] == 3
    assert crud.list_players(source="api", db_path=db)["total"] == 1
    page = crud.list_players(source="manual", limit=2, offset=2, db_path=db)
    assert page["total"] == 3 and len(page["rows"]) == 1


def test_search_treats_wildcards_and_sql_as_plain_text(db):
    assert crud.list_players(search="%", db_path=db)["total"] == 0
    hostile = "'; DROP TABLE players; --"
    assert crud.list_players(search=hostile, db_path=db)["total"] == 0
    assert count(db, "players") == 1  # table still there, data intact


# ------------------------------------------------------------------ batting ----
GOOD = {"match_id": 100, "innings_no": 2, "player_id": 1413, "team_id": 10,
        "runs": 45, "balls_faced": 30, "fours": 4, "sixes": 2}  # fmt: skip


def test_batting_create_computes_strike_rate_and_flags_manual(db):
    pid = crud.create_batting(GOOD, db)
    row = crud.get_batting(pid, db)
    assert row["strike_rate"] == 150.0 and row["is_sample"] == 1
    assert row["player_name"] == "Virat Kohli"


def test_batting_rejects_unknown_match_team_and_duplicates(db):
    with pytest.raises(crud.CrudError, match="Match 999"):
        crud.create_batting({**GOOD, "match_id": 999}, db)
    with pytest.raises(crud.CrudError, match="did not play"):
        crud.create_batting({**GOOD, "team_id": 3}, db)
    crud.create_batting(GOOD, db)
    with pytest.raises(crud.CrudError, match="already has"):
        crud.create_batting(GOOD, db)


def test_batting_update_recomputes_and_rechecks_together(db):
    pid = crud.create_batting(GOOD, db)
    row = crud.update_batting(pid, {"runs": 60, "balls_faced": 40}, db)
    assert row["runs"] == 60 and row["strike_rate"] == 150.0
    with pytest.raises(
        ValidationError
    ):  # 4 fours + 2 sixes = 28, so 20 runs is impossible
        crud.update_batting(pid, {"runs": 20}, db)
    assert crud.get_batting(pid, db)["runs"] == 60  # failed update changed nothing


def test_batting_keys_cannot_be_edited(db):
    pid = crud.create_batting(GOOD, db)
    with pytest.raises(ValidationError, match="cannot be changed"):
        crud.update_batting(pid, {"match_id": 5}, db)


def test_real_batting_rows_are_protected_but_manual_ones_are_not(db):
    real = fetch_all(
        "SELECT performance_id FROM batting_performances WHERE is_sample = 0",
        db_path=db,
    )[0]["performance_id"]
    with pytest.raises(crud.CrudError, match="protected"):
        crud.update_batting(real, {"runs": 1}, db)
    with pytest.raises(crud.CrudError, match="protected"):
        crud.delete_batting(real, db)
    manual = crud.create_batting(GOOD, db)
    crud.delete_batting(manual, db)
    assert crud.get_batting(manual, db) is None


def test_bulk_create_is_all_or_nothing(db):
    before = count(db, "batting_performances")
    rows = [
        {**GOOD, "innings_no": 3},
        {**GOOD, "innings_no": 4},
        {**GOOD, "innings_no": 3},  # duplicate of the first: the whole batch must fail
    ]
    with pytest.raises(crud.CrudError):
        crud.create_batting_rows(rows, db)
    assert count(db, "batting_performances") == before  # nothing half-saved
    assert len(crud.create_batting_rows(rows[:2], db)) == 2


def test_bad_row_in_a_batch_saves_nothing(db):
    before = count(db, "batting_performances")
    with pytest.raises(ValidationError):
        crud.create_batting_rows([GOOD, {**GOOD, "innings_no": 3, "runs": -5}], db)
    assert count(db, "batting_performances") == before


def test_list_batting_filters(db):
    crud.create_batting(GOOD, db)
    assert crud.list_batting(match_id=100, db_path=db)["total"] == 2
    assert crud.list_batting(player_id=1413, db_path=db)["total"] == 2
    assert crud.list_batting(player_id=1, db_path=db)["total"] == 0
