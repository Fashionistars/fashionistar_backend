# apps/ai/models/workflow_execution.py
"""
WorkflowExecution — Tracks every LangGraph AI workflow run.

Purpose:
  - Observability: admins can inspect every AI decision made
  - Debugging: full input/output snapshot for failed workflows
  - Cost tracking: duration_ms per workflow type
  - Audit: who triggered what AI workflow and when

Architecture:
  - TimeStampedModel only (no soft-delete — AI audit logs are immutable)
  - status field tracks the async pipeline state
  - Mutations via apps.ai.tasks.* Celery workers only (never in views)
"""

from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.common.models import TimeStampedModel


class WorkflowExecution(TimeStampedModel):
    """
    Records every AI workflow execution for observability and audit.

    Lifecycle:
      1. Celery task creates PENDING row before executing workflow
      2. Sets to RUNNING when workflow graph starts
      3. Updates to COMPLETED with output_snapshot on success
      4. Updates to FAILED with error_detail on exception

    Attributes:
        workflow_type: Which AI workflow was triggered
        status: Current pipeline state
        user: User who triggered the workflow (nullable for system tasks)
        input_snapshot: Sanitized copy of workflow input (no raw images)
        output_snapshot: Final workflow output (measurements, recommendations, etc.)
        error_detail: Exception detail on FAILED status
        started_at: When the LangGraph graph began executing
        completed_at: When the workflow terminated (success or failure)
        duration_ms: Total execution time in milliseconds
        model_version: AI model version string for reproducibility audit
        celery_task_id: Link back to Celery task for cross-referencing
    """

    class WorkflowType(models.TextChoices):
        MEASUREMENT     = "measurement",     _("Measurement")
        RECOMMENDATION  = "recommendation",  _("Recommendation")
        ANALYTICS       = "analytics",       _("Analytics")
        INGESTION       = "ingestion",       _("DB Ingestion")
        EMBEDDING       = "embedding",       _("Product Embedding")
        SIZE_REASONING  = "size_reasoning",  _("LLM Size Reasoning")

    class Status(models.TextChoices):
        PENDING    = "pending",    _("Pending")
        RUNNING    = "running",    _("Running")
        COMPLETED  = "completed",  _("Completed")
        FAILED     = "failed",     _("Failed")
        RETRYING   = "retrying",   _("Retrying")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workflow_type   = models.CharField(
        max_length=20,
        choices=WorkflowType.choices,
        db_index=True,
        verbose_name=_("Workflow Type"),
    )
    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
        verbose_name=_("Status"),
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="ai_workflow_executions",
        verbose_name=_("User"),
        help_text=_("Null for system-triggered workflows (e.g., analytics cron)."),
    )
    input_snapshot = models.JSONField(
        default=dict,
        blank=True,
        verbose_name=_("Input Snapshot"),
        help_text=_("Sanitized workflow input. No raw image bytes."),
    )
    output_snapshot = models.JSONField(
        default=dict,
        blank=True,
        verbose_name=_("Output Snapshot"),
        help_text=_("Final workflow output (measurements, recommendations, insights)."),
    )
    error_detail = models.TextField(
        blank=True,
        verbose_name=_("Error Detail"),
        help_text=_("Exception traceback on FAILED status."),
    )
    started_at   = models.DateTimeField(null=True, blank=True, verbose_name=_("Started At"))
    completed_at = models.DateTimeField(null=True, blank=True, verbose_name=_("Completed At"))
    duration_ms  = models.PositiveIntegerField(
        null=True, blank=True, verbose_name=_("Duration (ms)")
    )
    model_version = models.CharField(
        max_length=100,
        blank=True,
        verbose_name=_("Model Version"),
        help_text=_("AI model version for reproducibility audit."),
    )
    celery_task_id = models.CharField(
        max_length=200,
        blank=True,
        db_index=True,
        verbose_name=_("Celery Task ID"),
    )

    class Meta:
        verbose_name = _("Workflow Execution")
        verbose_name_plural = _("Workflow Executions")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["workflow_type", "status"], name="ai_wf_type_status_idx"),
            models.Index(fields=["user", "workflow_type"],   name="ai_wf_user_type_idx"),
            models.Index(fields=["created_at"],              name="ai_wf_created_idx"),
        ]

    def __str__(self) -> str:
        return f"[{self.workflow_type}] {self.status} — {self.created_at:%Y-%m-%d %H:%M}"
