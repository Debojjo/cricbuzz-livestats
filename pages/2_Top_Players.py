"""Top Players: leaderboards from stored career statistics, with charts."""

import plotly.express as px
import streamlit as st

from api.cricbuzz_client import ApiError, CricbuzzClient
from services import player_service, stats_service
from utils.ui import database_ready, setup_page, site_footer

setup_page("Top Players", "🏆", "Leaderboards from stored career statistics")
if not database_ready():
    st.stop()

left, middle, right = st.columns([3, 2, 1])
category = left.selectbox("Category", list(player_service.CATEGORIES))
format_label = middle.selectbox("Format", list(player_service.FORMATS), index=1)
limit = right.slider("Show", 5, 25, 10)

table = player_service.top_players(category, format_label, limit)
if table.empty:
    st.info(
        "No stored data for this category and format yet. Try another format, or "
        "refresh the leaderboard below."
    )
else:
    value_label = category.split(" (")[0]
    for column, medal, (_, leader) in zip(
        st.columns(3), ("🥇", "🥈", "🥉"), table.head(3).iterrows()
    ):
        value = leader["value"]
        shown = (
            f"{value:,.2f}"
            if isinstance(value, float) and value != int(value)
            else f"{int(value):,}"
        )
        with column.container(border=True):
            st.caption(f"{medal} Rank {leader['rank']}")
            st.markdown(f"**{leader['player']}**")
            st.metric(value_label, shown)
    chart_data = table.sort_values("value")
    figure = px.bar(
        chart_data,
        x="value",
        y="player",
        orientation="h",
        text="value",
        labels={"value": value_label, "player": ""},
        title=f"{category} - {format_label}",
    )
    figure.update_layout(height=max(320, 32 * len(table) + 120))
    st.plotly_chart(figure)
    st.dataframe(table, hide_index=True)
    st.caption(
        f"Based on career statistics stored for {player_service.players_with_stats()} "
        "players (loaded from the Cricbuzz API)."
    )

with st.expander("Refresh this leaderboard from the Cricbuzz API"):
    if category not in player_service.REFRESHABLE:
        st.write("Only 'Most runs' and 'Highest score' can be refreshed from the API.")
    else:
        client = CricbuzzClient()
        quota = stats_service.quota_status(client)
        st.write(
            f"Uses at most 1 API call ({quota['remaining']} left). If this leaderboard "
            "was fetched before, the saved copy is used and nothing is spent."
        )
        if st.button("Refresh"):
            try:
                outcome = player_service.refresh_from_api(
                    client, category, format_label
                )
                st.success(f"Updated {outcome['players']} players.")
            except ApiError as exc:
                st.error(f"Could not refresh: {exc}")

site_footer()
