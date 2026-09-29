"""Regression tests for usernames in existing config entries."""

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.setlistfm import SetlistFmCoordinator
from custom_components.setlistfm.const import CONF_API_KEY, CONF_USERID, DOMAIN
from custom_components.setlistfm.sensor import SetlistFmConcertsSensor


@pytest.mark.parametrize("username", ["Blabla", "BLABLA", "blabla", " Blabla "])
async def test_existing_entry_requests_use_lowercase(
    hass: HomeAssistant, aioclient_mock, username: str
) -> None:
    """Normalize the supported endpoint without migrating registry identities."""
    api_key = "CaseSensitive-API-Key"
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=username,
        data={CONF_USERID: username, CONF_API_KEY: api_key},
    )
    entry.add_to_hass(hass)
    aioclient_mock.get(
        "https://api.setlist.fm/rest/1.0/user/blabla/attended?p=1",
        json={
            "setlist": [{"id": "concert-id", "eventDate": "01-01-2026"}],
            "total": 1, "page": 1, "itemsPerPage": 20,
        },
    )

    coordinator = SetlistFmCoordinator(hass, entry)
    data = await coordinator._async_update_data()

    assert data["concerts"][0]["id"] == "concert-id"
    assert data["total"] == data["fetched_count"] == 1
    assert data["complete"]
    assert "user" not in data
    assert coordinator.userid == "blabla"
    assert coordinator.api_key == api_key
    assert aioclient_mock.call_count == 1
    for _, _, _, headers in aioclient_mock.mock_calls:
        assert headers == {"x-api-key": api_key, "Accept": "application/json"}
    assert entry.data[CONF_USERID] == username
    assert entry.unique_id == username
    sensor = SetlistFmConcertsSensor(coordinator, entry)
    assert sensor.unique_id == f"{entry.entry_id}_concerts"
    assert sensor.device_info["identifiers"] == {(DOMAIN, entry.entry_id)}


@pytest.mark.parametrize("status", [404, 429, 500])
async def test_later_page_failure_preserves_snapshot(hass, aioclient_mock, status):
    """A refresh failure retains all data from the previous successful refresh."""
    entry = MockConfigEntry(
        domain=DOMAIN, data={CONF_USERID: "blabla", CONF_API_KEY: "secret"}
    )
    entry.add_to_hass(hass)
    coordinator = SetlistFmCoordinator(hass, entry)
    previous = {
        "concerts": [{"id": "old", "eventDate": "01-01-2025"}],
        "total": 1, "fetched_count": 1, "skipped_count": 0,
        "complete": True, "completeness_reason": None, "pages_fetched": 1,
    }
    coordinator.async_set_updated_data(previous)
    url = "https://api.setlist.fm/rest/1.0/user/blabla/attended"
    aioclient_mock.get(f"{url}?p=1", json={
        "setlist": [{"id": "new", "eventDate": "01-01-2026"}],
        "total": 2, "page": 1, "itemsPerPage": 1,
    })
    aioclient_mock.get(f"{url}?p=2", status=status)
    await coordinator.async_refresh()
    assert coordinator.data is previous
    assert not coordinator.last_update_success
    assert coordinator.last_exception is not None


@pytest.mark.parametrize("status", [401, 403])
async def test_coordinator_auth_failure(hass, aioclient_mock, status):
    entry = MockConfigEntry(
        domain=DOMAIN, data={CONF_USERID: "blabla", CONF_API_KEY: "secret"}
    )
    coordinator = SetlistFmCoordinator(hass, entry)
    aioclient_mock.get(
        "https://api.setlist.fm/rest/1.0/user/blabla/attended?p=1", status=status
    )
    with pytest.raises(ConfigEntryAuthFailed):
        await coordinator._async_update_data()
