# apps/product/serializers/__init__.py
from apps.product.serializers.product_serializers import (
    ProductListSerializer,
    ProductDetailSerializer,
    ProductWriteSerializer,
    ProductGalleryMediaSerializer,
    ProductVariantSerializer,
    ProductSizeSerializer,
    ProductColorSerializer,
    ProductTagSerializer,
    ProductSpecificationSerializer,
    ProductFaqSerializer,
)
from apps.product.serializers.review_serializers import (
    ProductReviewSerializer,
    ProductReviewWriteSerializer,
)
from apps.product.serializers.coupon_serializers import (
    CouponSerializer,
    CouponWriteSerializer,
)

__all__ = [
    "ProductListSerializer",
    "ProductDetailSerializer",
    "ProductWriteSerializer",
    "ProductGalleryMediaSerializer",
    "ProductVariantSerializer",
    "ProductSizeSerializer",
    "ProductColorSerializer",
    "ProductTagSerializer",
    "ProductSpecificationSerializer",
    "ProductFaqSerializer",
    "ProductReviewSerializer",
    "ProductReviewWriteSerializer",
    "CouponSerializer",
    "CouponWriteSerializer",
]
