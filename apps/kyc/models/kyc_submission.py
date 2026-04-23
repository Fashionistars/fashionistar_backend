# apps/kyc/models/kyc_submission.py
"""
KycSubmission — Root KYC record for a user.

Tracks the overall verification state per user (vendor OR client).
Links to individual document submissions via KycDocument.

Activation: Run makemigrations kyc after adding "apps.kyc" to INSTALLED_APPS.
"""
import uuid

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


class KycStatus(models.TextChoices):
    PENDING    = "pending",    _("Pending Review")
    IN_REVIEW  = "in_review",  _("Under Review")
    APPROVED   = "approved",   _("Approved ✅")
    REJECTED   = "rejected",   _("Rejected ❌")
    RESUBMIT   = "resubmit",   _("Resubmission Required")


class KycSubmission(models.Model):
    """
    One KYC submission per user.
    On approval:
      - VendorSetupState.id_verified = True  (vendor)
      - ClientProfile signals / flags updated (client)

    External KYC Provider Integration (future):
      Supported providers: Smile Identity, Youverify, Dojah, Trulioo.
      provider_reference stores the external job/session ID for webhook matching.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="kyc_submission",
        verbose_name=_("User"),
    )

    status = models.CharField(
        max_length=20,
        choices=KycStatus.choices,
        default=KycStatus.PENDING,
        db_index=True,
    )

    # External provider reference (Smile ID job_id, Dojah request_id, etc.)
    provider_reference = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text=_("External KYC provider job/session reference ID."),
    )

    # Staff reviewer notes
    review_notes = models.TextField(blank=True, default="")

    # Timestamps
    submitted_at = models.DateTimeField(auto_now_add=True)
    reviewed_at  = models.DateTimeField(null=True, blank=True)
    updated_at   = models.DateTimeField(auto_now=True)

    class Meta:
        app_label  = "kyc"
        verbose_name = _("KYC Submission")
        verbose_name_plural = _("KYC Submissions")
        ordering   = ["-submitted_at"]
        indexes    = [
            models.Index(fields=["status"], name="kyc_submission_status_idx"),
            models.Index(fields=["user"], name="kyc_submission_user_idx"),
        ]

    def __str__(self) -> str:
        return f"KYC[{self.user}] — {self.status}"

    @property
    def is_approved(self) -> bool:
        return self.status == KycStatus.APPROVED

    @property
    def is_pending(self) -> bool:
        return self.status in {KycStatus.PENDING, KycStatus.IN_REVIEW}
