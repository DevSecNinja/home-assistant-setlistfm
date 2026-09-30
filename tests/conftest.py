"""Fixtures for the setlist.fm integration tests."""

from unittest.mock import patch

import pytest


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
