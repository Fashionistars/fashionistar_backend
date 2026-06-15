# apps/product/serializers/__init__.py
from .product_serializers import (
    ProductSizeAndMeasurementGuideSerializer,
    ProductMeasurementGuideSerializer,
    ProductTagSerializer,
    ProductVendorMiniSerializer,
    ProductVariantGalleryMediaSerializer,
    ProductVariantGalleryMediaWriteSerializer,
    ProductFaqSerializer,
    ProductFabricSpecificationSerializer,
    ProductListSerializer,
    ProductDetailSerializer,
    ProductWriteSerializer,
    ProductWriteFullSerializer,
    ProductAdminSerializer,
    ProductInventoryLogSerializer,
    ProductWishlistSerializer,
    ProductDraftSessionSerializer,
)
from .review_serializers import (
    ProductReviewSerializer,
    ProductReviewWriteSerializer,
    VendorReplySerializer,
    HelpfulVoteSerializer,
)
from .coupon_serializers import CouponSerializer

__all__ = [
    # Taxonomy
    "ProductSizeAndMeasurementGuideSerializer",
    "ProductTagSerializer",
    "ProductVendorMiniSerializer",
    # Media
    "ProductVariantGalleryMediaSerializer",
    "ProductVariantGalleryMediaWriteSerializer",
    # Content
    "ProductFaqSerializer",
    # Phase 2 new taxonomy
    "ProductFabricSpecificationSerializer",
    "ProductMeasurementGuideSerializer",
    # "ProductCertificationSerializer",
    # Product CRUD
    "ProductListSerializer",
    "ProductDetailSerializer",
    "ProductWriteSerializer",
    "ProductWriteFullSerializer",
    "ProductAdminSerializer",
    # Logs
    "ProductInventoryLogSerializer",
    "ProductWishlistSerializer",
    "ProductDraftSessionSerializer",
    # Reviews
    "ProductReviewSerializer",
    "ProductReviewWriteSerializer",
    "VendorReplySerializer",
    "HelpfulVoteSerializer",
    # Coupons
    "CouponSerializer",
]
