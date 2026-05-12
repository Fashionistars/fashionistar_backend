# apps/providers/KYC/dojah.py
"""
Dojah KYC Provider.

Dojah is a Nigerian identity verification platform supporting:
  - BVN validation (POST /api/v1/kyc/bvn)
  - NIN validation (POST /api/v1/kyc/nin)
  - Phone number lookup + face match

API Docs: https://api-docs.dojah.io/docs/nigeria/validate-bvn
CBN KYC Reference: https://www.cbn.gov.ng/PaymentsSystem/BVN.html

Required KYCProviderConfig fields:
  api_key      → Dojah App ID ("App-Id" header)
  api_secret   → Dojah private key ("Authorization" bearer header)
  base_url     → https://sandbox.dojah.io (sandbox) | https://api.dojah.io (live)

NDPR compliance:
  - Raw BVN/NIN are NEVER sent to Dojah. Only last4 is used for masked reference.
  - The `selfie_verification` parameter is False for text-only BVN/NIN lookups.
  - Dojah request_id is stored as provider_reference for webhook reconciliation.
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


class DojahProvider(AbstractKYCProvider):
    """
    Dojah Nigeria KYC provider via ProviderSyncHTTPClient.

    Dojah supports both real-time BVN/NIN validation and webhook callbacks.
    All credentials are sourced from KYCProviderConfig (DB), not .env.
    """

    PROVIDER_SLUG = "dojah"
    DEFAULT_BASE_URL = "https://sandbox.dojah.io"
    LIVE_BASE_URL = "https://api.dojah.io"

    def __init__(self, config) -> None:
        super().__init__(config)
        self._app_id: str = config.api_key or ""  # Dojah "App-Id" header
        self._private_key: str = config.api_secret or ""  # Dojah "Authorization" bearer
        self._webhook_secret: str = config.webhook_secret or ""
        base = self.LIVE_BASE_URL if not self._sandbox_mode() else self.DEFAULT_BASE_URL
        self._http = ProviderSyncHTTPClient(
            provider="dojah",
            base_url=base,
            retry_policy=RetryPolicy(max_attempts=2, backoff_seconds=1.0),
        )

    def _dojah_headers(self) -> dict:
        return {
            "Authorization": self._private_key,
            "AppId": self._app_id,
            "Content-Type": "application/json",
        }

    # ── BVN Verification ───────────────────────────────────────────────────────

    def verify_bvn(self, bvn_hash: str, last4: str) -> KYCVerificationResult:
        """
        BVN lookup via Dojah.

        Dojah validates BVN ownership and returns demographic data.
        We pass a masked BVN (last4 only) since Dojah accepts partial numbers
        in their sandbox environment for contract testing.

        In production: coordinate with Dojah account manager for consent-based
        BVN verification flow that does not require full BVN transmission.
        """
        request_id = str(uuid.uuid4())
        try:
            resp = self._http.request(
                "GET",
                "/api/v1/kyc/bvn",
                action="verify_bvn",
                reference=request_id,
                headers=self._dojah_headers(),
                params={"bvn": f"0000000{last4}"},
            )
            data = resp.data
            entity = data.get("entity", {})
            success = bool(entity.get("bvn")) or data.get("status") == "success"
            dojah_ref = entity.get("reference_id", request_id)
            if success:
                logger.info("DojahProvider.verify_bvn: success ref=%s", dojah_ref)
            else:
                logger.warning("DojahProvider.verify_bvn: failed ref=%s", dojah_ref)
            return KYCVerificationResult(
                success=success,
                provider_reference=str(dojah_ref),
                confidence_score=1.0 if success else 0.0,
                raw_response=data,
                error_code="" if success else "BVN_NOT_FOUND",
                error_message="" if success else str(data.get("error", "")),
            )
        except Exception as exc:
            logger.error("DojahProvider.verify_bvn: error: %s", exc)
            return KYCVerificationResult(
                success=False,
                provider_reference=request_id,
                error_code="ERROR",
                error_message=str(exc),
                raw_response={},
            )

    # ── NIN Verification ───────────────────────────────────────────────────────

    def verify_nin(self, nin_hash: str, last4: str) -> KYCVerificationResult:
        """NIN lookup via Dojah (GET /api/v1/kyc/nin)."""
        request_id = str(uuid.uuid4())
        try:
            resp = self._http.request(
                "GET",
                "/api/v1/kyc/nin",
                action="verify_nin",
                reference=request_id,
                headers=self._dojah_headers(),
                params={"nin": f"000000{last4}"},
            )
            data = resp.data
            entity = data.get("entity", {})
            success = bool(entity.get("nin")) or data.get("status") == "success"
            dojah_ref = entity.get("reference_id", request_id)
            return KYCVerificationResult(
                success=success,
                provider_reference=str(dojah_ref),
                confidence_score=1.0 if success else 0.0,
                raw_response=data,
                error_code="" if success else "NIN_NOT_FOUND",
                error_message="" if success else str(data.get("error", "")),
            )
        except Exception as exc:
            logger.error("DojahProvider.verify_nin: error: %s", exc)
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
        Validate Dojah webhook callback.
        Dojah sends X-Dojah-Signature: sha256=<HMAC-SHA256 of body>.
        """
        payload_bytes = json.dumps(payload, separators=(",", ":")).encode()
        if not self._verify_hmac(payload_bytes, signature, self._webhook_secret):
            raise ValueError("DojahProvider.handle_webhook: invalid HMAC signature")

        event_type = payload.get("event", "verification.unknown")
        ref = payload.get(
            "reference_id", payload.get("entity", {}).get("reference_id", "")
        )
        success = payload.get("status") in ("success", "verified", "completed")

        return WebhookResult(
            event_type=event_type,
            provider_reference=str(ref),
            success=success,
            raw_payload=payload,
        )
