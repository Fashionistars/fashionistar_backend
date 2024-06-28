from store.models import Notification


# Function to send notifications to users or vendors
def send_notification(user=None, vendor=None, order=None, order_item=None):
    """
    Create a notification entry in the database.

    Args:
        user: User object associated with the notification.
        vendor: Vendor object associated with the notification.
        order: CartOrder object associated with the notification.
        order_item: CartOrderItem object associated with the notification.
    """
    Notification.objects.create(
        user=user,
        vendor=vendor,
        order=order,
        order_item=order_item,
    )