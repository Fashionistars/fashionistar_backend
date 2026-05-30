# apps/providers/SMTP/mailgun_provider.py
"""
Mailgun transactional email provider implementation.

Health check: calls Mailgun's ``GET /v4/domains`` with the configured API key.
This validates API credentials and lists sender domains without sending email.

Anymail docs: https://anymail.dev/en/stable/esps/mailgun/
Mailgun API:  https://documentation.mailgun.com/docs/mailgun/api-reference/openapi-final/
"""

from __future__ import annotations

import base64
import logging
import time
from typing import Any

from apps.providers.SMTP.contract import ProviderHealthResult, SMTPProviderContract

logger = logging.getLogger(__name__)

_MAILGUN_API_BASE_US  = "https://api.mailgun.net/v4"
_MAILGUN_API_BASE_EU  = "https://api.eu.mailgun.net/v4"


class MailgunSMTPProvider(SMTPProviderContract):
    """
    Mailgun transactional email provider.

    Health check: GET /v4/domains with HTTP Basic auth (api:<MAILGUN_API_KEY>).
    Requires: ``ANYMAIL["MAILGUN_API_KEY"]`` and ``ANYMAIL["MAILGUN_SENDER_DOMAIN"]``
    in Django settings.
    """

    slug = "mailgun"
    display_name = "Mailgun"

    def _get_credentials(self) -> tuple[str, str]:
        """Resolve API key and sender domain from ANYMAIL settings."""
        from django.conf import settings
        anymail = getattr(settings, "ANYMAIL", {})
        api_key    = anymail.get("MAILGUN_API_KEY", "") or getattr(settings, "MAILGUN_API_KEY", "")
        sender_domain = (
            anymail.get("MAILGUN_SENDER_DOMAIN", "")
            or getattr(settings, "MAILGUN_SENDER_DOMAIN", "")
        )
        return api_key, sender_domain

    def _get_base_url(self) -> str:
        """Return EU or US API base URL based on MAILGUN_API_URL setting."""
        from django.conf import settings
        api_url = getattr(settings, "ANYMAIL", {}).get("MAILGUN_API_URL", "")
        if api_url:
            return api_url.rstrip("/")
        return _MAILGUN_API_BASE_US

    def health_check(self) -> ProviderHealthResult:
        """
        Probe Mailgun's GET /v4/domains endpoint to verify API key.

        Returns:
            ProviderHealthResult: healthy=True if Mailgun returned 200 OK.
        """
        import json
        import urllib.error
        import urllib.request

        api_key, _ = self._get_credentials()
        if not api_key:
            return ProviderHealthResult(
                provider_slug=self.slug,
                healthy=False,
                message="MAILGUN_API_KEY not configured in ANYMAIL settings.",
                error="Missing API key",
            )

        # Mailgun uses HTTP Basic auth: username="api", password=<API_KEY>
        credentials = base64.b64encode(f"api:{api_key}".encode()).decode("ascii")
        base_url = self._get_base_url()
        url = f"{base_url}/domains?limit=1"

        req = urllib.request.Request(url, method="GET")
        req.add_header("Authorization", f"Basic {credentials}")
        req.add_header("Accept", "application/json")

        t_start = time.monotonic()
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                latency_ms = (time.monotonic() - t_start) * 1000
                body = json.loads(resp.read().decode("utf-8"))
                total = body.get("total_count", "?")
                return ProviderHealthResult(
                    provider_slug=self.slug,
                    healthy=True,
                    latency_ms=round(latency_ms, 1),
                    message=f"Mailgun API OK: {total} domain(s) registered",
                    raw_response={"total_count": total},
                )
        except urllib.error.HTTPError as exc:
            latency_ms = (time.monotonic() - t_start) * 1000
            error_body = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
            return ProviderHealthResult(
                provider_slug=self.slug,
                healthy=False,
                latency_ms=round(latency_ms, 1),
                message=f"Mailgun HTTP {exc.code}: {exc.reason}",
                error=f"HTTPError {exc.code}: {error_body[:200]}",
            )
        except Exception as exc:
            latency_ms = (time.monotonic() - t_start) * 1000
            return ProviderHealthResult(
                provider_slug=self.slug,
                healthy=False,
                latency_ms=round(latency_ms, 1),
                message="Mailgun health check failed",
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
        Send email via Mailgun HTTP API (POST /v4/{domain}/messages).

        Supports Mailgun-specific features: o:tags, h:X-Mailgun-Variables.

        Returns:
            dict: Mailgun API response ({"id": "<...>", "message": "Queued"}).
        """
        import json
        import urllib.request
        import urllib.parse
        import urllib.error
        from django.conf import settings

        api_key, sender_domain = self._get_credentials()
        if not sender_domain:
            raise ValueError("MAILGUN_SENDER_DOMAIN not configured in ANYMAIL settings.")

        sender_email = from_email or getattr(
            settings, "DEFAULT_FROM_EMAIL", f"noreply@{sender_domain}"
        )

        # Mailgun messages endpoint uses multipart/form-data
        data: dict[str, Any] = {
            "from": sender_email,
            "to": to,
            "subject": subject,
            "html": html_body,
        }
        if text_body:
            data["text"] = text_body
        if tags:
            data["o:tag"] = tags  # Mailgun accepts multiple o:tag fields
        if metadata:
            import json as _json
            data["h:X-Mailgun-Variables"] = _json.dumps(metadata)

        # Build URL-encoded form data
        form_data = urllib.parse.urlencode(data, doseq=True).encode("utf-8")
        base_url = self._get_base_url()
        url = f"{base_url}/{sender_domain}/messages"

        credentials = base64.b64encode(f"api:{api_key}".encode()).decode("ascii")
        req = urllib.request.Request(url, data=form_data, method="POST")
        req.add_header("Authorization", f"Basic {credentials}")
        req.add_header("Content-Type", "application/x-www-form-urlencoded")
        req.add_header("Accept", "application/json")

        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                logger.info("Mailgun send OK: id=%s", result.get("id", "?"))
                return result
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
            logger.error("Mailgun send failed: HTTP %d — %s", exc.code, body[:400])
            raise


# Singleton — used by ProviderHealthCheck task
MAILGUN = MailgunSMTPProvider()
