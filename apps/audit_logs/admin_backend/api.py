# apps/audit_logs/admin_backend/api.py
import logging
from typing import List, Optional
from ninja import Router
from apps.admin_backend.permissions import admin_auth
from apps.audit_logs.admin_backend.selectors import AdminAuditSelector
from apps.audit_logs.admin_backend.schemas import AdminAuditEventSchema

logger = logging.getLogger(__name__)

router = Router(tags=["Admin - Audit Logs"])

@router.get("/", response=List[AdminAuditEventSchema], auth=admin_auth)
async def list_audit_events(
    request,
    category: Optional[str] = None,
    severity: Optional[str] = None,
    search: Optional[str] = None,
):
    """
    Get all audit event logs.
    """
    filters = {"category": category, "severity": severity, "search": search}
    return await AdminAuditSelector.aget_audit_logs_list(filters)

@router.get("/{log_id}/", response=AdminAuditEventSchema, auth=admin_auth)
async def get_audit_event_detail(request, log_id: str):
    """
    Get a specific audit event log detail.
    """
    try:
        return await AdminAuditSelector.aget_audit_log_detail(log_id)
    except Exception as e:
        from ninja.errors import HttpError
        raise HttpError(404, f"Audit event log not found: {str(e)}")
