# apps/measurements/models/scan.py
"""
BodyScanSession + MeasurementShareToken + MeasurementAccessLog.

Architecture Rules:
  - BodyScanSession: TimeStampedModel (no soft-delete — scans are transient).
  - MeasurementShareToken: TimeStampedModel + explicit revocation fields.
    GDPR lawful basis: explicit consent (Article 6(1)(a)).
  - MeasurementAccessLog: TimeStampedModel, NEVER soft-deleted, 3yr retention.
  - All token consumption is recorded in MeasurementAccessLog (GDPR audit).
  - Mutations live in apps/measurements/services/; no business logic here.
  - fields_allowed in MeasurementShareToken enables field-level consent:
    clients choose exactly which measurements to expose to each vendor.

Token lifecycle:
  1. Client grants share (POST /api/v1/measurements/profiles/{pk}/share/)
  2. Token created → measurement_share_notification Celery task fires.
  3. Vendor reads (GET /api/v1/ninja/measurements/shared/{token}/)
     → access logged in MeasurementAccessLog.
  4. Token expires (expires_at) OR client revokes (is_revoked=True).
"""

from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.common.models import TimeStampedModel


class BodyScanSession(TimeStampedModel):
    """
    AI-powered body scan session.

    Integrates with MirrorSize API or internal camera ML model.
    On status=COMPLETED, the service layer creates a MeasurementProfile
    populated from extracted_measurements.

    Status transitions:
      PENDING → PROCESSING → COMPLETED
                           ↘ FAILED

    Attributes:
        owner: Client who initiated the scan.
        session_id: External-facing immutable UUID (used in API URLs).
        device_type: ios / android / web.
        scan_provider: mirrorsize / manual / ai_camera.
        status: Scan pipeline status.
        raw_data_url: Provider or Cloudinary storage URL for raw scan data.
        scan_confidence: Provider confidence score (0.0–1.0).
        extracted_measurements: JSON dict mirroring MeasurementProfile fields.
        measurement_profile: Created MeasurementProfile once scan completes.
        processing_started_at: Set when Celery task picks up the scan.
        completed_at: Set on COMPLETED or FAILED.
        error_message: Filled on FAILED status.
        ip_address: Client IP for audit.
        user_agent: Client UA string for fraud/audit.
    """

    class DeviceType(models.TextChoices):
        IOS = "ios", _("iOS")
        ANDROID = "android", _("Android")
        WEB = "web", _("Web")

    class ScanProvider(models.TextChoices):
        MIRRORSIZE = "mirrorsize", _("MirrorSize")
        MANUAL = "manual", _("Manual Entry")
        AI_CAMERA = "ai_camera", _("AI Camera")

    class Status(models.TextChoices):
        PENDING = "pending", _("Pending")
        PROCESSING = "processing", _("Processing")
        COMPLETED = "completed", _("Completed")
        FAILED = "failed", _("Failed")

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="scan_sessions",
        verbose_name=_("Owner"),
    )
    session_id = models.UUIDField(
        unique=True,
        default=uuid.uuid4,
        editable=False,
        db_index=True,
        verbose_name=_("Session ID"),
    )
    device_type = models.CharField(
        max_length=10,
        choices=DeviceType.choices,
        verbose_name=_("Device Type"),
    )
    scan_provider = models.CharField(
        max_length=12,
        choices=ScanProvider.choices,
        verbose_name=_("Scan Provider"),
    )
    status = models.CharField(
        max_length=12,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
        verbose_name=_("Status"),
    )
    raw_data_url = models.CharField(
        max_length=500,
        blank=True,
        verbose_name=_("Raw Data URL"),
        help_text=_("Provider or Cloudinary URL for raw scan data."),
    )
    scan_confidence = models.FloatField(
        null=True,
        blank=True,
        verbose_name=_("Scan Confidence"),
        help_text=_("Provider confidence score 0.0–1.0."),
    )
    extracted_measurements = models.JSONField(
        default=dict,
        blank=True,
        verbose_name=_("Extracted Measurements"),
        help_text=_("JSON dict matching MeasurementProfile field names."),
    )
    measurement_profile = models.ForeignKey(
        "measurements.MeasurementProfile",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="source_scans",
        verbose_name=_("Measurement Profile"),
        help_text=_("Created after COMPLETED scan."),
    )

    # ── Audit timestamps ──────────────────────────────────────────────────────
    processing_started_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("Processing Started At"),
    )
    completed_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("Completed At"),
    )
    error_message = models.TextField(
        blank=True,
        verbose_name=_("Error Message"),
    )
    ip_address = models.GenericIPAddressField(
        null=True,
        blank=True,
        verbose_name=_("IP Address"),
    )
    user_agent = models.CharField(
        max_length=300,
        blank=True,
        verbose_name=_("User Agent"),
    )

    class Meta:
        verbose_name = _("Body Scan Session")
        verbose_name_plural = _("Body Scan Sessions")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["owner", "status"], name="scan_owner_status_idx"),
            models.Index(fields=["status", "created_at"], name="scan_status_created_idx"),
        ]

    def __str__(self) -> str:
        return f"Scan {self.session_id} [{self.status}] — {self.owner}"


class MeasurementShareToken(TimeStampedModel):
    """
    Secure, field-scoped, revocable measurement share token.

    Clients grant vendors access to a **subset** of their measurement fields
    without exposing the full profile directly.

    GDPR compliance:
      - Lawful basis: explicit consent (Article 6(1)(a)).
      - fields_allowed implements field-level data minimisation (Article 5(1)(c)).
      - Every access is recorded in MeasurementAccessLog.
      - Clients can revoke at any time (Article 7(3)).

    Attributes:
        profile: The MeasurementProfile being shared.
        vendor: Specific grantee VendorProfile. Null = any vendor via public link.
        granted_by: Client user who created this share.
        token: Immutable UUID shared as the access credential.
        fields_allowed: Subset of MeasurementProfile field names the client consented to.
        expires_at: Hard expiry datetime.
        is_revoked: True = access immediately blocked regardless of expires_at.
        revoked_at: Timestamp of revocation.
        revoked_reason: Optional reason logged for audit.
        accessed_count: Total number of accesses via this token.
        last_accessed_at: Timestamp of the most recent access.
    """

    profile = models.ForeignKey(
        "measurements.MeasurementProfile",
        on_delete=models.CASCADE,
        related_name="share_tokens",
        verbose_name=_("Measurement Profile"),
    )
    vendor = models.ForeignKey(
        "vendor.VendorProfile",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="received_measurement_tokens",
        verbose_name=_("Vendor"),
        help_text=_("Null = public link valid for any vendor."),
    )
    granted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="granted_measurement_shares",
        verbose_name=_("Granted By"),
    )
    token = models.UUIDField(
        unique=True,
        default=uuid.uuid4,
        editable=False,
        db_index=True,
        verbose_name=_("Token"),
    )
    fields_allowed = models.JSONField(
        default=list,
        verbose_name=_("Fields Allowed"),
        help_text=_(
            "Subset of MeasurementProfile field names the client consented to share. "
            "E.g. [\"bust\", \"waist\", \"hips\"]"
        ),
    )
    expires_at = models.DateTimeField(verbose_name=_("Expires At"))
    is_revoked = models.BooleanField(default=False, db_index=True, verbose_name=_("Revoked"))
    revoked_at = models.DateTimeField(null=True, blank=True, verbose_name=_("Revoked At"))
    revoked_reason = models.CharField(
        max_length=200,
        blank=True,
        verbose_name=_("Revocation Reason"),
    )
    accessed_count = models.PositiveIntegerField(
        default=0,
        verbose_name=_("Access Count"),
    )
    last_accessed_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("Last Accessed At"),
    )

    class Meta:
        verbose_name = _("Measurement Share Token")
        verbose_name_plural = _("Measurement Share Tokens")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["token"], name="mst_token_idx"),
            models.Index(fields=["vendor", "is_revoked"], name="mst_vendor_revoked_idx"),
            models.Index(fields=["profile", "is_revoked"], name="mst_profile_revoked_idx"),
            models.Index(fields=["expires_at", "is_revoked"], name="mst_expiry_idx"),
        ]

    def __str__(self) -> str:
        return f"ShareToken {self.token} [{self.profile}]"

    @property
    def is_active(self) -> bool:
        """True if token is not revoked and has not expired."""
        from django.utils import timezone
        return not self.is_revoked and self.expires_at > timezone.now()


class MeasurementAccessLog(TimeStampedModel):
    """
    GDPR-compliant immutable audit log for measurement profile access.

    Every read of a shared measurement profile via a MeasurementShareToken
    is recorded here for compliance and client transparency.

    Retention: 3 years (per platform data retention policy).
    NEVER soft-deleted. Hard-delete only via scheduled GDPR compliance job.

    Attributes:
        share_token: The token used for this access.
        accessor: The vendor user who accessed the data.
        accessor_ip: IP address of the accessor for fraud/audit.
        accessed_fields: Fields actually served in this access (may be subset of fields_allowed).
        access_purpose: Self-declared purpose recorded by the accessor's system.
        retention_expires_at: Auto-computed (created_at + 3 years).
    """

    share_token = models.ForeignKey(
        MeasurementShareToken,
        on_delete=models.CASCADE,
        related_name="access_logs",
        verbose_name=_("Share Token"),
    )
    accessor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="measurement_access_logs",
        verbose_name=_("Accessor"),
    )
    accessor_ip = models.GenericIPAddressField(verbose_name=_("Accessor IP"))
    accessed_fields = models.JSONField(
        default=list,
        verbose_name=_("Accessed Fields"),
        help_text=_("Fields actually served during this access."),
    )
    access_purpose = models.TextField(
        blank=True,
        verbose_name=_("Access Purpose"),
        help_text=_("Self-declared purpose by the accessor's system."),
    )
    retention_expires_at = models.DateTimeField(
        verbose_name=_("Retention Expires At"),
        help_text=_("Auto-set to created_at + 3 years at save time."),
    )

    class Meta:
        verbose_name = _("Measurement Access Log")
        verbose_name_plural = _("Measurement Access Logs")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["accessor", "created_at"], name="mal_accessor_created_idx"),
            models.Index(fields=["share_token", "created_at"], name="mal_token_created_idx"),
            models.Index(fields=["retention_expires_at"], name="mal_retention_idx"),
        ]

    def save(self, *args, **kwargs) -> None:
        """Auto-compute retention_expires_at = created_at + 3 years."""
        if not self.retention_expires_at:
            from datetime import timedelta
            from django.utils import timezone
            self.retention_expires_at = timezone.now() + timedelta(days=3 * 365)
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"AccessLog [{self.accessor}] → {self.share_token} @ {self.created_at}"
