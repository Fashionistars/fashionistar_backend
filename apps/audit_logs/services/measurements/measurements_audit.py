"""AI Measurements domain audit helper — Wave B12."""
from __future__ import annotations


def log_measurement_created(*, actor, measurement_id: str, source: str = "ai", request=None) -> None:
    """Record creation of a body measurement set.

    Args:
        actor: The client user.
        measurement_id: MeasurementSet PK.
        source: Measurement source ('ai', 'manual', 'device').
        request: Django HttpRequest.
    """
    from apps.audit_logs.services.audit import AuditService
    from apps.audit_logs.models import EventType, EventCategory

    AuditService.log(
        event_type=EventType.MEASUREMENT_CREATED,
        event_category=EventCategory.MEASUREMENT,
        action=f"Measurement set created: id={measurement_id} source={source}",
        actor=actor,
        actor_role="client",
        resource_type="MeasurementSet",
        resource_id=measurement_id,
        request=request,
        new_values={"source": source},
        is_compliance=True,
        retention_days=1825,
    )


def log_measurement_updated(
    *, actor, measurement_id: str,
    old_values: dict | None = None, new_values: dict | None = None, request=None
) -> None:
    """Record an update to a measurement set.

    Args:
        actor: The client or admin.
        measurement_id: MeasurementSet PK.
        old_values: Previous field snapshot.
        new_values: Updated field snapshot.
        request: Django HttpRequest.
    """
    from apps.audit_logs.services.audit import AuditService
    from apps.audit_logs.models import EventType, EventCategory

    AuditService.log(
        event_type=EventType.MEASUREMENT_UPDATED,
        event_category=EventCategory.MEASUREMENT,
        action=f"Measurement set updated: id={measurement_id}",
        actor=actor,
        resource_type="MeasurementSet",
        resource_id=measurement_id,
        request=request,
        old_values=old_values,
        new_values=new_values,
    )


def log_ai_scan_completed(
    *, actor, scan_id: str, confidence: float | None = None, request=None
) -> None:
    """Record a completed AI body scan.

    Args:
        actor: The client user.
        scan_id: AIScan PK or session ID.
        confidence: Confidence score (0.0-1.0).
        request: Django HttpRequest.
    """
    from apps.audit_logs.services.audit import AuditService
    from apps.audit_logs.models import EventType, EventCategory

    AuditService.log(
        event_type=EventType.MEASUREMENT_CREATED,
        event_category=EventCategory.MEASUREMENT,
        action=f"AI scan completed: scan={scan_id} confidence={confidence}",
        actor=actor,
        resource_type="AIScan",
        resource_id=scan_id,
        request=request,
        new_values={"confidence": confidence},
    )
