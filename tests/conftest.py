"""Fixtures for the setlist.fm integration tests."""

import pytest


@pytest.fixture(autouse=True)
def enable_custom_integration(enable_custom_integrations):
    """Allow Home Assistant to load the custom integration."""
