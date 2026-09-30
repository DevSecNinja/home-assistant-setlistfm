"""Config flow for setlist.fm integration."""
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import (
    SetlistFmAuthError,
    SetlistFmClient,
    SetlistFmConnectionError,
    SetlistFmRateLimitError,
    SetlistFmResponseError,
)
from .const import (
    DOMAIN,
    CONF_USERID,
    CONF_API_KEY,
    CONF_NAME,
    CONF_REFRESH_PERIOD,
    CONF_NUMBER_OF_CONCERTS,
    CONF_DATE_FORMAT,
    CONF_SHOW_CONCERTS,
    DEFAULT_REFRESH_PERIOD,
    DEFAULT_NUMBER_OF_CONCERTS,
    DEFAULT_DATE_FORMAT,
    DEFAULT_SHOW_CONCERTS,
    DATE_FORMATS,
    SHOW_CONCERTS_OPTIONS,
)
from .helpers import normalize_username


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Check attendance access without claiming to prove username existence."""
    userid = normalize_username(data[CONF_USERID])
    client = SetlistFmClient(
        async_get_clientsession(hass), data[CONF_API_KEY], userid
    )
    await client.async_validate_access()
    return {"title": data.get(CONF_NAME) or userid}


class SetlistFmConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for setlist.fm."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}
        
        if user_input is not None and not normalize_username(user_input[CONF_USERID]):
            errors["base"] = "invalid_username"
        elif user_input is not None:
            user_input = {
                **user_input,
                CONF_USERID: normalize_username(user_input[CONF_USERID]),
            }
            await self.async_set_unique_id(user_input[CONF_USERID])
            self._abort_if_unique_id_configured()

            # Older entries may still have mixed-case usernames and unique IDs.
            if any(
                normalize_username(entry.data[CONF_USERID]) == user_input[CONF_USERID]
                for entry in self._async_current_entries()
            ):
                return self.async_abort(reason="already_configured")

            try:
                info = await validate_input(self.hass, user_input)
            except SetlistFmConnectionError:
                errors["base"] = "cannot_connect"
            except SetlistFmAuthError:
                errors["base"] = "invalid_auth"
            except SetlistFmRateLimitError:
                errors["base"] = "rate_limited"
            except SetlistFmResponseError:
                errors["base"] = "invalid_response"
            else:
                return self.async_create_entry(
                    title=info["title"],
                    data={
                        CONF_USERID: user_input[CONF_USERID],
                        CONF_API_KEY: user_input[CONF_API_KEY],
                        CONF_NAME: user_input.get(CONF_NAME, info["title"]),
                    },
                    options={
                        CONF_REFRESH_PERIOD: DEFAULT_REFRESH_PERIOD,
                        CONF_NUMBER_OF_CONCERTS: DEFAULT_NUMBER_OF_CONCERTS,
                        CONF_DATE_FORMAT: DEFAULT_DATE_FORMAT,
                        CONF_SHOW_CONCERTS: DEFAULT_SHOW_CONCERTS,
                    },
                )
        
        data_schema = vol.Schema(
            {
                vol.Required(CONF_USERID): str,
                vol.Required(CONF_API_KEY): str,
                vol.Optional(CONF_NAME): str,
            }
        )
        
        return self.async_show_form(
            step_id="user",
            data_schema=data_schema,
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Get the options flow for this handler."""
        return SetlistFmOptionsFlowHandler(config_entry)


class SetlistFmOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options flow for setlist.fm integration."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self._config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)
        
        options = self._config_entry.options
        
        data_schema = vol.Schema(
            {
                vol.Optional(
                    CONF_REFRESH_PERIOD,
                    default=options.get(CONF_REFRESH_PERIOD, DEFAULT_REFRESH_PERIOD),
                ): vol.All(vol.Coerce(int), vol.Range(min=1, max=24)),
                vol.Optional(
                    CONF_NUMBER_OF_CONCERTS,
                    default=options.get(CONF_NUMBER_OF_CONCERTS, DEFAULT_NUMBER_OF_CONCERTS),
                ): vol.All(vol.Coerce(int), vol.Range(min=1, max=50)),
                vol.Optional(
                    CONF_DATE_FORMAT,
                    default=options.get(CONF_DATE_FORMAT, DEFAULT_DATE_FORMAT),
                ): vol.In(DATE_FORMATS),
                vol.Optional(
                    CONF_SHOW_CONCERTS,
                    default=options.get(CONF_SHOW_CONCERTS, DEFAULT_SHOW_CONCERTS),
                ): vol.In(SHOW_CONCERTS_OPTIONS),
            }
        )
        
        return self.async_show_form(
            step_id="init",
            data_schema=data_schema,
        )
