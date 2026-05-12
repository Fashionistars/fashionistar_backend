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
PROFILE_EDITABLE_FIELDS = frozenset(
    [
        "first_name",
        "last_name",
        "bio",
        "country",
        "state",
        "city",
        "address",
        "avatar",
    ]
)

CLIENT_PROFILE_EDITABLE_FIELDS = frozenset(
    [
        "bio",
        "default_shipping_address",
        "state",
        "country",
        "preferred_size",
        "style_preferences",
        "favourite_colours",
    ]
)


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

    attempting to update immutable fields (email, role, etc.) is silently
    ignored here; the serializer layer should catch them first.

    Runs inside ``transaction.atomic()`` to ensure partial updates don't
    leave inconsistent state in the DB.

    Args:
        user: The UnifiedUser instance to update.
        data: Dict of field names → new values (already validated by serializer).

    Returns:
        The updated UnifiedUser instance (refreshed from DB).

    Raises:
        ValueError: If data is empty or no valid fields are provided.
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
        "✅ Profile updated for user=%s fields=%s",
        user.pk,
        list(update_fields.keys()),
    )
    return user


def get_client_profile(*, user: "UnifiedUser") -> "ClientProfile":
    """
    Get or create the ClientProfile for a given user.

    Uses ClientProfile.get_or_create_for_user() which wraps
    objects.get_or_create() atomically.

    Args:
        user: UnifiedUser instance with role='client'.

    Returns:
        ClientProfile instance (created if it didn't exist).
    """
    from apps.authentication.models import ClientProfile

    return ClientProfile.get_or_create_for_user(user)


def update_client_profile(
    *,
    user: "UnifiedUser",
    data: dict[str, Any],
) -> "ClientProfile":
    """
    Partially update a user's ClientProfile with validated data.

    Args:
        user: UnifiedUser instance.
        data: Dict of field names → new values (validated by serializer).

    Returns:
        Updated ClientProfile instance.
    """
    from apps.authentication.models import ClientProfile

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
        "✅ ClientProfile updated for user=%s fields=%s",
        user.pk,
        list(update_fields_clean.keys()),
    )
    return profile


# ─────────────────────────────────────────────────────────────────────────────
# POST-AUTH STATE — computed routing hints for the frontend Zustand store
# ─────────────────────────────────────────────────────────────────────────────


def get_post_auth_state(*, user: "UnifiedUser") -> dict[str, Any]:
    """
    Compute the frontend routing state after authentication.

    Returns a dict consumed by MeSerializer's SerializerMethodFields and
    mirrored by the frontend ``useAuthHydration()`` hook.

    Keys returned:
        has_client_profile        → bool
        has_vendor_profile        → bool
        vendor_onboarding_status  → str | None
        dashboard_entrypoint      → str  (frontend route, e.g. "/dashboard/vendor")

    This function uses cheap reverse-relation existence checks
    (``hasattr`` + ``_set`` manager) to avoid N+1 queries when called
    from within a serializer that already has the user instance.

    Args:
        user: Authenticated UnifiedUser instance.

    Returns:
        Dict with the four routing-hint keys.
    """
    has_client = False
    has_vendor = False
    vendor_onboarding_status: str | None = None

    # ── Client profile check (reverse OneToOne) ────────────────────────────
    try:
        cp = getattr(user, "clientprofile", None)
        has_client = cp is not None
    except Exception:
        has_client = False

    # ── Vendor profile check (reverse OneToOne) ────────────────────────────
    try:
        vp = getattr(user, "vendorprofile", None)
        has_vendor = vp is not None
        if has_vendor and vp is not None:
            vendor_onboarding_status = getattr(vp, "onboarding_status", None)
    except Exception:
        has_vendor = False

    # ── Dashboard entry-point routing logic ───────────────────────────────
    role = getattr(user, "role", "client")

    if role in ("admin", "staff") or getattr(user, "is_staff", False):
        entrypoint = "/dashboard/admin"
    elif has_vendor:
        entrypoint = "/dashboard/vendor"
    elif has_client:
        entrypoint = "/dashboard/client"
    else:
        # New user — not yet onboarded
        entrypoint = "/onboarding"

    return {
        "has_client_profile": has_client,
        "has_vendor_profile": has_vendor,
        "vendor_onboarding_status": vendor_onboarding_status,
        "dashboard_entrypoint": entrypoint,
    }
