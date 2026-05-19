# apps/payment/orchestrator.py
"""
PaymentOrchestrator — Unified Runtime Payment Gateway Selector.

Architecture
────────────
At Fashionistar, the active payment gateway is **admin-switchable** via the
``PaymentProvider`` singleton (``apps.payment.models``).  No code change or
redeployment is required to swap providers — a superuser selects the provider
in the Django admin and the next request picks it up via cache.

Gateway Support Matrix
──────────────────────
| Feature                   | Paystack   | Flutterwave | OlivePay  |
|---------------------------|------------|-------------|-----------|
| Initialize payment        | ✓          | ✓           | ✓         |
| Verify payment            | ✓          | ✓           | ✓         |
| List banks                | ✓          | ✓           | ✓         |
| Initiate transfer (payout)| ✓ (2-step) | ✓ (1-step)  | ✓ (1-step)|
| Webhook HMAC verify       | SHA-512    | verif-hash  | SHA-256   |
| Amount unit               | Kobo       | Full naira  | Kobo      |

Usage (DRF sync views)
────────────────────────
    orchestrator = PaymentOrchestrator.for_provider(PaymentProviderCode.PAYSTACK)
    data = orchestrator.initialize_payment(
        email="user@example.com",
        amount=Decimal("5000.00"),
        reference="PAY-REF-001",
    )
    checkout_url = data.get("data", {}).get("authorization_url") or data.get("data", {}).get("checkout_url")

Usage (Ninja async views)
────────────────────────
    orchestrator = PaymentOrchestrator.for_provider(active_provider_code)
    data = await orchestrator.ainitialize_payment(...)
"""
from __future__ import annotations

import logging
import secrets
from decimal import Decimal
from typing import Any, Optional

from django.core.cache import cache

from apps.common.http import ProviderHTTPError
from apps.providers.Payment.flutterwave import FlutterwaveClient
from apps.providers.Payment.olivepay import OlivePayClient
from apps.providers.Payment.paystack import PaystackClient

logger = logging.getLogger("application")

_ACTIVE_GATEWAY_CACHE_KEY = "payment:active_gateway_code"
_ACTIVE_GATEWAY_TTL = 300  # 5 minutes


# ─────────────────────────────────────────────────────────────────────────────
# Gateway Resolution
# ─────────────────────────────────────────────────────────────────────────────

def get_active_gateway_code() -> str:
    """
    Return the active payment provider code from cache → DB → default.

    Cache TTL is 5 minutes.  Admin saves bust the cache via the post_save
    signal on ``PaymentProvider`` (wired in ``apps.payment.signals``).

    Returns:
        str: Payment provider code (e.g. ``"paystack"``, ``"flutterwave"``,
             ``"olive_pay"``).
    """
    code = cache.get(_ACTIVE_GATEWAY_CACHE_KEY)
    if code:
        return code

    try:
        from apps.payment.models import PaymentProvider
        provider = PaymentProvider.objects.filter(is_active=True).order_by("id").first()
        if provider:
            code = provider.code
            cache.set(_ACTIVE_GATEWAY_CACHE_KEY, code, _ACTIVE_GATEWAY_TTL)
            return code
    except Exception as exc:
        logger.warning("PaymentOrchestrator: DB gateway lookup failed — %s", exc)

    # Hard fallback: Paystack is the default production gateway
    return "paystack"


def bust_gateway_cache() -> None:
    """Bust the active gateway code cache (called by PaymentProvider post_save signal)."""
    cache.delete(_ACTIVE_GATEWAY_CACHE_KEY)
    logger.info("PaymentOrchestrator: active gateway cache cleared.")


# ─────────────────────────────────────────────────────────────────────────────
# PaymentOrchestrator
# ─────────────────────────────────────────────────────────────────────────────

class PaymentOrchestrator:
    """
    Unified payment interface that delegates to the active gateway driver.

    This class is **never** instantiated directly — use the class methods
    ``for_provider()`` or ``from_active_config()`` as factory methods.

    Thread-safety:
        All state is resolved per-call from the immutable ``_provider_code``
        attribute.  Instances are stateless beyond that.
    """

    def __init__(self, provider_code: str) -> None:
        self._provider_code = provider_code

    # ── Factory Methods ────────────────────────────────────────────────────────

    @classmethod
    def for_provider(cls, provider_code: str) -> "PaymentOrchestrator":
        """
        Create an orchestrator pinned to a specific provider.

        Args:
            provider_code: One of ``"paystack"``, ``"flutterwave"``, ``"olive_pay"``.

        Returns:
            PaymentOrchestrator: Configured instance.
        """
        return cls(provider_code)

    @classmethod
    def from_active_config(cls) -> "PaymentOrchestrator":
        """
        Create an orchestrator using the admin-configured active gateway.

        Reads from the ``PaymentProvider`` DB singleton (with Redis cache).
        Falls back to Paystack if no active provider is configured.

        Returns:
            PaymentOrchestrator: Configured instance targeting the live gateway.
        """
        return cls(get_active_gateway_code())

    # ── Internal Driver Resolution ─────────────────────────────────────────────

    @property
    def _is_paystack(self) -> bool:
        return self._provider_code == "paystack"

    @property
    def _is_flutterwave(self) -> bool:
        return self._provider_code == "flutterwave"

    @property
    def _is_olivepay(self) -> bool:
        return self._provider_code in ("olive_pay", "olivepay")

    # ── Reference Generation ───────────────────────────────────────────────────

    @staticmethod
    def make_reference(prefix: str = "FSPAY") -> str:
        """
        Generate a cryptographically secure, URL-safe payment reference.

        Args:
            prefix: Short prefix string (max 20 chars).

        Returns:
            str: Payment reference (e.g. ``"FSPAY_AbCdEfGhIjKlMnOpQrSt"``).
        """
        return f"{prefix}_{secrets.token_urlsafe(24)}"

    # ── Initialize Payment (sync) ─────────────────────────────────────────────

    def initialize_payment(
        self,
        *,
        email: str,
        amount: Decimal,
        reference: str,
        currency: str = "NGN",
        callback_url: str = "",
        redirect_url: str = "",
        customer_name: str = "",
        customer_phone: str = "",
        metadata: Optional[dict] = None,
    ) -> dict[str, Any]:
        """
        Initialize a checkout session on the active payment gateway (synchronous).

        Normalizes the call signature across Paystack, Flutterwave, and OlivePay
        into a single unified interface.  Callers should extract the checkout URL
        from ``data.authorization_url`` (Paystack) or ``data.link`` (Flutterwave)
        or ``data.checkout_url`` (OlivePay).

        Args:
            email: Customer email address.
            amount: Payment amount in NGN (full naira, not kobo).  Conversion
                    to kobo is handled internally by each gateway driver.
            reference: Unique transaction reference for idempotency (max 100 chars).
            currency: ISO 4217 code.  Defaults to ``"NGN"``.
            callback_url: Redirect URL after payment (OlivePay / Paystack metadata).
            redirect_url: Redirect URL after payment (Flutterwave).
            customer_name: Optional display name.
            customer_phone: Optional phone in ``+2348XXXXXXXXX`` format.
            metadata: Optional dict of extra key-value data.

        Returns:
            dict: Raw gateway response.  Shape varies per gateway:
                - Paystack:     ``{"status": True, "data": {"authorization_url": ...}}``
                - Flutterwave:  ``{"status": "success", "data": {"link": ...}}``
                - OlivePay:     ``{"status": "success", "data": {"checkout_url": ...}}``

        Raises:
            ProviderHTTPError: If the gateway returns an error or is unreachable.
            NotImplementedError: If an unsupported provider code is configured.
        """
        if self._is_paystack:
            return PaystackClient.initialize_transaction(
                email=email,
                amount=amount,
                reference=reference,
                currency=currency,
                callback_url=callback_url,
                metadata={
                    "callback_url": callback_url,
                    "customer_name": customer_name,
                    "customer_phone": customer_phone,
                    **(metadata or {}),
                },
            )
        elif self._is_flutterwave:
            return FlutterwaveClient.initialize_payment(
                email=email,
                amount=amount,
                tx_ref=reference,
                currency=currency,
                redirect_url=redirect_url or callback_url,
                customer_name=customer_name,
                customer_phone=customer_phone,
                meta=metadata,
            )
        elif self._is_olivepay:
            return OlivePayClient.initialize_payment(
                email=email,
                amount=amount,
                reference=reference,
                currency=currency,
                callback_url=callback_url or redirect_url,
                customer_name=customer_name,
                customer_phone=customer_phone,
                metadata=metadata,
            )
        else:
            raise NotImplementedError(
                f"PaymentOrchestrator: provider '{self._provider_code}' is not supported. "
                "Supported: paystack, flutterwave, olive_pay."
            )

    # ── Initialize Payment (async) ─────────────────────────────────────────────

    async def ainitialize_payment(
        self,
        *,
        email: str,
        amount: Decimal,
        reference: str,
        currency: str = "NGN",
        callback_url: str = "",
        redirect_url: str = "",
        customer_name: str = "",
        customer_phone: str = "",
        metadata: Optional[dict] = None,
    ) -> dict[str, Any]:
        """
        Initialize a checkout session on the active payment gateway (asynchronous).

        Async variant of ``initialize_payment`` for Django-Ninja views.
        Same argument/return contract as the sync variant.

        Raises:
            ProviderHTTPError: If the gateway returns an error or times out.
            NotImplementedError: If an unsupported provider code is configured.
        """
        if self._is_paystack:
            return await PaystackClient.ainitialize_transaction(
                email=email,
                amount=amount,
                reference=reference,
                currency=currency,
                callback_url=callback_url,
                metadata={
                    "callback_url": callback_url,
                    "customer_name": customer_name,
                    "customer_phone": customer_phone,
                    **(metadata or {}),
                },
            )
        elif self._is_flutterwave:
            return await FlutterwaveClient.ainitialize_payment(
                email=email,
                amount=amount,
                tx_ref=reference,
                currency=currency,
                redirect_url=redirect_url or callback_url,
                customer_name=customer_name,
                customer_phone=customer_phone,
                meta=metadata,
            )
        elif self._is_olivepay:
            return await OlivePayClient.ainitialize_payment(
                email=email,
                amount=amount,
                reference=reference,
                currency=currency,
                callback_url=callback_url or redirect_url,
                customer_name=customer_name,
                customer_phone=customer_phone,
                metadata=metadata,
            )
        else:
            raise NotImplementedError(
                f"PaymentOrchestrator: provider '{self._provider_code}' is not supported."
            )

    # ── Verify Payment (sync) ──────────────────────────────────────────────────

    def verify_payment(self, reference: str) -> dict[str, Any]:
        """
        Verify a transaction by reference / ID (synchronous).

        Args:
            reference: Merchant reference (all gateways) or Flutterwave transaction ID.

        Returns:
            dict: Raw gateway verification response.

        Raises:
            ProviderHTTPError: If the gateway returns an error or is unreachable.
        """
        if self._is_paystack:
            return PaystackClient.verify_payment(reference)
        elif self._is_flutterwave:
            return FlutterwaveClient.verify_transaction(reference)
        elif self._is_olivepay:
            return OlivePayClient.verify_payment(reference)
        else:
            raise NotImplementedError(f"Provider '{self._provider_code}' not supported.")

    async def averify_payment(self, reference: str) -> dict[str, Any]:
        """
        Verify a transaction by reference / ID (asynchronous).

        Args:
            reference: Merchant reference or Flutterwave transaction ID.

        Returns:
            dict: Raw gateway verification response.

        Raises:
            ProviderHTTPError: If the gateway returns an error or times out.
        """
        if self._is_paystack:
            return await PaystackClient.averify_payment(reference)
        elif self._is_flutterwave:
            return await FlutterwaveClient.averify_transaction(reference)
        elif self._is_olivepay:
            return await OlivePayClient.averify_payment(reference)
        else:
            raise NotImplementedError(f"Provider '{self._provider_code}' not supported.")

    # ── List Banks (sync) ──────────────────────────────────────────────────────

    def list_banks(self, country: str = "NG") -> dict[str, Any]:
        """
        Return the list of banks supported by the active gateway (synchronous).

        Args:
            country: ISO 3166-1 alpha-2 country code.  Defaults to ``"NG"``.

        Returns:
            dict: Raw gateway bank list response.
        """
        if self._is_paystack:
            return PaystackClient.list_banks(country=country)
        elif self._is_flutterwave:
            return FlutterwaveClient.list_banks(country=country)
        elif self._is_olivepay:
            return OlivePayClient.list_banks()
        else:
            raise NotImplementedError(f"Provider '{self._provider_code}' not supported.")

    async def alist_banks(self, country: str = "NG") -> dict[str, Any]:
        """
        Return the list of banks supported by the active gateway (asynchronous).

        Args:
            country: ISO 3166-1 alpha-2 country code.  Defaults to ``"NG"``.

        Returns:
            dict: Raw gateway bank list response.
        """
        if self._is_paystack:
            return await PaystackClient.alist_banks(country=country)
        elif self._is_flutterwave:
            return await FlutterwaveClient.alist_banks(country=country)
        elif self._is_olivepay:
            return await OlivePayClient.alist_banks()
        else:
            raise NotImplementedError(f"Provider '{self._provider_code}' not supported.")

    # ── Initiate Transfer / Payout (sync) ──────────────────────────────────────

    def initiate_transfer(
        self,
        *,
        amount: Decimal,
        reference: str,
        account_number: str,
        bank_code: str,
        account_name: str,
        recipient_code: str = "",
        narration: str = "Fashionistar Payout",
        currency: str = "NGN",
        idempotency_key: str = "",
    ) -> dict[str, Any]:
        """
        Initiate a bank transfer payout to a vendor's registered account (synchronous).

        Gateway-specific notes
        ────────────────────────
        • **Paystack (2-step)**:
            1. ``PaystackClient.create_transfer_recipient()`` → ``recipient_code``
            2. ``PaystackClient.initiate_transfer(recipient_code=...)``
            Callers MUST supply ``recipient_code`` for Paystack.
            If not supplied, the orchestrator will attempt to create a recipient
            automatically using the other args — but this consumes an extra API call.

        • **Flutterwave (1-step)**:
            Bank details are passed directly.  No pre-registration needed.
            Amount is in **full naira units** (the driver handles this).

        • **OlivePay (1-step)**:
            Bank details are passed directly.  Amount converted to kobo internally.

        Args:
            amount: Transfer amount in NGN as a ``Decimal``.
            reference: Unique payout reference for idempotency.
            account_number: Recipient NUBAN account number (10 digits).
            bank_code: Bank code from ``list_banks``.
            account_name: Verified account holder name.
            recipient_code: Paystack ``recipient_code`` (required for Paystack).
            narration: Bank statement description.
            currency: ISO 4217 currency code.  Defaults to ``"NGN"``.
            idempotency_key: Optional idempotency key to prevent duplicate transfers.

        Returns:
            dict: Raw gateway payout initiation response.

        Raises:
            ProviderHTTPError: If the gateway returns an error or circuit is open.
            ValueError: If Paystack ``recipient_code`` is missing.
        """
        if self._is_paystack:
            # Two-step Paystack payout: ensure recipient_code exists
            resolved_recipient_code = recipient_code
            if not resolved_recipient_code:
                logger.info(
                    "Paystack payout: recipient_code missing — auto-creating for %s (%s)",
                    account_name,
                    account_number,
                )
                recipient_data = PaystackClient.create_transfer_recipient(
                    name=account_name,
                    account_number=account_number,
                    bank_code=bank_code,
                    currency=currency,
                    idempotency_key=idempotency_key,
                )
                resolved_recipient_code = (
                    recipient_data.get("data", {}).get("recipient_code", "")
                )
                if not resolved_recipient_code:
                    raise ProviderHTTPError(
                        "Paystack create_transfer_recipient did not return a recipient_code.",
                        status_code=502,
                        response_payload=recipient_data,
                    )

            return PaystackClient.initiate_transfer(
                recipient_code=resolved_recipient_code,
                amount=amount,
                reference=reference,
                reason=narration,
                idempotency_key=idempotency_key,
            )

        elif self._is_flutterwave:
            return FlutterwaveClient.initiate_transfer(
                account_number=account_number,
                account_bank=bank_code,
                amount=amount,
                narration=narration,
                reference=reference,
                currency=currency,
            )

        elif self._is_olivepay:
            return OlivePayClient.initiate_transfer(
                amount=amount,
                reference=reference,
                account_number=account_number,
                bank_code=bank_code,
                account_name=account_name,
                narration=narration,
            )

        else:
            raise NotImplementedError(f"Provider '{self._provider_code}' not supported.")

    # ── Initiate Transfer / Payout (async) ─────────────────────────────────────

    async def ainitiate_transfer(
        self,
        *,
        amount: Decimal,
        reference: str,
        account_number: str,
        bank_code: str,
        account_name: str,
        recipient_code: str = "",
        narration: str = "Fashionistar Payout",
        currency: str = "NGN",
        idempotency_key: str = "",
    ) -> dict[str, Any]:
        """
        Initiate a bank transfer payout to a vendor's registered account (asynchronous).

        Async variant of ``initiate_transfer`` for Django-Ninja views and
        background task handlers.  The same gateway-specific notes apply.

        Args:
            amount: Transfer amount in NGN.
            reference: Unique payout reference.
            account_number: Recipient NUBAN account number.
            bank_code: Bank code from ``alist_banks``.
            account_name: Verified account holder name.
            recipient_code: Paystack ``recipient_code`` (required for Paystack).
            narration: Bank statement description.
            currency: ISO 4217 code.
            idempotency_key: Optional idempotency key.

        Returns:
            dict: Raw gateway payout response.

        Raises:
            ProviderHTTPError: If the gateway returns an error or times out.
        """
        if self._is_paystack:
            resolved_recipient_code = recipient_code
            if not resolved_recipient_code:
                logger.info(
                    "Paystack async payout: recipient_code missing — auto-creating for %s",
                    account_number,
                )
                recipient_data = await PaystackClient.acreate_transfer_recipient(
                    name=account_name,
                    account_number=account_number,
                    bank_code=bank_code,
                    currency=currency,
                    idempotency_key=idempotency_key,
                )
                resolved_recipient_code = (
                    recipient_data.get("data", {}).get("recipient_code", "")
                )
                if not resolved_recipient_code:
                    raise ProviderHTTPError(
                        "Paystack acreate_transfer_recipient did not return a recipient_code.",
                        status_code=502,
                        response_payload=recipient_data,
                    )

            return await PaystackClient.ainitiate_transfer(
                recipient_code=resolved_recipient_code,
                amount=amount,
                reference=reference,
                reason=narration,
                idempotency_key=idempotency_key,
            )

        elif self._is_flutterwave:
            return await FlutterwaveClient.ainitiate_transfer(
                account_number=account_number,
                account_bank=bank_code,
                amount=amount,
                narration=narration,
                reference=reference,
                currency=currency,
            )

        elif self._is_olivepay:
            return await OlivePayClient.ainitiate_transfer(
                amount=amount,
                reference=reference,
                account_number=account_number,
                bank_code=bank_code,
                account_name=account_name,
                narration=narration,
            )

        else:
            raise NotImplementedError(f"Provider '{self._provider_code}' not supported.")

    # ── Webhook Signature Verification ────────────────────────────────────────

    def verify_webhook_signature(
        self,
        raw_payload: bytes,
        signature: str,
        *,
        verif_hash: str = "",
    ) -> bool:
        """
        Verify the authenticity of an inbound webhook delivery (synchronous/sync-safe).

        Args:
            raw_payload: The raw, unmodified request body bytes.
            signature: The provider-specific signature header value.
                       - Paystack:    ``X-Paystack-Signature``
                       - OlivePay:   ``X-OlivePay-Signature``
            verif_hash: The ``verif-hash`` header for Flutterwave webhooks.

        Returns:
            bool: ``True`` if the signature is valid, ``False`` otherwise.
        """
        if self._is_paystack:
            return PaystackClient.verify_signature(raw_payload, signature)
        elif self._is_flutterwave:
            return FlutterwaveClient.verify_signature(verif_hash)
        elif self._is_olivepay:
            return OlivePayClient.verify_signature(raw_payload, signature)
        return False
