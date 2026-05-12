from venv import logger
from django.db import models

from store.models import CartOrder, CartOrderItem
from userauths.models import User
from vendor.models import Vendor

# Create your models here.





# Notification Types
NOTIFICATION_TYPE = (
    ("new_order", "New Order"),
    ("new_offer", "New Offer"),
    ("new_bidding", "New Bidding"),
    ("item_arrived", "Item Arrived"),
    ("item_shipped", "Item Shipped"),
    ("item_delivered", "Item Delivered"),
    ("tracking_id_added", "Tracking ID Added"),
    ("tracking_id_changed", "Tracking ID Changed"),
    ("offer_rejected", "Offer Rejected"),
    ("offer_accepted", "Offer Accepted"),
    ("update_offer", "Update Offer"),
    ("update_bid", "Update Bid"),
    ("order_cancelled", "Order Cancelled"),
    ("order_cancel_request", "Order Cancel Request"),
    ("new_review", "New Review"),
    ("noti_new_faq", "New Product Question"),
    ("bidding_won", "Bidding Won"),
    ("product_published", "Product Published"),
    ("product_rejected", "Product Rejected"),
    ("product_disabled", "Product Disabled"),
)

# Models
class Notification(models.Model):
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    vendor = models.ForeignKey(Vendor, on_delete=models.SET_NULL, null=True, blank=True)
    order = models.ForeignKey(CartOrder, on_delete=models.SET_NULL, null=True, blank=True)
    order_item = models.ForeignKey(CartOrderItem, on_delete=models.SET_NULL, null=True, blank=True)
    notification_type = models.CharField(max_length=50, choices=NOTIFICATION_TYPE)
    seen = models.BooleanField(default=False)
    date = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name_plural = "Notifications"
    
    def __str__(self):
        if self.order:
            return self.order.oid
        else:
            return "Notification"

class CancelledOrder(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True)
    orderitem = models.ForeignKey("store.CartOrderItem", on_delete=models.SET_NULL, null=True)
    email = models.CharField(max_length=100)
    refunded = models.BooleanField(default=False)
    
    class Meta:
        verbose_name_plural = "Cancelled Orders"
    
    def __str__(self):
        if self.user:
            return str(self.user.username)
        else:
            return "Cancelled Order"
        









                     