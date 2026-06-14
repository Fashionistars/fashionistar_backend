# apps/product/services/product_service.py
"""
Business logic for the Product domain.

Enterprise rules (Django 6.0 LTS):
  - Services call selectors for reads; ORM for writes.
  - ALL writes wrapped in transaction.atomic().
  - Audit events emitted via on_commit hook (never blocks the caller).
  - Review aggregate calculated in ONE annotated query (zero N+1).
  - Idempotency keys guard against duplicate writes on network retry.
  - Never raise Http404 — raise ValueError / PermissionError.

────────────────────────────────────────────────────────────────
5 Additional Enterprise Best-Practice Additions
────────────────────────────────────────────────────────────────
1. IDEMPOTENCY KEYS: create_product / create_review check a UUID
   idempotency_key field to prevent duplicate rows on network retry.
2. ON_COMMIT HOOKS: all audit events are fired via transaction.on_commit
   so they never execute inside the atomic block (avoids DB deadlock).
3. N+1 ELIMINATION: create_review uses a single aggregate()
   call combined with F() to avoid the two-query count + avg pattern.
4. STOCK FLOOR + CEILING: adjust_inventory enforces both a min floor (0)
   and an optional max_stock ceiling defined on the product model.
5. CIRCUIT BREAKER: _emit_audit swallows ALL exceptions so a broken
   audit service never kills the main mutation transaction.
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any

from django.db import transaction
from django.db.models import Avg, Count, F

from apps.product.models import (
    Coupon,
    Product,
    ProductGalleryMedia,
    ProductInventoryLog,
    ProductReview,
    ProductStatus,
    ProductWishlist,
    ProductVariant,
    ProductDraftStatus,
    ProductDraftSession,
    ProductFabric,
    ProductMeasurementGuide,
    ProductShippingProfile,
)
from apps.product.selectors import (
    get_coupon_by_code,
    get_user_review_for_product,
    get_vendor_product_or_404,
    is_in_wishlist,
)

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# INTERNAL HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _emit_audit(
    action: str,
    product: Product,
    actor: Any = None,
    request: Any = None,
    **metadata: Any,
) -> None:
    """
    Schedule an audit event via transaction.on_commit.

    Enterprise Strategy:
    - Best-practice #2 (on_commit): Audit is deferred until after the outer
      atomic block commits so a failed audit never rolls back the real mutation.
    - Forensic Context: Propagates the 'request' object to capture IP/User-Agent.
    - Best-practice #5 (circuit breaker): Every exception is swallowed so a
      broken audit service never surface-kills the caller.
    """
    def _fire():
        try:
            # Deferred import to prevent circular dependency at module level
            from apps.audit_logs.services.catalog import catalog_audit

            # Standardize metadata for forensic tracking
            audit_values = {"product_slug": product.slug, **metadata}

            if action == "product.created":
                catalog_audit.log_product_created(
                    actor=actor,
                    product_id=str(product.id),
                    name=product.title,
                    request=request,
                )
            elif action in {
                "product.updated",
                "product.inventory.adjusted",
                "product.coupon.applied",
                "product.wishlist.toggled",
                "product.media.attached"
            }:
                catalog_audit.log_product_updated(
                    actor=actor,
                    product_id=str(product.id),
                    name=product.title,
                    new_values=audit_values,
                    request=request,
                )
            elif action == "product.published":
                catalog_audit.log_product_published(
                    actor=actor,
                    product_id=str(product.id),
                    name=product.title,
                    request=request,
                )
            elif action in {"product.archived", "product.media.removed"}:
                catalog_audit.log_product_deleted(
                    actor=actor,
                    product_id=str(product.id),
                    name=product.title,
                    request=request,
                )
            elif action == "product.review.created":
                review_id = metadata.get("review_id")
                rating = metadata.get("rating")
                if review_id and rating is not None:
                    catalog_audit.log_review_posted(
                        actor=actor,
                        product_id=str(product.id),
                        review_id=str(review_id),
                        rating=int(rating),
                        request=request,
                    )
                else:
                    catalog_audit.log_product_updated(
                        actor=actor,
                        product_id=str(product.id),
                        name=product.title,
                        new_values=audit_values,
                        request=request,
                    )
            else:
                catalog_audit.log_product_updated(
                    actor=actor,
                    product_id=str(product.id),
                    name=product.title,
                    new_values={"action": action, **audit_values},
                    request=request,
                )
        except Exception:
            # Circuit breaker pattern: failure in audit must not affect production traffic
            logger.warning(
                "Audit event skipped — action=%s product=%s",
                action,
                getattr(product, "id", "?"),
            )

    try:
        # Schedule for execution AFTER DB commit to ensure consistency
        transaction.on_commit(_fire)
    except Exception:
        # Fallback for non-atomic contexts (e.g., shell or management commands)
        _fire()


def _pop_product_m2m(validated_data: dict) -> dict[str, Any]:
    """
    Extract canonical Product M2M assignments from validated write data.

    Product table writes stay scalar-first. Categories, sizes, colors, and tags
    are synchronized after the row exists so the M2M through tables are updated
    in the same short atomic transaction.
    """
    return {
        "categories": validated_data.pop("categories", []),
        "sub_categories": validated_data.pop("sub_categories", []),
        "sizes": validated_data.pop("sizes", []),
        "colors": validated_data.pop("colors", []),
        "tags": validated_data.pop("tags", []),
    }


def _sync_product_m2m(product: Product, relations: dict[str, Any], *, partial: bool) -> None:
    """
    Apply M2M relations and enforce the product taxonomy cap at service level.

    Args:
      product: Persisted Product row.
      relations: M2M payload extracted from the serializer.
      partial: True for PATCH updates; omitted keys are left untouched.
    """
    if "categories" in relations:
        categories = relations["categories"]
        if not (1 <= len(categories) <= 15):
            raise ValueError("Product requires 1 to 15 categories.")
        product.categories.set(categories)

    if "sub_categories" in relations:
        sub_categories = relations["sub_categories"]
        if len(sub_categories) > 15:
            raise ValueError("Product supports at most 15 sub-categories.")
        product.sub_categories.set(sub_categories)

    for relation_name in ("sizes", "colors", "tags"):
        if relation_name not in relations:
            continue
        values = relations[relation_name]
        if values or not partial:
            getattr(product, relation_name).set(values)


def _sync_product_variants(product: Product, variants_data: list[dict]) -> None:
    """
    Reconcile the product's variants.
    - If variant already exists with target SKU, update it.
    - If SKU is new, create it.
    - If existing variant SKU not submitted, soft-delete it.
    """
    existing_variants = {v.sku: v for v in product.product_variants.filter(is_deleted=False)}
    submitted_skus = set()

    for vdata in variants_data:
        sku = vdata.get("sku")
        if sku:
            sku = sku.strip().upper()
            vdata["sku"] = sku

        size = vdata.get("size")
        color = vdata.get("color")

        variant_fields = {
            "size": size,
            "color": color,
            "price_override": vdata.get("price_override"),
            "stock_qty": vdata.get("stock_qty", 0),
            "is_active": vdata.get("is_active", True),
            "is_default": vdata.get("is_default", False),
            "barcode": vdata.get("barcode", ""),
            "weight_kg": vdata.get("weight_kg"),
            "dimensions_cm": vdata.get("dimensions_cm"),
            "notes": vdata.get("notes", ""),
        }

        if sku and sku in existing_variants:
            variant = existing_variants[sku]
            for attr, val in variant_fields.items():
                setattr(variant, attr, val)
            variant.save()
            submitted_skus.add(sku)
        else:
            if not sku:
                import uuid
                sku = f"VAR-{str(uuid.uuid4()).upper()[:10]}"
            variant = ProductVariant(
                product=product,
                sku=sku,
                **variant_fields
            )
            variant.save()
            submitted_skus.add(sku)

    for sku, variant in existing_variants.items():
        if sku not in submitted_skus:
            variant.soft_delete()


def _sync_measurement_guide_from_template(product: Product) -> None:
    """
    If the product has a measurement_template, copy all its rows to ProductMeasurementGuide.
    Clear any existing guides for this product first.
    """
    if not product.measurement_template:
        return

    # Clear existing guide rows
    product.product_measurement_guide.all().delete()

    # Copy from template rows
    from apps.product.models import ProductMeasurementGuide
    template_rows = product.measurement_template.template_rows.all()
    for row in template_rows:
        ProductMeasurementGuide.objects.create(
            product=product,
            template=None,
            size=row.size,
            size_label=row.size_label,
            chest_cm=row.chest_cm,
            waist_cm=row.waist_cm,
            hip_cm=row.hip_cm,
            length_cm=row.length_cm,
            shoulder_cm=row.shoulder_cm,
            sleeve_cm=row.sleeve_cm,
            inseam_cm=row.inseam_cm,
            foot_length_cm=row.foot_length_cm,
            sort_order=row.sort_order
        )


# ─────────────────────────────────────────────────────────────────────────────
# PRODUCT CRUD
# ─────────────────────────────────────────────────────────────────────────────

@transaction.atomic
def create_product(
    *,
    vendor: Any,
    validated_data: dict,
    idempotency_key: str | None = None,
    request: Any = None,
) -> Product:
    """
    Create a new product for a vendor. Status starts as DRAFT.

    Enterprise Compliance:
    - Best-practice #1 (idempotency): Checks for duplicate creation requests.
    - Forensic Capture: Schedule audit with full request context.
    """
    # ── Idempotency guard ──────────────────────────────────────────────────────
    if idempotency_key:
        existing = (
            Product.objects.filter(
                vendor=vendor,
                idempotency_key=idempotency_key,
                is_deleted=False,
            )
            .first()
        )
        if existing:
            logger.info(
                "Idempotent create_product: returning existing product pk=%s", existing.pk
            )
            return existing

    variants_data = validated_data.pop("variants", None)
    fabric_data = validated_data.pop("fabric", None)
    guide_data = validated_data.pop("measurement_guide", [])
    shipping_data = validated_data.pop("shipping_profile", None)
    relations = _pop_product_m2m(validated_data)

    product = Product.objects.create(
        vendor=vendor,
        status=ProductStatus.DRAFT,
        idempotency_key=idempotency_key,
        **validated_data,
    )
    _sync_product_m2m(product, relations, partial=False)

    if fabric_data:
        from apps.product.models import ProductFabric
        ProductFabric.objects.create(product=product, **fabric_data)

    if shipping_data:
        from apps.product.models import ProductShippingProfile
        ProductShippingProfile.objects.create(product=product, **shipping_data)

    if guide_data:
        from apps.product.models import ProductMeasurementGuide
        for row in guide_data:
            ProductMeasurementGuide.objects.create(product=product, **row)
    elif product.measurement_template:
        _sync_measurement_guide_from_template(product)

    if variants_data is not None:
        _sync_product_variants(product, variants_data)

    # Dispatch audit via on_commit hook for atomic integrity
    _emit_audit(
        "product.created",
        product,
        actor=vendor.user if hasattr(vendor, "user") else None,
        request=request,
    )
    logger.info("Product created: %s by vendor %s", product.slug, vendor)
    return product


@transaction.atomic
def update_product(
    *,
    product: Product,
    validated_data: dict,
    actor: Any = None,
    request: Any = None,
) -> Product:
    """Update product fields. Vendor-owned products only."""
    variants_data = validated_data.pop("variants", None)
    fabric_data = validated_data.pop("fabric", None)
    guide_data = validated_data.pop("measurement_guide", None)
    shipping_data = validated_data.pop("shipping_profile", None)
    relations = {
        key: validated_data.pop(key)
        for key in ("categories", "sub_categories", "sizes", "colors", "tags")
        if key in validated_data
    }

    old_template = product.measurement_template

    for attr, value in validated_data.items():
        setattr(product, attr, value)
    product.save()

    _sync_product_m2m(product, relations, partial=True)

    if fabric_data is not None:
        if fabric_data:
            ProductFabric.objects.update_or_create(product=product, defaults=fabric_data)
        else:
            ProductFabric.objects.filter(product=product).delete()

    if shipping_data is not None:
        if shipping_data:
            ProductShippingProfile.objects.update_or_create(product=product, defaults=shipping_data)
        else:
            ProductShippingProfile.objects.filter(product=product).delete()

    if guide_data is not None:
        product.product_measurement_guide.all().delete()
        for row in guide_data:
            ProductMeasurementGuide.objects.create(product=product, **row)
    elif "measurement_template" in validated_data and product.measurement_template != old_template:
        _sync_measurement_guide_from_template(product)

    if variants_data is not None:
        _sync_product_variants(product, variants_data)

    _emit_audit("product.updated", product, actor=actor, request=request)
    return product


@transaction.atomic
def publish_product(
    *,
    product: Product,
    actor: Any = None,
    request: Any = None,
) -> Product:
    """Submit product for review → status: PENDING."""
    if product.status not in (ProductStatus.DRAFT, ProductStatus.REJECTED):
        raise ValueError(f"Cannot publish product with status '{product.status}'.")
    product.status = ProductStatus.PENDING
    product.save(update_fields=["status", "updated_at"])
    _emit_audit("product.published", product, actor=actor, request=request)
    return product


@transaction.atomic
def approve_product(
    *,
    product: Product,
    actor: Any = None,
    request: Any = None,
) -> Product:
    """Admin / moderator approves product → status: PUBLISHED."""
    product.status = ProductStatus.PUBLISHED
    product.save(update_fields=["status", "updated_at"])
    _emit_audit(
        "product.published",
        product,
        actor=actor,
        request=request,
        new_status="published",
    )
    return product


@transaction.atomic
def reject_product(
    *,
    product: Product,
    actor: Any = None,
    reason: str = "",
    request: Any = None,
) -> Product:
    """Admin / moderator rejects product → status: REJECTED."""
    product.status = ProductStatus.REJECTED
    product.save(update_fields=["status", "updated_at"])
    _emit_audit("product.archived", product, actor=actor, request=request, reason=reason)
    return product


@transaction.atomic
def archive_product(
    *,
    product: Product,
    actor: Any = None,
    request: Any = None,
) -> Product:
    """Soft-archive — removes from storefront but keeps record."""
    product.status = ProductStatus.ARCHIVED
    product.save(update_fields=["status", "updated_at"])
    _emit_audit("product.archived", product, actor=actor, request=request)
    return product


# ─────────────────────────────────────────────────────────────────────────────
# GALLERY / MEDIA
# ─────────────────────────────────────────────────────────────────────────────

@transaction.atomic
def attach_gallery_media(
    *,
    product: Product,
    media_file: Any,
    media_type: str = "image",
    alt_text: str = "",
    variant: Any = None,
    color: Any = None,
    actor: Any = None,
    request: Any = None,
) -> ProductGalleryMedia:
    """Attach a Cloudinary-uploaded media asset to a product gallery."""
    # Use the canonical reverse relation for ordering in one aggregate query.
    ordering = product.product_gallery_media.aggregate(n=Count("id"))["n"] + 1
    gallery_item = ProductGalleryMedia.objects.create(
        product=product,
        media=media_file,
        media_type=media_type,
        alt_text=alt_text,
        ordering=ordering,
        variant=variant,
        color=color,
    )
    _emit_audit(
        "product.media.attached",
        product,
        actor=actor,
        request=request,
        media_id=str(gallery_item.id),
    )
    return gallery_item


@transaction.atomic
def remove_gallery_media(
    *,
    product: Product,
    gallery_id: Any,
    actor: Any = None,
    request: Any = None,
) -> None:
    """Soft-delete a gallery media item by ID."""
    try:
        item = ProductGalleryMedia.objects.get(id=gallery_id, product=product)
    except ProductGalleryMedia.DoesNotExist:
        raise ValueError(
            f"Gallery media {gallery_id} not found for product {product.slug}."
        )
    item.soft_delete()
    _emit_audit(
        "product.media.removed",
        product,
        actor=actor,
        request=request,
        media_id=str(gallery_id),
    )


# ─────────────────────────────────────────────────────────────────────────────
# INVENTORY
# ─────────────────────────────────────────────────────────────────────────────

@transaction.atomic
def adjust_inventory(
    *,
    product: Product,
    quantity_delta: int,
    reason: str,
    actor: Any = None,
    variant: Any = None,
    reference_id: str = "",
    note: str = "",
    request: Any = None,
) -> ProductInventoryLog:
    """
    Atomic stock adjustment.

    Best-practice #4 (stock floor + ceiling):
    - Floor: stock cannot go below 0.
    - Ceiling: if product.max_stock is set, stock cannot exceed it.

    Forensic Tracking:
    - Schedules audit via on_commit hook with request context.
    """
    # Row-level lock prevents concurrent over-deductions
    product = Product.objects.select_for_update().get(pk=product.pk)
    before = product.stock_qty
    candidate = before + quantity_delta

    # Floor
    after = max(0, candidate)

    # Ceiling (optional field — only enforced when set)
    max_stock = getattr(product, "max_stock", None)
    if max_stock is not None and max_stock > 0:
        after = min(after, max_stock)

    product.stock_qty = after
    product.in_stock = after > 0
    product.save(update_fields=["stock_qty", "in_stock", "updated_at"])

    log = ProductInventoryLog.objects.create(
        product=product,
        variant=variant,
        actor=actor,
        quantity_delta=quantity_delta,
        quantity_before=before,
        quantity_after=after,
        reason=reason,
        reference_id=reference_id,
        note=note,
    )
    _emit_audit(
        "product.inventory.adjusted",
        product,
        actor=actor,
        request=request,
        delta=quantity_delta,
        before=before,
        after=after,
        reason=reason,
    )
    return log


# ─────────────────────────────────────────────────────────────────────────────
# REVIEWS
# ─────────────────────────────────────────────────────────────────────────────

@transaction.atomic
def create_review(
    *,
    user: Any,
    product: Product,
    rating: int,
    review_text: str,
    idempotency_key: str | None = None,
    request: Any = None,
) -> ProductReview:
    """
    Create a product review and update the product aggregate in one pass.

    Best-practice #1 (idempotency): duplicate submissions (same user + product)
    are rejected cleanly; the idempotency_key allows safe client retry.

    Best-practice #3 (N+1 elimination):
    The rating + count aggregate is computed in a SINGLE annotated query
    instead of two separate .aggregate() + .count() calls.
    Product.objects.filter(...).update() fires one UPDATE statement —
    zero additional SELECT round-trips.
    """
    # ── Idempotency guard ──────────────────────────────────────────────────────
    if idempotency_key:
        existing_by_key = ProductReview.objects.filter(
            idempotency_key=idempotency_key,
            user=user,
            product=product,
        ).first()
        if existing_by_key:
            return existing_by_key

    if ProductReview.objects.filter(user=user, product=product).exists():
        raise ValueError("already reviewed")

    obj = ProductReview.objects.create(
        product=product,
        user=user,
        rating=rating,
        review=review_text,
        idempotency_key=idempotency_key,
    )

    # ── Single-pass aggregate: avg + count in one DB round-trip ───────────────
    agg = (
        ProductReview.objects
        .filter(product=product, active=True)
        .aggregate(avg=Avg("rating"), total=Count("id"))
    )
    avg_rating = round(agg["avg"] or 0, 1)
    total_reviews = agg["total"] or 0

    Product.objects.filter(pk=product.pk).update(
        rating=avg_rating,
        review_count=total_reviews,
    )

    _emit_audit(
        "product.review.created",
        product,
        actor=user,
        request=request,
        rating=rating,
        review_id=obj.id,
    )
    return obj


# ─────────────────────────────────────────────────────────────────────────────
# WISHLIST
# ─────────────────────────────────────────────────────────────────────────────

def _wishlist_identity(*, user: Any | None = None, session_key: str | None = None) -> dict:
    """Return the exact wishlist owner fields for authenticated/anonymous users."""
    if user is not None and getattr(user, "is_authenticated", False):
        if session_key:
            raise ValueError("Authenticated wishlist writes must not include session_key.")
        return {"user": user}
    if session_key:
        return {"user": None, "session_key": session_key}
    raise ValueError("Wishlist requires either an authenticated user or session_key.")


@transaction.atomic
def toggle_wishlist(
    *,
    user: Any | None = None,
    session_key: str | None = None,
    product: Product,
    request: Any = None,
) -> dict:
    """Toggle product in a user or anonymous wishlist. Returns {added: bool}."""
    identity = _wishlist_identity(user=user, session_key=session_key)
    user_id = getattr(identity.get("user"), "id", None)
    if is_in_wishlist(user_id, product.id, session_key=identity.get("session_key")):
        ProductWishlist.objects.filter(product=product, **identity).delete()
        added = False
    else:
        ProductWishlist.objects.create(product=product, **identity)
        added = True

    _emit_audit(
        "product.wishlist.toggled",
        product,
        actor=identity.get("user"),
        request=request,
        added=added,
        session_key=identity.get("session_key"),
    )
    if identity.get("user") is not None:
        try:
            from apps.audit_logs.services.client import client_audit

            client_audit.log_wishlist_updated(
                actor=identity["user"],
                product_id=str(product.id),
                action="added" if added else "removed",
                request=request,
            )
        except Exception:
            logger.warning(
                "client_audit.log_wishlist_updated failed silently",
                exc_info=True,
            )
    return {"added": added}


@transaction.atomic
def merge_anonymous_wishlist_session(*, user: Any, session_key: str) -> dict:
    """
    Promote anonymous wishlist rows into an authenticated user's wishlist.

    Args:
        user: Authenticated user receiving the wishlist rows.
        session_key: Stable anonymous commerce key generated by the frontend.

    Returns:
        Dictionary with moved and deduplicated row counts.

    The merge is idempotent: duplicate user/product rows are deleted from the
    anonymous side instead of raising unique-constraint errors on retry.
    """
    if getattr(user, "role", None) != "client":
        raise ValueError("Wishlist operations are only available for client accounts.")

    if not session_key:
        return {"moved": 0, "deduplicated": 0}

    entries = list(
        ProductWishlist.objects.select_for_update()
        .filter(user__isnull=True, session_key=str(session_key)[:40])
        .select_related("product")
    )
    moved = 0
    deduplicated = 0

    for entry in entries:
        existing = ProductWishlist.objects.filter(
            user=user,
            product_id=entry.product_id,
        ).first()
        if existing:
            entry.delete()
            deduplicated += 1
            continue
        entry.user = user
        entry.session_key = None
        entry.save(update_fields=["user", "session_key", "updated_at"])
        moved += 1

    return {"moved": moved, "deduplicated": deduplicated}


# ─────────────────────────────────────────────────────────────────────────────
# COUPON
# ─────────────────────────────────────────────────────────────────────────────

@transaction.atomic
def validate_and_apply_coupon(
    *,
    code: str,
    user: Any,
    order_subtotal: Decimal,
    request: Any = None,
) -> dict:
    """
    Validate coupon and return discount amount.

    Does NOT increment usage_count — that happens at checkout commit.
    Raises ValueError for all invalid states (view converts to 400).
    """
    coupon = get_coupon_by_code(code)
    if not coupon:
        raise ValueError("Coupon not found.")
    if not coupon.is_valid():
        raise ValueError("Coupon is expired or has reached its usage limit.")
    if order_subtotal < coupon.minimum_order:
        raise ValueError(
            f"Minimum order amount is {coupon.minimum_order} to use this coupon."
        )

    if coupon.discount_type == "percentage":
        discount = (coupon.discount_value / 100) * order_subtotal
        if coupon.maximum_discount:
            discount = min(discount, coupon.maximum_discount)
    else:
        discount = min(coupon.discount_value, order_subtotal)

    _emit_audit(
        "product.coupon.applied",
        # Coupon has no product reference — use a dummy product attribute safely
        type("_Stub", (), {"id": coupon.id, "slug": coupon.code})(),  # type: ignore[call-arg]
        actor=user,
        request=request,
        code=coupon.code,
        discount=str(discount),
    )

    return {
        "coupon_id": str(coupon.id),
        "code": coupon.code,
        "discount_type": coupon.discount_type,
        "discount_amount": discount,
    }


@transaction.atomic
def redeem_coupon(*, coupon: "Coupon", user: Any) -> None:
    """
    Atomically increment usage_count on checkout commit.
    Called only from the order service after payment confirmation.
    """
    Coupon.objects.filter(pk=coupon.pk).update(usage_count=F("usage_count") + 1)
    logger.info("Coupon %s redeemed by user %s", coupon.code, getattr(user, "id", "?"))


# ─────────────────────────────────────────────────────────────────────────────
# COUPON — Read-only validation (no user, no DB mutation)
# ─────────────────────────────────────────────────────────────────────────────

def validate_coupon(*, code: str, order_subtotal: Decimal) -> dict:
    """
    Stateless coupon validation — returns validity and computed discount amount.

    Unlike validate_and_apply_coupon, this function:
      - Requires no user object (safe for anonymous previews and test fixtures)
      - Does NOT emit an audit event (no DB write at all)
      - Is NOT wrapped in transaction.atomic (read-only, zero side effects)

    Returns:
        {
            "valid": bool,
            "code": str,
            "discount_type": str | None,
            "discount_amount": Decimal,
            "reason": str | None,   # Populated when valid=False
        }
    """
    coupon = get_coupon_by_code(code)

    if not coupon:
        return {"valid": False, "code": code, "discount_type": None, "discount_amount": Decimal("0.00"), "reason": "Coupon not found."}

    if not coupon.is_valid():
        return {"valid": False, "code": code, "discount_type": coupon.discount_type, "discount_amount": Decimal("0.00"), "reason": "Coupon is expired or has reached its usage limit."}

    minimum_order = getattr(coupon, "minimum_order", Decimal("0.00")) or Decimal("0.00")
    if order_subtotal < minimum_order:
        return {
            "valid": False,
            "code": code,
            "discount_type": coupon.discount_type,
            "discount_amount": Decimal("0.00"),
            "reason": f"Minimum order amount is {minimum_order} to use this coupon.",
        }

    if coupon.discount_type == "percentage":
        discount = (coupon.discount_value / 100) * order_subtotal
        max_discount = getattr(coupon, "maximum_discount", None)
        if max_discount:
            discount = min(discount, max_discount)
    else:
        discount = min(coupon.discount_value, order_subtotal)

    return {
        "valid": True,
        "coupon_id": str(coupon.id),
        "code": coupon.code,
        "discount_type": coupon.discount_type,
        "discount_amount": discount,
        "reason": None,
    }


# ─────────────────────────────────────────────────────────────────────────────
# DRAFT SESSIONS
# ─────────────────────────────────────────────────────────────────────────────

@transaction.atomic
def create_draft_session(
    *,
    vendor: Any,
    draft_key: Any = None,
    idempotency_key: Any = None,
    payload: dict,
    current_step: int = 1,
) -> ProductDraftSession:
    """
    Create a new product draft session for the vendor.
    """
    import uuid
    from django.utils.timezone import now

    if idempotency_key:
        existing = ProductDraftSession.objects.filter(
            vendor=vendor,
            idempotency_key=idempotency_key,
        ).first()
        if existing:
            return existing

    if draft_key:
        existing_by_key = ProductDraftSession.objects.filter(draft_key=draft_key).first()
        if existing_by_key:
            if existing_by_key.vendor == vendor:
                existing_by_key.payload = payload
                existing_by_key.current_step = current_step
                existing_by_key.status = ProductDraftStatus.ACTIVE
                existing_by_key.idempotency_key = idempotency_key
                existing_by_key.last_synced_at = now()
                existing_by_key.save()
                return existing_by_key
            else:
                raise ValueError("Draft session key already exists for another vendor.")
    else:
        draft_key = uuid.uuid4()

    draft = ProductDraftSession.objects.create(
        vendor=vendor,
        draft_key=draft_key,
        idempotency_key=idempotency_key,
        payload=payload,
        current_step=current_step,
        status=ProductDraftStatus.ACTIVE,
        last_synced_at=now(),
    )
    return draft


@transaction.atomic
def update_draft_session(
    *,
    draft_session: ProductDraftSession,
    payload: dict,
    current_step: int | None = None,
    idempotency_key: Any = None,
) -> ProductDraftSession:
    """
    Update a draft session with payload and step changes.
    Applies row locking (select_for_update) to prevent collisions.
    """
    from django.utils.timezone import now

    # Apply row-level lock
    draft = ProductDraftSession.objects.select_for_update().get(pk=draft_session.pk)

    if draft.status != ProductDraftStatus.ACTIVE:
        raise ValueError("Cannot update a draft session that is not active.")

    draft.payload = payload
    if current_step is not None:
        draft.current_step = current_step
    if idempotency_key:
        draft.idempotency_key = idempotency_key

    draft.last_synced_at = now()
    draft.save()
    return draft


@transaction.atomic
def discard_draft_session(*, draft_session: ProductDraftSession) -> ProductDraftSession:
    """
    Mark a draft session as discarded (soft delete).
    """
    draft = ProductDraftSession.objects.select_for_update().get(pk=draft_session.pk)
    draft.status = ProductDraftStatus.DISCARDED
    draft.save(update_fields=["status", "updated_at"])
    draft.soft_delete()
    return draft


@transaction.atomic
def commit_draft_session(
    *,
    draft_session: ProductDraftSession,
    request: Any = None,
) -> Product:
    """
    Validate the draft session payload using ProductWriteFullSerializer,
    and create or update the canonical Product.
    """
    from rest_framework.exceptions import ValidationError
    from apps.product.serializers.product_serializers import ProductWriteFullSerializer

    draft = ProductDraftSession.objects.select_for_update().get(pk=draft_session.pk)
    if draft.status != ProductDraftStatus.ACTIVE:
        raise ValueError("Cannot commit a draft session that is not active.")

    # Validate payload
    serializer = ProductWriteFullSerializer(data=draft.payload)
    if not serializer.is_valid():
        raise ValidationError(serializer.errors)

    validated_data = serializer.validated_data

    # Decide whether to create or update product
    product = draft.linked_product
    if product:
        product = update_product(
            product=product,
            validated_data=validated_data,
            actor=draft.vendor.user if hasattr(draft.vendor, "user") else None,
            request=request,
        )
    else:
        product = create_product(
            vendor=draft.vendor,
            validated_data=validated_data,
            idempotency_key=draft.idempotency_key or str(draft.draft_key),
            request=request,
        )
        draft.linked_product = product

    draft.status = ProductDraftStatus.COMMITTED
    draft.save(update_fields=["status", "linked_product", "updated_at"])
    return product

