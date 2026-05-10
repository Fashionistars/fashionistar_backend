from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import Count, DecimalField, Q, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone

from apps.common.models import TimeStampedModel

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractUser


class Currency(TimeStampedModel):
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=10, unique=True, db_index=True)
    symbol = models.CharField(max_length=10, default="₦")
    decimal_places = models.PositiveSmallIntegerField(default=2)
    is_active = models.BooleanField(default=True)
    exchange_rate_usd = models.DecimalField(max_digits=20, decimal_places=8, default=Decimal("1.00000000"))

    class Meta:
        verbose_name_plural = "Currencies"
        ordering = ["code"]

    def __str__(self) -> str:
        return f"{self.code} ({self.name})"


class WalletOwnerType(models.TextChoices):
    CLIENT = "client", "Client"
    VENDOR = "vendor", "Vendor"
    SUPPORT = "support", "Support"
    EDITOR = "editor", "Editor"
    MODERATOR = "moderator", "Moderator"
    ADMIN = "admin", "Admin"
    COMPANY = "company", "Fashionistar Company"


class WalletStatus(models.TextChoices):
    ACTIVE = "active", "Active"
    INACTIVE = "inactive", "Inactive"
    FROZEN = "frozen", "Frozen"
    SUSPENDED = "suspended", "Suspended"
    CLOSED = "closed", "Closed"


class Wallet(TimeStampedModel):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="financial_wallets",
        null=True,
        blank=True,
    )
    owner_type = models.CharField(max_length=20, choices=WalletOwnerType.choices, db_index=True)
    currency = models.ForeignKey(Currency, on_delete=models.PROTECT, related_name="wallets")
    name = models.CharField(max_length=120)
    account_number = models.CharField(max_length=30, blank=True, default="", db_index=True)
    account_name = models.CharField(max_length=160, blank=True, default="")
    bank_name = models.CharField(max_length=120, blank=True, default="Fashionistar Wallet")
    provider = models.CharField(max_length=40, blank=True, default="internal")
    provider_account_id = models.CharField(max_length=120, blank=True, default="", db_index=True)
    provider_metadata = models.JSONField(default=dict, blank=True)
    balance = models.DecimalField(max_digits=20, decimal_places=2, default=Decimal("0.00"))
    available_balance = models.DecimalField(max_digits=20, decimal_places=2, default=Decimal("0.00"))
    pending_balance = models.DecimalField(max_digits=20, decimal_places=2, default=Decimal("0.00"))
    escrow_balance = models.DecimalField(max_digits=20, decimal_places=2, default=Decimal("0.00"))
    status = models.CharField(max_length=20, choices=WalletStatus.choices, default=WalletStatus.ACTIVE, db_index=True)
    is_default = models.BooleanField(default=True)
    pin_hash = models.CharField(max_length=255, blank=True, default="")
    pin_set_at = models.DateTimeField(null=True, blank=True)
    failed_pin_attempts = models.PositiveSmallIntegerField(default=0)
    pin_locked_until = models.DateTimeField(null=True, blank=True)
    daily_limit = models.DecimalField(max_digits=20, decimal_places=2, null=True, blank=True)
    monthly_limit = models.DecimalField(max_digits=20, decimal_places=2, null=True, blank=True)
    daily_spent = models.DecimalField(max_digits=20, decimal_places=2, default=Decimal("0.00"))
    monthly_spent = models.DecimalField(max_digits=20, decimal_places=2, default=Decimal("0.00"))
    last_daily_reset = models.DateField(default=timezone.localdate)
    last_monthly_reset = models.DateField(default=timezone.localdate)
    last_transaction_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "owner_type", "currency", "is_default"],
                name="wallet_unique_default_user_role_currency",
            ),
            models.UniqueConstraint(
                fields=["owner_type", "currency", "is_default"],
                condition=models.Q(user__isnull=True, owner_type=WalletOwnerType.COMPANY),
                name="wallet_unique_company_currency",
            ),
        ]
        indexes = [
            models.Index(fields=["user", "owner_type"]),
            models.Index(fields=["owner_type", "status"]),
            models.Index(fields=["currency", "status"]),
        ]

    def __str__(self) -> str:
        owner = self.user_id or "company"
        return f"{self.name} [{owner}] {self.currency.code}"

    def clean(self):
        if self.owner_type == WalletOwnerType.COMPANY and self.user_id:
            raise ValidationError("Company wallets must not be tied to a user.")
        if self.owner_type != WalletOwnerType.COMPANY and not self.user_id:
            raise ValidationError("User-owned wallets require a user.")

    # ------------------------------------------------------------------
    # DATABASE-LEVEL SYNC CLASSMETHODS (DRF / Admin use)
    # ------------------------------------------------------------------

    @classmethod
    def get_or_create_for_user(
        cls,
        user: "AbstractUser",
        owner_type: str = WalletOwnerType.CLIENT,
    ) -> "Wallet":
        """Get or provision a wallet for user. Uses select_for_update for race safety.

        Args:
            user: Authenticated Django user.
            owner_type: One of WalletOwnerType choices.

        Returns:
            Wallet: The user's active wallet, creating if absent.
        """
        with transaction.atomic():
            # Reverse manager first: user.financial_wallets is the canonical
            # ownership path for all user wallet reads/writes. The fallback
            # direct Currency lookup is limited to reference data provisioning.
            wallet = (
                user.financial_wallets.select_for_update()
                .filter(owner_type=owner_type, is_default=True)
                .select_related("currency")
                .first()
            )
            if wallet is None:
                ngn, _ = Currency.objects.get_or_create(
                    code="NGN",
                    defaults={
                        "name": "Nigerian Naira",
                        "symbol": "₦",
                        "decimal_places": 2,
                    },
                )
                wallet = user.financial_wallets.create(
                    owner_type=owner_type,
                    currency=ngn,
                    name=f"{user.get_full_name() or user.email} Wallet",
                    is_default=True,
                )
        return wallet

    @classmethod
    def get_balance_snapshot(cls, user: "AbstractUser") -> dict[str, Any]:
        """Single-query balance snapshot via aggregate on reverse FK.

        Args:
            user: Authenticated Django user.

        Returns:
            dict with balance, available_balance, pending_balance, escrow_balance,
            status, has_pin, currency_code.
        """
        # Reverse FK read: request.user.financial_wallets -> Wallet, with
        # currency joined in the same SQL query for the dashboard card.
        qs = user.financial_wallets.filter(
            owner_type=WalletOwnerType.CLIENT,
            is_default=True,
        ).select_related("currency")
        wallet = qs.first()
        if wallet is None:
            return {
                "balance": "0.00",
                "available_balance": "0.00",
                "pending_balance": "0.00",
                "escrow_balance": "0.00",
                "status": "active",
                "has_pin": False,
                "currency_code": "NGN",
            }
        return {
            "id": str(wallet.pk),
            "name": wallet.name,
            "account_number": wallet.account_number,
            "account_name": wallet.account_name,
            "bank_name": wallet.bank_name,
            "provider": wallet.provider,
            "balance": str(wallet.balance),
            "available_balance": str(wallet.available_balance),
            "pending_balance": str(wallet.pending_balance),
            "escrow_balance": str(wallet.escrow_balance),
            "status": wallet.status,
            "has_pin": wallet.has_pin,
            "currency_code": wallet.currency.code,
            "currency_symbol": wallet.currency.symbol,
        }

    @classmethod
    def get_hold_stats(cls, user: "AbstractUser") -> dict[str, Any]:
        """Aggregate active hold stats using DB-level reverse-FK traversal.

        Traversal: user.financial_wallets → wallet.holds

        Args:
            user: Authenticated Django user.

        Returns:
            dict with active_holds_count, total_held_amount.
        """
        # Reverse FK read keeps hold stats scoped from the authenticated owner.
        wallet = user.financial_wallets.filter(
            owner_type=WalletOwnerType.CLIENT,
            is_default=True,
        ).first()
        if wallet is None:
            return {"active_holds_count": 0, "total_held_amount": "0.00"}

        agg = wallet.holds.filter(status="active").aggregate(
            active_count=Count("id"),
            total=Coalesce(Sum("amount"), Decimal("0.00"), output_field=DecimalField()),
        )
        return {
            "active_holds_count": agg["active_count"],
            "total_held_amount": str(agg["total"]),
        }

    # ------------------------------------------------------------------
    # DATABASE-LEVEL ASYNC CLASSMETHODS (Ninja / async endpoints)
    # ------------------------------------------------------------------

    @classmethod
    async def aget_or_create_for_user(
        cls,
        user: "AbstractUser",
        owner_type: str = WalletOwnerType.CLIENT,
    ) -> "Wallet":
        """Async: get or provision a wallet for user.

        Args:
            user: Authenticated Django user.
            owner_type: One of WalletOwnerType choices.

        Returns:
            Wallet: The user's active wallet, creating if absent.
        """
        wallet = await (
            user.financial_wallets.filter(owner_type=owner_type, is_default=True)
            .select_related("currency")
            .afirst()
        )
        if wallet is None:
            ngn, _ = await Currency.objects.aget_or_create(
                code="NGN",
                defaults={"name": "Nigerian Naira", "symbol": "₦", "decimal_places": 2},
            )
            wallet = await user.financial_wallets.acreate(
                owner_type=owner_type,
                currency=ngn,
                name=f"{user.get_full_name() or user.email} Wallet",
                is_default=True,
            )
        return wallet

    @classmethod
    async def aget_balance_snapshot(cls, user: "AbstractUser") -> dict[str, Any]:
        """Async single-query balance snapshot.

        Args:
            user: Authenticated Django user.

        Returns:
            dict with all balance fields, status, has_pin, and currency info.
        """
        wallet = await (
            user.financial_wallets.filter(
                owner_type=WalletOwnerType.CLIENT,
                is_default=True,
            )
            .select_related("currency")
            .afirst()
        )
        if wallet is None:
            return {
                "balance": "0.00",
                "available_balance": "0.00",
                "pending_balance": "0.00",
                "escrow_balance": "0.00",
                "status": "active",
                "has_pin": False,
                "currency_code": "NGN",
            }
        return {
            "id": str(wallet.pk),
            "name": wallet.name,
            "account_number": wallet.account_number,
            "account_name": wallet.account_name,
            "bank_name": wallet.bank_name,
            "provider": wallet.provider,
            "balance": str(wallet.balance),
            "available_balance": str(wallet.available_balance),
            "pending_balance": str(wallet.pending_balance),
            "escrow_balance": str(wallet.escrow_balance),
            "status": wallet.status,
            "has_pin": wallet.has_pin,
            "currency_code": wallet.currency.code,
            "currency_symbol": wallet.currency.symbol,
        }

    @classmethod
    async def aget_hold_stats(cls, user: "AbstractUser") -> dict[str, Any]:
        """Async DB-level hold aggregation via reverse FK traversal.

        Traversal: user.financial_wallets → wallet.holds

        Args:
            user: Authenticated Django user.

        Returns:
            dict with active_holds_count and total_held_amount.
        """
        wallet = await user.financial_wallets.filter(
            owner_type=WalletOwnerType.CLIENT,
            is_default=True,
        ).afirst()
        if wallet is None:
            return {"active_holds_count": 0, "total_held_amount": "0.00"}

        agg = await wallet.holds.filter(status="active").aaggregate(
            active_count=Count("id"),
            total=Coalesce(Sum("amount"), Decimal("0.00"), output_field=DecimalField()),
        )
        return {
            "active_holds_count": agg["active_count"],
            "total_held_amount": str(agg["total"]),
        }

    @classmethod
    async def aget_full_dashboard_data(cls, user: "AbstractUser") -> dict[str, Any]:
        """Async full wallet dashboard: balance + hold stats in 2 targeted DB queries.

        Replaces N+1 patterns in selectors with database-first computation.

        Args:
            user: Authenticated Django user.

        Returns:
            dict combining balance snapshot and hold statistics.
        """
        balance = await cls.aget_balance_snapshot(user)
        holds = await cls.aget_hold_stats(user)
        return {**balance, **holds}

    # ------------------------------------------------------------------
    # INSTANCE PIN HELPERS (unchanged)
    # ------------------------------------------------------------------

    @property
    def has_pin(self) -> bool:
        return bool(self.pin_hash)

    def set_pin(self, raw_pin: str) -> None:
        if not raw_pin.isdigit() or len(raw_pin) != 4:
            raise ValidationError("Transaction PIN must be exactly 4 digits.")
        self.pin_hash = make_password(raw_pin)
        self.pin_set_at = timezone.now()
        self.failed_pin_attempts = 0
        self.pin_locked_until = None

    def verify_pin(self, raw_pin: str) -> bool:
        if self.pin_locked_until and self.pin_locked_until > timezone.now():
            return False
        ok = bool(self.pin_hash) and check_password(raw_pin, self.pin_hash)
        if ok:
            self.failed_pin_attempts = 0
            self.pin_locked_until = None
        else:
            self.failed_pin_attempts += 1
            if self.failed_pin_attempts >= 3:
                self.pin_locked_until = timezone.now() + timedelta(minutes=15)
        self.save(update_fields=["failed_pin_attempts", "pin_locked_until", "updated_at"])
        return ok



class WalletHoldStatus(models.TextChoices):
    ACTIVE = "active", "Active"
    RELEASED = "released", "Released"
    REFUNDED = "refunded", "Refunded"
    CANCELLED = "cancelled", "Cancelled"


class WalletHold(TimeStampedModel):
    wallet = models.ForeignKey(Wallet, on_delete=models.PROTECT, related_name="holds")
    amount = models.DecimalField(max_digits=20, decimal_places=2)
    released_amount = models.DecimalField(max_digits=20, decimal_places=2, default=Decimal("0.00"))
    refunded_amount = models.DecimalField(max_digits=20, decimal_places=2, default=Decimal("0.00"))
    reference = models.CharField(max_length=120, unique=True, db_index=True)
    order_id = models.CharField(max_length=120, blank=True, default="", db_index=True)
    status = models.CharField(max_length=20, choices=WalletHoldStatus.choices, default=WalletHoldStatus.ACTIVE, db_index=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["wallet", "status"]),
            models.Index(fields=["order_id", "status"]),
        ]

    @property
    def remaining_amount(self) -> Decimal:
        return self.amount - self.released_amount - self.refunded_amount
