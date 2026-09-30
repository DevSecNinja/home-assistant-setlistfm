"""Fixtures for the setlist.fm integration tests."""

from unittest.mock import patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.setlistfm.const import CONF_API_KEY, CONF_NAME, CONF_USERID, DOMAIN


@pytest.fixture(autouse=True)
def enable_custom_integration(enable_custom_integrations):
    """Allow Home Assistant to load the custom integration."""


@pytest.fixture(autouse=True)
def api_clock():
    """Advance only the API client's monotonic clock instead of waiting in tests."""
    now = 1000.0
    delays = []

    async def sleep(delay):
        nonlocal now
        delays.append(delay)
        now += delay

    with (
        patch("custom_components.setlistfm.api.monotonic", side_effect=lambda: now),
        patch("custom_components.setlistfm.api.sleep", side_effect=sleep),
    ):
        yield delays


@pytest.fixture
def attendance():
    """A full snapshot; native tests use dates independent of API ordering."""
    return {
        "concerts": [
            {
                "id": key,
                "eventDate": date,
                "artist": {"name": f"Artist {key}"},
                "venue": {"name": f"Venue {key}", "city": {"name": "City"}},
                "url": f"https://www.setlist.fm/setlist/{key}.html",
                "set": [],
            }
            for key, date in (
                ("far", "10-02-2026"),
                ("past", "01-01-2026"),
                ("near", "02-02-2026"),
                ("today", "01-02-2026"),
            )
        ],
        "total": 4,
        "fetched_count": 4,
        "skipped_count": 0,
        "complete": True,
        "completeness_reason": None,
        "pages_fetched": 1,
    }


@pytest.fixture
def entry(hass):
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="My shows",
        unique_id="Blabla",
        data={CONF_USERID: "Blabla", CONF_API_KEY: "old-key", CONF_NAME: "My shows"},
    )
    entry.add_to_hass(hass)
    return entry


@pytest.fixture
def mock_attendance(attendance):
    with patch(
        "custom_components.setlistfm.coordinator.SetlistFmClient.async_get_attendance",
        return_value=attendance,
    ) as mock:
        yield mock
