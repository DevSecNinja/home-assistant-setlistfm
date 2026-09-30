# Quick Start Installation Guide

## Prerequisites

- Home Assistant 2025.1.0 or newer (typed runtime data and explicit coordinator entry)
- Setlist.fm account
- Setlist.fm API key ([get one here](https://www.setlist.fm/settings/api))

## Installation Steps

### 1. Install the Integration

**Option A: Manual Installation**
```bash
# Copy the setlistfm folder to your custom_components directory
cd /config
mkdir -p custom_components
cp -r /path/to/home-assistant-setlistfm/custom_components/setlistfm custom_components/
```

**Option B: HACS Installation**
1. Open HACS
2. Go to Integrations
3. Click ⋮ → Custom repositories
4. Add: `https://github.com/DevSecNinja/home-assistant-setlistfm`
5. Category: Integration
6. Install "Setlist.fm"

### 2. Restart Home Assistant
```bash
# Restart Home Assistant to load the integration
```

### 3. Get Your Credentials

**Username**:
1. Go to your Setlist.fm profile
2. Look at the URL: `https://www.setlist.fm/user/YOUR_USERNAME`
3. Copy only `YOUR_USERNAME`, not the full URL or your display name. It is also shown at the top right next to **Add setlist**
4. Capitalization and surrounding spaces are handled automatically: `Blabla` becomes `blabla`

**API Key**:
1. Visit https://www.setlist.fm/settings/api
2. Request an API key and wait for approval if needed
3. Copy your API key

### 4. Add the Integration

1. In Home Assistant, go to **Settings** → **Devices & Services**
2. Click **+ Add Integration**
3. Search for **Setlist.fm**
4. Fill in the form:
   - **Username**: Your Setlist.fm profile username
   - **API Key**: Your API key
   - **Name** (optional): A friendly name (e.g., "John")
5. Click **Submit**

### 5. Configure Options (Optional)

1. In Devices & Services, find your Setlist.fm integration
2. Click **Configure**
3. Adjust settings:
   - **Refresh Period**: 1-24 hours (default: 6)
   - **Number of Concerts**: 1-50 (default: 10)
   - **Date Format**: DD-MM-YYYY, MM-DD-YYYY, etc.
   - **Show Concerts**: All / Upcoming only / Past only

### 6. Verify It's Working

Open the user's service device and check the four sensors **Concerts**, **Total
concerts**, **Next concert** and diagnostic **Last successful update**, plus the
**Refresh** button under configuration controls. The device links to the user's
setlist.fm profile. Unknown totals/dates are not zero; unavailable sensors mean
the latest retrieval failed. The button can retry a failed connection.

## First Use

### View Your Concerts

Add a card to your dashboard:

```yaml
type: markdown
title: My Concerts
content: |
  {{ state_attr('sensor.setlistfm_yourname_concerts', 'concert_list') }}
```

Replace each **entire entity ID** in examples with the ID in your entity settings.
HA generates IDs from names and translations; there is no guaranteed `setlistfm_`
prefix. Existing Concerts IDs and custom names are preserved on upgrade.
Alternatively, use **Edit dashboard → Add card → Entities** and select the entities
visually, without YAML.

### Check Status

Add an entities card:

```yaml
type: entities
title: Setlist.fm Status
entities:
  - sensor.setlistfm_yourname_concerts
  - sensor.yourname_total_concerts
  - sensor.yourname_next_concert
  - sensor.setlistfm_yourname_last_update
  - button.yourname_refresh
```

## Troubleshooting

### Integration Not Showing Up
- Verify files are in `/config/custom_components/setlistfm/`
- Check logs: Settings → System → Logs
- Restart Home Assistant again

### "Invalid API Key" Error
- Verify your API key is correct (copy/paste carefully)
- Check your API key is approved on Setlist.fm
- Make sure there are no extra spaces
- Use Home Assistant's reauthentication prompt to replace a rejected key. It
  preserves this account and its existing entities; do not delete/re-add it.

### Refresh and Removal

Press the device's **Refresh** button or use **Developer Tools → Actions →
setlistfm.refresh**, selecting a loaded entry. Leaving the entry field omitted
refreshes all loaded accounts; an invalid explicit target is an error. These
controls wait for the actual result and respect API cooldowns.

Delete an account from its integration entry menu to stop polling and remove its
HA entities. No setlist.fm data is deleted. See [reauthentication and
removal](README.md#reauthentication-and-removal).

### Empty Attendance or an Unknown Total
- Verify your username is correct (capitalization is handled automatically).
- Use only the username from `setlist.fm/user/YOUR_USERNAME`.
- Setup checks the attended endpoint, not account existence. A first-page 404 is
  ambiguous: setup accepts it, but the total remains unknown and coverage incomplete.
  A metadata-confirmed empty account has total zero and complete coverage.
- See [API behavior and coverage](README.md#api-behavior-and-coverage) for limitations.

### No Concerts Showing
- Check you have concerts logged on Setlist.fm
- Check the filter settings (All/Upcoming/Past)
- Check `total_attended`, `fetched_count`, `complete`, and `completeness_reason`
  to distinguish display filtering from unknown or incomplete attendance.

### Enable Debug Logging

Add to `configuration.yaml`:
```yaml
logger:
  default: info
  logs:
    custom_components.setlistfm: debug
```

Then restart and check: Settings → System → Logs

## Next Steps

- [Read the full README](README.md) for detailed features
- [Check usage examples](README.md#usage-examples)
- [Set up automations](README.md#automation-example)
- [Report an issue](https://github.com/DevSecNinja/home-assistant-setlistfm/issues)

## Getting Help

1. Check [Troubleshooting](README.md#troubleshooting)
2. Search [existing issues](https://github.com/DevSecNinja/home-assistant-setlistfm/issues)
3. Enable debug logging and check logs
4. [Open a new issue](https://github.com/DevSecNinja/home-assistant-setlistfm/issues/new) with:
   - Home Assistant version
   - Integration version
   - Relevant logs (with API key redacted!)
   - Steps to reproduce

## Multiple Users

To add multiple Setlist.fm accounts:

1. Go to **Settings** → **Devices & Services**
2. Click **+ Add Integration** again
3. Search for **Setlist.fm**
4. Add the second user's credentials
5. Repeat for each user

Each user gets their own sensors and can have different settings!

## Migrating from v1.x?

See [Migration from v1.x](README.md#migration-from-v1x) for the old YAML-based version.
