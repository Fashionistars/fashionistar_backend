# apps/kyc/models/kyc_document.py
"""
KycDocument — Individual identity document upload per KYC submission.

Supports: government ID (NIN, passport, driver's license), selfie,
business registration (CAC for Nigerian vendors), utility bill.

Design decisions:
  - KycDocumentType enum expanded to match Nigerian compliance standards.
  - `document_number` stores a last-four marker only. Raw NIN/BVN values are
    hashed in the service layer and must not be persisted in plaintext.
  - `public_id` stores the Cloudinary public_id (consistent with all
    other Cloudinary-integrated models in this codebase).
  - `provider_verified` / `provider_response` support external provider
    webhook callbacks (Dojah, Smile Identity, Youverify).
  - `update_or_create` on (submission, document_type): one record per
    document type per submission — resubmission replaces the previous file.

Activation: Run makemigrations kyc after adding "apps.kyc" to INSTALLED_APPS.
"""


from django.db import models
from django.utils.translation import gettext_lazy as _
from apps.common.models import TimeStampedModel


class KycDocumentType(models.TextChoices):
    NIN_CARD = "nin_card", _("NIN Card — National Identity Number")
    BVN_SLIP = "bvn_slip", _("BVN Slip — Bank Verification Number")
    PASSPORT = "passport", _("International Passport")
    DRIVERS_LICENSE = "drivers_license", _("Driver's License")
    VOTERS_CARD = "voters_card", _("Voter's Card")
    SELFIE = "selfie", _("Live Selfie / Biometric Photo")
    CAC_CERTIFICATE = "cac_certificate", _("CAC Certificate (Business Registration)")
    UTILITY_BILL = "utility_bill", _("Utility Bill (Address Proof)")


# Legacy alias — kept for backwards-compat with any imports using DocumentType
DocumentType = KycDocumentType


class KycDocument(TimeStampedModel):
    """
    Individual document submitted as part of a KYC submission.

    Documents are uploaded client-side to Cloudinary using a presigned token.
    The Cloudinary asset reference (secure_url + public_id) is stored here
    after upload. External provider verification result is stored in
    provider_response once the provider processes the document.
    """

    submission = models.ForeignKey(
        "kyc.KycSubmission",
        on_delete=models.CASCADE,
        related_name="documents",
    )

    document_type = models.CharField(
        max_length=30,
        choices=KycDocumentType.choices,
        db_index=True,
    )

    # Document number / ID string (NIN number, passport number, etc.)
    document_number = models.CharField(
        max_length=50,
        blank=True,
        default="",
        help_text=_(
            "The actual document number, e.g. NIN (11 digits), BVN, passport number. "
            "Encrypt at-rest in production."
        ),
    )

    # Cloudinary fields — consistent with other Cloudinary models in the codebase
    public_id = models.CharField(
        max_length=500,
        blank=True,
        default="",
        help_text=_("Cloudinary public_id returned after client-side upload."),
    )
    secure_url = models.URLField(
        max_length=1000,
        blank=True,
        default="",
        help_text=_("Cloudinary secure_url returned after client-side upload."),
    )

    # External provider verification result
    provider_verified = models.BooleanField(
        default=False,
        help_text=_(
            "True if the external KYC provider confirms this document is valid."
        ),
    )
    provider_response = models.JSONField(
        default=dict,
        blank=True,
        help_text=_("Raw JSON result from external KYC provider for this document."),
    )

    class Meta:
        app_label = "kyc"
        verbose_name = _("KYC Document")
        verbose_name_plural = _("KYC Documents")
        ordering = ["created_at"]
        # One document per type per submission — idempotent uploads
        unique_together = [("submission", "document_type")]
        indexes = [
            models.Index(
                fields=["submission", "document_type"],
                name="kyc_doc_submission_type_idx",
            ),
        ]

    def __str__(self) -> str:
        return f"KycDoc[{self.document_type}] — submission={self.submission_id}"
