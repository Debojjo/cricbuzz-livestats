"""Cricbuzz LiveStats - entry point. Start the app with:  streamlit run main.py

main.py only describes the navigation; every page is its own script.
"""

import streamlit as st

PAGES = [
    st.Page("views/home.py", title="Home", icon="🏠", default=True),
    st.Page("pages/1_Live_Matches.py", title="Live Matches", icon="📺"),
    st.Page("pages/2_Top_Players.py", title="Top Players", icon="🏆"),
    st.Page("pages/3_SQL_Analytics.py", title="SQL Analytics", icon="🔍"),
    st.Page("pages/4_CRUD_Operations.py", title="CRUD Operations", icon="🛠️"),
    st.Page("pages/5_Settings.py", title="Settings", icon="⚙️"),
]

st.navigation(PAGES).run()
