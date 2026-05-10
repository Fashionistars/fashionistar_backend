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

    @classmethod
    def initialize_paystack(cls, *, user, amount: Decimal, purpose: str, currency: str = "NGN", order_id: str = "", measurement_request_id: str = "", idempotency_key: str = "", metadata: dict | None = None) -> PaymentIntent:
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
    def mark_success(cls, intent: PaymentIntent, provider_payload: dict[str, Any]) -> PaymentIntent:
        """Handle a verified successful payment by executing side-effects.

        Performs all downstream state changes in a single atomic transaction:
        - Wallet topup: credits user's wallet.
        - Order payment: creates an escrow hold for the order amount.
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
        if intent.purpose == PaymentPurpose.WALLET_TOPUP:
            from apps.wallet.services import WalletBalanceService
            WalletBalanceService.credit(user_wallet, intent.amount)
        elif intent.purpose == PaymentPurpose.ORDER_PAYMENT:
            EscrowService.hold_order_payment(
                client_user=intent.user,
                amount=intent.amount,
                reference=intent.reference,
                order_id=intent.order_id,
                provider_reference=intent.provider_reference,
                idempotency_key=intent.idempotency_key,
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
