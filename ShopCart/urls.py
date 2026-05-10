from django.urls import path
from ShopCart import views as cart_views

app_name = 'ShopCart'  # Add this line to specify the app namespace

urlpatterns = [
    # Endpoint to view or create a cart
    path('cart/view/', cart_views.CartApiView.as_view(), name='cart-view'),

    # Endpoints to list all items in a cart, with or without a user ID
    path('cart/list/<str:cart_id>/', cart_views.CartListView.as_view(), name='cart-list'),
    path('cart/list/<str:cart_id>/<int:user_id>/', cart_views.CartListView.as_view(), name='cart-list-with-user'),

    # Endpoints to view cart details, with or without a user ID
    path('cart/detail/<str:cart_id>/', cart_views.CartDetailView.as_view(), name='cart-detail'),
    path('cart/detail/<str:cart_id>/<int:user_id>/', cart_views.CartDetailView.as_view(), name='cart-detail-with-user'),

    # Endpoints to delete an item from the cart, with or without a user ID
    path('cart/delete/<str:cart_id>/<int:item_id>/', cart_views.CartItemDeleteView.as_view(), name='cart-delete'),
    path('cart/delete/<str:cart_id>/<int:item_id>/<int:user_id>/', cart_views.CartItemDeleteView.as_view(), name='cart-delete-with-user'),

    # Endpoints to update an item in the cart, with or without a user ID
    path('cart/update/<str:cart_id>/<int:item_id>/', cart_views.CartUpdateApiView.as_view(), name='cart-update'),
    path('cart/update/<str:cart_id>/<int:item_id>/<int:user_id>/', cart_views.CartUpdateApiView.as_view(), name='cart-update-with-user'),

    # Endpoints to get total values for the cart, with or without a user ID
    path('cart/total/<str:cart_id>/', cart_views.CartTotalView.as_view(), name='cart-total'),
    path('cart/total/<str:cart_id>/<int:user_id>/', cart_views.CartTotalView.as_view(), name='cart-total-with-user'),
]
