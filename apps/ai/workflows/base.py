# apps/ai/workflows/base.py
"""
Base workflow class for all FASHIONISTAR LangGraph workflows.

Provides:
  - WorkflowExecution tracking (creates/updates audit rows)
  - Structured logging
  - Error handling + retry support
  - Timing metrics (duration_ms)

All domain workflows inherit from BaseWorkflow and call:
    self.start_execution()
    self.complete_execution(output)
    self.fail_execution(error)
"""

from __future__ import annotations

import logging
import time
from uuid import UUID

from django.utils import timezone

logger = logging.getLogger(__name__)


class BaseWorkflow:
    """
    Base class for all FASHIONISTAR AI LangGraph workflows.

    Provides WorkflowExecution lifecycle management.
    All concrete workflows must define:
        workflow_type: str   (WorkflowExecution.WorkflowType value)
        model_version: str   (e.g., "mediapipe-0.10.14")
    """

    workflow_type: str = "base"
    model_version: str = "1.0.0"

    def __init__(self, execution_id: UUID | None = None):
        self._execution_id = execution_id
        self._start_time: float | None = None

    # ── WorkflowExecution lifecycle ────────────────────────────────────────────

    def start_execution(
        self,
        user_id: int | None = None,
        input_snapshot: dict | None = None,
        celery_task_id: str = "",
    ) -> UUID:
        """
        Create WorkflowExecution row with status=RUNNING.
        Returns the execution UUID for future updates.
        """
        self._start_time = time.monotonic()
        try:
            from apps.ai.models import WorkflowExecution
            from django.contrib.auth import get_user_model

            user = None
            if user_id:
                try:
                    User = get_user_model()
                    user = User.objects.get(pk=user_id)
                except Exception:
                    pass

            execution = WorkflowExecution.objects.create(
                workflow_type=self.workflow_type,
                status=WorkflowExecution.Status.RUNNING,
                user=user,
                input_snapshot=input_snapshot or {},
                model_version=self.model_version,
                celery_task_id=celery_task_id,
                started_at=timezone.now(),
            )
            self._execution_id = execution.id
            logger.info("[%s] workflow started: %s", self.workflow_type, execution.id)
            return execution.id
        except Exception as exc:
            logger.warning("[%s] could not create WorkflowExecution: %s", self.workflow_type, exc)
            return None

    def complete_execution(self, output_snapshot: dict | None = None) -> None:
        """Mark WorkflowExecution as COMPLETED with output snapshot."""
        if not self._execution_id:
            return
        try:
            from apps.ai.models import WorkflowExecution
            duration = int((time.monotonic() - self._start_time) * 1000) if self._start_time else None
            WorkflowExecution.objects.filter(id=self._execution_id).update(
                status=WorkflowExecution.Status.COMPLETED,
                output_snapshot=output_snapshot or {},
                completed_at=timezone.now(),
                duration_ms=duration,
            )
        except Exception as exc:
            logger.warning("[%s] complete_execution failed: %s", self.workflow_type, exc)

    def fail_execution(self, error: Exception | str) -> None:
        """Mark WorkflowExecution as FAILED with error detail."""
        if not self._execution_id:
            return
        try:
            import traceback
            from apps.ai.models import WorkflowExecution
            duration = int((time.monotonic() - self._start_time) * 1000) if self._start_time else None
            error_detail = (
                traceback.format_exc() if isinstance(error, Exception) else str(error)
            )
            WorkflowExecution.objects.filter(id=self._execution_id).update(
                status=WorkflowExecution.Status.FAILED,
                error_detail=error_detail,
                completed_at=timezone.now(),
                duration_ms=duration,
            )
        except Exception as exc:
            logger.warning("[%s] fail_execution update failed: %s", self.workflow_type, exc)

    def execute(self, input_data: dict) -> dict:
        """
        Override in subclasses. Must return a dict output.
        Subclasses should call start_execution() / complete_execution() / fail_execution().
        """
        raise NotImplementedError(f"{self.__class__.__name__}.execute() must be implemented")
