"""Regression tests for username handling in the config flow."""

import json
from pathlib import Path
from unittest.mock import patch

import aiohttp
import pytest
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.setlistfm.config_flow import SetlistFmConfigFlow, validate_input
from custom_components.setlistfm.const import (
    CONF_API_KEY,
    CONF_NAME,
    CONF_USERID,
    DOMAIN,
)

USER_URL = "https://api.setlist.fm/rest/1.0/user/blabla/attended?p=1"
API_KEY = "CaseSensitive-API-Key"
EMPTY_ATTENDANCE = {"total": 0, "page": 1, "itemsPerPage": 20, "setlist": []}


@pytest.mark.parametrize("username", ["", " ", "   ", "\t", " \t\r\n "])
async def test_empty_username_rejected_before_identity_or_api(
    hass: HomeAssistant, aioclient_mock, username: str
) -> None:
    """An empty normalized username is invalid even if attendance would return 404."""
    aioclient_mock.get(
        "https://api.setlist.fm/rest/1.0/user//attended?p=1", status=404
    )
    with (
        patch.object(SetlistFmConfigFlow, "async_set_unique_id") as set_unique_id,
        patch("custom_components.setlistfm.async_setup_entry", return_value=True),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_USER},
            data={CONF_USERID: username, CONF_API_KEY: API_KEY},
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_username"}
    assert result["step_id"] == "user"
    set_unique_id.assert_not_called()
    assert aioclient_mock.call_count == 0
    assert hass.config_entries.async_entries(DOMAIN) == []


async def test_empty_username_can_be_corrected(hass, aioclient_mock) -> None:
    """Invalid input does not reserve an empty identity or prevent a later correction."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_USER},
        data={CONF_USERID: " \t ", CONF_API_KEY: API_KEY},
    )
    assert result["errors"] == {"base": "invalid_username"}
    assert aioclient_mock.call_count == 0
    aioclient_mock.get(USER_URL, status=404)
    with patch("custom_components.setlistfm.async_setup_entry", return_value=True):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_USERID: " BlaBla ", CONF_API_KEY: API_KEY},
        )
        await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["result"].unique_id == result["title"] == "blabla"
    assert aioclient_mock.call_count == 1


def test_invalid_username_error_is_localized() -> None:
    """The dedicated error must exist in the source strings and every locale."""
    component = Path(__file__).parents[1] / "custom_components" / DOMAIN
    translations = list((component / "translations").glob("*.json"))
    assert translations
    for path in [component / "strings.json", *translations]:
        messages = json.loads(path.read_text(encoding="utf-8"))
        assert messages["config"]["error"]["invalid_username"].strip(), path.name


@pytest.mark.parametrize("username", ["Blabla", "BLABLA", "blabla", " Blabla "])
async def test_create_entry_normalizes_username(
    hass: HomeAssistant, aioclient_mock, username: str
) -> None:
    """Use lowercase for requests and storage, not credentials or display names."""
    aioclient_mock.get(
        USER_URL,
        json=EMPTY_ATTENDANCE,
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
    assert result["title"] == "My Concerts"
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
    aioclient_mock.get(USER_URL, json=EMPTY_ATTENDANCE)

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
    aioclient_mock.get(USER_URL, json=EMPTY_ATTENDANCE)

    result = await validate_input(hass, data)

    assert result["title"] == "blabla"
    assert aioclient_mock.call_count == 1
    assert data == {CONF_USERID: " Blabla ", CONF_API_KEY: API_KEY}


@pytest.mark.parametrize(
    ("status", "error", "requests"),
    [
        (401, "invalid_auth", 1),
        (403, "invalid_auth", 1),
        (429, "rate_limited", 1),
        (500, "cannot_connect", 3),
        (400, "invalid_response", 1),
    ],
)
async def test_validation_errors_remain_visible(
    hass: HomeAssistant, aioclient_mock, status: int, error: str, requests: int
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
    assert aioclient_mock.call_count == requests


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


async def test_not_found_allows_empty_account(hass, aioclient_mock) -> None:
    """A 404 is not proof that a username is invalid."""
    aioclient_mock.get(USER_URL, status=404)
    with patch("custom_components.setlistfm.async_setup_entry", return_value=True):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_USER},
            data={CONF_USERID: "Blabla", CONF_API_KEY: API_KEY},
        )
        await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "blabla"


async def test_malformed_validation_response(hass, aioclient_mock) -> None:
    """A successful HTTP response must still contain a valid attendance page."""
    aioclient_mock.get(USER_URL, json={})
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_USER},
        data={CONF_USERID: "blabla", CONF_API_KEY: API_KEY},
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_response"}
