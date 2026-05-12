# apps/common/models/processed_webhook.py
"""
CloudinaryProcessedWebhook — Audit trail for all Cloudinary webhook processing.

Records every webhook processed, including:
  - Idempotency key (for duplicate detection)
  - Asset metadata (type, source, target)
  - Model affected (avatar, product, category, etc)
  - Success/failure status
  - Processing time (for performance monitoring)

Used for:
  1. Debugging webhook issues
  2. Detecting duplicates (in conjunction with Redis cache)
  3. Audit logging and compliance
  4. Performance metrics (latency, throughput)
  5. Rate limiting (optional: limits per user/day)

Design:
  - Immutable once created (no updates)
  - Queryable by public_id, asset_type, model_target, processed_at
  - Indexes optimized for common queries
  - Simple retention policy: delete after 90 days (configurable)
"""

from __future__ import annotations

import logging
from django.db import models
from django.utils.translation import gettext_lazy as _

logger = logging.getLogger(__name__)


class CloudinaryProcessedWebhook(models.Model):
    """
    Audit trail entry for each Cloudinary webhook processed.
    
    Immutable once created. Used for:
      - Duplicate detection (in conjunction with Redis cache)
      - Performance monitoring
      - Audit/compliance
      - Debugging webhook issues
    """
    
    # ── Webhook identification ────────────────────────────────────
    idempotency_key = models.CharField(
        max_length=64,  # SHA256 hex string
        unique=True,
        db_index=True,
        help_text="SHA256(public_id + timestamp + asset_type) — prevents duplicates.",
    )
    
    public_id = models.CharField(
        max_length=500,
        db_index=True,
        help_text="Cloudinary public_id (includes folder path).",
    )
    
    payload_hash = models.CharField(
        max_length=64,
        help_text="SHA256 of the original webhook payload — for validation.",
    )
    
    # ── Asset metadata ────────────────────────────────────────────
    asset_type = models.CharField(
        max_length=30,
        choices=[
            ("image", _("Image")),
            ("video", _("Video")),
            ("document", _("Document")),
            ("unknown", _("Unknown")),
        ],
        db_index=True,
        help_text="Asset media type (image, video, document).",
    )
    
    # ── Routing metadata ──────────────────────────────────────────
    model_target = models.CharField(
        max_length=100,
        db_index=True,
        help_text="Target Django model (avatar, product_image, category_image, etc).",
    )
    
    model_pk = models.CharField(
        max_length=255,
        db_index=True,
        help_text="PK of the model instance that was updated.",
    )
    
    secure_url = models.URLField(
        max_length=500,
        help_text="Cloudinary secure_url that was saved to the model.",
    )
    
    # ── Processing outcome ────────────────────────────────────────
    success = models.BooleanField(
        default=True,
        db_index=True,
        help_text="Whether webhook processing succeeded.",
    )
    
    error_message = models.TextField(
        null=True,
        blank=True,
        help_text="Error message if processing failed.",
    )
    
    processing_time_ms = models.FloatField(
        default=0.0,
        help_text="How long webhook processing took (milliseconds).",
    )
    
    # ── Timestamps ────────────────────────────────────────────────
    processed_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
        help_text="When the webhook was received and processed.",
    )
    
    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When this audit record was created.",
    )
    
    updated_at = models.DateTimeField(
        auto_now=True,
        help_text="When this record was last updated (should rarely happen).",
    )
    
    class Meta:
        db_table = "cloudinary_processed_webhooks"
        verbose_name = "Cloudinary Processed Webhook"
        verbose_name_plural = "Cloudinary Processed Webhooks"
        
        # Indexes for common query patterns
        indexes = [
            models.Index(fields=["public_id"]),
            models.Index(fields=["model_target", "model_pk"]),
            models.Index(fields=["asset_type"]),
            models.Index(fields=["processed_at"]),
            models.Index(fields=["-processed_at"]),  # Most recent first
            models.Index(fields=["success", "processed_at"]),  # Failures first
        ]
        
        # Read-only from application (audit trail must be immutable)
        permissions = [
            ("view_webhook", "Can view processed webhooks"),
        ]
        
        ordering = ["-processed_at"]
    
    def __str__(self) -> str:
        """Human-readable representation."""
        status = "✓" if self.success else "✗"
        return (
            f"{status} {self.asset_type} → {self.model_target} "
            f"({self.idempotency_key[:16]}... at {self.processed_at.isoformat()})"
        )
    
    def __repr__(self) -> str:
        """Developer-friendly representation."""
        return (
            f"<CloudinaryProcessedWebhook "
            f"public_id={self.public_id!r} "
            f"model={self.model_target} "
            f"success={self.success}>"
        )
    
    @classmethod
    def stats_last_n_hours(cls, hours: int = 24) -> dict:
        """
        Get summary statistics for webhooks processed in the last N hours.
        
        Useful for monitoring and alerting.
        
        Args:
            hours: Number of hours to look back
        
        Returns:
            Dictionary with stats: total, success, failure, avg_time_ms
        
        Example:
            >>> stats = CloudinaryProcessedWebhook.stats_last_n_hours(24)
            >>> print(f"Processed {stats['total']} webhooks in 24 hours")
            >>> print(f"Success rate: {stats['success_rate']}%")
        """
        from django.utils import timezone
        from datetime import timedelta
        
        cutoff = timezone.now() - timedelta(hours=hours)
        
        webhooks = cls.objects.filter(processed_at__gte=cutoff)
        total = webhooks.count()
        success = webhooks.filter(success=True).count()
        failure = webhooks.filter(success=False).count()
        
        # Average processing time
        from django.db.models import Avg
        avg_time = webhooks.aggregate(avg=Avg("processing_time_ms"))["avg"] or 0
        
        success_rate = (success / total * 100) if total > 0 else 0
        
        return {
            "total": total,
            "success": success,
            "failure": failure,
            "success_rate": f"{success_rate:.2f}",
            "avg_processing_time_ms": f"{avg_time:.2f}",
            "period_hours": hours,
        }
    
    @classmethod
    def failures_last_n_hours(cls, hours: int = 24, limit: int = 10) -> list:
        """
        Get most recent webhook failures.
        
        Useful for debugging and alerting.
        
        Args:
            hours: Look back this many hours
            limit: Return at most this many failures
        
        Returns:
            List of CloudinaryProcessedWebhook with success=False
        """
        from django.utils import timezone
        from datetime import timedelta
        
        cutoff = timezone.now() - timedelta(hours=hours)
        
        return cls.objects.filter(
            success=False,
            processed_at__gte=cutoff,
        ).order_by("-processed_at")[:limit]
