"""Admin Backend domain audit helper — Wave B16."""
from __future__ import annotations


def log_admin_action(
    *, actor, action_description: str, resource_type: str = "",
    resource_id: str = "", old_values: dict | None = None,
    new_values: dict | None = None, request=None
) -> None:
    """Record a generic admin action.

    Args:
        actor: The staff/admin user.
        action_description: Human-readable description of the action.
        resource_type: Model class name being affected.
        resource_id: Resource PK.
        old_values: State before the action.
        new_values: State after the action.
        request: Django HttpRequest.
    """
    from apps.audit_logs.services.audit import AuditService
    from apps.audit_logs.models import EventType, EventCategory

    AuditService.log(
        event_type=EventType.ADMIN_ACTION,
        event_category=EventCategory.ADMIN,
        action=action_description,
        actor=actor,
        actor_role="admin",
        resource_type=resource_type,
        resource_id=resource_id,
        request=request,
        old_values=old_values,
        new_values=new_values,
        is_compliance=True,
        retention_days=2555,
    )


def log_bulk_export(*, actor, resource_type: str, count: int, request=None) -> None:
    """Record an admin bulk data export.

    Args:
        actor: The admin exporting data.
        resource_type: Model type exported (e.g., 'Order', 'User').
        count: Number of records exported.
        request: Django HttpRequest.
    """
    from apps.audit_logs.services.audit import AuditService
    from apps.audit_logs.models import EventType, EventCategory

    AuditService.log(
        event_type=EventType.ADMIN_BULK_EXPORT,
        event_category=EventCategory.ADMIN,
        action=f"Bulk export: {count} {resource_type} records exported",
        actor=actor,
        actor_role="admin",
        resource_type=resource_type,
        request=request,
        severity="warning",
        new_values={"count": count, "resource_type": resource_type},
        is_compliance=True,
        retention_days=2555,
    )


def log_bulk_delete(*, actor, resource_type: str, count: int, request=None) -> None:
    """Record an admin bulk deletion.

    Args:
        actor: The admin deleting records.
        resource_type: Model type deleted.
        count: Number of records deleted.
        request: Django HttpRequest.
    """
    from apps.audit_logs.services.audit import AuditService
    from apps.audit_logs.models import EventType, EventCategory

    AuditService.log(
        event_type=EventType.ADMIN_BULK_DELETE,
        event_category=EventCategory.ADMIN,
        action=f"Bulk delete: {count} {resource_type} records deleted",
        actor=actor,
        actor_role="admin",
        resource_type=resource_type,
        request=request,
        severity="critical",
        new_values={"count": count, "resource_type": resource_type},
        is_compliance=True,
        retention_days=2555,
    )


def log_permission_changed(
    *, actor, target_user_id: str, permission: str, granted: bool, request=None
) -> None:
    """Record a user permission or role change made by admin.

    Args:
        actor: The admin making the change.
        target_user_id: UnifiedUser PK of the target.
        permission: Permission or role name.
        granted: True if granted, False if revoked.
        request: Django HttpRequest.
    """
    from apps.audit_logs.services.audit import AuditService
    from apps.audit_logs.models import EventType, EventCategory

    AuditService.log(
        event_type=EventType.ADMIN_ACTION,
        event_category=EventCategory.AUTHORIZATION,
        action=f"Permission {'granted' if granted else 'revoked'}: {permission} for user={target_user_id}",
        actor=actor,
        actor_role="admin",
        resource_type="UnifiedUser",
        resource_id=target_user_id,
        request=request,
        severity="critical",
        new_values={"permission": permission, "granted": granted},
        is_compliance=True,
        retention_days=2555,
    )
