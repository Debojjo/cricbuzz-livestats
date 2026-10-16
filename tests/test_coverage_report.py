"""The coverage report must run on any database, even an empty one."""

from data import coverage_report
from database.init_db import init_db


def test_report_runs_on_an_empty_database(tmp_path):
    rows = coverage_report.coverage(init_db(tmp_path / "empty.db"))
    assert len(rows) == 25
    assert [r[0] for r in rows] == [f"Q{i}" for i in range(1, 26)]
    assert all(r[4].strip() == "SEED" for r in rows)


def test_status_labels():
    assert coverage_report.status(10, 10) == "OK  "
    assert coverage_report.status(3, 10) == "THIN"
    assert coverage_report.status(0, 10) == "SEED"
