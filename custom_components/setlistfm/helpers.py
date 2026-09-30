"""Shared helpers for the setlist.fm integration."""


def normalize_username(username: str) -> str:
    """Return the lowercase username expected by the setlist.fm API."""
    return username.strip().lower()
