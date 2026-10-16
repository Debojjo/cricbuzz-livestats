"""Generate clearly FICTIONAL sample data (every row has is_sample = 1).

Why: the API's free quota only gives a few days of match history, but questions
like Q16, Q19, Q22-Q25 need years of it. This script plays out fictional teams
("Sample XI Alpha"...) ball by ball, so every number is internally consistent:
partnership runs add up to the innings total, bowlers' wickets match the
dismissals, catches match the 'c X b Y' text.

It never touches real rows and never uses real team or player names, so
nothing here can be mistaken for fact. Re-running replaces only sample rows::

    python -m data.seed_sample_data            # 700 matches, seed 2026
    python -m data.seed_sample_data --matches 300 --seed 7
"""

import argparse
import random
from datetime import date, timedelta
from typing import Optional

from database import repositories as repo
from database.init_db import init_db
from utils.db_connection import transaction

FIRST_DATE = date(2020, 1, 15)
TEAM_LETTERS = [
    "Alpha",
    "Bravo",
    "Charlie",
    "Delta",
    "Echo",
    "Foxtrot",
    "Golf",
    "Hotel",
]
VENUE_CAPACITIES = [
    65000, 32000, 52000, 25000, 45000, 38000, 58000, 21000,
    41000, 30000, 36000, 27000, 55000, 24000, 34000, 29000,
]  # fmt: skip
VENUE_KINDS = ["National Stadium", "Oval"]
TEAM_ID0, VENUE_ID0, PLAYER_ID0, SERIES_ID0, MATCH_ID0 = (
    900_001,
    900_101,
    910_001,
    920_000,
    930_000,
)

# (role, slot kind) for the 15-player squad: 11 core + 4 bench.
SQUAD_ROLES = (
    ["Batsman"] * 5
    + ["WK-Batsman", "Batting Allrounder", "Bowling Allrounder"]
    + ["Bowler"] * 3
    + ["Batsman", "Bowler", "Bowler", "Bowling Allrounder"]
)
BAT_BASE = {
    "Batsman": 1.15,
    "WK-Batsman": 1.0,
    "Batting Allrounder": 1.0,
    "Bowling Allrounder": 0.8,
    "Bowler": 0.55,
}
BOWL_BASE = {
    "Batsman": 0.3,
    "WK-Batsman": 0.2,
    "Batting Allrounder": 0.8,
    "Bowling Allrounder": 1.0,
    "Bowler": 1.1,
}
# Ball outcome weights: dot, 1, 2, 3, 4, 6, wicket, wide
OUTCOMES = {
    "T20": {
        "max_balls": 120,
        "w": [0.34, 0.35, 0.07, 0.01, 0.095, 0.037, 0.045, 0.035],
    },
    "ODI": {"max_balls": 300, "w": [0.44, 0.37, 0.06, 0.01, 0.06, 0.018, 0.025, 0.02]},
}
WICKET_KINDS = ["bowled", "lbw", "caught", "stumped", "run out"]
WICKET_WEIGHTS = [0.22, 0.18, 0.45, 0.05, 0.10]
SAMPLE_TABLES_DELETE_ORDER = [
    "partnerships",
    "fielding_performances",
    "bowling_performances",
    "batting_performances",
    "player_career_stats",
    "matches",
    "series",
    "players",
    "venues",
    "teams",
]


# ------------------------------------------------------------ the world ----
def build_world(rng: random.Random) -> dict:
    """Fictional teams, venues and players (with hidden skill and trend)."""
    teams, venues, players = [], [], []
    for index, letter in enumerate(TEAM_LETTERS):
        team_id = TEAM_ID0 + index
        country = f"{letter}land"
        teams.append(
            {
                "team_id": team_id,
                "team_name": f"Sample XI {letter}",
                "short_name": f"SX{letter[0]}",
                "country": country,
                "team_type": "international",
                "is_sample": 1,
            }
        )
        for n in range(2):
            venues.append(
                {
                    "venue_id": VENUE_ID0 + index * 2 + n,
                    "venue_name": f"{country} {VENUE_KINDS[n]}",
                    "city": f"{letter} City" if n == 0 else f"{letter} Town",
                    "country": country,
                    "capacity": VENUE_CAPACITIES[index * 2 + n],
                    "is_sample": 1,
                    "team_id": team_id,
                }
            )
        for slot, role in enumerate(SQUAD_ROLES):
            players.append(
                {
                    "player_id": PLAYER_ID0 + index * 15 + slot,
                    "full_name": f"Sample {letter} Player {slot + 1:02d}",
                    "display_name": f"{letter[0]}{slot + 1:02d}",
                    "country": country,
                    "playing_role": role,
                    "batting_style": rng.choice(["Right-hand bat", "Left-hand bat"]),
                    "bowling_style": (
                        rng.choice(
                            [
                                "Right-arm fast",
                                "Left-arm orthodox",
                                "Right-arm offbreak",
                            ]
                        )
                        if BOWL_BASE[role] >= 0.8
                        else None
                    ),
                    "is_sample": 1,
                    "team_id": team_id,
                    "slot": slot,
                    "role": role,
                    "bat": BAT_BASE[role] * rng.uniform(0.85, 1.15),
                    "bowl": BOWL_BASE[role] * rng.uniform(0.85, 1.15),
                    "slope": rng.uniform(-0.05, 0.06),  # skill change per year
                }
            )
    return {"teams": teams, "venues": venues, "players": players}


def pick_xi(rng: random.Random, squad: list) -> list:
    """11 players: the core, with occasional same-role swaps from the bench."""
    core, bench = list(squad[:11]), list(squad[11:])
    for i, player in enumerate(core):
        if rng.random() < 0.12:
            options = [b for b in bench if b["role"] == player["role"]]
            if options:
                swap = rng.choice(options)
                bench.remove(swap)
                bench.append(core[i])
                core[i] = swap
    return core


def skill_at(player: dict, key: str, years: float) -> float:
    """Skill at a point in time: base level plus the player's personal trend."""
    base = player[key]
    if key == "bat":
        base *= 1 + player["slope"] * years
    return min(max(base, 0.2), 1.9)


# ----------------------------------------------------------- simulation ----
def simulate_innings(
    rng: random.Random,
    fmt: str,
    batters: list,
    bowlers: list,
    fielders: list,
    years: float,
    target: Optional[int] = None,
) -> dict:
    """Play one innings ball by ball and return every number a scorecard has."""
    cfg = OUTCOMES[fmt]
    stats = {
        p["player_id"]: {"runs": 0, "balls": 0, "fours": 0, "sixes": 0, "out": None}
        for p in batters
    }
    bowl = {
        p["player_id"]: {"balls": 0, "runs": 0, "wkts": 0, "maidens": 0}
        for p in bowlers
    }
    striker, non_striker, next_in = 0, 1, 2
    wickets = total = legal = over = 0
    pair_runs = pair_balls = 0
    partnerships: list = []
    catches: dict = {}
    stumpings: dict = {}
    keeper = next((p for p in fielders if p["role"] == "WK-Batsman"), fielders[0])
    done = False

    while legal < cfg["max_balls"] and wickets < 10 and not done:
        bowler = bowlers[over % len(bowlers)]
        bid = bowler["player_id"]
        over_runs = over_legal = 0
        while over_legal < 6 and legal < cfg["max_balls"] and wickets < 10 and not done:
            bat = batters[striker]
            bat_s, bowl_s = skill_at(bat, "bat", years), skill_at(bowler, "bowl", years)
            ratio = bowl_s / bat_s
            boost = (bat_s / bowl_s) ** 0.6
            w = list(cfg["w"])
            w[0] /= boost**0.5
            w[4] *= boost
            w[5] *= boost
            w[6] *= ratio**0.8
            outcome = rng.choices(range(8), weights=w)[0]

            if outcome == 7:  # wide: a run, but not a legal ball
                total += 1
                pair_runs += 1
                bowl[bid]["runs"] += 1
                over_runs += 1
                continue

            legal += 1
            over_legal += 1
            stats[bat["player_id"]]["balls"] += 1
            bowl[bid]["balls"] += 1
            pair_balls += 1

            if outcome == 6:  # wicket
                kind = rng.choices(WICKET_KINDS, weights=WICKET_WEIGHTS)[0]
                out_index = striker
                if kind == "run out" and rng.random() < 0.5:
                    out_index = non_striker
                out_player = batters[out_index]
                fielder = rng.choice(fielders)
                if kind == "bowled":
                    text = f"b {bowler['full_name']}"
                elif kind == "lbw":
                    text = f"lbw b {bowler['full_name']}"
                elif kind == "caught":
                    if fielder["player_id"] == bid:
                        text = f"c and b {bowler['full_name']}"
                    else:
                        text = f"c {fielder['full_name']} b {bowler['full_name']}"
                    catches[fielder["player_id"]] = (
                        catches.get(fielder["player_id"], 0) + 1
                    )
                elif kind == "stumped":
                    text = f"st {keeper['full_name']} b {bowler['full_name']}"
                    stumpings[keeper["player_id"]] = (
                        stumpings.get(keeper["player_id"], 0) + 1
                    )
                else:
                    text = f"run out ({fielder['full_name']})"
                if kind != "run out":
                    bowl[bid]["wkts"] += 1
                stats[out_player["player_id"]]["out"] = text
                wickets += 1
                partnerships.append(
                    {
                        "wicket_no": wickets,
                        "bat1": batters[striker]["player_id"],
                        "bat2": batters[non_striker]["player_id"],
                        "runs": pair_runs,
                        "balls": pair_balls,
                    }
                )
                pair_runs = pair_balls = 0
                if wickets < 10 and next_in < len(batters):
                    if out_index == striker:
                        striker = next_in
                    else:
                        non_striker = next_in
                    next_in += 1
                continue

            runs = [0, 1, 2, 3, 4, 6][outcome]
            total += runs
            pair_runs += runs
            bowl[bid]["runs"] += runs
            over_runs += runs
            row = stats[bat["player_id"]]
            row["runs"] += runs
            row["fours"] += runs == 4
            row["sixes"] += runs == 6
            if runs in (1, 3):
                striker, non_striker = non_striker, striker
            if target is not None and total > target:
                done = True

        if over_legal == 6 and over_runs == 0:
            bowl[bid]["maidens"] += 1
        striker, non_striker = non_striker, striker
        over += 1

    if wickets < 10 and (pair_runs or pair_balls):
        partnerships.append(
            {
                "wicket_no": wickets + 1,
                "bat1": batters[striker]["player_id"],
                "bat2": batters[non_striker]["player_id"],
                "runs": pair_runs,
                "balls": pair_balls,
            }
        )
    return {
        "total": total,
        "wickets": wickets,
        "balls": legal,
        "stats": stats,
        "arrived": next_in if wickets < 10 else len(batters),
        "bowl": bowl,
        "partnerships": partnerships,
        "catches": catches,
        "stumpings": stumpings,
    }


def _overs(balls: int) -> float:
    return float(f"{balls // 6}.{balls % 6}")


# ---------------------------------------------------------- orchestration ----
def delete_sample_rows(conn) -> None:
    """Remove every sample row (and only sample rows), children first."""
    for table in SAMPLE_TABLES_DELETE_ORDER:
        conn.execute(f"DELETE FROM {table} WHERE is_sample = 1")


def bulk_insert(conn, table: str, rows: list) -> None:
    """Fast insert for rows that cannot already exist (we deleted them first)."""
    if not rows:
        return
    allowed = repo._columns(conn, table)
    cols = [c for c in rows[0] if c in allowed]
    marks = ", ".join("?" for _ in cols)
    conn.executemany(
        f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({marks})",
        [[row[c] for c in cols] for row in rows],
    )


def generate(conn, matches: int = 700, seed: int = 2026, today: Optional[date] = None):
    """Delete old sample rows and write a fresh, consistent fictional history."""
    rng = random.Random(seed)
    today = today or date.today()
    delete_sample_rows(conn)
    world = build_world(rng)
    squads = {
        t["team_id"]: [p for p in world["players"] if p["team_id"] == t["team_id"]]
        for t in world["teams"]
    }
    venues_by_team = {
        t["team_id"]: [v for v in world["venues"] if v["team_id"] == t["team_id"]]
        for t in world["teams"]
    }
    team_by_id = {t["team_id"]: t for t in world["teams"]}

    span = (today - timedelta(days=1) - FIRST_DATE).days
    dates = sorted(
        FIRST_DATE + timedelta(days=rng.randrange(span)) for _ in range(matches)
    )

    series_rows, match_rows = {}, []
    bat_rows, bowl_rows, field_rows, pair_rows = [], [], [], []
    for number, played in enumerate(dates, start=1):
        match_id = MATCH_ID0 + number
        t1, t2 = rng.sample(list(team_by_id), 2)
        fmt = rng.choices(["T20", "ODI"], weights=[0.6, 0.4])[0]
        home_pool = venues_by_team[t1] if rng.random() < 0.75 else venues_by_team[t2]
        venue = rng.choice(home_pool)
        years = (played - FIRST_DATE).days / 365
        toss_winner = rng.choice([t1, t2])
        decision = rng.choices(["bat", "bowl"], weights=[0.55, 0.45])[0]
        first = toss_winner if decision == "bat" else (t2 if toss_winner == t1 else t1)
        second = t2 if first == t1 else t1

        xi = {tid: pick_xi(rng, squads[tid]) for tid in (t1, t2)}

        def bowlers_of(team_id):
            pool = [p for p in xi[team_id] if p["bowl"] >= 0.7]
            pool.sort(key=lambda p: -p["bowl"])
            return pool[:5]

        inn1 = simulate_innings(
            rng, fmt, xi[first], bowlers_of(second), xi[second], years
        )
        inn2 = simulate_innings(
            rng,
            fmt,
            xi[second],
            bowlers_of(first),
            xi[first],
            years,
            target=inn1["total"],
        )

        if inn2["total"] > inn1["total"]:
            winner, vtype, margin = second, "wickets", 10 - inn2["wickets"]
        elif inn2["total"] < inn1["total"]:
            winner, vtype, margin = first, "runs", inn1["total"] - inn2["total"]
        else:
            winner, vtype, margin = None, "tie", None
        status = (
            "Match tied"
            if winner is None
            else f"{team_by_id[winner]['team_name']} won by {margin} "
            f"{'runs' if vtype == 'runs' else 'wkts'}"
        )
        year = played.year
        series_rows.setdefault(
            year,
            {
                "series_id": SERIES_ID0 + year,
                "series_name": f"Sample Series {year}",
                "start_date": f"{year}-01-01",
                "end_date": f"{year}-12-31",
                "total_matches": 0,
                "is_sample": 1,
            },
        )["total_matches"] += 1
        match_rows.append(
            {
                "match_id": match_id,
                "series_id": SERIES_ID0 + year,
                "match_desc": f"Sample match {number}",
                "format": fmt,
                "match_category": "international",
                "match_date": played.isoformat(),
                "venue_id": venue["venue_id"],
                "team1_id": t1,
                "team2_id": t2,
                "toss_winner_id": toss_winner,
                "toss_decision": decision,
                "winner_id": winner,
                "victory_margin": margin,
                "victory_type": vtype,
                "state": "Complete",
                "status": status,
                "is_sample": 1,
            }
        )

        fielding: dict = {}
        for number_in_match, (bat_team, bowl_team, inn) in enumerate(
            ((first, second, inn1), (second, first, inn2)), start=1
        ):
            batting_xi = xi[bat_team]
            for position, player in enumerate(batting_xi[: inn["arrived"]], start=1):
                s = inn["stats"][player["player_id"]]
                bat_rows.append(
                    {
                        "match_id": match_id,
                        "innings_no": number_in_match,
                        "player_id": player["player_id"],
                        "team_id": bat_team,
                        "batting_position": position,
                        "runs": s["runs"],
                        "balls_faced": s["balls"],
                        "fours": s["fours"],
                        "sixes": s["sixes"],
                        "strike_rate": (
                            round(s["runs"] * 100 / s["balls"], 2)
                            if s["balls"]
                            else 0.0
                        ),
                        "is_not_out": 0 if s["out"] else 1,
                        "out_desc": s["out"] or "not out",
                        "is_sample": 1,
                    }
                )
            for player_id, b in inn["bowl"].items():
                if b["balls"] == 0 and b["runs"] == 0:
                    continue
                bowl_rows.append(
                    {
                        "match_id": match_id,
                        "innings_no": number_in_match,
                        "player_id": player_id,
                        "team_id": bowl_team,
                        "overs": _overs(b["balls"]),
                        "balls": b["balls"],
                        "maidens": b["maidens"],
                        "runs_conceded": b["runs"],
                        "wickets": b["wkts"],
                        "economy": (
                            round(b["runs"] * 6 / b["balls"], 2) if b["balls"] else None
                        ),
                        "is_sample": 1,
                    }
                )
            for pair in inn["partnerships"]:
                pair_rows.append(
                    {
                        "match_id": match_id,
                        "innings_no": number_in_match,
                        "wicket_no": pair["wicket_no"],
                        "bat1_id": pair["bat1"],
                        "bat2_id": pair["bat2"],
                        "runs": pair["runs"],
                        "balls": pair["balls"],
                        "is_sample": 1,
                    }
                )
            for pid, n in inn["catches"].items():
                fielding.setdefault(pid, [0, 0])[0] += n
            for pid, n in inn["stumpings"].items():
                fielding.setdefault(pid, [0, 0])[1] += n
        for pid, (c, st) in fielding.items():
            field_rows.append(
                {
                    "match_id": match_id,
                    "player_id": pid,
                    "catches": c,
                    "stumpings": st,
                    "is_sample": 1,
                }
            )

    bulk_insert(conn, "teams", world["teams"])
    bulk_insert(conn, "venues", world["venues"])
    bulk_insert(conn, "players", world["players"])
    bulk_insert(conn, "series", list(series_rows.values()))
    bulk_insert(conn, "matches", match_rows)
    bulk_insert(conn, "batting_performances", bat_rows)
    bulk_insert(conn, "bowling_performances", bowl_rows)
    bulk_insert(conn, "fielding_performances", field_rows)
    bulk_insert(conn, "partnerships", pair_rows)
    return {
        "teams": len(world["teams"]),
        "venues": len(world["venues"]),
        "players": len(world["players"]),
        "matches": len(match_rows),
        "batting": len(bat_rows),
        "bowling": len(bowl_rows),
        "fielding": len(field_rows),
        "partnerships": len(pair_rows),
    }


def main() -> None:
    """Command-line entry point."""
    parser = argparse.ArgumentParser(description="Generate fictional sample data.")
    parser.add_argument("--matches", type=int, default=700)
    parser.add_argument("--seed", type=int, default=2026)
    args = parser.parse_args()
    init_db()
    with transaction() as conn:
        summary = generate(conn, args.matches, args.seed)
    print("\nSample data written (is_sample = 1, fictional teams/players):")
    for key, value in summary.items():
        print(f"  {key}: {value}")


if __name__ == "__main__":
    main()
