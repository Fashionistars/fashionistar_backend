"""Vendor domain audit helper — Wave B8."""
from __future__ import annotations


def log_vendor_registered(*, actor, vendor_id: str, request=None) -> None:
    """Record a vendor registration.

    Args:
        actor: The user registering as a vendor.
        vendor_id: Vendor/VendorProfile PK.
        request: Django HttpRequest.
    """
    from apps.audit_logs.services.audit import AuditService
    from apps.audit_logs.models import EventType, EventCategory

    AuditService.log(
        event_type=EventType.VENDOR_REGISTERED,
        event_category=EventCategory.VENDOR,
        action=f"Vendor registered: {getattr(actor, 'email', str(actor))}",
        actor=actor,
        actor_role="vendor",
        resource_type="VendorProfile",
        resource_id=vendor_id,
        request=request,
        is_compliance=True,
        retention_days=2555,
    )


def log_vendor_kyc_gate_passed(*, actor, vendor_id: str, request=None) -> None:
    """Record a vendor passing the KYC gate for payouts.

    Args:
        actor: The vendor user.
        vendor_id: VendorProfile PK.
        request: Django HttpRequest.
    """
    from apps.audit_logs.services.audit import AuditService
    from apps.audit_logs.models import EventType, EventCategory

    AuditService.log(
        event_type=EventType.VENDOR_KYC_GATE_PASSED,
        event_category=EventCategory.VENDOR,
        action=f"Vendor KYC gate passed for payouts: {getattr(actor, 'email', str(actor))}",
        actor=actor,
        actor_role="vendor",
        resource_type="VendorProfile",
        resource_id=vendor_id,
        request=request,
        is_compliance=True,
        retention_days=2555,
    )


def log_vendor_commission_changed(
    *, actor, vendor_id: str, old_rate: str, new_rate: str, request=None
) -> None:
    """Record a vendor commission rate change.

    Args:
        actor: Admin making the change.
        vendor_id: VendorProfile PK.
        old_rate: Previous commission rate.
        new_rate: New commission rate.
        request: Django HttpRequest.
    """
    from apps.audit_logs.services.audit import AuditService
    from apps.audit_logs.models import EventType, EventCategory

    AuditService.log(
        event_type=EventType.VENDOR_COMMISSION_CHANGED,
        event_category=EventCategory.VENDOR,
        action=f"Vendor commission changed: vendor={vendor_id} {old_rate}% → {new_rate}%",
        actor=actor,
        actor_role="admin",
        resource_type="VendorProfile",
        resource_id=vendor_id,
        request=request,
        old_values={"commission_rate": old_rate},
        new_values={"commission_rate": new_rate},
        severity="warning",
        is_compliance=True,
        retention_days=2555,
    )


def log_vendor_suspended(*, actor, vendor_id: str, reason: str = "", request=None) -> None:
    """Record a vendor account suspension.

    Args:
        actor: Admin performing the suspension.
        vendor_id: VendorProfile PK.
        reason: Reason for suspension.
        request: Django HttpRequest.
    """
    from apps.audit_logs.services.audit import AuditService
    from apps.audit_logs.models import EventType, EventCategory

    AuditService.log(
        event_type=EventType.VENDOR_SUSPENDED,
        event_category=EventCategory.VENDOR,
        action=f"Vendor suspended: vendor={vendor_id} reason={reason[:200]}",
        actor=actor,
        actor_role="admin",
        resource_type="VendorProfile",
        resource_id=vendor_id,
        request=request,
        severity="critical",
        new_values={"reason": reason},
        is_compliance=True,
        retention_days=2555,
    )


def log_vendor_provisioned(
    *, actor, vendor_profile, store_name: str = "", collections_count: int = 0, request=None
) -> None:
    """Record a vendor's initial provisioning (first-time setup completed).

    Args:
        actor: The vendor user completing setup.
        vendor_profile: VendorProfile instance.
        store_name: Store name chosen during setup.
        collections_count: Number of product collections selected.
        request: Django HttpRequest (optional).
    """
    from apps.audit_logs.services.audit import AuditService
    from apps.audit_logs.models import EventType, EventCategory

    AuditService.log(
        event_type=EventType.VENDOR_PROVISIONED,
        event_category=EventCategory.VENDOR,
        action=(
            f"Vendor provisioned: {getattr(actor, 'email', str(actor))} "
            f"— store='{store_name}' collections={collections_count}"
        ),
        actor=actor,
        actor_role="vendor",
        resource_type="VendorProfile",
        resource_id=str(getattr(vendor_profile, "pk", "")),
        request=request,
        new_values={"store_name": store_name, "collections_count": collections_count},
        is_compliance=True,
        retention_days=2555,
    )


def log_vendor_profile_updated(
    *, actor, vendor_profile, new_values: dict | None = None, request=None
) -> None:
    """Record a vendor profile update.

    Args:
        actor: The vendor or admin who made the update.
        vendor_profile: VendorProfile instance.
        new_values: Dict of fields that changed.
        request: Django HttpRequest (optional).
    """
    from apps.audit_logs.services.audit import AuditService
    from apps.audit_logs.models import EventType, EventCategory

    AuditService.log(
        event_type=EventType.VENDOR_PROFILE_UPDATED,
        event_category=EventCategory.VENDOR,
        action=f"Vendor profile updated: {getattr(actor, 'email', str(actor))}",
        actor=actor,
        actor_role=getattr(actor, "user_type", "vendor"),
        resource_type="VendorProfile",
        resource_id=str(getattr(vendor_profile, "pk", "")),
        request=request,
        new_values=new_values or {},
        is_compliance=False,
        retention_days=730,  # 2 years
    )

