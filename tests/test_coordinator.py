"""Regression tests for usernames in existing config entries."""

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.setlistfm import SetlistFmCoordinator
from custom_components.setlistfm.const import CONF_API_KEY, CONF_USERID, DOMAIN
from custom_components.setlistfm.sensor import SetlistFmConcertsSensor


@pytest.mark.parametrize("username", ["Blabla", "BLABLA", "blabla", " Blabla "])
async def test_existing_entry_requests_use_lowercase(
    hass: HomeAssistant, aioclient_mock, username: str
) -> None:
    """Normalize both endpoints without migrating existing registry identities."""
    api_key = "CaseSensitive-API-Key"
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=username,
        data={CONF_USERID: username, CONF_API_KEY: api_key},
    )
    entry.add_to_hass(hass)
    aioclient_mock.get(
        "https://api.setlist.fm/rest/1.0/user/blabla",
        json={"userId": "blabla"},
    )
    aioclient_mock.get(
        "https://api.setlist.fm/rest/1.0/user/blabla/attended",
        json={"setlist": [{"id": "concert-id"}]},
    )

    coordinator = SetlistFmCoordinator(hass, entry)
    data = await coordinator._async_update_data()

    assert data == {
        "user": {"userId": "blabla"},
        "concerts": [{"id": "concert-id"}],
    }
    assert coordinator.userid == "blabla"
    assert coordinator.api_key == api_key
    assert aioclient_mock.call_count == 2
    for _, _, _, headers in aioclient_mock.mock_calls:
        assert headers == {"x-api-key": api_key, "Accept": "application/json"}
    assert entry.data[CONF_USERID] == username
    assert entry.unique_id == username
    sensor = SetlistFmConcertsSensor(coordinator, entry)
    assert sensor.unique_id == f"{entry.entry_id}_concerts"
    assert sensor.device_info["identifiers"] == {(DOMAIN, entry.entry_id)}
