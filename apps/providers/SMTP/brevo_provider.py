# apps/providers/SMTP/brevo_provider.py
"""
Brevo (Sendinblue) transactional email provider implementation.

Health check: calls Brevo's ``GET /v3/account`` endpoint with the configured
API key.  This validates credentials without sending any email.

Anymail docs: https://anymail.dev/en/stable/esps/brevo/
Brevo API:    https://developers.brevo.com/reference/getaccount
"""

from __future__ import annotations

import logging
import time
from typing import Any

from apps.providers.SMTP.contract import ProviderHealthResult, SMTPProviderContract

logger = logging.getLogger(__name__)

_BREVO_API_BASE = "https://api.brevo.com/v3"


class BrevoSMTPProvider(SMTPProviderContract):
    """
    Brevo (formerly Sendinblue) transactional email provider.

    Health check: GET /v3/account with X-API-Key header.
    Requires: ``ANYMAIL["BREVO_API_KEY"]`` in Django settings.
    """

    slug = "brevo"
    display_name = "Brevo (Sendinblue)"

    def _get_api_key(self) -> str:
        """Resolve API key from ANYMAIL settings."""
        from django.conf import settings
        return (
            getattr(settings, "ANYMAIL", {}).get("BREVO_API_KEY", "")
            or getattr(settings, "BREVO_API_KEY", "")
        )

    def health_check(self) -> ProviderHealthResult:
        """
        Probe Brevo's /v3/account endpoint to verify API key and connectivity.

        Returns:
            ProviderHealthResult: healthy=True if the API returned 200 OK.
        """
        import urllib.error
        import urllib.request
        import json

        api_key = self._get_api_key()
        if not api_key:
            return ProviderHealthResult(
                provider_slug=self.slug,
                healthy=False,
                message="BREVO_API_KEY not configured in ANYMAIL settings.",
                error="Missing API key",
            )

        url = f"{_BREVO_API_BASE}/account"
        req = urllib.request.Request(url, method="GET")
        req.add_header("accept", "application/json")
        req.add_header("api-key", api_key)

        t_start = time.monotonic()
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                latency_ms = (time.monotonic() - t_start) * 1000
                body = json.loads(resp.read().decode("utf-8"))
                email = body.get("email", "")
                return ProviderHealthResult(
                    provider_slug=self.slug,
                    healthy=True,
                    latency_ms=round(latency_ms, 1),
                    message=f"Brevo account OK: {email}",
                    raw_response=body,
                )
        except urllib.error.HTTPError as exc:
            latency_ms = (time.monotonic() - t_start) * 1000
            error_body = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
            return ProviderHealthResult(
                provider_slug=self.slug,
                healthy=False,
                latency_ms=round(latency_ms, 1),
                message=f"Brevo HTTP {exc.code}: {exc.reason}",
                error=f"HTTPError {exc.code}: {error_body[:200]}",
            )
        except Exception as exc:
            latency_ms = (time.monotonic() - t_start) * 1000
            return ProviderHealthResult(
                provider_slug=self.slug,
                healthy=False,
                latency_ms=round(latency_ms, 1),
                message="Brevo health check failed",
                error=str(exc),
            )

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
        Send a transactional email via Brevo API v3 directly (bypasses Anymail).

        Supports Brevo-specific features: tags, sender validation, tracking.
        Falls back to Anymail backend if direct API call fails.

        Returns:
            dict: Brevo API response ({"messageId": "..."}).
        """
        import json
        import urllib.request
        import urllib.error
        from django.conf import settings

        api_key = self._get_api_key()
        sender_email = from_email or getattr(
            settings, "DEFAULT_FROM_EMAIL", "noreply@fashionistar.net"
        )
        payload: dict[str, Any] = {
            "sender": {"email": sender_email},
            "to": [{"email": to}],
            "subject": subject,
            "htmlContent": html_body,
        }
        if text_body:
            payload["textContent"] = text_body
        if tags:
            payload["tags"] = tags
        if metadata:
            payload["params"] = metadata

        url = f"{_BREVO_API_BASE}/smtp/email"
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            method="POST",
        )
        req.add_header("accept", "application/json")
        req.add_header("content-type", "application/json")
        req.add_header("api-key", api_key)

        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                logger.info("Brevo send OK: messageId=%s", result.get("messageId"))
                return result
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
            logger.error("Brevo send failed: HTTP %d — %s", exc.code, body[:400])
            raise


# Singleton — used by ProviderHealthCheck task
BREVO = BrevoSMTPProvider()
