"""Django-Ninja schemas for read-only reference data endpoints."""

from __future__ import annotations

from ninja import Schema


class ReferenceCountryOut(Schema):
    id: str
    code: str
    name: str
    flag: str
    phone_code: str
    is_active: bool


class ReferenceStateOut(Schema):
    code: str
    name: str
    country_code: str
    is_active: bool


class ReferenceLgaOut(Schema):
    code: str
    name: str
    state_code: str
    country_code: str
    is_active: bool


class ReferenceCityOut(Schema):
    code: str
    name: str
    lga_code: str
    state_code: str
    country_code: str
    latitude: float | None = None
    longitude: float | None = None
    is_active: bool


class ReferenceBankOut(Schema):
    id: str
    code: str
    name: str
    country_code: str
    currency: str
    provider: str
    is_active: bool
