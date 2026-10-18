"""Logic behind the SQL Analytics page: list, run and explain queries safely."""

import re
import sqlite3
import time
from pathlib import Path
from typing import Optional

import pandas as pd

from services import query_runner
from utils.db_connection import get_connection

_HEADER = re.compile(
    r"^--\s*Q(?P<label>\d+[a-z]?)\s*\((?P<level>[^)]*)\)\s*:\s*(?P<title>.+?)\s*$"
)
MAX_CUSTOM_ROWS = 1000
CUSTOM_TIMEOUT_SECONDS = 5


def list_queries() -> list:
    """Every numbered query: [{'label', 'level', 'title', 'name'}], in order."""
    items = []
    for path in sorted(query_runner.QUERY_DIR.glob("q*.sql")):
        first = path.read_text(encoding="utf-8").splitlines()[0]
        match = _HEADER.match(first)
        label = str(query_runner.label_of(path))
        items.append(
            {
                "label": label,
                "level": match["level"].split(",")[0] if match else "",
                "title": match["title"] if match else path.stem,
                "name": path.name,
            }
        )
    return items


def describe(label) -> str:
    """The comment block at the top of a query file, as plain text."""
    lines = []
    for line in query_runner.read_sql(query_runner.find_query_file(label)).splitlines():
        if not line.startswith("--"):
            break
        lines.append(line[2:].strip())
    return "\n".join(lines)


def get_sql(label) -> str:
    """The SQL text of a query."""
    return query_runner.read_sql(query_runner.find_query_file(label))


def run_numbered(label, include_sample: bool = True, db_path: Optional[Path] = None):
    """Run a stored query. Returns {'df': DataFrame, 'seconds': float}."""
    sql = get_sql(label)
    started = time.perf_counter()
    conn = get_connection(db_path, read_only=True, include_sample=include_sample)
    try:
        cursor = conn.execute(sql)
        columns = [c[0] for c in cursor.description]
        rows = [tuple(r) for r in cursor.fetchall()]
    finally:
        conn.close()
    return {
        "df": pd.DataFrame.from_records(rows, columns=columns),
        "seconds": time.perf_counter() - started,
    }


def explain_numbered(
    label, include_sample: bool = True, db_path: Optional[Path] = None
):
    """SQLite's plan for a stored query, one line per step."""
    sql = re.sub(r"--[^\n]*", "", get_sql(label))
    conn = get_connection(db_path, read_only=True, include_sample=include_sample)
    try:
        return [row[3] for row in conn.execute("EXPLAIN QUERY PLAN " + sql)]
    finally:
        conn.close()


def validate_select(sql: str) -> str:
    """Return the cleaned query, or raise ValueError with a readable reason.

    Only one SELECT (or WITH ... SELECT) statement is accepted. This is the first of
    two locks: the connection is also read-only, so even a cleverly written
    statement cannot change data.
    """
    text = re.sub(r"/\*.*?\*/", " ", sql or "", flags=re.S)
    text = re.sub(r"--[^\n]*", " ", text).strip().rstrip(";").strip()
    if not text:
        raise ValueError("Type a query first.")
    if ";" in text:
        raise ValueError("Only one statement at a time (remove the ';' in the middle).")
    if text.split(None, 1)[0].lower() not in ("select", "with"):
        raise ValueError("Only SELECT queries are allowed here.")
    return text


def run_custom(
    sql: str,
    include_sample: bool = True,
    max_rows: int = MAX_CUSTOM_ROWS,
    timeout: float = CUSTOM_TIMEOUT_SECONDS,
    db_path: Optional[Path] = None,
) -> dict:
    """Run a user-typed SELECT: read-only, row-limited and time-limited."""
    text = validate_select(sql)
    started = time.perf_counter()
    deadline = started + timeout
    conn = get_connection(db_path, read_only=True, include_sample=include_sample)
    conn.set_progress_handler(
        lambda: 1 if time.perf_counter() > deadline else 0, 10_000
    )
    try:
        cursor = conn.execute(text)
        if cursor.description is None:
            raise ValueError("That statement returns no table.")
        columns = [c[0] for c in cursor.description]
        rows = [tuple(r) for r in cursor.fetchmany(max_rows + 1)]
    except sqlite3.OperationalError as exc:
        if "interrupted" in str(exc):
            raise ValueError(f"Stopped: the query ran longer than {timeout:g} seconds.")
        raise ValueError(f"SQL error: {exc}") from exc
    except sqlite3.Error as exc:
        raise ValueError(f"SQL error: {exc}") from exc
    finally:
        conn.close()
    truncated = len(rows) > max_rows
    return {
        "df": pd.DataFrame.from_records(rows[:max_rows], columns=columns),
        "truncated": truncated,
        "seconds": time.perf_counter() - started,
    }


def schema_overview(db_path: Optional[Path] = None) -> dict:
    """{table or view: [column names]} to help people write their own queries."""
    conn = get_connection(db_path, read_only=True)
    try:
        names = conn.execute(
            "SELECT name FROM sqlite_master WHERE type IN ('table', 'view') "
            "AND name NOT LIKE 'sqlite_%' ORDER BY type, name"
        ).fetchall()
        return {
            n[0]: [c[1] for c in conn.execute(f"PRAGMA table_info({n[0]})")]
            for n in names
        }
    finally:
        conn.close()
