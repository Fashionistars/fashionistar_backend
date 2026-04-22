# apps/authentication/services/profile_service/profile_service.py
"""
Profile Business Logic Service — Enterprise Edition
====================================================

Provides clean business-logic functions for fetching and updating user
profiles. Views call these functions — never raw ORM directly.

Architecture:
  - Reads go through selectors (apps.authentication.selectors.UserSelector)
  - Writes are validated then committed inside transaction.atomic()
  - ClientProfile is fetched/created via get_or_create_for_user()

Functions:
  - get_user_profile(user_id)         -> UnifiedUser | None
  - get_me_profile(user_id)           -> UnifiedUser | None  (full MeSerializer fields)
  - update_user_profile(user, data)   -> UnifiedUser
  - get_client_profile(user)          -> ClientProfile
  - update_client_profile(user, data) -> ClientProfile
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from django.db import transaction

logger = logging.getLogger("application")

# Allowed profile update fields (security guard)
# NEVER allow: email, phone, role, auth_provider, member_id, password, is_staff
PROFILE_EDITABLE_FIELDS = frozenset([
    "first_name",
    "last_name",
    "bio",
    "country",
    "state",
    "city",
    "address",
    "avatar",
])

CLIENT_PROFILE_EDITABLE_FIELDS = frozenset([
    "bio",
    "default_shipping_address",
    "state",
    "country",
    "preferred_size",
    "style_preferences",
    "favourite_colours",
])


def get_user_profile(*, user_id: str) -> Optional["UnifiedUser"]:
    """
    Fetch a user full profile by UUID string via UserSelector.get_by_id_safe().
    Returns None for unknown/invalid IDs.
    """
    from apps.authentication.selectors import UserSelector
    return UserSelector.get_by_id_safe(user_id)


def get_me_profile(*, user_id: str) -> Optional["UnifiedUser"]:
    """
    Fetch a user full profile for the /auth/me/ endpoint.
    Loads all fields required by MeSerializer in one optimized query.
    Returns None for unknown/invalid IDs.
    """
    from apps.authentication.selectors import UserSelector
    return UserSelector.get_me_profile(user_id)


def update_user_profile(
    *,
    user: "UnifiedUser",
    data: dict[str, Any],
) -> "UnifiedUser":
    """
    Partially update a user profile. Only PROFILE_EDITABLE_FIELDS are applied.
    Raises ValueError if no valid fields provided.
    """
    update_fields = {
        field: value
        for field, value in data.items()
        if field in PROFILE_EDITABLE_FIELDS
    }

    if not update_fields:
        raise ValueError(
            "No editable profile fields provided. "
            f"Allowed fields: {sorted(PROFILE_EDITABLE_FIELDS)}"
        )

    with transaction.atomic():
        for field, value in update_fields.items():
            setattr(user, field, value)
        user.save(update_fields=list(update_fields.keys()) + ["updated_at"])

    logger.info(
        "Profile updated for user=%s fields=%s",
        user.pk,
        list(update_fields.keys()),
    )
    return user


def get_client_profile(*, user: "UnifiedUser") -> "ClientProfile":
    """Get or create the ClientProfile for a given user."""
    from apps.client.models import ClientProfile
    return ClientProfile.get_or_create_for_user(user)


def update_client_profile(
    *,
    user: "UnifiedUser",
    data: dict[str, Any],
) -> "ClientProfile":
    """Partially update a user ClientProfile with validated data."""
    from apps.client.models import ClientProfile

    profile = ClientProfile.get_or_create_for_user(user)
    update_fields_clean = {
        field: value
        for field, value in data.items()
        if field in CLIENT_PROFILE_EDITABLE_FIELDS
    }

    with transaction.atomic():
        for field, value in update_fields_clean.items():
            setattr(profile, field, value)
        fields_to_save = list(update_fields_clean.keys()) + ["updated_at"]
        profile.save(update_fields=fields_to_save)
        profile.update_completeness()

    logger.info(
        "ClientProfile updated for user=%s fields=%s",
        user.pk,
        list(update_fields_clean.keys()),
    )
    return profile


def get_post_auth_state(*, user: "UnifiedUser") -> dict[str, Any]:
    """
    Return the post-auth routing state consumed by the frontend.

    The frontend uses this to decide between `/client/dashboard`,
    `/vendor/setup`, and `/vendor/dashboard`.
    """
    from apps.client.selectors.client_selectors import get_client_profile_or_none
    from apps.vendor.selectors.vendor_selectors import (
        get_vendor_profile_or_none,
        get_vendor_setup_state,
    )

    has_client_profile = bool(get_client_profile_or_none(user)) if user.role == "client" else False
    vendor_profile = get_vendor_profile_or_none(user) if user.role == "vendor" else None
    has_vendor_profile = vendor_profile is not None

    vendor_onboarding_status = None
    dashboard_entrypoint = "/client/dashboard"

    if user.role == "vendor":
        if not vendor_profile:
            vendor_onboarding_status = "not_started"
            dashboard_entrypoint = "/vendor/setup"
        else:
            setup_state = get_vendor_setup_state(vendor_profile)
            if setup_state and not setup_state.profile_complete:
                vendor_onboarding_status = "draft"
                dashboard_entrypoint = "/vendor/setup"
            elif vendor_profile.is_verified and vendor_profile.is_active:
                vendor_onboarding_status = "active"
                dashboard_entrypoint = "/vendor/dashboard"
            elif vendor_profile.is_active:
                vendor_onboarding_status = "submitted"
                dashboard_entrypoint = "/vendor/dashboard"
            else:
                vendor_onboarding_status = "restricted"
                dashboard_entrypoint = "/vendor/dashboard"

    return {
        "has_client_profile": has_client_profile,
        "has_vendor_profile": has_vendor_profile,
        "vendor_onboarding_status": vendor_onboarding_status,
        "dashboard_entrypoint": dashboard_entrypoint,
    }
