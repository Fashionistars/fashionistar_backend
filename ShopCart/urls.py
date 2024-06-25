from django.urls import path
from ShopCart import views as cart_views



app_name = 'ShopCart'  # Add this line to specify the app namespace


urlpatterns = [
    path('cart/view/', cart_views.CartApiView.as_view(), name='cart-view'),
    path('cart/list/<str:cart_id>/', cart_views.CartListView.as_view(), name='cart-list'),
    path('cart/list/<str:cart_id>/<int:user_id>/', cart_views.CartListView.as_view(), name='cart-list-with-user'),
    path('cart/detail/<str:cart_id>/', cart_views.CartDetailView.as_view(), name='cart-detail'),
    path('cart/detail/<str:cart_id>/<int:user_id>/', cart_views.CartDetailView.as_view(), name='cart-detail-with-user'),
    path('cart/delete/<str:cart_id>/<int:item_id>/', cart_views.CartItemDeleteView.as_view(), name='cart-delete'),
    path('cart/delete/<str:cart_id>/<int:item_id>/<int:user_id>/', cart_views.CartItemDeleteView.as_view(), name='cart-delete-with-user'),

    # URL pattern for updating cart without user_id
    path('cart/update/<str:cart_id>/<int:item_id>/', cart_views.CartUpdateApiView.as_view(), name='cart-update'),
    # URL pattern for updating cart with user_id
    path('cart/update/<str:cart_id>/<int:item_id>/<int:user_id>/', cart_views.CartUpdateApiView.as_view(), name='cart-update-with-user'),
]
