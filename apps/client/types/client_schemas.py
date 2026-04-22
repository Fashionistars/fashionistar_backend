# apps/client/types/client_schemas.py
"""
Pydantic / Django-Ninja schemas for the async Client API.

These replace DRF serializers for all Ninja endpoints under /api/v1/ninja/.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID

from ninja import Schema
from pydantic import Field


# ── Output Schemas ──────────────────────────────────────────────────────


class AddressOut(Schema):
    id:             UUID
    label:          str
    full_name:      str
    phone:          str
    street_address: str
    city:           str
    state:          str
    country:        str
    postal_code:    str
    is_default:     bool


class ProfileOut(Schema):
    id:                         UUID
    user_id:                    str
    bio:                        str
    preferred_size:             str
    style_preferences:          list[str]
    favourite_colours:          list[str]
    country:                    str
    state:                      str
    is_profile_complete:        bool
    total_orders:               int
    total_spent_ngn:            Decimal
    email_notifications_enabled:bool
    sms_notifications_enabled:  bool
    addresses:                  list[AddressOut] = Field(default_factory=list)


class AnalyticsOut(Schema):
    total_orders:    int
    total_spent_ngn: float
    saved_addresses: int


class DashboardOut(Schema):
    profile:          ProfileOut
    analytics:        AnalyticsOut
    ai_recommendations: list[Any] = Field(default_factory=list)


# ── Input Schemas ───────────────────────────────────────────────────────


class ProfileUpdateIn(Schema):
    bio:                         str | None = None
    default_shipping_address:    str | None = None
    state:                       str | None = None
    country:                     str | None = None
    preferred_size:              str | None = None
    style_preferences:           list[str] | None = None
    favourite_colours:           list[str] | None = None
    email_notifications_enabled: bool | None = None
    sms_notifications_enabled:   bool | None = None


class AddressIn(Schema):
    label:          str = "Home"
    full_name:      str = ""
    phone:          str = ""
    street_address: str
    city:           str
    state:          str
    country:        str = "Nigeria"
    postal_code:    str = ""
    is_default:     bool = False
