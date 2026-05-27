# apps/client/admin_backend/api.py
import logging
from typing import Optional, List
from ninja import Router, Query
from ninja.errors import HttpError
from apps.client.admin_backend.selectors import AdminClientSelector
from apps.client.admin_backend.schemas import (
    ClientProfileListSchema,
    ClientProfileDetailSchema,
    ClientMetricsSchema,
)

logger = logging.getLogger(__name__)

router = Router(tags=["Admin - Client"])

@router.get("/", response=List[ClientProfileListSchema])
async def list_clients(
    request,
    preferred_size: Optional[str] = None,
    is_profile_complete: Optional[bool] = None,
    search: Optional[str] = None,
):
    """
    Get all client profiles, optimized for admin.
    """
    if not (request.auth.is_staff or request.auth.role in ["admin", "super_admin"]):
        raise HttpError(403, "Permission Denied: Admin access required.")
        
    filters = {
        "preferred_size": preferred_size,
        "is_profile_complete": is_profile_complete,
        "search": search,
    }
    return await AdminClientSelector.aget_clients_list(filters)

@router.get("/metrics/", response=ClientMetricsSchema)
async def get_metrics(request):
    """
    Get client profile metrics for the admin dashboard.
    """
    if not (request.auth.is_staff or request.auth.role in ["admin", "super_admin"]):
        raise HttpError(403, "Permission Denied: Admin access required.")
        
    return await AdminClientSelector.aget_admin_dashboard_metrics()

@router.get("/{client_id}/", response=ClientProfileDetailSchema)
async def get_client_detail(request, client_id: str):
    """
    Get detailed client profile.
    """
    if not (request.auth.is_staff or request.auth.role in ["admin", "super_admin"]):
        raise HttpError(403, "Permission Denied: Admin access required.")
        
    try:
        return await AdminClientSelector.aget_client_detail(client_id)
    except Exception as e:
        raise HttpError(404, f"Client profile not found: {str(e)}")
