"""Regression tests for username handling in the config flow."""

from unittest.mock import patch

import aiohttp
import pytest
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.setlistfm.config_flow import validate_input
from custom_components.setlistfm.const import (
    CONF_API_KEY,
    CONF_NAME,
    CONF_USERID,
    DOMAIN,
)

USER_URL = "https://api.setlist.fm/rest/1.0/user/blabla"
API_KEY = "CaseSensitive-API-Key"


@pytest.mark.parametrize("username", ["Blabla", "BLABLA", "blabla", " Blabla "])
async def test_create_entry_normalizes_username(
    hass: HomeAssistant, aioclient_mock, username: str
) -> None:
    """Use lowercase for requests and storage, not credentials or display names."""
    aioclient_mock.get(
        USER_URL,
        json={"userId": "blabla", "fullname": "Bla Bla"},
    )
    with patch("custom_components.setlistfm.async_setup_entry", return_value=True):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_USER},
            data={
                CONF_USERID: username,
                CONF_API_KEY: API_KEY,
                CONF_NAME: "My Concerts",
            },
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Bla Bla"
    assert result["data"] == {
        CONF_USERID: "blabla",
        CONF_API_KEY: API_KEY,
        CONF_NAME: "My Concerts",
    }
    assert result["result"].unique_id == "blabla"
    assert aioclient_mock.call_count == 1
    assert aioclient_mock.mock_calls[0][3] == {
        "x-api-key": API_KEY,
        "Accept": "application/json",
    }


@pytest.mark.parametrize("existing_username", ["blabla", "Blabla", " BLABLA "])
async def test_duplicate_username(
    hass: HomeAssistant, aioclient_mock, existing_username: str
) -> None:
    """Reject duplicates, including legacy entries, before contacting the API."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=existing_username,
        data={CONF_USERID: existing_username, CONF_API_KEY: API_KEY},
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_USER},
        data={CONF_USERID: "BlaBla", CONF_API_KEY: API_KEY},
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert aioclient_mock.call_count == 0
    assert hass.config_entries.async_entries(DOMAIN) == [entry]
    assert entry.unique_id == existing_username
    assert entry.data[CONF_USERID] == existing_username


async def test_different_user_can_be_added(
    hass: HomeAssistant, aioclient_mock
) -> None:
    """Normalization must not turn multi-user support into a single-entry limit."""
    MockConfigEntry(
        domain=DOMAIN,
        unique_id="another-user",
        data={CONF_USERID: "another-user", CONF_API_KEY: API_KEY},
    ).add_to_hass(hass)
    aioclient_mock.get(USER_URL, json={"userId": "blabla"})

    with patch("custom_components.setlistfm.async_setup_entry", return_value=True):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_USER},
            data={CONF_USERID: "Blabla", CONF_API_KEY: API_KEY},
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_NAME] == "blabla"
    assert len(hass.config_entries.async_entries(DOMAIN)) == 2


async def test_validate_input_normalizes_username(
    hass: HomeAssistant, aioclient_mock
) -> None:
    """The validation request also normalizes usernames when called directly."""
    data = {CONF_USERID: " Blabla ", CONF_API_KEY: API_KEY}
    aioclient_mock.get(USER_URL, json={})

    result = await validate_input(hass, data)

    assert result["title"] == "blabla"
    assert aioclient_mock.call_count == 1
    assert data == {CONF_USERID: " Blabla ", CONF_API_KEY: API_KEY}


@pytest.mark.parametrize(
    ("status", "error"),
    [(401, "invalid_auth"), (404, "user_not_found"), (500, "cannot_connect")],
)
async def test_validation_errors_remain_visible(
    hass: HomeAssistant, aioclient_mock, status: int, error: str
) -> None:
    """Normalizing a username must not hide API errors."""
    aioclient_mock.get(USER_URL, status=status)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_USER},
        data={CONF_USERID: "Blabla", CONF_API_KEY: API_KEY},
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": error}
    assert aioclient_mock.call_count == 1


async def test_connection_error(
    hass: HomeAssistant, aioclient_mock
) -> None:
    """Keep network failures visible when using Home Assistant's HTTP session."""
    aioclient_mock.get(USER_URL, exc=aiohttp.ClientConnectionError)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_USER},
        data={CONF_USERID: "Blabla", CONF_API_KEY: API_KEY},
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


async def test_user_form(hass: HomeAssistant, aioclient_mock) -> None:
    """Opening the setup form must not contact the API."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert not result["errors"]
    assert aioclient_mock.call_count == 0
