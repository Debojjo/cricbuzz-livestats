"""Cricbuzz LiveStats - home page. Start the app with:  streamlit run main.py"""

import streamlit as st

import config
from services import stats_service
from utils.ui import database_ready, setup_page

setup_page("Cricbuzz LiveStats")
st.caption("Real-time cricket insights and SQL-based analytics")

st.markdown("""
This dashboard combines **live data from the Cricbuzz API** with a **SQL database** to
deliver match updates, player statistics, 25 analytical SQL questions and hands-on
data management.
""")

st.subheader("Where to go")
pages = [
    ("pages/1_Live_Matches.py", "📺 Live Matches", "Live feed, recent results and full scorecards"),
    ("pages/2_Top_Players.py", "🏆 Top Players", "Leaderboards for runs, scores, wickets and more"),
    ("pages/3_SQL_Analytics.py", "🔍 SQL Analytics", "25 questions, a custom query box, CSV export"),
    ("pages/4_CRUD_Operations.py", "🛠️ CRUD Operations", "Create, read, update and delete players and batting entries"),
    ("pages/5_Settings.py", "⚙️ Settings", "Data volume, API quota, known data limits"),
]  # fmt: skip
for target, label, text in pages:
    try:
        st.page_link(target, label=label, help=text)
    except Exception:  # navigation links are a convenience, never a reason to fail
        st.markdown(f"- **{label}**: {text}")

if database_ready():
    st.subheader("What is in the database")
    overview = stats_service.data_overview()
    columns = st.columns(len(overview[:5]))
    for column, row in zip(columns, overview[:5]):
        column.metric(
            row["name"], f"{row['real']:,}", help=f"plus {row['sample']:,} sample rows"
        )
    span = stats_service.date_range()
    if span["first"]:
        st.caption(f"Real matches span {span['first']} to {span['last']}.")
    sample = sum(r["sample"] for r in overview)
    if sample:
        st.info(
            "**Real vs sample data.** The free API plan returns only a few days of match "
            "history, so questions about years of history use **clearly fictional sample "
            "data** ('Sample XI ...' teams, generated ball by ball). Every such row is "
            "flagged, and the Analytics page lets you switch it off."
        )

st.subheader("How it works")
st.markdown("""
1. **Data**: the Cricbuzz API (via RapidAPI) is fetched once, cached on disk and loaded
   into SQLite. A budget guard protects the 200-requests-a-month quota.
2. **Analytics**: 25 SQL questions (plus two companions) run on the database.
3. **Live pages**: only user-requested live data touches the API.
4. **CRUD**: manual and sample rows can be edited; real API rows are protected.
""")

st.subheader("Built with")
st.table(
    {
        "Layer": [
            "Language",
            "Web app",
            "Database",
            "Data access",
            "Charts",
            "Testing",
        ],
        "Tool": [
            "Python",
            "Streamlit",
            "SQLite",
            "requests, pandas",
            "Plotly",
            "pytest",
        ],
    }
)

with st.expander("Project folder structure"):
    st.code(
        """cricbuzz-livestats/
├── main.py                 home page (this page)
├── pages/                  Live Matches, Top Players, SQL Analytics, CRUD, Settings
├── api/                    API client (cache, budget guard), parsers, endpoints
├── services/               logic behind each page (no SQL in the pages)
├── database/               schema, views, repositories, init script
├── sql/queries/            the 25 analytics queries, one file each
├── data/                   ingestion, sample data, raw API cache
├── utils/                  db_connection, validators, logger, UI helpers
└── tests/                  automated tests and saved API samples""",
        language="text",
    )
    st.caption("Full setup and documentation: see README.md in the repository.")

st.caption(f"Database file: {config.DB_PATH.name}")
