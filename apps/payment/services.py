# apps/payment/services.py
"""Payment domain service layer — Paystack integration for the Fashionistar platform.

Architecture:
    Dual-engine HTTP client strategy:
    - ``ProviderSyncHTTPClient``  (Axios-equivalent) for synchronous DRF views.
    - ``ProviderAsyncHTTPClient`` (Ky-equivalent) for async Django-Ninja views.

    All provider calls auto-retry up to ``RetryPolicy.max_attempts`` times on
    transient errors (5xx, connection timeouts).  Every call is logged to
    ``PaymentProviderLog`` (success + failure) for audit and debugging.

Services:
    PaystackClient          — Low-level Paystack API wrapper (sync + async).
    PaymentIntentService    — High-level payment intent lifecycle (init, succeed).
    PaystackWebhookService  — Idempotent webhook event processor.
    TransferRecipientService — Bank transfer recipient registration.

Compliance:
    Every successful payment writes an immutable ledger entry via
    ``TransactionLedgerService`` (PCI-DSS and CBN audit trail).
    Webhook deduplication uses a SHA-256 payload hash to prevent replay attacks.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from decimal import Decimal
from typing import Any

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction as db_transaction

from apps.common.http import (
    ProviderAsyncHTTPClient,
    ProviderHTTPError,
    ProviderSyncHTTPClient,
    RetryPolicy,
)
from apps.global_platform_settings.cache import get_platform_settings
from apps.order.models import (
    CashPaymentMode,
    Order,
    OrderPaymentPath,
    OrderPaymentSource,
)
from apps.order.services import register_payment_tranche
from apps.payment.orchestrator import PaymentOrchestrator
from apps.payment.models import (
    PaymentIntent,
    PaymentIntentStatus,
    PaymentProviderCode,
    PaymentProviderLog,
    PaymentPurpose,
    PaymentWebhookEvent,
    PaystackTransferRecipient,
)
from apps.transactions.services import TransactionLedgerService
from apps.wallet.services import EscrowService, WalletProvisioningService


class PaystackClient:
    """Low-level Paystack REST API client wrapping sync and async HTTP transports.

    Provides a 1:1 mapping of each Paystack API endpoint with automatic:
    - Retry on transient failures (configured via ``RetryPolicy``).
    - Structured logging to ``PaymentProviderLog`` (both success and failure).
    - Idempotency header injection for all mutating requests.
    - Kobo conversion (NGN is stored as Decimal Naira, Paystack expects kobo).

    All async methods are prefixed with ``a`` (``ainitialize_transaction``,
    ``averify_payment``, etc.) and are safe to ``await`` from async views.
    """

    base_url = "https://api.paystack.co"
    retry_policy = RetryPolicy(max_attempts=2)

    @classmethod
    def _headers(cls, *, idempotency_key: str = "") -> dict[str, str]:
        """Build standard Paystack request headers.

        Args:
            idempotency_key: Optional ``Idempotency-Key`` header value.
                When provided prevents duplicate requests at the provider level.

        Returns:
            dict: HTTP headers dict with Bearer token and content type.
        """
        headers = {
            "Authorization": f"Bearer {settings.PAYSTACK_SECRET_KEY}",
            "Content-Type": "application/json",
        }
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        return headers

    @staticmethod
    def _kobo(amount: Decimal) -> int:
        """Convert a Naira ``Decimal`` to kobo integer for the Paystack API.

        Args:
            amount: Amount in NGN (e.g. ``Decimal('1500.00')`` = ₦1,500).

        Returns:
            int: Amount in kobo (e.g. ``150000``).
        """
        return int((amount * Decimal("100")).quantize(Decimal("1")))

    @classmethod
    def _sync_client(cls) -> ProviderSyncHTTPClient:
        return ProviderSyncHTTPClient(
            provider=PaymentProviderCode.PAYSTACK,
            base_url=cls.base_url,
            retry_policy=cls.retry_policy,
        )

    @classmethod
    def _async_client(cls) -> ProviderAsyncHTTPClient:
        return ProviderAsyncHTTPClient(
            provider=PaymentProviderCode.PAYSTACK,
            base_url=cls.base_url,
            retry_policy=cls.retry_policy,
        )

    @staticmethod
    def _log_provider_call(
        *,
        action: str,
        reference: str = "",
        success: bool,
        request_payload: dict | None = None,
        response_payload: dict | None = None,
        error_message: str = "",
    ) -> None:
        """Write a synchronous ``PaymentProviderLog`` entry.

        Called after every provider API request (success or failure) to
        maintain an immutable audit trail of all outbound provider calls.

        Args:
            action: Paystack action string (e.g. ``"transaction.initialize"``).
            reference: Payment reference associated with this call.
            success: ``True`` if the provider returned a success response.
            request_payload: Dict of the request body sent to the provider.
            response_payload: Dict of the response body received.
            error_message: Error string if the call failed.
        """
        PaymentProviderLog.objects.create(
            provider=PaymentProviderCode.PAYSTACK,
            action=action,
            reference=reference,
            success=success,
            request_payload=request_payload or {},
            response_payload=response_payload or {},
            error_message=error_message,
        )

    @staticmethod
    async def _alog_provider_call(
        *,
        action: str,
        reference: str = "",
        success: bool,
        request_payload: dict | None = None,
        response_payload: dict | None = None,
        error_message: str = "",
    ) -> None:
        await PaymentProviderLog.objects.acreate(
            provider=PaymentProviderCode.PAYSTACK,
            action=action,
            reference=reference,
            success=success,
            request_payload=request_payload or {},
            response_payload=response_payload or {},
            error_message=error_message,
        )

    @classmethod
    def _raise_provider_error(
        cls,
        *,
        exc: ProviderHTTPError,
        action: str,
        reference: str = "",
        request_payload: dict | None = None,
    ) -> None:
        cls._log_provider_call(
            action=action,
            reference=reference,
            success=False,
            request_payload=request_payload,
            response_payload=exc.response_payload,
            error_message=str(exc),
        )
        raise ValidationError(str(exc)) from exc

    @classmethod
    async def _araise_provider_error(
        cls,
        *,
        exc: ProviderHTTPError,
        action: str,
        reference: str = "",
        request_payload: dict | None = None,
    ) -> None:
        await cls._alog_provider_call(
            action=action,
            reference=reference,
            success=False,
            request_payload=request_payload,
            response_payload=exc.response_payload,
            error_message=str(exc),
        )
        raise ValidationError(str(exc)) from exc

    @classmethod
    def initialize_transaction(cls, *, email: str, amount: Decimal, reference: str, currency: str = "NGN", metadata: dict | None = None, idempotency_key: str = "") -> dict:
        """Initialize a Paystack payment transaction.

        Creates a new transaction on Paystack and returns the authorization URL
        and access code for the payment popup.

        Args:
            email: Customer's email address.
            amount: Amount in NGN (Naira). Converted to kobo internally.
            reference: Unique transaction reference. Use ``make_reference()``.
            currency: ISO 4217 currency code. Defaults to ``"NGN"``.
            metadata: Additional metadata to pass to Paystack.
            idempotency_key: Optional key to prevent duplicate charges.

        Returns:
            dict: Raw Paystack response payload. Access ``data.authorization_url``
                for the checkout URL.

        Raises:
            ValidationError: If Paystack returns an error response.
        """
        payload = {
            "email": email,
            "amount": cls._kobo(amount),
            "reference": reference,
            "currency": currency,
            "channels": ["bank", "card", "ussd", "mobile_money", "bank_transfer", "qr"],
            "metadata": metadata or {},
        }
        action = "transaction.initialize"
        try:
            res = cls._sync_client().request(
                "POST",
                "/transaction/initialize",
                action=action,
                reference=reference,
                idempotency_key=idempotency_key,
                headers=cls._headers(idempotency_key=idempotency_key),
                json=payload,
            )
        except ProviderHTTPError as exc:
            cls._raise_provider_error(action=action, reference=reference, request_payload=payload, exc=exc)
        data = res.data
        cls._log_provider_call(action=action, reference=reference, success=bool(data.get("status")), request_payload=payload, response_payload=data)
        return data

    @classmethod
    def verify_payment(cls, reference: str) -> dict:
        action = "transaction.verify"
        try:
            res = cls._sync_client().request(
                "GET",
                f"/transaction/verify/{reference}",
                action=action,
                reference=reference,
                headers=cls._headers(),
            )
        except ProviderHTTPError as exc:
            cls._raise_provider_error(action=action, reference=reference, exc=exc)
        data = res.data
        cls._log_provider_call(action=action, reference=reference, success=bool(data.get("status")), response_payload=data)
        return data

    @classmethod
    def list_banks(cls) -> dict:
        action = "bank.list"
        try:
            res = cls._sync_client().request(
                "GET",
                "/bank",
                action=action,
                headers=cls._headers(),
            )
        except ProviderHTTPError as exc:
            cls._raise_provider_error(action=action, exc=exc)
        data = res.data
        cls._log_provider_call(action=action, success=bool(data.get("status")), response_payload=data)
        return data

    @classmethod
    def create_transfer_recipient(cls, *, name: str, account_number: str, bank_code: str, currency: str = "NGN", idempotency_key: str = "") -> dict:
        payload = {"type": "nuban", "name": name, "account_number": account_number, "bank_code": bank_code, "currency": currency}
        action = "transferrecipient.create"
        try:
            res = cls._sync_client().request(
                "POST",
                "/transferrecipient",
                action=action,
                idempotency_key=idempotency_key,
                headers=cls._headers(idempotency_key=idempotency_key),
                json=payload,
            )
        except ProviderHTTPError as exc:
            cls._raise_provider_error(action=action, request_payload=payload, exc=exc)
        data = res.data
        cls._log_provider_call(action=action, success=bool(data.get("status")), request_payload=payload, response_payload=data)
        return data

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
        action = "transaction.initialize"
        try:
            res = await cls._async_client().request(
                "POST",
                "/transaction/initialize",
                action=action,
                reference=reference,
                idempotency_key=idempotency_key,
                headers=cls._headers(idempotency_key=idempotency_key),
                json=payload,
            )
        except ProviderHTTPError as exc:
            await cls._araise_provider_error(action=action, reference=reference, request_payload=payload, exc=exc)
        data = res.data
        await cls._alog_provider_call(action=action, reference=reference, success=bool(data.get("status")), request_payload=payload, response_payload=data)
        return data

    @classmethod
    async def averify_payment(cls, reference: str) -> dict:
        action = "transaction.verify"
        try:
            res = await cls._async_client().request(
                "GET",
                f"/transaction/verify/{reference}",
                action=action,
                reference=reference,
                headers=cls._headers(),
            )
        except ProviderHTTPError as exc:
            await cls._araise_provider_error(action=action, reference=reference, exc=exc)
        data = res.data
        await cls._alog_provider_call(action=action, reference=reference, success=bool(data.get("status")), response_payload=data)
        return data

    @classmethod
    async def alist_banks(cls) -> dict:
        action = "bank.list"
        try:
            res = await cls._async_client().request(
                "GET",
                "/bank",
                action=action,
                headers=cls._headers(),
            )
        except ProviderHTTPError as exc:
            await cls._araise_provider_error(action=action, exc=exc)
        data = res.data
        await cls._alog_provider_call(action=action, success=bool(data.get("status")), response_payload=data)
        return data

    @classmethod
    async def acreate_transfer_recipient(cls, *, name: str, account_number: str, bank_code: str, currency: str = "NGN", idempotency_key: str = "") -> dict:
        payload = {"type": "nuban", "name": name, "account_number": account_number, "bank_code": bank_code, "currency": currency}
        action = "transferrecipient.create"
        try:
            res = await cls._async_client().request(
                "POST",
                "/transferrecipient",
                action=action,
                idempotency_key=idempotency_key,
                headers=cls._headers(idempotency_key=idempotency_key),
                json=payload,
            )
        except ProviderHTTPError as exc:
            await cls._araise_provider_error(action=action, request_payload=payload, exc=exc)
        data = res.data
        await cls._alog_provider_call(action=action, success=bool(data.get("status")), request_payload=payload, response_payload=data)
        return data

    @staticmethod
    def verify_signature(raw_payload: bytes, signature: str) -> bool:
        digest = hmac.new(settings.PAYSTACK_SECRET_KEY.encode("utf-8"), raw_payload, hashlib.sha512).hexdigest()
        return hmac.compare_digest(digest, signature or "")


class PaymentIntentService:
    """High-level payment intent lifecycle management.

    Orchestrates the full payment flow from intent creation through
    success/failure handling and downstream wallet/escrow side-effects.

    Design:
        ``PaymentIntent`` is the authoritative record of a payment attempt.
        Webhook events from Paystack call ``mark_success()`` which performs
        all downstream side-effects (wallet topup, escrow hold, ledger entry)
        inside a single atomic DB transaction.
    """
    @staticmethod
    def make_reference(prefix: str = "FSPAY") -> str:
        """Generate a cryptographically secure unique payment reference.

        Args:
            prefix: Reference prefix string. Defaults to ``"FSPAY"``.

        Returns:
            str: Reference in ``'{prefix}_{token}'`` format where ``token``
                is a 32-character URL-safe random string.
        """
        return f"{prefix}_{secrets.token_urlsafe(24)}"

    @staticmethod
    def _extract_checkout_url(response: dict[str, Any]) -> str:
        data = response.get("data") or {}
        return (
            data.get("authorization_url")
            or data.get("link")
            or data.get("checkout_url")
            or ""
        )

    @staticmethod
    def _get_allowed_percentages() -> list[int]:
        cfg = get_platform_settings()
        raw = getattr(cfg, "order_payment_allowed_percentages", [30, 50, 70, 100])
        if isinstance(raw, str):
            raw = [int(part.strip()) for part in raw.split(",") if part.strip()]
        return sorted({int(value) for value in raw}) or [30, 50, 70, 100]

    @staticmethod
    def _get_minimum_commitment_amount() -> Decimal:
        cfg = get_platform_settings()
        minimum = getattr(cfg, "order_payment_minimum_commitment_ngn", Decimal("0.00"))
        return Decimal(str(minimum or "0.00")).quantize(Decimal("0.01"))

    @classmethod
    def _get_order_for_payment(cls, *, user, order_id: str) -> Order:
        try:
            return (
                Order.objects.select_related("vendor", "vendor__user")
                .prefetch_related("cart_order_items__product")
                .get(pk=order_id, user=user)
            )
        except Order.DoesNotExist as exc:
            raise ValidationError("Order not found for this user.") from exc

    @staticmethod
    def _payment_path_allowed(order: Order, payment_path: str) -> bool:
        mode = order.cash_payment_mode_snapshot or CashPaymentMode.DISABLED
        if payment_path == OrderPaymentPath.COD:
            return mode in {CashPaymentMode.COD, CashPaymentMode.BOTH}
        if payment_path == OrderPaymentPath.PAY_AT_SHOP:
            return mode in {CashPaymentMode.PAY_AT_SHOP, CashPaymentMode.BOTH}
        return True

    @classmethod
    def _validate_order_payment_request(
        cls,
        *,
        order: Order,
        provider: str,
        payment_path: str,
        selected_percent: int,
    ) -> None:
        allowed_percentages = cls._get_allowed_percentages()
        if selected_percent not in allowed_percentages:
            raise ValidationError(f"selected_percent must be one of {allowed_percentages}.")
        if order.status not in {"pending_payment", "awaiting_cash_confirmation", "payment_confirmed"}:
            raise ValidationError("This order is not open for additional payment.")
        if order.is_fully_paid:
            raise ValidationError("This order is already fully paid.")
        if payment_path == OrderPaymentPath.WALLET and provider != PaymentProviderCode.WALLET:
            raise ValidationError("Wallet payment path must use provider='wallet'.")
        if payment_path == OrderPaymentPath.GATEWAY and provider == PaymentProviderCode.WALLET:
            raise ValidationError("Gateway payment path cannot use provider='wallet'.")
        if payment_path in {OrderPaymentPath.COD, OrderPaymentPath.PAY_AT_SHOP} and not cls._payment_path_allowed(order, payment_path):
            raise ValidationError("Requested cash payment mode is not enabled for this order.")
        if order.cash_payment_mode_snapshot == CashPaymentMode.DISABLED and selected_percent != 100:
            raise ValidationError("This order requires full payment because COD / Pay At Shop is disabled.")

    @classmethod
    def calculate_order_payment_amount(
        cls,
        *,
        order: Order,
        selected_percent: int,
    ) -> Decimal:
        minimum_amount = cls._get_minimum_commitment_amount()
        requested_amount = (order.total_amount * Decimal(selected_percent) / Decimal("100")).quantize(Decimal("0.01"))
        payable = max(requested_amount, minimum_amount)
        outstanding = order.amount_outstanding or order.total_amount
        return min(payable, outstanding).quantize(Decimal("0.01"))

    @classmethod
    def initialize_gateway_payment(
        cls,
        *,
        user,
        order: Order,
        provider: str,
        selected_percent: int,
        payment_path: str,
        currency: str = "NGN",
        idempotency_key: str = "",
        cash_payment_mode: str = CashPaymentMode.DISABLED,
        metadata: dict | None = None,
    ) -> PaymentIntent:
        amount = cls.calculate_order_payment_amount(order=order, selected_percent=selected_percent)
        idempotency_key = idempotency_key or (
            f"order-payment:{user.pk}:{order.pk}:{payment_path}:{provider}:{selected_percent}"
        )
        existing = PaymentIntent.objects.filter(
            user=user,
            provider=provider,
            purpose=PaymentPurpose.ORDER_PAYMENT,
            order_id=str(order.pk),
            idempotency_key=idempotency_key,
        ).order_by("-created_at").first()
        if existing and existing.status in {PaymentIntentStatus.PENDING, PaymentIntentStatus.INITIALIZED, PaymentIntentStatus.SUCCEEDED}:
            return existing

        reference = cls.make_reference(prefix="FSORD")
        orchestrator = PaymentOrchestrator.for_provider(provider)
        payload_metadata = {
            "purpose": PaymentPurpose.ORDER_PAYMENT,
            "order_id": str(order.pk),
            "selected_percent": selected_percent,
            "payment_path": payment_path,
            "cash_payment_mode": cash_payment_mode,
            "amount_outstanding_before": str(order.amount_outstanding or order.total_amount),
            **(metadata or {}),
        }
        response = orchestrator.initialize_payment(
            email=str(user.email),
            amount=amount,
            reference=reference,
            currency=currency,
            metadata=payload_metadata,
        )
        checkout_url = cls._extract_checkout_url(response)
        with db_transaction.atomic():
            intent = PaymentIntent.objects.create(
                user=user,
                provider=provider,
                purpose=PaymentPurpose.ORDER_PAYMENT,
                amount=amount,
                currency=currency,
                status=PaymentIntentStatus.INITIALIZED if checkout_url else PaymentIntentStatus.PENDING,
                reference=reference,
                provider_reference=((response.get("data") or {}).get("reference") or reference),
                authorization_url=checkout_url,
                access_code=((response.get("data") or {}).get("access_code") or ""),
                order_id=str(order.pk),
                idempotency_key=idempotency_key,
                metadata=payload_metadata,
                provider_response=response,
            )
        return intent

    @classmethod
    def initialize_paystack(cls, *, user, amount: Decimal, purpose: str, currency: str = "NGN", order_id: str = "", measurement_request_id: str = "", idempotency_key: str = "", metadata: dict | None = None) -> PaymentIntent:
        if purpose == PaymentPurpose.ORDER_PAYMENT and order_id:
            order = cls._get_order_for_payment(user=user, order_id=order_id)
            selected_percent = int((metadata or {}).get("selected_percent") or 100)
            payment_path = (metadata or {}).get("payment_path") or OrderPaymentPath.GATEWAY
            cash_payment_mode = (metadata or {}).get("cash_payment_mode") or order.cash_payment_mode_snapshot
            cls._validate_order_payment_request(
                order=order,
                provider=PaymentProviderCode.PAYSTACK,
                payment_path=payment_path,
                selected_percent=selected_percent,
            )
            return cls.initialize_gateway_payment(
                user=user,
                order=order,
                provider=PaymentProviderCode.PAYSTACK,
                selected_percent=selected_percent,
                payment_path=payment_path,
                currency=currency,
                idempotency_key=idempotency_key,
                cash_payment_mode=cash_payment_mode,
                metadata=metadata,
            )
        reference = cls.make_reference()
        response = PaystackClient.initialize_transaction(
            email=str(user.email),
            amount=amount,
            reference=reference,
            currency=currency,
            idempotency_key=idempotency_key,
            metadata={"purpose": purpose, "order_id": order_id, "measurement_request_id": measurement_request_id, **(metadata or {})},
        )
        with db_transaction.atomic():
            intent = PaymentIntent.objects.create(
                user=user,
                provider=PaymentProviderCode.PAYSTACK,
                purpose=purpose,
                amount=amount,
                currency=currency,
                status=PaymentIntentStatus.PENDING,
                reference=reference,
                order_id=order_id,
                measurement_request_id=measurement_request_id,
                idempotency_key=idempotency_key,
                metadata=metadata or {},
                provider_response=response,
            )
            if response.get("status"):
                data = response.get("data") or {}
                intent.status = PaymentIntentStatus.INITIALIZED
                intent.provider_reference = data.get("reference", reference)
                intent.authorization_url = data.get("authorization_url", "")
                intent.access_code = data.get("access_code", "")
            else:
                intent.status = PaymentIntentStatus.FAILED
            intent.save(update_fields=["provider_response", "status", "provider_reference", "authorization_url", "access_code", "updated_at"])
            return intent

    @classmethod
    @db_transaction.atomic
    def pay_order_from_wallet(
        cls,
        *,
        user,
        order: Order,
        selected_percent: int,
        payment_path: str,
        idempotency_key: str = "",
        metadata: dict | None = None,
    ) -> tuple[PaymentIntent, Any]:
        amount = cls.calculate_order_payment_amount(order=order, selected_percent=selected_percent)
        idempotency_key = idempotency_key or (
            f"wallet-order-payment:{user.pk}:{order.pk}:{payment_path}:{selected_percent}"
        )
        existing = PaymentIntent.objects.filter(
            user=user,
            provider=PaymentProviderCode.WALLET,
            purpose=PaymentPurpose.ORDER_PAYMENT,
            order_id=str(order.pk),
            idempotency_key=idempotency_key,
            status=PaymentIntentStatus.SUCCEEDED,
        ).order_by("-created_at").first()
        if existing:
            latest_record = order.payment_records.order_by("-sequence_number").first()
            return existing, latest_record

        intent = PaymentIntent.objects.create(
            user=user,
            provider=PaymentProviderCode.WALLET,
            purpose=PaymentPurpose.ORDER_PAYMENT,
            amount=amount,
            currency=order.currency,
            status=PaymentIntentStatus.SUCCEEDED,
            reference=cls.make_reference(prefix="FSWALLET"),
            provider_reference="wallet-internal",
            order_id=str(order.pk),
            idempotency_key=idempotency_key,
            metadata={
                "selected_percent": selected_percent,
                "payment_path": payment_path,
                "cash_payment_mode": order.cash_payment_mode_snapshot,
                **(metadata or {}),
            },
        )
        EscrowService.hold_order_payment(
            client_user=user,
            amount=amount,
            reference=intent.reference,
            order_id=str(order.pk),
            provider_reference=intent.provider_reference,
            idempotency_key=idempotency_key,
        )
        record = register_payment_tranche(
            order=order,
            amount=amount,
            selected_percent=selected_percent,
            payment_source=(
                OrderPaymentSource.COD_COMMITMENT
                if payment_path == OrderPaymentPath.COD
                else OrderPaymentSource.PAY_AT_SHOP_COMMITMENT
                if payment_path == OrderPaymentPath.PAY_AT_SHOP
                else OrderPaymentSource.WALLET
            ),
            payment_path=payment_path,
            provider=PaymentProviderCode.WALLET,
            actor=user,
            payment_intent=intent,
            correlation_id=idempotency_key,
            metadata=metadata or {},
        )
        return intent, record

    @classmethod
    @db_transaction.atomic
    def mark_success(cls, intent: PaymentIntent, provider_payload: dict[str, Any]) -> PaymentIntent:
        """Handle a verified successful payment by executing side-effects.

        Performs all downstream state changes in a single atomic transaction:
        - Wallet topup: credits user's wallet.
        - Order payment: credits user wallet, then performs escrow hold.
        - Measurement fee: records a platform fee ledger entry.

        Idempotent: calling ``mark_success()`` on an already-succeeded intent
        returns the intent unchanged without duplicating side-effects.

        Args:
            intent: The ``PaymentIntent`` instance to mark as succeeded.
            provider_payload: Raw Paystack webhook payload for archiving.

        Returns:
            PaymentIntent: The updated intent with status ``SUCCEEDED``.
        """
        if intent.status == PaymentIntentStatus.SUCCEEDED:
            return intent
        intent.status = PaymentIntentStatus.SUCCEEDED
        intent.provider_response = provider_payload
        intent.save(update_fields=["status", "provider_response", "updated_at"])
        user_wallet = WalletProvisioningService.ensure_wallet(intent.user, intent.currency)
        company_wallet = WalletProvisioningService.ensure_company_wallet(intent.currency)
        from apps.wallet.services import WalletBalanceService
        if intent.purpose == PaymentPurpose.WALLET_TOPUP:
            WalletBalanceService.credit(user_wallet, intent.amount)
        elif intent.purpose == PaymentPurpose.ORDER_PAYMENT:
            WalletBalanceService.credit(user_wallet, intent.amount)
            EscrowService.hold_order_payment(
                client_user=intent.user,
                amount=intent.amount,
                reference=intent.reference,
                order_id=intent.order_id,
                provider_reference=intent.provider_reference,
                idempotency_key=intent.idempotency_key,
            )
            if intent.order_id:
                order = cls._get_order_for_payment(user=intent.user, order_id=intent.order_id)
                payment_path = (intent.metadata or {}).get("payment_path", OrderPaymentPath.GATEWAY)
                register_payment_tranche(
                    order=order,
                    amount=intent.amount,
                    selected_percent=int((intent.metadata or {}).get("selected_percent") or 100),
                    payment_source=(
                        OrderPaymentSource.COD_COMMITMENT
                        if payment_path == OrderPaymentPath.COD
                        else OrderPaymentSource.PAY_AT_SHOP_COMMITMENT
                        if payment_path == OrderPaymentPath.PAY_AT_SHOP
                        else OrderPaymentSource.GATEWAY
                    ),
                    payment_path=payment_path,
                    provider=intent.provider,
                    actor=intent.user,
                    payment_intent=intent,
                    correlation_id=intent.idempotency_key or intent.reference,
                    metadata=intent.metadata or {},
                )
        elif intent.purpose == PaymentPurpose.MEASUREMENT_FEE:
            TransactionLedgerService.record_measurement_fee(
                user=intent.user,
                wallet=user_wallet,
                company_wallet=company_wallet,
                reference=intent.reference,
                amount=intent.amount,
                measurement_request_id=intent.measurement_request_id,
                idempotency_key=intent.idempotency_key,
            )
        return intent


class PaystackWebhookService:
    """Idempotent Paystack webhook event processor.

    Deduplicates events via SHA-256 hash of the raw payload body so
    duplicate deliveries (Paystack retries) are silently ignored.

    Security:
        HMAC-SHA512 signature verification is performed BEFORE any DB
        writes to prevent processing forged webhook events.

    Compliance:
        All webhook events write to ``PaymentWebhookEvent`` for audit.
        Transfer outcomes are additionally logged in ``PaymentProviderLog``.
    """

    @staticmethod
    def _payload_hash(raw_payload: bytes) -> str:
        """Compute a SHA-256 hash of the raw webhook payload for deduplication.

        Args:
            raw_payload: Raw bytes from the incoming HTTP request body.

        Returns:
            str: Hex-encoded SHA-256 digest.
        """
        return hashlib.sha256(raw_payload).hexdigest()

    @classmethod
    @db_transaction.atomic
    def process(cls, *, raw_payload: bytes, signature: str) -> PaymentWebhookEvent:
        """Verify and process an incoming Paystack webhook event.

        Steps:
            1. Validates HMAC-SHA512 signature.
            2. Deduplicates via ``PaymentWebhookEvent`` SHA-256 hash.
            3. Dispatches to the correct handler (charge success/failure,
               transfer outcome).
            4. Marks the event as processed.

        Args:
            raw_payload: Raw request body bytes (used for signature + hash).
            signature: ``X-Paystack-Signature`` header value.

        Returns:
            PaymentWebhookEvent: The created or existing webhook event record.

        Raises:
            ValidationError: If signature verification fails.
        """
        if not PaystackClient.verify_signature(raw_payload, signature):
            raise ValidationError("Invalid Paystack webhook signature.")
        payload = json.loads(raw_payload.decode("utf-8"))
        event_name = payload.get("event", "")
        data = payload.get("data") or {}
        reference = data.get("reference") or data.get("transfer_code") or ""
        event_id = str(data.get("id") or data.get("event_id") or reference)
        webhook, created = PaymentWebhookEvent.objects.get_or_create(
            payload_hash=cls._payload_hash(raw_payload),
            defaults={
                "provider": PaymentProviderCode.PAYSTACK,
                "event": event_name,
                "event_id": event_id,
                "reference": reference,
                "payload": payload,
            },
        )
        if not created or webhook.processed:
            return webhook
        try:
            if event_name == "charge.success":
                intent = PaymentIntent.objects.select_for_update().get(reference=reference)
                PaymentIntentService.mark_success(intent, payload)
            elif event_name == "charge.failed":
                PaymentIntent.objects.filter(reference=reference).update(status=PaymentIntentStatus.FAILED, provider_response=payload)
            elif event_name in {"transfer.success", "transfer.failed", "transfer.reversed"}:
                # Transfer settlement is recorded in the provider audit trail here;
                # payout ledger entries remain in apps.transactions.
                PaymentProviderLog.objects.create(
                    provider=PaymentProviderCode.PAYSTACK,
                    action=event_name,
                    reference=reference,
                    success=event_name == "transfer.success",
                    response_payload=payload,
                )
            webhook.processed = True
            webhook.save(update_fields=["processed", "updated_at"])
        except Exception as exc:
            webhook.processing_error = str(exc)
            webhook.save(update_fields=["processing_error", "updated_at"])
            raise
        return webhook


class TransferRecipientService:
    """Bank transfer recipient registration service.

    Creates a Paystack transfer recipient for a Nigerian bank account
    and persists the result as a ``PaystackTransferRecipient`` record
    linked to the user for future payout operations.
    """

    @staticmethod
    @db_transaction.atomic
    def create_for_user(*, user, account_number: str, account_name: str, bank_code: str, bank_name: str, idempotency_key: str = "") -> PaystackTransferRecipient:
        """Create and persist a Paystack transfer recipient for a bank account.

        Args:
            user: The ``UnifiedUser`` who owns this bank account.
            account_number: Nigerian bank account number (10 digits, NUBAN).
            account_name: Account holder's name as on record with the bank.
            bank_code: Paystack bank code (use ``PaystackClient.list_banks()``).
            bank_name: Human-readable bank name for display.
            idempotency_key: Optional key to prevent duplicate registrations.

        Returns:
            PaystackTransferRecipient: The created recipient record containing
                the Paystack ``recipient_code`` for future transfers.

        Raises:
            ValidationError: If Paystack rejects the recipient registration.
        """
        response = PaystackClient.create_transfer_recipient(
            name=account_name,
            account_number=account_number,
            bank_code=bank_code,
            idempotency_key=idempotency_key,
        )
        if not response.get("status"):
            raise ValidationError(response.get("message", "Paystack recipient creation failed."))
        data = response.get("data") or {}
        recipient = PaystackTransferRecipient.objects.create(
            user=user,
            recipient_code=data.get("recipient_code", ""),
            account_number=account_number,
            account_name=account_name,
            bank_code=bank_code,
            bank_name=bank_name,
            provider_response=response,
        )
        return recipient
