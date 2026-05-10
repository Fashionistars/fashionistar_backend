"""Measurements Domain — Django-Ninja Async Router.

Mounted at: /api/v1/ninja/measurements/

Architecture:
  - READ ONLY. Mutation endpoints live on the DRF sync surface.
  - Async reads use Django native async ORM through selectors.
  - No ``sync_to_async`` and no executor bridge in canonical read routers.
"""

import logging

from ninja import Router
from ninja.errors import HttpError

from apps.measurements.selectors import (
    aget_default_profile,
    aget_profile_by_id,
    aget_user_profiles,
)

logger = logging.getLogger(__name__)

router = Router(tags=["Measurements — Async"])


def _get_auth_user(request):
    """Extract the authenticated user from the Ninja request."""
    return request.auth.user if hasattr(request.auth, "user") else request.auth


def _serialize_profile(profile) -> dict:
    """Serialize a MeasurementProfile ORM instance to a plain dict."""
    return {
        "id": str(profile.pk),
        "name": profile.name,
        "is_default": profile.is_default,
        "unit": profile.unit,
        "is_verified": profile.is_verified,
        "has_core_measurements": profile.has_core_measurements,
        "bust": str(profile.bust) if profile.bust is not None else None,
        "waist": str(profile.waist) if profile.waist is not None else None,
        "hips": str(profile.hips) if profile.hips is not None else None,
        "shoulder_width": str(profile.shoulder_width) if profile.shoulder_width is not None else None,
        "neck": str(profile.neck) if profile.neck is not None else None,
        "inseam": str(profile.inseam) if profile.inseam is not None else None,
        "thigh": str(profile.thigh) if profile.thigh is not None else None,
        "knee": str(profile.knee) if profile.knee is not None else None,
        "ankle": str(profile.ankle) if profile.ankle is not None else None,
        "arm_length": str(profile.arm_length) if profile.arm_length is not None else None,
        "bicep": str(profile.bicep) if profile.bicep is not None else None,
        "wrist": str(profile.wrist) if profile.wrist is not None else None,
        "height": str(profile.height) if profile.height is not None else None,
        "weight_kg": str(profile.weight_kg) if profile.weight_kg is not None else None,
        "notes": profile.notes,
        "reference_photo_url": profile.reference_photo.url if profile.reference_photo else None,
        "created_at": profile.created_at.isoformat(),
        "updated_at": profile.updated_at.isoformat(),
    }


@router.get("/")
async def list_profiles(request):
    """Async list of the authenticated user's measurement profiles.

    Traversal:
        ``request.auth.client_measurement_profiles`` -> MeasurementProfile.
    """
    user = _get_auth_user(request)
    if user is None:
        raise HttpError(401, "Authentication required.")
    try:
        profiles = await aget_user_profiles(user)
    except Exception:
        logger.exception("list_profiles: error for user=%s", getattr(user, "pk", "?"))
        raise HttpError(500, "Failed to fetch measurement profiles.")
    return {"status": "success", "data": [_serialize_profile(profile) for profile in profiles]}


@router.get("/default/")
async def get_default_measurement_profile(request):
    """Async default MeasurementProfile read through the user reverse manager."""
    user = _get_auth_user(request)
    if user is None:
        raise HttpError(401, "Authentication required.")
    try:
        profile = await aget_default_profile(user)
    except Exception:
        logger.exception(
            "get_default_measurement_profile: error for user=%s",
            getattr(user, "pk", "?"),
        )
        raise HttpError(500, "Failed to fetch default profile.")
    if profile is None:
        raise HttpError(404, "No default measurement profile found.")
    return {"status": "success", "data": _serialize_profile(profile)}


@router.get("/{profile_id}/")
async def get_profile_detail(request, profile_id: int):
    """Async profile detail scoped to the authenticated user."""
    user = _get_auth_user(request)
    if user is None:
        raise HttpError(401, "Authentication required.")
    try:
        profile = await aget_profile_by_id(profile_id=profile_id, user=user)
    except Exception:
        logger.exception(
            "get_profile_detail: error profile=%s user=%s",
            profile_id,
            getattr(user, "pk", "?"),
        )
        raise HttpError(500, "Failed to fetch profile.")
    if profile is None:
        raise HttpError(404, "Measurement profile not found.")
    return {"status": "success", "data": _serialize_profile(profile)}
