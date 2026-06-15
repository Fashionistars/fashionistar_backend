# apps/product/admin/__init__.py
"""
Admin package for the Product domain.
All admin classes are registered in product_admin.py.
"""
from apps.product.admin.product_admin import (  # noqa: F401
    ProductAdmin,
    ProductFaqAdmin,
    ProductReviewAdmin,
    CouponAdmin,
    DeliveryCourierAdmin,
    ProductTagAdmin,
    ProductVariantGalleryMediaAdmin,
    ProductFabricAdmin,
    ProductSizeAndMeasurementGuideAdmin,
    ProductShippingProfileAdmin,
    ProductPriceHistoryAdmin,
    ProductViewLogAdmin,
    ProductInventoryLogAdmin,
    ProductWishlistAdmin,
    ProductCommissionSnapshotAdmin,
)
