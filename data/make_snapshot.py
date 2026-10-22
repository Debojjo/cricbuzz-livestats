"""Save a compact copy of your database for deployment.

    python -m data.make_snapshot

Writes data/snapshot/cricbuzz_snapshot.db (a clean, vacuumed copy) that you commit
to Git. A hosted app then starts with all the real data you loaded, without needing
your API key or the raw response cache.
"""

import sqlite3
from pathlib import Path
from typing import Optional

import config
from utils.bootstrap import SNAPSHOT_PATH


def make_snapshot(db_path: Optional[Path] = None, out: Optional[Path] = None) -> Path:
    """Copy the database safely (SQLite backup API), then compact it."""
    source = Path(db_path) if db_path else config.DB_PATH
    target = Path(out) if out else SNAPSHOT_PATH
    if not source.exists():
        raise FileNotFoundError(f"database not found: {source}")
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        target.unlink()
    src = sqlite3.connect(source)
    dst = sqlite3.connect(target)
    try:
        src.backup(dst)
        dst.execute("VACUUM")
    finally:
        dst.close()
        src.close()
    return target


def main() -> None:
    """Command-line entry point."""
    target = make_snapshot()
    megabytes = target.stat().st_size / 1_000_000
    print(f"\nSnapshot written: {target}  ({megabytes:.1f} MB)")
    print(
        "GitHub accepts files up to 100 MB; this one is "
        + ("fine." if megabytes < 90 else "TOO BIG.")
    )
    print(
        "Next:  git add data/snapshot  &&  git commit -m 'data: add database snapshot'"
    )


if __name__ == "__main__":
    main()
