"""Small Streamlit helpers shared by every page (the only module besides pages
that imports streamlit)."""

import streamlit as st

import config


def setup_page(title: str, icon: str = "🏏") -> None:
    """Page title, browser tab and wide layout. Must be the first Streamlit call."""
    st.set_page_config(
        page_title=f"{title} - Cricbuzz LiveStats", page_icon=icon, layout="wide"
    )
    st.title(f"{icon} {title}")


def database_ready() -> bool:
    """True when the database file exists; otherwise shows how to create it."""
    if config.DB_PATH.exists():
        return True
    st.error("The database was not found.")
    st.markdown(
        "Create it with:\n\n"
        "```\npython -m database.init_db\npython -m data.ingest --fixtures\n```\n"
        "See the README for the full setup."
    )
    return False


def sample_toggle(key: str, default: bool = False) -> bool:
    """Sidebar switch: include the fictional sample rows in the results?"""
    return st.sidebar.toggle(
        "Include sample (fictional) data",
        value=default,
        key=key,
        help=(
            "Sample rows are generated, not real: teams called 'Sample XI ...', plus a "
            "few manually entered stadiums. Switch off to see real API data only."
        ),
    )


def show_validation_errors(errors: dict) -> None:
    """One red line per invalid field."""
    for field, message in errors.items():
        st.error(f"**{field.replace('_', ' ').title()}** {message}")
