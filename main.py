"""Cricbuzz LiveStats - home page. Start the app with:  streamlit run main.py"""

import streamlit as st

import config
from services import analytics_service, match_service, player_service, stats_service
from utils.ui import configure_page, database_ready, hero, site_footer

configure_page("Cricbuzz LiveStats")
hero(
    "Cricbuzz LiveStats",
    "Live scores, player analytics and 27 SQL-driven insights, in one place.",
    ["Live API data", "SQL analytics", "Safe data management"],
)

if not database_ready():
    st.stop()

overview = {row["name"]: row for row in stats_service.data_overview()}
quota = stats_service.quota_status()
kpis = [
    ("Real matches", f"{overview['Matches']['real']:,}"),
    ("Players", f"{overview['Players']['real'] + overview['Players']['sample']:,}"),
    ("Analytics queries", f"{len(analytics_service.list_queries())}"),
    ("Career-stat rows", f"{overview['Career-stat rows']['real']:,}"),
    ("API requests left", f"{quota['remaining']}"),
]
for column, (label, value) in zip(st.columns(len(kpis)), kpis):
    with column.container(border=True):
        st.metric(label, value)

st.subheader("Explore")
features = [
    ("📺", "Live Matches", "Live feed on demand, saved results and full scorecards", "pages/1_Live_Matches.py"),
    ("🏆", "Top Players", "Leaderboards for runs, scores, wickets and averages", "pages/2_Top_Players.py"),
    ("🔍", "SQL Analytics", "27 analytical queries, charts, CSV export and a safe query box", "pages/3_SQL_Analytics.py"),
    ("🛠️", "CRUD Operations", "Create, edit and delete players and batting entries", "pages/4_CRUD_Operations.py"),
    ("⚙️", "Settings", "API quota, data volume and known data limits", "pages/5_Settings.py"),
]  # fmt: skip
for index, (icon, name, text, target) in enumerate(features):
    if index % 3 == 0:
        cards = st.columns(3)
    with cards[index % 3].container(border=True):
        st.markdown(f"#### {icon} {name}")
        st.caption(text)
        try:
            st.page_link(target, label=f"Open {name}")
        except Exception:  # navigation links are a convenience, never a reason to fail
            st.write("")

left, right = st.columns([3, 2])
with left:
    st.subheader("Latest results")
    results = match_service.recent_results(limit=5)
    if not results:
        st.info("No results stored yet.")
    for row in results:
        with st.container(border=True):
            st.markdown(f"**{row['team1_name']} v {row['team2_name']}**")
            st.markdown(row["status"] or "")
            venue = ", ".join(x for x in (row["venue_name"], row["venue_city"]) if x)
            st.markdown(
                f"<span class='muted'>{row['match_date']} · {row['format']} · {venue}</span>",
                unsafe_allow_html=True,
            )
with right:
    st.subheader("Top ODI run scorers")
    table = player_service.top_players("Most runs", "ODI", 5)
    if table.empty:
        st.info("No ODI career statistics stored yet.")
    else:
        st.dataframe(
            table[["rank", "player", "value"]].rename(columns={"value": "runs"}),
            hide_index=True,
        )

with st.expander("About this project"):
    st.markdown("""
**How it works.** The Cricbuzz API (via RapidAPI) is fetched once, cached on disk and
loaded into SQLite. A budget guard protects the 200-requests-a-month quota. Pages never
contain SQL: they call services. Live data is fetched only when you press a button.

**Real vs sample data.** The free API plan returns only a few days of match history, so
questions about years of history use clearly **fictional sample data** ('Sample XI ...'
teams, generated ball by ball). Every such row is flagged, and the SQL Analytics page can
hide it.

**Built with** Python · Streamlit · SQLite · pandas · Plotly · pytest.
""")
    if sum(r["sample"] for r in overview.values()):
        st.info(
            "**Real vs sample data.** Sample rows are fictional and flagged. "
            "Switch them off on the SQL Analytics page to see real data only."
        )
    st.code(
        """main.py  pages/  api/  services/  database/  sql/queries/  data/  utils/  tests/""",
        language="text",
    )
    st.caption(
        f"Full setup and documentation: README.md · database file: {config.DB_PATH.name}"
    )

site_footer()
