# apps/providers/Payment/paystack.py
"""
Paystack payment provider — canonical registry implementation.

This is the single source of truth for all Paystack HTTP operations.
apps/payment/services.py should import PaystackClient from here.

Credentials:
    PAYSTACK_SECRET_KEY = env("PAYSTACK_SECRET_KEY")
    PAYSTACK_PUBLIC_KEY = env("PAYSTACK_PUBLIC_KEY")

Features covered:
  • Initialize transaction (sync + async)
  • Verify payment (sync + async)
  • List banks (sync + async)
  • Create transfer recipient (sync + async)
  • Initiate transfer (sync + async)
  • Verify webhook signature (HMAC-SHA512)
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

_breaker = CircuitBreaker(provider_key="paystack", failure_threshold=5)

_RETRY = RetryPolicy(max_attempts=2, backoff_seconds=0.5)
_BASE_URL = "https://api.paystack.co"


class PaystackClient:
    """
    Full Paystack API client with circuit breaker + shared HTTP layer.
    All kobo conversion is internal — callers always pass NGN Decimal amounts.
    """

    @staticmethod
    def _secret() -> str:
        return getattr(settings, "PAYSTACK_SECRET_KEY", "")

    @classmethod
    def _headers(cls, *, idempotency_key: str = "") -> dict:
        h = {
            "Authorization": f"Bearer {cls._secret()}",
            "Content-Type": "application/json",
        }
        if idempotency_key:
            h["Idempotency-Key"] = idempotency_key
        return h

    @staticmethod
    def _kobo(amount: Decimal) -> int:
        return int((amount * 100).quantize(Decimal("1")))

    @classmethod
    def _sync(cls) -> ProviderSyncHTTPClient:
        return ProviderSyncHTTPClient(provider="paystack", base_url=_BASE_URL, retry_policy=_RETRY)

    @classmethod
    def _async(cls) -> ProviderAsyncHTTPClient:
        return ProviderAsyncHTTPClient(provider="paystack", base_url=_BASE_URL, retry_policy=_RETRY)

    # ── Initialize Transaction ────────────────────────────────────────────────

    @classmethod
    def initialize_transaction(cls, *, email: str, amount: Decimal, reference: str, currency: str = "NGN", metadata: dict | None = None, idempotency_key: str = "") -> dict:
        payload = {
            "email": email,
            "amount": cls._kobo(amount),
            "reference": reference,
            "currency": currency,
            "channels": ["bank", "card", "ussd", "mobile_money", "bank_transfer", "qr"],
            "metadata": metadata or {},
        }
        def _call():
            return cls._sync().request("POST", "/transaction/initialize", action="transaction.initialize", reference=reference, idempotency_key=idempotency_key, headers=cls._headers(idempotency_key=idempotency_key), json=payload)
        try:
            res = _breaker.call(_call)
        except ProviderHTTPError as exc:
            logger.error("Paystack.initialize_transaction failed: %s", exc)
            raise
        return res.data

    @classmethod
    async def ainitialize_transaction(cls, *, email: str, amount: Decimal, reference: str, currency: str = "NGN", metadata: dict | None = None, idempotency_key: str = "") -> dict:
        payload = {
            "email": email,
            "amount": cls._kobo(amount),
            "reference": reference,
            "currency": currency,
            "channels": ["bank", "card", "ussd", "mobile_money", "bank_transfer", "qr"],
            "metadata": metadata or {},
        }
        try:
            res = await cls._async().request("POST", "/transaction/initialize", action="transaction.initialize", reference=reference, idempotency_key=idempotency_key, headers=cls._headers(idempotency_key=idempotency_key), json=payload)
        except ProviderHTTPError as exc:
            logger.error("Paystack.ainitialize_transaction failed: %s", exc)
            raise
        return res.data

    # ── Verify Payment ────────────────────────────────────────────────────────

    @classmethod
    def verify_payment(cls, reference: str) -> dict:
        def _call():
            return cls._sync().request("GET", f"/transaction/verify/{reference}", action="transaction.verify", reference=reference, headers=cls._headers())
        try:
            res = _breaker.call(_call)
        except ProviderHTTPError as exc:
            logger.error("Paystack.verify_payment failed ref=%s: %s", reference, exc)
            raise
        return res.data

    @classmethod
    async def averify_payment(cls, reference: str) -> dict:
        try:
            res = await cls._async().request("GET", f"/transaction/verify/{reference}", action="transaction.verify", reference=reference, headers=cls._headers())
        except ProviderHTTPError as exc:
            logger.error("Paystack.averify_payment failed: %s", exc)
            raise
        return res.data

    # ── Banks & Transfer Recipients ───────────────────────────────────────────

    @classmethod
    def list_banks(cls, *, country: str = "NG", pay_with_bank_transfer: bool = True) -> dict:
        """Return a list of Nigerian banks supported by Paystack (synchronous).

        Args:
            country: ISO 3166-1 alpha-2 country code. Defaults to ``"NG"``.
            pay_with_bank_transfer: Filter to banks that support pay-with-bank-transfer.

        Returns:
            dict: Paystack bank list response.

        Raises:
            ProviderHTTPError: If the API is unreachable or the circuit is open.
        """
        def _call():
            return cls._sync().request(
                "GET",
                "/bank",
                action="bank.list",
                headers=cls._headers(),
                params={"country": country, "pay_with_bank_transfer": str(pay_with_bank_transfer).lower()},
            )
        try:
            res = _breaker.call(_call)
        except ProviderHTTPError as exc:
            logger.error("Paystack.list_banks failed: %s", exc)
            raise
        return res.data

    @classmethod
    async def alist_banks(cls, *, country: str = "NG", pay_with_bank_transfer: bool = True) -> dict:
        """Return a list of Nigerian banks supported by Paystack (asynchronous).

        Args:
            country: ISO 3166-1 alpha-2 country code. Defaults to ``"NG"``.
            pay_with_bank_transfer: Filter to banks that support pay-with-bank-transfer.

        Returns:
            dict: Paystack bank list response.

        Raises:
            ProviderHTTPError: If the API is unreachable or times out.
        """
        try:
            res = await cls._async().request(
                "GET",
                "/bank",
                action="bank.list",
                headers=cls._headers(),
                params={"country": country, "pay_with_bank_transfer": str(pay_with_bank_transfer).lower()},
            )
        except ProviderHTTPError as exc:
            logger.error("Paystack.alist_banks failed: %s", exc)
            raise
        return res.data

    @classmethod
    def create_transfer_recipient(
        cls,
        *,
        name: str,
        account_number: str,
        bank_code: str,
        currency: str = "NGN",
        idempotency_key: str = "",
    ) -> dict:
        """Register a bank account as a Paystack transfer recipient (synchronous).

        Must be called before ``initiate_transfer`` — the ``recipient_code`` returned
        here is the value passed to ``initiate_transfer``.

        Args:
            name: Account holder's full name (must match bank records).
            account_number: NUBAN account number (10 digits).
            bank_code: Paystack bank code (from ``list_banks``).
            currency: ISO 4217 currency code, defaults to ``"NGN"``.
            idempotency_key: Optional key to prevent duplicate recipient creation.

        Returns:
            dict: Paystack response containing ``recipient_code``.

        Raises:
            ProviderHTTPError: If the API is unreachable or returns an error.
        """
        payload = {
            "type": "nuban",
            "name": name,
            "account_number": account_number,
            "bank_code": bank_code,
            "currency": currency,
        }
        def _call():
            return cls._sync().request(
                "POST",
                "/transferrecipient",
                action="transferrecipient.create",
                idempotency_key=idempotency_key,
                headers=cls._headers(idempotency_key=idempotency_key),
                json=payload,
            )
        try:
            res = _breaker.call(_call)
        except ProviderHTTPError as exc:
            logger.error("Paystack.create_transfer_recipient failed acct=%s bank=%s: %s", account_number, bank_code, exc)
            raise
        return res.data

    @classmethod
    async def acreate_transfer_recipient(
        cls,
        *,
        name: str,
        account_number: str,
        bank_code: str,
        currency: str = "NGN",
        idempotency_key: str = "",
    ) -> dict:
        """Register a bank account as a Paystack transfer recipient (asynchronous).

        Async variant of ``create_transfer_recipient`` for Django-Ninja views.

        Args:
            name: Account holder's full name.
            account_number: NUBAN account number.
            bank_code: Paystack bank code.
            currency: ISO 4217 currency code.
            idempotency_key: Optional idempotency key.

        Returns:
            dict: Paystack response containing ``recipient_code``.

        Raises:
            ProviderHTTPError: If the API is unreachable or returns an error.
        """
        payload = {
            "type": "nuban",
            "name": name,
            "account_number": account_number,
            "bank_code": bank_code,
            "currency": currency,
        }
        try:
            res = await cls._async().request(
                "POST",
                "/transferrecipient",
                action="transferrecipient.create",
                idempotency_key=idempotency_key,
                headers=cls._headers(idempotency_key=idempotency_key),
                json=payload,
            )
        except ProviderHTTPError as exc:
            logger.error("Paystack.acreate_transfer_recipient failed acct=%s bank=%s: %s", account_number, bank_code, exc)
            raise
        return res.data

    # ── Initiate Transfer (Payout) ────────────────────────────────────────────

    @classmethod
    def initiate_transfer(
        cls,
        *,
        recipient_code: str,
        amount: Decimal,
        reference: str,
        reason: str = "Fashionistar Payout",
        idempotency_key: str = "",
    ) -> dict:
        """Initiate a bank transfer payout to a registered recipient (synchronous).

        Paystack payout is a **two-step flow**:

        1. ``create_transfer_recipient()`` — register the beneficiary's bank account
           and obtain a ``recipient_code``.
        2. ``initiate_transfer()`` — trigger the money movement using the
           ``recipient_code`` from step 1.

        Both steps are idempotent when an ``idempotency_key`` is supplied.
        Use this from synchronous DRF views or management commands.

        Args:
            recipient_code: The ``recipient_code`` from ``create_transfer_recipient``
                            (format: ``RCP_xxxxxxxxxxxxxxxx``).
            amount: Transfer amount in NGN as a ``Decimal``.
            reference: Unique payout reference for idempotency (max 100 chars).
            reason: Transfer description shown on recipient's bank statement.
            idempotency_key: Optional key to prevent duplicate transfers.

        Returns:
            dict: Paystack transfer initiation response.  On success:
                ``{"status": True, "data": {"transfer_code": "TRF_xxx", "status": "otp"|"pending"}}``.

        Raises:
            ProviderHTTPError: If the API returns an error or the circuit is open.
        """
        payload = {
            "source": "balance",
            "reason": reason,
            "amount": cls._kobo(amount),
            "recipient": recipient_code,
            "reference": reference,
        }

        def _call():
            return cls._sync().request(
                "POST",
                "/transfer",
                action="transfer.initiate",
                reference=reference,
                idempotency_key=idempotency_key,
                headers=cls._headers(idempotency_key=idempotency_key),
                json=payload,
            )

        try:
            res = _breaker.call(_call)
        except ProviderHTTPError as exc:
            logger.error("Paystack.initiate_transfer failed ref=%s: %s", reference, exc)
            raise
        return res.data

    @classmethod
    async def ainitiate_transfer(
        cls,
        *,
        recipient_code: str,
        amount: Decimal,
        reference: str,
        reason: str = "Fashionistar Payout",
        idempotency_key: str = "",
    ) -> dict:
        """Initiate a bank transfer payout to a registered recipient (asynchronous).

        Async variant of ``initiate_transfer`` for use in Django-Ninja views and
        background task handlers.  The same two-step flow applies:

        1. ``acreate_transfer_recipient()`` → get ``recipient_code``.
        2. ``ainitiate_transfer()`` → trigger payout.

        Args:
            recipient_code: The ``recipient_code`` from ``acreate_transfer_recipient``.
            amount: Transfer amount in NGN as a ``Decimal``.
            reference: Unique payout reference for idempotency.
            reason: Bank statement description.
            idempotency_key: Optional idempotency key.

        Returns:
            dict: Paystack transfer initiation response.

        Raises:
            ProviderHTTPError: If the API returns an error or times out.
        """
        payload = {
            "source": "balance",
            "reason": reason,
            "amount": cls._kobo(amount),
            "recipient": recipient_code,
            "reference": reference,
        }
        try:
            res = await cls._async().request(
                "POST",
                "/transfer",
                action="transfer.initiate",
                reference=reference,
                idempotency_key=idempotency_key,
                headers=cls._headers(idempotency_key=idempotency_key),
                json=payload,
            )
        except ProviderHTTPError as exc:
            logger.error("Paystack.ainitiate_transfer failed ref=%s: %s", reference, exc)
            raise
        return res.data

    # ── Webhook Verification ──────────────────────────────────────────────────

    @classmethod
    def verify_signature(cls, raw_payload: bytes, signature: str) -> bool:
        """Verify a Paystack webhook HMAC-SHA512 signature.

        Paystack signs each webhook delivery with HMAC-SHA512 using the merchant
        secret key.  The digest is sent in the ``X-Paystack-Signature`` HTTP header.

        Args:
            raw_payload: Raw, unmodified request body bytes (do NOT decode first).
            signature: Value of the ``X-Paystack-Signature`` request header.

        Returns:
            bool: ``True`` if the digest matches; ``False`` otherwise.

        Security:
            Uses ``hmac.compare_digest`` to prevent timing attacks.
        """
        secret = cls._secret()
        if not secret:
            logger.warning("Paystack.verify_signature: PAYSTACK_SECRET_KEY is not configured.")
            return False
        digest = hmac.new(secret.encode("utf-8"), raw_payload, hashlib.sha512).hexdigest()
        return hmac.compare_digest(digest, signature or "")
