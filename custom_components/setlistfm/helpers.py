"""Shared helpers for the setlist.fm integration."""

from datetime import datetime
from typing import Any


def normalize_username(username: str) -> str:
    """Return the lowercase username expected by the setlist.fm API."""
    return username.strip().lower()


def normalize_concert(record: Any) -> tuple[dict[str, Any], bool]:
    """Validate a concert and repair unusable optional fields without losing it."""
    if (
        not isinstance(record, dict)
        or not isinstance(record.get("id"), str)
        or not record["id"]
        or not isinstance(record.get("eventDate"), str)
    ):
        raise ValueError("Concert is missing an ID or event date")
    datetime.strptime(record["eventDate"], "%d-%m-%Y")
    repaired = False

    def mapping(value: Any) -> dict[str, Any]:
        nonlocal repaired
        if value is None:
            return {}
        if not isinstance(value, dict):
            repaired = True
            return {}
        return value

    def text(value: Any, default: str = "") -> str:
        nonlocal repaired
        if value is None:
            return default
        if not isinstance(value, str):
            repaired = True
            return default
        return value

    artist = mapping(record.get("artist"))
    venue = mapping(record.get("venue"))
    city = mapping(venue.get("city"))
    country = mapping(city.get("country"))
    # Prefer the documented representation, even when empty, never sum both.
    sets = record.get("set") if "set" in record else mapping(record.get("sets")).get("set")
    if sets is None:
        sets = []
    elif not isinstance(sets, list):
        repaired = True
        sets = []
    clean_sets = []
    for item in sets:
        if not isinstance(item, dict):
            repaired = True
            continue
        songs = item.get("song")
        if songs is None:
            songs = []
        elif not isinstance(songs, list):
            repaired = True
            songs = []
        clean_songs = [song for song in songs if isinstance(song, dict)]
        repaired |= len(clean_songs) != len(songs)
        clean_sets.append({**item, "song": clean_songs})

    return {
        **record,
        "artist": {
            **artist,
            "name": text(artist.get("name"), "Unknown"),
            "mbid": text(artist.get("mbid")) or None,
        },
        "venue": {
            **venue,
            "name": text(venue.get("name"), "Unknown"),
            "city": {
                **city,
                "name": text(city.get("name")),
                "state": text(city.get("state")),
                "country": {**country, "name": text(country.get("name"))},
            },
        },
        "set": clean_sets,
        "url": text(record.get("url")),
    }, repaired
