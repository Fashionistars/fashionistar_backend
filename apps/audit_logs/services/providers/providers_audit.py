"""Payment Providers domain audit helper — Wave B15."""
from __future__ import annotations


def log_provider_webhook_received(
    *, provider: str, event: str, reference: str = "", metadata: dict | None = None
) -> None:
    """Record an incoming webhook from a payment provider.

    Args:
        provider: Provider name (paystack, flutterwave, stripe, etc.).
        event: Webhook event type from the provider.
        reference: Payment reference extracted from the payload.
        metadata: Sanitized payload summary for audit context.
    """
    from apps.audit_logs.services.audit import AuditService
    from apps.audit_logs.models import EventType, EventCategory

    AuditService.log(
        event_type=EventType.PROVIDER_WEBHOOK_RECEIVED,
        event_category=EventCategory.PROVIDER,
        action=f"Provider webhook: provider={provider} event={event} ref={reference}",
        resource_type="PaymentProviderLog",
        resource_id=reference,
        metadata=metadata,
        new_values={"provider": provider, "event": event, "reference": reference},
        is_compliance=True,
        retention_days=-1,
    )


def log_provider_webhook_failed(
    *, provider: str, event: str, error: str, reference: str = ""
) -> None:
    """Record a provider webhook processing failure.

    Args:
        provider: Provider name.
        event: Webhook event type.
        error: Error details.
        reference: Payment reference if available.
    """
    from apps.audit_logs.services.audit import AuditService
    from apps.audit_logs.models import EventType, EventCategory

    AuditService.log(
        event_type=EventType.PROVIDER_WEBHOOK_FAILED,
        event_category=EventCategory.PROVIDER,
        action=f"Provider webhook FAILED: provider={provider} event={event} error={error[:200]}",
        resource_type="PaymentProviderLog",
        resource_id=reference,
        severity="error",
        error_message=error,
        new_values={"provider": provider, "event": event},
        is_compliance=True,
        retention_days=-1,
    )


def log_provider_health_check(
    *, provider: str, status: str, latency_ms: int | None = None
) -> None:
    """Record a provider health check result.

    Args:
        provider: Provider name.
        status: 'healthy', 'degraded', or 'down'.
        latency_ms: Round-trip latency in milliseconds.
    """
    from apps.audit_logs.services.audit import AuditService
    from apps.audit_logs.models import EventType, EventCategory

    severity = "info" if status == "healthy" else ("warning" if status == "degraded" else "critical")

    AuditService.log(
        event_type=EventType.PROVIDER_HEALTH_CHECK,
        event_category=EventCategory.PROVIDER,
        action=f"Provider health check: {provider} → {status} latency={latency_ms}ms",
        resource_type="PaymentProvider",
        resource_id=provider,
        severity=severity,
        new_values={"status": status, "latency_ms": latency_ms},
    )


def log_provider_switched(*, actor, from_provider: str, to_provider: str, reason: str = "") -> None:
    """Record a payment provider failover / switch event.

    Args:
        actor: Admin or system triggering the switch.
        from_provider: Previous provider name.
        to_provider: New active provider.
        reason: Reason for the switch (e.g. 'health check failed').
    """
    from apps.audit_logs.services.audit import AuditService
    from apps.audit_logs.models import EventType, EventCategory

    AuditService.log(
        event_type=EventType.PROVIDER_SWITCHED,
        event_category=EventCategory.PROVIDER,
        action=f"Payment provider switched: {from_provider} → {to_provider} reason={reason}",
        actor=actor,
        resource_type="PaymentProvider",
        resource_id=to_provider,
        severity="warning",
        old_values={"provider": from_provider},
        new_values={"provider": to_provider, "reason": reason},
        is_compliance=True,
        retention_days=1825,
    )


def log_provider_config_changed(
    *, provider: str, instance_pk: str, created: bool = False
) -> None:
    """Record a provider config create/update (from post_save signal).

    Every infrastructure-level change to a payment/KYC/email/SMS/Cloudinary
    provider config is a compliance event — retained indefinitely.

    Args:
        provider: Model class name (e.g. 'EmailProviderConfig').
        instance_pk: PK of the provider config instance.
        created: True if this is a new row (INSERT), False for UPDATE.
    """
    from apps.audit_logs.services.audit import AuditService
    from apps.audit_logs.models import EventCategory

    # Use PROVIDER_HEALTH_CHECK as a generic infrastructure event if a dedicated
    # PROVIDER_CONFIG_CHANGED type is not yet declared in EventType.
    # Replace with EventType.PROVIDER_CONFIG_CHANGED once the enum is extended.
    try:
        from apps.audit_logs.models import EventType
        event_type = EventType.PROVIDER_CONFIG_CHANGED
    except AttributeError:
        from apps.audit_logs.models import EventType
        event_type = EventType.PROVIDER_HEALTH_CHECK

    action_verb = "Created" if created else "Updated"
    AuditService.log(
        event_type=event_type,
        event_category=EventCategory.PROVIDER,
        action=f"{action_verb} provider config: {provider} pk={instance_pk}",
        actor=None,
        resource_type=provider,
        resource_id=instance_pk,
        severity="warning",
        new_values={"provider": provider, "created": created},
        is_compliance=True,
        retention_days=-1,  # indefinite — infrastructure changes are permanently audited
    )

