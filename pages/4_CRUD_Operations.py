"""CRUD Operations: manage players and batting entries through forms."""

from datetime import date

import pandas as pd
import streamlit as st

from services import crud_service as crud
from services import match_service
from utils.ui import database_ready, setup_page, show_validation_errors, site_footer
from utils.validators import BATTING_STYLES, ROLES, ValidationError

setup_page("CRUD Operations", "🛠️", "Manage players and batting entries safely")
if not database_ready():
    st.stop()

if "crud_flash" in st.session_state:
    st.success(st.session_state.pop("crud_flash"))

st.caption(
    "Create always works and flags the new row as manual. Update and Delete work on "
    "manual and sample rows only: real Cricbuzz rows are protected."
)


def table(rows):
    """Rows as a DataFrame with blanks instead of the word None."""
    return pd.DataFrame(rows).fillna("")


def run_action(action, success_message):
    """Run a CRUD call and show friendly errors; on success remember a message."""
    try:
        outcome = action()
    except ValidationError as exc:
        show_validation_errors(exc.errors)
        return None
    except crud.CrudError as exc:
        st.error(str(exc))
        return None
    st.session_state["crud_flash"] = success_message
    st.rerun()
    return outcome


tab_players, tab_batting = st.tabs(["Players", "Batting entries"])

# ------------------------------------------------------------------ players ----
with tab_players:
    st.subheader("Find players")
    f1, f2, f3 = st.columns([3, 2, 1])
    search = f1.text_input("Name contains", key="player_search")
    source_label = f2.selectbox(
        "Source", ["All", "Cricbuzz API", "Manual / sample"], key="player_source"
    )
    page = f3.number_input("Page", min_value=1, value=1, key="player_page")
    source = {"All": "all", "Cricbuzz API": "api", "Manual / sample": "manual"}[
        source_label
    ]
    found = crud.list_players(
        search=search or None, source=source, limit=20, offset=(page - 1) * 20
    )
    st.caption(f"{found['total']:,} players match. Showing page {page}.")
    st.dataframe(table(found["rows"]), hide_index=True, column_order=[
        "player_id", "full_name", "country", "playing_role", "batting_style", "bowling_style", "source",
    ])  # fmt: skip

    st.subheader("Add a player")
    with st.form("add_player", clear_on_submit=True):
        a1, a2 = st.columns(2)
        full_name = a1.text_input("Full name *", key="new_player_name")
        display_name = a2.text_input("Short name")
        country = a1.text_input("Country")
        role = a2.selectbox("Playing role", [""] + list(ROLES))
        batting = a1.selectbox("Batting style", [""] + list(BATTING_STYLES))
        bowling = a2.text_input("Bowling style")
        born = a1.date_input(
            "Date of birth",
            value=None,
            min_value=date(1940, 1, 1),
            max_value=date.today(),
        )
        birth_place = a2.text_input("Birth place")
        if st.form_submit_button("Add player"):
            data = {
                "full_name": full_name, "display_name": display_name, "country": country,
                "playing_role": role, "batting_style": batting, "bowling_style": bowling,
                "date_of_birth": born, "birth_place": birth_place,
            }  # fmt: skip
            run_action(lambda: crud.create_player(data), "Player added.")

    st.subheader("Edit or delete a player")
    pick = st.text_input("Search for the player to change", key="edit_search")
    candidates = crud.list_players(search=pick or None, limit=30)["rows"]
    if candidates:
        labels = {
            r["player_id"]: f"{r['full_name']} ({r['source']}, id {r['player_id']})"
            for r in candidates
        }
        chosen = st.selectbox(
            "Player", list(labels), format_func=labels.get, key="edit_pick"
        )
        current = crud.get_player(chosen)
        with st.form("edit_player"):
            e1, e2 = st.columns(2)
            new_role = e1.selectbox(
                "Playing role", [""] + list(ROLES),
                index=([""] + list(ROLES)).index(current["playing_role"]) if current["playing_role"] in ROLES else 0,
            )  # fmt: skip
            new_country = e2.text_input("Country", value=current["country"] or "")
            new_name = e1.text_input("Full name", value=current["full_name"])
            if st.form_submit_button("Save changes"):
                changes = {
                    "full_name": new_name,
                    "playing_role": new_role,
                    "country": new_country,
                }
                run_action(
                    lambda: crud.update_player(chosen, changes), "Player updated."
                )
        confirm = st.checkbox(
            "I understand this deletes the player", key="confirm_delete_player"
        )
        if st.button("Delete player", disabled=not confirm):
            run_action(lambda: crud.delete_player(chosen), "Player deleted.")
    else:
        st.info("No player matches that search.")

# ------------------------------------------------------------ batting entries ----
with tab_batting:
    st.subheader("Find entries")
    matches = match_service.match_choices(limit=100)
    if not matches:
        st.info("There are no matches yet.")
        st.stop()
    labels = {m["match_id"]: m["label"] for m in matches}
    match_id = st.selectbox(
        "Match", list(labels), format_func=labels.get, key="batting_match"
    )
    entries = crud.list_batting(match_id=match_id, limit=100)
    st.caption(f"{entries['total']} batting entries in this match.")
    st.dataframe(table(entries["rows"]), hide_index=True, column_order=[
        "performance_id", "innings_no", "team_name", "batting_position", "player_name",
        "runs", "balls_faced", "fours", "sixes", "source",
    ])  # fmt: skip

    st.subheader("Add a batting entry")
    chosen_match = next(m for m in matches if m["match_id"] == match_id)
    team_labels = {
        chosen_match["team1_id"]: chosen_match["team1_name"],
        chosen_match["team2_id"]: chosen_match["team2_name"],
    }
    who = st.text_input("Search for the batsman", key="batter_search")
    players = crud.list_players(search=who or None, limit=30)["rows"]
    with st.form("add_batting", clear_on_submit=True):
        b1, b2, b3 = st.columns(3)
        player_id = b1.selectbox(
            "Batsman", [p["player_id"] for p in players],
            format_func=lambda i: next(p["full_name"] for p in players if p["player_id"] == i),
        ) if players else None  # fmt: skip
        team_id = b2.selectbox("Team", list(team_labels), format_func=team_labels.get)
        innings = b3.number_input("Innings", 1, 4, 1)
        position = b1.number_input("Batting position (0 = unknown)", 0, 11, 0)
        runs = b2.number_input("Runs", 0, 500, 0)
        balls = b3.number_input("Balls faced", 0, 600, 0)
        fours = b1.number_input("Fours", 0, 100, 0)
        sixes = b2.number_input("Sixes", 0, 100, 0)
        not_out = b3.checkbox("Not out")
        dismissal = st.text_input("Dismissal text (optional)")
        if st.form_submit_button("Add entry"):
            data = {
                "match_id": match_id, "innings_no": innings, "player_id": player_id,
                "team_id": team_id, "batting_position": position or None, "runs": runs,
                "balls_faced": balls, "fours": fours, "sixes": sixes,
                "is_not_out": 1 if not_out else 0, "out_desc": dismissal,
            }  # fmt: skip
            run_action(lambda: crud.create_batting(data), "Batting entry added.")

    st.subheader("Edit or delete an entry")
    if entries["rows"]:
        options = {
            r[
                "performance_id"
            ]: f"#{r['performance_id']} {r['player_name']} - {r['runs']} runs ({r['source']})"
            for r in entries["rows"]
        }
        entry_id = st.selectbox(
            "Entry", list(options), format_func=options.get, key="entry_pick"
        )
        current_entry = crud.get_batting(entry_id)
        with st.form("edit_batting"):
            n1, n2, n3 = st.columns(3)
            new_runs = n1.number_input("Runs", 0, 500, int(current_entry["runs"]))
            new_balls = n2.number_input(
                "Balls faced", 0, 600, int(current_entry["balls_faced"] or 0)
            )
            new_fours = n3.number_input(
                "Fours", 0, 100, int(current_entry["fours"] or 0)
            )
            if st.form_submit_button("Save entry"):
                changes = {
                    "runs": new_runs,
                    "balls_faced": new_balls,
                    "fours": new_fours,
                }
                run_action(
                    lambda: crud.update_batting(entry_id, changes), "Entry updated."
                )
        confirm_entry = st.checkbox(
            "I understand this deletes the entry", key="confirm_delete_entry"
        )
        if st.button("Delete entry", disabled=not confirm_entry):
            run_action(lambda: crud.delete_batting(entry_id), "Entry deleted.")

site_footer()
