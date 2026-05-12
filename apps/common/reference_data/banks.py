"""Bank reference data normalized from the legacy Paystack bank seed."""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from apps.common.reference_data.normalizers import compact_text


def _load_legacy_bank_choices() -> list[dict[str, str]]:
    try:
        from Paystack_Webhoook_Prod.BANKS_LIST import BANK_CHOICES
    except Exception:
        BANK_CHOICES = [
            {"bank_code": "044", "bank_name": "Access Bank"},
            {"bank_code": "058", "bank_name": "Guaranty Trust Bank"},
            {"bank_code": "011", "bank_name": "First Bank of Nigeria"},
            {"bank_code": "057", "bank_name": "Zenith Bank"},
        ]
    return BANK_CHOICES


@lru_cache(maxsize=1)
def get_banks(country_code: str = "NG") -> list[dict[str, Any]]:
    """Return normalized active banks for the selected country."""
    country = compact_text(country_code).upper() or "NG"
    if country != "NG":
        return []

    bank_by_code: dict[str, dict[str, Any]] = {}
    for bank in _load_legacy_bank_choices():
        code = compact_text(bank.get("bank_code", ""))
        name = compact_text(bank.get("bank_name", ""))
        if not code or not name:
            continue
        bank_by_code[code] = {
            "id": code,
            "code": code,
            "name": name,
            "country_code": "NG",
            "currency": "NGN",
            "provider": "paystack",
            "is_active": True,
        }

    return sorted(bank_by_code.values(), key=lambda item: item["name"].lower())


@lru_cache(maxsize=1)
def _bank_index() -> dict[str, dict[str, Any]]:
    return {bank["code"].upper(): bank for bank in get_banks("NG")}


def get_bank(bank_code: str, country_code: str = "NG") -> dict[str, Any] | None:
    if compact_text(country_code).upper() != "NG":
        return None
    return _bank_index().get(compact_text(bank_code).upper())


def is_valid_bank_code(bank_code: str, country_code: str = "NG") -> bool:
    return get_bank(bank_code, country_code) is not None

