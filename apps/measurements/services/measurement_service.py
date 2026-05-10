# apps/measurements/services/measurement_service.py
"""
Business logic for the Measurements domain.

Key rules:
  1. All writes use transaction.atomic().
  2. A user may have up to 5 measurement profiles (configurable).
  3. assert_buyer_has_measurement() is the checkout-gate — called by cart
     service before checkout of `requires_measurement=True` products.
  4. Audit events emitted for profile creation and verification.
"""

import logging
from decimal import Decimal, InvalidOperation
from typing import Any

from django.db import transaction
from django.core.exceptions import PermissionDenied

from apps.measurements.models import MeasurementProfile
from apps.measurements.providers import MirrorSizeClient, MirrorSizeProviderError

logger = logging.getLogger(__name__)

# Maximum profiles per user
MAX_PROFILES_PER_USER = 5


class MeasurementRequiredError(Exception):
    """
    Raised when a buyer tries to checkout a custom-tailored product
    without having a valid MeasurementProfile.
    HTTP layer maps this to HTTP 422 Unprocessable Entity.
    """


class MeasurementProfileLimitError(Exception):
    """Raised when a user tries to exceed MAX_PROFILES_PER_USER."""


# ─────────────────────────────────────────────────────────────────────────────
# CHECKOUT GATE (called by cart service)
# ─────────────────────────────────────────────────────────────────────────────

def assert_buyer_has_measurement(user) -> MeasurementProfile:
    """
    Gate for `requires_measurement=True` products.

    Raises MeasurementRequiredError if the user has no valid
    default MeasurementProfile with core measurements filled.

    Returns the valid profile for use in order creation.
    """
    # Reverse FK traversal: request.user.client_measurement_profiles is the
    # canonical owner path for measurement reads. Checkout gates never query a
    # global MeasurementProfile table for a user-owned row.
    profile = user.client_measurement_profiles.filter(is_default=True).first()

    if profile is None:
        # Fall back to any profile if no default
        profile = user.client_measurement_profiles.order_by("-updated_at").first()

    if profile is None:
        raise MeasurementRequiredError(
            "This product requires your body measurements. "
            "Please add a measurement profile before checkout."
        )

    if not profile.has_core_measurements:
        raise MeasurementRequiredError(
            "Your measurement profile is incomplete. "
            "Please fill in bust, waist, hips, and height to proceed."
        )

    return profile


# ─────────────────────────────────────────────────────────────────────────────
# CRUD
# ─────────────────────────────────────────────────────────────────────────────

@transaction.atomic
def create_measurement_profile(
    *,
    owner,
    name: str = "My Measurements",
    data: dict,
    set_as_default: bool = False,
) -> MeasurementProfile:
    """
    Create a new MeasurementProfile for a user.

    Args:
        owner: The authenticated User instance.
        name: Display name for this profile.
        data: Dict of measurement field values (bust, waist, etc.).
        set_as_default: Whether to make this the user's default profile.

    Raises:
        MeasurementProfileLimitError: if user already has MAX_PROFILES_PER_USER.
    """
    # Reverse FK count avoids unscoped table reads while enforcing the user's
    # per-account profile limit.
    existing_count = owner.client_measurement_profiles.count()
    if existing_count >= MAX_PROFILES_PER_USER:
        raise MeasurementProfileLimitError(
            f"You can have at most {MAX_PROFILES_PER_USER} measurement profiles. "
            "Please delete an existing profile before creating a new one."
        )

    profile = owner.client_measurement_profiles.create(
        name=name,
        **data,
    )

    if set_as_default or existing_count == 0:
        profile.set_as_default()

    logger.info(
        "MeasurementProfile created: id=%s owner=%s name=%s",
        profile.id,
        owner.id,
        name,
    )
    return profile


@transaction.atomic
def update_measurement_profile(
    *,
    profile_id,
    owner,
    data: dict,
) -> MeasurementProfile:
    """
    Update an existing MeasurementProfile.
    Verifies that the requesting user owns the profile.
    """
    try:
        profile = owner.client_measurement_profiles.select_for_update().get(id=profile_id)
    except MeasurementProfile.DoesNotExist:
        raise PermissionDenied("Measurement profile not found or access denied.")

    for field, value in data.items():
        setattr(profile, field, value)

    # Always update the timestamp
    profile.save()
    logger.info(
        "MeasurementProfile updated: id=%s owner=%s",
        profile.id,
        owner.id,
    )
    return profile


@transaction.atomic
def delete_measurement_profile(*, profile_id, owner) -> None:
    """
    Hard-delete a MeasurementProfile (GDPR right-to-erasure compliant).
    Verifies ownership. If the deleted profile was default, promotes
    the most recently updated profile to default.
    """
    try:
        profile = owner.client_measurement_profiles.get(id=profile_id)
    except MeasurementProfile.DoesNotExist:
        raise PermissionDenied("Measurement profile not found or access denied.")

    was_default = profile.is_default
    profile.delete()
    logger.info("MeasurementProfile deleted: id=%s owner=%s", profile_id, owner.id)

    if was_default:
        # Promote the next most-recent profile
        next_profile = owner.client_measurement_profiles.order_by("-updated_at").first()
        if next_profile:
            next_profile.set_as_default()


@transaction.atomic
def set_default_profile(*, profile_id, owner) -> MeasurementProfile:
    """Mark a specific profile as the user's default."""
    try:
        profile = owner.client_measurement_profiles.get(id=profile_id)
    except MeasurementProfile.DoesNotExist:
        raise PermissionDenied("Measurement profile not found or access denied.")
    profile.set_as_default()
    return profile


def create_mirrorsize_browser_session(
    *,
    user,
    name: str = "",
    email: str = "",
    mobile_no: str = "",
) -> dict[str, Any]:
    """Create a MirrorSize mobile-browser measurement session.

    Args:
        user: Authenticated user. Contact information is read from the user
            object to avoid importing profile models across domains.
        name: Optional display name supplied by the frontend.
        email: Optional email override.
        mobile_no: Optional mobile number override.

    Returns:
        dict containing ``access_code``, ``qr_code``, and ``measurement_url``.
    """
    client = MirrorSizeClient.from_settings()
    display_name = name or getattr(user, "get_full_name", lambda: "")() or getattr(user, "email", "")
    user_email = email or getattr(user, "email", "")
    phone = mobile_no or getattr(user, "phone", "") or getattr(user, "phone_number", "")
    if not user_email:
        raise MirrorSizeProviderError("A verified email address is required before taking measurements.")
    return client.generate_mobile_browser_access_code(
        email=user_email,
        name=display_name,
        mobile_no=phone,
        reference=str(user.pk),
    )


def _decimal_from_mirrorsize(value: Any) -> Decimal | None:
    """Normalize MirrorSize values such as ``'111.11 cm'`` into Decimal cm."""
    if value in (None, ""):
        return None
    numeric = str(value).lower().replace("cm", "").strip()
    try:
        return Decimal(numeric).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return None


def _map_mirrorsize_measurements(provider_data: dict[str, Any]) -> dict[str, Any]:
    """Map MirrorSize point names into Fashionistar MeasurementProfile fields."""
    point_values: dict[str, Any] = {}
    for item in provider_data.get("measurement", []) or []:
        point = str(item.get("pointName", "")).replace("_", "").lower()
        point_values[point] = _decimal_from_mirrorsize(item.get("valueIncm"))

    return {
        "bust": point_values.get("chest") or point_values.get("chestgirth"),
        "waist": point_values.get("waist") or point_values.get("stomach"),
        "hips": point_values.get("hips") or point_values.get("hip"),
        "shoulder_width": point_values.get("shoulderacross") or point_values.get("shoulderwidth"),
        "neck": point_values.get("upperneck") or point_values.get("neck"),
        "arm_length": point_values.get("armslength") or point_values.get("sleevelengthfull"),
        "height": _decimal_from_mirrorsize(provider_data.get("height")),
        "weight_kg": _decimal_from_mirrorsize(provider_data.get("weight")),
        "notes": "Imported from MirrorSize mobile-browser measurement flow.",
        "is_verified": True,
    }


@transaction.atomic
def import_mirrorsize_browser_measurement(
    *,
    user,
    access_code: str,
    set_as_default: bool = True,
) -> MeasurementProfile:
    """Import completed MirrorSize measurements into a local profile."""
    provider_data = MirrorSizeClient.from_settings().get_mobile_browser_measurement(
        access_code=access_code,
        reference=str(user.pk),
    )
    mapped = {
        key: value
        for key, value in _map_mirrorsize_measurements(provider_data).items()
        if value not in (None, "")
    }
    if not any(mapped.get(field) is not None for field in ("bust", "waist", "hips", "height")):
        raise MirrorSizeProviderError("MirrorSize returned no usable body measurements yet.")

    return create_measurement_profile(
        owner=user,
        name=f"MirrorSize {access_code}",
        data=mapped,
        set_as_default=set_as_default,
    )
