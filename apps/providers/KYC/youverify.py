# apps/providers/KYC/youverify.py
"""
Youverify KYC Provider.

Youverify is a Nigerian compliance and identity verification platform supporting:
  - BVN verification
  - NIN verification
  - Liveness check + document comparison

API Docs: https://doc.youverify.co/our-legacy-api-and-sdk/identity-verification/identity-verification

Required KYCProviderConfig fields:
  api_key       → Youverify API token ("token" header)
  extra_config  → {"account_id": "<your_account_id>"} (for advanced flows)
  base_url      → https://api.qc.youverify.co/v2 (sandbox) | https://api.youverify.co/v2 (live)

NDPR compliance:
  - Raw BVN/NIN never transmitted. Only masked values used for sandbox contract tests.
  - provider_reference = Youverify request ID, stored for webhook reconciliation.

API Docs: https://doc.youverify.co/our-legacy-api-and-sdk/identity-verification
NDPR: Raw BVN/NIN never transmitted. Only masked values used.
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


class YouverifyProvider(AbstractKYCProvider):
    """
    Youverify Nigeria KYC provider implementation via ProviderSyncHTTPClient

    All credentials sourced from KYCProviderConfig (DB), not .env files.
    """

    PROVIDER_SLUG = "youverify"
    DEFAULT_BASE_URL = "https://api.qc.youverify.co/v2"  # QC = sandbox
    LIVE_BASE_URL = "https://api.youverify.co/v2"

    def __init__(self, config) -> None:
        super().__init__(config)
        self._token: str = config.api_key or ""
        self._webhook_secret: str = config.webhook_secret or ""
        base = self.LIVE_BASE_URL if not self._sandbox_mode() else self.DEFAULT_BASE_URL
        self._http = ProviderSyncHTTPClient(
            provider="youverify",
            base_url=base,
            retry_policy=RetryPolicy(max_attempts=2, backoff_seconds=1.0),
        )

    def _yv_headers(self) -> dict:
        return {"token": self._token, "Content-Type": "application/json"}

    # ── BVN Verification ───────────────────────────────────────────────────────

    def verify_bvn(self, bvn_hash: str, last4: str) -> KYCVerificationResult:
        """
        BVN verification via Youverify.

        POST /v2/api/identities/individual/bvn
        """
        request_id = str(uuid.uuid4())
        try:
            resp = self._http.request(
                "POST",
                "/api/identities/individual/bvn",
                action="verify_bvn",
                reference=request_id,
                headers=self._yv_headers(),
                json={
                    "id": f"0000000{last4}",
                    "isSubjectConsent": True,
                    "metadata": {"requestId": request_id},
                },
            )
            data = resp.data
            success = data.get("success", False) or data.get("data", {}).get(
                "isValid", False
            )
            yv_ref = data.get("data", {}).get("requestId", request_id)
            if success:
                logger.info("YouverifyProvider.verify_bvn: success ref=%s", yv_ref)
            else:
                logger.warning(
                    "YouverifyProvider.verify_bvn: failed ref=%s msg=%s",
                    yv_ref,
                    data.get("message", ""),
                )
            return KYCVerificationResult(
                success=success,
                provider_reference=str(yv_ref),
                confidence_score=1.0 if success else 0.0,
                raw_response=data,
                error_code="" if success else "VERIFICATION_FAILED",
                error_message=(
                    "" if success else data.get("message", "BVN verification failed")
                ),
            )
        except Exception as exc:
            logger.error("YouverifyProvider.verify_bvn: error: %s", exc)
            return KYCVerificationResult(
                success=False,
                provider_reference=request_id,
                error_code="ERROR",
                error_message=str(exc),
                raw_response={},
            )

    # ── NIN Verification ───────────────────────────────────────────────────────

    def verify_nin(self, nin_hash: str, last4: str) -> KYCVerificationResult:
        """
        NIN verification via Youverify.

        POST /v2/api/identities/individual/nin
        """
        request_id = str(uuid.uuid4())
        try:
            resp = self._http.request(
                "POST",
                "/api/identities/individual/nin",
                action="verify_nin",
                reference=request_id,
                headers=self._yv_headers(),
                json={
                    "id": f"000000{last4}",
                    "isSubjectConsent": True,
                    "metadata": {"requestId": request_id},
                },
            )
            data = resp.data
            success = data.get("success", False) or data.get("data", {}).get(
                "isValid", False
            )
            yv_ref = data.get("data", {}).get("requestId", request_id)

            return KYCVerificationResult(
                success=success,
                provider_reference=str(yv_ref),
                confidence_score=1.0 if success else 0.0,
                raw_response=data,
                error_code="" if success else "NIN_VERIFICATION_FAILED",
                error_message=(
                    "" if success else data.get("message", "NIN verification failed")
                ),
            )
        except Exception as exc:
            logger.error("YouverifyProvider.verify_nin: error: %s", exc)
            return KYCVerificationResult(
                success=False,
                provider_reference=request_id,
                error_code="ERROR",
                error_message=str(exc),
                raw_response={},
            )

    # ── Webhook Handler ────────────────────────────────────────────────────────

    def handle_webhook(self, payload: dict, signature: str) -> WebhookResult:
        """
        Validate Youverify webhook.
        Youverify sends X-Youverify-Signature: <HMAC-SHA256 of body>.
        """
        payload_bytes = json.dumps(payload, separators=(",", ":")).encode()
        if not self._verify_hmac(payload_bytes, signature, self._webhook_secret):
            raise ValueError("YouverifyProvider.handle_webhook: invalid HMAC signature")

        event_type = payload.get("event", "verification.unknown")
        ref = payload.get("data", {}).get("requestId", "")
        success = payload.get("success", False) or payload.get("data", {}).get(
            "isValid", False
        )

        return WebhookResult(
            event_type=event_type,
            provider_reference=str(ref),
            success=success,
            raw_payload=payload,
        )
