from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from apps.common.models import TimeStampedModel


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
