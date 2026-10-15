"""API client tests. A fake session stands in for the network: no real calls."""

import json

import pytest
import requests

import config
from api.cricbuzz_client import (
    ApiError,
    BudgetExceeded,
    CricbuzzClient,
    cache_filename,
)
from database.init_db import init_db


class FakeResponse:
    def __init__(self, status=200, payload=None, bad_json=False):
        self.status_code = status
        self._payload = payload if payload is not None else {"ok": True}
        self._bad_json = bad_json

    def json(self):
        if self._bad_json:
            raise ValueError("not json")
        return self._payload


class FakeSession:
    """Returns queued responses (or raises queued exceptions) in order."""

    def __init__(self, *queue):
        self.queue = list(queue)
        self.calls = []

    def get(self, url, headers=None, params=None, timeout=None):
        self.calls.append({"url": url, "headers": headers, "params": params})
        item = self.queue.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


@pytest.fixture()
def make_client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "API_CALLS_OFFSET", 0)
    db = init_db(tmp_path / "t.db")

    def _make(*queue, api_key="test-key"):
        session = FakeSession(*queue)
        client = CricbuzzClient(
            session=session,
            db_path=db,
            raw_dir=tmp_path / "raw",
            api_key=api_key,
            sleep=lambda seconds: None,
        )
        return client, session

    return _make


def test_cache_filename_matches_the_fixture_naming():
    assert cache_filename("matches/recent") == "matches_recent.json"
    assert (
        cache_filename("matches/get-info", {"matchId": 151587})
        == "matches_get-info_151587.json"
    )


def test_path_parameters_fill_the_url_and_the_rest_become_the_query(make_client):
    client, session = make_client(FakeResponse())
    client.get("mcenter/v1/{matchId}/scard", {"matchId": 40381, "extra": 1})
    call = session.calls[0]
    assert call["url"].endswith("/mcenter/v1/40381/scard")
    assert call["params"] == {"extra": 1}
    path = client.cache_path(
        "mcenter/v1/{matchId}/scard", {"matchId": 40381, "extra": 1}
    )
    assert path.name == "mcenter_v1_scard_1_40381.json"


def test_missing_path_parameter_fails_before_any_request(make_client):
    client, session = make_client(FakeResponse())
    with pytest.raises(ApiError, match="missing path parameter"):
        client.get("mcenter/v1/{matchId}", {})
    assert session.calls == []


def test_is_cached_reports_saved_responses(make_client):
    client, _ = make_client(FakeResponse())
    assert not client.is_cached("matches/v1/recent")
    client.get("matches/v1/recent")
    assert client.is_cached("matches/v1/recent")


def test_first_call_hits_the_api_second_reads_the_cache(make_client):
    client, session = make_client(FakeResponse(payload={"hello": 1}))
    assert client.get("matches/recent") == {"hello": 1}
    assert client.get("matches/recent") == {"hello": 1}
    assert len(session.calls) == 1  # the second one never left the machine
    assert client.calls_used() == 1  # cache hits do not count against the quota
    assert client.cache_path("matches/recent").exists()


def test_request_carries_the_rapidapi_headers(make_client):
    client, session = make_client(FakeResponse())
    client.get("players/get-info", {"playerId": 6635})
    call = session.calls[0]
    assert call["headers"]["X-RapidAPI-Key"] == "test-key"
    assert call["headers"]["X-RapidAPI-Host"] == config.RAPIDAPI_HOST
    assert call["params"] == {"playerId": 6635}


def test_budget_guard_refuses_when_only_the_reserve_is_left(make_client, monkeypatch):
    monkeypatch.setattr(config, "API_CALLS_OFFSET", 181)  # 200 - 181 = 19 < reserve 20
    client, session = make_client(FakeResponse())
    with pytest.raises(BudgetExceeded):
        client.get("matches/recent")
    assert session.calls == []


def test_budget_guard_still_serves_cached_files(make_client, monkeypatch):
    client, _ = make_client(FakeResponse(payload={"x": 1}))
    client.get("matches/recent")
    monkeypatch.setattr(config, "API_CALLS_OFFSET", 190)
    assert client.get("matches/recent") == {"x": 1}  # cache needs no quota


def test_server_error_is_retried_then_succeeds(make_client):
    client, session = make_client(FakeResponse(500), FakeResponse(payload={"ok": 2}))
    assert client.get("matches/recent") == {"ok": 2}
    assert len(session.calls) == 2
    assert client.calls_used() == 2  # both attempts are logged


def test_network_error_is_retried(make_client):
    client, session = make_client(requests.ConnectionError("boom"), FakeResponse())
    assert client.get("matches/recent") == {"ok": True}
    assert len(session.calls) == 2


def test_forbidden_stops_immediately(make_client):
    client, session = make_client(FakeResponse(403))
    with pytest.raises(ApiError, match="403"):
        client.get("matches/recent")
    assert len(session.calls) == 1


def test_rate_limit_stops_immediately(make_client):
    client, session = make_client(FakeResponse(429))
    with pytest.raises(ApiError, match="429"):
        client.get("matches/recent")
    assert len(session.calls) == 1


def test_gives_up_after_retries(make_client):
    client, session = make_client(*[FakeResponse(503)] * 5)
    with pytest.raises(ApiError, match="gave up"):
        client.get("matches/recent")
    assert len(session.calls) == config.API_MAX_RETRIES + 1


def test_invalid_json_is_an_api_error(make_client):
    client, _ = make_client(FakeResponse(bad_json=True))
    with pytest.raises(ApiError, match="not valid JSON"):
        client.get("matches/recent")


def test_missing_key_is_reported_clearly(make_client):
    client, session = make_client(FakeResponse(), api_key="")
    with pytest.raises(ApiError, match="RAPIDAPI_KEY"):
        client.get("matches/recent")
    assert session.calls == []


def test_corrupt_cache_file_is_ignored_and_refetched(make_client):
    client, session = make_client(FakeResponse(payload={"fresh": True}))
    path = client.cache_path("matches/recent")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{ not json", encoding="utf-8")
    assert client.get("matches/recent") == {"fresh": True}
    assert json.loads(path.read_text())["fresh"] is True
