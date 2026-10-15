"""Database write helpers: one small function per table.

All writes are *upserts* ("insert, or update if the row already exists"), so
running an import twice never duplicates anything. SQL values always travel as
``?`` parameters. Table and column names come from our own code, and are still
checked against the real schema before being placed into a statement.
"""

import sqlite3
from typing import Optional, Sequence

import config

# table -> columns that identify a row (must match a PRIMARY KEY / UNIQUE rule)
_KEYS = {
    "teams": ("team_id",),
    "players": ("player_id",),
    "venues": ("venue_id",),
    "series": ("series_id",),
    "matches": ("match_id",),
    "batting_performances": ("match_id", "innings_no", "player_id"),
    "bowling_performances": ("match_id", "innings_no", "player_id"),
    "fielding_performances": ("match_id", "player_id"),
    "partnerships": ("match_id", "innings_no", "wicket_no"),
    "player_career_stats": ("player_id", "format"),
}


def _columns(conn: sqlite3.Connection, table: str) -> set:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


def upsert(
    conn: sqlite3.Connection,
    table: str,
    row: dict,
    prefer_existing: Sequence[str] = (),
) -> None:
    """Insert ``row`` or update the existing row with the same key.

    A new NULL never erases a stored value (COALESCE keeps the old one), so a
    sparse response cannot wipe out a richer earlier one. Columns listed in
    ``prefer_existing`` are never changed once they have a value.
    """
    if table not in _KEYS:
        raise ValueError(f"unknown table: {table}")
    known = _columns(conn, table)
    unknown = set(row) - known
    if unknown:
        raise ValueError(f"unknown columns for {table}: {sorted(unknown)}")

    cols = list(row)
    keys = _KEYS[table]
    updates = [c for c in cols if c not in keys]
    sql = (
        f"INSERT INTO {table} ({', '.join(cols)}) "
        f"VALUES ({', '.join('?' for _ in cols)}) "
    )
    if updates:
        sets = []
        for col in updates:
            if col in prefer_existing:
                sets.append(f"{col} = COALESCE({table}.{col}, excluded.{col})")
            else:
                sets.append(f"{col} = COALESCE(excluded.{col}, {table}.{col})")
        sql += f"ON CONFLICT({', '.join(keys)}) DO UPDATE SET {', '.join(sets)}"
    else:
        sql += f"ON CONFLICT({', '.join(keys)}) DO NOTHING"
    conn.execute(sql, [row[c] for c in cols])


def update_row(conn: sqlite3.Connection, table: str, key: dict, changes: dict) -> int:
    """Fill in columns of an existing row; None values are ignored.

    Use this (not upsert) for partial updates such as adding a toss result to a
    stored match: an upsert tries to INSERT first, and an incomplete row would
    fail the NOT NULL rules before the conflict is even noticed.
    Returns the number of rows changed (0 when the row does not exist).
    """
    if table not in _KEYS:
        raise ValueError(f"unknown table: {table}")
    known = _columns(conn, table)
    unknown = (set(key) | set(changes)) - known
    if unknown:
        raise ValueError(f"unknown columns for {table}: {sorted(unknown)}")
    changes = {c: v for c, v in changes.items() if v is not None}
    if not changes:
        return 0
    sets = ", ".join(f"{c} = ?" for c in changes)
    where = " AND ".join(f"{c} = ?" for c in key)
    cursor = conn.execute(
        f"UPDATE {table} SET {sets} WHERE {where}",
        [*changes.values(), *key.values()],
    )
    return cursor.rowcount


def upsert_team(conn: sqlite3.Connection, team: dict) -> None:
    """Teams: keep the first team_type we saw (e.g. 'associate' from teams/list)."""
    upsert(conn, "teams", team, prefer_existing=("team_type",))


def upsert_player(conn: sqlite3.Connection, player: dict) -> None:
    """Full player profile."""
    upsert(conn, "players", player)


def ensure_player(
    conn: sqlite3.Connection, player_id: int, name: Optional[str]
) -> None:
    """Create a minimal player row if none exists (never overwrites a profile)."""
    conn.execute(
        "INSERT OR IGNORE INTO players (player_id, full_name, display_name) "
        "VALUES (?, ?, ?)",
        (player_id, name or f"Player {player_id}", name),
    )


def upsert_venue(conn: sqlite3.Connection, venue: dict) -> None:
    """Venue; blanks never erase known country / capacity."""
    upsert(conn, "venues", venue)


def upsert_series(conn: sqlite3.Connection, series: dict) -> None:
    """Series row."""
    upsert(conn, "series", series)


def upsert_match(conn: sqlite3.Connection, match: dict) -> None:
    """Match header; later responses may fill in toss and result."""
    upsert(conn, "matches", match)


def upsert_career_stats(conn: sqlite3.Connection, stats: dict) -> None:
    """One row per player and format; batting and bowling parts merge."""
    upsert(conn, "player_career_stats", stats)


def save_scorecard(conn: sqlite3.Connection, parsed: dict) -> dict:
    """Write everything parse_scorecard() returned. Returns row counts."""
    for player_id, name in parsed["players"].items():
        ensure_player(conn, player_id, name)
    for row in parsed["batting"]:
        upsert(conn, "batting_performances", row)
    for row in parsed["bowling"]:
        upsert(conn, "bowling_performances", row)
    for row in parsed["fielding"]:
        upsert(conn, "fielding_performances", row)
    for row in parsed["partnerships"]:
        upsert(conn, "partnerships", row)
    return {
        "batting": len(parsed["batting"]),
        "bowling": len(parsed["bowling"]),
        "fielding": len(parsed["fielding"]),
        "partnerships": len(parsed["partnerships"]),
    }


def match_teams(conn: sqlite3.Connection, match_id: int) -> list:
    """The two teams of a stored match, in the shape the parsers expect."""
    rows = conn.execute(
        "SELECT t.team_id, t.team_name, t.short_name FROM matches m "
        "JOIN teams t ON t.team_id IN (m.team1_id, m.team2_id) "
        "WHERE m.match_id = ? ORDER BY t.team_id",
        (match_id,),
    ).fetchall()
    return [dict(row) for row in rows]


# ----------------------------------------------------------- API call log ----
def log_api_call(
    conn: sqlite3.Connection,
    endpoint: str,
    params: str,
    status_code: Optional[int],
    from_cache: bool,
) -> None:
    """Record one request (or cache hit) in api_call_log."""
    conn.execute(
        "INSERT INTO api_call_log (endpoint, params, status_code, from_cache) "
        "VALUES (?, ?, ?, ?)",
        (endpoint, params, status_code, 1 if from_cache else 0),
    )


def calls_used(conn: sqlite3.Connection) -> int:
    """Quota used: calls made before logging began + real calls we logged."""
    row = conn.execute(
        "SELECT COUNT(*) FROM api_call_log WHERE from_cache = 0"
    ).fetchone()
    return config.API_CALLS_OFFSET + row[0]
