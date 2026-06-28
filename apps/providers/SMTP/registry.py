"""
apps/providers/SMTP/registry.py — Phase F5

SMTP Provider Registry — maps slug → provider singleton.
Used to resolve which provider to use for transactional email delivery.

Usage:
    from apps.providers.SMTP.registry import get_active_provider, SMTP_PROVIDER_REGISTRY

    provider = get_active_provider()
    provider.send_transactional(to="...", subject="...", html_body="...")

Fallback chain (priority order):
    1. Brevo    (priority 1) — EU-compliant, Nigerian deliverability ✅
    2. Mailgun  (priority 2) — high-volume, developer-friendly
    3. Zoho     (priority 3) — Zoho ecosystem teams

The active provider is resolved from the EmailProviderConfig DB model.
If none configured, falls back by priority order.
"""
from __future__ import annotations

import logging


from apps.providers.SMTP.contract import SMTPProviderContract
from apps.providers.SMTP.brevo_provider import BREVO
from apps.providers.SMTP.mailgun_provider import MAILGUN
from apps.providers.SMTP.zoho_provider import ZOHO

logger = logging.getLogger(__name__)


# ── Unified registry (slug → singleton) ──────────────────────────────────────

SMTP_PROVIDER_REGISTRY: dict[str, SMTPProviderContract] = {
    BREVO.slug:   BREVO,
    MAILGUN.slug: MAILGUN,
    ZOHO.slug:    ZOHO,
}

# Priority order for fallback chain
_PROVIDER_PRIORITY: list[str] = [BREVO.slug, MAILGUN.slug, ZOHO.slug]


def get_active_provider() -> SMTPProviderContract:
    """
    Resolve the highest-priority active SMTP provider.

    Resolution order:
    1. Read `EmailProviderConfig.email_backend` from the DB (admin-managed).
    2. Map the backend path to a provider slug.
    3. Return the corresponding singleton from SMTP_PROVIDER_REGISTRY.
    4. If the DB lookup fails or the backend is unknown, fall back to
       the first provider in _PROVIDER_PRIORITY order.

    Returns:
        SMTPProviderContract: Ready-to-use provider singleton.

    Raises:
        RuntimeError: If no provider is registered (should never happen).
    """
    # Attempt DB resolution first
    try:
        from apps.providers.models import EmailProviderConfig  # lazy import to avoid circular
        config = EmailProviderConfig.objects.select_related(None).only("email_backend").first()
        if config and config.email_backend:
            backend_path = config.email_backend
            # Map backend path → slug
            for slug, provider in SMTP_PROVIDER_REGISTRY.items():
                if hasattr(provider, "backend_path") and provider.backend_path == backend_path:
                    logger.debug("[SMTP Registry] Active provider resolved from DB: %s", slug)
                    return provider
            # Backend path is a standard Django backend (SMTP/console), not in registry.
            # Fall through to priority fallback.
    except Exception as exc:
        logger.warning("[SMTP Registry] DB lookup failed, using priority fallback: %s", exc)

    # Priority fallback — return first available provider
    for slug in _PROVIDER_PRIORITY:
        provider = SMTP_PROVIDER_REGISTRY.get(slug)
        if provider is not None:
            logger.debug("[SMTP Registry] Fallback provider: %s", slug)
            return provider

    raise RuntimeError(
        "[SMTP Registry] No SMTP provider registered. "
        "Check apps/providers/SMTP/registry.py and provider singletons."
    )


def get_provider_by_slug(slug: str) -> SMTPProviderContract | None:
    """
    Return a specific provider by slug, or None if not found.

    Args:
        slug: Provider slug (e.g. "brevo", "mailgun", "zoho").

    Returns:
        SMTPProviderContract | None
    """
    return SMTP_PROVIDER_REGISTRY.get(slug)


def run_all_health_checks() -> list[dict]:
    """
    Run health checks on all registered providers.

    Returns a list of health result dicts for the admin health dashboard.
    """
    results = []
    for slug, provider in SMTP_PROVIDER_REGISTRY.items():
        try:
            result = provider.health_check()
            results.append({
                "slug": slug,
                "display_name": getattr(provider, "display_name", slug),
                "healthy": result.healthy,
                "latency_ms": result.latency_ms,
                "message": result.message,
                "error": result.error,
            })
        except Exception as exc:
            logger.error("[SMTP Registry] Health check failed for %s: %s", slug, exc)
            results.append({
                "slug": slug,
                "display_name": getattr(provider, "display_name", slug),
                "healthy": False,
                "latency_ms": 0.0,
                "message": "Health check raised an exception",
                "error": str(exc),
            })
    return results


__all__ = [
    "SMTP_PROVIDER_REGISTRY",
    "get_active_provider",
    "get_provider_by_slug",
    "run_all_health_checks",
]
