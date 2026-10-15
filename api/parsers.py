"""Pure parsing functions: raw Cricbuzz JSON in, clean dicts out.

Nothing here touches the network or the database, so every function can be
tested with a saved JSON file. The API is inconsistent (key casing differs
between endpoints, numbers arrive as strings, tables are transposed), so all
of that mess is handled in this one file and nowhere else.
"""

import re
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

FORMATS = {"TEST": "TEST", "ODI": "ODI", "T20": "T20", "T20I": "T20"}
MATCH_CATEGORIES = {
    "international": "international",
    "league": "league",
    "domestic": "domestic",
    "women": "women",
}


class ParseError(ValueError):
    """Raised when a payload does not have the shape we need."""


# --------------------------------------------------------------- helpers ----
def lower_keys(obj: Any) -> Any:
    """Recursively lowercase every dict key (casing differs per endpoint)."""
    if isinstance(obj, dict):
        return {str(k).lower(): lower_keys(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [lower_keys(v) for v in obj]
    return obj


def to_int(value: Any) -> Optional[int]:
    """'11,600' -> 11600, '199*' -> 199, '' / '-' / None -> None."""
    if value is None:
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    text = str(value).strip().replace(",", "").rstrip("*")
    if text in ("", "-", "--", "N/A"):
        return None
    try:
        return int(float(text))
    except ValueError:
        return None


def to_float(value: Any) -> Optional[float]:
    """'51.32' -> 51.32, '' / '-' / None -> None."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(",", "").rstrip("*")
    if text in ("", "-", "--", "N/A"):
        return None
    try:
        return float(text)
    except ValueError:
        return None


def norm(text: Any) -> str:
    """Lowercase letters and digits only, so 'KwaZulu - Natal' == 'KwaZulu-Natal'."""
    return re.sub(r"[^a-z0-9]", "", str(text or "").lower())


def overs_to_balls(overs: Any) -> Optional[int]:
    """'3.5' overs means 3 overs and 5 balls = 23 balls (NOT 3.5 * 6)."""
    if overs is None or str(overs).strip() == "":
        return None
    text = str(overs).strip()
    whole, _, part = text.partition(".")
    try:
        balls = int(whole) * 6 + (int(part) if part else 0)
    except ValueError:
        return None
    return balls


def epoch_ms_to_date(value: Any, tz_offset: Optional[str] = None) -> Optional[str]:
    """Epoch milliseconds (string or int) -> 'YYYY-MM-DD' in the venue's timezone.

    tz_offset looks like '+05:30'. Without it we use UTC.
    """
    ms = to_int(value)
    if ms is None or ms <= 0:
        return None
    offset = timedelta(0)
    if tz_offset:
        match = re.fullmatch(r"([+-])(\d{2}):?(\d{2})", tz_offset.strip())
        if match:
            delta = timedelta(hours=int(match[2]), minutes=int(match[3]))
            offset = delta if match[1] == "+" else -delta
    moment = datetime.fromtimestamp(ms / 1000, tz=timezone.utc) + offset
    return moment.date().isoformat()


def parse_long_date(text: Any) -> Optional[str]:
    """'December 18, 1986' -> '1986-12-18'."""
    if not text:
        return None
    try:
        return datetime.strptime(str(text).strip(), "%B %d, %Y").date().isoformat()
    except ValueError:
        return None


def clean_text(value: Any) -> Optional[str]:
    """Strip whitespace; empty strings become None."""
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def pivot_stats_table(payload: dict) -> dict:
    """Turn the transposed career table into {row_label: {column: value}}.

    headers = ['ROWHEADER', 'Test', 'ODI', ...]; each row = [label, v1, v2, ...].
    """
    headers = payload.get("headers") or []
    table: dict = {}
    for row in payload.get("values") or []:
        cells = row.get("values") or []
        if not cells:
            continue
        label = str(cells[0]).strip()
        table[label] = {
            headers[i]: cells[i] for i in range(1, min(len(headers), len(cells)))
        }
    return table


# --------------------------------------------------------- match results ----
def parse_result(
    status: Optional[str], state_title: Optional[str], teams: list
) -> dict:
    """Work out winner / victory type / margin from the result text.

    teams: [{'team_id', 'team_name', 'short_name'}, ...] (the two teams).
    Returns {'winner_id', 'victory_type', 'victory_margin'} (values may be None).
    """
    out = {"winner_id": None, "victory_type": None, "victory_margin": None}
    text = (status or "").strip()
    low = text.lower()
    if not text:
        return out

    if "forfeit" in low:
        out["victory_type"] = "forfeit"
        return out
    if "abandon" in low:
        out["victory_type"] = "abandoned"
        return out
    if "no result" in low:
        out["victory_type"] = "no result"
        return out
    if "tied" in low:
        out["victory_type"] = "tie"
        return out
    if "drawn" in low or low.strip() == "match drawn":
        out["victory_type"] = "draw"
        return out

    if " won by " in low:
        inn = re.search(r"won by an innings and (\d+) runs?", low)
        runs = re.search(r"won by (\d+) runs?", low)
        wkts = re.search(r"won by (\d+) (?:wkts?|wickets?)", low)
        if inn:
            out["victory_type"], out["victory_margin"] = "innings", int(inn[1])
        elif runs:
            out["victory_type"], out["victory_margin"] = "runs", int(runs[1])
        elif wkts:
            out["victory_type"], out["victory_margin"] = "wickets", int(wkts[1])

        winner_text = norm(text[: low.index(" won by ")])
        for team in teams:
            if norm(team["team_name"]) == winner_text:
                out["winner_id"] = team["team_id"]
        if out["winner_id"] is None and state_title:
            short = norm(re.sub(r"\s+won$", "", state_title.strip(), flags=re.I))
            for team in teams:
                if norm(team.get("short_name")) == short:
                    out["winner_id"] = team["team_id"]
    return out


def parse_toss(toss_text: Optional[str], teams: list) -> dict:
    """'West Indies opt to bowl' -> {'toss_winner_id': 10, 'toss_decision': 'bowl'}.

    Wording varies ('opt to', 'elected to', 'chose to'), so anything we cannot
    read safely returns None values instead of guessing.
    """
    out = {"toss_winner_id": None, "toss_decision": None}
    text = (toss_text or "").strip()
    if not text:
        return out
    low = text.lower()
    head = norm(re.split(r"\s+(?:won the toss|opt|elected|chose|choose)", low)[0])
    for team in teams:
        if head and norm(team["team_name"]) == head:
            out["toss_winner_id"] = team["team_id"]
    if re.search(r"\bbowl|\bfield", low):
        out["toss_decision"] = "bowl"
    elif re.search(r"\bbat", low):
        out["toss_decision"] = "bat"
    if out["toss_winner_id"] is None:
        out["toss_decision"] = None
    return out


def _team_dict(raw: dict, category: Optional[str]) -> dict:
    name = clean_text(raw.get("teamname"))
    return {
        "team_id": to_int(raw.get("teamid")),
        "team_name": name,
        "short_name": clean_text(raw.get("teamsname")),
        "country": name if category == "international" else None,
        "team_type": category,
    }


def parse_recent_matches(payload: dict) -> list:
    """Parse a matches/recent (or live / upcoming) response.

    Returns a list of dicts: {'match', 'teams', 'venue', 'series'}.
    Matches in formats we do not model (e.g. T10) are skipped.
    """
    data = lower_keys(payload)
    results = []
    for group in data.get("typematches") or []:
        category = MATCH_CATEGORIES.get(str(group.get("matchtype", "")).lower())
        for series_block in group.get("seriesmatches") or []:
            wrapper = series_block.get("seriesadwrapper")
            if not wrapper:  # advert rows have no 'seriesadwrapper'
                continue
            for item in wrapper.get("matches") or []:
                info = item.get("matchinfo") or {}
                fmt = FORMATS.get(str(info.get("matchformat", "")).upper())
                match_id = to_int(info.get("matchid"))
                if fmt is None or match_id is None:
                    continue
                team1 = _team_dict(info.get("team1") or {}, category)
                team2 = _team_dict(info.get("team2") or {}, category)
                if not team1["team_id"] or not team2["team_id"]:
                    continue
                venue_raw = info.get("venueinfo") or {}
                tz = clean_text(venue_raw.get("timezone"))
                venue = None
                if to_int(venue_raw.get("id")):
                    venue = {
                        "venue_id": to_int(venue_raw.get("id")),
                        "venue_name": clean_text(venue_raw.get("ground")),
                        "city": clean_text(venue_raw.get("city")),
                        "country": clean_text(venue_raw.get("country")),
                        "capacity": to_int(venue_raw.get("capacity")),
                    }
                series = {
                    "series_id": to_int(info.get("seriesid")),
                    "series_name": clean_text(info.get("seriesname")),
                    "start_date": epoch_ms_to_date(info.get("seriesstartdt")),
                    "end_date": epoch_ms_to_date(info.get("seriesenddt")),
                }
                state = clean_text(info.get("state"))
                result = {
                    "winner_id": None,
                    "victory_type": None,
                    "victory_margin": None,
                }
                if state and state.lower() == "complete":
                    result = parse_result(
                        info.get("status"), info.get("statetitle"), [team1, team2]
                    )
                results.append(
                    {
                        "match": {
                            "match_id": match_id,
                            "series_id": series["series_id"],
                            "match_desc": clean_text(info.get("matchdesc")),
                            "format": fmt,
                            "match_category": category,
                            "match_date": epoch_ms_to_date(info.get("startdate"), tz),
                            "venue_id": venue["venue_id"] if venue else None,
                            "team1_id": team1["team_id"],
                            "team2_id": team2["team_id"],
                            "state": state,
                            "status": clean_text(info.get("status")),
                            **result,
                        },
                        "teams": [team1, team2],
                        "venue": venue,
                        "series": series if series["series_id"] else None,
                    }
                )
    return results


def parse_match_info(payload: dict) -> dict:
    """Parse matches/get-info: toss, venue details, winner short name.

    Only fields that are present are returned, so the caller never overwrites
    good data with blanks (a toss text is empty for old matches).
    """
    data = lower_keys(payload)
    t1, t2 = data.get("team1") or {}, data.get("team2") or {}
    teams = [
        {
            "team_id": to_int(t["teamid"]),
            "team_name": t.get("teamname"),
            "short_name": t.get("teamsname"),
        }
        for t in (t1, t2)
        if to_int(t.get("teamid"))
    ]
    if len(teams) != 2:
        raise ParseError("match info has no two teams")
    toss = parse_toss(data.get("tossstatus"), teams)
    winner_id = None
    short = norm(re.sub(r"\s+won$", "", str(data.get("shortstatus") or ""), flags=re.I))
    for team in teams:
        if short and norm(team["short_name"]) == short:
            winner_id = team["team_id"]
    venue_raw = data.get("venueinfo") or {}
    venue = None
    if to_int(venue_raw.get("id")):
        venue = {
            "venue_id": to_int(venue_raw["id"]),
            "venue_name": clean_text(venue_raw.get("ground")),
            "city": clean_text(venue_raw.get("city")),
            "country": clean_text(venue_raw.get("country")),
            "capacity": to_int(venue_raw.get("capacity")),
        }
    return {
        "match_id": to_int(data.get("matchid")),
        "toss_winner_id": toss["toss_winner_id"],
        "toss_decision": toss["toss_decision"],
        "winner_id": winner_id,
        "venue": venue,
    }


def parse_venue_info(payload: dict, venue_id: int) -> dict:
    """venues/get-info has no id in its body, so the caller passes it in."""
    data = lower_keys(payload)
    return {
        "venue_id": venue_id,
        "venue_name": clean_text(data.get("ground")),
        "city": clean_text(data.get("city")),
        "country": clean_text(data.get("country")),
        "capacity": to_int(data.get("capacity")),
    }


# ----------------------------------------------------------- teams/players ----
def parse_teams_list(payload: dict) -> list:
    """teams/list: section header rows ('Test Teams') have no teamId."""
    teams = []
    section_type = None
    for row in payload.get("list") or []:
        if "teamId" not in row:
            title = str(row.get("teamName", "")).lower()
            section_type = "associate" if "associate" in title else "international"
            continue
        name = clean_text(row.get("teamName"))
        teams.append(
            {
                "team_id": to_int(row["teamId"]),
                "team_name": name,
                "short_name": clean_text(row.get("teamSName")),
                "country": clean_text(row.get("countryName")) or name,
                "team_type": section_type or "international",
            }
        )
    return teams


def parse_player_info(payload: dict) -> dict:
    """players/get-info -> a row for the players table."""
    player_id = to_int(payload.get("id"))
    if player_id is None:
        raise ParseError("player info has no id")
    name = clean_text(payload.get("name"))
    return {
        "player_id": player_id,
        "full_name": clean_text(payload.get("fullName")) or name,
        "display_name": name,
        "country": clean_text(payload.get("intlTeam")),
        "playing_role": clean_text(payload.get("role")),
        "batting_style": clean_text(payload.get("bat")),
        "bowling_style": clean_text(payload.get("bowl")),
        "date_of_birth": parse_long_date(payload.get("DoBFormat")),
        "birth_place": clean_text(payload.get("birthPlace")),
    }


def parse_records(payload: dict) -> list:
    """stats/get-records: each row is [player_id, name, stat1, stat2, ...]."""
    headers = ["id"] + list(payload.get("headers") or [])
    rows = []
    for row in payload.get("values") or []:
        cells = row.get("values") or []
        if len(cells) < 2:
            continue
        record = dict(zip(headers, cells))
        rows.append(
            {
                "player_id": to_int(record["id"]),
                "name": clean_text(cells[1]),
                "stats": {k: v for k, v in list(record.items())[2:]},
            }
        )
    return rows


CAREER_FORMATS = {"Test": "TEST", "ODI": "ODI", "T20": "T20"}  # 'IPL' is ignored
_BATTING_LABELS = {
    "Matches": ("matches_played", to_int),
    "Innings": ("innings", to_int),
    "Runs": ("runs", to_int),
    "Balls": ("balls_faced", to_int),
    "Highest": ("highest_score", to_int),
    "Average": ("batting_avg", to_float),
    "SR": ("strike_rate", to_float),
    "Not Out": ("not_outs", to_int),
    "Fours": ("fours", to_int),
    "Sixes": ("sixes", to_int),
    "Ducks": ("ducks", to_int),
    "50s": ("fifties", to_int),
    "100s": ("centuries", to_int),
}
# The bowling table has not been sampled yet: labels below are our best guess
# and are confirmed against the first real players/get-bowling response.
_BOWLING_LABELS = {
    "Wickets": ("wickets", to_int),
    "Wkts": ("wickets", to_int),
    "Average": ("bowling_avg", to_float),
    "Avg": ("bowling_avg", to_float),
    "Economy": ("economy_rate", to_float),
    "Econ": ("economy_rate", to_float),
}


def _career_rows(payload: dict, player_id: int, labels: dict) -> dict:
    table = pivot_stats_table(payload)
    rows: dict = {}
    for label, (column, convert) in labels.items():
        for fmt_name, fmt_code in CAREER_FORMATS.items():
            if label in table and fmt_name in table[label]:
                row = rows.setdefault(
                    fmt_code, {"player_id": player_id, "format": fmt_code}
                )
                row[column] = convert(table[label][fmt_name])
    return rows


def parse_career_batting(payload: dict, player_id: int) -> list:
    """players/get-batting -> rows for player_career_stats (Test, ODI, T20)."""
    return list(_career_rows(payload, player_id, _BATTING_LABELS).values())


def parse_career_bowling(payload: dict, player_id: int) -> list:
    """players/get-bowling -> partial rows (wickets, average, economy)."""
    return list(_career_rows(payload, player_id, _BOWLING_LABELS).values())


# -------------------------------------------------------------- scorecard ----
_CATCH = re.compile(r"^c\s+(?P<fielder>.+?)\s+b\s+.+$", re.I)
_CAUGHT_AND_BOWLED = re.compile(r"^c\s*(?:&|and)\s*b\s+(?P<bowler>.+)$", re.I)
_STUMPED = re.compile(r"^st\s+(?P<fielder>.+?)\s+b\s+.+$", re.I)


def parse_dismissal(out_desc: Optional[str]) -> Optional[tuple]:
    """'c Smith b Jones' -> ('catch', 'Smith'); 'c and b Jones' -> ('catch', 'Jones').

    Returns (kind, fielder_name) or None (bowled, lbw, run out, not out ...).
    """
    text = (out_desc or "").strip()
    if not text:
        return None
    match = _CAUGHT_AND_BOWLED.match(text)
    if match:
        return ("catch", match["bowler"].strip())
    match = _CATCH.match(text)
    if match:
        return ("catch", match["fielder"].strip())
    match = _STUMPED.match(text)
    if match:
        return ("stumping", match["fielder"].strip())
    return None


def _resolve_name(name: str, roster: dict) -> Optional[int]:
    """Find a player id from a (possibly partial) name in a {norm_name: id} roster."""
    key = norm(name)
    if key in roster:
        return roster[key]
    hits = {
        pid
        for rname, pid in roster.items()
        if rname.endswith(key) or key.endswith(rname)
    }
    return hits.pop() if len(hits) == 1 else None


def parse_scorecard(payload: dict, match_id: int, teams: list) -> dict:
    """Parse matches/get-scorecard-v2 for one match.

    teams: the match's two teams as [{'team_id', 'team_name', 'short_name'}].
    Returns dict with 'players', 'batting', 'bowling', 'fielding',
    'partnerships' and 'unresolved_fielders' (names we could not match).
    """
    data = lower_keys(payload)
    innings_list = data.get("scorecard")
    if not innings_list:
        raise ParseError("scorecard payload has no innings")
    if len(teams) != 2:
        raise ParseError("exactly two teams are needed to read a scorecard")

    def team_for(inn: dict) -> int:
        for key in ("batteamsname", "batteamname"):
            wanted = norm(inn.get(key))
            for team in teams:
                if wanted and wanted in (
                    norm(team.get("short_name")),
                    norm(team["team_name"]),
                ):
                    return team["team_id"]
        raise ParseError(f"cannot match batting team in innings {inn.get('inningsid')}")

    def other(team_id: int) -> int:
        return (
            teams[1]["team_id"]
            if team_id == teams[0]["team_id"]
            else teams[0]["team_id"]
        )

    players: dict = {}
    batting, bowling, partnerships = [], [], []
    rosters: dict = {}  # team_id -> {norm_name: player_id}

    for inn in innings_list:
        bat_team = team_for(inn)
        bowl_team = other(bat_team)
        number = to_int(inn.get("inningsid")) or 1
        position = 0
        for b in inn.get("batsman") or []:
            pid = to_int(b.get("id"))
            if pid is None:
                continue
            name = clean_text(b.get("name"))
            players[pid] = name
            rosters.setdefault(bat_team, {})[norm(name)] = pid
            out_desc = clean_text(b.get("outdec"))
            balls = to_int(b.get("balls")) or 0
            if not out_desc and balls == 0:
                continue  # did not bat
            position += 1
            batting.append(
                {
                    "match_id": match_id,
                    "innings_no": number,
                    "player_id": pid,
                    "team_id": bat_team,
                    "batting_position": position if position <= 11 else None,
                    "runs": to_int(b.get("runs")) or 0,
                    "balls_faced": balls,
                    "fours": to_int(b.get("fours")) or 0,
                    "sixes": to_int(b.get("sixes")) or 0,
                    "strike_rate": to_float(b.get("strkrate")),
                    "is_not_out": 1 if (out_desc or "").lower() == "not out" else 0,
                    "out_desc": out_desc,
                }
            )
        for w in inn.get("bowler") or []:
            pid = to_int(w.get("id"))
            if pid is None:
                continue
            name = clean_text(w.get("name"))
            players[pid] = players.get(pid) or name
            rosters.setdefault(bowl_team, {})[norm(name)] = pid
            overs = clean_text(w.get("overs"))
            balls = overs_to_balls(overs)
            if balls is None:
                continue
            bowling.append(
                {
                    "match_id": match_id,
                    "innings_no": number,
                    "player_id": pid,
                    "team_id": bowl_team,
                    "overs": to_float(overs),
                    # Derived from overs: the API's own 'balls' is really overs x 10.
                    "balls": balls,
                    "maidens": to_int(w.get("maidens")) or 0,
                    "runs_conceded": to_int(w.get("runs")) or 0,
                    "wickets": to_int(w.get("wickets")) or 0,
                    "economy": to_float(w.get("economy")),
                }
            )
        pairs = (inn.get("partnership") or {}).get("partnership") or []
        for index, pair in enumerate(pairs[:10], start=1):
            a, b = to_int(pair.get("bat1id")), to_int(pair.get("bat2id"))
            if not a or not b or a == b:
                continue
            partnerships.append(
                {
                    "match_id": match_id,
                    "innings_no": number,
                    "wicket_no": index,
                    "bat1_id": a,
                    "bat2_id": b,
                    "runs": to_int(pair.get("totalruns")) or 0,
                    "balls": to_int(pair.get("totalballs")),
                }
            )

    # Fielding: read dismissal text and credit the fielder from the bowling side.
    counts: dict = {}
    unresolved: list = []
    for inn in innings_list:
        bowl_team = other(team_for(inn))
        for b in inn.get("batsman") or []:
            parsed = parse_dismissal(b.get("outdec"))
            if not parsed:
                continue
            kind, fielder = parsed
            pid = _resolve_name(fielder, rosters.get(bowl_team, {}))
            if pid is None:
                unresolved.append(fielder)
                continue
            entry = counts.setdefault(pid, {"catches": 0, "stumpings": 0})
            entry["catches" if kind == "catch" else "stumpings"] += 1
    fielding = [
        {"match_id": match_id, "player_id": pid, **c} for pid, c in counts.items()
    ]

    return {
        "players": players,
        "batting": batting,
        "bowling": bowling,
        "fielding": fielding,
        "partnerships": partnerships,
        "unresolved_fielders": unresolved,
    }


# ------------------------------------------------- series and leaderboards ----
def parse_series_archives(payload: dict) -> list:
    """series/archives: groups by year, each with a list of series.

    The response has no host country, match type or match count, so those
    series columns stay empty (NULL) until another source fills them in.
    """
    data = lower_keys(payload)
    series = []
    for group in data.get("seriesmapproto") or []:
        for item in group.get("series") or []:
            series_id = to_int(item.get("id"))
            if series_id is None:
                continue
            series.append(
                {
                    "series_id": series_id,
                    "series_name": clean_text(item.get("name")),
                    "start_date": epoch_ms_to_date(item.get("startdt")),
                    "end_date": epoch_ms_to_date(item.get("enddt")),
                }
            )
    return series


MATCH_TYPE_IDS = {"1": "TEST", "2": "ODI", "3": "T20"}
_BOWLING_STATS = {
    "mostWickets",
    "lowestAvg",
    "bestBowlingInnings",
    "mostFiveWickets",
    "lowestEcon",
    "lowestSr",
}
_BATTING_RECORD_COLUMNS = {
    "M": ("matches_played", to_int),
    "I": ("innings", to_int),
    "R": ("runs", to_int),
    "RUNS": ("runs", to_int),
    "SR": ("strike_rate", to_float),
    "AVG": ("batting_avg", to_float),
    "HS": ("highest_score", to_int),
    "HIGHEST": ("highest_score", to_int),
    "SCORE": ("highest_score", to_int),
    "100S": ("centuries", to_int),
    "50S": ("fifties", to_int),
}
_BOWLING_RECORD_COLUMNS = {
    "M": ("matches_played", to_int),
    "I": ("innings", to_int),
    "W": ("wickets", to_int),
    "WKTS": ("wickets", to_int),
    "AVG": ("bowling_avg", to_float),
    "ECON": ("economy_rate", to_float),
}
_SELECTED_NAMES = {"1": "test", "2": "odi", "3": "t20"}


def parse_records_stats(payload: dict, stats_type: str, match_type: str) -> dict:
    """stats/topstats leaderboard -> rows for player_career_stats.

    Returns {'rows': [...], 'names': {player_id: name}, 'recognized': [...],
    'ignored': [...]}. Refuses to continue if the API answered for a different
    match type than the one we asked for, so numbers can never be filed under
    the wrong format.
    """
    fmt = MATCH_TYPE_IDS.get(str(match_type))
    if fmt is None:
        raise ParseError(f"matchType must be 1, 2 or 3 (got {match_type!r})")
    selected = str((payload.get("filter") or {}).get("selectedMatchType", "")).lower()
    if selected and selected != _SELECTED_NAMES[str(match_type)]:
        raise ParseError(
            f"records reply is for '{selected}', expected "
            f"'{_SELECTED_NAMES[str(match_type)]}' - matchType may mean something else"
        )
    mapping = (
        _BOWLING_RECORD_COLUMNS
        if stats_type in _BOWLING_STATS
        else _BATTING_RECORD_COLUMNS
    )
    recognized, ignored = set(), set()
    rows, names = [], {}
    for record in parse_records(payload):
        row = {"player_id": record["player_id"], "format": fmt}
        for header, value in record["stats"].items():
            target = mapping.get(str(header).upper())
            if target is None:
                ignored.add(header)
                continue
            column, convert = target
            row[column] = convert(value)
            recognized.add(header)
        names[record["player_id"]] = record["name"]
        rows.append(row)
    return {
        "rows": rows,
        "names": names,
        "recognized": sorted(recognized),
        "ignored": sorted(ignored),
    }
