# apps/ai/tasks/measurement_tasks.py
"""
Celery tasks for AI-powered body measurement processing.

Tasks:
  process_body_scan()    — Main scan processing pipeline (MeasurementWorkflow)
  prepare_scan_session() — Pre-warms Celery worker before landmark submission

Queue: "ai" (dedicated queue for ML-heavy tasks)
Worker: Start with: celery -A backend worker -Q ai --concurrency=2 --loglevel=info
"""

import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    name="apps.ai.tasks.measurement_tasks.process_body_scan",
    queue="ai",
    max_retries=2,
    default_retry_delay=30,
    soft_time_limit=120,   # 2 minutes max for scan processing
    time_limit=150,
)
def process_body_scan(
    self,
    session_id: str,
    landmarks: list,
    user_height_cm: float,
    user_id: int,
    user_weight_kg: float | None = None,
) -> dict:
    """
    Main AI body measurement processing pipeline.

    Called by: DRF SubmitLandmarksView after receiving browser MediaPipe data.

    Pipeline:
      1. MeasurementWorkflow (LangGraph):
         - validate_pose_quality
         - compute_scale_factor (calibration)
         - extract_linear_measurements (world coords → cm)
         - estimate_circumferences_geometric (anthropometric models)
      2. create_or_update_ai_scan_profile → MeasurementProfile
      3. Update BodyScanSession status → COMPLETED
      4. Fire run_profile_recommendations.delay()

    Args:
        session_id:      BodyScanSession UUID
        landmarks:       33 MediaPipe world landmarks (from browser)
        user_height_cm:  User-provided height (cm) for scale calibration
        user_id:         Owner user PK
        user_weight_kg:  Optional user-provided weight (kg) for BMI correction

    Returns:
        dict: {status, profile_id, quality_score, errors}
    """
    logger.info("[process_body_scan] session=%s user=%s", session_id, user_id)

    try:
        from apps.ai.workflows.measurement import MeasurementWorkflow

        workflow = MeasurementWorkflow()
        result = workflow.execute({
            "session_id":     session_id,
            "user_id":        user_id,
            "user_height_cm": user_height_cm,
            "user_weight_kg": user_weight_kg,
            "landmarks":      landmarks,
            "celery_task_id": self.request.id or "",
        })

        logger.info(
            "[process_body_scan] DONE session=%s profile=%s quality=%.2f",
            session_id,
            result.get("profile_id"),
            result.get("quality_score", 0),
        )
        return result

    except Exception as exc:
        logger.exception("[process_body_scan] FAILED session=%s", session_id)

        # Mark session failed before retrying
        try:
            from apps.measurements.models.scan import BodyScanSession
            from django.utils import timezone
            BodyScanSession.objects.filter(session_id=session_id).update(
                status="failed",
                error_message=f"Processing error: {exc}",
                completed_at=timezone.now(),
            )
        except Exception:
            pass

        raise self.retry(exc=exc, countdown=30)


@shared_task(
    name="apps.ai.tasks.measurement_tasks.prepare_scan_session",
    queue="ai",
    ignore_result=True,
)
def prepare_scan_session(session_id: str) -> None:
    """
    Pre-warm the Celery AI worker before the user submits landmarks.

    Called immediately after InitiateScanView creates the BodyScanSession.
    This ensures the geometry utilities are imported and ready in the worker
    before the user completes their pose, reducing processing latency.

    Args:
        session_id: BodyScanSession UUID (used for logging only)
    """
    logger.debug("[prepare_scan_session] warming up for session=%s", session_id)
    # Import the heavy modules to ensure they're cached in the worker process
    try:
        from apps.ai.utils import geometry  # noqa: F401
    except Exception:
        pass
