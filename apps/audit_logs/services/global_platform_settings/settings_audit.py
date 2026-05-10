"""Global Platform Settings domain audit helper — Wave B17."""
from __future__ import annotations


def log_setting_changed(
    *, actor, setting_key: str, old_value=None, new_value=None, request=None
) -> None:
    """Record a platform-wide configuration setting change.

    Args:
        actor: The admin making the change.
        setting_key: The setting identifier / key path.
        old_value: Previous value (will be JSON-serialized).
        new_value: New value (will be JSON-serialized).
        request: Django HttpRequest.
    """
    from apps.audit_logs.services.audit import AuditService
    from apps.audit_logs.models import EventType, EventCategory

    AuditService.log(
        event_type=EventType.SETTINGS_CHANGED,
        event_category=EventCategory.SETTINGS,
        action=f"Platform setting changed: key={setting_key}",
        actor=actor,
        actor_role="admin",
        resource_type="PlatformSetting",
        resource_id=setting_key,
        request=request,
        severity="warning",
        old_values={"value": old_value},
        new_values={"value": new_value},
        is_compliance=True,
        retention_days=2555,
    )


def log_commission_policy_changed(
    *, actor, old_rate: str, new_rate: str, scope: str = "global", request=None
) -> None:
    """Record a change to the global commission policy.

    Args:
        actor: The admin/finance team member.
        old_rate: Previous commission rate (percentage string).
        new_rate: New commission rate.
        scope: 'global', 'category', or 'vendor-specific'.
        request: Django HttpRequest.
    """
    from apps.audit_logs.services.audit import AuditService
    from apps.audit_logs.models import EventType, EventCategory

    AuditService.log(
        event_type=EventType.SETTINGS_CHANGED,
        event_category=EventCategory.SETTINGS,
        action=f"Commission policy changed: {old_rate}% → {new_rate}% scope={scope}",
        actor=actor,
        actor_role="admin",
        resource_type="CommissionPolicy",
        resource_id=scope,
        request=request,
        severity="critical",
        old_values={"rate": old_rate, "scope": scope},
        new_values={"rate": new_rate, "scope": scope},
        is_compliance=True,
        retention_days=2555,
    )


def log_feature_flag_toggled(*, actor, flag: str, enabled: bool, request=None) -> None:
    """Record a feature flag being toggled.

    Args:
        actor: The admin toggling the flag.
        flag: Feature flag name.
        enabled: New state (True = on, False = off).
        request: Django HttpRequest.
    """
    from apps.audit_logs.services.audit import AuditService
    from apps.audit_logs.models import EventType, EventCategory

    AuditService.log(
        event_type=EventType.SETTINGS_CHANGED,
        event_category=EventCategory.SETTINGS,
        action=f"Feature flag {'enabled' if enabled else 'disabled'}: {flag}",
        actor=actor,
        actor_role="admin",
        resource_type="FeatureFlag",
        resource_id=flag,
        request=request,
        new_values={"flag": flag, "enabled": enabled},
        is_compliance=True,
        retention_days=1825,
    )


def log_maintenance_mode_toggled(*, actor, enabled: bool, reason: str = "", request=None) -> None:
    """Record maintenance mode being enabled or disabled.

    Args:
        actor: The admin toggling maintenance mode.
        enabled: True if entering maintenance, False if leaving.
        reason: Reason for maintenance window.
        request: Django HttpRequest.
    """
    from apps.audit_logs.services.audit import AuditService
    from apps.audit_logs.models import EventType, EventCategory

    AuditService.log(
        event_type=EventType.SETTINGS_CHANGED,
        event_category=EventCategory.SETTINGS,
        action=f"Maintenance mode {'ENABLED' if enabled else 'DISABLED'}: {reason}",
        actor=actor,
        actor_role="admin",
        resource_type="MaintenanceMode",
        resource_id="global",
        request=request,
        severity="critical",
        new_values={"enabled": enabled, "reason": reason},
        is_compliance=True,
        retention_days=1825,
    )
