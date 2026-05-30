# apps/providers/tasks.py
"""
Provider Registry — Celery Tasks (Phase 10).

Tasks
─────
  check_email_provider_health   Periodic probe of all configured email providers.

Celery Beat Schedule (add to CELERY_BEAT_SCHEDULE in settings):
    "check_email_provider_health": {
        "task": "check_email_provider_health",
        "schedule": crontab(minute="*/15"),   # Every 15 minutes
        "options": {"ignore_result": True},
    },

Design
──────
✅ Probes all three providers in order: Brevo → Mailgun → Zoho.
✅ Dispatches CircuitBreaker failure events on unhealthy probes.
✅ Records structured audit log for each health check result.
✅ Sends superuser alert (via existing circuit breaker alert) on OPEN.
✅ All provider HTTP calls use stdlib urllib (no extra dependencies).
✅ Task is idempotent — safe to retry if the Celery worker dies mid-run.
✅ Never blocks on provider failures — each probe is isolated with try/except.
"""

from __future__ import annotations

import logging

from celery import shared_task

logger = logging.getLogger(__name__)


# ── Provider singleton registry ──────────────────────────────────────────────

def _load_email_providers():
    """
    Lazily import provider singletons.

    Deferred import prevents circular imports at module load time.
    Returns a list of (provider_slug, SMTPProviderContract instance) tuples.
    """
    from apps.providers.SMTP.brevo_provider   import BREVO
    from apps.providers.SMTP.mailgun_provider import MAILGUN
    from apps.providers.SMTP.zoho_provider    import ZOHO

    return [
        ("brevo",   BREVO),
        ("mailgun", MAILGUN),
        ("zoho",    ZOHO),
    ]


# ═══════════════════════════════════════════════════════════════════════════
# PROVIDER HEALTH CHECK — Celery Beat periodic task
# ═══════════════════════════════════════════════════════════════════════════

@shared_task(
    name="check_email_provider_health",
    bind=True,
    max_retries=1,
    default_retry_delay=30,
    ignore_result=True,
)
def check_email_provider_health(self) -> None:
    """
    Probe all email provider APIs and record health status.

    Called by Celery Beat every 15 minutes (configure in CELERY_BEAT_SCHEDULE).

    For each provider:
      1. Call ``provider.health_check()`` — HTTP ping, no real email sent.
      2. If healthy: reset circuit breaker failure counter.
      3. If unhealthy: record circuit breaker failure; alert if threshold reached.
      4. Dispatch audit log event (INFO on healthy, ERROR on failure).

    Circuit Breaker Integration
    ───────────────────────────
    The circuit breaker is keyed by ``email:{slug}`` so it does not conflict
    with SMS/KYC circuits.  On 5 consecutive failures, the circuit opens and
    a superuser alert email is dispatched (de-duplicated, 1 per hour).
    """
    from apps.providers.circuit_breaker import CircuitBreaker

    providers = _load_email_providers()
    results = []

    for slug, provider in providers:
        try:
            result = provider.health_check()
        except Exception as exc:
            # Catch any unhandled exception from the health check method itself
            result_err = {
                "slug": slug,
                "healthy": False,
                "latency_ms": 0,
                "message": f"health_check() raised unexpectedly: {exc}",
                "error": str(exc),
            }
            logger.error(
                "check_email_provider_health: unhandled exception for %s: %s",
                slug, exc,
            )
            results.append(result_err)
            continue

        if result.healthy:
            logger.info(
                "✅ Email provider healthy: %s | latency=%.1fms | %s",
                slug, result.latency_ms, result.message,
            )
            # Reset circuit breaker failure counter
            try:
                cb = CircuitBreaker(f"email:{slug}")
                cb.record_success()
            except Exception as cb_exc:
                logger.debug("CircuitBreaker reset failed for %s: %s", slug, cb_exc)
        else:
            logger.warning(
                "❌ Email provider UNHEALTHY: %s | latency=%.1fms | error=%s",
                slug, result.latency_ms, result.error,
            )
            # Record failure — circuit breaker will open if threshold reached
            try:
                from apps.providers.circuit_breaker import CircuitBreaker
                cb = CircuitBreaker(f"email:{slug}")
                cb.record_failure(Exception(result.error or result.message))
            except Exception as cb_exc:
                logger.error(
                    "CircuitBreaker record_failure failed for %s: %s", slug, cb_exc
                )

        results.append({
            "slug": slug,
            "healthy": result.healthy,
            "latency_ms": result.latency_ms,
            "message": result.message,
            "error": result.error,
        })

    # ── Audit log ──────────────────────────────────────────────────────────
    _dispatch_health_check_audit(results)

    # ── Summary ────────────────────────────────────────────────────────────
    healthy_count   = sum(1 for r in results if r["healthy"])
    unhealthy_count = len(results) - healthy_count
    logger.info(
        "check_email_provider_health: %d/%d providers healthy",
        healthy_count, len(results),
    )

    if unhealthy_count > 0:
        logger.warning(
            "check_email_provider_health: %d provider(s) UNHEALTHY — "
            "check circuit breaker status in Django Admin → Providers.",
            unhealthy_count,
        )


def _dispatch_health_check_audit(results: list[dict]) -> None:
    """
    Dispatch a single audit log event summarising all provider health check results.

    Never raises — audit failure must never fail the health check task.
    """
    try:
        from apps.audit_logs.services.audit import AuditService

        healthy_slugs   = [r["slug"] for r in results if r["healthy"]]
        unhealthy_slugs = [r["slug"] for r in results if not r["healthy"]]

        action = (
            f"Email provider health check: "
            f"{len(healthy_slugs)} healthy ({', '.join(healthy_slugs) or 'none'}), "
            f"{len(unhealthy_slugs)} unhealthy ({', '.join(unhealthy_slugs) or 'none'})"
        )

        AuditService.log(
            event_type="SYSTEM_HEALTH_CHECK",
            event_category="system",
            action=action,
            metadata={
                "provider_results": results,
                "healthy_count":   len(healthy_slugs),
                "unhealthy_count": len(unhealthy_slugs),
            },
            is_compliance=False,
        )
    except Exception as exc:
        logger.debug("_dispatch_health_check_audit: failed (non-fatal): %s", exc)


__all__ = [
    "check_email_provider_health",
]
