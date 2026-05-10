from django.urls import path

from notification  import vendor_views as vendor_order_views
from notification  import vendor_views as vendor_notification_views



app_name = 'notification'  # Add this line to specify the app namespace



urlpatterns = [

    # Vendor Order Acceptance and Complete API Endpoints
    path('vendor/order-accept/<int:order_item_id>/', vendor_order_views.VendorUpdateOrderStatusView.as_view(), name='vendor-accept-order'),
    path('vendor/order-complete/<int:order_item_id>/', vendor_order_views.VendorCompleteOrderView.as_view(), name='vendor-complete-order'),
    path('vendor/order-notification/<int:vendor_id>/', vendor_order_views.VendorOrderNotificationView.as_view(), name='vendor-order-notification'),

    # Vendor Notifications API Endpoints
    path('vendor/notifications-unseen/<vendor_id>/', vendor_notification_views.NotificationUnSeenListAPIView.as_view(), name='vendor-notifications-unseen'),
    path('vendor/notifications-seen/<vendor_id>/', vendor_notification_views.NotificationSeenListAPIView.as_view(), name='vendor-notifications-seen'),
    path('vendor/notifications-summary/<vendor_id>/', vendor_notification_views.NotificationSummaryAPIView.as_view(), name='vendor-notifications-summary'),
    path('vendor/notifications-mark-as-seen/<vendor_id>/<noti_id>/', vendor_notification_views.NotificationMarkAsSeen.as_view(), name='vendor-notifications-mark-as-seen'),


]


