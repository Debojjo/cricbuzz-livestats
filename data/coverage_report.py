"""Which of the 25 questions already have enough REAL data?

Read-only (no API calls, no writes). Run::

    python -m data.coverage_report

Each line shows how many rows a question can find right now. OK means a
sensible answer exists, THIN means a few rows, SEED means nothing yet and the
labeled sample-data generator has to fill it. The second part lists simple
data-quality checks (NULLs, unparsed results).
"""

from pathlib import Path
from typing import Optional

from utils.db_connection import fetch_all

# (question, description, SQL returning one number, rows needed for "OK")
CHECKS = [
    (
        "Q1",
        "players who represent India",
        "SELECT COUNT(*) FROM players WHERE country = 'India'",
        10,
    ),
    (
        "Q2",
        "matches in the last 30 days",
        "SELECT COUNT(*) FROM matches WHERE match_date >= date('now','-30 day')",
        10,
    ),
    (
        "Q3",
        "ODI run-scorers with average and centuries",
        "SELECT COUNT(*) FROM player_career_stats WHERE format='ODI' AND runs>0 AND batting_avg IS NOT NULL AND centuries IS NOT NULL",
        10,
    ),
    (
        "Q4",
        "venues with capacity over 50,000",
        "SELECT COUNT(*) FROM venues WHERE capacity > 50000",
        3,
    ),
    (
        "Q5",
        "teams with at least one win",
        "SELECT COUNT(DISTINCT winner_id) FROM matches WHERE winner_id IS NOT NULL",
        10,
    ),
    (
        "Q6",
        "distinct playing roles known",
        "SELECT COUNT(DISTINCT playing_role) FROM players WHERE playing_role IS NOT NULL",
        4,
    ),
    (
        "Q7",
        "formats with a highest score",
        "SELECT COUNT(DISTINCT format) FROM player_career_stats WHERE highest_score IS NOT NULL",
        3,
    ),
    (
        "Q8",
        "series starting in 2024",
        "SELECT COUNT(*) FROM series WHERE start_date >= '2024-01-01' AND start_date < '2025-01-01'",
        5,
    ),
    (
        "Q9",
        "all-rounders over 1000 runs and 50 wickets",
        "SELECT COUNT(*) FROM player_career_stats c JOIN players p USING(player_id) WHERE p.playing_role LIKE '%Allrounder%' AND c.runs>1000 AND c.wickets>50",
        3,
    ),
    (
        "Q10",
        "completed matches with winner and margin",
        "SELECT COUNT(*) FROM matches WHERE winner_id IS NOT NULL AND victory_margin IS NOT NULL",
        20,
    ),
    (
        "Q11",
        "players with career stats in 2+ formats",
        "SELECT COUNT(*) FROM (SELECT player_id FROM player_career_stats GROUP BY player_id HAVING COUNT(*)>=2)",
        10,
    ),
    (
        "Q12",
        "international matches with venue and team country known",
        "SELECT COUNT(*) FROM v_match_results WHERE match_category='international' AND venue_country IS NOT NULL AND team1_country IS NOT NULL",
        20,
    ),
    (
        "Q13",
        "consecutive partnerships of 100+ runs",
        "SELECT COUNT(*) FROM v_partnership_detail WHERE is_consecutive=1 AND runs>=100",
        3,
    ),
    (
        "Q14",
        "bowler-venue pairs with 3+ matches",
        "SELECT COUNT(*) FROM (SELECT player_id, venue_id FROM v_bowling_detail GROUP BY player_id, venue_id HAVING COUNT(DISTINCT match_id)>=3)",
        5,
    ),
    (
        "Q15",
        "players in close matches (<50 runs or <5 wickets)",
        "SELECT COUNT(DISTINCT player_id) FROM v_batting_detail WHERE (victory_type='runs' AND victory_margin<50) OR (victory_type='wickets' AND victory_margin<5)",
        10,
    ),
    (
        "Q16",
        "player-years with 5+ matches since 2020",
        "SELECT COUNT(*) FROM (SELECT player_id, match_year FROM v_batting_detail WHERE match_year>=2020 GROUP BY player_id, match_year HAVING COUNT(DISTINCT match_id)>=5)",
        10,
    ),
    (
        "Q17",
        "matches with toss and winner known",
        "SELECT COUNT(*) FROM matches WHERE toss_winner_id IS NOT NULL AND winner_id IS NOT NULL",
        30,
    ),
    (
        "Q18",
        "limited-overs bowlers with 10+ matches",
        "SELECT COUNT(*) FROM (SELECT player_id FROM v_bowling_detail WHERE format IN ('ODI','T20') GROUP BY player_id HAVING COUNT(DISTINCT match_id)>=10)",
        10,
    ),
    (
        "Q19",
        "players with 10+ innings since 2022",
        "SELECT COUNT(*) FROM (SELECT player_id FROM v_batting_detail WHERE match_year>=2022 GROUP BY player_id HAVING COUNT(*)>=10)",
        10,
    ),
    (
        "Q20",
        "players with 20+ career matches",
        "SELECT COUNT(*) FROM (SELECT player_id FROM player_career_stats GROUP BY player_id HAVING SUM(matches_played)>=20)",
        10,
    ),
    (
        "Q21",
        "players with batting, bowling and fielding data",
        "SELECT COUNT(*) FROM players p WHERE EXISTS (SELECT 1 FROM batting_performances b WHERE b.player_id=p.player_id) AND EXISTS (SELECT 1 FROM bowling_performances w WHERE w.player_id=p.player_id) AND EXISTS (SELECT 1 FROM fielding_performances f WHERE f.player_id=p.player_id)",
        10,
    ),
    (
        "Q22",
        "team pairs with 5+ matches in the last 3 years",
        "SELECT COUNT(*) FROM (SELECT MIN(team1_id,team2_id) a, MAX(team1_id,team2_id) b FROM matches WHERE match_date >= date('now','-3 year') GROUP BY a, b HAVING COUNT(*)>=5)",
        5,
    ),
    (
        "Q23",
        "players with 10+ batting innings",
        "SELECT COUNT(*) FROM (SELECT player_id FROM batting_performances GROUP BY player_id HAVING COUNT(*)>=10)",
        10,
    ),
    (
        "Q24",
        "player pairs with 5+ consecutive partnerships",
        "SELECT COUNT(*) FROM (SELECT MIN(bat1_id,bat2_id) a, MAX(bat1_id,bat2_id) b FROM v_partnership_detail WHERE is_consecutive=1 GROUP BY a, b HAVING COUNT(*)>=5)",
        5,
    ),
    (
        "Q25",
        "players spanning 6+ quarters",
        "SELECT COUNT(*) FROM (SELECT player_id FROM v_batting_detail GROUP BY player_id HAVING COUNT(DISTINCT match_year*10+match_quarter)>=6)",
        5,
    ),
]

QUALITY = [
    (
        "completed matches with no winner/result parsed",
        "SELECT COUNT(*) FROM matches WHERE state='Complete' AND victory_type IS NULL",
    ),
    ("matches without a venue", "SELECT COUNT(*) FROM matches WHERE venue_id IS NULL"),
    (
        "matches with a toss recorded",
        "SELECT COUNT(*) FROM matches WHERE toss_winner_id IS NOT NULL",
    ),
    ("venues without a country", "SELECT COUNT(*) FROM venues WHERE country IS NULL"),
    (
        "venues with a capacity",
        "SELECT COUNT(*) FROM venues WHERE capacity IS NOT NULL",
    ),
    (
        "players without a role",
        "SELECT COUNT(*) FROM players WHERE playing_role IS NULL",
    ),
    (
        "players with a full profile",
        "SELECT COUNT(*) FROM players WHERE country IS NOT NULL",
    ),
    (
        "batting rows without a batting position",
        "SELECT COUNT(*) FROM batting_performances WHERE batting_position IS NULL",
    ),
    (
        "sample (non-real) rows in matches",
        "SELECT COUNT(*) FROM matches WHERE is_sample = 1",
    ),
]


def _scalar(sql: str, db_path: Optional[Path]) -> int:
    return list(fetch_all(sql, db_path=db_path)[0].values())[0] or 0


def status(value: int, needed: int) -> str:
    """OK / THIN / SEED label for a coverage number."""
    if value >= needed:
        return "OK  "
    return "THIN" if value > 0 else "SEED"


def coverage(db_path: Optional[Path] = None) -> list:
    """Return [(question, description, value, needed, status)] for all 25."""
    result = []
    for question, text, sql, needed in CHECKS:
        value = _scalar(sql, db_path)
        result.append((question, text, value, needed, status(value, needed)))
    return result


def main() -> None:
    """Print the report."""
    print("\nREAL-DATA COVERAGE PER QUESTION (OK / THIN / SEED)")
    rows = coverage()
    for question, text, value, needed, label in rows:
        print(f"  {label} {question:<4} {value:>5} / {needed:<3} {text}")
    summary = {
        k: sum(1 for r in rows if r[4].strip() == k) for k in ("OK", "THIN", "SEED")
    }
    print(
        f"\n  OK: {summary['OK']}   THIN: {summary['THIN']}   SEED: {summary['SEED']}"
    )
    print("\nDATA QUALITY")
    for text, sql in QUALITY:
        print(f"  {_scalar(sql, None):>6}  {text}")


if __name__ == "__main__":
    main()
