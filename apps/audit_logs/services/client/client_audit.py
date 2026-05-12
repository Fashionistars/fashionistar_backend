"""Client / Consumer domain audit helper — Wave B9."""
from __future__ import annotations


def log_profile_updated(
    *, actor, resource_id: str,
    old_values: dict | None = None, new_values: dict | None = None, request=None
) -> None:
    """Record a client profile update.

    Args:
        actor: The client user.
        resource_id: ClientProfile PK.
        old_values: Previous field snapshot.
        new_values: Updated field snapshot.
        request: Django HttpRequest.
    """
    from apps.audit_logs.services.audit import AuditService
    from apps.audit_logs.models import EventType, EventCategory

    AuditService.log(
        event_type=EventType.ACCOUNT_UPDATED,
        event_category=EventCategory.CLIENT,
        action=f"Client profile updated: {getattr(actor, 'email', str(actor))}",
        actor=actor,
        actor_role="client",
        resource_type="ClientProfile",
        resource_id=resource_id,
        request=request,
        old_values=old_values,
        new_values=new_values,
    )


def log_avatar_uploaded(*, actor, resource_id: str, public_id: str = "", request=None) -> None:
    """Record a client avatar upload.

    Args:
        actor: The client user.
        resource_id: ClientProfile PK.
        public_id: Cloudinary public_id.
        request: Django HttpRequest.
    """
    from apps.audit_logs.services.audit import AuditService
    from apps.audit_logs.models import EventType, EventCategory

    AuditService.log(
        event_type=EventType.AVATAR_UPLOADED,
        event_category=EventCategory.CLIENT,
        action=f"Avatar uploaded: user={getattr(actor, 'email', str(actor))} public_id={public_id}",
        actor=actor,
        actor_role="client",
        resource_type="ClientProfile",
        resource_id=resource_id,
        request=request,
        new_values={"cloudinary_public_id": public_id},
    )


def log_address_saved(*, actor, address_id: str, is_default: bool = False, request=None) -> None:
    """Record a client delivery address save.

    Args:
        actor: The client.
        address_id: Address PK.
        is_default: Whether marked as default address.
        request: Django HttpRequest.
    """
    from apps.audit_logs.services.audit import AuditService
    from apps.audit_logs.models import EventType, EventCategory

    AuditService.log(
        event_type=EventType.ACCOUNT_UPDATED,
        event_category=EventCategory.CLIENT,
        action=f"Client address saved: id={address_id} default={is_default}",
        actor=actor,
        actor_role="client",
        resource_type="Address",
        resource_id=address_id,
        request=request,
        new_values={"is_default": is_default},
    )


def log_wishlist_updated(
    *, actor, product_id: str, action: str = "added", request=None
) -> None:
    """Record a wishlist add/remove event.

    Args:
        actor: The client.
        product_id: Product PK.
        action: 'added' or 'removed'.
        request: Django HttpRequest.
    """
    from apps.audit_logs.services.audit import AuditService
    from apps.audit_logs.models import EventType, EventCategory

    AuditService.log(
        event_type=EventType.ACCOUNT_UPDATED,
        event_category=EventCategory.CLIENT,
        action=f"Wishlist {action}: product={product_id}",
        actor=actor,
        actor_role="client",
        resource_type="Wishlist",
        resource_id=product_id,
        request=request,
        new_values={"action": action, "product_id": product_id},
    )


def log_account_deactivated(*, actor, resource_id: str, reason: str = "", request=None) -> None:
    """Record a client account deactivation (soft-delete).

    Args:
        actor: Admin or the user themselves.
        resource_id: UnifiedUser PK.
        reason: Deactivation reason.
        request: Django HttpRequest.
    """
    from apps.audit_logs.services.audit import AuditService
    from apps.audit_logs.models import EventType, EventCategory

    AuditService.log(
        event_type=EventType.ACCOUNT_SOFT_DELETED,
        event_category=EventCategory.CLIENT,
        action=f"Client account deactivated: user={resource_id} reason={reason[:200]}",
        actor=actor,
        resource_type="UnifiedUser",
        resource_id=resource_id,
        request=request,
        severity="warning",
        new_values={"reason": reason},
        is_compliance=True,
        retention_days=2555,
    )
