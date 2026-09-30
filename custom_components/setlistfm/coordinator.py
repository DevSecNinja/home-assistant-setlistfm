"""Attendance snapshots and serialized refresh operations."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import AttendanceData, SetlistFmAuthError, SetlistFmClient, SetlistFmError
from .const import (
    CONF_API_KEY,
    CONF_REFRESH_PERIOD,
    CONF_USERID,
    DEFAULT_REFRESH_PERIOD,
    DOMAIN,
)
from .helpers import normalize_username

_LOGGER = logging.getLogger(__name__)

type SetlistFmConfigEntry = ConfigEntry[SetlistFmCoordinator]


class SetlistFmCoordinator(DataUpdateCoordinator[AttendanceData]):
    """Fetch all advertised pages before publishing a new snapshot."""

    def __init__(self, hass: HomeAssistant, entry: SetlistFmConfigEntry) -> None:
        self.entry = entry
        self.userid = normalize_username(entry.data[CONF_USERID])
        self.api_key = entry.data[CONF_API_KEY]
        self.client = SetlistFmClient(
            async_get_clientsession(hass), self.api_key, self.userid
        )
        self.last_successful_update: datetime | None = None
        self._refresh_lock = asyncio.Lock()
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN}_{self.userid}",
            update_interval=timedelta(
                hours=entry.options.get(CONF_REFRESH_PERIOD, DEFAULT_REFRESH_PERIOD)
            ),
        )

    async def _async_refresh(
        self,
        log_failures: bool = True,
        raise_on_auth_failed: bool = False,
        scheduled: bool = False,
        raise_on_entry_error: bool = False,
    ) -> None:
        """Serialize scheduled, setup, debounced and direct coordinator work."""
        async with self._refresh_lock:
            await super()._async_refresh(
                log_failures=log_failures,
                raise_on_auth_failed=raise_on_auth_failed,
                scheduled=scheduled,
                raise_on_entry_error=raise_on_entry_error,
            )

    async def async_manual_refresh(self) -> None:
        """Await this refresh and its result, without debouncer early returns."""
        # Hold the same lock through HA's data/error publication and inspection.
        # Locking only _async_update_data would let a later refresh change the result.
        async with self._refresh_lock:
            if self._shutdown_requested:
                raise HomeAssistantError(
                    translation_domain=DOMAIN,
                    translation_key="entry_unloaded",
                )
            await super()._async_refresh(log_failures=True)
            if self._shutdown_requested:
                raise HomeAssistantError(
                    translation_domain=DOMAIN,
                    translation_key="entry_unloaded",
                )
            if not self.last_update_success:
                raise HomeAssistantError(
                    translation_domain=DOMAIN,
                    translation_key="refresh_failed",
                    translation_placeholders={
                        "entries": self.entry.title,
                        "error": str(self.last_exception),
                    },
                ) from self.last_exception

    async def _async_update_data(self) -> AttendanceData:
        """Timestamp completed retrievals, not reads or partial failed requests."""
        try:
            data = await self.client.async_get_attendance()
        except SetlistFmAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except SetlistFmError as err:
            raise UpdateFailed(str(err)) from err
        self.last_successful_update = dt_util.utcnow()
        self.last_exception = None
        return data

    @callback
    def async_update_local_date(self, now: datetime) -> None:
        """Re-evaluate date-based entities at local midnight without an API call."""
        self.async_update_listeners()
