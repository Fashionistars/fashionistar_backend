# apps/vendor/models/vendor_setup_state.py
"""
VendorSetupState — Multi-step onboarding tracker.

IMPORTANT PRODUCT DECISION:
  KYC (id_verified step) is EXCLUDED from the onboarding completion check.
  Vendors get full dashboard + product creation access immediately after
  completing profile_complete + bank_details + first_product.

  id_verified is a FUTURE field, reserved for the dedicated KYC app which
  will call an external KYC API (Youverify / Smile Identity) in a separate
  sprint. It defaults to False and does NOT gate any current functionality.

Steps (in order):
  1. profile_complete  — store name, description, logo uploaded
  2. bank_details      — payout bank account added
  3. id_verified       — FUTURE: KYC via external verification API (does NOT block dashboard)
  4. first_product     — at least one product listed
  5. onboarding_done   — steps 1 + 2 + 4 complete; store goes live

Completion formula (current):
  onboarding_done = profile_complete AND bank_details AND first_product
  (id_verified is informational only — does NOT block any access)
"""
from django.db import models

from apps.common.models import TimeStampedModel


class VendorSetupState(TimeStampedModel):
    """
    One row per vendor — tracks which onboarding milestones are complete.

    The vendor gains FULL dashboard access immediately upon registration.
    No gate exists between registration and product creation.
    """

    vendor = models.OneToOneField(
        "vendor_domain.VendorProfile",
        on_delete=models.CASCADE,
        related_name="setup_state",
        help_text="The VendorProfile this setup state belongs to.",
    )

    # ── Milestone flags ────────────────────────────────────────────
    profile_complete = models.BooleanField(default=False)
    bank_details     = models.BooleanField(default=False)

    # FUTURE: KYC step — reserved for dedicated KYC app + external API.
    # Does NOT block dashboard access or product creation.
    id_verified = models.BooleanField(
        default=False,
        help_text=(
            "FUTURE: government ID verified via external KYC API (Youverify/Smile Identity). "
            "Does NOT block dashboard or product creation — informational only."
        ),
    )

    first_product = models.BooleanField(default=False)
    onboarding_done = models.BooleanField(
        default=False,
        help_text=(
            "True once profile_complete + bank_details + first_product are all done. "
            "Store becomes fully visible on the marketplace."
        ),
    )

    # ── Current step pointer ───────────────────────────────────────
    current_step = models.PositiveSmallIntegerField(
        default=1,
        help_text="Step number (1–4) the vendor is currently on.",
    )

    class Meta:
        verbose_name        = "Vendor Setup State"
        verbose_name_plural = "Vendor Setup States"
        db_table            = "vendor_setup_state"

    def __str__(self) -> str:
        return f"SetupState(vendor={self.vendor_id}, step={self.current_step})"

    @property
    def completion_percentage(self) -> int:
        """
        Return setup completion as an integer percentage 0–100.
        Based on the 3 active steps (id_verified excluded from formula).
        """
        flags = [
            self.profile_complete,
            self.bank_details,
            self.first_product,
        ]
        done = sum(1 for f in flags if f)
        return int((done / len(flags)) * 100)

    def mark_profile_complete(self) -> None:
        """Mark profile setup step as done. Advances current_step if needed."""
        if not self.profile_complete:
            self.profile_complete = True
            self.current_step = max(self.current_step, 2)
            self.save(update_fields=["profile_complete", "current_step", "updated_at"])

    def mark_bank_details(self) -> None:
        """Mark bank/payout details step as done."""
        if not self.bank_details:
            self.bank_details = True
            self.current_step = max(self.current_step, 3)
            self.save(update_fields=["bank_details", "current_step", "updated_at"])

    def mark_first_product(self) -> None:
        """
        Mark first product listed.
        Triggers onboarding_done check (id_verified NOT required).
        """
        if not self.first_product:
            self.first_product = True
            self.current_step = max(self.current_step, 4)
            self._check_onboarding_done()

    def _check_onboarding_done(self) -> None:
        """
        Onboarding is done when profile + bank + first product are complete.
        id_verified is NEVER checked here — it is a future KYC-only concern.
        """
        if self.profile_complete and self.bank_details and self.first_product:
            self.onboarding_done = True
        self.save(update_fields=[
            "first_product", "onboarding_done", "current_step", "updated_at"
        ])
