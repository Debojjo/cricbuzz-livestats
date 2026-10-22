"""First-start setup for hosts that begin without a database file.

Locally you build the database with the commands in the README. A hosted app
(Streamlit Community Cloud) starts from a fresh copy of the repository instead, so
with ``AUTO_SETUP=1`` the app calls ``ensure_database()`` on its first start:

1. database file already there  -> nothing to do;
2. a committed snapshot exists   -> copy it (your real, loaded data);
3. neither                       -> build a small demo from the saved sample files
                                    plus clearly flagged fictional history.
"""

import json
import shutil
from pathlib import Path
from typing import Optional

import config
from utils.logger import get_logger

logger = get_logger(__name__)
SNAPSHOT_PATH = config.BASE_DIR / "data" / "snapshot" / "cricbuzz_snapshot.db"
FIXTURE_DIR = config.BASE_DIR / "tests" / "fixtures"


def ensure_database(
    db_path: Optional[Path] = None,
    snapshot: Optional[Path] = None,
    sample_matches: int = 700,
) -> str:
    """Make sure a usable database exists. Returns 'existing', 'snapshot' or 'built'."""
    path = Path(db_path) if db_path else config.DB_PATH
    snapshot = Path(snapshot) if snapshot else SNAPSHOT_PATH
    if path.exists():
        return "existing"

    path.parent.mkdir(parents=True, exist_ok=True)
    if snapshot.exists():
        shutil.copyfile(snapshot, path)
        logger.info("Database copied from snapshot %s", snapshot.name)
        return "snapshot"

    # Imported here: they pull in the whole data layer, which is not needed otherwise.
    from data import enrich, ingest, seed_sample_data
    from database.init_db import init_db
    from utils.db_connection import transaction

    init_db(path)
    ingest.load_fixtures(path)
    squad = FIXTURE_DIR / "teams_v1_players_2.json"
    with transaction(path) as conn:
        if squad.exists():
            ingest.load_team_players(
                conn, json.loads(squad.read_text("utf-8")), "India"
            )
        seed_sample_data.generate(conn, matches=sample_matches)
        enrich.load_venues_extra(conn)
        enrich.enrich_series(conn)
        enrich.normalize_player_styles(conn)
    logger.info("Demo database built from saved samples")
    return "built"
