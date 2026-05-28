# apps/notification/admin_backend/services.py
from __future__ import annotations
import logging
from django.db import transaction
from django.contrib.auth import get_user_model
from apps.common.events import event_bus
from apps.notification.models.notification import Notification, NotificationChannel, NotificationType

User = get_user_model()
logger = logging.getLogger(__name__)

@transaction.atomic
def admin_broadcast_notification(
    admin_user,
    notification_type: str,
    title: str,
    body: str,
    target_role: str = None,
) -> int:
    """
    Broadcast an in-app notification to all users or all users with a specific role.
    """
    users_qs = User.objects.filter(is_active=True, is_deleted=False)
    if target_role:
        users_qs = users_qs.filter(role=target_role)
        
    notifications = []
    # Bulk create notifications for targeted users
    for user in users_qs:
        notifications.append(
            Notification(
                recipient=user,
                notification_type=notification_type,
                channel=NotificationChannel.IN_APP,
                title=title,
                body=body,
                metadata={
                    "broadcasted_by": admin_user.email,
                    "target_role": target_role or "all",
                },
            )
        )
        
    Notification.objects.bulk_create(notifications)
    
    logger.info("Admin %s broadcasted notification of type %s to %d users (role=%s)", 
                admin_user.email, notification_type, len(notifications), target_role)
                
    event_bus.emit_on_commit(
        "admin.notification.broadcasted",
        notification_type=notification_type,
        target_role=target_role,
        count=len(notifications),
        admin_id=str(admin_user.id),
    )
    return len(notifications)
