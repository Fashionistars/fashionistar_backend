from django.urls import path

from vendor import views as vendor_order



app_name = 'vendor'  # Add this line to specify the app namespace



urlpatterns = [


    path('order/vendor-accept/<int:order_item_id>/', vendor_order.VendorAcceptOrderView.as_view(), name='vendor-accept-order'),
    path('order/vendor-complete/<int:order_item_id>/', vendor_order.VendorCompleteOrderView.as_view(), name='vendor-complete-order'),
    path('order/vendor-notification/<int:vendor_id>/', vendor_order.VendorOrderNotificationView.as_view(), name='vendor-order-notification'),

]