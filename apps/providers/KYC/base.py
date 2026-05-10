# apps/providers/KYC/base.py
"""
AbstractKYCProvider — Interface contract for all KYC identity verification drivers.

Every KYC provider (Smile Identity, Dojah, Youverify) must implement this interface.
The KycService layer calls only this interface; it never imports a concrete driver directly.
The active driver is resolved at runtime from KYCProviderConfig via the cache layer.

NDPR / CBN compliance:
  - Concrete providers MUST NOT log raw BVN/NIN values.
  - Only hashes + last-four markers + the provider-issued reference ID may be stored.
  - `provider_reference` is the job/session ID used for webhook callback matching.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

logger = logging.getLogger("application")


@dataclass
class KYCVerificationResult:
    """
    Normalized result returned by any KYC provider call.

    Attributes:
        success: True if the provider confirmed the identity.
        provider_reference: External job/session ID (stored in KycSubmission.provider_reference).
        confidence_score: Float 0.0–1.0. Providers that don't supply this return 1.0 on success.
        raw_response: Full provider JSON response (stored in KycDocument.provider_response).
        error_code: Machine-readable provider error code (for logging / circuit breaker).
        error_message: Human-readable failure reason (logged but not shown to end users).
    """
    success: bool
    provider_reference: str = ""
    confidence_score: float = 0.0
    raw_response: dict = field(default_factory=dict)
    error_code: str = ""
    error_message: str = ""


@dataclass
class WebhookResult:
    """Normalized result returned by handle_webhook()."""
    event_type: str          # e.g. "verification.complete", "verification.failed"
    provider_reference: str  # Job/session ID — used to look up KycDocument
    success: bool
    raw_payload: dict = field(default_factory=dict)


class AbstractKYCProvider(ABC):
    """
    Abstract base class for KYC identity verification providers.

    Concrete drivers must implement:
      - verify_bvn()       — validate BVN against provider records
      - verify_nin()       — validate NIN against provider records
      - handle_webhook()   — verify HMAC signature and parse inbound callback
    """

    # Populated by concrete classes
    PROVIDER_SLUG: str = ""
    DEFAULT_BASE_URL: str = ""

    def __init__(self, config: "KYCProviderConfig") -> None:  # noqa: F821
        """
        Args:
            config: The active KYCProviderConfig ORM instance (passed from cache layer).
                    Credentials (api_key, api_secret, webhook_secret) are read from config
                    so no environment variables are needed at the driver level.
        """
        self._config = config
        self._base_url = config.base_url.rstrip("/") if config.base_url else self.DEFAULT_BASE_URL.rstrip("/")

    @abstractmethod
    def verify_bvn(self, bvn_hash: str, last4: str) -> KYCVerificationResult:
        """
        Validate the user's BVN.

        Args:
            bvn_hash: Salted SHA-256 hash of the raw BVN (never the raw number).
            last4: Last four digits of the BVN (used for provider lookup reference).

        Returns:
            KYCVerificationResult with success, provider_reference, and raw_response.
        """
        ...

    @abstractmethod
    def verify_nin(self, nin_hash: str, last4: str) -> KYCVerificationResult:
        """
        Validate the user's NIN.

        Args:
            nin_hash: Salted SHA-256 hash of the raw NIN.
            last4: Last four digits of the NIN.

        Returns:
            KYCVerificationResult
        """
        ...

    @abstractmethod
    def handle_webhook(self, payload: dict, signature: str) -> WebhookResult:
        """
        Validate HMAC signature and parse an inbound provider webhook callback.

        Args:
            payload: Parsed JSON body from the webhook request.
            signature: Value of the provider's signature header (X-Smile-Signature, etc.).

        Returns:
            WebhookResult with event_type, provider_reference, and success flag.

        Raises:
            ValueError: If the HMAC signature is invalid.
        """
        ...

    # ── Shared Utilities ───────────────────────────────────────────────────────

    def _verify_hmac(self, payload_bytes: bytes, signature: str, secret: str) -> bool:
        """
        Verify HMAC-SHA256 signature from provider webhook.
        Constant-time comparison to prevent timing attacks.
        """
        if not secret:
            logger.warning(
                "%s.handle_webhook: webhook_secret is not configured — skipping HMAC verification.",
                self.__class__.__name__,
            )
            return True  # Allow in sandbox; reject in production via sandbox_mode check

        expected = hmac.new(
            secret.encode(),
            payload_bytes,
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(expected, signature.lower().replace("sha256=", ""))

    def _sandbox_mode(self) -> bool:
        return self._config.sandbox_mode
