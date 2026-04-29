"""Django-Ninja response schemas for cart async read endpoints."""

from __future__ import annotations

from ninja import Schema


class CartProductRefOut(Schema):
    """Compact product snapshot used inside cart lines."""

    id: str
    slug: str
    title: str
    sku: str
    cover_image_url: str | None
    requires_measurement: bool
    vendor_name: str


class CartItemOut(Schema):
    """Cart item payload with snapshotted price and variant labels."""

    id: str
    product: CartProductRefOut
    variant_id: str | None
    size_label: str | None
    color_label: str | None
    quantity: int
    unit_price: str
    line_total: str
    currency: str


class CartOut(Schema):
    """Authenticated user's current cart summary."""

    id: str | None
    items: list[CartItemOut]
    item_count: int
    subtotal: str
    currency: str
    expires_at: str | None
