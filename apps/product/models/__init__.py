# apps/product/models/__init__.py
"""
Public model barrel for the product domain.

Import from this module in serializers, selectors, services, and admin:
    from apps.product.models import Product, ProductFabric, ...

Phase 1 expansion (2026):
    - ProductFabric        — fabric composition, care instructions, organic flags
    - ProductMeasurementGuide — size chart rows per product
    - ProductShippingProfile  — per-product shipping rules
    - ProductPriceHistory  — append-only price change audit trail
    - ProductViewLog       — AI recommendation engine analytics events
"""
from apps.product.models.product import (
    # ── Choices ─────────────────────────────────────────────────────────────
    ProductStatus,
    # ── Taxonomy ────────────────────────────────────────────────────────────
    ProductTag,
    # ── Core product ────────────────────────────────────────────────────────
    Product,
    # ── Variants & inventory ────────────────────────────────────────────────
    ProductVariantGalleryMedia,
    ProductInventoryLog,
    # ── Social / engagement ─────────────────────────────────────────────────
    ProductReview,
    ProductWishlist,
    # ── Financial ───────────────────────────────────────────────────────────
    ProductCommissionSnapshot,
    # ── Commerce ────────────────────────────────────────────────────────────
    Coupon,
    DeliveryCourier,
    # ── Phase 1 enterprise expansions (2026) ────────────────────────────────
    ProductFabric,
    ProductSizeAndMeasurementGuide,
    ProductShippingProfile,
    ProductPriceHistory,
    ProductViewLog,
    ProductDraftStatus,
    ProductDraftSession,
)

__all__ = [
    # Choices
    "ProductStatus",
    "ProductDraftStatus",
    # Taxonomy
    "ProductTag",
    # Product content
    "ProductSpecification",
    "ProductFaq",
    # Core
    "Product",
    "ProductDraftSession",
    # Variants & inventory
    "ProductVariantGalleryMedia",
    "ProductInventoryLog",
    # Social
    "ProductReview",
    "ProductWishlist",
    # Financial
    "ProductCommissionSnapshot",
    # Commerce
    "Coupon",
    "DeliveryCourier",
    # Phase 1 enterprise expansions
    "ProductFabric",
    "ProductSizeAndMeasurementGuide",
    "ProductShippingProfile",
    "ProductPriceHistory",
    "ProductViewLog",
]
