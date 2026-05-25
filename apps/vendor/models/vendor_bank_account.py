# apps/vendor/models/vendor_bank_account.py
"""
VendorBankAccount — Multi-bank-account payout destinations for a vendor.

Design decisions:
  - ForeignKey to VendorProfile (not OneToOneField) allows up to MAX_BANK_ACCOUNTS
    saved accounts per vendor — consistent with the legacy Paystack app which also
    supported multiple accounts.
  - account_number_enc (BinaryField, Fernet): the raw NUBAN is NEVER stored in plain
    text. Only account_last4 is safe for display, consistent with VendorPayoutProfile.
  - paystack_recipient_code has a UniqueConstraint to prevent two vendors registering
    the same bank account.
  - kyc_name_matched: advisory flag set by the service layer after comparing the
    Paystack-resolved account_name against KycSubmission.legal_name. If no KYC
    legal_name is on file the flag stays False and the account is still saved.
  - is_default: at most one account per vendor can be default. The service layer
    enforces this with select_for_update + update().
  - SoftDeleteModel: deletion sets deleted_at rather than DELETing the row, which
    preserves the payout audit trail (CBN / NDPR requirement).
"""
from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.common.models import TimeStampedModel, SoftDeleteModel

MAX_BANK_ACCOUNTS = 5


class BankAccountVerificationStatus(models.TextChoices):
    PENDING  = "pending",  _("Pending Verification")
    VERIFIED = "verified", _("Verified ✅")
    FAILED   = "failed",   _("Verification Failed ❌")


class VendorBankAccount(TimeStampedModel, SoftDeleteModel):
    """
    One saved bank account / payout destination for a vendor.

    A vendor can save up to MAX_BANK_ACCOUNTS (5) distinct bank accounts.
    Each one is registered with Paystack as a Transfer Recipient before being
    stored here, so payouts can be initiated by recipient_code alone — the
    account number never leaves the backend after initial registration.

    Lifecycle:
      1. Vendor submits (account_number, bank_code) in the frontend.
      2. Backend calls POST /api/v1/vendor/bank-accounts/resolve/ to get account_name.
      3. Backend calls Paystack POST /transferrecipient → stores recipient_code.
      4. account_number is Fernet-encrypted → stored in account_number_enc.
      5. KYC name cross-check → sets kyc_name_matched.
      6. Record is saved here.
      7. Payout: VendorPayoutService.initiate() uses recipient_code directly.
    """

    # ── Relationship ─────────────────────────────────────────────────────
    vendor = models.ForeignKey(
        "vendor.VendorProfile",
        on_delete=models.CASCADE,
        related_name="bank_accounts",
        help_text="The VendorProfile this bank account belongs to.",
    )

    # ── Bank Details (display-safe) ───────────────────────────────────────
    bank_name = models.CharField(
        max_length=150,
        help_text="Human-readable bank name, e.g. 'Access Bank'.",
    )
    bank_code = models.CharField(
        max_length=10,
        blank=True,
        default="",
        help_text="Paystack bank code, e.g. '044'.",
    )
    account_name = models.CharField(
        max_length=200,
        help_text="Account holder name as verified by Paystack resolve API.",
    )

    # ── Encrypted Account Number ──────────────────────────────────────────
    account_number_enc = models.BinaryField(
        blank=True,
        default=b"",
        help_text="Fernet-encrypted NUBAN account number. NEVER store plain text.",
    )
    account_last4 = models.CharField(
        max_length=4,
        blank=True,
        default="",
        help_text="Last 4 digits of the account number — safe to display.",
    )

    # ── Paystack Integration ──────────────────────────────────────────────
    paystack_recipient_code = models.CharField(
        max_length=120,
        blank=True,
        default="",
        db_index=True,
        help_text="Paystack Transfer Recipient code (RCP_xxx). Used for payouts.",
    )

    # ── KYC Cross-Check ───────────────────────────────────────────────────
    kyc_name_matched = models.BooleanField(
        default=False,
        help_text=(
            "True if account_name (from Paystack resolve) matches the vendor's "
            "KYC-approved legal name (KycSubmission.legal_name). Advisory only — "
            "does NOT block saving the account."
        ),
    )

    # ── Status & Priority ─────────────────────────────────────────────────
    is_default = models.BooleanField(
        default=False,
        db_index=True,
        help_text="True for the vendor's primary payout account.",
    )
    verification_status = models.CharField(
        max_length=20,
        choices=BankAccountVerificationStatus.choices,
        default=BankAccountVerificationStatus.PENDING,
        db_index=True,
    )

    class Meta:
        app_label = "vendor"
        verbose_name = "Vendor Bank Account"
        verbose_name_plural = "Vendor Bank Accounts"
        ordering = ["-is_default", "-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["paystack_recipient_code"],
                condition=models.Q(deleted_at__isnull=True)
                & ~models.Q(paystack_recipient_code=""),
                name="vendor_bank_account_unique_recipient_code",
            ),
        ]
        indexes = [
            models.Index(fields=["vendor", "is_default"], name="vba_vendor_default_idx"),
            models.Index(fields=["vendor", "verification_status"], name="vba_vendor_status_idx"),
        ]

    def __str__(self) -> str:
        return (
            f"BankAccount(vendor={self.vendor_id}, "
            f"bank={self.bank_name}, ***{self.account_last4})"
        )

    def clean(self) -> None:
        """Enforce max bank account limit at the model level."""
        if not self.pk:
            existing = (
                VendorBankAccount.objects.filter(
                    vendor=self.vendor,
                    deleted_at__isnull=True,
                ).count()
            )
            if existing >= MAX_BANK_ACCOUNTS:
                raise ValidationError(
                    _(
                        f"A vendor can have at most {MAX_BANK_ACCOUNTS} saved bank accounts. "
                        "Please delete an existing account before adding a new one."
                    )
                )

    def save(self, *args, **kwargs) -> None:
        self.full_clean()
        super().save(*args, **kwargs)

    # ── Convenience Properties ────────────────────────────────────────────

    @property
    def masked_account(self) -> str:
        """Return '****1234' for UI display."""
        return f"****{self.account_last4}" if self.account_last4 else "****"

    @property
    def is_verified(self) -> bool:
        return self.verification_status == BankAccountVerificationStatus.VERIFIED
