# apps/product/urls.py
"""
Product domain URL configuration.

All routes prefixed with /api/v1/products/ in the root urls.py.
"""

from django.urls import path
from apps.product.apis.sync.product_views import (
    ProductListView,
    FeaturedProductListView,
    ProductDetailView,
    VendorProductListCreateView,
    VendorProductDetailView,
    VendorProductPublishView,
    VendorProductGalleryView,
    VendorProductGalleryDeleteView,
    ProductReviewListCreateView,
    WishlistListView,
    WishlistToggleView,
    VendorCouponListCreateView,
)

app_name = "product"

urlpatterns = [
    # ── Public ────────────────────────────────────────────────────────────
    path("", ProductListView.as_view(), name="product-list"),
    path("featured/", FeaturedProductListView.as_view(), name="product-featured"),
    path("<slug:slug>/", ProductDetailView.as_view(), name="product-detail"),
    path("<slug:slug>/reviews/", ProductReviewListCreateView.as_view(), name="product-reviews"),

    # ── Client: Wishlist ──────────────────────────────────────────────────
    path("wishlist/", WishlistListView.as_view(), name="wishlist-list"),
    path("wishlist/<slug:slug>/toggle/", WishlistToggleView.as_view(), name="wishlist-toggle"),

    # ── Vendor: Product CRUD ──────────────────────────────────────────────
    path("vendor/", VendorProductListCreateView.as_view(), name="vendor-product-list-create"),
    path("vendor/<slug:slug>/", VendorProductDetailView.as_view(), name="vendor-product-detail"),
    path("vendor/<slug:slug>/publish/", VendorProductPublishView.as_view(), name="vendor-product-publish"),

    # ── Vendor: Gallery ───────────────────────────────────────────────────
    path("vendor/<slug:slug>/media/", VendorProductGalleryView.as_view(), name="vendor-product-gallery"),
    path("vendor/<slug:slug>/media/<uuid:gid>/", VendorProductGalleryDeleteView.as_view(), name="vendor-product-gallery-delete"),

    # ── Vendor: Coupons ───────────────────────────────────────────────────
    path("coupons/", VendorCouponListCreateView.as_view(), name="vendor-coupon-list-create"),
]
