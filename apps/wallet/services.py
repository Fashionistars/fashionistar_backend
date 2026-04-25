from __future__ import annotations

import secrets
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import transaction as db_transaction
from django.utils import timezone

from apps.wallet.models import Currency, Wallet, WalletHold, WalletHoldStatus, WalletOwnerType, WalletStatus

User = get_user_model()


class WalletProvisioningService:
    @staticmethod
    def ensure_currency(code: str = "NGN") -> Currency:
        currency, _ = Currency.objects.get_or_create(
            code=code.upper(),
            defaults={
                "name": "Nigerian Naira" if code.upper() == "NGN" else code.upper(),
                "symbol": "₦" if code.upper() == "NGN" else code.upper(),
                "decimal_places": 2,
                "exchange_rate_usd": Decimal("0.00065000") if code.upper() == "NGN" else Decimal("1.00000000"),
            },
        )
        return currency

    @staticmethod
    def owner_type_for_user(user) -> str:
        role = getattr(user, "role", WalletOwnerType.CLIENT)
        if role in {WalletOwnerType.VENDOR, WalletOwnerType.SUPPORT, WalletOwnerType.EDITOR, WalletOwnerType.MODERATOR, WalletOwnerType.ADMIN}:
            return role
        if role and role.startswith("super_"):
            return WalletOwnerType.ADMIN
        return WalletOwnerType.CLIENT

    @classmethod
    def ensure_wallet(cls, user, currency_code: str = "NGN") -> Wallet:
        currency = cls.ensure_currency(currency_code)
        owner_type = cls.owner_type_for_user(user)
        wallet, _ = Wallet.objects.get_or_create(
            user=user,
            owner_type=owner_type,
            currency=currency,
            is_default=True,
            defaults={
                "name": f"{owner_type.title()} Wallet",
                "account_name": str(getattr(user, "email", None) or getattr(user, "phone", "") or user.pk),
                "account_number": f"90{secrets.randbelow(10**8):08d}",
            },
        )
        return wallet

    @classmethod
    def ensure_company_wallet(cls, currency_code: str = "NGN") -> Wallet:
        currency = cls.ensure_currency(currency_code)
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
    @staticmethod
    @db_transaction.atomic
    def set_pin(user, raw_pin: str) -> Wallet:
        wallet = Wallet.objects.select_for_update().get(pk=WalletProvisioningService.ensure_wallet(user).pk)
        wallet.set_pin(raw_pin)
        wallet.save(update_fields=["pin_hash", "pin_set_at", "failed_pin_attempts", "pin_locked_until", "updated_at"])
        return wallet

    @staticmethod
    def verify_pin(user, raw_pin: str) -> bool:
        wallet = WalletProvisioningService.ensure_wallet(user)
        return wallet.verify_pin(raw_pin)

    @staticmethod
    @db_transaction.atomic
    def change_pin(user, current_pin: str, new_pin: str) -> Wallet:
        wallet = Wallet.objects.select_for_update().get(pk=WalletProvisioningService.ensure_wallet(user).pk)
        if not wallet.verify_pin(current_pin):
            raise ValidationError("Current transaction PIN is invalid.")
        wallet.set_pin(new_pin)
        wallet.save(update_fields=["pin_hash", "pin_set_at", "failed_pin_attempts", "pin_locked_until", "updated_at"])
        return wallet


class WalletBalanceService:
    @staticmethod
    def _assert_active(wallet: Wallet) -> None:
        if wallet.status != WalletStatus.ACTIVE:
            raise ValidationError("Wallet is not active.")

    @classmethod
    def credit(cls, wallet: Wallet, amount: Decimal) -> Wallet:
        cls._assert_active(wallet)
        wallet.balance += amount
        wallet.available_balance += amount
        wallet.last_transaction_at = timezone.now()
        wallet.save(update_fields=["balance", "available_balance", "last_transaction_at", "updated_at"])
        return wallet

    @classmethod
    def debit(cls, wallet: Wallet, amount: Decimal) -> Wallet:
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
    def transfer(cls, *, sender_user, receiver_user, amount: Decimal, pin: str, reference: str = "", idempotency_key: str = "") -> dict:
        from apps.transactions.models import TransactionDirection, TransactionStatus, TransactionType
        from apps.transactions.services import TransactionLedgerService

        sender_wallet = Wallet.objects.select_for_update().get(pk=WalletProvisioningService.ensure_wallet(sender_user).pk)
        receiver_wallet = Wallet.objects.select_for_update().get(pk=WalletProvisioningService.ensure_wallet(receiver_user, sender_wallet.currency.code).pk)
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
        return {"transaction_id": str(txn.pk), "sender_balance": sender_wallet.balance, "receiver_balance": receiver_wallet.balance}


class EscrowService:
    @staticmethod
    @db_transaction.atomic
    def hold_order_payment(*, client_user, amount: Decimal, reference: str, order_id: str = "", provider_reference: str = "", idempotency_key: str = "") -> WalletHold:
        from apps.transactions.services import TransactionLedgerService

        client_wallet = Wallet.objects.select_for_update().get(pk=WalletProvisioningService.ensure_wallet(client_user).pk)
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
        return hold

    @staticmethod
    @db_transaction.atomic
    def release_order_payment(*, hold_reference: str, vendor_user, commission_rate: Decimal = Decimal("0.10"), idempotency_key: str = "") -> dict:
        from apps.transactions.services import TransactionLedgerService

        hold = WalletHold.objects.select_for_update().select_related("wallet", "wallet__currency").get(reference=hold_reference)
        if hold.status != WalletHoldStatus.ACTIVE:
            raise ValidationError("Escrow hold is not active.")
        amount = hold.remaining_amount
        if amount <= 0:
            raise ValidationError("No escrow balance remains to release.")
        client_wallet = Wallet.objects.select_for_update().get(pk=hold.wallet_id)
        vendor_wallet = Wallet.objects.select_for_update().get(pk=WalletProvisioningService.ensure_wallet(vendor_user, client_wallet.currency.code).pk)
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
        return {"gross_amount": amount, "vendor_amount": vendor_amount, "commission_amount": commission_amount}

    @staticmethod
    @db_transaction.atomic
    def refund_escrow(*, hold_reference: str, idempotency_key: str = "") -> WalletHold:
        from apps.transactions.services import TransactionLedgerService

        hold = WalletHold.objects.select_for_update().select_related("wallet").get(reference=hold_reference)
        if hold.status != WalletHoldStatus.ACTIVE:
            raise ValidationError("Escrow hold is not active.")
        amount = hold.remaining_amount
        wallet = Wallet.objects.select_for_update().get(pk=hold.wallet_id)
        wallet.pending_balance -= amount
        wallet.escrow_balance -= amount
        wallet.available_balance += amount
        wallet.last_transaction_at = timezone.now()
        wallet.save(update_fields=["pending_balance", "escrow_balance", "available_balance", "last_transaction_at", "updated_at"])
        hold.refunded_amount += amount
        hold.status = WalletHoldStatus.REFUNDED
        hold.save(update_fields=["refunded_amount", "status", "updated_at"])
        TransactionLedgerService.record_refund(wallet=wallet, amount=amount, reference=hold.reference, order_id=hold.order_id, idempotency_key=idempotency_key)
        return hold
