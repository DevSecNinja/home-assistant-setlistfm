"""The setlist.fm integration."""
from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.exceptions import ConfigEntryAuthFailed

from .api import AttendanceData, SetlistFmAuthError, SetlistFmClient, SetlistFmError
from .const import DOMAIN, CONF_USERID, CONF_API_KEY
from .helpers import normalize_username

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up setlist.fm from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    coordinator = SetlistFmCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()

    hass.data[DOMAIN][entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Register update listener for options changes
    entry.async_on_unload(entry.add_update_listener(update_listener))

    # Register a single shared refresh service, guarded against double-registration
    if not hass.services.has_service(DOMAIN, "refresh"):
        async def handle_refresh(call) -> None:
            """Force refresh of data for a config entry."""
            entry_id = call.data.get("entry_id")
            if entry_id and entry_id in hass.data[DOMAIN]:
                await hass.data[DOMAIN][entry_id].async_request_refresh()
            else:
                # Refresh all entries if no specific entry_id given
                for coord in hass.data[DOMAIN].values():
                    if isinstance(coord, SetlistFmCoordinator):
                        await coord.async_request_refresh()

        hass.services.async_register(DOMAIN, "refresh", handle_refresh)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
        # Remove the shared service only when the last entry is unloaded
        if not hass.data[DOMAIN]:
            hass.services.async_remove(DOMAIN, "refresh")

    return unload_ok


async def update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update."""
    await hass.config_entries.async_reload(entry.entry_id)


class SetlistFmCoordinator(DataUpdateCoordinator):
    """Class to manage fetching setlist.fm data."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize."""
        self.entry = entry
        self.userid = normalize_username(entry.data[CONF_USERID])
        self.api_key = entry.data[CONF_API_KEY]
        self.client = SetlistFmClient(
            async_get_clientsession(hass), self.api_key, self.userid
        )

        refresh_hours = entry.options.get("refresh_period", 6)

        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{self.userid}",
            update_interval=timedelta(hours=refresh_hours),
        )

    async def _async_update_data(self) -> AttendanceData:
        """Only replace the previous snapshot after all pages have succeeded."""
        try:
            return await self.client.async_get_attendance()
        except SetlistFmAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except SetlistFmError as err:
            raise UpdateFailed(str(err)) from err
