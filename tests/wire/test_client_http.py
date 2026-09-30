"""Real SetlistFmClient/session requests against the loopback mock service."""

import asyncio
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from unittest.mock import patch

import aiohttp
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.setlistfm import SetlistFmCoordinator, api
from custom_components.setlistfm.api import (
    SetlistFmAuthError,
    SetlistFmClient,
    SetlistFmConnectionError,
    SetlistFmRateLimitError,
    SetlistFmResponseError,
)
from custom_components.setlistfm.const import CONF_API_KEY, CONF_USERID, DOMAIN
from devtools.setlistfm_mock import Account, ResponseStep, make_concerts


async def test_actual_path_headers_pages_and_no_profile(
    setlist_server, http_session, api_clock,
):
    server = await setlist_server(deprecated_profile=True)
    client = SetlistFmClient(http_session, "mock-api-key", " DeMo ")
    await client.async_validate_access()
    data = await client.async_get_attendance()
    assert [record["id"] for record in data["concerts"]] == [
        "mock-0", "mock-1", "mock-2", "mock-3", "mock-4",
    ]
    assert data | {"concerts": []} == {
        "concerts": [], "total": 5, "fetched_count": 5, "skipped_count": 0,
        "complete": True, "completeness_reason": None, "pages_fetched": 3,
    }
    assert [entry.query for entry in server.journal] == [
        (("p", "1"),), (("p", "1"),), (("p", "2"),), (("p", "3"),),
    ]
    for entry in server.journal:
        assert entry.method == "GET"
        assert entry.path == "/rest/1.0/user/demo/attended"
        assert entry.headers["x-api-key"] == "<redacted>"
        assert entry.api_key_matches
        assert entry.headers["accept"] == "application/json"
    assert api_clock == [0, 1, 1, 1]


async def test_userid_is_one_encoded_path_segment(setlist_server, http_session):
    server = await setlist_server([Account("demo/with space", [])])
    data = await SetlistFmClient(
        http_session, "mock-api-key", " DEMO/with space "
    ).async_get_attendance()
    assert data["complete"]
    assert server.journal[0].raw_path == (
        "/rest/1.0/user/demo%2Fwith%20space/attended"
    )
    assert server.journal[0].query == (("p", "1"),)


async def test_wire_attendance_is_not_capped_at_1000(setlist_server, http_session):
    server = await setlist_server([
        Account("demo", make_concerts(1001, optional_fields=False), items_per_page=1000)
    ])
    data = await SetlistFmClient(
        http_session, "mock-api-key", "demo"
    ).async_get_attendance()
    assert data["fetched_count"] == data["total"] == 1001
    assert data["complete"]
    assert len(server.journal) == 2


@pytest.mark.parametrize("shape", ["flat", "nested", "mixed", "minimal"])
async def test_optional_fields_and_song_shapes(setlist_server, http_session, shape):
    server = await setlist_server([Account("demo", make_concerts(
        shape="mixed" if shape == "minimal" else shape,
        optional_fields=shape != "minimal",
    ))])
    data = await SetlistFmClient(
        http_session, "mock-api-key", "demo"
    ).async_get_attendance()
    assert data["complete"]
    assert data["fetched_count"] == 5
    for record in data["concerts"]:
        assert sum(len(item["song"]) for item in record["set"]) == (
            0 if shape == "minimal" else 3
        )
        if shape == "minimal":
            assert record["artist"]["name"] == record["venue"]["name"] == "Unknown"
            assert record["venue"]["city"]["country"]["name"] == ""
    assert len(server.journal) == 3


async def test_zero_attendance_is_distinct_from_ambiguous_404(setlist_server, http_session):
    server = await setlist_server([Account("empty", [])])
    empty = await SetlistFmClient(
        http_session, "mock-api-key", "empty"
    ).async_get_attendance()
    unknown_client = SetlistFmClient(http_session, "mock-api-key", "unknown")
    await unknown_client.async_validate_access()
    unknown = await unknown_client.async_get_attendance()
    assert empty["concerts"] == unknown["concerts"] == []
    assert empty["total"] == 0
    assert empty["complete"]
    assert unknown["total"] is None
    assert not unknown["complete"]
    assert unknown["completeness_reason"] == "attendance_not_found"
    assert [entry.status for entry in server.journal] == [200, 404, 404]


@pytest.mark.parametrize("status", [401, 403])
async def test_wire_auth_errors_do_not_retry(setlist_server, http_session, status):
    server = await setlist_server()
    server.script("demo", 1, ResponseStep(status=status), repeat_last=True)
    with pytest.raises(SetlistFmAuthError):
        await SetlistFmClient(
            http_session, "mock-api-key", "demo"
        ).async_validate_access()
    assert server.counts[("demo", 1)] == 1


@pytest.mark.parametrize("status", [500, 502, 503, 504])
async def test_wire_transient_retry_recovers(setlist_server, http_session, api_clock, status):
    server = await setlist_server()
    server.script("demo", 1, ResponseStep(status=status))
    await SetlistFmClient(http_session, "mock-api-key", "demo").async_validate_access()
    assert server.counts[("demo", 1)] == 2
    assert [entry.status for entry in server.journal] == [status, 200]
    assert api_clock == [0, 2, 0]


@pytest.mark.parametrize("kind", ["seconds", "http-date"])
async def test_wire_short_retry_after(setlist_server, http_session, api_clock, kind):
    server = await setlist_server()
    now = datetime(2026, 9, 29, 12, 0, tzinfo=timezone.utc)
    value = "5" if kind == "seconds" else format_datetime(now + timedelta(seconds=5), usegmt=True)
    server.script("demo", 1, ResponseStep(status=429, headers={"Retry-After": value}))
    with patch.object(api, "datetime") as clock:
        clock.now.return_value = now
        await SetlistFmClient(http_session, "mock-api-key", "demo").async_validate_access()
    assert [entry.status for entry in server.journal] == [429, 200]
    assert api_clock == [0, 5, 0]


@pytest.mark.parametrize("guidance", ["60", None])
async def test_cooldown_blocks_wire_requests_until_expiry(
    setlist_server, http_session, api_clock, guidance,
):
    server = await setlist_server()
    headers = {} if guidance is None else {"Retry-After": guidance}
    server.script("demo", 1, ResponseStep(status=429, headers=headers))
    client = SetlistFmClient(http_session, "mock-api-key", "demo")
    for _ in range(2):
        with pytest.raises(SetlistFmRateLimitError) as error:
            await client.async_validate_access()
        assert error.value.retry_after == 60
    assert len(server.journal) == 1
    assert api_clock == [0]
    await api.sleep(60)  # Advance only the existing API clock seam, not real time.
    await client.async_validate_access()
    assert len(server.journal) == 2


async def test_retry_exhaustion_retains_cooldown(setlist_server, http_session, api_clock):
    server = await setlist_server()
    server.script(
        "demo", 1, ResponseStep(status=429, headers={"Retry-After": "0"}), repeat_last=True,
    )
    client = SetlistFmClient(http_session, "mock-api-key", "demo")
    with pytest.raises(SetlistFmRateLimitError):
        await client.async_validate_access()
    with pytest.raises(SetlistFmRateLimitError):
        await client.async_validate_access()
    assert len(server.journal) == 3
    assert sum(api_clock) == 6


@pytest.mark.parametrize(
    "step",
    [
        ResponseStep(raw_body=b'{"broken":'),
        ResponseStep(raw_body=b"null"),
        ResponseStep(raw_body=b"<html>oops</html>", content_type="text/html"),
        ResponseStep(payload={"setlist": {}, "page": 1, "total": 0, "itemsPerPage": 2}),
        ResponseStep(payload={"setlist": [], "page": 1, "total": "0", "itemsPerPage": 2}),
    ],
)
async def test_bad_wire_response_is_not_empty_success(setlist_server, http_session, step):
    server = await setlist_server()
    server.script("demo", 1, step, repeat_last=True)
    with pytest.raises(SetlistFmResponseError):
        await SetlistFmClient(
            http_session, "mock-api-key", "demo"
        ).async_get_attendance()
    assert len(server.journal) == 1


async def test_invalid_record_keeps_valid_records_with_coverage(
    setlist_server, http_session, caplog,
):
    server = await setlist_server()
    server.script("demo", 1, ResponseStep(payload={
        "setlist": [
            {"id": "valid", "eventDate": "01-01-2026"},
            {"id": "invalid", "eventDate": "not-a-date"},
        ],
        "page": 1, "total": 2, "itemsPerPage": 2,
    }))
    data = await SetlistFmClient(
        http_session, "mock-api-key", "demo"
    ).async_get_attendance()
    assert [record["id"] for record in data["concerts"]] == ["valid"]
    assert data["skipped_count"] == 1
    assert not data["complete"]
    assert data["completeness_reason"] == "invalid_records"
    assert "skipped 1 records" in caplog.text
    assert "mock-api-key" not in caplog.text


@pytest.mark.parametrize("fault", ["duplicate", "changing-total"])
async def test_inconsistent_wire_pagination_fails_atomically(
    setlist_server, http_session, fault,
):
    server = await setlist_server()
    server.script("demo", 2, ResponseStep(payload={
        "setlist": make_concerts(2) if fault == "duplicate" else make_concerts(2, prefix="new"),
        "page": 2, "total": 5 if fault == "duplicate" else 6, "itemsPerPage": 2,
    }))
    with pytest.raises(SetlistFmResponseError):
        await SetlistFmClient(
            http_session, "mock-api-key", "demo"
        ).async_get_attendance()
    assert len(server.journal) == 2


async def test_real_timeout_is_bounded_and_classified(
    setlist_server, http_session, monkeypatch, api_clock,
):
    server = await setlist_server()
    server.script("demo", 1, ResponseStep(gate=asyncio.Event()), repeat_last=True)
    monkeypatch.setattr(api, "REQUEST_TIMEOUT", aiohttp.ClientTimeout(total=0.05))
    with pytest.raises(SetlistFmConnectionError):
        await SetlistFmClient(
            http_session, "mock-api-key", "demo"
        ).async_validate_access()
    assert len(server.journal) == 3
    assert sum(api_clock) == 6


async def test_cancellation_during_request_releases_client_lock(
    setlist_server, http_session,
):
    server = await setlist_server()
    server.script("demo", 1, ResponseStep(gate=asyncio.Event()))
    client = SetlistFmClient(http_session, "mock-api-key", "demo")
    task = asyncio.create_task(client.async_get_attendance())
    await server.wait_for_requests(1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert len(server.journal) == 1
    data = await asyncio.wait_for(client.async_get_attendance(), timeout=2)
    assert data["complete"]
    assert len(server.journal) == 4


async def test_cancellation_during_backoff_sends_no_retry(
    setlist_server, http_session, monkeypatch,
):
    server = await setlist_server()
    server.script("demo", 1, ResponseStep(status=503), repeat_last=True)
    backing_off = asyncio.Event()

    async def sleep(delay):
        if delay:
            backing_off.set()
            await asyncio.Event().wait()

    monkeypatch.setattr(api, "sleep", sleep)
    task = asyncio.create_task(
        SetlistFmClient(http_session, "mock-api-key", "demo").async_validate_access()
    )
    await asyncio.wait_for(backing_off.wait(), timeout=2)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert len(server.journal) == 1


@pytest.mark.parametrize("status", [404, 429, 500])
async def test_wire_later_failure_retains_real_previous_snapshot(
    hass, setlist_server, status,
):
    server = await setlist_server()
    entry = MockConfigEntry(
        domain=DOMAIN, data={CONF_USERID: "demo", CONF_API_KEY: "mock-api-key"},
    )
    entry.add_to_hass(hass)
    coordinator = SetlistFmCoordinator(hass, entry)
    await coordinator.async_refresh()
    previous = coordinator.data
    assert previous["fetched_count"] == 5
    assert coordinator.last_update_success
    server.accounts["demo"].concerts = make_concerts(prefix="changed")
    server.script("demo", 2, ResponseStep(status=status), repeat_last=True)
    await coordinator.async_refresh()
    assert coordinator.data is previous
    assert coordinator.data["concerts"][0]["id"] == "mock-0"
    assert not coordinator.last_update_success
    assert coordinator.last_exception is not None
    assert server.counts[("demo", 2)] == (4 if status == 500 else 2)
