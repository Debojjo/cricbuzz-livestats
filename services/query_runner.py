"""Run one of the numbered analytics queries from ``sql/queries``.

    python -m services.query_runner 1            # run Q1, print the rows
    python -m services.query_runner 1 --plan     # also show how SQLite runs it
    python -m services.query_runner 1 --limit 5  # show only the first 5 rows

Queries run on a READ-ONLY connection, so nothing here can change your data.
"""

import argparse
import re
from pathlib import Path
from typing import Optional

import config
from utils.db_connection import get_connection

QUERY_DIR = config.BASE_DIR / "sql" / "queries"


def find_query_file(number: int) -> Path:
    """sql/queries/q07_*.sql for number 7."""
    matches = sorted(QUERY_DIR.glob(f"q{number:02d}_*.sql"))
    if not matches:
        raise FileNotFoundError(f"no query file for Q{number} in {QUERY_DIR}")
    return matches[0]


def read_sql(path: Path) -> str:
    """The query text without the leading comment block."""
    return path.read_text(encoding="utf-8")


def run_query(number: int, db_path: Optional[Path] = None) -> dict:
    """Execute a query file; returns {'columns': [...], 'rows': [...], 'sql': text}."""
    sql = read_sql(find_query_file(number))
    conn = get_connection(db_path, read_only=True)
    try:
        cursor = conn.execute(sql)
        columns = [c[0] for c in cursor.description]
        rows = [tuple(row) for row in cursor.fetchall()]
    finally:
        conn.close()
    return {"columns": columns, "rows": rows, "sql": sql}


def explain(number: int, db_path: Optional[Path] = None) -> list:
    """SQLite's execution plan for the query, one line per step."""
    sql = re.sub(r"--[^\n]*", "", read_sql(find_query_file(number)))
    conn = get_connection(db_path, read_only=True)
    try:
        return [row[3] for row in conn.execute("EXPLAIN QUERY PLAN " + sql)]
    finally:
        conn.close()


def format_table(columns: list, rows: list, limit: Optional[int] = None) -> str:
    """Plain-text table for the terminal."""
    shown = rows if limit is None else rows[:limit]
    cells = [[("" if v is None else str(v)) for v in row] for row in shown]
    widths = [
        max([len(str(col))] + [len(row[i]) for row in cells])
        for i, col in enumerate(columns)
    ]
    line = " | ".join(str(c).ljust(w) for c, w in zip(columns, widths))
    rule = "-+-".join("-" * w for w in widths)
    body = "\n".join(
        " | ".join(v.ljust(w) for v, w in zip(row, widths)) for row in cells
    )
    return f"{line}\n{rule}\n{body}"


def main() -> None:
    """Command-line entry point."""
    parser = argparse.ArgumentParser(description="Run an analytics query.")
    parser.add_argument("number", type=int, help="question number, 1-25")
    parser.add_argument("--plan", action="store_true", help="show the execution plan")
    parser.add_argument("--limit", type=int, default=None, help="rows to print")
    args = parser.parse_args()

    result = run_query(args.number)
    print(f"\nQ{args.number}: {find_query_file(args.number).name}\n")
    print(format_table(result["columns"], result["rows"], args.limit))
    print(f"\n{len(result['rows'])} row(s)")
    if args.plan:
        print("\nExecution plan:")
        for step in explain(args.number):
            print(f"  {step}")


if __name__ == "__main__":
    main()
