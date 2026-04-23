# apps/kyc/models/kyc_document.py
"""
KycDocument — Individual identity document upload per KYC submission.

Supports: government ID (NIN, passport, driver's license), selfie,
business registration (CAC for Nigerian vendors), utility bill.

Activation: Run makemigrations kyc after adding "apps.kyc" to INSTALLED_APPS.
"""
import uuid

from django.db import models
from django.utils.translation import gettext_lazy as _


class DocumentType(models.TextChoices):
    NIN             = "nin",             _("NIN — National Identity Number")
    PASSPORT        = "passport",        _("International Passport")
    DRIVERS_LICENSE = "drivers_license", _("Driver's License")
    VOTERS_CARD     = "voters_card",     _("Voter's Card")
    SELFIE          = "selfie",          _("Live Selfie / Biometric")
    CAC_CERT        = "cac_cert",        _("CAC Certificate (Business Reg.)")
    UTILITY_BILL    = "utility_bill",    _("Utility Bill (Address Proof)")


class KycDocument(models.Model):
    """
    Individual document submitted as part of a KYC submission.
    Stored on Cloudinary via apps.common upload utilities.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    submission = models.ForeignKey(
        "kyc.KycSubmission",
        on_delete=models.CASCADE,
        related_name="documents",
    )

    document_type = models.CharField(
        max_length=30,
        choices=DocumentType.choices,
        db_index=True,
    )

    # Cloudinary public_id or secure_url (from apps.common.cloudinary_utils)
    cloudinary_public_id = models.CharField(max_length=500, blank=True, default="")
    secure_url           = models.URLField(max_length=1000, blank=True, default="")

    # External provider's result for this specific document
    provider_result = models.JSONField(
        default=dict,
        blank=True,
        help_text=_("Raw JSON result from external KYC provider for this document."),
    )

    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label  = "kyc"
        verbose_name = _("KYC Document")
        verbose_name_plural = _("KYC Documents")
        ordering   = ["uploaded_at"]
        indexes    = [
            models.Index(fields=["submission", "document_type"], name="kyc_doc_submission_type_idx"),
        ]

    def __str__(self) -> str:
        return f"KycDoc[{self.document_type}] — submission={self.submission_id}"
