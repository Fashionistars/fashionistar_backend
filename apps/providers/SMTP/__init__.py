# apps/providers/SMTP/__init__.py
"""
SMTP / Transactional Email Provider Sub-Package.

Provides metadata for three transactional email backends.  Unlike the SMS
and KYC sub-packages, these providers do NOT implement a custom class driver —
they delegate actual delivery to the Anymail library (Brevo, Mailgun) or the
Zoho ZeptoMail library (Zoho), which wrap Django's standard email backend
interface natively.

Providers:
    Brevo (Sendinblue) — EU GDPR-compliant, excellent Nigerian deliverability.
    Mailgun            — Developer-friendly, high-volume capable, DKIM/SPF.
    Zoho ZeptoMail     — Suits teams already on the Zoho suite.

Selection:
    The active backend is resolved from the ``EmailProviderConfig`` DB model
    (admin-managed).  Configure via Django Admin → Providers → Email Config.

Required Environment Variables (per backend):
    Brevo:   BREVO_API_KEY
    Mailgun: MAILGUN_API_KEY, MAILGUN_SENDER_DOMAIN
    Zoho:    ZOHO_ZEPTOMAIL_TOKEN

Usage (via Django's email API — preferred)::

    from django.core.mail import send_mail
    send_mail(
        subject="Order confirmed",
        message="Thank you for your order.",
        from_email="noreply@fashionistar.net",
        recipient_list=["customer@example.com"],
    )
"""

from apps.providers.SMTP.brevo import BREVO_PROVIDER
from apps.providers.SMTP.mailgun import MAILGUN_PROVIDER
from apps.providers.SMTP.zoho import ZOHO_PROVIDER

# ── Registry ──────────────────────────────────────────────────────────────────

# All known email providers in display-priority order
_ALL_EMAIL_PROVIDERS = [
    BREVO_PROVIDER,
    MAILGUN_PROVIDER,
    ZOHO_PROVIDER,
]

# ── Django Admin Choices ───────────────────────────────────────────────────────

# Additional standard Django backends surfaced in the admin dropdown
_STANDARD_BACKENDS = [
    ("django.core.mail.backends.smtp.EmailBackend", "SMTP (Gmail / Custom)"),
    ("django.core.mail.backends.console.EmailBackend", "Console (dev only)"),
]

# Full choices list for ``EmailProviderConfig.email_backend``
EMAIL_BACKEND_CHOICES: list[tuple[str, str]] = [
    (p["backend_path"], p["display_name"]) for p in _ALL_EMAIL_PROVIDERS
] + _STANDARD_BACKENDS


def get_email_backend_label(backend_path: str) -> str:
    """Return the human-readable display name for a backend path.

    Used in ``EmailProviderConfig.__str__`` and admin list displays.

    Args:
        backend_path: The dotted Python import path of the email backend.

    Returns:
        str: The display name, or the ``backend_path`` itself if not found.
    """
    lookup = dict(EMAIL_BACKEND_CHOICES)
    return lookup.get(backend_path, backend_path)


__all__ = [
    # Provider metadata dicts
    "BREVO_PROVIDER",
    "MAILGUN_PROVIDER",
    "ZOHO_PROVIDER",
    # Registry helpers (consumed by EmailProviderConfig)
    "EMAIL_BACKEND_CHOICES",
    "get_email_backend_label",
    # Provider registry list
    "_ALL_EMAIL_PROVIDERS",
]
