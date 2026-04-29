"""
SMTP provider registry for Fashionistar.

This package centralizes provider metadata so admin choices, health checks,
and runtime backend resolution share one source of truth instead of scattered
string literals.
"""

from __future__ import annotations

from apps.common.providers.SMTP.brevo import BREVO_PROVIDER
from apps.common.providers.SMTP.mailgun import MAILGUN_PROVIDER
from apps.common.providers.SMTP.zoho import ZOHO_PROVIDER


_BUILTIN_BACKENDS: tuple[tuple[str, str], ...] = (
    ("django.core.mail.backends.smtp.EmailBackend", "SMTP (Gmail)"),
    ("django.core.mail.backends.console.EmailBackend", "Console"),
    ("anymail.backends.sendgrid.EmailBackend", "SendGrid"),
)

_THIRD_PARTY_PROVIDERS: tuple[dict[str, str], ...] = (
    MAILGUN_PROVIDER,
    ZOHO_PROVIDER,
    BREVO_PROVIDER,
)

EMAIL_BACKEND_CHOICES: tuple[tuple[str, str], ...] = _BUILTIN_BACKENDS + tuple(
    (provider["backend_path"], provider["display_name"])
    for provider in _THIRD_PARTY_PROVIDERS
)

EMAIL_PROVIDER_REGISTRY: dict[str, dict[str, str]] = {
    backend_path: {"backend_path": backend_path, "display_name": display_name}
    for backend_path, display_name in _BUILTIN_BACKENDS
}
EMAIL_PROVIDER_REGISTRY.update(
    {provider["backend_path"]: provider for provider in _THIRD_PARTY_PROVIDERS}
)


def get_email_backend_choices() -> tuple[tuple[str, str], ...]:
    """Return the canonical backend choices used by admin configuration."""

    return EMAIL_BACKEND_CHOICES


def get_email_backend_label(backend_path: str) -> str:
    """Resolve a human-friendly provider label from a backend path."""

    provider = EMAIL_PROVIDER_REGISTRY.get(backend_path, {})
    return provider.get("display_name", backend_path)


__all__ = [
    "BREVO_PROVIDER",
    "EMAIL_BACKEND_CHOICES",
    "EMAIL_PROVIDER_REGISTRY",
    "MAILGUN_PROVIDER",
    "ZOHO_PROVIDER",
    "get_email_backend_choices",
    "get_email_backend_label",
]
