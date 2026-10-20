"""Small Streamlit helpers shared by every page (the only module besides pages
that imports streamlit)."""

import streamlit as st

import config

_CSS = """
<style>
.block-container {padding-top: 2.2rem; max-width: 1200px;}
footer {visibility: hidden;}
.hero {background: linear-gradient(120deg, #0b6b3a 0%, #1b9a58 60%, #2fbf71 100%);
       color: #fff; padding: 2.4rem 2.2rem; border-radius: 18px; margin-bottom: 1.4rem;}
.hero h1 {color: #fff; margin: 0; font-size: 2.6rem; letter-spacing: -0.5px;}
.hero p {color: #e8f7ee; margin: 0.5rem 0 0.9rem 0; font-size: 1.15rem;}
.pill {display: inline-block; padding: 0.2rem 0.75rem; border-radius: 999px;
       background: rgba(255,255,255,0.18); color: #fff; font-size: 0.8rem;
       font-weight: 600; margin-right: 0.4rem;}
.muted {color: #6b7a72; font-size: 0.85rem;}
</style>
"""


def configure_page(title: str, icon: str = "🏏") -> None:
    """Browser tab, wide layout and the site-wide look (first Streamlit call)."""
    st.set_page_config(
        page_title=f"{title} - Cricbuzz LiveStats", page_icon=icon, layout="wide"
    )
    st.markdown(_CSS, unsafe_allow_html=True)


def setup_page(title: str, icon: str = "🏏", subtitle: str = "") -> None:
    """Configure the page and show its heading (and a one-line subtitle)."""
    configure_page(title, icon)
    st.title(f"{icon} {title}")
    if subtitle:
        st.caption(subtitle)


def hero(title: str, tagline: str, pills: list) -> None:
    """The large green banner at the top of the home page."""
    tags = "".join(f'<span class="pill">{p}</span>' for p in pills)
    st.markdown(
        f'<div class="hero"><h1>🏏 {title}</h1><p>{tagline}</p>{tags}</div>',
        unsafe_allow_html=True,
    )


def site_footer() -> None:
    """One quiet line at the bottom of every page."""
    st.divider()
    st.caption(
        "Cricbuzz LiveStats · data from the Cricbuzz API via RapidAPI · "
        "fictional sample data is always flagged"
    )


def database_ready() -> bool:
    """True when the database file exists; otherwise shows how to create it.

    On a fresh host with AUTO_SETUP=1 the database is created here on first use.
    """
    if not config.DB_PATH.exists() and config.AUTO_SETUP:
        from utils import bootstrap

        with st.spinner("First start: preparing the database..."):
            bootstrap.ensure_database()
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
