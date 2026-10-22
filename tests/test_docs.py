"""The documentation must stay in step with the code."""

import re

from config import BASE_DIR
from services import analytics_service

DOCS = BASE_DIR / "documentation"


def read(path):
    return (BASE_DIR / path).read_text(encoding="utf-8")


def test_queries_document_lists_every_query():
    text = (DOCS / "QUERIES.md").read_text(encoding="utf-8")
    for query in analytics_service.list_queries():
        assert f"### Q{query['label']} -" in text, query["label"]


def test_readme_has_the_required_sections():
    text = read("README.md")
    for heading in (
        "## Features",
        "## Quick start",
        "### API key configuration",
        "## Project structure",
        "## Testing",
        "## Deployment",
        "## Known limitations",
        "## Future improvements",
    ):
        assert heading in text, heading
    assert "images/home.png" in text


def test_interview_prep_has_exactly_fifty_questions():
    text = (DOCS / "INTERVIEW_PREP.md").read_text(encoding="utf-8")
    numbers = [int(n) for n in re.findall(r"^### (\d+)\. ", text, flags=re.M)]
    assert numbers == list(range(1, 51))


def test_deployment_guide_covers_every_option_and_the_database_problem():
    text = (DOCS / "DEPLOYMENT.md").read_text(encoding="utf-8")
    for word in (
        "Streamlit Community Cloud",
        "Docker",
        "Render",
        "Railway",
        "Azure",
        "AWS",
        "AUTO_SETUP",
        "snapshot",
    ):
        assert word in text, word
    assert (BASE_DIR / "Dockerfile").exists() and (BASE_DIR / "Procfile").exists()


def test_no_secret_looking_values_are_committed_in_examples():
    assert "RAPIDAPI_KEY=\n" in read(".env.example")
