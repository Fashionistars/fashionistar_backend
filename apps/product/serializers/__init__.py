# apps/product/serializers/__init__.py
from .product_serializers import (
    ProductSizeTypeSerializer,
    ProductSizeSerializer,
    ProductColorSerializer,
    ProductTagSerializer,
    ProductVendorMiniSerializer,
    ProductGalleryMediaSerializer,
    ProductSpecificationSerializer,
    ProductFaqSerializer,
    ProductVariantSerializer,
    ProductVariantWriteSerializer,
    ProductFabricSerializer,
    ProductMeasurementGuideSerializer,
    ProductCertificationSerializer,
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
    "ProductSizeTypeSerializer",
    "ProductSizeSerializer",
    "ProductColorSerializer",
    "ProductTagSerializer",
    "ProductVendorMiniSerializer",
    # Media
    "ProductGalleryMediaSerializer",
    # Content
    "ProductSpecificationSerializer",
    "ProductFaqSerializer",
    # Variants
    "ProductVariantSerializer",
    "ProductVariantWriteSerializer",
    # Phase 2 new taxonomy
    "ProductFabricSerializer",
    "ProductMeasurementGuideSerializer",
    "ProductCertificationSerializer",
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
