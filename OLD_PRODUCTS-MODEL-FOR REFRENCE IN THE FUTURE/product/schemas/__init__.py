# apps/product/schemas/__init__.py
"""
Ninja typed schemas for async product read endpoints.
Used by apps/product/apis/async_/ views.
"""
from apps.product.schemas.product_schemas import (
    CouponOut,
    ProductBrandOut,
    ProductCategoryOut,
    ProductColorOut,
    ProductDetailOut,
    ProductGalleryMediaOut,
    ProductListItemOut,
    ProductReviewOut,
    ProductSizeOut,
    ProductTagOut,
    ProductVariantOut,
    ProductVendorOut,
    WishlistItemOut,
)

__all__ = [
    "CouponOut",
    "ProductBrandOut",
    "ProductCategoryOut",
    "ProductColorOut",
    "ProductDetailOut",
    "ProductGalleryMediaOut",
    "ProductListItemOut",
    "ProductReviewOut",
    "ProductSizeOut",
    "ProductTagOut",
    "ProductVariantOut",
    "ProductVendorOut",
    "WishlistItemOut",
]
