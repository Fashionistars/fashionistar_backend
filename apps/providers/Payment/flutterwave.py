# apps/providers/Payment/flutterwave.py
"""
Flutterwave payment provider driver.

Credentials (in .env / Django settings):
    FLUTTERWAVE_SECRET_KEY  = env("FLUTTERWAVE_SECRET_KEY")
    FLUTTERWAVE_PUBLIC_KEY  = env("FLUTTERWAVE_PUBLIC_KEY")
    FLUTTERWAVE_ENCRYPT_KEY = env("FLUTTERWAVE_ENCRYPT_KEY")  # 3DES encrypt key

Features:
  • Initialize payment (Standard Checkout redirect — sync + async)
  • Verify transaction by ID or tx_ref (sync + async)
  • List Nigerian banks (sync + async)
  • Create transfer / payout (sync + async)
  • Verify webhook signature (HMAC-SHA256 over request body + secret hash header)
"""
from __future__ import annotations

import hmac
import logging
import secrets
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

_breaker = CircuitBreaker(provider_key="flutterwave", failure_threshold=5)
_RETRY = RetryPolicy(max_attempts=2, backoff_seconds=0.5)
_BASE_URL = "https://api.flutterwave.com/v3"


class FlutterwaveClient:
    """
    Flutterwave v3 API client with circuit breaker + unified HTTP layer.
    Amounts always in NGN (or specified currency). The API uses full units — no kobo conversion.
    """

    @staticmethod
    def _secret() -> str:
        return getattr(settings, "FLUTTERWAVE_SECRET_KEY", "")

    @staticmethod
    def _secret_hash() -> str:
        """The Flutterwave webhook secret hash set on the dashboard."""
        return getattr(settings, "FLUTTERWAVE_WEBHOOK_SECRET_HASH", "")

    @classmethod
    def _headers(cls) -> dict:
        return {
            "Authorization": f"Bearer {cls._secret()}",
            "Content-Type": "application/json",
        }

    @classmethod
    def _sync(cls) -> ProviderSyncHTTPClient:
        return ProviderSyncHTTPClient(provider="flutterwave", base_url=_BASE_URL, retry_policy=_RETRY)

    @classmethod
    def _async(cls) -> ProviderAsyncHTTPClient:
        return ProviderAsyncHTTPClient(provider="flutterwave", base_url=_BASE_URL, retry_policy=_RETRY)

    # ── Initialize Payment ────────────────────────────────────────────────────

    @classmethod
    def initialize_payment(
        cls,
        *,
        email: str,
        amount: Decimal,
        tx_ref: str,
        currency: str = "NGN",
        redirect_url: str = "",
        customer_name: str = "",
        customer_phone: str = "",
        meta: dict | None = None,
    ) -> dict:
        """
        Create a Flutterwave Standard Checkout payment link.
        Returns ``{"status": "success", "data": {"link": "https://..."}}``
        """
        payload = {
            "tx_ref": tx_ref,
            "amount": str(amount),
            "currency": currency,
            "redirect_url": redirect_url or getattr(settings, "FLUTTERWAVE_REDIRECT_URL", ""),
            "customer": {
                "email": email,
                "name": customer_name or email.split("@")[0],
                "phonenumber": customer_phone,
            },
            "meta": meta or {},
            "customizations": {
                "title": "Fashionistar",
                "logo": getattr(settings, "FLUTTERWAVE_LOGO_URL", ""),
            },
        }

        def _call():
            return cls._sync().request(
                "POST",
                "/payments",
                action="payment.initialize",
                reference=tx_ref,
                headers=cls._headers(),
                json=payload,
            )

        try:
            res = _breaker.call(_call)
        except ProviderHTTPError as exc:
            logger.error("Flutterwave.initialize_payment failed tx_ref=%s: %s", tx_ref, exc)
            raise
        return res.data

    @classmethod
    async def ainitialize_payment(cls, *, email: str, amount: Decimal, tx_ref: str, currency: str = "NGN", redirect_url: str = "", customer_name: str = "", customer_phone: str = "", meta: dict | None = None) -> dict:
        payload = {
            "tx_ref": tx_ref,
            "amount": str(amount),
            "currency": currency,
            "redirect_url": redirect_url or getattr(settings, "FLUTTERWAVE_REDIRECT_URL", ""),
            "customer": {"email": email, "name": customer_name or email.split("@")[0], "phonenumber": customer_phone},
            "meta": meta or {},
            "customizations": {"title": "Fashionistar", "logo": getattr(settings, "FLUTTERWAVE_LOGO_URL", "")},
        }
        try:
            res = await cls._async().request("POST", "/payments", action="payment.initialize", reference=tx_ref, headers=cls._headers(), json=payload)
        except ProviderHTTPError as exc:
            logger.error("Flutterwave.ainitialize_payment failed: %s", exc)
            raise
        return res.data

    # ── Verify Transaction ────────────────────────────────────────────────────

    @classmethod
    def verify_transaction(cls, transaction_id: int | str) -> dict:
        """Verify a Flutterwave transaction by its internal numeric ID (synchronous).

        Use the transaction ID returned by the ``/payments/verify/{tx_ref}`` webhook
        or the Flutterwave redirect callback to confirm payment before releasing goods.

        Args:
            transaction_id: Flutterwave's internal transaction integer ID
                            (NOT the merchant's ``tx_ref``).

        Returns:
            dict: Flutterwave verification response. On success:
                ``{"status": "success", "data": {"status": "successful", ...}}``.

        Raises:
            ProviderHTTPError: If the API is unreachable or the circuit is open.
        """
        def _call():
            return cls._sync().request(
                "GET",
                f"/transactions/{transaction_id}/verify",
                action="transaction.verify",
                reference=str(transaction_id),
                headers=cls._headers(),
            )
        try:
            res = _breaker.call(_call)
        except ProviderHTTPError as exc:
            logger.error("Flutterwave.verify_transaction failed id=%s: %s", transaction_id, exc)
            raise
        return res.data

    @classmethod
    async def averify_transaction(cls, transaction_id: int | str) -> dict:
        """Verify a Flutterwave transaction by its internal numeric ID (asynchronous).

        Async variant of ``verify_transaction`` for Django-Ninja views.

        Args:
            transaction_id: Flutterwave's internal transaction integer ID.

        Returns:
            dict: Flutterwave verification response.

        Raises:
            ProviderHTTPError: If the API is unreachable or times out.
        """
        try:
            res = await cls._async().request(
                "GET",
                f"/transactions/{transaction_id}/verify",
                action="transaction.verify",
                reference=str(transaction_id),
                headers=cls._headers(),
            )
        except ProviderHTTPError as exc:
            logger.error("Flutterwave.averify_transaction failed id=%s: %s", transaction_id, exc)
            raise
        return res.data

    # ── List Banks ────────────────────────────────────────────────────────────

    @classmethod
    def list_banks(cls, country: str = "NG") -> dict:
        def _call():
            return cls._sync().request("GET", f"/banks/{country}", action="bank.list", headers=cls._headers())
        try:
            res = _breaker.call(_call)
        except ProviderHTTPError:
            raise
        return res.data

    @classmethod
    async def alist_banks(cls, country: str = "NG") -> dict:
        try:
            res = await cls._async().request("GET", f"/banks/{country}", action="bank.list", headers=cls._headers())
        except ProviderHTTPError:
            raise
        return res.data

    # ── Transfer / Payout ─────────────────────────────────────────────────────

    @classmethod
    def initiate_transfer(
        cls,
        *,
        account_number: str,
        account_bank: str,
        amount: Decimal,
        narration: str = "Fashionistar Payout",
        reference: str = "",
        currency: str = "NGN",
    ) -> dict:
        """Create a bank transfer payout to a vendor's bank account (synchronous).

        Flutterwave does **not** require a pre-registered recipient — the bank
        account details are passed directly in the transfer payload.  This is
        a single-step payout flow, unlike Paystack's two-step create-then-transfer.

        Args:
            account_number: Recipient NUBAN account number (10 digits).
            account_bank: Flutterwave bank code (from ``list_banks``).
            amount: Transfer amount in the specified currency (NGN by default).
                    Flutterwave uses full naira units — **not** kobo.
            narration: Transfer description shown on recipient's bank statement.
            reference: Unique payout reference.  A random hex reference is
                       generated if not supplied (not recommended for idempotency).
            currency: ISO 4217 currency code, defaults to ``"NGN"``.

        Returns:
            dict: Flutterwave transfer response. On success:
                ``{"status": "success", "data": {"id": ..., "status": "NEW"|"PENDING"}}``.

        Raises:
            ProviderHTTPError: If the API returns an error or the circuit is open.
        """
        effective_ref = reference or f"FLW-TRF-{secrets.token_hex(8)}"
        payload = {
            "account_bank": account_bank,
            "account_number": account_number,
            "amount": str(amount),
            "narration": narration,
            "currency": currency,
            "reference": effective_ref,
        }

        def _call():
            return cls._sync().request(
                "POST",
                "/transfers",
                action="transfer.initiate",
                reference=effective_ref,
                headers=cls._headers(),
                json=payload,
            )

        try:
            res = _breaker.call(_call)
        except ProviderHTTPError as exc:
            logger.error("Flutterwave.initiate_transfer failed ref=%s: %s", effective_ref, exc)
            raise
        return res.data

    @classmethod
    async def ainitiate_transfer(
        cls,
        *,
        account_number: str,
        account_bank: str,
        amount: Decimal,
        narration: str = "Fashionistar Payout",
        reference: str = "",
        currency: str = "NGN",
    ) -> dict:
        """Create a bank transfer payout to a vendor's bank account (asynchronous).

        Async variant of ``initiate_transfer`` for use in Django-Ninja views and
        background task handlers.  Flutterwave payout is a **single-step** flow
        (unlike Paystack's two-step create-recipient → transfer pattern).

        Args:
            account_number: Recipient NUBAN account number.
            account_bank: Flutterwave bank code (from ``alist_banks``).
            amount: Transfer amount in full naira units (NOT kobo).
            narration: Bank statement description.
            reference: Unique payout reference (auto-generated if empty).
            currency: ISO 4217 currency code.

        Returns:
            dict: Flutterwave transfer response.

        Raises:
            ProviderHTTPError: If the API returns an error or times out.
        """
        effective_ref = reference or f"FLW-TRF-{secrets.token_hex(8)}"
        payload = {
            "account_bank": account_bank,
            "account_number": account_number,
            "amount": str(amount),
            "narration": narration,
            "currency": currency,
            "reference": effective_ref,
        }
        try:
            res = await cls._async().request(
                "POST",
                "/transfers",
                action="transfer.initiate",
                reference=effective_ref,
                headers=cls._headers(),
                json=payload,
            )
        except ProviderHTTPError as exc:
            logger.error("Flutterwave.ainitiate_transfer failed ref=%s: %s", effective_ref, exc)
            raise
        return res.data

    # ── Webhook Signature ─────────────────────────────────────────────────────

    @classmethod
    def verify_signature(cls, verif_hash_header: str) -> bool:
        """
        Verify Flutterwave webhook by comparing the `verif-hash` header
        against the FLUTTERWAVE_WEBHOOK_SECRET_HASH env variable.
        """
        secret = cls._secret_hash()
        if not secret:
            return False
        return hmac.compare_digest(verif_hash_header or "", secret)
