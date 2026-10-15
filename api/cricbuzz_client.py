"""The only code in the project that talks to the Cricbuzz API.

Three protections stand between a bug and your 200-calls-a-month quota:

1. Disk cache  - an endpoint + parameters pair is fetched at most once; later
                 requests read ``data/raw/<endpoint>_<params>.json``.
2. Budget guard - every real request is logged in ``api_call_log``; the client
                 refuses to run once only the safety reserve is left.
3. Careful retries - only network errors and 5xx replies are retried. A 403
                 (bad key / not subscribed) or 429 (rate limit) stops at once.
"""

import json
import re
import time
from pathlib import Path
from typing import Any, Optional

import requests

import config
from database import repositories
from utils.db_connection import get_connection
from utils.logger import get_logger

logger = get_logger(__name__)


class ApiError(RuntimeError):
    """The API answered with an error, or with something that is not JSON."""


class BudgetExceeded(ApiError):
    """Raised instead of sending a request that would eat into the reserve."""


def cache_filename(endpoint: str, params: Optional[dict] = None) -> str:
    """'matches/get-info' + {'matchId': 151587} -> 'matches_get-info_151587.json'."""
    parts = [endpoint.strip("/").replace("/", "_")]
    for key in sorted(params or {}):
        parts.append(str(params[key]))
    return re.sub(r"[^A-Za-z0-9_.-]", "_", "_".join(parts)) + ".json"


class CricbuzzClient:
    """Cached, budget-guarded client for the Cricbuzz Cricket RapidAPI."""

    def __init__(
        self,
        session: Optional[requests.Session] = None,
        db_path: Optional[Path] = None,
        raw_dir: Optional[Path] = None,
        api_key: Optional[str] = None,
        sleep=time.sleep,
    ):
        self.session = session or requests.Session()
        self.db_path = db_path
        self.raw_dir = Path(raw_dir) if raw_dir else config.RAW_DIR
        self.api_key = config.RAPIDAPI_KEY if api_key is None else api_key
        self._sleep = sleep

    # -------------------------------------------------------------- budget ----
    def calls_used(self) -> int:
        """Requests used this month (dashboard offset + logged real calls)."""
        conn = get_connection(self.db_path)
        try:
            return repositories.calls_used(conn)
        finally:
            conn.close()

    def calls_remaining(self) -> int:
        """Requests left before the hard monthly limit."""
        return config.API_MONTHLY_LIMIT - self.calls_used()

    def _log(self, endpoint: str, params: dict, status: Optional[int], cached: bool):
        conn = get_connection(self.db_path)
        try:
            repositories.log_api_call(
                conn, endpoint, json.dumps(params or {}, sort_keys=True), status, cached
            )
            conn.commit()
        finally:
            conn.close()

    # --------------------------------------------------------------- cache ----
    def cache_path(self, endpoint: str, params: Optional[dict] = None) -> Path:
        """Where the response for this request is (or will be) stored."""
        return self.raw_dir / cache_filename(endpoint, params)

    def _read_cache(self, path: Path, max_age: Optional[float]) -> Optional[Any]:
        if not path.exists():
            return None
        if max_age is not None and time.time() - path.stat().st_mtime > max_age:
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            logger.warning("Ignoring unreadable cache file %s", path)
            return None

    def _write_cache(self, path: Path, payload: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        tmp.replace(path)  # atomic: a crash never leaves a half-written file

    # ----------------------------------------------------------------- get ----
    def get(
        self,
        endpoint: str,
        params: Optional[dict] = None,
        max_age: Optional[float] = None,
    ) -> Any:
        """Return the JSON for ``endpoint``, from cache when possible.

        max_age: seconds a cached copy stays valid (None = forever). The Live
        page passes a short value; historical data uses the default.
        """
        params = params or {}
        path = self.cache_path(endpoint, params)

        cached = self._read_cache(path, max_age)
        if cached is not None:
            self._log(endpoint, params, None, cached=True)
            logger.info("cache hit: %s", path.name)
            return cached

        if not self.api_key:
            raise ApiError("RAPIDAPI_KEY is empty - add it to your .env file.")

        remaining = self.calls_remaining()
        if remaining <= config.API_SAFETY_RESERVE:
            raise BudgetExceeded(
                f"Only {remaining} API calls left (reserve is "
                f"{config.API_SAFETY_RESERVE}). Refusing to send: {endpoint}"
            )

        payload = self._request(endpoint, params)
        self._write_cache(path, payload)
        return payload

    def _request(self, endpoint: str, params: dict) -> Any:
        url = f"{config.API_BASE_URL}/{endpoint.strip('/')}"
        headers = {
            "X-RapidAPI-Key": self.api_key,
            "X-RapidAPI-Host": config.RAPIDAPI_HOST,
        }
        last_error = "unknown error"
        for attempt in range(config.API_MAX_RETRIES + 1):
            try:
                response = self.session.get(
                    url,
                    headers=headers,
                    params=params,
                    timeout=config.API_TIMEOUT_SECONDS,
                )
            except (requests.ConnectionError, requests.Timeout) as exc:
                last_error = f"network problem: {exc}"
                logger.warning("%s (attempt %d)", last_error, attempt + 1)
                self._sleep(2**attempt)
                continue

            self._log(endpoint, params, response.status_code, cached=False)
            status = response.status_code
            if status == 200:
                try:
                    return response.json()
                except ValueError as exc:
                    raise ApiError(f"{endpoint}: reply is not valid JSON") from exc
            if status in (401, 403):
                raise ApiError(
                    f"{endpoint}: HTTP {status} - check RAPIDAPI_KEY and that you "
                    "are subscribed to this API."
                )
            if status == 429:
                raise ApiError(f"{endpoint}: HTTP 429 - rate limit hit, stop for now.")
            if 500 <= status < 600:
                last_error = f"server error HTTP {status}"
                logger.warning("%s (attempt %d)", last_error, attempt + 1)
                self._sleep(2**attempt)
                continue
            raise ApiError(f"{endpoint}: unexpected HTTP {status}")
        raise ApiError(f"{endpoint}: gave up after retries ({last_error})")
