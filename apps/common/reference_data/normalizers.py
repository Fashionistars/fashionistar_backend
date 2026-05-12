"""Small normalization helpers for reference data."""

from __future__ import annotations

import re

_NON_CODE_CHARS = re.compile(r"[^a-z0-9]+")
_MULTI_SPACES = re.compile(r"\s+")


def compact_text(value: object) -> str:
    """Normalize user/display text without destroying readable casing."""
    return _MULTI_SPACES.sub(" ", str(value or "").strip())


def code_slug(value: object) -> str:
    """Return a stable uppercase code from a display name."""
    text = compact_text(value).lower()
    return _NON_CODE_CHARS.sub("-", text).strip("-").upper()


def flag_emoji(country_code: str) -> str:
    """Return an ISO-3166 flag emoji from a two-letter country code."""
    code = compact_text(country_code).upper()
    if len(code) != 2 or not code.isalpha():
        return ""
    return "".join(chr(127397 + ord(char)) for char in code)

