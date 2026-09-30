# Bundled setlist.fm cards

The integration includes four **individual cards**, inspired by the optional YAML dashboards. They use one local, dependency-free web component implementation. They do not install or replace a dashboard view.

## Add a card without YAML

1. Install/update the integration and restart Home Assistant.
2. Configure at least one setlist.fm account under **Settings > Devices & services** and allow its first refresh to finish.
3. Open a dashboard you can edit, choose **Edit dashboard > Add card > By cards** (**By card** in some versions), then find the **Community** section (or search for `setlist.fm`).
4. Pick **setlist.fm Complete**, **Compact**, **Deluxe**, or **Mobile**.
5. In the visual editor, select **Account / concerts entity**. The preview uses that account's available records. Adjust the title, filter, section limit, location and song-count options, then save.

No separate frontend repository, CDN, JavaScript resource configuration, or YAML copying is required. A freshly added account with no available records shows explanatory guidance instead of invented sample concerts.

| Preset | Presentation |
| --- | --- |
| Complete | Next available show, more upcoming dates, recent concerts and display-list counts |
| Compact | A small next-show highlight and a short artist/date/link recent list; venue/location details appear in the highlight |
| Deluxe | A larger featured show, detailed lists and upcoming/past counts within the available records |
| Mobile | A single-column layout with touch-sized links and controls |

All presets follow Home Assistant theme colors and typography, adapt to narrow widths, and work in masonry and sections dashboards. Wide Complete and Deluxe cards arrange lists in two columns. The editor uses labeled native controls with keyboard support. **Account details** opens the selected sensor's Home Assistant more-info dialog. Setlist links open safely in a new tab.

## Accounts, dates and limits

The selector recognizes the concerts data contract, not a `sensor.setlistfm_` naming prefix. Multiple accounts and renamed entity IDs work. If you rename an entity after saving a card, reselect it in the editor: Home Assistant does not necessarily rewrite custom-card configurations. If an account is temporarily unavailable, its saved selection is retained.

Cards use the existing `concerts` array (`date` in `dd-MM-yyyy`, artist, venue, song count and URL), `last_updated`, and `last_update_success`. They do not parse `concert_list` text for presentation or need new total/date entities. The next show is the **earliest upcoming record in the available list**, with today's date counted as upcoming. Date boundaries use **Home Assistant's configured time zone**, even if the browser is elsewhere.

The integration's **Show concerts** and **Number of concerts** options filter and cap the source list before a card sees it. Card options can narrow that list further but cannot recover omitted records. A section limit applies separately to the more-upcoming and recent lists, in addition to the featured next show. Compact intentionally shows only one upcoming show. Counts describe the available list, **not lifetime attendance**; an empty response does not prove zero attendance. Upcoming coverage is limited by setlist.fm, with no guaranteed future-date window. Song counts are songs listed in a setlist, not predictions.

Unavailable data, unknown/loading states, missing entities, invalid records and failed updates have distinct messages. The card does not display raw API errors or credentials. API text is always inserted as text, never HTML. Only HTTP(S) links on `setlist.fm` or `www.setlist.fm` are accepted, and accepted HTTP URLs are upgraded to HTTPS.

## Installation and updates

Tested with **Home Assistant 2026.9.4**; see [INSTALL.md](INSTALL.md) and `hacs.json` for the integration's supported minimum. Entity-specific suggestions under **By entity** are optional and available in HA 2026.6 and later. The normal **By cards** workflow does not depend on suggestions.

The integration registers a single bundled JavaScript file through HA's asynchronous static-path API and public frontend module loader. The module waits for HA's own card element in the active browser registry before publishing its card types, avoiding HA's bootstrap registry replacement race. Its content hash changes the resource URL on updates. Restart HA after upgrading and reload open browser/Companion App views to load the new custom-element definitions. Only the JavaScript asset is publicly served, not the integration's source or account data. There are no API credentials in the bundle.

Account reloads and removal do not unregister the shared card types for the running HA instance. Saved cards remain on the dashboard and show a missing/unavailable-account message when appropriate. If you remove every account and restart HA (so the integration no longer loads), or uninstall the integration, its card definitions will no longer be loaded; remove those cards or reinstall/reconfigure the integration.

If cards do not appear, confirm the integration is installed and loaded, restart HA, and reload the browser. Inspect HA logs for frontend setup errors. Do not add a duplicate manual resource as a workaround.

## Optional YAML

The existing `DASHBOARD_COMPLETE.yaml`, `DASHBOARD_COMPACT.yaml`, `DASHBOARD_DELUXE.yaml`, `DASHBOARD_MOBILE.yaml` and [DASHBOARDS.md](DASHBOARDS.md) examples remain optional dashboard-view templates. They are not required by these cards and may include separately installed custom cards. Replace example entity IDs with your actual IDs.

Advanced users can also configure an individual bundled card as YAML:

```yaml
type: custom:setlistfm-complete-card
entity: sensor.alex_concerts
title: My concerts
filter: all
limit: 5
show_location: true
show_songs: true
```

Use `setlistfm-compact-card`, `setlistfm-deluxe-card` or `setlistfm-mobile-card` for the other presets. `filter` accepts `all`, `upcoming` or `past`; `limit` is an integer from 1 to 50. Never put your API key in a dashboard.

## Development verification

The runtime bundle needs no build step. Browser-test tooling is development-only:

```text
npm ci
npx playwright install chromium
npm test
```

Playwright runs the real web components in Chromium against a local HA-themed fixture: discovery metadata, visual-editor events and keyboard actions, exact entity selection, dates/time zones, hostile text/URLs, lifecycle, states and responsive light/dark layouts. Layout tests save screenshots in `test-results` (or `PLAYWRIGHT_OUTPUT_DIR`). The fixture is explicitly **not the actual HA card picker**; discovery metadata tests alone do not demonstrate end-to-end picker operation.

Run `python -m pytest` in the supported Linux/Python test environment with `requirements-test.txt` installed. Frontend backend tests cover public module registration, concurrent/repeated setup, retry failures, content-hash cache busting and serving the asset through HA's real HTTP implementation.

### Reproducible real Home Assistant picker smoke

The opt-in `tests/test_live_frontend.py` host and `npm run test:ha` browser driver exercise the **actual HA 2026.9.4 frontend**, not the themed fixture. Install the latest `requirements-test.txt` environment and the browser tools above. From the repository root, use two terminals with `SETLISTFM_LIVE_DIR` pointing to the same **new, empty, temporary directory**:

```text
# Terminal 1 (Linux / supported HA Python): set SETLISTFM_LIVE_DIR, then
python -m pytest tests/test_live_frontend.py -q -s

# Terminal 2 (Node/Chromium): set SETLISTFM_LIVE_DIR, then
npm run test:ha
```

On Windows/WSL, Python uses the Linux spelling of that shared directory, and Node uses the Windows spelling. WSL loopback forwarding must be enabled. The Python host waits up to five minutes; the browser waits up to one minute for the host.

The host uses an isolated HA test config, synthetic authentication and two renamed sensor states, an in-memory recorder, and only the explicit frontend/Lovelace shell components. No `default_config`, discovery scanning, real account or live API key is used. Backend HTTP calls are mocked and asserted absent; unrelated brand artwork and HA's built-in card demo images are served as local placeholder SVGs. Screenshots and `live-result.json` are saved in the supplied directory. The temporary `live-host.json` contains synthetic local auth and is removed on normal teardown; remove it if you interrupt the host.

The smoke verifies four visible Community presets, the real editor's account selection and empty preview, title/filter/limit/song options, saving the card, rendering after reload, and absence of browser errors. Python additionally checks the saved Lovelace storage. The host is skipped in the normal suite; use the latest HA environment, not the minimum-version compatibility environment, for this UI smoke.
