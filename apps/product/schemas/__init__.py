# apps/product/schemas/__init__.py
"""
Ninja typed schemas for async product read endpoints.
Used by apps/product/apis/async_/ views.
"""
from apps.product.schemas.product_schemas import (
    CouponOut,
    ProductCategoryOut,
    ProductDetailOut,
    ProductVariantGalleryMediaOut,
    ProductListItemOut,
    ProductReviewOut,
    ProductSizeAndMeasurementGuideOut,
    ProductVendorOut,
    WishlistItemOut,
)

__all__ = [
    "CouponOut",
    "ProductCategoryOut",
    "ProductDetailOut",
    "ProductVariantGalleryMediaOut",
    "ProductListItemOut",
    "ProductReviewOut",
    "ProductSizeAndMeasurementGuideOut",
    "ProductVendorOut",
    "WishlistItemOut",
]
