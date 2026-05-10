# apps/providers/backends/__init__.py
"""
Provider Backend Adapters Sub-Package.

This sub-package bridges the Fashionistar provider registry with Django's
standard backend dispatch mechanism, enabling the rest of the codebase to
send emails and SMS messages using Django's familiar ``send_mail()`` / custom
SMS APIs without coupling to a specific vendor.

Backends:
    email_backend.EmailBackend — Django ``EMAIL_BACKEND``-compatible adapter.
        Resolves the active ``EmailProviderConfig`` from the DB and dispatches
        through the configured SMTP/API driver (Brevo, Mailgun, or Zoho).

    sms_backend.SMSBackend — Custom SMS dispatch adapter.
        Resolves the active ``SMSProviderConfig`` from the DB and dispatches
        through the configured SMS driver (Termii, Twilio, or BulkSMS NG).

Configuration:
    Set ``EMAIL_BACKEND = "apps.providers.backends.email_backend.EmailBackend"``
    in Django settings to activate the DB-driven email provider selection.

    SMS dispatch is called directly:
        ``from apps.providers.backends.sms_backend import SMSBackend``
"""

from apps.providers.backends.email_backend import EmailBackend
from apps.providers.backends.sms_backend import SMSBackend

__all__ = [
    "EmailBackend",
    "SMSBackend",
]
