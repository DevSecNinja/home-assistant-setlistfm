"""Opt-in real HA picker smoke host; pair with tests/frontend/live-smoke.js."""

import asyncio
from datetime import timedelta
import json
import os
from pathlib import Path

import pytest
from homeassistant.components import websocket_api
from homeassistant.components.energy.websocket_api import ws_get_prefs
from homeassistant.components.lovelace import LOVELACE_DATA
from homeassistant.helpers.storage import Store
from homeassistant.setup import async_setup_component
from homeassistant.util import dt as dt_util

from custom_components.setlistfm import async_setup

pytestmark = pytest.mark.skipif(
    not os.environ.get("SETLISTFM_LIVE_DIR"),
    reason="Opt-in browser smoke; see CARDS.md",
)


@pytest.fixture
def mock_recorder_before_hass(async_test_recorder):
    """Initialize recorder test patches before the HA fixture is constructed."""


async def test_live_picker(
    recorder_mock,
    hass,
    hass_client,
    hass_access_token,
    aioclient_mock,
):
    """Run the real frontend on loopback, with no default_config or live API."""
    artifacts = Path(os.environ["SETLISTFM_LIVE_DIR"])
    await hass.async_add_executor_job(artifacts.mkdir, 0o700, True, True)
    host_path = artifacts / "live-host.json"
    result_path = artifacts / "live-result.json"
    await hass.async_add_executor_job(result_path.unlink, True)
    hass.config.time_zone = "Europe/Amsterdam"
    hass.config.skip_pip = True
    await Store(hass, 1, "lovelace").async_save(
        {"config": {"views": [{"title": "Concerts", "path": "concerts", "cards": []}]}}
    )
    for component in (
        "frontend", "lovelace", "api", "labs", "persistent_notification",
        "brands", "config",
    ):
        assert await async_setup_component(hass, component, {})
    assert await async_setup(hass, {})
    # The card picker queries optional energy preferences even without energy.
    # Register its real read-only handler without starting energy or discovery.
    websocket_api.async_register_command(hass, ws_get_prefs)
    if "onboarding" in hass.data:
        hass.data["onboarding"].onboarded = True

    today = dt_util.as_local(dt_util.utcnow()).date()
    hass.states.async_set("sensor.alex_renamed_concerts", "2", {
        "friendly_name": "Alex's concerts",
        "concert_list": "",
        "attribution": "Data provided by setlist.fm",
        "last_update_success": True,
        "concerts": [
            {
                "id": "future", "date": (today + timedelta(days=2)).strftime("%d-%m-%Y"),
                "artist": {"name": "Future Fixture Band"},
                "venue": {"name": "Example Hall", "city": "Utrecht", "country": "Netherlands"},
                "song_count": 19, "url": "https://www.setlist.fm/setlist/example.html",
            },
            {
                "id": "past", "date": (today - timedelta(days=1)).strftime("%d-%m-%Y"),
                "artist": {"name": "Recent Fixture Band"},
                "venue": {"name": "Example Club", "city": "Amsterdam", "country": "Netherlands"},
                "song_count": 12, "url": "https://www.setlist.fm/setlist/example.html",
            },
        ],
    })
    hass.states.async_set("sensor.sam_renamed_concerts", "0", {
        "friendly_name": "SAM Concerts", "concert_list": "", "concerts": [],
    })
    client = await hass_client()
    url = str(client.make_url("/"))
    assert client.host == "127.0.0.1"
    try:
        await hass.async_add_executor_job(
            host_path.write_text,
            json.dumps({"url": url, "access_token": hass_access_token}),
        )
        print("Local HA picker ready; run npm run test:ha with the same SETLISTFM_LIVE_DIR.", flush=True)
        async with asyncio.timeout(300):
            while not await hass.async_add_executor_job(result_path.exists):
                await asyncio.sleep(0.25)
        result = json.loads(await hass.async_add_executor_job(result_path.read_text))
        assert result["ok"], result
        assert result["errors"] == []
        dashboards = hass.data[LOVELACE_DATA].dashboards
        dashboard = dashboards.get("lovelace", dashboards[None])
        storage_key = f"lovelace.{dashboard.config['id']}" if dashboard.config else "lovelace"
        saved = await Store(hass, 1, storage_key).async_load()
        card = saved["config"]["views"][0]["cards"][0]
        assert card["type"] == "custom:setlistfm-complete-card"
        assert card["entity"] == "sensor.alex_renamed_concerts"
        assert card["title"] == "My live music"
        assert card["filter"] == "past"
        assert card["limit"] == 3
        assert card["show_songs"] is False
        assert aioclient_mock.call_count == 0
    finally:
        await hass.async_add_executor_job(host_path.unlink, True)
