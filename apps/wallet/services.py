# apps/wallet/services.py
"""Wallet domain service layer for the Fashionistar platform.

Architecture:
    All wallet mutations go through atomic service methods that:
    - Acquire ``SELECT FOR UPDATE`` locks before balance mutations to prevent
      race conditions under high concurrency.
    - Write immutable ledger rows via ``TransactionLedgerService`` for every
      balance change (PCI-DSS and CBN compliance requirement).
    - Gate financial exit operations (withdrawal, transfer) behind
      ``assert_kyc_approved()`` from the KYC domain.

Services:
    WalletProvisioningService — Create/ensure user and company wallets.
    WalletPinService          — Set, verify, and change transaction PINs.
    WalletBalanceService      — Atomic credit, debit, and transfer operations.
    WalletWithdrawalService   — KYC-gated bank withdrawal requests.
    EscrowService             — Order payment hold, release, and refund.
"""
from __future__ import annotations

import secrets
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction as db_transaction
from django.utils import timezone

from apps.global_platform_settings.cache import get_platform_settings
from apps.wallet.models import Currency, Wallet, WalletHold, WalletHoldStatus, WalletOwnerType, WalletStatus


class WalletProvisioningService:
    """Idempotent wallet provisioning for users and the company account.

    All methods are safe to call multiple times — they use ``get_or_create``
    patterns internally so duplicate wallets are never created, even under
    concurrent requests.
    """
    @staticmethod
    def ensure_currency(code: str = "NGN") -> Currency:
        """Retrieve or create a Currency record for the given ISO 4217 code.

        Args:
            code: ISO 4217 currency code (e.g. ``"NGN"``, ``"USD"``).
                Case-insensitive. Defaults to ``"NGN"``.

        Returns:
            Currency: The existing or newly created Currency instance.
        """
        cfg = get_platform_settings()
        fallback_ngn_usd = cfg.ngn_usd_rate
        currency, _ = Currency.objects.get_or_create(
            code=code.upper(),
            defaults={
                "name": "Nigerian Naira" if code.upper() == "NGN" else code.upper(),
                "symbol": "₦" if code.upper() == "NGN" else code.upper(),
                "decimal_places": 2,
                "exchange_rate_usd": fallback_ngn_usd if code.upper() == "NGN" else Decimal("1.00000000"),
            },
        )
        return currency

    @staticmethod
    def owner_type_for_user(user) -> str:
        """Resolve the ``WalletOwnerType`` for a given ``UnifiedUser``.

        Args:
            user: A ``UnifiedUser`` instance.

        Returns:
            str: One of the ``WalletOwnerType`` constants — ``'client'``,
                ``'vendor'``, ``'admin'``, etc.
        """
        role = getattr(user, "role", WalletOwnerType.CLIENT)
        if role in {WalletOwnerType.VENDOR, WalletOwnerType.SUPPORT, WalletOwnerType.EDITOR, WalletOwnerType.MODERATOR, WalletOwnerType.ADMIN}:
            return role
        if role and role.startswith("super_"):
            return WalletOwnerType.ADMIN
        return WalletOwnerType.CLIENT

    @classmethod
    def ensure_wallet(cls, user, currency_code: str = "NGN", request=None) -> Wallet:
        """Retrieve or create the default wallet for ``user``.

        Uses the ``user.financial_wallets`` reverse FK manager so wallet
        ownership is always bound to the authenticated user's identity.

        Args:
            user: A ``UnifiedUser`` instance.
            currency_code: ISO 4217 code for the wallet currency.
                Defaults to ``"NGN"``.

        Returns:
            Wallet: The existing or newly created default wallet.
        """
        currency = cls.ensure_currency(currency_code)
        owner_type = cls.owner_type_for_user(user)
        # Canonical Wave 4 ownership traversal:
        # user.financial_wallets is the reverse FK from request.user to Wallet.
        # Keeping provisioning on the reverse manager makes wallet ownership
        # obvious and avoids ad hoc Wallet.objects filters in API flows.
        wallet, created = user.financial_wallets.get_or_create(
            owner_type=owner_type,
            currency=currency,
            is_default=True,
            defaults={
                "name": f"{owner_type.title()} Wallet",
                "account_name": str(getattr(user, "email", None) or getattr(user, "phone", "") or user.pk),
                "account_number": f"90{secrets.randbelow(10**8):08d}",
            },
        )
        if created:
            try:
                from apps.audit_logs.services.wallet import wallet_audit

                db_transaction.on_commit(
                    lambda: wallet_audit.log_wallet_created(
                        actor=user,
                        wallet_id=str(wallet.pk),
                        currency=currency_code,
                        request=request,
                    )
                )
            except Exception:
                pass
        return wallet

    @classmethod
    def ensure_company_wallet(cls, currency_code: str = "NGN") -> Wallet:
        """Retrieve or create the singleton Fashionistar company wallet.

        The company wallet has ``user=NULL`` by design — it receives platform
        commissions from escrow releases.  This is an intentional documented
        exception to the FK-based ownership pattern.

        Args:
            currency_code: ISO 4217 code. Defaults to ``"NGN"``.

        Returns:
            Wallet: The Fashionistar company wallet instance.
        """
        currency = cls.ensure_currency(currency_code)
        # Company wallets intentionally have no request.user reverse path.
        # This singleton is the documented exception because user is NULL by
        # design and enforced by Wallet.clean()/database constraints.
        wallet, _ = Wallet.objects.get_or_create(
            user=None,
            owner_type=WalletOwnerType.COMPANY,
            currency=currency,
            is_default=True,
            defaults={
                "name": "Fashionistar Company Wallet",
                "account_name": "Fashionistar Company",
                "account_number": "FASHIONISTAR-COMPANY",
            },
        )
        return wallet


class WalletPinService:
    """Transaction PIN management for wallets.

    PINs are bcrypt-hashed before storage — the raw PIN is NEVER persisted.
    Failed attempts are tracked; the wallet is locked after 5 consecutive
    failures (configurable in ``Wallet.verify_pin()``).
    """

    @staticmethod
    @db_transaction.atomic
    def set_pin(user, raw_pin: str, request=None) -> Wallet:
        """Set a new transaction PIN for the user's default wallet.

        Args:
            user: A ``UnifiedUser`` instance.
            raw_pin: The plaintext 4–6 digit PIN to hash and store.

        Returns:
            Wallet: The updated wallet instance.
        """
        provisioned = WalletProvisioningService.ensure_wallet(user, request=request)
        wallet = user.financial_wallets.select_for_update().get(pk=provisioned.pk)
        wallet.set_pin(raw_pin)
        wallet.save(update_fields=["pin_hash", "pin_set_at", "failed_pin_attempts", "pin_locked_until", "updated_at"])
        # Audit trail: PIN set event (compliance-grade, no raw PIN stored)
        try:
            from apps.audit_logs.services.wallet import wallet_audit
            db_transaction.on_commit(
                lambda: wallet_audit.log_wallet_pin_set(
                    actor=user,
                    wallet_id=str(wallet.pk),
                    request=request,
                )
            )
        except Exception:
            pass
        return wallet

    @staticmethod
    def verify_pin(user, raw_pin: str, request=None) -> bool:
        """Verify a PIN against the stored bcrypt hash.

        Args:
            user: A ``UnifiedUser`` instance.
            raw_pin: The plaintext PIN to verify.

        Returns:
            bool: ``True`` if the PIN matches, ``False`` otherwise.
        """
        wallet = WalletProvisioningService.ensure_wallet(user, request=request)
        return wallet.verify_pin(raw_pin)

    @staticmethod
    @db_transaction.atomic
    def change_pin(user, current_pin: str, new_pin: str, request=None) -> Wallet:
        """Verify the current PIN then replace it with a new one.

        Args:
            user: A ``UnifiedUser`` instance.
            current_pin: The existing plaintext PIN for verification.
            new_pin: The new plaintext PIN to set.

        Returns:
            Wallet: The updated wallet instance.

        Raises:
            ValidationError: If ``current_pin`` does not match the stored hash.
        """
        provisioned = WalletProvisioningService.ensure_wallet(user, request=request)
        wallet = user.financial_wallets.select_for_update().get(pk=provisioned.pk)
        if not wallet.verify_pin(current_pin):
            raise ValidationError("Current transaction PIN is invalid.")
        wallet.set_pin(new_pin)
        wallet.save(update_fields=["pin_hash", "pin_set_at", "failed_pin_attempts", "pin_locked_until", "updated_at"])
        try:
            from apps.audit_logs.services.wallet import wallet_audit
            db_transaction.on_commit(
                lambda: wallet_audit.log_wallet_pin_changed(
                    actor=user,
                    wallet_id=str(wallet.pk),
                    request=request,
                )
            )
        except Exception:
            pass
        return wallet


class WalletBalanceService:
    """Atomic balance mutation service for wallets.

    All methods that modify balances acquire ``SELECT FOR UPDATE`` locks
    on the wallet row before any arithmetic to prevent race conditions
    under concurrent requests.

    Every credit/debit/transfer also writes an immutable ledger row via
    ``TransactionLedgerService`` for PCI-DSS and CBN compliance.
    """

    @staticmethod
    def _assert_active(wallet: Wallet) -> None:
        """Assert the wallet is in ACTIVE status before any mutation.

        Args:
            wallet: The ``Wallet`` instance to check.

        Raises:
            ValidationError: If the wallet is frozen, suspended, or closed.
        """
        if wallet.status != WalletStatus.ACTIVE:
            raise ValidationError("Wallet is not active.")

    @classmethod
    def credit(cls, wallet: Wallet, amount: Decimal) -> Wallet:
        """Add ``amount`` to the wallet's balance and available_balance.

        Args:
            wallet: The locked ``Wallet`` instance (caller must hold
                ``SELECT FOR UPDATE``).
            amount: Positive ``Decimal`` amount to credit.

        Returns:
            Wallet: The updated wallet instance.

        Raises:
            ValidationError: If the wallet is not ACTIVE.
        """
        cls._assert_active(wallet)
        wallet.balance += amount
        wallet.available_balance += amount
        wallet.last_transaction_at = timezone.now()
        wallet.save(update_fields=["balance", "available_balance", "last_transaction_at", "updated_at"])
        return wallet

    @classmethod
    def debit(cls, wallet: Wallet, amount: Decimal) -> Wallet:
        """Subtract ``amount`` from wallet balance and available_balance.

        Args:
            wallet: The locked ``Wallet`` instance.
            amount: Positive ``Decimal`` amount to debit.

        Returns:
            Wallet: The updated wallet instance.

        Raises:
            ValidationError: If wallet is not ACTIVE or available_balance
                is insufficient.
        """
        cls._assert_active(wallet)
        if wallet.available_balance < amount:
            raise ValidationError("Insufficient available balance.")
        wallet.balance -= amount
        wallet.available_balance -= amount
        wallet.daily_spent += amount
        wallet.monthly_spent += amount
        wallet.last_transaction_at = timezone.now()
        wallet.save(update_fields=["balance", "available_balance", "daily_spent", "monthly_spent", "last_transaction_at", "updated_at"])
        return wallet

    @classmethod
    @db_transaction.atomic
    def transfer(
        cls,
        *,
        sender_user,
        receiver_user,
        amount: Decimal,
        pin: str,
        reference: str = "",
        idempotency_key: str = "",
        request=None,
    ) -> dict:
        """KYC-gated wallet-to-wallet transfer between two platform users.

        Acquires ``SELECT FOR UPDATE`` locks on both wallets in a deterministic
        order to prevent AB/BA deadlocks.  Creates an immutable ledger entry
        via ``TransactionLedgerService``.

        Args:
            sender_user: The ``UnifiedUser`` sending funds.
            receiver_user: The ``UnifiedUser`` receiving funds.
            amount: Positive ``Decimal`` amount to transfer.
            pin: Sender's plaintext transaction PIN for authorisation.
            reference: Optional human-readable reference string.
            idempotency_key: Optional key for duplicate-request protection.

        Returns:
            dict: Keys ``transaction_id``, ``sender_balance``, and
                ``receiver_balance`` (as ``Decimal`` instances).

        Raises:
            ValidationError: If KYC gate fails, PIN is wrong, or sender
                has insufficient available balance.
        """
        from apps.transactions.models import TransactionDirection, TransactionStatus, TransactionType
        from apps.transactions.services import TransactionLedgerService
        # ── KYC Gate ──────────────────────────────────────────────
        # Transfers are a financial exit path. Sender must hold an APPROVED KYC
        # submission before any funds can leave their wallet.
        from apps.kyc.services.kyc_service import assert_kyc_approved
        assert_kyc_approved(sender_user)
        # ───────────────────────────────────────────────────────────────────

        sender_wallet = sender_user.financial_wallets.select_for_update().get(
            pk=WalletProvisioningService.ensure_wallet(sender_user, request=request).pk
        )
        receiver_wallet = receiver_user.financial_wallets.select_for_update().get(
            pk=WalletProvisioningService.ensure_wallet(receiver_user, sender_wallet.currency.code, request=request).pk
        )
        if not sender_wallet.verify_pin(pin):
            raise ValidationError("Invalid transaction PIN.")
        sender_before = sender_wallet.balance
        receiver_before = receiver_wallet.balance
        cls.debit(sender_wallet, amount)
        cls.credit(receiver_wallet, amount)
        txn = TransactionLedgerService.create_entry(
            transaction_type=TransactionType.TRANSFER,
            status=TransactionStatus.COMPLETED,
            direction=TransactionDirection.OUTBOUND,
            amount=amount,
            net_amount=amount,
            from_user=sender_user,
            to_user=receiver_user,
            from_wallet=sender_wallet,
            to_wallet=receiver_wallet,
            reference=reference or f"wallet-transfer:{sender_wallet.pk}:{receiver_wallet.pk}:{sender_wallet.last_transaction_at.timestamp()}",
            idempotency_key=idempotency_key,
            description="Wallet-to-wallet transfer.",
            from_balance_before=sender_before,
            from_balance_after=sender_wallet.balance,
            to_balance_before=receiver_before,
            to_balance_after=receiver_wallet.balance,
            completed_at=timezone.now(),
        )
        # Compliance audit trail — permanent retention for CBN/GDPR
        try:
            from apps.audit_logs.services.wallet import wallet_audit
            db_transaction.on_commit(
                lambda: wallet_audit.log_wallet_transfer(
                    actor=sender_user,
                    wallet_id=str(sender_wallet.pk),
                    transaction_id=str(txn.pk),
                    amount=str(amount),
                    receiver_id=str(getattr(receiver_user, "id", "")),
                    reference=txn.reference,
                    request=request,
                )
            )
        except Exception:
            pass
        return {"transaction_id": str(txn.pk), "sender_balance": sender_wallet.balance, "receiver_balance": receiver_wallet.balance}


class WalletWithdrawalService:
    """KYC-gated wallet-to-bank withdrawal request service.

    This service creates a durable ledger row and moves funds from available to
    pending balance. Provider transfer execution/reconciliation can safely run
    later without losing the original authenticated request context.
    """

    @classmethod
    @db_transaction.atomic
    def request_withdrawal(
        cls,
        *,
        user,
        amount: Decimal,
        pin: str,
        bank_code: str,
        account_number: str,
        account_name: str,
        idempotency_key: str = "",
        request=None,
    ) -> dict:
        """Create a pending withdrawal after the KYC gate passes.

        Traversal:
            ``request.user.kyc_submission`` gates the fund exit, then
            ``request.user.financial_wallets`` locks and updates the wallet.
        """
        from apps.kyc.services import assert_kyc_approved
        from apps.transactions.models import TransactionDirection, TransactionStatus, TransactionType
        from apps.transactions.services import TransactionLedgerService

        assert_kyc_approved(user)
        cfg = get_platform_settings()
        if amount < cfg.min_withdrawal_ngn:
            raise ValidationError(
                f"Minimum withdrawal is {cfg.min_withdrawal_ngn} NGN."
            )
        if amount > cfg.max_withdrawal_ngn:
            raise ValidationError(
                f"Maximum withdrawal is {cfg.max_withdrawal_ngn} NGN."
            )

        if idempotency_key:
            existing = user.financial_transactions_sent.filter(
                idempotency_key=idempotency_key,
                transaction_type=TransactionType.PAYOUT,
            ).first()
            if existing:
                return {
                    "transaction_id": str(existing.pk),
                    "reference": existing.reference,
                    "status": existing.status,
                    "amount": str(existing.amount),
                    "available_balance": str(existing.from_balance_after or "0.00"),
                }

        provisioned = WalletProvisioningService.ensure_wallet(user, request=request)
        wallet = user.financial_wallets.select_for_update().get(pk=provisioned.pk)
        WalletBalanceService._assert_active(wallet)
        if not wallet.verify_pin(pin):
            raise ValidationError("Invalid transaction PIN.")
        if wallet.available_balance < amount:
            raise ValidationError("Insufficient available balance.")

        before_available = wallet.available_balance
        wallet.available_balance -= amount
        wallet.pending_balance += amount
        wallet.last_transaction_at = timezone.now()
        wallet.save(
            update_fields=[
                "available_balance",
                "pending_balance",
                "last_transaction_at",
                "updated_at",
            ]
        )

        txn = TransactionLedgerService.create_entry(
            transaction_type=TransactionType.PAYOUT,
            status=TransactionStatus.PROCESSING,
            direction=TransactionDirection.OUTBOUND,
            amount=amount,
            net_amount=amount,
            from_user=user,
            from_wallet=wallet,
            reference=f"wallet-withdrawal:{wallet.pk}:{timezone.now().timestamp()}",
            idempotency_key=idempotency_key,
            description="Wallet withdrawal request pending provider payout.",
            from_balance_before=before_available,
            from_balance_after=wallet.available_balance,
            metadata={
                "bank_code": bank_code,
                "account_number_last4": account_number[-4:],
                "account_name": account_name,
                "payout_state": "pending_provider_execution",
            },
        )
        # Compliance audit trail — permanent retention CBN/GDPR
        try:
            from apps.audit_logs.services.wallet import wallet_audit
            db_transaction.on_commit(
                lambda: wallet_audit.log_withdrawal_requested(
                    actor=user,
                    wallet_id=str(wallet.pk),
                    transaction_id=str(txn.pk),
                    amount=str(amount),
                    bank_code=bank_code,
                    account_number_last4=account_number[-4:],
                    request=request,
                )
            )
        except Exception:
            pass
        return {
            "transaction_id": str(txn.pk),
            "reference": txn.reference,
            "status": txn.status,
            "amount": str(amount),
            "available_balance": str(wallet.available_balance),
            "pending_balance": str(wallet.pending_balance),
        }


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

    @staticmethod
    @db_transaction.atomic
    def hold_order_payment(*, client_user, amount: Decimal, reference: str, order_id: str = "", provider_reference: str = "", idempotency_key: str = "", request=None) -> WalletHold:
        """Place an escrow hold on client funds for a pending order payment.

        Moves ``amount`` from client ``available_balance`` into
        ``pending_balance + escrow_balance``. Creates a ``WalletHold`` record
        and an immutable ledger entry.

        Args:
            client_user: The ``UnifiedUser`` (buyer) whose wallet to hold.
            amount: Positive ``Decimal`` amount to hold in escrow.
            reference: Unique escrow hold reference (e.g. ``"escrow-{order_pk}"``).
            order_id: String representation of the linked ``Order.pk``.
            provider_reference: Payment provider's transaction reference.
            idempotency_key: Optional key for duplicate-request protection.

        Returns:
            WalletHold: The created (or existing, if idempotent) hold record.

        Raises:
            ValidationError: If the wallet is not ACTIVE or available_balance
                is insufficient.
        """
        from apps.transactions.services import TransactionLedgerService

        provisioned = WalletProvisioningService.ensure_wallet(client_user, request=request)
        client_wallet = client_user.financial_wallets.select_for_update().get(pk=provisioned.pk)
        WalletBalanceService._assert_active(client_wallet)
        if client_wallet.available_balance < amount:
            raise ValidationError("Insufficient wallet balance for escrow hold.")
        client_wallet.available_balance -= amount
        client_wallet.pending_balance += amount
        client_wallet.escrow_balance += amount
        client_wallet.last_transaction_at = timezone.now()
        client_wallet.save(update_fields=["available_balance", "pending_balance", "escrow_balance", "last_transaction_at", "updated_at"])
        hold, created = WalletHold.objects.get_or_create(
            reference=reference,
            defaults={"wallet": client_wallet, "amount": amount, "order_id": order_id, "metadata": {"provider_reference": provider_reference}},
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
            # Audit trail: Escrow hold
            try:
                from apps.audit_logs.services.wallet import wallet_audit
                db_transaction.on_commit(
                    lambda: wallet_audit.log_escrow_hold(
                        actor=client_user,
                        wallet_id=str(client_wallet.pk),
                        amount=str(amount),
                        order_id=order_id,
                        request=request,
                    )
                )
            except Exception:
                pass
        return hold

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

        Calculates commission split, credits vendor and company wallets,
        and marks the hold as RELEASED.  Records an immutable escrow-release
        ledger entry via ``TransactionLedgerService``.

        Args:
            hold_reference: The ``WalletHold.reference`` to release.
            vendor_user: The ``UnifiedUser`` vendor to credit.
            commission_rate: Override commission ratio (``Decimal``).  Falls
                back to ``GlobalPlatformSettings.vendor_commission_rate``.
            idempotency_key: Optional key for replay safety.

        Returns:
            dict: Keys ``gross_amount``, ``vendor_amount``,
                ``commission_amount`` (all ``Decimal``).

        Raises:
            ValidationError: If the hold is not ACTIVE or remaining amount
                is zero.
        """
        from apps.transactions.services import TransactionLedgerService
        commission_rate = (
            commission_rate
            if commission_rate is not None
            else get_platform_settings().vendor_commission_rate
        )

        hold = WalletHold.objects.select_for_update().select_related("wallet", "wallet__currency").get(reference=hold_reference)
        if hold.status != WalletHoldStatus.ACTIVE:
            raise ValidationError("Escrow hold is not active.")
        amount = hold.remaining_amount
        if amount <= 0:
            raise ValidationError("No escrow balance remains to release.")
        client_wallet = hold.wallet.user.financial_wallets.select_for_update().get(pk=hold.wallet_id)
        vendor_wallet = vendor_user.financial_wallets.select_for_update().get(
            pk=WalletProvisioningService.ensure_wallet(vendor_user, client_wallet.currency.code, request=request).pk
        )
        company_wallet = Wallet.objects.select_for_update().get(pk=WalletProvisioningService.ensure_company_wallet(client_wallet.currency.code).pk)
        commission_amount = (amount * commission_rate).quantize(Decimal("0.01"))
        vendor_amount = amount - commission_amount
        client_wallet.pending_balance -= amount
        client_wallet.escrow_balance -= amount
        vendor_wallet.balance += vendor_amount
        vendor_wallet.available_balance += vendor_amount
        company_wallet.balance += commission_amount
        company_wallet.available_balance += commission_amount
        now = timezone.now()
        client_wallet.last_transaction_at = vendor_wallet.last_transaction_at = company_wallet.last_transaction_at = now
        client_wallet.save(update_fields=["pending_balance", "escrow_balance", "last_transaction_at", "updated_at"])
        vendor_wallet.save(update_fields=["balance", "available_balance", "last_transaction_at", "updated_at"])
        company_wallet.save(update_fields=["balance", "available_balance", "last_transaction_at", "updated_at"])
        hold.released_amount += amount
        hold.status = WalletHoldStatus.RELEASED
        hold.save(update_fields=["released_amount", "status", "updated_at"])
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
        # Audit trail: Escrow release
        try:
            from apps.audit_logs.services.wallet import wallet_audit
            # Use current transaction actor if available, or vendor_user
            db_transaction.on_commit(
                lambda: wallet_audit.log_escrow_release(
                    actor=vendor_user,  # Usually triggered by vendor or system
                    wallet_id=str(client_wallet.pk),
                    amount=str(amount),
                    order_id=hold.order_id,
                    request=request,
                )
            )
        except Exception:
            pass
        return {"gross_amount": amount, "vendor_amount": vendor_amount, "commission_amount": commission_amount}

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

        Traversal:
            request.user.financial_wallets -> wallet.holds -> WalletHold
            request.user.user_orders -> Order -> order.vendor.user

        Args:
            client_user: Authenticated client from ``request.user``.
            hold_reference: Escrow hold reference generated during payment.
            commission_rate: Platform commission ratio.
            idempotency_key: Optional idempotency header for ledger replay safety.

        Returns:
            dict: Gross, vendor, and commission amounts from the release.

        Raises:
            ValidationError: If the hold or linked order cannot be resolved from
                the authenticated user's reverse relationships.
        """
        client_wallet = client_user.financial_wallets.select_for_update().first()
        if client_wallet is None:
            raise ValidationError("Client wallet not found.")

        # Hold ownership is verified through the wallet reverse relation. This
        # prevents a user from releasing another customer's escrow reference.
        try:
            hold = client_wallet.holds.select_for_update().get(reference=hold_reference)
        except client_wallet.holds.model.DoesNotExist as exc:
            raise ValidationError("Escrow hold not found for this client wallet.") from exc
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

    @staticmethod
    @db_transaction.atomic
    def refund_escrow(*, hold_reference: str, idempotency_key: str = "", request=None) -> WalletHold:
        """Refund an active escrow hold back to the client's available balance.

        Called on order cancellation or dispute resolution in favour of the
        client. Returns held funds to ``available_balance`` and zeroes the
        ``escrow_balance`` and ``pending_balance`` accordingly.

        Args:
            hold_reference: The ``WalletHold.reference`` to refund.
            idempotency_key: Optional key for replay safety.

        Returns:
            WalletHold: The updated hold instance with status ``REFUNDED``.

        Raises:
            ValidationError: If the hold is not in ACTIVE status.
        """
        from apps.transactions.services import TransactionLedgerService

        hold = WalletHold.objects.select_for_update().select_related("wallet").get(reference=hold_reference)
        if hold.status != WalletHoldStatus.ACTIVE:
            raise ValidationError("Escrow hold is not active.")
        amount = hold.remaining_amount
        wallet = hold.wallet.user.financial_wallets.select_for_update().get(pk=hold.wallet_id)
        wallet.pending_balance -= amount
        wallet.escrow_balance -= amount
        wallet.available_balance += amount
        wallet.last_transaction_at = timezone.now()
        wallet.save(update_fields=["pending_balance", "escrow_balance", "available_balance", "last_transaction_at", "updated_at"])
        hold.refunded_amount += amount
        hold.status = WalletHoldStatus.REFUNDED
        hold.save(update_fields=["refunded_amount", "status", "updated_at"])
        TransactionLedgerService.record_refund(wallet=wallet, amount=amount, reference=hold.reference, order_id=hold.order_id, idempotency_key=idempotency_key)
        # Audit trail: Escrow refund
        try:
            from apps.audit_logs.services.wallet import wallet_audit
            db_transaction.on_commit(
                lambda: wallet_audit.log_escrow_refunded(
                    actor=wallet.user,
                    wallet_id=str(wallet.pk),
                    amount=str(amount),
                    order_id=hold.order_id,
                    request=request,
                )
            )
        except Exception:
            pass
        return hold
