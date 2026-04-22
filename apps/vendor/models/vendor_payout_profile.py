# apps/vendor/models/vendor_payout_profile.py
"""
VendorPayoutProfile — Bank account / payout details.

Encrypted at rest via field-level encryption (Fernet via cryptography lib).
Only the last 4 digits of the account number are stored in plain text
for display purposes.
"""
from django.db import models

from apps.common.models import TimeStampedModel, SoftDeleteModel


class VendorPayoutProfile(TimeStampedModel, SoftDeleteModel):
    """
    Bank/payout account details for a vendor.

    Sensitive fields (account_number_enc) must be encrypted before storage.
    The service layer handles encryption/decryption transparently.
    """

    # ── Relationship ───────────────────────────────────────────────
    vendor = models.OneToOneField(
        "vendor_domain.VendorProfile",
        on_delete=models.CASCADE,
        related_name="payout_profile",
        help_text="The VendorProfile this payout data belongs to.",
    )

    # ── Bank Details ───────────────────────────────────────────────
    bank_name    = models.CharField(max_length=150)
    bank_code    = models.CharField(max_length=10, blank=True, default="")
    account_name = models.CharField(
        max_length=200,
        help_text="Account holder name as it appears on the bank record.",
    )

    # Encrypted account number — do NOT store plain text
    account_number_enc = models.BinaryField(
        help_text="Fernet-encrypted account number.",
    )
    # Last 4 digits for display — safe to store plain
    account_last4 = models.CharField(max_length=4, blank=True, default="")

    # ── Paystack recipient code ────────────────────────────────────
    paystack_recipient_code = models.CharField(
        max_length=100,
        blank=True,
        default="",
        help_text="Paystack transfer recipient code for payouts.",
    )

    # ── Status ─────────────────────────────────────────────────────
    is_verified = models.BooleanField(
        default=False,
        help_text="Set True once Fashionistar finance team has verified the account.",
    )

    class Meta:
        verbose_name        = "Vendor Payout Profile"
        verbose_name_plural = "Vendor Payout Profiles"
        db_table            = "vendor_payout_profile"
        indexes = [
            models.Index(fields=["vendor"], name="vendor_payout_vendor_idx"),
        ]

    def __str__(self) -> str:
        return f"PayoutProfile(vendor={self.vendor_id}, bank={self.bank_name}, ***{self.account_last4})"
