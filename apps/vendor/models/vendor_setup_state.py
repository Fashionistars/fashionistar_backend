# apps/vendor/models/vendor_setup_state.py
"""
VendorSetupState — Multi-step onboarding tracker.

Tracks which onboarding steps a vendor has completed.
The frontend reads this to render the correct step in the setup wizard.

Steps (in order):
  1. profile_complete  — store name, description, logo uploaded
  2. bank_details      — payout bank account added
  3. id_verified       — government ID verified by staff
  4. first_product     — at least one product listed
  5. onboarding_done   — all steps complete; store goes live
"""
from django.db import models

from apps.common.models import TimeStampedModel


class VendorSetupState(TimeStampedModel):
    """
    One row per vendor — tracks which onboarding milestones are complete.
    """

    vendor = models.OneToOneField(
        "vendor_domain.VendorProfile",
        on_delete=models.CASCADE,
        related_name="setup_state",
        help_text="The VendorProfile this setup state belongs to.",
    )

    # ── Milestone flags ────────────────────────────────────────────
    profile_complete  = models.BooleanField(default=False)
    bank_details      = models.BooleanField(default=False)
    id_verified       = models.BooleanField(default=False)
    first_product     = models.BooleanField(default=False)
    onboarding_done   = models.BooleanField(
        default=False,
        help_text="Set True once ALL steps are complete. Store becomes visible.",
    )

    # ── Current step pointer ───────────────────────────────────────
    current_step = models.PositiveSmallIntegerField(
        default=1,
        help_text="Step number (1–5) the vendor is currently on.",
    )

    class Meta:
        verbose_name        = "Vendor Setup State"
        verbose_name_plural = "Vendor Setup States"
        db_table            = "vendor_setup_state"

    def __str__(self) -> str:
        return f"SetupState(vendor={self.vendor_id}, step={self.current_step})"

    @property
    def completion_percentage(self) -> int:
        """Return setup completion as an integer percentage 0–100."""
        flags = [
            self.profile_complete,
            self.bank_details,
            self.id_verified,
            self.first_product,
            self.onboarding_done,
        ]
        done = sum(1 for f in flags if f)
        return int((done / len(flags)) * 100)

    def mark_profile_complete(self) -> None:
        if not self.profile_complete:
            self.profile_complete = True
            self.current_step = max(self.current_step, 2)
            self.save(update_fields=["profile_complete", "current_step", "updated_at"])

    def mark_bank_details(self) -> None:
        if not self.bank_details:
            self.bank_details = True
            self.current_step = max(self.current_step, 3)
            self.save(update_fields=["bank_details", "current_step", "updated_at"])

    def mark_first_product(self) -> None:
        if not self.first_product:
            self.first_product = True
            self.current_step = max(self.current_step, 4)
            self._check_onboarding_done()

    def _check_onboarding_done(self) -> None:
        if all([self.profile_complete, self.bank_details, self.first_product]):
            self.onboarding_done = True
            self.current_step = 5
        self.save(update_fields=[
            "first_product", "onboarding_done", "current_step", "updated_at"
        ])
