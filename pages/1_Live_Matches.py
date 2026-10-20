"""Live Matches: live feed (on demand), recent results and full scorecards."""

import streamlit as st

from api.cricbuzz_client import ApiError, CricbuzzClient
from services import match_service, stats_service
from utils.ui import database_ready, sample_toggle, setup_page, site_footer

setup_page(
    "Live Matches", "📺", "Live feed on demand, plus saved results with full scorecards"
)
include_sample = sample_toggle("live_include_sample", default=False)
if not database_ready():
    st.stop()

tab_live, tab_recent = st.tabs(["Live now (API)", "Recent results (saved)"])

# ----------------------------------------------------------------- live feed ----
with tab_live:
    client = CricbuzzClient()
    quota = stats_service.quota_status(client)
    st.caption(
        f"The live feed uses the Cricbuzz API. Requests left this month: "
        f"**{quota['remaining']}** of {quota['limit']}. A fetched feed is saved for "
        f"15 minutes, so repeated clicks cost nothing."
    )
    if st.button("Fetch live matches"):
        try:
            st.session_state["live_items"] = match_service.live_matches(client)
        except ApiError as exc:
            st.session_state["live_items"] = None
            st.error(f"Could not load the live feed: {exc}")
    items = st.session_state.get("live_items")
    if items is not None and not items:
        st.info("No matches are being played right now.")
    if items:
        labels = [match_service.describe_live(i) for i in items]
        choice = st.selectbox(
            "Match", range(len(items)), format_func=labels.__getitem__
        )
        item = items[choice]
        match = item["match"]
        st.subheader(labels[choice])
        c1, c2, c3 = st.columns(3)
        c1.metric("Format", match["format"])
        c2.metric("State", match["state"] or "-")
        c3.metric("Venue", (item["venue"] or {}).get("venue_name") or "-")
        if st.button("Load scorecard (1 API call)"):
            try:
                card = match_service.live_scorecard(client, item)
                st.dataframe(card["batting"], hide_index=True)
                st.dataframe(card["bowling"], hide_index=True)
            except ApiError as exc:
                st.error(f"Could not load the scorecard: {exc}")
            except Exception as exc:  # live scorecards can have unexpected shapes
                st.warning(f"The scorecard could not be read ({exc}).")

# ------------------------------------------------------------ saved results ----
with tab_recent:
    results = match_service.recent_results(include_sample=include_sample)
    if not results:
        st.info("No completed matches stored yet.")
    else:

        def pick(index):
            st.session_state["recent_pick"] = index

        st.markdown("##### Latest results")
        for start in range(0, min(len(results), 6), 3):
            for offset, column in enumerate(st.columns(3)):
                index = start + offset
                if index >= len(results):
                    break
                card = results[index]
                with column.container(border=True):
                    st.markdown(f"**{card['team1_name']} v {card['team2_name']}**")
                    st.caption(f"{card['match_date']} · {card['format']}")
                    st.markdown(card["status"] or "")
                    st.button(
                        "View scorecard",
                        key=f"card_{index}",
                        on_click=pick,
                        args=(index,),
                    )

        labels = [
            f"{r['match_date']} - {r['team1_name']} v {r['team2_name']} "
            f"({r['match_desc'] or r['format']})"
            for r in results
        ]
        choice = st.selectbox(
            "Result",
            range(len(results)),
            format_func=labels.__getitem__,
            key="recent_pick",
        )
        row = results[choice]
        st.subheader(f"{row['team1_name']} v {row['team2_name']}")
        st.write(f"**{row['status']}**")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Format", row["format"])
        c2.metric("Date", row["match_date"] or "-")
        c3.metric("Winner", row["winner_name"] or "No winner")
        c4.metric(
            "Venue",
            ", ".join(x for x in (row["venue_name"], row["venue_city"]) if x) or "-",
        )
        card = match_service.stored_scorecard(row["match_id"], include_sample)
        if card["batting"].empty:
            st.info(
                "No scorecard is stored for this match (scorecards were loaded for a "
                "limited number of matches to protect the API quota)."
            )
        else:
            st.markdown("**Batting**")
            st.dataframe(card["batting"], hide_index=True)
            st.markdown("**Bowling**")
            st.dataframe(card["bowling"], hide_index=True)
            with st.expander("Partnerships"):
                st.dataframe(card["partnerships"], hide_index=True)

site_footer()
