# apps/wallet/services/escrow.py
"""
EscrowService — Order Payment Escrow Hold, Release, and Refund.

Architecture:
    Escrow flow (three-stage lifecycle):
        1. ``hold_order_payment()``
           Client funds → escrow_balance + pending_balance.
           Creates a ``WalletHold`` record and an immutable ledger entry.

        2. ``release_order_payment()``
           On order delivery confirmation:
           Gross amount → split into vendor_amount + commission_amount.
           Vendor wallet credited, Company wallet (singleton owned by
           fashionistarclothings@outlook.com) credited with commission.
           WalletHold status → RELEASED.

        3. ``refund_escrow()``
           On order cancellation / dispute resolved for client:
           Held funds → returned to client available_balance.
           WalletHold status → REFUNDED.

    All three stages are wrapped in ``@db_transaction.atomic`` and acquire
    ``SELECT FOR UPDATE`` locks on ALL affected wallet rows in a consistent
    order to prevent AB/BA deadlocks at 10k+ RPS.

Company Wallet Enforcement:
    ``ensure_company_wallet()`` always resolves the singleton wallet via
    ``WalletProvisioningService`` which enforces the link to
    fashionistarclothings@outlook.com. Commission credits are ALWAYS routed
    to this specific wallet for full CBN-compliant audit accountability.

Integration Guide::

    from apps.wallet.services.escrow import EscrowService

    # Step 1: Hold client funds at order creation
    hold = EscrowService.hold_order_payment(
        client_user=request.user,
        amount=Decimal("10000.00"),
        reference="escrow-order-abc123",
        order_id="order-abc123",
    )

    # Step 2: Release on delivery (triggered by webhook or admin)
    result = EscrowService.release_order_payment(
        hold_reference="escrow-order-abc123",
        vendor_user=vendor_user,
    )
    # result = {"gross_amount": ..., "vendor_amount": ..., "commission_amount": ...}

    # Step 3: Refund on cancellation
    hold = EscrowService.refund_escrow(hold_reference="escrow-order-abc123")

EventBus Events (emitted on transaction.on_commit):
    ``escrow.hold_created``  — funds locked for order.
    ``escrow.released``      — funds split to vendor + company.
    ``escrow.refunded``      — funds returned to client.
"""
from __future__ import annotations

import logging
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction as db_transaction
from django.utils import timezone

from apps.common.events import event_bus
from apps.global_platform_settings.cache import get_platform_settings
from apps.wallet.models import Wallet, WalletHold, WalletHoldStatus
from apps.wallet.services.balance import WalletBalanceService
from apps.wallet.services.provisioning import WalletProvisioningService

logger = logging.getLogger(__name__)


class EscrowService:
    """Order payment escrow service — hold, release, and refund.

    Escrow flow:
        1. ``hold_order_payment()`` — deducts from client available_balance,
           adds to pending and escrow balances, creates a ``WalletHold``.
        2. ``release_order_payment()`` — on order delivery confirmation:
           splits gross amount into vendor_amount + commission_amount,
           credits vendor and company wallets, zeroes escrow hold.
        3. ``refund_escrow()`` — on order cancellation/dispute: returns
           held funds to client available_balance, zeroes escrow hold.

    All methods are wrapped in ``@db_transaction.atomic`` and acquire
    ``SELECT FOR UPDATE`` locks on all affected wallet rows.
    """

    # ── Step 1: Hold ───────────────────────────────────────────────────────────

    @staticmethod
    @db_transaction.atomic
    def hold_order_payment(
        *,
        client_user,
        amount: Decimal,
        reference: str,
        order_id: str = "",
        provider_reference: str = "",
        idempotency_key: str = "",
        request=None,
    ) -> WalletHold:
        """Place an escrow hold on client funds for a pending order payment.

        Moves ``amount`` from client ``available_balance`` into
        ``pending_balance + escrow_balance``. Creates a ``WalletHold`` record
        and an immutable ledger entry via ``TransactionLedgerService``.

        Args:
            client_user: The ``UnifiedUser`` (buyer) whose wallet to hold.
            amount: Positive ``Decimal`` amount to hold in escrow.
            reference: Unique escrow hold reference (e.g. ``"escrow-{order_pk}"``).
            order_id: String representation of the linked ``Order.pk``.
            provider_reference: Payment provider's transaction reference.
            idempotency_key: Optional key for duplicate-request protection.
            request: Optional HTTP request for audit metadata.

        Returns:
            WalletHold: The created (or existing, if idempotent) hold record.

        Raises:
            ValidationError: If the wallet is not ACTIVE or available_balance
                is insufficient.
        """
        from apps.transactions.services import TransactionLedgerService

        # ── Lock client wallet ────────────────────────────────────────────────
        provisioned = WalletProvisioningService.ensure_wallet(client_user, request=request)
        client_wallet = client_user.financial_wallets.select_for_update().get(
            pk=provisioned.pk
        )
        WalletBalanceService._assert_active(client_wallet)

        if client_wallet.available_balance < amount:
            raise ValidationError("Insufficient wallet balance for escrow hold.")

        # ── Atomic balance mutation ───────────────────────────────────────────
        client_wallet.available_balance -= amount
        client_wallet.pending_balance += amount
        client_wallet.escrow_balance += amount
        client_wallet.last_transaction_at = timezone.now()
        client_wallet.save(
            update_fields=[
                "available_balance",
                "pending_balance",
                "escrow_balance",
                "last_transaction_at",
                "updated_at",
            ]
        )

        # ── Idempotent WalletHold creation ───────────────────────────────────
        hold, created = WalletHold.objects.get_or_create(
            reference=reference,
            defaults={
                "wallet": client_wallet,
                "amount": amount,
                "order_id": order_id,
                "metadata": {"provider_reference": provider_reference},
            },
        )

        if created:
            TransactionLedgerService.record_escrow_hold(
                user=client_user,
                wallet=client_wallet,
                amount=amount,
                reference=reference,
                order_id=order_id,
                provider_reference=provider_reference,
                idempotency_key=idempotency_key,
            )
            # ── Capture IDs before on_commit ──────────────────────────────────
            _wid = str(client_wallet.pk)
            _uid = str(client_user.pk)
            _amt = str(amount)
            _oid = order_id

            def _on_hold():
                try:
                    from apps.audit_logs.services.wallet import wallet_audit
                    wallet_audit.log_escrow_hold(
                        actor=client_user,
                        wallet_id=_wid,
                        amount=_amt,
                        order_id=_oid,
                        request=request,
                    )
                except Exception:
                    logger.warning(
                        "wallet_audit.log_escrow_hold failed silently",
                        exc_info=True,
                    )
                event_bus.emit(
                    "escrow.hold_created",
                    wallet_id=_wid,
                    user_id=_uid,
                    amount=_amt,
                    order_id=_oid,
                    reference=reference,
                )

            db_transaction.on_commit(_on_hold)
            logger.info(
                "Escrow hold created: user=%s amount=%s order=%s ref=%s",
                client_user.pk, amount, order_id, reference,
            )

        return hold

    # ── Step 2: Release ────────────────────────────────────────────────────────

    @staticmethod
    @db_transaction.atomic
    def release_order_payment(
        *,
        hold_reference: str,
        vendor_user,
        commission_rate: Decimal | None = None,
        idempotency_key: str = "",
        request=None,
    ) -> dict:
        """Release an active escrow hold to the vendor and company accounts.

        Calculates commission split, credits vendor and company wallets atomically,
        and marks the hold as RELEASED. Records an immutable escrow-release
        ledger entry via ``TransactionLedgerService``.

        The company wallet commission is ALWAYS routed to the singleton wallet
        owned by ``fashionistarclothings@outlook.com`` for full audit compliance.

        Args:
            hold_reference: The ``WalletHold.reference`` to release.
            vendor_user: The ``UnifiedUser`` vendor to credit.
            commission_rate: Override commission ratio (``Decimal``). Falls
                back to ``GlobalPlatformSettings.vendor_commission_rate``.
            idempotency_key: Optional key for replay safety.
            request: Optional HTTP request for audit metadata.

        Returns:
            dict: Keys ``gross_amount``, ``vendor_amount``,
                ``commission_amount`` (all ``Decimal``).

        Raises:
            ValidationError: If the hold is not ACTIVE or remaining amount
                is zero.
        """
        from apps.transactions.services import TransactionLedgerService

        # ── Resolve commission rate ───────────────────────────────────────────
        if commission_rate is None:
            commission_rate = get_platform_settings().vendor_commission_rate

        # ── Lock escrow hold + related wallets ────────────────────────────────
        hold = (
            WalletHold.objects
            .select_for_update()
            .select_related("wallet", "wallet__currency")
            .get(reference=hold_reference)
        )
        if hold.status != WalletHoldStatus.ACTIVE:
            raise ValidationError("Escrow hold is not active.")

        amount = hold.remaining_amount
        if amount <= 0:
            raise ValidationError("No escrow balance remains to release.")

        # Deterministic wallet locking order: client, vendor, company
        client_wallet = hold.wallet.user.financial_wallets.select_for_update().get(
            pk=hold.wallet_id
        )
        vendor_wallet = vendor_user.financial_wallets.select_for_update().get(
            pk=WalletProvisioningService.ensure_wallet(
                vendor_user, client_wallet.currency.code, request=request
            ).pk
        )
        # ENFORCEMENT: Company wallet is ALWAYS the singleton linked to COMPANY_EMAIL
        company_wallet = Wallet.objects.select_for_update().get(
            pk=WalletProvisioningService.ensure_company_wallet(
                client_wallet.currency.code
            ).pk
        )

        # ── Calculate split ───────────────────────────────────────────────────
        commission_amount = (amount * commission_rate).quantize(Decimal("0.01"))
        vendor_amount = amount - commission_amount

        # ── Atomic balance mutations ──────────────────────────────────────────
        now = timezone.now()

        # Client: release escrow hold
        client_wallet.pending_balance -= amount
        client_wallet.escrow_balance -= amount
        client_wallet.last_transaction_at = now
        client_wallet.save(
            update_fields=["pending_balance", "escrow_balance", "last_transaction_at", "updated_at"]
        )

        # Vendor: credit net amount
        vendor_wallet.balance += vendor_amount
        vendor_wallet.available_balance += vendor_amount
        vendor_wallet.last_transaction_at = now
        vendor_wallet.save(
            update_fields=["balance", "available_balance", "last_transaction_at", "updated_at"]
        )

        # Company: credit commission (fashionistarclothings@outlook.com wallet)
        company_wallet.balance += commission_amount
        company_wallet.available_balance += commission_amount
        company_wallet.last_transaction_at = now
        company_wallet.save(
            update_fields=["balance", "available_balance", "last_transaction_at", "updated_at"]
        )

        # ── Mark hold as released ─────────────────────────────────────────────
        hold.released_amount += amount
        hold.status = WalletHoldStatus.RELEASED
        hold.save(update_fields=["released_amount", "status", "updated_at"])

        # ── Immutable ledger entry ────────────────────────────────────────────
        TransactionLedgerService.record_escrow_release(
            hold=hold,
            vendor_user=vendor_user,
            vendor_wallet=vendor_wallet,
            company_wallet=company_wallet,
            gross_amount=amount,
            vendor_amount=vendor_amount,
            commission_amount=commission_amount,
            idempotency_key=idempotency_key,
        )

        # ── EventBus + audit on_commit ────────────────────────────────────────
        _cwid = str(client_wallet.pk)
        _oid = hold.order_id
        _amt = str(amount)
        _vendor_id = str(vendor_user.pk)

        def _on_release():
            try:
                from apps.audit_logs.services.wallet import wallet_audit
                wallet_audit.log_escrow_release(
                    actor=vendor_user,
                    wallet_id=_cwid,
                    amount=_amt,
                    order_id=_oid,
                    request=request,
                )
            except Exception:
                logger.warning(
                    "wallet_audit.log_escrow_release failed silently",
                    exc_info=True,
                )
            event_bus.emit(
                "escrow.released",
                wallet_id=_cwid,
                vendor_id=_vendor_id,
                amount=_amt,
                vendor_amount=str(vendor_amount),
                commission_amount=str(commission_amount),
                order_id=_oid,
            )

        db_transaction.on_commit(_on_release)
        logger.info(
            "Escrow released: hold=%s vendor=%s vendor_amount=%s commission=%s",
            hold_reference, vendor_user.pk, vendor_amount, commission_amount,
        )

        return {
            "gross_amount": amount,
            "vendor_amount": vendor_amount,
            "commission_amount": commission_amount,
        }

    # ── Step 2b: Release from client context ───────────────────────────────────

    @staticmethod
    @db_transaction.atomic
    def release_order_payment_for_client(
        *,
        client_user,
        hold_reference: str,
        commission_rate: Decimal | None = None,
        idempotency_key: str = "",
        request=None,
    ) -> dict:
        """Release a client's escrow hold to the vendor attached to its order.

        Traversal (Wave-4 canonical):
            request.user.financial_wallets → wallet.holds → WalletHold
            request.user.user_orders → Order → order.vendor.user

        Args:
            client_user: Authenticated client from ``request.user``.
            hold_reference: Escrow hold reference generated during payment.
            commission_rate: Platform commission ratio.
            idempotency_key: Optional idempotency header for ledger replay safety.
            request: Optional HTTP request for audit metadata.

        Returns:
            dict: Gross, vendor, and commission amounts from the release.

        Raises:
            ValidationError: If the hold or linked order cannot be resolved from
                the authenticated user's reverse relationships.
        """
        # Verify hold ownership through wallet reverse relation
        client_wallet = client_user.financial_wallets.select_for_update().first()
        if client_wallet is None:
            raise ValidationError("Client wallet not found.")

        try:
            hold = client_wallet.holds.select_for_update().get(reference=hold_reference)
        except client_wallet.holds.model.DoesNotExist as exc:
            raise ValidationError(
                "Escrow hold not found for this client wallet."
            ) from exc

        if not hold.order_id:
            raise ValidationError("Escrow hold is not linked to an order.")

        try:
            order = client_user.user_orders.select_related("vendor__user").get(
                pk=hold.order_id,
            )
        except client_user.user_orders.model.DoesNotExist as exc:
            raise ValidationError("Linked order is not owned by this client.") from exc

        vendor_user = getattr(getattr(order, "vendor", None), "user", None)
        if vendor_user is None:
            raise ValidationError("Linked order does not have a vendor user.")

        return EscrowService.release_order_payment(
            hold_reference=hold_reference,
            vendor_user=vendor_user,
            commission_rate=commission_rate,
            idempotency_key=idempotency_key,
            request=request,
        )

    # ── Step 3: Refund ─────────────────────────────────────────────────────────

    @staticmethod
    @db_transaction.atomic
    def refund_escrow(
        *,
        hold_reference: str,
        idempotency_key: str = "",
        request=None,
    ) -> WalletHold:
        """Refund an active escrow hold back to the client's available balance.

        Called on order cancellation or dispute resolution in favour of the
        client. Returns held funds to ``available_balance`` and zeroes the
        ``escrow_balance`` and ``pending_balance`` accordingly.

        Args:
            hold_reference: The ``WalletHold.reference`` to refund.
            idempotency_key: Optional key for replay safety.
            request: Optional HTTP request for audit metadata.

        Returns:
            WalletHold: The updated hold instance with status ``REFUNDED``.

        Raises:
            ValidationError: If the hold is not in ACTIVE status.
        """
        from apps.transactions.services import TransactionLedgerService

        hold = (
            WalletHold.objects
            .select_for_update()
            .select_related("wallet")
            .get(reference=hold_reference)
        )
        if hold.status != WalletHoldStatus.ACTIVE:
            raise ValidationError("Escrow hold is not active.")

        amount = hold.remaining_amount
        wallet = hold.wallet.user.financial_wallets.select_for_update().get(
            pk=hold.wallet_id
        )

        # ── Atomic balance restoration ────────────────────────────────────────
        wallet.pending_balance -= amount
        wallet.escrow_balance -= amount
        wallet.available_balance += amount
        wallet.last_transaction_at = timezone.now()
        wallet.save(
            update_fields=[
                "pending_balance",
                "escrow_balance",
                "available_balance",
                "last_transaction_at",
                "updated_at",
            ]
        )

        hold.refunded_amount += amount
        hold.status = WalletHoldStatus.REFUNDED
        hold.save(update_fields=["refunded_amount", "status", "updated_at"])

        # ── Immutable ledger entry ────────────────────────────────────────────
        TransactionLedgerService.record_refund(
            wallet=wallet,
            amount=amount,
            reference=hold.reference,
            order_id=hold.order_id,
            idempotency_key=idempotency_key,
        )

        # ── EventBus + audit on_commit ────────────────────────────────────────
        _wid = str(wallet.pk)
        _uid = str(getattr(wallet.user, "pk", ""))
        _amt = str(amount)
        _oid = hold.order_id

        def _on_refund():
            try:
                from apps.audit_logs.services.wallet import wallet_audit
                wallet_audit.log_escrow_refunded(
                    actor=wallet.user,
                    wallet_id=_wid,
                    amount=_amt,
                    order_id=_oid,
                    request=request,
                )
            except Exception:
                logger.warning(
                    "wallet_audit.log_escrow_refunded failed silently",
                    exc_info=True,
                )
            event_bus.emit(
                "escrow.refunded",
                wallet_id=_wid,
                user_id=_uid,
                amount=_amt,
                order_id=_oid,
                reference=hold_reference,
            )

        db_transaction.on_commit(_on_refund)
        logger.info(
            "Escrow refunded: hold=%s user=%s amount=%s",
            hold_reference, _uid, amount,
        )

        return hold
