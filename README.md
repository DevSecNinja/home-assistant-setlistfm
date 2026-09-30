# Setlist.fm Integration for Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-c62828.svg)](https://github.com/hacs/integration)
[![version](https://img.shields.io/github/v/release/DevSecNinja/home-assistant-setlistfm?display_name=tag&sort=semver&color=blue&label=version)](https://github.com/DevSecNinja/home-assistant-setlistfm/releases/latest)
[![license](https://img.shields.io/github/license/DevSecNinja/home-assistant-setlistfm)](LICENSE)

This custom integration allows you to display your concert attendance data from [Setlist.fm](https://www.setlist.fm) in Home Assistant.

This is the maintained DevSecNinja fork, based on Ian Pleasance's integration.
Requires **Home Assistant 2025.1.0 or newer** for typed config-entry runtime data
and an explicit coordinator/config-entry relationship. Upgrades retain existing
Concerts entity IDs, custom names, options and device associations.

## Features

- ✅ **UI Configuration** - No YAML required! Configure through the Home Assistant UI
- ✅ **Async/Await** - Non-blocking API calls that won't freeze your Home Assistant
- ✅ **Multiple Users** - Add multiple Setlist.fm accounts
- ✅ **Flexible Filtering** - Show past concerts, upcoming concerts, or all
- ✅ **Customizable Display** - Choose date format and number of concerts to display
- ✅ **Automatic Updates** - Configurable refresh interval (1-24 hours)
- ✅ **Rate Limiting Protection** - Built-in retry logic for API rate limits
- ✅ **Proper Entity Registry** - Entities have unique IDs for proper HA integration
- ✅ **Bundled Community Cards** - Complete, Compact, Deluxe and Mobile cards with previews and a visual account selector; no dashboard YAML or manual JS resources

## Installation

### HACS (Recommended)

1. Open HACS in your Home Assistant instance
2. Click on "Integrations"
3. Click the three dots in the top right and select "Custom repositories"
4. Add `https://github.com/DevSecNinja/home-assistant-setlistfm` as an integration repository
5. Click "Install" on the Setlist.fm card
6. Restart Home Assistant

### Manual Installation

1. Download this fork and copy `custom_components/setlistfm` to your Home Assistant `custom_components` directory
2. Restart Home Assistant

## Configuration

### Getting Your Setlist.fm Credentials

1. **Username**:
   - Go to your Setlist.fm profile
   - Use the part after `/user/` in `https://www.setlist.fm/user/YOUR_USERNAME`, not the full URL or your display name
   - You can also find your username at the top right, next to **Add setlist**
   - Usernames are automatically converted to lowercase and surrounding spaces are removed, so `Blabla` becomes `blabla`

2. **API Key**:
   - Go to https://www.setlist.fm/settings/api
   - Request an API key (it's free!)
   - Copy the API key once approved

### Adding the Integration

1. Go to **Settings** → **Devices & Services**
2. Click **+ Add Integration**
3. Search for "Setlist.fm"
4. Enter your Username and API Key
5. (Optional) Enter a friendly name
6. Click **Submit**

Empty or whitespace-only usernames are rejected before any API request.
Setup checks access to the supported attended-concert endpoint, not account existence.
The entry title uses your optional friendly name, otherwise your normalized username;
the integration no longer requests a profile display name. See [API behavior and
coverage](#api-behavior-and-coverage) for empty-account and username-validation limits.

### Configuring Options

After adding the integration, you can configure options:

1. Go to **Settings** → **Devices & Services**
2. Find your Setlist.fm integration
3. Click **Configure**
4. Adjust the following options:
   - **Refresh Period**: How often to check for updates (1-24 hours, default: 6)
   - **Number of Concerts**: How many concerts to display (1-50, default: 10)
   - **Date Format**: Choose your preferred date format
     - `DD-MM-YYYY` (31-12-2024)
     - `DD-MM-YY` (31-12-24)
     - `MM-DD-YYYY` (12-31-2024)
     - `MM-DD-YY` (12-31-24)
   - **Show Concerts**: Filter which concerts to display
     - `All concerts` - Show both past and upcoming
     - `Upcoming only` - Only show future concerts
     - `Past only` - Only show attended concerts

## Entities Created

Each user gets one service device, linked to their setlist.fm profile, with four
sensors and one button. Open it through **Settings → Devices & Services →
setlist.fm → your device**. These are standard Home Assistant entities, usable
with the visual dashboard card/entity picker; no replacement device screen is needed.

| Entity | Meaning |
| --- | --- |
| Concerts | Count after your date filter and display limit; retains the existing unique ID and attributes |
| Total concerts | Authoritative API total before filtering, or **unknown** when not supplied |
| Next concert | Date of the earliest returned setlist on/after today, with `artist`, `venue`, `url`, `complete` and `completeness_reason` attributes |
| Last successful update | Diagnostic timestamp of the last completed retrieval, with `last_update_success` and an optional `last_error` |
| Refresh | Configuration button; waits for a real refresh and reports failures, also usable to retry a failed connection |

The Concerts sensor retains `concerts`, `concert_list`, `last_updated`,
`last_update_success`, optional `last_error`, and the [coverage attributes](#coverage-metadata).
Its displayed count is not a measurement or a monotonically increasing counter,
so it no longer advertises a long-term-statistics state class.

Next concert uses the **full fetched dataset**, not the display filter or limit.
No matching setlist gives **unknown**, not a claim that you have no future bookings.
Dates and display filters re-evaluate at local midnight without an API request.
All four sensors become **unavailable** on a failed retrieval; the previous
snapshot and successful timestamp remain in memory until recovery. A restart or
entry reload begins with no timestamp until the first successful retrieval.

`last_updated` and Last successful update share one timezone-aware timestamp.
Reading attributes never changes it. A failed later page does not advance it.
A completed retrieval can still have `complete: false` (ambiguous first-page
404 or skipped records): the timestamp means the fetch completed, **not** that
the attendance history is complete.

**Entity IDs are generated by Home Assistant from device/entity names and may
be customized; they do not inherently start with `sensor.setlistfm_`.** Find the
actual IDs in entity settings. All example IDs below are placeholders; replace
each full ID, rather than just substituting your username. Existing registered
Concerts IDs are preserved.

## Services

### `setlistfm.refresh`

Refresh concert data and wait for the result. The per-user Refresh button is
usually easier than supplying an entry ID. Requests remain subject to API pacing
and cooldowns; repeated or concurrent actions are serialized with scheduled polls.

| Field | Required | Description |
|-------|----------|-------------|
| `entry_id` | No | A loaded setlist.fm entry; omission refreshes all loaded entries. |

Use the entry picker in **Developer Tools → Actions → setlistfm.refresh**.
An empty, unknown, foreign or unloaded explicit ID is rejected, never interpreted
as "all". No loaded entries is an error. All-target refresh attempts every loaded
entry and reports any failures. The action remains registered across entry unloads
and setup failures.

**Example — refresh a specific entry**:
```yaml
service: setlistfm.refresh
data:
  entry_id: abc123def456abc123def456abc123de
```

**Example — refresh all entries**:
```yaml
service: setlistfm.refresh
```

**Example automation**:
```yaml
automation:
  - alias: "Refresh Setlist.fm Daily"
    trigger:
      - platform: time
        at: "06:00:00"
    action:
      - service: setlistfm.refresh
```

## Usage Examples

### Community cards (no YAML)

Edit a dashboard and choose **Add card > By cards > Community**, then search for **setlist.fm**. Choose **Complete**, **Compact**, **Deluxe** or **Mobile** and select your account's concerts entity in the visual editor. The integration automatically loads these cards after installation and a Home Assistant restart.

These are individual cards, not full dashboard views. They support multiple accounts, renamed entities, HA themes and mobile layouts. They show the integration's filtered and capped display list, not your complete attendance history. See [CARDS.md](CARDS.md) for options, update behavior and limitations.

### Display in Lovelace

The following YAML examples remain an optional alternative.

**Simple Markdown Card**:
```yaml
type: markdown
content: |
  ## 🎵 My Concerts
  {{ state_attr('sensor.setlistfm_yourname_concerts', 'concert_list') }}
```

**Entities Card**:
```yaml
type: entities
entities:
  - sensor.setlistfm_yourname_concerts
  - sensor.yourname_total_concerts
  - sensor.yourname_next_concert
  - sensor.setlistfm_yourname_last_update
  - button.yourname_refresh
```

**Quick Upcoming Concerts**:
```yaml
type: markdown
title: 🎤 Upcoming Shows
content: |
  {% set concerts = state_attr('sensor.setlistfm_yourname_concerts', 'concert_list') or '' %}
  {% set upcoming = concerts.split('\n') | select('search', 'Upcoming') | list %}
  {% for concert in upcoming %}
  🔜 {{ concert.replace('(Upcoming)', '') }}
  {% endfor %}
```

For more dashboard examples see [DASHBOARDS.md](DASHBOARDS.md).

### Automation Example

Send a notification when you have an upcoming concert:

```yaml
automation:
  - alias: "Upcoming Concert Reminder"
    trigger:
      - platform: state
        entity_id: sensor.setlistfm_yourname_concerts
    condition:
      - condition: template
        value_template: >
          {{ 'Upcoming' in (state_attr('sensor.setlistfm_yourname_concerts', 'concert_list') or '') }}
    action:
      - service: notify.mobile_app
        data:
          title: "Concert Reminder"
          message: >
            You have upcoming concerts!
            {{ state_attr('sensor.setlistfm_yourname_concerts', 'concert_list') }}
```

## Migration from v1.x

If you were using the old YAML-based version:

1. **Backup your configuration** - Copy your YAML config before removing it
2. **Install the new version** - Follow installation steps above
3. **Remove YAML configuration** - Delete the `setlistfm:` section from `configuration.yaml`
4. **Add via UI** - Configure through the UI as described above
5. **Update automations** - Use the actual registered sensor IDs. Old YAML `text`
   entities are not automatically migrated. The old response sensor is replaced by
   diagnostic attributes. UI-configured Concerts entities keep their existing IDs.

## Reauthentication and Removal

When an API key is rejected, Home Assistant offers **Reconfigure** on the existing
entry. Enter a replacement key in the masked field. A successful validation updates
and reloads that same entry without changing its username, options, title or entity
and device associations. Connection errors, rate limits and unexpected responses
remain visible so you can retry; do not delete the account to change a rejected key.

To remove an account, use its three-dot menu in **Settings → Devices & Services →
setlist.fm → Delete**. Home Assistant removes its entities and device association;
local polling and midnight listeners stop. This does not alter your setlist.fm
account or revoke the API key. Other users and the shared refresh action remain.

## Troubleshooting

### "Invalid API Key" Error
- Verify your API key is correct
- Check if your API key has been approved by Setlist.fm
- Request a new API key if needed

### "User Not Found" Error
Current versions no longer claim that an attendance response proves a username is
invalid. If an older version reports this error, upgrade. For an empty result, verify
the username from your profile URL (capitalization is handled automatically).

### No Concerts Showing
- Check your filter settings (upcoming/past/all)
- Verify you have concerts logged on Setlist.fm

### Upcoming Concerts not Showing

The integration can only show future-dated setlists that the attended API returns.
It is not a full concert schedule, and no fixed future-availability window is
documented or guaranteed.

### Rate Limiting
- Each request has a 20-second timeout and at most 3 attempts, with backoff.
- Requests are paced at least one second apart per integration entry.
- Valid `Retry-After` seconds or HTTP dates are respected. Delays above 30 seconds
  end the refresh rather than keeping setup or polling waiting; the client refuses
  further requests during its cooldown. Without valid guidance, a 429 starts a
  60-second cooldown without an immediate retry.
- Default refresh is 6 hours to avoid rate limits
- Consider increasing the refresh period if you hit rate limits frequently
- Pacing is per entry, not a global quota manager; other applications or entries
  using the same key also consume its quota. Cooldowns are in memory.

## API Behavior and Coverage

The integration uses [`GET /user/{userId}/attended`](https://api.setlist.fm/docs/1.0/resource__1.0_user__userId__attended.html)
for setup and polling. The deprecated [user-profile endpoint](https://api.setlist.fm/docs/1.0/resource__1.0_user__userId_.html)
always returns a result, even for nonexistent users, and is not used.

A metadata-confirmed empty response (`total: 0`, empty `setlist`) is accepted.
The published attended endpoint and Swagger definition do not specify how a valid
zero-attendance account differs from an unknown username. No authenticated live
checks were performed, and no public recorded empty/unknown response pair was
verified. A first-page HTTP 404 is therefore accepted during setup as **ambiguous
no attendance**, not proof of account existence or nonexistence. It produces an
empty list with an **unknown total** and `complete: false`. Check the username
yourself if this persists. Other service, authentication and malformed-response
errors remain errors, not empty successes.

All pages advertised by `total`, `page` and `itemsPerPage` are requested using `p`,
before local date sorting, filtering and the 1-50 display limit. The integration
does not assume API sort order. Inconsistent metadata, repeated IDs, short/repeated
pages and failures on later pages fail the refresh and retain the previous
successful snapshot; entities become unavailable until recovery. A malformed
individual concert is instead skipped with an aggregate warning and explicit
incomplete coverage, allowing valid concerts to remain useful.

No attended-endpoint 1,000-result hard limit was verified in the public API
documentation. The client therefore does not impose one. A defensive limit of
1,000 **pages** fails the refresh explicitly, rather than silently truncating.
Any upstream refusal of a required page also fails the refresh. Pagination cannot
guarantee a transactionally consistent snapshot if upstream records change between
requests without detectable changes to totals or IDs.

The existing simplified `concerts` attribute remains
`id/date/artist{name,mbid}/venue{name,city,state,country}/song_count/url`.
Missing optional location fields use empty strings; missing names use `Unknown`.
Attribution URLs are retained and should be linked in dashboards.
Song counting supports both the [documented top-level `set` array](https://api.setlist.fm/docs/1.0/json_Setlist.html)
and the nested `sets.set` shape found in
[historical public production recordings](https://github.com/zschumacher/setlist-fm-client/blob/2b492a6fc940a484e3e4b6461a5057111ed44004/tests/cassettes/TestGetSetlist.test%5BAccept.json0%5D.yaml#L18-L36).
When both occur, the documented `set` field wins (including an empty array);
they are never counted twice. Test fixtures are synthetic examples of these shapes.

### Coverage metadata

| Concert sensor attribute | Meaning |
| --- | --- |
| `total_attended` | Upstream total before display filtering; `null` when unknown |
| `fetched_count` | Number of valid, unique concerts available before filtering |
| `skipped_count` | Invalid individual records omitted from the fetched pages |
| `complete` | Whether every advertised concert is available as a valid record |
| `completeness_reason` | `null`, `attendance_not_found`, or `invalid_records` |

For integration developers, `coordinator.data["concerts"]` contains the full
unfiltered API-style concert list with normalized optional fields and canonical
`set` arrays. The coordinator exposes the same metadata, naming the upstream
count `total` instead of `total_attended`, plus `pages_fetched`. There is no `user`
profile object. A successful transport refresh with `complete: false` must not
be described as a complete attendance history.

Runtime access is through the typed `entry.runtime_data` coordinator, not a
per-entry `hass.data` dictionary. `last_successful_update` is the shared UTC
timestamp; `async_manual_refresh()` is the error-aware, awaited operation for
manual controls. Unique IDs use the entry ID plus `_concerts`, `_total_concerts`,
`_next_concert`, `_last_update` and `_refresh`, with device identifiers unchanged.

### Enable Debug Logging

Add to `configuration.yaml`:
```yaml
logger:
  default: info
  logs:
    custom_components.setlistfm: debug
```

Then restart and check: **Settings → System → Logs**

## Development

Run the regression tests on Linux (including WSL) with Python 3.14. The test
dependencies pin Home Assistant 2026.9.4; they are not runtime requirements for
installing this integration.

```bash
python -m pip install -r requirements-test.txt
python -m pytest
```

The CI matrix also runs the suite on Python 3.13 with
`requirements-test-min.txt` (Home Assistant 2025.1.4). Use a separate environment
for that historical check. Its test-only pycares 4.5 pin prevents a newer DNS
library's persistent cleanup thread from conflicting with the historical test
fixtures; neither runtime requirements nor the latest test pin are changed.

The [local mock API](devtools/setlistfm_mock/README.md) provides a loopback-only
aiohttp server, synthetic datasets, fault scenarios and real HTTP wire tests.
It needs no live API key and does not change the production endpoint or normal
integration installation.

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for full version history.

## Support

- **Issues**: [GitHub Issues](https://github.com/DevSecNinja/home-assistant-setlistfm/issues)

## Credits

- Original version by [@ianpleasance](https://github.com/ianpleasance)
- Fork maintenance by [@DevSecNinja](https://github.com/DevSecNinja)

## License

This project is licensed under the Apache 2.0 License.
