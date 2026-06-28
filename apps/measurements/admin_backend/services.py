# apps/measurements/admin_backend/services.py
from __future__ import annotations
import logging
from django.db import transaction
from apps.common.events import event_bus
from apps.measurements.models.measurement import MeasurementProfile

logger = logging.getLogger(__name__)

@transaction.atomic
def admin_verify_measurement_profile(
    profile_id: str,
    admin_user,
    notes: str = "",
) -> MeasurementProfile:
    """
    Verify a client's measurement profile by an admin or staff user.
    """
    profile = MeasurementProfile.objects.select_for_update().get(id=profile_id)
    profile.is_verified = True
    profile.verified_by = admin_user
    if notes:
        profile.notes = f"{profile.notes}\n[Admin Verification Notes]: {notes}".strip()
    profile.save()
    
    logger.info("Admin %s verified measurement profile %s", admin_user.email, profile.id)
    event_bus.emit_on_commit(
        "admin.measurements.profile_verified",
        profile_id=str(profile.id),
        owner_id=str(profile.owner_id),
        admin_id=str(admin_user.id),
    )
    return profile
