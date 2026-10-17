"""Reloading from saved responses repairs data without any API call."""

import json
import shutil

from config import BASE_DIR
from data.reload_cache import reload_cache
from database import repositories as repo
from database.init_db import init_db
from utils.db_connection import fetch_all, transaction

FX = BASE_DIR / "tests" / "fixtures"


def test_reload_repairs_a_corrupted_strike_rate_and_a_wrong_highest_score(tmp_path):
    db = init_db(tmp_path / "r.db")
    raw = tmp_path / "raw"
    raw.mkdir()
    shutil.copy(
        FX / "players_get-batting_8733.json", raw / "stats_v1_player_batting_8733.json"
    )
    payload = {
        "filter": {"selectedMatchType": "test"},
        "headers": ["Batter", "HS", "Balls", "SR", "Vs"],
        "values": [{"values": ["8733", "KL Rahul", "199", "300", "66.0", "ENG"]}],
    }
    (raw / "stats_v1_topstats_0_1_highestScore.json").write_text(json.dumps(payload))
    with transaction(db) as conn:  # the damage the old loader did
        repo.ensure_player(conn, 8733, "KL Rahul")
        repo.upsert_career_stats(
            conn,
            {
                "player_id": 8733,
                "format": "T20",
                "strike_rate": 50.0,
                "highest_score": 20,
            },
        )
    counts = reload_cache(db, raw)
    assert counts["leaderboards"] == 1 and counts["career_tables"] == 1
    row = fetch_all(
        "SELECT * FROM player_career_stats WHERE player_id = 8733 AND format = 'T20'",
        db_path=db,
    )[0]
    assert row["strike_rate"] == 139.13 and row["highest_score"] == 110
    test_row = fetch_all(
        "SELECT highest_score FROM player_career_stats WHERE format = 'TEST'",
        db_path=db,
    )[0]
    assert test_row["highest_score"] == 199


def test_reload_with_an_empty_cache_does_nothing(tmp_path):
    db = init_db(tmp_path / "e.db")
    assert reload_cache(db, tmp_path / "missing") == {
        "leaderboards": 0, "career_tables": 0, "skipped": 0,
    }  # fmt: skip
