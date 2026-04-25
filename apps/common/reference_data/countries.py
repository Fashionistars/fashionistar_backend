"""Country reference data built at module import time."""

from __future__ import annotations

from functools import lru_cache
from typing import Any

import phonenumbers

from apps.common.reference_data.normalizers import compact_text, flag_emoji

COUNTRY_NAME_OVERRIDES: dict[str, str] = {
    "AE": "United Arab Emirates",
    "CA": "Canada",
    "CN": "China",
    "DE": "Germany",
    "FR": "France",
    "GB": "United Kingdom",
    "GH": "Ghana",
    "IE": "Ireland",
    "IN": "India",
    "IT": "Italy",
    "KE": "Kenya",
    "NG": "Nigeria",
    "NL": "Netherlands",
    "RW": "Rwanda",
    "SN": "Senegal",
    "TZ": "Tanzania",
    "UG": "Uganda",
    "US": "United States",
    "ZA": "South Africa",
}


@lru_cache(maxsize=1)
def get_countries() -> list[dict[str, Any]]:
    """Return active phone-capable countries in a deterministic order."""
    countries: list[dict[str, Any]] = []
    for code in sorted(phonenumbers.SUPPORTED_REGIONS):
        phone_code = phonenumbers.country_code_for_region(code)
        if not phone_code:
            continue
        countries.append(
            {
                "id": code,
                "code": code,
                "name": COUNTRY_NAME_OVERRIDES.get(code, code),
                "flag": flag_emoji(code),
                "phone_code": f"+{phone_code}",
                "is_active": True,
            }
        )
    countries.sort(key=lambda item: (item["name"] != "Nigeria", item["name"]))
    return countries


@lru_cache(maxsize=1)
def _country_index() -> dict[str, dict[str, Any]]:
    return {country["code"].upper(): country for country in get_countries()}


def get_country(country_code: str) -> dict[str, Any] | None:
    """Return a country by ISO code, or None."""
    return _country_index().get(compact_text(country_code).upper())


def is_valid_country_code(country_code: str) -> bool:
    """Return whether the supplied country code is in our reference set."""
    return get_country(country_code) is not None

