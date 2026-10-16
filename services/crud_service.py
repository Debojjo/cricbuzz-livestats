"""Create / Read / Update / Delete for players and batting performances.

Rules (all explained in the README):

* Create always works and flags the new row ``is_sample = 1`` ("not from the API").
* Read sees everything.
* Update and Delete only touch rows flagged ``is_sample = 1``. Real API rows are
  protected unless ``CRUD_ALLOW_EDIT_REAL`` is switched on.
* A player with match history cannot be deleted (the message says why).
* Every write runs inside one transaction: it fully succeeds or leaves no trace.
* Values always travel as ``?`` parameters, never inside the SQL text.
"""

import sqlite3
from pathlib import Path
from typing import Optional

import config
from utils.db_connection import fetch_all, transaction
from utils.validators import (
    BATTING_EDITABLE,
    PLAYER_FIELDS,
    ValidationError,
    validate_batting,
    validate_player,
)


class CrudError(RuntimeError):
    """A readable problem for the user: not found, protected, in use, duplicate."""


# ---------------------------------------------------------------- helpers ----
def _like(term: str) -> str:
    """Escape % and _ so a search for '50%' means literally that."""
    escaped = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _one(sql: str, params: tuple, db_path) -> Optional[dict]:
    rows = fetch_all(sql, params, db_path=db_path)
    return rows[0] if rows else None


def _check_editable(row: dict, label: str) -> None:
    if row["is_sample"] == 0 and not config.CRUD_ALLOW_EDIT_REAL:
        raise CrudError(
            f"{label} comes from the Cricbuzz API and is protected. "
            "Create a new entry, or edit a manually created / sample row."
        )


def _source(row: dict) -> dict:
    row["source"] = "manual/sample" if row["is_sample"] else "API"
    return row


# ---------------------------------------------------------------- players ----
def create_player(data: dict, db_path: Optional[Path] = None) -> int:
    """Validate and insert a player; returns the new player_id."""
    clean = validate_player(data)
    with transaction(db_path) as conn:
        row = conn.execute(
            "SELECT COALESCE(MAX(player_id), ?) FROM players WHERE player_id >= ?",
            (config.MANUAL_ID_START - 1, config.MANUAL_ID_START),
        ).fetchone()
        player_id = row[0] + 1
        clean["player_id"] = player_id
        clean["is_sample"] = 1
        cols = list(clean)
        conn.execute(
            f"INSERT INTO players ({', '.join(cols)}) "
            f"VALUES ({', '.join('?' for _ in cols)})",
            [clean[c] for c in cols],
        )
    return player_id


def get_player(player_id: int, db_path: Optional[Path] = None) -> Optional[dict]:
    """One player, or None."""
    row = _one("SELECT * FROM players WHERE player_id = ?", (player_id,), db_path)
    return _source(row) if row else None


def list_players(
    search: Optional[str] = None,
    country: Optional[str] = None,
    role: Optional[str] = None,
    source: str = "all",
    limit: int = 25,
    offset: int = 0,
    db_path: Optional[Path] = None,
) -> dict:
    """A page of players plus the total match count.

    source: 'all', 'api' (real) or 'manual' (manual + sample rows).
    """
    where, params = [], []
    if search:
        where.append(
            "(full_name LIKE ? ESCAPE '\\' OR display_name LIKE ? ESCAPE '\\')"
        )
        params += [_like(search), _like(search)]
    if country:
        where.append("country = ?")
        params.append(country)
    if role:
        where.append("playing_role = ?")
        params.append(role)
    if source == "api":
        where.append("is_sample = 0")
    elif source == "manual":
        where.append("is_sample = 1")
    clause = f"WHERE {' AND '.join(where)}" if where else ""
    limit = max(1, min(int(limit), 500))
    offset = max(0, int(offset))
    total = fetch_all(
        f"SELECT COUNT(*) AS n FROM players {clause}", tuple(params), db_path=db_path
    )[0]["n"]
    rows = fetch_all(
        f"SELECT * FROM players {clause} ORDER BY full_name LIMIT ? OFFSET ?",
        tuple(params) + (limit, offset),
        db_path=db_path,
    )
    return {"rows": [_source(r) for r in rows], "total": total}


def update_player(
    player_id: int, changes: dict, db_path: Optional[Path] = None
) -> dict:
    """Change some fields of a player; returns the updated row."""
    clean = validate_player(changes, partial=True)
    if not clean:
        raise ValidationError({"changes": "nothing to update"})
    current = get_player(player_id, db_path)
    if current is None:
        raise CrudError(f"Player {player_id} does not exist.")
    _check_editable(current, f"Player {current['full_name']}")
    assignments = ", ".join(f"{c} = ?" for c in clean)
    with transaction(db_path) as conn:
        conn.execute(
            f"UPDATE players SET {assignments} WHERE player_id = ?",
            [*clean.values(), player_id],
        )
    return get_player(player_id, db_path)


def delete_player(player_id: int, db_path: Optional[Path] = None) -> None:
    """Delete a manual/sample player who has no match history."""
    current = get_player(player_id, db_path)
    if current is None:
        raise CrudError(f"Player {player_id} does not exist.")
    _check_editable(current, f"Player {current['full_name']}")
    history = _one(
        """
        SELECT
          (SELECT COUNT(*) FROM batting_performances WHERE player_id = ?) AS batting,
          (SELECT COUNT(*) FROM bowling_performances WHERE player_id = ?) AS bowling,
          (SELECT COUNT(*) FROM fielding_performances WHERE player_id = ?) AS fielding,
          (SELECT COUNT(*) FROM partnerships
             WHERE bat1_id = ? OR bat2_id = ?) AS partnerships
        """,
        (player_id,) * 5,
        db_path,
    )
    used = {k: v for k, v in history.items() if v}
    if used:
        detail = ", ".join(f"{v} {k}" for k, v in used.items())
        raise CrudError(
            f"Cannot delete {current['full_name']}: the player appears in {detail} "
            "record(s). Delete those records first."
        )
    with transaction(db_path) as conn:
        conn.execute(
            "DELETE FROM player_career_stats WHERE player_id = ?", (player_id,)
        )
        conn.execute("DELETE FROM players WHERE player_id = ?", (player_id,))


# ------------------------------------------------------ batting performances ----
def _strike_rate(runs: int, balls: Optional[int]) -> Optional[float]:
    return round(runs * 100 / balls, 2) if balls else None


def _insert_batting(conn: sqlite3.Connection, clean: dict) -> int:
    match = conn.execute(
        "SELECT team1_id, team2_id FROM matches WHERE match_id = ?",
        (clean["match_id"],),
    ).fetchone()
    if match is None:
        raise CrudError(f"Match {clean['match_id']} does not exist.")
    if (
        conn.execute(
            "SELECT 1 FROM players WHERE player_id = ?", (clean["player_id"],)
        ).fetchone()
        is None
    ):
        raise CrudError(f"Player {clean['player_id']} does not exist.")
    if clean["team_id"] not in (match["team1_id"], match["team2_id"]):
        raise CrudError("That team did not play in this match.")
    row = dict(clean)
    row["strike_rate"] = _strike_rate(row["runs"], row.get("balls_faced"))
    row["fours"] = row.get("fours") or 0
    row["sixes"] = row.get("sixes") or 0
    if row["is_not_out"] and not row.get("out_desc"):
        row["out_desc"] = "not out"
    row["is_sample"] = 1
    cols = list(row)
    try:
        cursor = conn.execute(
            f"INSERT INTO batting_performances ({', '.join(cols)}) "
            f"VALUES ({', '.join('?' for _ in cols)})",
            [row[c] for c in cols],
        )
    except sqlite3.IntegrityError as exc:
        if "UNIQUE" in str(exc):
            raise CrudError(
                "That player already has a batting entry for this match and innings."
            ) from exc
        raise CrudError(f"The database rejected this entry: {exc}") from exc
    return cursor.lastrowid


def create_batting(data: dict, db_path: Optional[Path] = None) -> int:
    """Validate and add one batting entry; returns its performance_id."""
    clean = validate_batting(data)
    with transaction(db_path) as conn:
        return _insert_batting(conn, clean)


def create_batting_rows(rows: list, db_path: Optional[Path] = None) -> list:
    """Add several entries as ONE unit: if any row is bad, none are saved."""
    cleaned = [validate_batting(row) for row in rows]
    with transaction(db_path) as conn:
        return [_insert_batting(conn, clean) for clean in cleaned]


def get_batting(performance_id: int, db_path: Optional[Path] = None) -> Optional[dict]:
    """One batting entry (with player and match details), or None."""
    row = _one(
        "SELECT * FROM v_batting_detail WHERE performance_id = ?",
        (performance_id,),
        db_path,
    )
    return _source(row) if row else None


def list_batting(
    match_id: Optional[int] = None,
    player_id: Optional[int] = None,
    limit: int = 25,
    offset: int = 0,
    db_path: Optional[Path] = None,
) -> dict:
    """A page of batting entries, newest matches first."""
    where, params = [], []
    if match_id is not None:
        where.append("match_id = ?")
        params.append(int(match_id))
    if player_id is not None:
        where.append("player_id = ?")
        params.append(int(player_id))
    clause = f"WHERE {' AND '.join(where)}" if where else ""
    limit = max(1, min(int(limit), 500))
    offset = max(0, int(offset))
    total = fetch_all(
        f"SELECT COUNT(*) AS n FROM v_batting_detail {clause}",
        tuple(params),
        db_path=db_path,
    )[0]["n"]
    rows = fetch_all(
        f"SELECT * FROM v_batting_detail {clause} "
        "ORDER BY match_date DESC, match_id, innings_no, batting_position "
        "LIMIT ? OFFSET ?",
        tuple(params) + (limit, offset),
        db_path=db_path,
    )
    return {"rows": [_source(r) for r in rows], "total": total}


def update_batting(
    performance_id: int, changes: dict, db_path: Optional[Path] = None
) -> dict:
    """Change runs, balls, boundaries, position or dismissal of one entry."""
    not_editable = set(changes) - set(BATTING_EDITABLE)
    if not_editable:
        raise ValidationError(
            {
                k: "cannot be changed (delete the entry and create a new one)"
                for k in not_editable
            }
        )
    current = get_batting(performance_id, db_path)
    if current is None:
        raise CrudError(f"Batting entry {performance_id} does not exist.")
    _check_editable(current, "This batting entry")
    merged = {
        k: current[k]
        for k in (
            "match_id", "innings_no", "player_id", "team_id", "batting_position",
            "runs", "balls_faced", "fours", "sixes", "is_not_out", "out_desc",
        )  # fmt: skip
    }
    merged.update(changes)
    clean = validate_batting(merged)  # re-check the combined values together
    update = {k: clean[k] for k in BATTING_EDITABLE}
    update["strike_rate"] = _strike_rate(clean["runs"], clean.get("balls_faced"))
    assignments = ", ".join(f"{c} = ?" for c in update)
    with transaction(db_path) as conn:
        conn.execute(
            f"UPDATE batting_performances SET {assignments} WHERE performance_id = ?",
            [*update.values(), performance_id],
        )
    return get_batting(performance_id, db_path)


def delete_batting(performance_id: int, db_path: Optional[Path] = None) -> None:
    """Delete one manual/sample batting entry."""
    current = get_batting(performance_id, db_path)
    if current is None:
        raise CrudError(f"Batting entry {performance_id} does not exist.")
    _check_editable(current, "This batting entry")
    with transaction(db_path) as conn:
        conn.execute(
            "DELETE FROM batting_performances WHERE performance_id = ?",
            (performance_id,),
        )


__all__ = [
    "CrudError",
    "ValidationError",
    "PLAYER_FIELDS",
    "create_player",
    "get_player",
    "list_players",
    "update_player",
    "delete_player",
    "create_batting",
    "create_batting_rows",
    "get_batting",
    "list_batting",
    "update_batting",
    "delete_batting",
]
