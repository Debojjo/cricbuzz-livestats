"""Smoke and interaction tests: every page is loaded headlessly with Streamlit's
AppTest, against a temporary database, with no API key (so no network use)."""

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

import config
from config import BASE_DIR
from data import ingest, seed_sample_data
from database.init_db import init_db
from utils.db_connection import transaction

PAGES = {
    "home": "main.py",
    "live": "pages/1_Live_Matches.py",
    "players": "pages/2_Top_Players.py",
    "sql": "pages/3_SQL_Analytics.py",
    "crud": "pages/4_CRUD_Operations.py",
    "settings": "pages/5_Settings.py",
}


@pytest.fixture()
def app_db(tmp_path, monkeypatch):
    db = init_db(tmp_path / "app.db")
    ingest.load_fixtures(db)
    with transaction(db) as conn:
        seed_sample_data.generate(conn, matches=80, seed=4)
    monkeypatch.setattr(config, "DB_PATH", db)
    monkeypatch.setattr(config, "RAW_DIR", tmp_path / "raw")
    monkeypatch.setattr(config, "RAPIDAPI_KEY", "")
    return db


def click(at, label):
    """Click the button with this label and re-run the page."""
    next(b for b in at.button if b.label == label).click()
    at.run()


def open_page(name):
    return AppTest.from_file(str(BASE_DIR / PAGES[name]), default_timeout=60).run()


@pytest.mark.parametrize("name", list(PAGES))
def test_every_page_loads_without_errors(app_db, name):
    at = open_page(name)
    assert not at.exception, [e.value for e in at.exception]


def test_every_page_explains_a_missing_database(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "nothing.db")
    for name in ("live", "players", "sql", "crud", "settings"):
        at = open_page(name)
        assert not at.exception
        assert any("database was not found" in e.value for e in at.error)


def test_home_shows_the_hero_kpis_features_and_the_sample_data_notice(app_db):
    at = open_page("home")
    assert not at.exception
    assert any(
        "Cricbuzz LiveStats" in m.value and "hero" in m.value for m in at.markdown
    )
    labels = {m.label for m in at.metric}
    assert {
        "Real matches",
        "Players",
        "Analytics queries",
        "API requests left",
    } <= labels
    assert any("Latest results" in s.value for s in at.subheader)
    assert any("Real vs sample data" in i.value for i in at.info)


def test_live_page_without_a_key_shows_a_friendly_error_not_a_crash(app_db):
    at = open_page("live")
    at.button[0].click().run()
    assert not at.exception
    assert any("RAPIDAPI_KEY" in e.value for e in at.error)


def test_live_page_recent_results_work_offline(app_db):
    at = open_page("live")
    assert not at.exception
    assert any(s.label == "Result" for s in at.selectbox)


def test_players_page_shows_a_podium_for_the_leaders(app_db):
    at = open_page("players")  # default: Most runs, ODI -> the fixture player
    assert not at.exception
    assert any("3,541" in m.value for m in at.metric)


def test_live_results_are_shown_as_cards_with_a_scorecard_button(app_db):
    at = open_page("live")
    cards = [b for b in at.button if b.label == "View scorecard"]
    assert len(cards) >= 1
    cards[-1].click()
    at.run()
    assert not at.exception
    assert at.session_state["recent_pick"] == len(cards) - 1


def test_sql_page_filters_questions_by_level_and_search(app_db):
    at = open_page("sql")
    all_options = list(at.selectbox[0].options)
    assert len(all_options) == 27
    at.radio[0].set_value("Advanced").run()
    advanced = list(at.selectbox[0].options)
    assert 0 < len(advanced) < 27 and all("Advanced" in o for o in advanced)
    at.radio[0].set_value("All").run()
    at.text_input[0].set_value("toss").run()
    assert list(at.selectbox[0].options) == [
        o for o in all_options if "toss" in o.lower()
    ]
    at.text_input[0].set_value("zzzz-no-such-question").run()
    assert not at.exception and any("No question matches" in i.value for i in at.info)


def test_players_page_draws_a_chart_or_explains_why_not(app_db):
    at = open_page("players")
    assert not at.exception
    assert at.selectbox[0].value == "Most runs"
    at.selectbox[1].set_value("Test").run()  # nothing stored for this combination?
    assert not at.exception


def test_sql_page_runs_the_first_question_automatically(app_db):
    at = open_page("sql")
    assert not at.exception
    assert at.selectbox[0].value == "1"
    assert at.metric[0].label == "Rows"
    at.selectbox[0].set_value("7").run()
    assert not at.exception and at.selectbox[0].value == "7"


def test_sql_page_switch_changes_the_row_count(app_db):
    at = open_page("sql")
    at.selectbox[0].set_value("5").run()  # wins per team
    with_sample = int(at.metric[0].value.replace(",", ""))
    at.sidebar.toggle[0].set_value(False).run()
    real_only = int(at.metric[0].value.replace(",", "")) if at.metric else 0
    assert with_sample > real_only


def test_custom_query_box_blocks_writes_and_accepts_selects(app_db):
    at = open_page("sql")
    at.text_area(key="custom_sql").set_value("DROP TABLE players").run()
    at.button(key="run_custom").click().run()
    assert not at.exception
    assert any("Only SELECT" in e.value for e in at.error)
    at.text_area(key="custom_sql").set_value("SELECT COUNT(*) AS n FROM players").run()
    at.button(key="run_custom").click().run()
    assert not at.exception and not at.error


def test_crud_page_adds_a_player_and_rejects_bad_input(app_db):
    from services import crud_service

    at = open_page("crud")
    assert not at.exception
    at.text_input(key="new_player_name").set_value("Page Test Player")
    click(at, "Add player")
    assert not at.exception
    found = crud_service.list_players(search="Page Test Player", db_path=app_db)
    assert found["total"] == 1
    # an empty name is explained field by field, nothing is saved
    before = crud_service.list_players(db_path=app_db)["total"]
    at = open_page("crud")
    click(at, "Add player")
    assert any("Full Name" in e.value for e in at.error)
    assert crud_service.list_players(db_path=app_db)["total"] == before


def test_settings_page_shows_quota_and_limitations(app_db):
    at = open_page("settings")
    assert not at.exception
    assert {m.label for m in at.metric} >= {"Remaining", "Safety reserve"}


def test_pages_folder_holds_only_page_scripts():
    """A stray __init__.py would show up as a page in the sidebar."""
    names = sorted(p.name for p in (BASE_DIR / "pages").glob("*.py"))
    expected = sorted(Path(v).name for k, v in PAGES.items() if k != "home")
    assert names == expected
