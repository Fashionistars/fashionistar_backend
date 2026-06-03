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
    VendorProductDraftListView,
    VendorProductDraftDetailView,
    VendorProductDraftCommitView,
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

    # ── Vendor Drafts ────────────────────────────────────────────────────────
    path("vendor/drafts/", VendorProductDraftListView.as_view(), name="vendor-product-draft-list"),
    path("vendor/drafts/<uuid:draft_key>/", VendorProductDraftDetailView.as_view(), name="vendor-product-draft-detail"),
    path("vendor/drafts/<uuid:draft_key>/commit/", VendorProductDraftCommitView.as_view(), name="vendor-product-draft-commit"),

    # ── Reviews (per-product) ─────────────────────────────────────────────────
    path("<slug:product_slug>/reviews/", ProductReviewListCreateView.as_view(), name="product-reviews-list"),

    # ── Public detail (must be LAST to avoid shadowing named paths above) ────
    path("<slug:slug>/", ProductDetailView.as_view(), name="product-detail"),

    # ── Admin ─────────────────────────────────────────────────────────────────
    path("admin/<slug:slug>/approve/", AdminProductApproveView.as_view(), name="admin-product-approve"),
    path("admin/<slug:slug>/reject/", AdminProductRejectView.as_view(), name="admin-product-reject"),
]
