from django.urls import path
from customer import views as trans_password 
from customer import views as customer_views






urlpatterns = [
    # Transaction Password
    path('client/set-transaction-password/', trans_password.SetTransactionPasswordView.as_view(), name='set-transaction-password'),
    path('client/validate-transaction-password/', trans_password.ValidateTransactionPasswordView.as_view(), name='validate-transaction-password'),


    # Client API Endpoints
    path('client/orders/<user_id>/', customer_views.OrdersAPIView.as_view(), name='customer-orders'),
    path('client/order/detail/<user_id>/<order_oid>/', customer_views.OrdersDetailAPIView.as_view(), name='customer-order-detail'),
    path('client/wishlist/create/', customer_views.WishlistCreateAPIView.as_view(), name='customer-wishlist-create'),
    path('client/wishlist/<user_id>/', customer_views.WishlistAPIView.as_view(), name='customer-wishlist'),
    path('client/notification/<user_id>/', customer_views.CustomerNotificationView.as_view(), name='customer-notification'),
    path('client/setting/<int:pk>/', customer_views.CustomerUpdateView.as_view(), name='customer-settings'),


    # DeliveryContact URLs
    path('client/delivery-contact/', customer_views.DeliveryContactListCreateView.as_view(), name='delivery-contact-list-create'),
    path('client/delivery-contact/<int:pk>/', customer_views.DeliveryContactDetailView.as_view(), name='delivery-contact-detail'),

    # ShippingAddress URLs
    path('client/shipping-address/', customer_views.ShippingAddressListCreateView.as_view(), name='shipping-address-list-create'),
    path('client/shipping-address/<int:pk>/', customer_views.ShippingAddressDetailView.as_view(), name='shipping-address-detail'),
]
# urls.py

