"""Country/state/LGA/city reference lookups."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from apps.common.reference_data.countries import is_valid_country_code
from apps.common.reference_data.normalizers import code_slug, compact_text

DATA_DIR = Path(__file__).resolve().parent / "data"
NIGERIA_COUNTRY_CODE = "NG"

STATE_CODE_OVERRIDES = {
    "FEDERAL CAPITAL TERRITORY": "FCT",
    "FCT": "FCT",
}


def _state_code(name: str) -> str:
    return STATE_CODE_OVERRIDES.get(compact_text(name).upper(), code_slug(name))


def _lga_code(name: str) -> str:
    return code_slug(name)


def _city_code(name: str) -> str:
    return code_slug(name)


@lru_cache(maxsize=1)
def _raw_nigeria_locations() -> list[dict[str, Any]]:
    with (DATA_DIR / "NG.locations.json").open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _matches(value: str, candidate_code: str, candidate_name: str) -> bool:
    normalized = compact_text(value).upper()
    return normalized in {candidate_code.upper(), compact_text(candidate_name).upper(), code_slug(candidate_name)}


@lru_cache(maxsize=1)
def get_states(country_code: str = NIGERIA_COUNTRY_CODE) -> list[dict[str, Any]]:
    """Return state/province options for a country. Nigeria is complete first."""
    country = compact_text(country_code).upper()
    if country != NIGERIA_COUNTRY_CODE or not is_valid_country_code(country):
        return []
    return [
        {
            "code": _state_code(state["state"]),
            "name": state["state"],
            "country_code": NIGERIA_COUNTRY_CODE,
            "is_active": True,
        }
        for state in _raw_nigeria_locations()
    ]


def _find_state(country_code: str, state_ref: str) -> dict[str, Any] | None:
    country = compact_text(country_code).upper()
    if country != NIGERIA_COUNTRY_CODE:
        return None
    for state in _raw_nigeria_locations():
        code = _state_code(state["state"])
        if _matches(state_ref, code, state["state"]):
            return state
    return None


def get_lgas(country_code: str, state_ref: str) -> list[dict[str, Any]]:
    """Return LGA options for a country/state pair."""
    state = _find_state(country_code, state_ref)
    if not state:
        return []
    state_code = _state_code(state["state"])
    return [
        {
            "code": _lga_code(lga["name"]),
            "name": lga["name"],
            "state_code": state_code,
            "country_code": NIGERIA_COUNTRY_CODE,
            "is_active": True,
        }
        for lga in state.get("lgas", [])
    ]


def _find_lga(country_code: str, state_ref: str, lga_ref: str) -> dict[str, Any] | None:
    state = _find_state(country_code, state_ref)
    if not state:
        return None
    for lga in state.get("lgas", []):
        code = _lga_code(lga["name"])
        if _matches(lga_ref, code, lga["name"]):
            return lga
    return None


def get_cities(
    country_code: str,
    *,
    state_ref: str | None = None,
    lga_ref: str | None = None,
) -> list[dict[str, Any]]:
    """Return city/area options, backed by Nigeria ward-level location data."""
    country = compact_text(country_code).upper()
    if country != NIGERIA_COUNTRY_CODE:
        return []

    states = [_find_state(country, state_ref)] if state_ref else _raw_nigeria_locations()
    results: list[dict[str, Any]] = []
    for state in states:
        if not state:
            continue
        state_code = _state_code(state["state"])
        lgas = [_find_lga(country, state_code, lga_ref)] if lga_ref else state.get("lgas", [])
        for lga in lgas:
            if not lga:
                continue
            lga_code = _lga_code(lga["name"])
            for ward in lga.get("wards", []):
                results.append(
                    {
                        "code": _city_code(ward["name"]),
                        "name": ward["name"],
                        "lga_code": lga_code,
                        "state_code": state_code,
                        "country_code": NIGERIA_COUNTRY_CODE,
                        "latitude": ward.get("latitude"),
                        "longitude": ward.get("longitude"),
                        "is_active": True,
                    }
                )
    return results


def is_valid_state_code(country_code: str, state_ref: str) -> bool:
    return _find_state(country_code, state_ref) is not None


def is_valid_lga_code(country_code: str, state_ref: str, lga_ref: str) -> bool:
    return _find_lga(country_code, state_ref, lga_ref) is not None


def is_valid_city_code(
    country_code: str,
    city_ref: str,
    *,
    state_ref: str | None = None,
    lga_ref: str | None = None,
) -> bool:
    for city in get_cities(country_code, state_ref=state_ref, lga_ref=lga_ref):
        if _matches(city_ref, city["code"], city["name"]):
            return True
    return False

