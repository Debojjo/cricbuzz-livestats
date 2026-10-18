"""Settings: data volume, API quota and the known limits of the data."""

import sys

import pandas as pd
import streamlit as st

import config
from services import stats_service
from utils.ui import database_ready, setup_page

setup_page("Settings", "⚙️")
if not database_ready():
    st.stop()

st.subheader("Cricbuzz API quota")
quota = stats_service.quota_status()
st.progress(
    min(quota["used"] / quota["limit"], 1.0),
    text=f"{quota['used']} of {quota['limit']} requests used this month",
)
c1, c2, c3 = st.columns(3)
c1.metric("Remaining", quota["remaining"])
c2.metric(
    "Safety reserve",
    quota["reserve"],
    help="The app refuses new requests below this level.",
)
c3.metric(
    "Saved responses",
    stats_service.cache_summary()["files"],
    help="Cached copies cost no requests.",
)
if quota["remaining"] <= quota["reserve"]:
    st.warning("Only the safety reserve is left, so live requests are switched off.")

st.subheader("Data in the database")
overview = pd.DataFrame(stats_service.data_overview()).rename(
    columns={"name": "Table", "real": "Real (API)", "sample": "Sample / manual"}
)
st.dataframe(overview, hide_index=True)

st.subheader("Known data limitations")
st.markdown("""
- **History is short.** The free API plan returns only recent matches, so multi-year questions use clearly flagged fictional sample data.
- **Roles are often unknown.** Players seen only in scorecards have no role, and show as *Unknown* in Q6.
- **Series details are thin.** Match type and planned match count are not in the API archive; host country is read from the series name when it states one.
- **Stadium capacities** for a few famous grounds are approximate manual figures.
- **Fielding** is derived from dismissal text (catches and stumpings); run-outs are not counted.
""")

st.subheader("About")
st.write(
    {
        "Database": str(config.DB_PATH.name),
        "Python": sys.version.split()[0],
        "Streamlit": st.__version__,
        "Real-edit protection": (
            "off" if not config.CRUD_ALLOW_EDIT_REAL else "ON (real rows editable)"
        ),
    }
)
