"""SQL Analytics: the 25 questions, a read-only custom query box, charts, CSV export."""

import plotly.express as px
import streamlit as st

from services import analytics_service
from utils.ui import database_ready, sample_toggle, setup_page, site_footer

setup_page(
    "SQL Analytics",
    "🔍",
    "27 analytical queries on the cricket database, plus a safe query box",
)
include_sample = sample_toggle("analytics_include_sample", default=True)
if not database_ready():
    st.stop()
if include_sample:
    st.sidebar.caption(
        "Results include fictional sample data. Switch it off for real data only."
    )
else:
    st.sidebar.caption(
        "Real API data only. Questions about years of history may be empty."
    )


def show_chart(df, key):
    """Bar chart of one numeric column against the first text column."""
    numeric = [c for c in df.columns if str(df[c].dtype) in ("int64", "float64")]
    labels = [c for c in df.columns if c not in numeric]
    if not numeric or not labels or df.empty:
        st.info("This result has no numeric column to chart.")
        return
    value = st.selectbox("Chart this column", numeric, key=f"{key}_col")
    top = df.head(25)
    st.plotly_chart(
        px.bar(top, x=labels[0], y=value, color_discrete_sequence=["#0b6b3a"]),
        key=f"{key}_chart",
    )


def show_result(result, name, key):
    """Metrics, table, download and chart for one result."""
    df = result["df"]
    c1, c2 = st.columns(2)
    c1.metric("Rows", f"{len(df):,}")
    c2.metric("Time", f"{result['seconds'] * 1000:.0f} ms")
    if result.get("truncated"):
        st.warning(f"Only the first {len(df):,} rows are shown.")
    if df.empty:
        st.info(
            "No rows. With sample data switched off, history questions can be empty."
        )
        return
    st.dataframe(df, hide_index=True)
    st.download_button(
        "Download CSV",
        df.to_csv(index=False),
        file_name=f"{name}.csv",
        mime="text/csv",
        key=f"{key}_csv",
    )
    with st.expander("Chart"):
        show_chart(df, key)


tab_numbered, tab_custom = st.tabs(["The questions", "Your own query"])

with tab_numbered:
    queries = analytics_service.list_queries()
    f_level, f_search = st.columns([2, 3])
    level = f_level.radio(
        "Level", ["All", "Beginner", "Intermediate", "Advanced"], horizontal=True
    )
    word = f_search.text_input(
        "Search the questions", placeholder="e.g. toss, partnership, economy"
    )
    shown = [
        q
        for q in queries
        if (level == "All" or q["level"] == level)
        and word.lower() in q["title"].lower()
    ]
    if not shown:
        st.info("No question matches that filter.")
        st.stop()
    names = {q["label"]: f"Q{q['label']} - {q['level']} - {q['title']}" for q in shown}
    label = st.selectbox("Question", list(names), format_func=names.get)
    with st.expander("About this query", expanded=True):
        st.text(analytics_service.describe(label))
    result = analytics_service.run_numbered(label, include_sample)
    show_result(result, f"q{label}", "numbered")
    col_sql, col_plan = st.columns(2)
    with col_sql.expander("SQL"):
        st.code(analytics_service.get_sql(label), language="sql")
    with col_plan.expander("Execution plan"):
        for step in analytics_service.explain_numbered(label, include_sample):
            st.text(step)

with tab_custom:
    st.caption(
        "Write one SELECT (or WITH ... SELECT). The database is opened read-only, results "
        f"are limited to {analytics_service.MAX_CUSTOM_ROWS:,} rows and queries stop after "
        f"{analytics_service.CUSTOM_TIMEOUT_SECONDS} seconds."
    )
    default_sql = (
        "SELECT p.full_name, c.runs, c.batting_avg\n"
        "FROM player_career_stats AS c\n"
        "JOIN players AS p ON p.player_id = c.player_id\n"
        "WHERE c.format = 'ODI'\n"
        "ORDER BY c.runs DESC\n"
        "LIMIT 10"
    )
    sql = st.text_area("Your SQL", value=default_sql, height=170, key="custom_sql")
    if st.button("Run my query", key="run_custom"):
        try:
            st.session_state["custom_result"] = analytics_service.run_custom(
                sql, include_sample
            )
            st.session_state["custom_error"] = None
        except ValueError as exc:
            st.session_state["custom_result"] = None
            st.session_state["custom_error"] = str(exc)
    if st.session_state.get("custom_error"):
        st.error(st.session_state["custom_error"])
    if st.session_state.get("custom_result") is not None:
        show_result(st.session_state["custom_result"], "custom_query", "custom")
    with st.expander("Tables and columns you can query"):
        for table, columns in analytics_service.schema_overview().items():
            st.markdown(f"**{table}**: " + ", ".join(columns))

site_footer()
