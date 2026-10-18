"""Match data for the Live Matches page: saved results, scorecards, live feed."""

from typing import Optional

import pandas as pd

from api import endpoints, parsers
from api.cricbuzz_client import CricbuzzClient
from utils.db_connection import fetch_all

LIVE_CACHE_SECONDS = 15 * 60
SCORECARD_CACHE_SECONDS = 60 * 60


def recent_results(limit: int = 40, include_sample: bool = False, db_path=None) -> list:
    """The newest completed matches in the database (real ones by default)."""
    return fetch_all(
        """
        SELECT match_id, match_desc, format, match_date, status, series_name,
               team1_name, team2_name, winner_name, venue_name, venue_city
        FROM v_match_results
        WHERE state = 'Complete'
        ORDER BY match_date DESC, match_id DESC
        LIMIT ?
        """,
        (int(limit),),
        db_path=db_path,
        include_sample=include_sample,
    )


def stored_scorecard(match_id: int, include_sample: bool = False, db_path=None) -> dict:
    """Batting, bowling and partnership tables of a stored match (may be empty)."""

    def frame(sql: str) -> pd.DataFrame:
        rows = fetch_all(
            sql, (int(match_id),), db_path=db_path, include_sample=include_sample
        )
        return pd.DataFrame(rows)

    return {
        "batting": frame(
            "SELECT innings_no AS innings, team_name AS team, batting_position AS pos,"
            " player_name AS batsman, runs, balls_faced AS balls, fours, sixes,"
            " strike_rate AS sr, out_desc AS dismissal FROM v_batting_detail"
            " WHERE match_id = ? ORDER BY innings_no, batting_position"
        ),
        "bowling": frame(
            "SELECT innings_no AS innings, team_name AS team, player_name AS bowler,"
            " overs, maidens, runs_conceded AS runs, wickets, economy_calc AS economy"
            " FROM v_bowling_detail WHERE match_id = ? ORDER BY innings_no, balls DESC"
        ),
        "partnerships": frame(
            "SELECT innings_no AS innings, wicket_no AS wicket, bat1_name AS batsman_1,"
            " bat2_name AS batsman_2, runs, balls FROM v_partnership_detail"
            " WHERE match_id = ? ORDER BY innings_no, wicket_no"
        ),
    }


def live_matches(client: CricbuzzClient) -> list:
    """Matches from the live feed (1 API call, then cached for 15 minutes)."""
    payload = client.get(endpoints.MATCHES_LIVE, max_age=LIVE_CACHE_SECONDS)
    return parsers.parse_recent_matches(payload)


def live_scorecard(client: CricbuzzClient, item: dict) -> dict:
    """Scorecard tables for one live match (1 API call, cached for an hour)."""
    match = item["match"]
    payload = client.get(
        endpoints.SCORECARD,
        {"matchId": match["match_id"]},
        max_age=SCORECARD_CACHE_SECONDS,
    )
    teams = [
        {
            "team_id": t["team_id"],
            "team_name": t["team_name"],
            "short_name": t["short_name"],
        }
        for t in item["teams"]
    ]
    parsed = parsers.parse_scorecard(payload, match["match_id"], teams)
    names = parsed["players"]
    bat = pd.DataFrame(parsed["batting"])
    bowl = pd.DataFrame(parsed["bowling"])
    if not bat.empty:
        bat["batsman"] = bat["player_id"].map(names)
        bat = bat[["innings_no", "batting_position", "batsman", "runs", "balls_faced",
                   "fours", "sixes", "strike_rate", "out_desc"]]  # fmt: skip
    if not bowl.empty:
        bowl["bowler"] = bowl["player_id"].map(names)
        bowl = bowl[["innings_no", "bowler", "overs", "maidens", "runs_conceded",
                     "wickets", "economy"]]  # fmt: skip
    return {"batting": bat, "bowling": bowl, "raw": payload}


def match_choices(search: Optional[str] = None, limit: int = 60, db_path=None) -> list:
    """Matches to pick from in a form, newest first (optional text filter)."""
    where, params = "", []
    if search:
        where = "WHERE team1_name LIKE ? OR team2_name LIKE ? OR match_desc LIKE ?"
        params = [f"%{search}%"] * 3
    rows = fetch_all(
        f"""
        SELECT match_id, match_date, match_desc, format, team1_id, team1_name,
               team2_id, team2_name
        FROM v_match_results {where}
        ORDER BY match_date DESC, match_id DESC LIMIT ?
        """,
        tuple(params) + (int(limit),),
        db_path=db_path,
    )
    for row in rows:
        row["label"] = (
            f"{row['match_date']} - {row['team1_name']} v {row['team2_name']} "
            f"({row['match_desc'] or row['format']}) #{row['match_id']}"
        )
    return rows


def describe_live(item: dict) -> str:
    """One-line label for a live match in a selector."""
    match = item["match"]
    t1, t2 = item["teams"]
    status = match["status"] or match["state"]
    names = f"{t1['team_name']} v {t2['team_name']}"
    return f"{names} - {match['match_desc'] or ''} ({status})"


__all__ = [
    "recent_results",
    "stored_scorecard",
    "live_matches",
    "live_scorecard",
    "describe_live",
    "match_choices",
]
