"""Bounded, asynchronous access to the supported setlist.fm attendance API."""
from __future__ import annotations

import asyncio
from asyncio import sleep
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import json
import logging
import math
from time import monotonic
from typing import Any, TypedDict
from urllib.parse import quote

import aiohttp

from .helpers import normalize_concert, normalize_username

_LOGGER = logging.getLogger(__name__)

BASE_URL = "https://api.setlist.fm/rest/1.0"
REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=20)
MAX_ATTEMPTS = 3
REQUEST_INTERVAL = 1.0
MAX_RETRY_DELAY = 30
DEFAULT_RATE_LIMIT_DELAY = 60
# A safety guard, not an upstream limit: exceeding it fails the entire refresh.
MAX_PAGES = 1000


class SetlistFmError(Exception):
    """Base class for expected API errors."""


class SetlistFmAuthError(SetlistFmError):
    """The API rejected the credentials."""


class SetlistFmConnectionError(SetlistFmError):
    """The service could not be reached after bounded retries."""


class SetlistFmResponseError(SetlistFmError):
    """The response cannot safely be used."""


class SetlistFmNotFoundError(SetlistFmResponseError):
    """No attendance was found; this does not prove a user is nonexistent."""


class SetlistFmRateLimitError(SetlistFmError):
    """The service requires requests to stop temporarily."""

    def __init__(self, retry_after: float) -> None:
        """Expose the remaining cooldown without including request credentials."""
        self.retry_after = retry_after
        super().__init__(
            f"setlist.fm rate limit reached; retry after {math.ceil(retry_after)} seconds"
        )


class AttendanceData(TypedDict):
    """Full, unfiltered attendance plus explicit coverage information."""

    concerts: list[dict[str, Any]]
    total: int | None
    fetched_count: int
    skipped_count: int
    complete: bool
    completeness_reason: str | None
    pages_fetched: int


def _retry_after(value: str | None) -> float | None:
    """Parse Retry-After delay-seconds or an HTTP date, ignoring invalid values."""
    if value is None:
        return None
    value = value.strip()
    if value.isascii() and value.isdigit():
        delay = float(value)
        return delay if math.isfinite(delay) else None
    try:
        date = parsedate_to_datetime(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if date.tzinfo is None:
        return None
    delay = (date - datetime.now(timezone.utc)).total_seconds()
    return delay if delay >= 0 else None


def _page_metadata(data: dict[str, Any], page: int) -> tuple[int, int, list[Any]]:
    """Require trustworthy metadata before fetching or publishing a page."""
    total, actual_page, size = (
        data.get("total"), data.get("page"), data.get("itemsPerPage")
    )
    records = data.get("setlist")
    if (
        type(total) is not int
        or type(actual_page) is not int
        or type(size) is not int
        or total < 0
        or actual_page != page
        or size < (1 if total else 0)
        or not isinstance(records, list)
    ):
        raise SetlistFmResponseError("Invalid attendance pagination metadata")
    expected = min(size, max(0, total - (page - 1) * size))
    if len(records) != expected:
        raise SetlistFmResponseError("Attendance page length disagrees with metadata")
    return total, size, records


class SetlistFmClient:
    """Reuse a caller-owned HA session; never create or close global resources."""

    def __init__(self, session: aiohttp.ClientSession, api_key: str, userid: str) -> None:
        """Initialize per-entry request pacing and cooldown state."""
        self._session = session
        self._headers = {"x-api-key": api_key, "Accept": "application/json"}
        self._url = (
            f"{BASE_URL}/user/{quote(normalize_username(userid), safe='')}/attended"
        )
        self._next_request = 0.0
        self._blocked_until = 0.0
        self._request_lock = asyncio.Lock()

    async def _request(self, page: int) -> dict[str, Any]:
        """Apply identical finite error handling to validation and polling."""
        async with self._request_lock:
            for attempt in range(MAX_ATTEMPTS):
                cooldown = self._blocked_until - monotonic()
                if cooldown > 0:
                    raise SetlistFmRateLimitError(cooldown)
                await sleep(max(0, self._next_request - monotonic()))
                delay = float(2 ** (attempt + 1))
                error: SetlistFmError
                self._next_request = monotonic() + REQUEST_INTERVAL
                try:
                    async with self._session.get(
                        self._url,
                        params={"p": page},
                        headers=self._headers,
                        timeout=REQUEST_TIMEOUT,
                    ) as response:
                        if response.status in (401, 403):
                            raise SetlistFmAuthError("setlist.fm rejected the API key")
                        if response.status == 404:
                            raise SetlistFmNotFoundError("Attendance not found")
                        if response.status == 200:
                            try:
                                data = await response.json()
                            except (
                                aiohttp.ContentTypeError,
                                json.JSONDecodeError,
                                UnicodeDecodeError,
                            ) as err:
                                raise SetlistFmResponseError(
                                    "setlist.fm returned invalid JSON"
                                ) from err
                            if not isinstance(data, dict):
                                raise SetlistFmResponseError(
                                    "setlist.fm returned a non-object response"
                                )
                            return data
                        if response.status == 429:
                            retry_after = _retry_after(response.headers.get("Retry-After"))
                            delay = max(
                                delay,
                                retry_after if retry_after is not None
                                else DEFAULT_RATE_LIMIT_DELAY,
                            )
                            error = SetlistFmRateLimitError(delay)
                            self._blocked_until = monotonic() + delay
                            if delay > MAX_RETRY_DELAY or attempt == MAX_ATTEMPTS - 1:
                                raise error
                        elif response.status in (500, 502, 503, 504):
                            error = SetlistFmConnectionError(
                                f"setlist.fm service error (HTTP {response.status})"
                            )
                            retry_after = _retry_after(response.headers.get("Retry-After"))
                            if retry_after is not None:
                                delay = max(delay, retry_after)
                                self._blocked_until = monotonic() + delay
                            if delay > MAX_RETRY_DELAY:
                                self._blocked_until = monotonic() + delay
                                raise SetlistFmRateLimitError(delay)
                        else:
                            raise SetlistFmResponseError(
                                f"Unexpected setlist.fm response (HTTP {response.status})"
                            )
                except (aiohttp.ClientError, TimeoutError) as err:
                    error = SetlistFmConnectionError(
                        "Timed out or could not connect to setlist.fm"
                    )
                    if attempt == MAX_ATTEMPTS - 1:
                        raise error from err
                if attempt == MAX_ATTEMPTS - 1:
                    raise error
                # Release the HTTP response before backing off; cancellation propagates.
                await sleep(delay)
        raise AssertionError("Unreachable request retry state")

    async def async_validate_access(self) -> None:
        """Check the supported endpoint, not the deprecated profile endpoint."""
        try:
            data = await self._request(1)
        except SetlistFmNotFoundError:
            # The API does not document whether this is an empty or unknown account.
            return
        _page_metadata(data, 1)

    async def async_get_attendance(self) -> AttendanceData:
        """Fetch an atomic snapshot; a later-page failure never returns partial data."""
        try:
            first_page = await self._request(1)
        except SetlistFmNotFoundError:
            return {
                "concerts": [],
                "total": None,
                "fetched_count": 0,
                "skipped_count": 0,
                "complete": False,
                "completeness_reason": "attendance_not_found",
                "pages_fetched": 1,
            }

        total, size, records = _page_metadata(first_page, 1)
        pages = max(1, (total + size - 1) // size) if size else 1
        if pages > MAX_PAGES:
            raise SetlistFmResponseError("Attendance exceeds the pagination safety bound")

        concerts: list[dict[str, Any]] = []
        seen: set[str] = set()
        skipped = repaired = 0
        for page in range(1, pages + 1):
            if page > 1:
                data = await self._request(page)
                page_total, page_size, records = _page_metadata(data, page)
                if (page_total, page_size) != (total, size):
                    raise SetlistFmResponseError("Attendance changed during pagination")
            for record in records:
                concert_id = record.get("id") if isinstance(record, dict) else None
                if isinstance(concert_id, str) and concert_id:
                    if concert_id in seen:
                        raise SetlistFmResponseError(
                            "Repeated concert during pagination; snapshot is incomplete"
                        )
                    seen.add(concert_id)
                try:
                    concert, was_repaired = normalize_concert(record)
                except ValueError:
                    skipped += 1
                    continue
                repaired += was_repaired
                concerts.append(concert)

        if skipped or repaired:
            _LOGGER.warning(
                "Malformed attendance data: skipped %d records, repaired optional "
                "fields in %d records",
                skipped, repaired,
            )
        return {
            "concerts": concerts,
            "total": total,
            "fetched_count": len(concerts),
            "skipped_count": skipped,
            "complete": skipped == 0,
            "completeness_reason": "invalid_records" if skipped else None,
            "pages_fetched": pages,
        }
