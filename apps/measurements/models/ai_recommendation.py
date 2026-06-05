# apps/measurements/models/ai_recommendation.py
"""
SizeRecommendationRequest — AI-driven size recommendation pipeline entity.

Architecture Rules:
  - TimeStampedModel only (no soft-delete — AI outputs are audit data).
  - status field tracks the async ML pipeline state.
  - fit_notes and alternative_sizes are JSONField for structured AI output.
  - model_version required for reproducibility audits.
  - Mutations live in apps/measurements/services/ai_recommendation_service.py.

Lifecycle:
  1. Client requests (POST /api/v1/measurements/profiles/{pk}/recommend-size/)
  2. Service creates PENDING row, fires process_size_recommendation.delay(pk)
  3. Celery task calls ML service, updates to COMPLETED with recommended_size
  4. Client polls (GET /api/v1/ninja/measurements/recommendations/{pk}/)
"""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.common.models import TimeStampedModel


class SizeRecommendationRequest(TimeStampedModel):
    """
    AI-generated size recommendation request.

    Captures the client's measurement profile + product context and
    stores the ML model's structured output for fast future retrieval.

    Attributes:
        client: The requesting client user.
        product: Product being sized.
        measurement_profile: Measurement data used for the recommendation.
        recommended_size: Primary recommended size label (e.g. "M", "42", "L").
        confidence: Model confidence score (0.0–1.0).
        fit_notes: Structured per-measurement-field fit commentary.
        alternative_sizes: Ordered list of alternative size options.
        reasoning: Plain English explanation of the recommendation.
        status: Pipeline status (pending / completed / failed).
        model_version: ML model version string for reproducibility audits.
        processed_at: Timestamp of ML service completion.
        error_message: Set on FAILED status.

    fit_notes format:
        {
            "bust": "relaxed_fit",
            "waist": "true_to_size",
            "hips": "slightly_tight"
        }

    alternative_sizes format:
        [{"size": "L", "confidence": 0.72, "note": "If you prefer relaxed fit"}]
    """

    class Status(models.TextChoices):
        PENDING = "pending", _("Pending")
        COMPLETED = "completed", _("Completed")
        FAILED = "failed", _("Failed")

    client = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="size_recommendation_requests",
        verbose_name=_("Client"),
    )
    product = models.ForeignKey(
        "product.Product",
        on_delete=models.CASCADE,
        related_name="size_recommendation_requests",
        verbose_name=_("Product"),
    )
    measurement_profile = models.ForeignKey(
        "measurements.MeasurementProfile",
        on_delete=models.CASCADE,
        related_name="size_recommendation_requests",
        verbose_name=_("Measurement Profile"),
    )

    # ── AI output ─────────────────────────────────────────────────────────────
    recommended_size = models.CharField(
        max_length=10,
        blank=True,
        verbose_name=_("Recommended Size"),
    )
    confidence = models.FloatField(
        null=True,
        blank=True,
        verbose_name=_("Confidence"),
        help_text=_("0.0 = low confidence, 1.0 = high confidence."),
    )
    fit_notes = models.JSONField(
        default=dict,
        blank=True,
        verbose_name=_("Fit Notes"),
        help_text=_(
            'Per-field fit commentary. '
            'E.g. {"bust": "relaxed_fit", "waist": "true_to_size"}'
        ),
    )
    alternative_sizes = models.JSONField(
        default=list,
        blank=True,
        verbose_name=_("Alternative Sizes"),
        help_text=_("Ordered alternative size options with confidence and notes."),
    )
    reasoning = models.TextField(
        blank=True,
        verbose_name=_("Reasoning"),
        help_text=_("Plain English explanation from the AI model."),
    )

    # ── Pipeline state ────────────────────────────────────────────────────────
    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
        verbose_name=_("Status"),
    )
    model_version = models.CharField(
        max_length=50,
        blank=True,
        verbose_name=_("Model Version"),
        help_text=_("ML model version for reproducibility audit."),
    )
    processed_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("Processed At"),
    )
    error_message = models.TextField(
        blank=True,
        verbose_name=_("Error Message"),
        help_text=_("Set on FAILED status."),
    )

    class Meta:
        verbose_name = _("Size Recommendation Request")
        verbose_name_plural = _("Size Recommendation Requests")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["client", "status"], name="srr_client_status_idx"),
            models.Index(fields=["product", "status"], name="srr_product_status_idx"),
            models.Index(
                fields=["measurement_profile", "product"],
                name="srr_profile_product_idx",
            ),
        ]

    def __str__(self) -> str:
        return (
            f"SizeRec [{self.status}] {self.client} → {self.product}: "
            f"{self.recommended_size or 'pending'}"
        )
