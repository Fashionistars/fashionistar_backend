# apps/product/urls.py
"""
Product domain URL configuration.

All routes are prefixed with /api/v1/products/ in the root urls.py. Product
reads live under /api/v1/ninja/products/; these DRF routes are write-only.
"""

from django.urls import path

from apps.product.apis.sync.product_views import (
    ProductReviewListCreateView,
    VendorCouponListCreateView,
    VendorProductDetailView,
    VendorProductGalleryDeleteView,
    VendorProductGalleryView,
    VendorProductListCreateView,
    VendorProductPublishView,
    WishlistToggleView,
)

app_name = "product"

urlpatterns = [
    path("wishlist/<slug:slug>/toggle/", WishlistToggleView.as_view(), name="wishlist-toggle"),
    path("coupons/", VendorCouponListCreateView.as_view(), name="vendor-coupon-list-create"),
    path("vendor/", VendorProductListCreateView.as_view(), name="vendor-product-list-create"),
    path("vendor/<slug:slug>/", VendorProductDetailView.as_view(), name="vendor-product-detail"),
    path("vendor/<slug:slug>/publish/", VendorProductPublishView.as_view(), name="vendor-product-publish"),
    path("vendor/<slug:slug>/media/", VendorProductGalleryView.as_view(), name="vendor-product-gallery"),
    path("vendor/<slug:slug>/media/<uuid:gid>/", VendorProductGalleryDeleteView.as_view(), name="vendor-product-gallery-delete"),
    path("<slug:slug>/reviews/", ProductReviewListCreateView.as_view(), name="product-reviews"),
]
