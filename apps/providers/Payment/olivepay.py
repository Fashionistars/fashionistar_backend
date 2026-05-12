# apps/providers/Payment/olivepay.py
"""
OlivePay Payment Gateway Driver.

OlivePay is a Nigerian fintech payment gateway offering local card, USSD,
bank transfer, QR, and Pay-by-Link checkout options.  This driver follows
the same public API surface as the Paystack and Flutterwave drivers, making
it a drop-in alternative if the active gateway is swapped via admin config.

Credentials (injected via Django settings / .env — never stored in DB):
    OLIVEPAY_API_KEY    = env("OLIVEPAY_API_KEY")
    OLIVEPAY_SECRET_KEY = env("OLIVEPAY_SECRET_KEY")
    OLIVEPAY_BASE_URL   = env("OLIVEPAY_BASE_URL", default="https://api.olivepay.ng/v1")

API Reference:
    OlivePay API documentation is published at https://developers.olivepay.ng
    (credentials required; endpoint paths are provisional pending public release).

Features:
    - Initialize payment checkout session (sync + async).
    - Verify a transaction by reference (sync + async).
    - List supported banks (sync + async).
    - Initiate a bank transfer payout (sync + async).
    - Verify HMAC-SHA256 webhook signature.

Amount Convention:
    All amounts are received as Python ``Decimal`` in NGN (naira) and converted
    internally to kobo (×100, integer) before transmission to the OlivePay API.

Resilience:
    - ``CircuitBreaker(failure_threshold=5)`` — opens after 5 consecutive failures,
      preventing cascade failures when OlivePay is degraded.
    - ``RetryPolicy(max_attempts=2, backoff_seconds=0.5)`` — retries once on
      transient network errors before propagating the exception.

Note:
    OlivePay is a growing Nigerian fintech.  Endpoint paths and payload schemas
    should be verified against the live developer portal before production cutover.
    Coordinate with the OlivePay account manager (AM) for sandbox credentials.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
from decimal import Decimal

from django.conf import settings

from apps.common.http import (
    ProviderAsyncHTTPClient,
    ProviderHTTPError,
    ProviderSyncHTTPClient,
    RetryPolicy,
)
from apps.providers.circuit_breaker import CircuitBreaker

logger = logging.getLogger("application")

_breaker = CircuitBreaker(provider_key="olive_pay", failure_threshold=5)
_RETRY = RetryPolicy(max_attempts=2, backoff_seconds=0.5)
_DEFAULT_BASE_URL = "https://api.olivepay.ng/v1"


class OlivePayClient:
    """
    OlivePay API client with circuit breaker + unified HTTP layer.

    This class is a collection of class methods — it is never instantiated.
    All amounts are expressed in NGN (``Decimal``) and converted to integer
    kobo (NGN × 100) before sending to the API.

    Usage::

        from apps.providers.Payment.olivepay import OlivePayClient

        # Synchronous (DRF views, management commands)
        data = OlivePayClient.initialize_payment(
            email="customer@example.com",
            amount=Decimal("5000.00"),
            reference="ORD-20250509-001",
        )
        checkout_url = data["data"]["checkout_url"]

        # Asynchronous (Django-Ninja views)
        data = await OlivePayClient.ainitialize_payment(
            email="customer@example.com",
            amount=Decimal("5000.00"),
            reference="ORD-20250509-001",
        )
    """

    @staticmethod
    def _api_key() -> str:
        """Return the OlivePay API key from Django settings.

        Returns:
            str: The API key, or an empty string if not configured.
        """
        return getattr(settings, "OLIVEPAY_API_KEY", "")

    @staticmethod
    def _secret() -> str:
        """Return the OlivePay secret key from Django settings.

        Returns:
            str: The secret key, or an empty string if not configured.
        """
        return getattr(settings, "OLIVEPAY_SECRET_KEY", "")

    @staticmethod
    def _base_url() -> str:
        """Return the OlivePay API base URL from settings or the default.

        Returns:
            str: The resolved base URL (no trailing slash).
        """
        return getattr(settings, "OLIVEPAY_BASE_URL", _DEFAULT_BASE_URL)

    @classmethod
    def _headers(cls) -> dict:
        """Build the standard request headers for all OlivePay API calls.

        Returns:
            dict: Authentication and content-type headers.
        """
        return {
            "Authorization": f"Bearer {cls._api_key()}",
            "X-Secret-Key": cls._secret(),
            "Content-Type": "application/json",
        }

    @classmethod
    def _sync(cls) -> ProviderSyncHTTPClient:
        """Return a configured synchronous HTTP client for OlivePay.

        Returns:
            ProviderSyncHTTPClient: Client bound to the OlivePay base URL with retry.
        """
        return ProviderSyncHTTPClient(
            provider="olive_pay",
            base_url=cls._base_url(),
            retry_policy=_RETRY,
        )

    @classmethod
    def _async(cls) -> ProviderAsyncHTTPClient:
        """Return a configured asynchronous HTTP client for OlivePay.

        Returns:
            ProviderAsyncHTTPClient: Async client bound to the OlivePay base URL with retry.
        """
        return ProviderAsyncHTTPClient(
            provider="olive_pay",
            base_url=cls._base_url(),
            retry_policy=_RETRY,
        )

    @staticmethod
    def _kobo(amount: Decimal) -> int:
        """Convert a naira Decimal amount to integer kobo.

        Args:
            amount: The NGN amount to convert (e.g., ``Decimal("500.00")``).

        Returns:
            int: The equivalent amount in kobo (``amount × 100``).
        """
        return int((amount * 100).quantize(Decimal("1")))

    # ── Initialize Payment ─────────────────────────────────────────────────────

    @classmethod
    def initialize_payment(
        cls,
        *,
        email: str,
        amount: Decimal,
        reference: str,
        currency: str = "NGN",
        callback_url: str = "",
        customer_name: str = "",
        customer_phone: str = "",
        metadata: dict | None = None,
    ) -> dict:
        """Initialize an OlivePay Standard checkout session (synchronous).

        Creates a hosted checkout page URL that the customer completes in their
        browser.  Use this from synchronous DRF views or management commands.

        Args:
            email: Customer email address.
            amount: Payment amount in NGN as a ``Decimal``.
            reference: Unique transaction reference (max 100 chars).
            currency: ISO 4217 currency code — defaults to ``"NGN"``.
            callback_url: URL OlivePay redirects to after payment.
                          Falls back to ``settings.OLIVEPAY_CALLBACK_URL``.
            customer_name: Optional display name for the customer.
            customer_phone: Optional customer phone number (``+2348XXXXXXXXX``).
            metadata: Optional dict of extra key-value data stored on the transaction.

        Returns:
            dict: OlivePay response payload.  On success:
                ``{"status": "success", "data": {"checkout_url": "...", "reference": "..."}}``.

        Raises:
            ProviderHTTPError: If the API returns an error or the circuit is open.
        """
        payload = {
            "amount": cls._kobo(amount),
            "currency": currency,
            "reference": reference,
            "email": email,
            "customer_name": customer_name or "",
            "customer_phone": customer_phone or "",
            "callback_url": callback_url or getattr(settings, "OLIVEPAY_CALLBACK_URL", ""),
            "metadata": metadata or {},
        }

        def _call():
            return cls._sync().request(
                "POST",
                "/payments/initialize",
                action="payment.initialize",
                reference=reference,
                headers=cls._headers(),
                json=payload,
            )

        try:
            res = _breaker.call(_call)
        except ProviderHTTPError as exc:
            logger.error("OlivePay.initialize_payment failed ref=%s: %s", reference, exc)
            raise
        return res.data

    @classmethod
    async def ainitialize_payment(
        cls,
        *,
        email: str,
        amount: Decimal,
        reference: str,
        currency: str = "NGN",
        callback_url: str = "",
        customer_name: str = "",
        customer_phone: str = "",
        metadata: dict | None = None,
    ) -> dict:
        """Initialize an OlivePay Standard checkout session (asynchronous).

        Async variant of ``initialize_payment`` for use in Django-Ninja views.

        Args:
            email: Customer email address.
            amount: Payment amount in NGN as a ``Decimal``.
            reference: Unique transaction reference (max 100 chars).
            currency: ISO 4217 currency code — defaults to ``"NGN"``.
            callback_url: URL OlivePay redirects to after payment.
            customer_name: Optional display name for the customer.
            customer_phone: Optional customer phone number.
            metadata: Optional dict of extra key-value data.

        Returns:
            dict: OlivePay response payload (same shape as ``initialize_payment``).

        Raises:
            ProviderHTTPError: If the API returns an error or times out.
        """
        payload = {
            "amount": cls._kobo(amount),
            "currency": currency,
            "reference": reference,
            "email": email,
            "customer_name": customer_name or "",
            "customer_phone": customer_phone or "",
            "callback_url": callback_url or getattr(settings, "OLIVEPAY_CALLBACK_URL", ""),
            "metadata": metadata or {},
        }
        try:
            res = await cls._async().request(
                "POST",
                "/payments/initialize",
                action="payment.initialize",
                reference=reference,
                headers=cls._headers(),
                json=payload,
            )
        except ProviderHTTPError as exc:
            logger.error("OlivePay.ainitialize_payment failed ref=%s: %s", reference, exc)
            raise
        return res.data

    # ── Verify Payment ─────────────────────────────────────────────────────────

    @classmethod
    def verify_payment(cls, reference: str) -> dict:
        """Query the status of a transaction by its reference (synchronous).

        Use this in webhook handlers and order confirmation flows to confirm
        that the customer's payment was actually received before releasing goods.

        Args:
            reference: The unique transaction reference originally passed to
                       ``initialize_payment``.

        Returns:
            dict: OlivePay verification response.  On success the ``status``
                  field inside ``data`` will be ``"successful"``.

        Raises:
            ProviderHTTPError: If the API is unreachable or returns an error.
        """
        def _call():
            return cls._sync().request(
                "GET",
                f"/payments/verify/{reference}",
                action="payment.verify",
                reference=reference,
                headers=cls._headers(),
            )

        try:
            res = _breaker.call(_call)
        except ProviderHTTPError as exc:
            logger.error("OlivePay.verify_payment failed ref=%s: %s", reference, exc)
            raise
        return res.data

    @classmethod
    async def averify_payment(cls, reference: str) -> dict:
        """Query the status of a transaction by its reference (asynchronous).

        Async variant of ``verify_payment`` for Django-Ninja views.

        Args:
            reference: The unique transaction reference.

        Returns:
            dict: OlivePay verification response payload.

        Raises:
            ProviderHTTPError: If the API is unreachable or returns an error.
        """
        try:
            res = await cls._async().request(
                "GET",
                f"/payments/verify/{reference}",
                action="payment.verify",
                reference=reference,
                headers=cls._headers(),
            )
        except ProviderHTTPError as exc:
            logger.error("OlivePay.averify_payment failed ref=%s: %s", reference, exc)
            raise
        return res.data

    # ── List Banks ─────────────────────────────────────────────────────────────

    @classmethod
    def list_banks(cls) -> dict:
        """Return the list of banks supported by OlivePay for transfer payments (sync).

        Returns:
            dict: OlivePay banks list response.

        Raises:
            ProviderHTTPError: If the API is unreachable or the circuit is open.
        """
        def _call():
            return cls._sync().request(
                "GET",
                "/banks",
                action="bank.list",
                headers=cls._headers(),
            )

        try:
            res = _breaker.call(_call)
        except ProviderHTTPError as exc:
            logger.error("OlivePay.list_banks failed: %s", exc)
            raise
        return res.data

    @classmethod
    async def alist_banks(cls) -> dict:
        """Return the list of banks supported by OlivePay (asynchronous).

        Returns:
            dict: OlivePay banks list response.

        Raises:
            ProviderHTTPError: If the API is unreachable or times out.
        """
        try:
            res = await cls._async().request(
                "GET",
                "/banks",
                action="bank.list",
                headers=cls._headers(),
            )
        except ProviderHTTPError as exc:
            logger.error("OlivePay.alist_banks failed: %s", exc)
            raise
        return res.data

    # ── Transfer / Payout ──────────────────────────────────────────────────────

    @classmethod
    def initiate_transfer(
        cls,
        *,
        amount: Decimal,
        reference: str,
        account_number: str,
        bank_code: str,
        account_name: str,
        narration: str = "Fashionistar Payout",
    ) -> dict:
        """Initiate a bank transfer payout to a vendor (synchronous).

        Used in the vendor payout flow when a vendor requests a wallet withdrawal
        to their registered bank account.

        Args:
            amount: Transfer amount in NGN as a ``Decimal``.
            reference: Unique payout reference for idempotency.
            account_number: Recipient NUBAN account number.
            bank_code: Bank code (3–6 digits, from ``list_banks``).
            account_name: Account holder name (pre-validated via name enquiry).
            narration: Transfer description shown on recipient's bank statement.

        Returns:
            dict: OlivePay transfer initiation response.

        Raises:
            ProviderHTTPError: If the payout API returns an error or circuit is open.
        """
        payload = {
            "amount": cls._kobo(amount),
            "reference": reference,
            "account_number": account_number,
            "bank_code": bank_code,
            "account_name": account_name,
            "narration": narration,
        }

        def _call():
            return cls._sync().request(
                "POST",
                "/transfers/initiate",
                action="transfer.initiate",
                reference=reference,
                headers=cls._headers(),
                json=payload,
            )

        try:
            res = _breaker.call(_call)
        except ProviderHTTPError as exc:
            logger.error("OlivePay.initiate_transfer failed ref=%s: %s", reference, exc)
            raise
        return res.data

    @classmethod
    async def ainitiate_transfer(
        cls,
        *,
        amount: Decimal,
        reference: str,
        account_number: str,
        bank_code: str,
        account_name: str,
        narration: str = "Fashionistar Payout",
    ) -> dict:
        """Initiate a bank transfer payout to a vendor (asynchronous).

        Async variant of ``initiate_transfer`` for Django-Ninja views.

        Args:
            amount: Transfer amount in NGN as a ``Decimal``.
            reference: Unique payout reference.
            account_number: Recipient NUBAN account number.
            bank_code: Bank code from ``alist_banks``.
            account_name: Account holder name.
            narration: Bank statement description.

        Returns:
            dict: OlivePay transfer initiation response.

        Raises:
            ProviderHTTPError: If the API returns an error or times out.
        """
        payload = {
            "amount": cls._kobo(amount),
            "reference": reference,
            "account_number": account_number,
            "bank_code": bank_code,
            "account_name": account_name,
            "narration": narration,
        }
        try:
            res = await cls._async().request(
                "POST",
                "/transfers/initiate",
                action="transfer.initiate",
                reference=reference,
                headers=cls._headers(),
                json=payload,
            )
        except ProviderHTTPError as exc:
            logger.error("OlivePay.ainitiate_transfer failed ref=%s: %s", reference, exc)
            raise
        return res.data

    # ── Webhook Signature ──────────────────────────────────────────────────────

    @classmethod
    def verify_signature(cls, raw_payload: bytes, signature: str) -> bool:
        """Verify an OlivePay webhook HMAC-SHA256 signature.

        OlivePay signs each webhook delivery with HMAC-SHA256 of the raw request
        body using the merchant secret key.  The computed digest is sent in the
        ``X-OlivePay-Signature`` HTTP header.

        Args:
            raw_payload: The raw, unmodified request body bytes.
                         Do NOT decode or parse before passing here.
            signature: The value of the ``X-OlivePay-Signature`` request header.

        Returns:
            bool: ``True`` if the computed digest matches the provided signature.
                  ``False`` if the secret is not configured or the digests differ.

        Security:
            Uses ``hmac.compare_digest`` to prevent timing-based attacks.
        """
        secret = cls._secret()
        if not secret:
            logger.warning("OlivePay.verify_signature: OLIVEPAY_SECRET_KEY is not configured.")
            return False
        computed = hmac.new(
            secret.encode("utf-8"), raw_payload, hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(computed, signature or "")
