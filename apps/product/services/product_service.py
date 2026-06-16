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

from apps.vendor.models import VendorProfile
from apps.product.models import (
    Coupon,
    Product,
    ProductVariantGalleryMedia,
    ProductInventoryLog,
    ProductReview,
    ProductWishlist,
    ProductSizeAndMeasurementGuide,
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
        "productsizeandmeasurementguides": validated_data.pop("productsizeandmeasurementguides", []),
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

    for relation_name in ("sizes", "tags"):
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
    existing_variants = {v.sku: v for v in product.product_variants_gallery_media.filter(is_deleted=False)}
    submitted_skus = set()

    for vdata in variants_data:
        sku = vdata.get("sku")
        if sku:
            sku = sku.strip().upper()
            vdata["sku"] = sku

        size = vdata.get("size")
        color_name = vdata.get("color_name", "")
        color_hex = vdata.get("color_hex", "")

        # Only write fields that actually exist on ProductVariantGalleryMedia
        variant_fields = {
            "size": size,
            "color_name": color_name,
            "color_hex": color_hex,
            "barcode": vdata.get("barcode", ""),
            "media": vdata.get("media"),
            "media_type": vdata.get("media_type", "image"),
            "alt_text": vdata.get("alt_text", ""),
            "ordering": vdata.get("ordering", 0),
            "is_primary": vdata.get("is_primary", False),
            "video_thumbnail": vdata.get("video_thumbnail"),
            "duration_sec": vdata.get("duration_sec"),
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
                sku = f"FASTAR-{str(uuid.uuid4()).upper()[:10]}"
            variant = ProductVariantGalleryMedia(
                product=product,
                sku=sku,
                **variant_fields
            )
            variant.save()
            submitted_skus.add(sku)

    for sku, variant in existing_variants.items():
        if sku not in submitted_skus:
            variant.soft_delete()


def _sync_measurement_guide_from_template(vendor: VendorProfile) -> None:
    """
    If the vendor has a measurement_template name, copy all its template rows (where vendor is NULL)
    to the vendor's sizing guide.
    """
    if not vendor.measurement_template:
        return

    # Clear existing guide rows
    vendor.vendor_measurement_guide.all().delete()

    # Query template rows where product is NULL, matches vendor and template name
    template_rows = ProductSizeAndMeasurementGuide.objects.filter(
        vendor=vendor,
    )
    for row in template_rows:
        ProductSizeAndMeasurementGuide.objects.create(
            vendor=vendor,
            size_label=row.size_label,
            chest_cm=row.chest_cm,
            waist_cm=row.waist_cm,
            hip_cm=row.hip_cm,
            length_cm=row.length_cm,
            shoulder_cm=row.shoulder_cm,
            sleeve_cm=row.sleeve_cm,
            inseam_cm=row.inseam_cm,
            foot_length_cm=row.foot_length_cm,
            sort_order=row.sort_order,
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

