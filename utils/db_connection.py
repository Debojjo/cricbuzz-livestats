"""The single place where database connections are created.

Every other module asks this file for a connection. That keeps three things
in one spot: foreign-key enforcement, row format, and the choice of database
(swapping SQLite for PostgreSQL later means changing this file and
``database/schema.sql`` only).
"""

import math
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Optional, Sequence

import config


def _sqrt(value):
    """SQL SQRT(): NULL in, NULL out; tiny negative rounding noise becomes 0."""
    if value is None:
        return None
    return math.sqrt(max(float(value), 0.0))


def get_connection(
    db_path: Optional[Path] = None, read_only: bool = False
) -> sqlite3.Connection:
    """Open a connection with the project's standard settings.

    * ``PRAGMA foreign_keys = ON`` - SQLite ignores foreign keys unless this is
      set on *every* connection, so we set it here and nowhere else.
    * ``row_factory = sqlite3.Row`` - rows behave like dicts (row["name"]).
    * ``read_only=True`` - the file is opened in read-only mode. Used by the
      custom SQL box so a typed ``DROP TABLE`` cannot do any damage.
    """
    path = Path(db_path) if db_path else config.DB_PATH

    if read_only:
        uri = f"{path.resolve().as_uri()}?mode=ro"
        conn = sqlite3.connect(uri, uri=True, timeout=10)
        conn.execute("PRAGMA query_only = ON")
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(path, timeout=10)

    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    # Not every SQLite build has SQRT; defining it here makes the standard-deviation
    # queries (Q19, Q23) behave the same on every machine.
    conn.create_function("SQRT", 1, _sqrt, deterministic=True)
    return conn


@contextmanager
def transaction(db_path: Optional[Path] = None) -> Iterator[sqlite3.Connection]:
    """Run a block of writes as one unit: all of it commits, or none of it does.

    Usage::

        with transaction() as conn:
            conn.execute("INSERT ...", params)
            conn.execute("UPDATE ...", params)
    """
    conn = get_connection(db_path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def fetch_all(
    sql: str,
    params: Sequence[Any] = (),
    db_path: Optional[Path] = None,
    read_only: bool = True,
) -> list[dict]:
    """Run a SELECT and return the rows as a list of plain dicts."""
    conn = get_connection(db_path, read_only=read_only)
    try:
        return [dict(row) for row in conn.execute(sql, params).fetchall()]
    finally:
        conn.close()
