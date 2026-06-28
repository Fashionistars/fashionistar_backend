# apps/providers/SMTP/contract.py
"""
SMTPProviderContract — Abstract base class for transactional email providers.

Defines the standard interface every email provider implementation must satisfy.
This enables the ProviderHealthCheck Celery task to call a uniform ``health_check()``
method on each provider without knowing their internal API details.

Design
------
* ``health_check()`` → sends a no-op probe to the provider's API.
  It never sends a real email; it uses a credentials validation or API-ping
  endpoint where available.
* ``send_transactional()`` → direct programmatic send (bypasses Django's
  email backend layer for high-priority transactional emails that need
  provider-specific features, e.g. Brevo tags, Mailgun delivery tracking).
* All methods are synchronous (called from Celery tasks, never ASGI views).

Each provider module (brevo.py, mailgun.py, zoho.py) exports an instance:
  BREVO  = BrevoSMTPProvider()
  MAILGUN = MailgunSMTPProvider()
  ZOHO   = ZohoSMTPProvider()

The ProviderHealthCheck Celery task imports these instances and calls
``instance.health_check()`` on each.
"""

from __future__ import annotations

import abc
import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ProviderHealthResult:
    """
    Structured result from a provider health check probe.

    Attributes:
        provider_slug: Short key for the provider (e.g. "brevo").
        healthy:       True if the provider API responded successfully.
        latency_ms:    Round-trip latency of the health check in milliseconds.
        message:       Human-readable status description.
        raw_response:  Optional raw API response payload (for debug logging).
        error:         Exception string if the check failed, else None.
    """
    provider_slug: str
    healthy: bool
    latency_ms: float = 0.0
    message: str = ""
    raw_response: dict[str, Any] | None = None
    error: str | None = None


class SMTPProviderContract(abc.ABC):
    """
    Abstract base contract for transactional email providers.

    All SMTP provider implementations MUST subclass this and implement:
      - ``health_check()``
      - ``send_transactional()`` (optional but recommended)

    Providers that delegate entirely to Anymail (Brevo, Mailgun) implement
    ``health_check()`` by calling the provider's credentials-validation API.
    """

    #: Short slug matching the SMTP metadata dict (e.g. "brevo", "mailgun", "zoho")
    slug: str = ""

    #: Human-readable display name for logging and admin alerts
    display_name: str = ""

    @abc.abstractmethod
    def health_check(self) -> ProviderHealthResult:
        """
        Probe the provider API to verify credentials and connectivity.

        Must NOT send a real email.  Use a dedicated ping or validate-credentials
        endpoint where available.

        Returns:
            ProviderHealthResult: Structured result with healthy flag + latency.
        """

    def send_transactional(
        self,
        *,
        to: str,
        subject: str,
        html_body: str,
        text_body: str = "",
        from_email: str | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Send a single transactional email directly via the provider's HTTP API.

        Default implementation delegates to Django's configured email backend
        (i.e. Anymail).  Subclasses can override for provider-specific features
        (delivery time windows, dedicated IPs, advanced tracking).

        Args:
            to:         Recipient email address.
            subject:    Email subject line.
            html_body:  HTML body content.
            text_body:  Plain-text fallback (optional).
            from_email: Override sender address (defaults to DEFAULT_FROM_EMAIL).
            tags:       Provider-specific tags/categories for analytics.
            metadata:   Provider-specific metadata dict.

        Returns:
            dict: Provider API response payload (varies by provider).
        """
        from django.conf import settings
        from django.core.mail import send_mail

        sender = from_email or getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@fashionistar.net")
        try:
            send_mail(
                subject=subject,
                message=text_body or "",
                from_email=sender,
                recipient_list=[to],
                html_message=html_body,
                fail_silently=False,
            )
            return {"status": "sent", "provider": self.slug}
        except Exception as exc:
            logger.error(
                "SMTPProviderContract.send_transactional [%s]: %s", self.slug, exc
            )
            raise


__all__ = [
    "SMTPProviderContract",
    "ProviderHealthResult",
]
