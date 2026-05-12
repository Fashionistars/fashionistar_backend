# apps/cart/urls.py
from django.urls import path
from apps.cart.apis.sync.cart_views import (
    CartAddItemView,
    CartRemoveItemView,
    CartUpdateQuantityView,
    CartSaveForLaterView,
    CartCouponView,
    CartClearView,
    CartMergeView,
)

app_name = "cart"

urlpatterns = [
    path("add/", CartAddItemView.as_view(), name="cart-add-item"),
    path("items/<uuid:item_id>/", CartRemoveItemView.as_view(), name="cart-remove-item"),
    path("items/<uuid:item_id>/quantity/", CartUpdateQuantityView.as_view(), name="cart-update-quantity"),
    path("items/<uuid:item_id>/save-later/", CartSaveForLaterView.as_view(), name="cart-save-later"),
    path("coupon/", CartCouponView.as_view(), name="cart-coupon"),
    path("clear/", CartClearView.as_view(), name="cart-clear"),
    path("merge/", CartMergeView.as_view(), name="cart-merge"),
]
