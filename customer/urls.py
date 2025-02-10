from django.urls import path
from customer import views as trans_password 
from customer import views as customer_views
from customer import profile as customer_profile
from customer import wishlist as client_wishlist
from customer import reviews as client_reviews
from customer import orders as client_orders
from customer.wallet_balance import UserTransferView, UserWalletBalanceView




app_name = 'customer'  # Add this line to specify the app namespace


urlpatterns = [

    # ORDERS API ENDPOINTS                          
    path('client/orders/', client_orders.OrdersAPIView.as_view(), name='client-orders'),
    path('client/order/detail/<str:order_oid>/', client_orders.OrdersDetailAPIView.as_view(), name='client-order-detail'),
    
    
    
    # WISH-LIST API ENDPOINTS                          
    path('client/wishlist/create/', client_wishlist.WishlistCreateAPIView.as_view(), name='customer-wishlist-create'),
    path('client/wishlist/', client_wishlist.WishlistAPIView.as_view(), name='customer-wishlist'),

    #  REVIEW API ENDPOINTS
    path('home/reviews/<product_id>/', client_reviews.ReviewListView.as_view(), name='product-reviews'),
    path('client/reviews/create/', client_reviews.ReviewCreateAPIView.as_view(), name='customer-review-create'),


    # Customer ProfileView API Endpoints
    path('client/settings/<str:pid>/', customer_profile.CustomerProfileView.as_view(), name='client-profile'),
    path('client/settings/update/<str:pid>/', customer_profile.CustomerProfileUpdateView.as_view(), name='client-profile-update'),

    # Transaction Password
    path('client/set-transaction-password/', trans_password.SetTransactionPasswordView.as_view(), name='set-transaction-password'),
    path('client/validate-transaction-password/', trans_password.ValidateTransactionPasswordView.as_view(), name='validate-transaction-password'),

    #  RETRIEVING USER'S WALLET BALANCE AND TRNASFERING MONEY  FROM USER'S WALLET BALANCE INTO ANOTHER USER'S ACCOUNT
    path('client/transfer/', UserTransferView.as_view()),
    path('client/wallet-balance/', UserWalletBalanceView.as_view()),


    # Client API Endpoints
    path('client/orders/<user_id>/', customer_views.OrdersAPIView.as_view(), name='customer-orders'),
    path('client/order/detail/<user_id>/<order_oid>/', customer_views.OrdersDetailAPIView.as_view(), name='customer-order-detail'),
    path('client/wishlist/create/', customer_views.WishlistCreateAPIView.as_view(), name='customer-wishlist-create'),
    path('client/wishlist/<user_id>/', customer_views.WishlistAPIView.as_view(), name='customer-wishlist'),


    
    # Client Notifications API Endpoints
    path('client/notifications-unseen/<user_id>/', customer_views.ClientNotificationUnSeenListAPIView.as_view(), name='client-notifications-unseen'),
    path('client/notifications-seen/<user_id>/', customer_views.ClientNotificationSeenListAPIView.as_view(), name='client-notifications-seen'),
    path('client/notifications-summary/<user_id>/', customer_views.ClientNotificationSummaryAPIView.as_view(), name='client-notifications-summary'),
    path('client/notifications-mark-as-seen/<user_id>/<noti_id>/', customer_views.ClientNotificationMarkAsSeen.as_view(), name='client-notifications-mark-as-seen'),


    # delivery and order tracking to be paid attention to later
    path('client/order/tracking/<int:order_id>/', customer_views.OrderTrackingView.as_view(), name='order-tracking'),


    # DeliveryContact URLs
    path('client/delivery-contact/', customer_views.DeliveryContactListCreateView.as_view(), name='delivery-contact-list-create'),
    path('client/delivery-contact/<int:pk>/', customer_views.DeliveryContactDetailView.as_view(), name='delivery-contact-detail'),

    # ShippingAddress URLs
    path('client/shipping-address/', customer_views.ShippingAddressListCreateView.as_view(), name='shipping-address-list-create'),
    path('client/shipping-address/<int:pk>/', customer_views.ShippingAddressDetailView.as_view(), name='shipping-address-detail'),
]