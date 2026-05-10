"""Backend validation helpers for trusted reference data."""

from __future__ import annotations

import re

from django.core.exceptions import ValidationError

from apps.common.reference_data.banks import is_valid_bank_code
from apps.common.reference_data.countries import is_valid_country_code
from apps.common.reference_data.locations import (
    get_states,
    is_valid_city_code,
    is_valid_lga_code,
    is_valid_state_code,
)
from apps.common.reference_data.normalizers import compact_text

_CUSTOM_CITY_RE = re.compile(r"^[A-Za-z0-9 .,'()/&-]{2,80}$")
_STREET_RE = re.compile(r"^[A-Za-z0-9 .,'#/()&-]{5,180}$")


def validate_country_code(value: str) -> str:
    code = compact_text(value).upper()
    if not code or not is_valid_country_code(code):
        raise ValidationError("Select a supported country.")
    return code


def validate_state_code(country_code: str, value: str) -> str:
    country = validate_country_code(country_code)
    state = compact_text(value)
    if not state:
        raise ValidationError("State is required.")
    if not get_states(country):
        raise ValidationError("State reference data is not configured for this country.")
    if not is_valid_state_code(country, state):
        raise ValidationError("Select a valid state for the selected country.")
    return state


def validate_lga_code(country_code: str, state_code: str, value: str) -> str:
    country = validate_country_code(country_code)
    state = validate_state_code(country, state_code)
    lga = compact_text(value)
    if not lga:
        raise ValidationError("Local government is required.")
    if not is_valid_lga_code(country, state, lga):
        raise ValidationError("Select a valid local government for the selected state.")
    return lga


def validate_city_or_custom_city(
    country_code: str,
    state_code: str | None = None,
    lga_code: str | None = None,
    city_code: str | None = None,
    custom_city: str | None = None,
) -> dict[str, str | None]:
    """Validate a listed city/area code or a sanitized city fallback.

    Custom free text is allowed only for city-level input. Country, state,
    LGA, and bank fields stay strict.
    """
    country = validate_country_code(country_code)
    state = compact_text(state_code) if state_code else None
    lga = compact_text(lga_code) if lga_code else None
    city = compact_text(city_code) if city_code else None
    custom = compact_text(custom_city) if custom_city else None

    if state:
        validate_state_code(country, state)
    if lga and state:
        validate_lga_code(country, state, lga)

    if city and is_valid_city_code(country, city, state_ref=state, lga_ref=lga):
        return {"city_code": city, "custom_city": None}

    if custom:
        if not _CUSTOM_CITY_RE.fullmatch(custom):
            raise ValidationError("Custom city contains unsupported characters.")
        return {"city_code": None, "custom_city": custom}

    raise ValidationError("Select a listed city or provide a custom city.")


def validate_street_address(value: str) -> str:
    street_address = compact_text(value)
    if not _STREET_RE.fullmatch(street_address):
        raise ValidationError("Enter a valid street address.")
    return street_address


def validate_bank_code(value: str, country_code: str = "NG") -> str:
    country = validate_country_code(country_code)
    bank_code = compact_text(value)
    if not bank_code or not is_valid_bank_code(bank_code, country):
        raise ValidationError("Select a valid bank for the selected country.")
    return bank_code

