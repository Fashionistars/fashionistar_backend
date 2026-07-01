# apps/providers/SMS/__init__.py
"""
SMS Provider Sub-Package.

Provides three SMS dispatch class drivers for Nigerian and global message
delivery.  Each driver implements ``.send(to, body) -> str`` (sync) and
``.asend(to, body) -> str`` (async) interfaces.

Drivers:
    TermiiSMSProvider    — Termii (Nigerian-first, OTP + bulk SMS, NDPC compliant).
    TwilioSMSProvider    — Twilio (global, WhatsApp, programmable messaging).
    BulksmsNGSMSProvider — BulkSMS Nigeria (cost-effective local delivery).

Selection:
    The active provider is resolved from the ``SMSProviderConfig`` DB record
    (admin-managed).  Configure via Django Admin → Providers → SMS Config.

Environment Variables (per driver):
    Termii:
        TERMII_API_KEY, TERMII_SENDER_ID (default: "Fashionistar")
    Twilio:
        TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_FROM_NUMBER
    BulkSMS Nigeria:
        BULKSMS_NG_API_TOKEN, BULKSMS_NG_SENDER_ID (default: "Fashionistar")

Usage (via backend — preferred)::

    from apps.providers.backends.sms_backend import SMSBackend
    SMSBackend().send_sms(to="+2348012345678", message="Your OTP is 123456")

Direct usage (for testing)::

    from apps.providers.SMS.termii import TermiiSMSProvider
    provider = TermiiSMSProvider()
    provider.send(to="+2348012345678", message="Hello from Fashionistar")
"""

from apps.providers.SMS.bulksmsNG import BulksmsNGSMSProvider
from apps.providers.SMS.termii import TermiiSMSProvider
from apps.providers.SMS.twilio import TwilioSMSProvider
from apps.providers.SMS.kudi import KudiSMSProvider

# ── Django Admin Choices ───────────────────────────────────────────────────────

SMS_BACKEND_CHOICES: list[tuple[str, str]] = [
    ("apps.providers.SMS.termii.TermiiSMSProvider", "Termii (Nigerian-first)"),
    ("apps.providers.SMS.twilio.TwilioSMSProvider", "Twilio (Global / WhatsApp)"),
    ("apps.providers.SMS.bulksmsNG.BulksmsNGSMSProvider", "BulkSMS Nigeria"),
    ("apps.providers.SMS.kudi.KudiSMSProvider", "Kudi SMS"),
]

_SMS_LABEL_LOOKUP: dict[str, str] = dict(SMS_BACKEND_CHOICES)


def get_sms_provider_label(class_path: str) -> str:
    """Return the human-readable name for an SMS provider class path.

    Used in ``SMSProviderConfig.__str__`` and admin list displays.

    Args:
        class_path: Dotted Python import path of the SMS provider class.

    Returns:
        str: Display name, or the ``class_path`` itself if not found.
    """
    return _SMS_LABEL_LOOKUP.get(class_path, class_path)


__all__ = [
    # Driver classes
    "TermiiSMSProvider",
    "TwilioSMSProvider",
    "BulksmsNGSMSProvider",
    "KudiSMSProvider",
    # Registry helpers (consumed by SMSProviderConfig)
    "SMS_BACKEND_CHOICES",
    "get_sms_provider_label",
]
