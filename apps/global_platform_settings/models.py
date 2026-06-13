# apps/global_platform_settings/models.py
"""
PlatformSettings — Global admin-configurable singleton model.

All business-critical platform parameters that were previously hardcoded as
Python constants (commission rates, fees, wallet limits, KYC policy) are
centralised here so they can be changed from the Django Admin without
a code redeployment.

Singleton Pattern:
    - Only one row is ever permitted (pk = 1, enforced in ``save()``).
    - ``post_migrate`` signal seeds a default row on first deployment.
    - Django Admin blocks the *Add* button when a row already exists.
    - Django Admin blocks *Delete* at all times.

Cache Layer:
    - Redis TTL = 60 seconds.  Short so fee changes propagate quickly
      across all horizontal processes.
    - ``cache.py`` exposes ``get_platform_settings()`` → Redis → DB.
    - ``post_save`` signal busts the cache key on every admin save.

Usage::

    from apps.global_platform_settings.cache import get_platform_settings

    cfg = get_platform_settings()
    rate = cfg.vendor_commission_rate          # Decimal e.g. Decimal("0.10")
    fee  = cfg.measurement_fee_ngn             # Decimal e.g. Decimal("1000.00")
    cod  = cfg.cod_platform_commission_rate    # Decimal e.g. Decimal("0.10")
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from django.core.cache import cache
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.common.models import TimeStampedModel

# ── Cache configuration ────────────────────────────────────────────────────────
PLATFORM_SETTINGS_CACHE_KEY = "fashionistar:global_platform_settings:v1"
PLATFORM_SETTINGS_CACHE_TTL = 60  # seconds — tight TTL so fee changes propagate fast

# ── Singleton sentinel ─────────────────────────────────────────────────────────
# A stable UUID used as the singleton PK.  Using a fixed UUID (not uuid7()) means
# the same row is always targeted on every save, enforcing the single-row invariant
# without needing an integer primary key.
SINGLETON_PK = uuid.UUID("00000000-0000-4000-8000-000000000001")


class PlatformSettings(TimeStampedModel):
    """
    Singleton model for global Fashionistar platform configuration.

    Inherits ``created_at`` and ``updated_at`` from ``TimeStampedModel``.
    Always access via ``get_platform_settings()`` from ``cache.py``.
    Never instantiate directly — use ``PlatformSettings.objects.get(pk=1)``
    only in admin or management commands.

    Attributes:
        vendor_commission_rate: Default fraction retained by Fashionistar on each sale.
        client_platform_fee_rate: Additional fee charged to clients per purchase.
        measurement_fee_ngn: Fixed NGN fee for MirrorSize precision measurement requests.
        advertisement_fee_ngn: Fixed NGN fee for vendor promoted listing slots.
        min_wallet_topup_ngn: Minimum single wallet top-up amount.
        max_wallet_topup_ngn: Maximum single wallet top-up amount (anti-fraud cap).
        min_withdrawal_ngn: Minimum payout / withdrawal amount.
        max_withdrawal_ngn: Maximum single withdrawal amount.
        max_daily_withdrawal_ngn: Aggregate daily withdrawal limit per user.
        cod_enabled: Toggle for Cash-on-Delivery payment method.
        in_store_payment_enabled: Toggle for in-store QR-token payment flow.
        cod_confirmation_window_hours: Deadline for vendor to confirm COD delivery.
        cod_platform_commission_rate: Commission rate applied to COD orders.
        kyc_max_retry_attempts: Max failed KYC attempts before lockout.
        kyc_lockout_hours: Lockout duration after exceeding retry limit.
        ngn_usd_rate: Fallback NGN→USD exchange rate (updated from admin panel).
        platform_name: Public-facing platform name.
        support_email: Customer-facing support email address.
        support_phone: Customer-facing support phone number.
        terms_url: URL to Terms & Conditions page.
        privacy_url: URL to Privacy Policy page.
    """

    # ── Commission & Fees ─────────────────────────────────────────────────────
    vendor_commission_rate = models.DecimalField(
        max_digits=5,
        decimal_places=4,
        default=Decimal("0.1000"),
        validators=[
            MinValueValidator(Decimal("0.0")),
            MaxValueValidator(Decimal("1.0")),
        ],
        verbose_name=_("Default Vendor Commission Rate"),
        help_text=_(
            "Fraction of each sale retained by Fashionistar as commission (e.g. 0.10 = 10%). "
            "Can be overridden per-vendor via CommissionRule."
        ),
    )
    client_platform_fee_rate = models.DecimalField(
        max_digits=5,
        decimal_places=4,
        default=Decimal("0.0000"),
        validators=[
            MinValueValidator(Decimal("0.0")),
            MaxValueValidator(Decimal("1.0")),
        ],
        verbose_name=_("Client Platform Fee Rate"),
        help_text=_(
            "Additional platform fee charged to clients on each purchase (e.g. 0.015 = 1.5%). "
            "Set to 0 to disable. Added on top of the order total."
        ),
    )
    measurement_fee_ngn = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("1000.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
        verbose_name=_("MirrorSize Measurement Fee (₦)"),
        help_text=_(
            "Amount in NGN charged to clients for each precision measurement request."
        ),
    )
    advertisement_fee_ngn = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("5000.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
        verbose_name=_("Vendor Advertisement Fee (₦)"),
        help_text=_("Amount charged to vendors for a standard promoted listing slot."),
    )
    default_free_shipping_threshold = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("50000.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
        verbose_name=_("Default Free Shipping Threshold (₦)"),
        help_text=_(
            "Fallback free shipping threshold in NGN. Overridden per product in shipping profiles."
        ),
    )

    # ── Wallet Limits ─────────────────────────────────────────────────────────
    min_wallet_topup_ngn = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("500.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
        verbose_name=_("Minimum Wallet Top-up (₦)"),
        help_text=_(
            "Minimum single top-up amount a client can fund their wallet with."
        ),
    )
    max_wallet_topup_ngn = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("5000000.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
        verbose_name=_("Maximum Wallet Top-up (₦)"),
        help_text=_("Maximum single top-up amount (anti-fraud cap)."),
    )
    min_withdrawal_ngn = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("1000.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
        verbose_name=_("Minimum Withdrawal Amount (₦)"),
        help_text=_(
            "Minimum amount a vendor or client can withdraw to their bank account."
        ),
    )
    max_withdrawal_ngn = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("2000000.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
        verbose_name=_("Maximum Single Withdrawal (₦)"),
        help_text=_("Maximum single withdrawal amount (anti-fraud / regulatory cap)."),
    )
    max_daily_withdrawal_ngn = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("5000000.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
        verbose_name=_("Maximum Daily Withdrawal (₦)"),
        help_text=_("Total withdrawal limit per user per calendar day."),
    )

    # ── Cash / COD Settings ───────────────────────────────────────────────────
    cod_enabled = models.BooleanField(
        default=True,
        verbose_name=_("Cash-on-Delivery Enabled"),
        help_text=_(
            "Allow clients to pay cash when the vendor delivers. "
            "Commission is still collected via wallet reconciliation at delivery confirmation."
        ),
    )
    in_store_payment_enabled = models.BooleanField(
        default=True,
        verbose_name=_("In-store / Shop Payment Enabled"),
        help_text=_(
            "Allow clients to pay at a vendor's physical shop. "
            "A QR confirmation token is required from the client to prevent bypass."
        ),
    )
    cod_confirmation_window_hours = models.PositiveSmallIntegerField(
        default=72,
        verbose_name=_("COD Confirmation Window (hours)"),
        help_text=_(
            "Hours within which a vendor must confirm COD delivery. "
            "After this window the platform auto-flags the order for review."
        ),
    )
    cod_platform_commission_rate = models.DecimalField(
        max_digits=5,
        decimal_places=4,
        default=Decimal("0.1000"),
        validators=[
            MinValueValidator(Decimal("0.0")),
            MaxValueValidator(Decimal("1.0")),
        ],
        verbose_name=_("COD Platform Commission Rate"),
        help_text=_(
            "Commission rate applied on cash / COD orders. "
            "Vendor must remit this fraction to Fashionistar wallet after delivery."
        ),
    )

    # ── KYC Settings ──────────────────────────────────────────────────────────
    kyc_max_retry_attempts = models.PositiveSmallIntegerField(
        default=3,
        verbose_name=_("KYC Max Retry Attempts"),
        help_text=_(
            "Number of times a user can retry a failed KYC verification before lockout."
        ),
    )
    kyc_lockout_hours = models.PositiveSmallIntegerField(
        default=24,
        verbose_name=_("KYC Lockout Duration (hours)"),
        help_text=_(
            "Hours a user is locked out of KYC submission after exceeding max retries."
        ),
    )

    # ── Exchange Rate ─────────────────────────────────────────────────────────
    ngn_usd_rate = models.DecimalField(
        max_digits=12,
        decimal_places=8,
        default=Decimal("0.00065000"),
        validators=[MinValueValidator(Decimal("0.000001"))],
        verbose_name=_("NGN → USD Exchange Rate"),
        help_text=_(
            "Fallback exchange rate used when live rate lookup fails. "
            "Update regularly. Format: 1 NGN = X USD."
        ),
    )

    # ── Platform Identity ─────────────────────────────────────────────────────
    platform_name = models.CharField(
        max_length=120,
        default="Fashionistar",
        verbose_name=_("Platform Name"),
    )
    support_email = models.EmailField(
        default="support@fashionistar.net",
        verbose_name=_("Support Email"),
        help_text=_("Customer-facing support email shown in transactional emails."),
    )
    support_phone = models.CharField(
        max_length=30,
        blank=True,
        default="+234 913 7654 300",
        verbose_name=_("Support Phone"),
    )
    terms_url = models.URLField(
        max_length=500,
        blank=True,
        default="https://fashionistar.net/terms",
        verbose_name=_("Terms & Conditions URL"),
    )
    privacy_url = models.URLField(
        max_length=500,
        blank=True,
        default="https://fashionistar.net/privacy",
        verbose_name=_("Privacy Policy URL"),
    )

    # ── Timestamps from TimeStampedModel ──────────────────────────────────────
    # created_at and updated_at are inherited from TimeStampedModel.
    # Do NOT add explicit DateTimeField definitions here.

    class Meta:
        app_label = "global_platform_settings"
        verbose_name = _("Platform Settings")
        verbose_name_plural = _("Platform Settings")

    def __str__(self) -> str:
        return (
            f"PlatformSettings ["
            f"commission={self.vendor_commission_rate}, "
            f"measurement=₦{self.measurement_fee_ngn}"
            f"]"
        )

    def save(self, *args, **kwargs) -> None:
        """Force singleton invariant: always save as ``SINGLETON_PK`` and bust the Redis cache.

        Sets ``self.pk`` to the stable sentinel UUID before every save so that
        Django always UPDATE-or-INSERT the same row regardless of how the object
        was constructed.

        Args:
            *args: Positional arguments forwarded to ``super().save()``.
            **kwargs: Keyword arguments forwarded to ``super().save()``.
        """
        self.pk = SINGLETON_PK  # Enforce singleton — only one UUID row may ever exist
        super().save(*args, **kwargs)
        # Bust cache immediately so updated rates propagate within the next request
        cache.delete(PLATFORM_SETTINGS_CACHE_KEY)

    def delete(self, *args, **kwargs):  # type: ignore[override]
        """Block deletion — the singleton row must persist.

        Args:
            *args: Ignored positional arguments.
            **kwargs: Ignored keyword arguments.

        Raises:
            NotImplementedError: Always. Reset to defaults via the admin panel instead.
        """
        raise NotImplementedError(
            "PlatformSettings cannot be deleted. Use the admin panel to reset to defaults."
        )
