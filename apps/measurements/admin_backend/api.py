# apps/measurements/admin_backend/api.py
import logging
from typing import List, Optional
from ninja import Router
from apps.admin_backend.permissions import admin_auth
from apps.measurements.admin_backend.selectors import AdminMeasurementSelector
from apps.measurements.admin_backend.schemas import AdminMeasurementProfileSchema

logger = logging.getLogger(__name__)

router = Router(tags=["Admin - Measurements"])

@router.get("/", response=List[AdminMeasurementProfileSchema], auth=admin_auth)
async def list_measurements(
    request,
    is_verified: Optional[bool] = None,
    search: Optional[str] = None,
):
    """
    Get all client measurement profiles.
    """
    filters = {"is_verified": is_verified, "search": search}
    return await AdminMeasurementSelector.aget_measurements_list(filters)

@router.get("/{profile_id}/", response=AdminMeasurementProfileSchema, auth=admin_auth)
async def get_measurement_detail(request, profile_id: str):
    """
    Get a specific measurement profile.
    """
    try:
        return await AdminMeasurementSelector.aget_measurement_detail(profile_id)
    except Exception as e:
        from ninja.errors import HttpError
        raise HttpError(404, f"Measurement profile not found: {str(e)}")
