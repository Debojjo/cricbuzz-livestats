"""Enrichment tests: manual venues and series details derived from names."""

import pytest

from data import enrich
from database import repositories as repo
from database.init_db import init_db
from utils.db_connection import fetch_all, transaction


@pytest.mark.parametrize(
    "name, host",
    [
        ("West Indies tour of India, 2026", "India"),
        ("Australia tour of South Africa, 2026", "South Africa"),
        ("Hong Kong, China tour of Japan 2026", "Japan"),
        ("Afghanistan vs Bangladesh in UAE, 2026", "UAE"),
        ("Quadrangular T20I Series in Nigeria, 2026", "Nigeria"),
        ("Asian Games 2026", None),
        ("ICC Men's T20 World Cup Asia Sub Regional Qualifier A 2026", None),
    ],
)
def test_host_country_only_when_the_name_says_so(name, host):
    assert enrich.host_country_from_name(name) == host


@pytest.mark.parametrize(
    "name, kind",
    [
        ("ICC Men's T20 World Cup 2026", "T20"),
        ("Border-Gavaskar Test Series", "Test"),
        ("Asia Cup ODI 2026", "ODI"),
        ("Asian Games 2026", None),
    ],
)
def test_match_type_from_name(name, kind):
    assert enrich.match_type_from_name(name) == kind


def test_manual_venues_load_and_include_big_stadiums(tmp_path):
    db = init_db(tmp_path / "e.db")
    with transaction(db) as conn:
        assert enrich.load_venues_extra(conn) == 8
        enrich.load_venues_extra(conn)  # repeating must not duplicate
    rows = fetch_all(
        "SELECT * FROM venues WHERE capacity > 50000 ORDER BY capacity DESC", db_path=db
    )
    assert [r["city"] for r in rows][:2] == ["Ahmedabad", "Melbourne"]
    assert len(rows) == 6
    assert all(r["is_sample"] == 1 for r in rows)  # flagged as not-from-the-API


def test_enrich_series_fills_only_empty_fields(tmp_path):
    db = init_db(tmp_path / "s.db")
    with transaction(db) as conn:
        repo.upsert_series(
            conn, {"series_id": 1, "series_name": "Sri Lanka tour of Pakistan, 2024"}
        )
        repo.upsert_series(
            conn,
            {
                "series_id": 2,
                "series_name": "Asian Games 2024",
                "host_country": "China",
            },
        )
        filled = enrich.enrich_series(conn)
    assert filled["host_country"] == 1
    rows = {r["series_id"]: r for r in fetch_all("SELECT * FROM series", db_path=db)}
    assert rows[1]["host_country"] == "Pakistan"
    assert rows[2]["host_country"] == "China"  # existing value untouched
    assert rows[1]["match_type"] is None  # nothing in the name -> not guessed
