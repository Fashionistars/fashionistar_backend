"""Catalog & Products domain audit helper — Wave B7."""
from __future__ import annotations


def log_product_created(*, actor, product_id: str, name: str = "", request=None) -> None:
    """Record a new product creation.

    Args:
        actor: The vendor or admin creating the product.
        product_id: Product PK as string.
        name: Product name for context.
        request: Django HttpRequest.
    """
    from apps.audit_logs.services.audit import AuditService
    from apps.audit_logs.models import EventType, EventCategory

    AuditService.log(
        event_type=EventType.PRODUCT_CREATED,
        event_category=EventCategory.CATALOG,
        action=f"Product created: '{name}' id={product_id}",
        actor=actor,
        actor_role=getattr(actor, "user_type", None),
        resource_type="Product",
        resource_id=product_id,
        request=request,
        new_values={"name": name},
        is_compliance=True,
        retention_days=1825,  # 5 years
    )


def log_product_updated(
    *, actor, product_id: str, name: str = "",
    old_values: dict | None = None, new_values: dict | None = None, request=None
) -> None:
    """Record a product update.

    Args:
        actor: Vendor or admin performing the update.
        product_id: Product PK.
        name: Product name.
        old_values: Previous field values.
        new_values: Updated field values.
        request: Django HttpRequest.
    """
    from apps.audit_logs.services.audit import AuditService
    from apps.audit_logs.models import EventType, EventCategory

    AuditService.log(
        event_type=EventType.PRODUCT_UPDATED,
        event_category=EventCategory.CATALOG,
        action=f"Product updated: '{name}' id={product_id}",
        actor=actor,
        actor_role=getattr(actor, "user_type", None),
        resource_type="Product",
        resource_id=product_id,
        request=request,
        old_values=old_values,
        new_values=new_values,
    )


def log_product_published(*, actor, product_id: str, name: str = "", request=None) -> None:
    """Record a product going live.

    Args:
        actor: Vendor or admin publishing.
        product_id: Product PK.
        name: Product name.
        request: Django HttpRequest.
    """
    from apps.audit_logs.services.audit import AuditService
    from apps.audit_logs.models import EventType, EventCategory

    AuditService.log(
        event_type=EventType.PRODUCT_PUBLISHED,
        event_category=EventCategory.CATALOG,
        action=f"Product published: '{name}' id={product_id}",
        actor=actor,
        resource_type="Product",
        resource_id=product_id,
        request=request,
        is_compliance=True,
    )


def log_product_deleted(*, actor, product_id: str, name: str = "", request=None) -> None:
    """Record a product deletion (soft or hard).

    Args:
        actor: Vendor or admin deleting.
        product_id: Product PK.
        name: Product name.
        request: Django HttpRequest.
    """
    from apps.audit_logs.services.audit import AuditService
    from apps.audit_logs.models import EventType, EventCategory

    AuditService.log(
        event_type=EventType.PRODUCT_DELETED,
        event_category=EventCategory.CATALOG,
        action=f"Product deleted: '{name}' id={product_id}",
        actor=actor,
        actor_role=getattr(actor, "user_type", None),
        resource_type="Product",
        resource_id=product_id,
        request=request,
        severity="warning",
        is_compliance=True,
    )


def log_review_posted(
    *, actor, product_id: str, review_id: str, rating: int, request=None
) -> None:
    """Record a product review being posted.

    Args:
        actor: Client posting the review.
        product_id: Reviewed product PK.
        review_id: ProductReview PK.
        rating: Star rating (1-5).
        request: Django HttpRequest.
    """
    from apps.audit_logs.services.audit import AuditService
    from apps.audit_logs.models import EventType, EventCategory

    AuditService.log(
        event_type=EventType.REVIEW_POSTED,
        event_category=EventCategory.CATALOG,
        action=f"Review posted: rating={rating}★ on product={product_id}",
        actor=actor,
        resource_type="ProductReview",
        resource_id=review_id,
        request=request,
        new_values={"product_id": product_id, "rating": rating},
    )


def log_cloudinary_webhook(*, asset_id: str, event: str, metadata: dict | None = None) -> None:
    """Record an incoming Cloudinary media webhook event.

    Args:
        asset_id: Cloudinary public_id or asset_id.
        event: Cloudinary notification type.
        metadata: Webhook payload summary.
    """
    from apps.audit_logs.services.audit import AuditService
    from apps.audit_logs.models import EventType, EventCategory

    AuditService.log(
        event_type=EventType.CLOUDINARY_WEBHOOK,
        event_category=EventCategory.CATALOG,
        action=f"Cloudinary webhook: event={event} asset={asset_id}",
        resource_type="CloudinaryAsset",
        resource_id=asset_id,
        metadata=metadata,
    )
