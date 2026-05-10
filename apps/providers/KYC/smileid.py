# apps/providers/KYC/smileid.py
"""
Smile Identity KYC Provider.

Smile ID is the leading biometric identity verification platform across
West and East Africa. It supports:
  - BVN lookup (Nigeria)
  - NIN lookup (Nigeria)
  - Document verification (NIN card, passport, driver's license)
  - Biometric liveness check + selfie match

API version: v2
Docs: https://docs.usesmileid.com/

Smile Identity KYC Provider — Africa's leading biometric identity platform.


Required KYCProviderConfig fields:
  api_key       → Smile ID API key (called "api_key" in Smile ID docs)
  api_secret    → Smile ID API key secret ("api_key_secret")
  extra_config  → {"partner_id": "<YOUR_PARTNER_ID>"}
  base_url      → https://testapi.smileidentity.com/v1 (sandbox)
               or https://api.smileidentity.com/v1 (live)

NDPR compliance:
  - Raw BVN/NIN numbers are NEVER sent. Only last4 + KycService hash is used
    to generate the id_number for Smile ID lookups.
  - The provider_reference (SmileJobID) is stored for webhook reconciliation.
"""

from __future__ import annotations

import json
import logging
import uuid

from apps.common.http import ProviderSyncHTTPClient, RetryPolicy
from apps.providers.KYC.base import (
    AbstractKYCProvider,
    KYCVerificationResult,
    WebhookResult,
)

logger = logging.getLogger("application")


class SmileIdentityProvider(AbstractKYCProvider):
    """
    Smile Identity v2 KYC provider implementation.

    Endpoints used:
      POST /v1/id_verification        — BVN / NIN lookup (Basic KYC)
      POST /v1/smile_links            — Hosted smart selfie flow
      POST /v1/business_verification  — CAC lookup (vendor onboarding)

    All requests are synchronous (httpx.post). Async callers should wrap
    with asyncio.to_thread via the circuit breaker decorator.

    Smile Identity v2 KYC provider via ProviderSyncHTTPClient
    (retry, structured logging, idempotency headers, circuit-safe errors).
    """

    PROVIDER_SLUG = "smileid"
    DEFAULT_BASE_URL = "https://testapi.smileidentity.com/v1"  # default to sandbox
    LIVE_BASE_URL = "https://api.smileidentity.com/v1"

    def __init__(self, config) -> None:
        super().__init__(config)
        self._partner_id: str = config.extra_config.get("partner_id", "")
        self._api_key: str = config.api_key or ""
        self._api_secret: str = config.api_secret or ""
        base = self.LIVE_BASE_URL if not self._sandbox_mode() else self.DEFAULT_BASE_URL
        self._http = ProviderSyncHTTPClient(
            provider="smileid",
            base_url=base,
            retry_policy=RetryPolicy(max_attempts=2, backoff_seconds=1.0),
        )

    # ── BVN Verification ───────────────────────────────────────────────────────

    def verify_bvn(self, bvn_hash: str, last4: str) -> KYCVerificationResult:
        """
        BVN lookup via Smile ID Basic KYC.

        Smile ID does not accept raw BVN. We use the last4 to generate a
        masked id_number that Smile ID uses for disambiguation only.
        The actual identity match happens server-side via the partner integration.
        """
        job_id = str(uuid.uuid4())
        try:
            resp = self._http.request(
                "POST",
                "/id_verification",
                action="verify_bvn",
                reference=job_id,
                json={
                    "source_sdk": "python",
                    "source_sdk_version": "1.0.0",
                    "partner_id": self._partner_id,
                    "partner_params": {
                        "job_id": job_id,
                        "user_id": f"bvn_{bvn_hash[:16]}",
                        "job_type": 5,  # Basic KYC
                    },
                    "id_info": {
                        "country": "NG",
                        "id_type": "BVN",
                        "id_number": f"*******{last4}",
                    },
                    "api_key": self._api_key,
                },
            )
            data = resp.data
            smile_job_id = data.get("SmileJobID", job_id)
            result_code = data.get("ResultCode", "")
            result_text = data.get("ResultText", "")
            success = result_code in ("1012", "1020")  # Exact match codes

            logger.info(
                "SmileIdentityProvider.verify_bvn: job=%s success=%s code=%s",
                smile_job_id,
                success,
                result_code,
            )
            return KYCVerificationResult(
                success=success,
                provider_reference=smile_job_id,
                confidence_score=1.0 if success else 0.0,
                raw_response=data,
                error_code=result_code if not success else "",
                error_message=result_text if not success else "",
            )
        except Exception as exc:
            logger.error("SmileIdentityProvider.verify_bvn: unexpected error: %s", exc)
            return KYCVerificationResult(
                success=False,
                provider_reference=job_id,
                error_code="ERROR",
                error_message=str(exc),
                raw_response={},
            )

    # ── NIN Verification ───────────────────────────────────────────────────────

    def verify_nin(self, nin_hash: str, last4: str) -> KYCVerificationResult:
        """NIN lookup via Smile ID Basic KYC (job_type=5, id_type=NIN)."""
        job_id = str(uuid.uuid4())
        try:
            resp = self._http.request(
                "POST",
                "/id_verification",
                action="verify_nin",
                reference=job_id,
                json={
                    "source_sdk": "python",
                    "source_sdk_version": "1.0.0",
                    "partner_id": self._partner_id,
                    "partner_params": {
                        "job_id": job_id,
                        "user_id": f"nin_{nin_hash[:16]}",
                        "job_type": 5,
                    },
                    "id_info": {
                        "country": "NG",
                        "id_type": "NIN",
                        "id_number": f"*******{last4}",
                    },
                    "api_key": self._api_key,
                },
            )
            data = resp.data
            smile_job_id = data.get("SmileJobID", job_id)
            result_code = data.get("ResultCode", "")
            success = result_code in ("1012", "1020")
            return KYCVerificationResult(
                success=success,
                provider_reference=smile_job_id,
                confidence_score=1.0 if success else 0.0,
                raw_response=data,
                error_code=result_code if not success else "",
                error_message=data.get("ResultText", "") if not success else "",
            )
        except Exception as exc:
            logger.error("SmileIdentityProvider.verify_nin: error: %s", exc)
            return KYCVerificationResult(
                success=False,
                provider_reference=job_id,
                error_code="ERROR",
                error_message=str(exc),
                raw_response={},
            )

    # ── Webhook Handler ────────────────────────────────────────────────────────

    def handle_webhook(self, payload: dict, signature: str) -> WebhookResult:
        """
        Validate Smile ID callback and parse the result.

        Smile ID sends a JSON body with SmileJobID, ResultCode, ResultText.
        Signature header: X-Smile-Signature (HMAC-SHA256 of body using api_secret).
        """
        payload_bytes = json.dumps(payload, separators=(",", ":")).encode()
        if not self._verify_hmac(payload_bytes, signature, self._api_secret):
            raise ValueError(
                "SmileIdentityProvider.handle_webhook: invalid HMAC signature"
            )

        job_id = payload.get("SmileJobID", "")
        result_code = payload.get("ResultCode", "")
        success = result_code in ("1012", "1020")

        return WebhookResult(
            event_type="verification.complete" if success else "verification.failed",
            provider_reference=job_id,
            success=success,
            raw_payload=payload,
        )
