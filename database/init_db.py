"""Create (or reset) the database from schema.sql and views.sql.

Run from the project root::

    python -m database.init_db            # create anything that is missing
    python -m database.init_db --reset    # delete the file and rebuild it
"""

import argparse
from pathlib import Path
from typing import Optional

import config
from utils.db_connection import get_connection
from utils.logger import get_logger

logger = get_logger(__name__)


def init_db(db_path: Optional[Path] = None, reset: bool = False) -> Path:
    """Build the database and return its path.

    Safe to run repeatedly: tables and indexes use ``IF NOT EXISTS`` and the
    views are dropped and recreated.
    """
    path = Path(db_path) if db_path else config.DB_PATH

    if reset and path.exists():
        path.unlink()
        logger.info("Deleted existing database: %s", path)

    schema_sql = config.SCHEMA_FILE.read_text(encoding="utf-8")
    views_sql = config.VIEWS_FILE.read_text(encoding="utf-8")

    conn = get_connection(path)
    try:
        conn.executescript(schema_sql)
        conn.executescript(views_sql)
        conn.commit()
    finally:
        conn.close()

    logger.info("Database ready: %s", path)
    return path


def describe_db(db_path: Optional[Path] = None) -> dict:
    """Return the names of the tables, views and indexes that exist."""
    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            "SELECT type, name FROM sqlite_master "
            "WHERE name NOT LIKE 'sqlite_%' ORDER BY type, name"
        ).fetchall()
    finally:
        conn.close()
    result: dict = {"table": [], "view": [], "index": []}
    for row in rows:
        result[row["type"]].append(row["name"])
    return result


def main() -> None:
    """Command-line entry point."""
    parser = argparse.ArgumentParser(description="Initialise the database.")
    parser.add_argument("--reset", action="store_true", help="delete and rebuild")
    parser.add_argument("--db", type=Path, default=None, help="alternative path")
    args = parser.parse_args()

    path = init_db(args.db, reset=args.reset)
    summary = describe_db(path)
    print(f"\nDatabase: {path}")
    print(f"Tables  ({len(summary['table'])}): {', '.join(summary['table'])}")
    print(f"Views   ({len(summary['view'])}): {', '.join(summary['view'])}")
    print(f"Indexes ({len(summary['index'])})")


if __name__ == "__main__":
    main()
