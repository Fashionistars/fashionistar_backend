"""
MirrorSize / GetMeasured provider — centralized registry version.

This is the canonical implementation inside apps/providers.
The measurements app should import from here via:

    from apps.providers.MirrorSize import MirrorSizeClient, MirrorSizeProviderError

The old apps.measurements.providers.mirrorsize is kept as a thin compatibility
shim that re-exports from this module so no existing service code breaks.

All external HTTP traffic goes through apps.common.http for consistent retry,
timeout, logging, and circuit-breaker behaviour across all domains.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from django.conf import settings

from apps.common.http import ProviderHTTPError, ProviderSyncHTTPClient, RetryPolicy
from apps.providers.circuit_breaker import CircuitBreaker

logger = logging.getLogger("application")

_breaker = CircuitBreaker(provider_key="mirrorsize", failure_threshold=3)


class MirrorSizeProviderError(Exception):
    """Raised when MirrorSize credentials or responses are invalid."""


@dataclass(frozen=True)
class MirrorSizeClient:
    """
    Sync client for MirrorSize mobile-browser APIs.

    Instantiate via:
      - ``MirrorSizeClient.from_settings()``     — settings/env only
      - ``MirrorSizeClient.from_config(config)`` — DB provider config + env secrets
    """

    api_key: str
    merchant_id: str
    product_name: str = "GET_MEASURED"
    browser_api_base_url: str = "https://api.user.mirrorsize.com"
    user_home_base_url: str = "https://user.mirrorsize.com/home"

    # ── Factories ──────────────────────────────────────────────────────────────

    @classmethod
    def from_settings(cls) -> "MirrorSizeClient":
        """Build a provider client from Django settings / environment only."""
        api_key = getattr(settings, "MIRRORSIZE_API_KEY", "")
        merchant_id = getattr(settings, "MIRRORSIZE_MERCHANT_ID", "")
        if not api_key or not merchant_id:
            raise MirrorSizeProviderError(
                "MirrorSize is not configured. Set MIRRORSIZE_API_KEY and MIRRORSIZE_MERCHANT_ID."
            )
        return cls(
            api_key=api_key,
            merchant_id=merchant_id,
            product_name=getattr(settings, "MIRRORSIZE_PRODUCT_NAME", "GET_MEASURED"),
            browser_api_base_url=getattr(
                settings,
                "MIRRORSIZE_BROWSER_API_BASE_URL",
                "https://api.user.mirrorsize.com",
            ),
            user_home_base_url=getattr(
                settings,
                "MIRRORSIZE_USER_HOME_BASE_URL",
                "https://user.mirrorsize.com/home",
            ),
        )

    @classmethod
    def from_config(cls, config) -> "MirrorSizeClient":
        """
        Build a client from a MirrorSizeProviderConfig DB instance.

        Operational parameters (product_name, URLs) come from the DB.
        Sensitive credentials (api_key, merchant_id) come from Django settings
        to keep secrets out of the database.
        """
        if not config.enabled:
            raise MirrorSizeProviderError("MirrorSize integration is disabled by admin.")

        api_key = getattr(settings, "MIRRORSIZE_API_KEY", "")
        merchant_id = getattr(settings, "MIRRORSIZE_MERCHANT_ID", "")
        if not api_key or not merchant_id:
            raise MirrorSizeProviderError(
                "MirrorSize is not configured. Set MIRRORSIZE_API_KEY and MIRRORSIZE_MERCHANT_ID."
            )
        return cls(
            api_key=api_key,
            merchant_id=merchant_id,
            product_name=config.product_name,
            browser_api_base_url=config.browser_api_base_url,
            user_home_base_url=config.user_home_base_url,
        )

    # ── HTTP Client ────────────────────────────────────────────────────────────

    def _http(self) -> ProviderSyncHTTPClient:
        return ProviderSyncHTTPClient(
            provider="mirrorsize",
            base_url=self.browser_api_base_url,
            retry_policy=RetryPolicy(max_attempts=2, backoff_seconds=0.4),
        )

    # ── Access Code Generation ─────────────────────────────────────────────────

    def generate_mobile_browser_access_code(
        self,
        *,
        email: str,
        name: str = "",
        mobile_no: str = "",
        reference: str = "",
    ) -> dict[str, Any]:
        """Generate a MirrorSize mobile-browser access code and QR code."""
        payload = {
            "apiKey": self.api_key,
            "merchantID": self.merchant_id,
            "productname": self.product_name,
            "emailId": email,
            "name": name,
            "mobileNo": mobile_no,
        }

        def _call():
            return self._http().request(
                "POST",
                "/api/webBrowser/generateAccessCode/",
                action="generate_access_code",
                reference=reference,
                json=payload,
            )

        try:
            response = _breaker.call(_call)
        except ProviderHTTPError as exc:
            raise MirrorSizeProviderError(str(exc)) from exc

        data = response.data
        if data.get("code") != 1 or "data" not in data:
            raise MirrorSizeProviderError(data.get("message") or "MirrorSize access-code generation failed.")

        provider_data = data["data"]
        access_code = str(provider_data.get("accessCode", "")).strip()
        if not access_code:
            raise MirrorSizeProviderError("MirrorSize did not return an access code.")

        logger.info("MirrorSizeClient: access_code generated for ref=%s", reference)
        return {
            "access_code": access_code,
            "qr_code": provider_data.get("qrCode", ""),
            "measurement_url": f"{self.user_home_base_url.rstrip('/')}/{access_code}",
            "provider_payload": data,
        }

    # ── Measurement Retrieval ──────────────────────────────────────────────────

    def get_mobile_browser_measurement(
        self, *, access_code: str, reference: str = ""
    ) -> dict[str, Any]:
        """Fetch completed mobile-browser measurements for an access code."""
        payload = {
            "apiKey": self.api_key,
            "merchantId": self.merchant_id,
            "accessCode": access_code,
        }

        def _call():
            return self._http().request(
                "POST",
                "/api/webBrowser/getmeasurement",
                action="get_measurement",
                reference=reference or access_code,
                json=payload,
            )

        try:
            response = _breaker.call(_call)
        except ProviderHTTPError as exc:
            raise MirrorSizeProviderError(str(exc)) from exc

        data = response.data
        if data.get("code") != 1 or "data" not in data:
            raise MirrorSizeProviderError(
                data.get("message") or "MirrorSize measurement is not available yet."
            )
        return data["data"]
