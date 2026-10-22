"""First-start setup and snapshot tests."""

import sqlite3

import pytest
from streamlit.testing.v1 import AppTest

import config
from config import BASE_DIR
from data.make_snapshot import make_snapshot
from database import repositories as repo
from database.init_db import init_db
from utils import bootstrap
from utils.db_connection import transaction


def table_count(path, table):
    conn = sqlite3.connect(path)
    try:
        return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    finally:
        conn.close()


def test_an_existing_database_is_left_alone(tmp_path):
    db = init_db(tmp_path / "keep.db")
    assert bootstrap.ensure_database(db, tmp_path / "none.db") == "existing"


def test_snapshot_is_copied_when_there_is_no_database(tmp_path):
    source = init_db(tmp_path / "source.db")
    with transaction(source) as conn:
        repo.upsert_team(conn, {"team_id": 2, "team_name": "India"})
    snapshot = make_snapshot(source, tmp_path / "snap" / "snapshot.db")
    target = tmp_path / "fresh" / "app.db"
    assert bootstrap.ensure_database(target, snapshot) == "snapshot"
    assert table_count(target, "teams") == 1


def test_demo_database_is_built_from_saved_samples_as_a_last_resort(tmp_path):
    target = tmp_path / "demo.db"
    assert (
        bootstrap.ensure_database(target, tmp_path / "missing.db", sample_matches=40)
        == "built"
    )
    assert table_count(target, "matches") == 41  # 1 real fixture match + 40 sample
    assert table_count(target, "players") > 100
    conn = sqlite3.connect(target)
    try:
        india = conn.execute(
            "SELECT COUNT(*) FROM players WHERE country = 'India'"
        ).fetchone()[0]
    finally:
        conn.close()
    assert india >= 37  # the saved India squad


def test_snapshot_is_a_clean_complete_copy(tmp_path):
    source = init_db(tmp_path / "s.db")
    with transaction(source) as conn:
        repo.upsert_team(conn, {"team_id": 1, "team_name": "A"})
    out = make_snapshot(source, tmp_path / "out.db")
    assert table_count(out, "teams") == 1
    with pytest.raises(FileNotFoundError):
        make_snapshot(tmp_path / "nothing.db", tmp_path / "x.db")


def test_a_page_prepares_the_database_on_first_start_when_enabled(
    tmp_path, monkeypatch
):
    source = init_db(tmp_path / "source.db")
    with transaction(source) as conn:
        repo.upsert_team(conn, {"team_id": 2, "team_name": "India"})
    snapshot = make_snapshot(source, tmp_path / "snapshot.db")
    target = tmp_path / "hosted" / "app.db"
    monkeypatch.setattr(config, "DB_PATH", target)
    monkeypatch.setattr(config, "AUTO_SETUP", True)
    monkeypatch.setattr(bootstrap, "SNAPSHOT_PATH", snapshot)
    at = AppTest.from_file(
        str(BASE_DIR / "pages/5_Settings.py"), default_timeout=60
    ).run()
    assert not at.exception and target.exists()


def test_without_the_switch_a_missing_database_is_explained_not_built(
    tmp_path, monkeypatch
):
    target = tmp_path / "x" / "app.db"
    monkeypatch.setattr(config, "DB_PATH", target)
    monkeypatch.setattr(config, "AUTO_SETUP", False)
    at = AppTest.from_file(
        str(BASE_DIR / "pages/5_Settings.py"), default_timeout=60
    ).run()
    assert not target.exists() and any("not found" in e.value for e in at.error)
