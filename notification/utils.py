from notification.models import Notification

import logging

logger = logging.getLogger(__name__)



# Utility Function to send notifications to users or vendors
def send_notification(user, vendor, order, order_item, notification_type):
    """
    Create a notification entry in the database.

    Args:
        user: User object associated with the notification.
        vendor: Vendor object associated with the notification.
        order: CartOrder object associated with the notification.
        order_item: CartOrderItem object associated with the notification.
    """
    try:
        Notification.objects.create(
            user=user,
            vendor=vendor,
            order=order,
            order_item=order_item,
            notification_type=notification_type
        )
    except Exception as e:
        # Log the error
        logger.error(f"Failed to send notification: {e}")
