"""Parser tests, run against your real saved API responses."""

import json

import pytest

from api import parsers as P
from config import BASE_DIR

FX = BASE_DIR / "tests" / "fixtures"
IRE_USA = [
    {"team_id": 27, "team_name": "Ireland", "short_name": "IRE"},
    {"team_id": 15, "team_name": "United States of America", "short_name": "USA"},
]


def load(name):
    return json.loads((FX / name).read_text(encoding="utf-8"))


# ---------------------------------------------------------------- helpers ----
def test_to_int_handles_api_quirks():
    assert P.to_int("11,600") == 11600
    assert P.to_int("199*") == 199
    assert P.to_int("") is None
    assert P.to_int("-") is None
    assert P.to_int(None) is None


def test_overs_to_balls_is_not_decimal_arithmetic():
    assert P.overs_to_balls("3.5") == 23
    assert P.overs_to_balls("4") == 24
    assert P.overs_to_balls("19.6") == 120
    assert P.overs_to_balls("") is None


def test_epoch_ms_uses_venue_timezone():
    # 2026-10-11 22:00 UTC is already 12 Oct in +05:30
    assert P.epoch_ms_to_date("1791756000000") == "2026-10-11"
    assert P.epoch_ms_to_date("1791756000000", "+05:30") == "2026-10-12"


def test_lower_keys_is_recursive():
    assert P.lower_keys({"A": [{"B": 1}]}) == {"a": [{"b": 1}]}


# ---------------------------------------------------------------- results ----
TEAMS = [
    {"team_id": 1, "team_name": "KwaZulu-Natal Inland Tuskers", "short_name": "KZNIN"},
    {"team_id": 2, "team_name": "Knights", "short_name": "KNG"},
]


@pytest.mark.parametrize(
    "status, winner, vtype, margin",
    [
        ("KwaZulu - Natal Inland - Tuskers won by 7 wkts", 1, "wickets", 7),
        ("Knights won by an innings and 155 runs", 2, "innings", 155),
        ("Knights won by 37 runs (DLS method)", 2, "runs", 37),
        ("Match drawn", None, "draw", None),
        ("Match tied (Knights won the Super Over)", None, "tie", None),
        ("No result due to rain", None, "no result", None),
        ("Match abandoned due to rain (with toss)", None, "abandoned", None),
        ("Knights are deemed to have forfeited", None, "forfeit", None),
    ],
)
def test_parse_result(status, winner, vtype, margin):
    result = parsers_result(status)
    assert result == {
        "winner_id": winner,
        "victory_type": vtype,
        "victory_margin": margin,
    }


def parsers_result(status):
    return P.parse_result(status, "Complete", TEAMS)


def test_winner_falls_back_to_state_title():
    result = P.parse_result("Their side won by 4 wkts", "KNG Won", TEAMS)
    assert result["winner_id"] == 2


def test_parse_toss():
    teams = [
        {"team_id": 2, "team_name": "India"},
        {"team_id": 10, "team_name": "West Indies"},
    ]
    assert P.parse_toss("West Indies opt to bowl", teams) == {
        "toss_winner_id": 10,
        "toss_decision": "bowl",
    }
    assert P.parse_toss("India won the toss and elected to bat", teams) == {
        "toss_winner_id": 2,
        "toss_decision": "bat",
    }
    assert P.parse_toss("", teams) == {"toss_winner_id": None, "toss_decision": None}
    assert P.parse_toss("Mystery wording", teams)["toss_decision"] is None


# ------------------------------------------------------------- real files ----
def test_recent_matches_fixture():
    item = P.parse_recent_matches(load("matches_recent.json"))[0]
    match = item["match"]
    assert match["match_id"] == 151587
    assert match["format"] == "T20"
    assert match["match_category"] == "international"
    assert (match["winner_id"], match["victory_type"], match["victory_margin"]) == (
        2,
        "runs",
        14,
    )
    assert item["venue"]["venue_name"] == "Holkar Stadium"
    assert item["teams"][0]["country"] == "India"


def test_match_info_toss_and_empty_toss():
    info = P.parse_match_info(load("matches_get-info_151587.json"))
    assert (info["toss_winner_id"], info["toss_decision"]) == (10, "bowl")
    assert info["winner_id"] == 2
    old = P.parse_match_info(load("matches_get-info_41881.json"))
    assert old["toss_winner_id"] is None  # empty toss text must not crash
    assert old["winner_id"] == 223
    assert old["venue"]["country"] == "United Arab Emirates"


def test_player_info_fixture():
    player = P.parse_player_info(load("players_get-info_6635.json"))
    assert player["player_id"] == 6635
    assert player["full_name"] == "Usman Tariq Khawaja"
    assert player["date_of_birth"] == "1986-12-18"
    assert player["playing_role"] == "Batsman"
    assert player["birth_place"] == "Islamabad, Pakistan"


def test_career_batting_matches_records_leaderboard():
    rows = {
        r["format"]: r
        for r in P.parse_career_batting(load("players_get-batting_8733.json"), 8733)
    }
    assert set(rows) == {"TEST", "ODI", "T20"}  # the IPL column is dropped
    assert rows["T20"]["matches_played"] == 72
    assert rows["T20"]["runs"] == 2265
    assert rows["T20"]["strike_rate"] == pytest.approx(139.13)
    assert rows["TEST"]["centuries"] == 12
    # cross-check against a different endpoint (stats/get-records)
    records = {
        r["player_id"]: r for r in P.parse_records(load("stats_get-records_t20.json"))
    }
    assert records[8733]["stats"]["R"] == "2265"


def test_teams_list_fixture():
    teams = P.parse_teams_list(load("teams_list.json"))
    by_id = {t["team_id"]: t for t in teams}
    assert len(teams) == 38
    assert by_id[2]["team_type"] == "international"
    assert by_id[71]["team_type"] == "associate"
    assert by_id[27]["short_name"] == "IRE"


def test_venue_info_fixture():
    venue = P.parse_venue_info(load("venues_get-info_basin-reserve.json"), 45)
    assert venue["capacity"] == 11600
    assert venue["country"] == "New Zealand"


# -------------------------------------------------------------- scorecard ----
@pytest.fixture(scope="module")
def scorecard():
    return P.parse_scorecard(load("scorecard_v2_sample.json"), 40381, IRE_USA)


def test_scorecard_counts(scorecard):
    assert len(scorecard["batting"]) == 20  # 11 + 9 who batted (2 did not bat)
    assert len(scorecard["bowling"]) == 12
    assert len(scorecard["partnerships"]) == 18


def test_scorecard_runs_add_up(scorecard):
    for innings, total in ((1, 150), (2, 141)):
        pairs = [p for p in scorecard["partnerships"] if p["innings_no"] == innings]
        assert sum(p["runs"] for p in pairs) == total


def test_bowling_balls_come_from_overs_not_the_api_balls_field(scorecard):
    spell = next(
        b
        for b in scorecard["bowling"]
        if b["player_id"] == 9748 and b["innings_no"] == 1
    )
    assert spell["overs"] == 3.5
    assert spell["balls"] == 23  # the API says 35, which is overs x 10
    assert spell["runs_conceded"] * 6 / spell["balls"] == pytest.approx(8.61, abs=0.01)


def test_batting_positions_and_not_outs(scorecard):
    first = [b for b in scorecard["batting"] if b["innings_no"] == 1]
    assert [b["batting_position"] for b in first] == list(range(1, 12))
    assert first[0]["player_id"] == 1114  # Stirling opened
    not_out = {b["player_id"] for b in scorecard["batting"] if b["is_not_out"]}
    assert not_out == {11124, 15475, 9748}


def test_bowling_side_is_the_opposite_team(scorecard):
    spell = next(b for b in scorecard["bowling"] if b["innings_no"] == 1)
    assert spell["team_id"] == 15  # USA bowled while Ireland batted


def test_fielding_credits_catches_only(scorecard):
    assert sum(f["catches"] for f in scorecard["fielding"]) == 10
    assert sum(f["stumpings"] for f in scorecard["fielding"]) == 0
    assert scorecard["unresolved_fielders"] == []
    credited = {f["player_id"]: f["catches"] for f in scorecard["fielding"]}
    assert credited[10699] == 2  # Marty Kain took two catches in Ireland's innings
    assert credited[18143] == 1  # Campher: 'c and b' in the USA innings


@pytest.mark.parametrize(
    "text, expected",
    [
        ("c Smith b Jones", ("catch", "Smith")),
        ("c and b Jones", ("catch", "Jones")),
        ("c & b Jones", ("catch", "Jones")),
        ("st Rock b Singh", ("stumping", "Rock")),
        ("run out (Monank Patel)", None),
        ("lbw b Nisarg Patel", None),
        ("b Netravalkar", None),
        ("not out", None),
        ("", None),
    ],
)
def test_parse_dismissal(text, expected):
    assert P.parse_dismissal(text) == expected


def test_bad_scorecards_raise_parse_error():
    with pytest.raises(P.ParseError):
        P.parse_scorecard({"scorecard": []}, 1, IRE_USA)
    bad = load("scorecard_v2_sample.json")
    with pytest.raises(P.ParseError):
        P.parse_scorecard(
            bad,
            1,
            [
                {"team_id": 1, "team_name": "A", "short_name": "A"},
                {"team_id": 2, "team_name": "B", "short_name": "B"},
            ],
        )


# ------------------------------------------------- fielder name matching ----
ROSTER = [("Pichet Jirapatananukul", 5), ("Aslam Khan", 6), ("Imran Khan", 7)]


@pytest.mark.parametrize(
    "name, expected",
    [
        ("Pichet Jirapatananukul", 5),  # exact
        ("P Jirapatananukul", 5),  # initial + surname
        ("Aslam Khan", 6),
        ("Khan", None),  # ambiguous: two Khans
        ("Nobody Known", None),
    ],
)
def test_resolve_fielder_names(name, expected):
    assert P._resolve_name(name, ROSTER) == expected


def test_substitute_fielders_are_skipped_not_reported():
    payload = {
        "scorecard": [
            {
                "inningsid": 1,
                "batteamsname": "IRE",
                "batsman": [
                    {
                        "id": 1,
                        "name": "A Bat",
                        "runs": 5,
                        "balls": 4,
                        "outdec": "c (sub)Ravi Bishnoi b Zed Bowl",
                        "strkrate": "125",
                    },
                ],
                "bowler": [
                    {
                        "id": 2,
                        "name": "Zed Bowl",
                        "overs": "1",
                        "runs": 5,
                        "wickets": 1,
                    },
                ],
                "partnership": {"partnership": []},
            }
        ]
    }
    parsed = P.parse_scorecard(payload, 1, IRE_USA)
    assert parsed["fielding"] == []
    assert parsed["unresolved_fielders"] == []


# ------------------------------------------------------------ team squads ----
def test_squad_fixture_gets_roles_from_section_headers():
    players = P.parse_team_players(load("teams_v1_players_2.json"), "India")
    assert len(players) == 37
    by_id = {p["player_id"]: p for p in players}
    assert by_id[576]["playing_role"] == "Batsman"
    assert by_id[9647]["playing_role"] == "Allrounder"
    assert by_id[10744]["playing_role"] == "WK-Batsman"
    assert by_id[9311]["playing_role"] == "Bowler"
    assert by_id[9311]["bowling_style"] == "Right-arm fast"
    assert by_id[10744]["bowling_style"] is None  # keepers list no bowling style
    assert {p["country"] for p in players} == {"India"}
    assert all(p["player_id"] and p["full_name"] for p in players)


def test_squad_headers_are_not_returned_as_players():
    payload = {"player": [{"name": "BATSMEN"}, {"id": "1", "name": "A"}, {"name": "X"}]}
    players = P.parse_team_players(payload)
    assert [p["player_id"] for p in players] == [1]
