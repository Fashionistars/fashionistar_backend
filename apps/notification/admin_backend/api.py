# apps/notification/admin_backend/api.py
import logging
from typing import List, Optional
from ninja import Router
from apps.admin_backend.permissions import admin_auth
from apps.notification.admin_backend.selectors import AdminNotificationSelector
from apps.notification.admin_backend.schemas import AdminNotificationSchema

logger = logging.getLogger(__name__)

router = Router(tags=["Admin - Notification"])

@router.get("/", response=List[AdminNotificationSchema], auth=admin_auth)
async def list_notifications(
    request,
    notification_type: Optional[str] = None,
    channel: Optional[str] = None,
    search: Optional[str] = None,
):
    """
    Get all sent notifications.
    """
    filters = {"notification_type": notification_type, "channel": channel, "search": search}
    return await AdminNotificationSelector.aget_notifications_list(filters)

@router.get("/{notification_id}/", response=AdminNotificationSchema, auth=admin_auth)
async def get_notification_detail(request, notification_id: str):
    """
    Get details of a specific notification.
    """
    try:
        return await AdminNotificationSelector.aget_notification_detail(notification_id)
    except Exception as e:
        from ninja.errors import HttpError
        raise HttpError(404, f"Notification not found: {str(e)}")
