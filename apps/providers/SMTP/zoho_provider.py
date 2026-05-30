# apps/providers/SMTP/zoho_provider.py
"""
Zoho ZeptoMail transactional email provider implementation.

Health check: calls Zoho ZeptoMail's ``GET /p1/getMailAgentDetails`` endpoint
with the configured send-mail token.  This validates credentials without
sending a real email.

Library:     https://pypi.org/project/django-zoho-zeptomail/
API docs:    https://www.zoho.com/zeptomail/help/api/
"""

from __future__ import annotations

import logging
import time
from typing import Any

from apps.providers.SMTP.contract import ProviderHealthResult, SMTPProviderContract

logger = logging.getLogger(__name__)

_ZOHO_ZEPTOMAIL_API_BASE = "https://api.zeptomail.com/v1.1"


class ZohoSMTPProvider(SMTPProviderContract):
    """
    Zoho ZeptoMail transactional email provider.

    Health check: GET /v1.1/mailagent with Authorization header.
    Requires: ``ZOHO_ZEPTOMAIL_TOKEN`` in Django settings.
    """

    slug = "zoho"
    display_name = "Zoho ZeptoMail"

    def _get_token(self) -> str:
        """Resolve ZeptoMail send-mail token from Django settings."""
        from django.conf import settings
        return (
            getattr(settings, "ZOHO_ZEPTOMAIL_TOKEN", "")
            or getattr(settings, "ANYMAIL", {}).get("ZOHO_ZEPTOMAIL_TOKEN", "")
        )

    def health_check(self) -> ProviderHealthResult:
        """
        Probe ZeptoMail GET /mailagent to verify send-mail token and connectivity.

        Returns:
            ProviderHealthResult: healthy=True if ZeptoMail returned 200 OK.
        """
        import json
        import urllib.error
        import urllib.request

        token = self._get_token()
        if not token:
            return ProviderHealthResult(
                provider_slug=self.slug,
                healthy=False,
                message="ZOHO_ZEPTOMAIL_TOKEN not configured in Django settings.",
                error="Missing token",
            )

        # ZeptoMail uses Authorization: Zoho-enczapikey <token>
        url = f"{_ZOHO_ZEPTOMAIL_API_BASE}/mailagent"
        req = urllib.request.Request(url, method="GET")
        req.add_header("Authorization", f"Zoho-enczapikey {token}")
        req.add_header("Accept", "application/json")

        t_start = time.monotonic()
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                latency_ms = (time.monotonic() - t_start) * 1000
                body = json.loads(resp.read().decode("utf-8"))
                # ZeptoMail returns mail agent details on 200 OK
                agent_name = (
                    body.get("data", {}).get("display_name", "")
                    or body.get("display_name", "")
                )
                return ProviderHealthResult(
                    provider_slug=self.slug,
                    healthy=True,
                    latency_ms=round(latency_ms, 1),
                    message=f"Zoho ZeptoMail OK: agent={agent_name!r}",
                    raw_response=body,
                )
        except urllib.error.HTTPError as exc:
            latency_ms = (time.monotonic() - t_start) * 1000
            error_body = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
            return ProviderHealthResult(
                provider_slug=self.slug,
                healthy=False,
                latency_ms=round(latency_ms, 1),
                message=f"Zoho ZeptoMail HTTP {exc.code}: {exc.reason}",
                error=f"HTTPError {exc.code}: {error_body[:200]}",
            )
        except Exception as exc:
            latency_ms = (time.monotonic() - t_start) * 1000
            return ProviderHealthResult(
                provider_slug=self.slug,
                healthy=False,
                latency_ms=round(latency_ms, 1),
                message="Zoho ZeptoMail health check failed",
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
        Send email via ZeptoMail API v1.1 (POST /email).

        Returns:
            dict: ZeptoMail API response ({"data": [...], "message": "OK"}).
        """
        import json
        import urllib.request
        import urllib.error
        from django.conf import settings

        token = self._get_token()
        sender_email = from_email or getattr(
            settings, "DEFAULT_FROM_EMAIL", "noreply@fashionistar.net"
        )

        payload: dict[str, Any] = {
            "from": {"address": sender_email},
            "to": [{"email_address": {"address": to}}],
            "subject": subject,
            "htmlbody": html_body,
        }
        if text_body:
            payload["textbody"] = text_body
        if metadata:
            payload["mail_template_key"] = metadata.get("template_key", "")

        url = f"{_ZOHO_ZEPTOMAIL_API_BASE}/email"
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            method="POST",
        )
        req.add_header("Authorization", f"Zoho-enczapikey {token}")
        req.add_header("Content-Type", "application/json")
        req.add_header("Accept", "application/json")

        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                logger.info("Zoho ZeptoMail send OK: %s", result.get("message", ""))
                return result
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
            logger.error("Zoho send failed: HTTP %d — %s", exc.code, body[:400])
            raise


# Singleton — used by ProviderHealthCheck task
ZOHO = ZohoSMTPProvider()
