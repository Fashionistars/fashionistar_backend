# apps/measurements/services/measurement_service.py
"""
Business logic for the Measurements domain.

Key rules:
  1. All writes use transaction.atomic().
  2. A user may have up to 5 measurement profiles (configurable).
  3. assert_buyer_has_measurement() is the checkout-gate — called by cart
     service before checkout of `requires_measurement=True` products.
  4. Audit events emitted for profile creation and verification via
     ``apps.audit_logs.services.measurements.measurements_audit``.
  5. All audit imports are deferred inside function bodies (never module-level)
     to prevent circular imports during Django startup / makemigrations.
"""

import logging
from decimal import Decimal, InvalidOperation
from typing import Any

from django.db import transaction
from django.core.exceptions import PermissionDenied

from apps.measurements.models import MeasurementProfile


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
    # ── Audit event (on_commit: inside @transaction.atomic) ────────────────
    _profile_id = str(profile.id)
    _owner = owner
    def _audit_profile_created():
        try:
            from apps.audit_logs.services.measurements import measurements_audit
            measurements_audit.log_measurement_created(
                actor=_owner,
                measurement_id=_profile_id,
                source="manual",
            )
        except Exception:
            logger.warning(
                "measurements_audit.log_measurement_created failed silently", exc_info=True
            )
    transaction.on_commit(_audit_profile_created)
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
    # ── Audit event ──────────────────────────────────────────────────────────
    _profile_id = str(profile.id)
    _owner = owner
    _new_values = {k: str(v) for k, v in data.items()}
    def _audit_profile_updated():
        try:
            from apps.audit_logs.services.measurements import measurements_audit
            measurements_audit.log_measurement_updated(
                actor=_owner,
                measurement_id=_profile_id,
                new_values=_new_values,
            )
        except Exception:
            logger.warning(
                "measurements_audit.log_measurement_updated failed silently", exc_info=True
            )
    transaction.on_commit(_audit_profile_updated)
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
    # ── Audit (GDPR: right-to-erasure events must be logged) ────────────────
    try:
        from apps.audit_logs.services.measurements import measurements_audit
        measurements_audit.log_measurement_deleted(
            actor=owner,
            measurement_id=str(profile_id),
        )
    except Exception:
        logger.warning(
            "measurements_audit.delete failed silently", exc_info=True
        )
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
