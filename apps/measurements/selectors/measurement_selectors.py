# apps/measurements/selectors/measurement_selectors.py
"""Read-only queries for the Measurements domain.

Owner-scoped selectors begin from ``request.user`` reverse relationships. This
keeps measurement reads pinned to the authenticated user and keeps endpoint
functions away from raw model table queries.
"""
from typing import Any

from django.db.models import QuerySet


def get_user_profiles(user) -> QuerySet:
    """Return all measurement profiles for a user, default first.

    Traversal:
        ``request.user.client_measurement_profiles`` -> MeasurementProfile.

    Args:
        user: Authenticated Django user.

    Returns:
        QuerySet ordered with default profiles first.
    """
    return user.client_measurement_profiles.order_by("-is_default", "-updated_at")


def get_default_profile(user) -> Any | None:
    """Return the user's default measurement profile, or None.

    Traversal:
        ``request.user.client_measurement_profiles`` filtered by
        ``is_default``.
    """
    return user.client_measurement_profiles.filter(is_default=True).first()


def get_profile_by_id(profile_id, user) -> Any | None:
    """Return a profile by ID, scoped to the requesting user.

    Traversal:
        ``request.user.client_measurement_profiles`` filtered by profile ID.
    """
    return user.client_measurement_profiles.filter(id=profile_id).first()


async def aget_user_profiles(user, *, limit: int = 50) -> list:
    """Async list of measurement profiles via the user reverse manager.

    Traversal:
        ``request.auth.client_measurement_profiles`` -> MeasurementProfile.
    """
    qs = user.client_measurement_profiles.order_by("-is_default", "-updated_at")
    return [profile async for profile in qs[:limit]]


async def aget_default_profile(user):
    """Async fetch of the default measurement profile through reverse ORM."""
    return await user.client_measurement_profiles.filter(is_default=True).afirst()


async def aget_profile_by_id(profile_id, user):
    """Async user-scoped profile detail through reverse ORM."""
    return await user.client_measurement_profiles.filter(id=profile_id).afirst()
