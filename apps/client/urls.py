# apps/client/urls.py
"""
Client Domain — DRF URL Patterns.

Mounted at: /api/v1/client/  (via backend/urls.py include)

Async Ninja endpoints are registered separately in:
  backend/urls.py → ninja_api.add_router("/client/", client_router)

Endpoints — Profile & Address:
  GET    /api/v1/client/profile/                            — retrieve client profile
  PATCH  /api/v1/client/profile/                            — update profile
  GET    /api/v1/client/addresses/                          — list saved addresses
  POST   /api/v1/client/addresses/                          — add new address
  DELETE /api/v1/client/addresses/<id>/                     — remove address
  POST   /api/v1/client/addresses/<id>/set-default/         — set default

Endpoints — Orders:
  GET    /api/v1/client/orders/                             — list all paid orders
  GET    /api/v1/client/orders/<str:oid>/                   — single order detail

Endpoints — Wishlist:
  GET    /api/v1/client/wishlist/                           — list wishlist items
  POST   /api/v1/client/wishlist/toggle/                    — add / remove product

Endpoints — Reviews:
  POST   /api/v1/client/reviews/create/                     — submit a product review

Endpoints — Wallet:
  GET    /api/v1/client/wallet/balance/                     — get wallet balance
  POST   /api/v1/client/wallet/transfer/                    — P2P fund transfer (PIN protected)
"""
from django.urls import path

from apps.client.apis.sync.order_views import (
    ClientOrderDetailView,
    ClientOrderListView,
)
from apps.client.apis.sync.profile_views import (
    ClientAddressDetailView,
    ClientAddressListCreateView,
    ClientAddressSetDefaultView,
    ClientProfileView,
)
from apps.client.apis.sync.review_views import ClientReviewCreateView
from apps.client.apis.sync.wallet_views import (
    ClientWalletBalanceView,
    ClientWalletTransferView,
)
from apps.client.apis.sync.wishlist_views import (
    ClientWishlistToggleView,
    ClientWishlistView,
)

app_name = "client"

urlpatterns = [
    # ── Profile ────────────────────────────────────────────────────
    path("profile/", ClientProfileView.as_view(), name="profile"),

    # ── Addresses ──────────────────────────────────────────────────
    path("addresses/", ClientAddressListCreateView.as_view(), name="address-list"),
    path("addresses/<uuid:address_id>/", ClientAddressDetailView.as_view(), name="address-detail"),
    path(
        "addresses/<uuid:address_id>/set-default/",
        ClientAddressSetDefaultView.as_view(),
        name="address-set-default",
    ),

    # ── Orders ─────────────────────────────────────────────────────
    path("orders/", ClientOrderListView.as_view(), name="orders"),
    path("orders/<str:oid>/", ClientOrderDetailView.as_view(), name="order-detail"),

    # ── Wishlist ───────────────────────────────────────────────────
    path("wishlist/", ClientWishlistView.as_view(), name="wishlist"),
    path("wishlist/toggle/", ClientWishlistToggleView.as_view(), name="wishlist-toggle"),

    # ── Reviews ────────────────────────────────────────────────────
    path("reviews/create/", ClientReviewCreateView.as_view(), name="review-create"),

    # ── Wallet ─────────────────────────────────────────────────────
    path("wallet/balance/", ClientWalletBalanceView.as_view(), name="wallet-balance"),
    path("wallet/transfer/", ClientWalletTransferView.as_view(), name="wallet-transfer"),
]

