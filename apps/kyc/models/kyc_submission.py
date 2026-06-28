# apps/kyc/models/kyc_submission.py
"""
KycSubmission — Root KYC record for a user.

Tracks the overall verification state per user (vendor OR client).
Links to individual document submissions via KycDocument.

Design decisions:
  - OneToOneField(user): one KYC submission per user. Resubmission reuses
    the same record (status reset to PENDING).
  - created_at added for audit trail consistency with TimeStampedModel.
  - mark_approved / mark_rejected are atomic model-level state transitions.
  - is_rejected / can_resubmit properties for frontend UX gating.

Activation: Run makemigrations kyc after adding "apps.kyc" to INSTALLED_APPS.
"""


from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from apps.common.models import TimeStampedModel


class KycStatus(models.TextChoices):
    PENDING = "pending", _("Pending Review")
    IN_REVIEW = "in_review", _("Under Review")
    APPROVED = "approved", _("Approved ✅")
    REJECTED = "rejected", _("Rejected ❌")
    RESUBMIT = "resubmit", _("Resubmission Required")


class KycSubmission(TimeStampedModel):
    """
    One KYC submission per user.

    Lifecycle:
      (initiate) → PENDING
                → (admin picks up) → IN_REVIEW
                → (admin approves) → APPROVED
                → (admin rejects)  → REJECTED | RESUBMIT
                → (user resubmits) → PENDING (cycle repeats)

    On approval:
      - VendorSetupState.id_verified = True  (vendor)
      - Withdrawal gates are lifted for the user

    External KYC Provider Integration:
      Supported providers: Smile Identity, Youverify, Dojah.
      provider_reference stores the external job/session ID for webhook matching.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="kyc_submission",
        verbose_name=_("User"),
        help_text=_(
            "PROTECT: KYC records are CBN/NDPR/GDPR compliance documents with a 7-year "
            "retention requirement. User deletion MUST NOT cascade-destroy this record. "
            "Use the admin anonymization action to null PII fields while retaining the "
            "compliance audit trail. Attempting to delete a user who has a KYC submission "
            "will raise ProtectedError — resolve via the anonymize_user management command."
        ),
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

    # Legal name — resolved from NIN/BVN/CAC documents by admin on approval.
    # Used to cross-validate bank account holder names at payout registration.
    # If blank, the bank account name check is advisory only.
    legal_name = models.CharField(
        max_length=200,
        blank=True,
        default="",
        help_text=_(
            "Full legal name as it appears on the government-issued ID (NIN/BVN/CAC). "
            "Set by admin staff on KYC approval. Used to cross-check bank account "
            "holder names when vendors register payout accounts."
        ),
    )

    # Staff reviewer notes (shown to the user on rejection)
    review_notes = models.TextField(blank=True, default="")

    # Timestamps
    submitted_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        app_label = "kyc"
        verbose_name = _("KYC Submission")
        verbose_name_plural = _("KYC Submissions")
        ordering = ["-submitted_at"]
        indexes = [
            models.Index(fields=["status"], name="kyc_submission_status_idx"),
            models.Index(fields=["user"], name="kyc_submission_user_idx"),
        ]

    def __str__(self) -> str:
        return f"KYC[{self.user}] — {self.status}"

    # ── Status Properties ──────────────────────────────────────────────────────

    @property
    def is_approved(self) -> bool:
        return self.status == KycStatus.APPROVED

    @property
    def is_pending(self) -> bool:
        return self.status in {KycStatus.PENDING, KycStatus.IN_REVIEW}

    @property
    def is_rejected(self) -> bool:
        return self.status in {KycStatus.REJECTED, KycStatus.RESUBMIT}

    @property
    def can_resubmit(self) -> bool:
        """True if the user can upload new documents to resubmit for review."""
        return self.status in {KycStatus.REJECTED, KycStatus.RESUBMIT}

    # ── State Transition Methods ───────────────────────────────────────────────

    def mark_approved(self, *, admin_user=None, provider_reference: str = "") -> None:
        """
        Transition to APPROVED status.
        Sets reviewed_at and optional provider_reference.
        Caller MUST be inside a transaction.atomic() block.
        """
        self.status = KycStatus.APPROVED
        self.reviewed_at = timezone.now()
        if provider_reference:
            self.provider_reference = provider_reference
        self.save(
            update_fields=["status", "reviewed_at", "provider_reference", "updated_at"]
        )

    def mark_rejected(
        self,
        *,
        admin_user=None,
        notes: str,
        allow_resubmit: bool = True,
    ) -> None:
        """
        Transition to REJECTED or RESUBMIT status.
        Sets review_notes and reviewed_at.
        Caller MUST be inside a transaction.atomic() block.

        Args:
            notes: Rejection reason shown to the user.
            allow_resubmit: If True → status = RESUBMIT (can resubmit).
                            If False → status = REJECTED (hard block).
        """
        self.status = KycStatus.RESUBMIT if allow_resubmit else KycStatus.REJECTED
        self.review_notes = notes
        self.reviewed_at = timezone.now()
        self.save(update_fields=["status", "review_notes", "reviewed_at", "updated_at"])

    def mark_in_review(self) -> None:
        """Transition to IN_REVIEW (admin has picked up the submission)."""
        self.status = KycStatus.IN_REVIEW
        self.save(update_fields=["status", "updated_at"])
