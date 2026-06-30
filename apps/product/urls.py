# apps/product/urls.py
"""
Product domain URL configuration.

All routes are prefixed with /api/v1/products/ in the root urls.py. Product
reads live under /api/v1/ninja/products/; these DRF routes are write-only.

URL Names (used in reverse() / tests):
  Public:
    product-list               GET  /api/v1/products/
    product-detail             GET  /api/v1/products/<slug>/
    product-featured           GET  /api/v1/products/featured/
    product-by-category        GET  /api/v1/products/category/<category_id>/
    product-reviews-list       GET/POST /api/v1/products/<product_slug>/reviews/
    product-wishlist-toggle    POST /api/v1/products/wishlist/<slug>/toggle/

  Vendor:
    vendor-product-list        GET/POST /api/v1/products/vendor/
    vendor-product-detail      GET/PATCH/DELETE /api/v1/products/vendor/<slug>/
    vendor-product-publish     POST /api/v1/products/vendor/<slug>/publish/
    vendor-product-gallery     GET/POST /api/v1/products/vendor/<slug>/media/
    vendor-product-gallery-delete  DELETE /api/v1/products/vendor/<slug>/media/<gid>/
    vendor-inventory           GET/POST /api/v1/products/vendor/<slug>/inventory/
    vendor-coupon-list         GET/POST /api/v1/products/coupons/

  Phase 8 — Size Guides, Shipping Profiles, Commission Snapshots:
    vendor-size-guide-list     GET/POST  /api/v1/products/size-guides/
    vendor-size-guide-detail   GET/PATCH/DELETE /api/v1/products/size-guides/<pk>/
    vendor-shipping-list       GET/POST  /api/v1/products/shipping-profiles/
    vendor-shipping-detail     GET/PATCH /api/v1/products/shipping-profiles/<pk>/
    admin-commission-list      GET/POST  /api/v1/products/commission-snapshots/
    admin-commission-detail    GET/PATCH /api/v1/products/commission-snapshots/<pk>/
"""

from django.urls import path

from apps.product.apis.sync.product_views import (
    AdminProductApproveView,
    AdminProductRejectView,
    FeaturedProductListView,
    ProductDetailView,
    ProductListView,
    ProductReviewListCreateView,
    ProductsByCategoryView,
    VendorCouponListCreateView,
    VendorCouponDetailView,
    VendorInventoryLogView,
    VendorProductDetailView,
    VendorProductGalleryDeleteView,
    VendorProductGalleryView,
    VendorProductListCreateView,
    VendorProductPublishView,
    VendorReviewReplyView,
    WishlistListView,
    WishlistMergeView,
    WishlistToggleView,
)

# Phase 8 — new DRF write views
from apps.product.apis.sync.size_guide_views import (
    VendorSizeGuideListCreateView,
    VendorSizeGuideDetailView,
)
from apps.product.apis.sync.shipping_views import (
    VendorShippingProfileListCreateView,
    VendorShippingProfileDetailView,
)
from apps.product.apis.sync.commission_views import (
    AdminCommissionSnapshotListCreateView,
    AdminCommissionSnapshotDetailView,
)

app_name = "product"

urlpatterns = [
    # ── Public ──────────────────────────────────────────────────────────────
    path("", ProductListView.as_view(), name="product-list"),
    path("featured/", FeaturedProductListView.as_view(), name="product-featured"),
    path("category/<str:category_id>/", ProductsByCategoryView.as_view(), name="product-by-category"),

    # ── Wishlist ─────────────────────────────────────────────────────────────
    path("wishlist/", WishlistListView.as_view(), name="product-wishlist-list"),
    path("wishlist/merge/", WishlistMergeView.as_view(), name="product-wishlist-merge"),
    path("wishlist/<slug:slug>/toggle/", WishlistToggleView.as_view(), name="product-wishlist-toggle"),
    path("<slug:slug>/wishlist/toggle/", WishlistToggleView.as_view(), name="product-wishlist-toggle-by-product"),

    # ── Coupons ──────────────────────────────────────────────────────────────
    path("coupons/", VendorCouponListCreateView.as_view(), name="vendor-coupon-list"),
    path("coupons/<uuid:coupon_id>/", VendorCouponDetailView.as_view(), name="vendor-coupon-detail"),

    # ── Vendor ───────────────────────────────────────────────────────────────
    path("vendor/", VendorProductListCreateView.as_view(), name="vendor-product-list"),
    path("vendor/<slug:slug>/", VendorProductDetailView.as_view(), name="vendor-product-detail"),
    path("vendor/<slug:slug>/publish/", VendorProductPublishView.as_view(), name="vendor-product-publish"),
    path("vendor/<slug:slug>/media/", VendorProductGalleryView.as_view(), name="vendor-product-gallery"),
    path("vendor/<slug:slug>/media/<uuid:gid>/", VendorProductGalleryDeleteView.as_view(), name="vendor-product-gallery-delete"),
    path("vendor/<slug:slug>/inventory/", VendorInventoryLogView.as_view(), name="vendor-inventory"),
    path("vendor/reviews/<uuid:review_id>/reply/", VendorReviewReplyView.as_view(), name="vendor-review-reply"),

    # ── Reviews (per-product) ─────────────────────────────────────────────────
    path("<slug:product_slug>/reviews/", ProductReviewListCreateView.as_view(), name="product-reviews-list"),

    # ── Phase 8: Size Guides ─────────────────────────────────────────────────
    path("size-guides/", VendorSizeGuideListCreateView.as_view(), name="vendor-size-guide-list"),
    path("size-guides/<uuid:pk>/", VendorSizeGuideDetailView.as_view(), name="vendor-size-guide-detail"),

    # ── Phase 8: Shipping Profiles ───────────────────────────────────────────
    path("shipping-profiles/", VendorShippingProfileListCreateView.as_view(), name="vendor-shipping-list"),
    path("shipping-profiles/<uuid:pk>/", VendorShippingProfileDetailView.as_view(), name="vendor-shipping-detail"),

    # ── Phase 8: Commission Snapshots (admin only) ───────────────────────────
    path("commission-snapshots/", AdminCommissionSnapshotListCreateView.as_view(), name="admin-commission-list"),
    path("commission-snapshots/<uuid:pk>/", AdminCommissionSnapshotDetailView.as_view(), name="admin-commission-detail"),

    # ── Public detail (must be LAST to avoid shadowing named paths above) ────
    path("<slug:slug>/", ProductDetailView.as_view(), name="product-detail"),

    # ── Admin ─────────────────────────────────────────────────────────────────
    path("admin/<slug:slug>/approve/", AdminProductApproveView.as_view(), name="admin-product-approve"),
    path("admin/<slug:slug>/reject/", AdminProductRejectView.as_view(), name="admin-product-reject"),
]


from django.urls import path

from apps.product.apis.sync.product_views import (
    AdminProductApproveView,
    AdminProductRejectView,
    FeaturedProductListView,
    ProductDetailView,
    ProductListView,
    ProductReviewListCreateView,
    ProductsByCategoryView,
    VendorCouponListCreateView,
    VendorCouponDetailView,
    VendorInventoryLogView,
    VendorProductDetailView,
    VendorProductGalleryDeleteView,
    VendorProductGalleryView,
    VendorProductListCreateView,
    VendorProductPublishView,
    VendorReviewReplyView,
    WishlistListView,
    WishlistMergeView,
    WishlistToggleView,
)

app_name = "product"

urlpatterns = [
    # ── Public ──────────────────────────────────────────────────────────────
    path("", ProductListView.as_view(), name="product-list"),
    path("featured/", FeaturedProductListView.as_view(), name="product-featured"),
    path("category/<str:category_id>/", ProductsByCategoryView.as_view(), name="product-by-category"),

    # ── Wishlist ─────────────────────────────────────────────────────────────
    path("wishlist/", WishlistListView.as_view(), name="product-wishlist-list"),
    path("wishlist/merge/", WishlistMergeView.as_view(), name="product-wishlist-merge"),
    path("wishlist/<slug:slug>/toggle/", WishlistToggleView.as_view(), name="product-wishlist-toggle"),
    path("<slug:slug>/wishlist/toggle/", WishlistToggleView.as_view(), name="product-wishlist-toggle-by-product"),

    # ── Coupons ──────────────────────────────────────────────────────────────
    path("coupons/", VendorCouponListCreateView.as_view(), name="vendor-coupon-list"),
    path("coupons/<uuid:coupon_id>/", VendorCouponDetailView.as_view(), name="vendor-coupon-detail"),

    # ── Vendor ───────────────────────────────────────────────────────────────
    path("vendor/", VendorProductListCreateView.as_view(), name="vendor-product-list"),
    path("vendor/<slug:slug>/", VendorProductDetailView.as_view(), name="vendor-product-detail"),
    path("vendor/<slug:slug>/publish/", VendorProductPublishView.as_view(), name="vendor-product-publish"),
    path("vendor/<slug:slug>/media/", VendorProductGalleryView.as_view(), name="vendor-product-gallery"),
    path("vendor/<slug:slug>/media/<uuid:gid>/", VendorProductGalleryDeleteView.as_view(), name="vendor-product-gallery-delete"),
    path("vendor/<slug:slug>/inventory/", VendorInventoryLogView.as_view(), name="vendor-inventory"),
    path("vendor/reviews/<uuid:review_id>/reply/", VendorReviewReplyView.as_view(), name="vendor-review-reply"),

    # ── Reviews (per-product) ─────────────────────────────────────────────────
    path("<slug:product_slug>/reviews/", ProductReviewListCreateView.as_view(), name="product-reviews-list"),

    # ── Public detail (must be LAST to avoid shadowing named paths above) ────
    path("<slug:slug>/", ProductDetailView.as_view(), name="product-detail"),

    # ── Admin ─────────────────────────────────────────────────────────────────
    path("admin/<slug:slug>/approve/", AdminProductApproveView.as_view(), name="admin-product-approve"),
    path("admin/<slug:slug>/reject/", AdminProductRejectView.as_view(), name="admin-product-reject"),
]
