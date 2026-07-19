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
    user_age: int | None = None,            # B-1 FIX: age-based anthropometric calibration
    side_landmarks: list | None = None,     # GAP-5 FIX: side pose for depth estimation
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
         - apply_bmi_corrections (BMI-scaled circumference adjustment)
         - verify_anthropometric_plausibility (flag implausible values)
      2. create_or_update_ai_scan_profile → MeasurementProfile
      3. Update BodyScanSession status → COMPLETED
      4. Fire run_profile_recommendations.delay()

    Args:
        session_id:      BodyScanSession UUID
        landmarks:       33 MediaPipe world landmarks — FRONT pose (primary)
        user_height_cm:  User-provided height (cm) for scale calibration
        user_id:         Owner user PK
        user_weight_kg:  Optional user-provided weight (kg) for BMI correction
        user_age:        Optional age in years for anthropometric ratio adjustment
        side_landmarks:  Optional 33 side-pose landmarks for depth estimation

    Returns:
        dict: {status, profile_id, quality_score, errors}
    """
    logger.info(
        "[process_body_scan] session=%s user=%s age=%s has_side=%s",
        session_id, user_id, user_age, side_landmarks is not None
    )

    try:
        from apps.ai.workflows.measurement import MeasurementWorkflow

        workflow = MeasurementWorkflow()
        result = workflow.execute({
            "session_id":     session_id,
            "user_id":        user_id,
            "user_height_cm": user_height_cm,
            "user_weight_kg": user_weight_kg,
            "user_age":       user_age,          # B-1 FIX
            "landmarks":      landmarks,
            "side_landmarks": side_landmarks,    # GAP-5 FIX
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


@shared_task(
    bind=True,
    name="apps.ai.tasks.measurement_tasks.upload_qr_code_to_cloudinary",
    queue="default",           # Not AI queue — this is a lightweight I/O task
    max_retries=3,
    default_retry_delay=5,     # Retry after 5s (Cloudinary transient errors)
    ignore_result=True,
)
def upload_qr_code_to_cloudinary(self, session_id: str, qr_b64: str) -> None:
    """
    Upload the QR code PNG to Cloudinary and persist the URL to BodyScanSession.

    Called non-blocking immediately after InitiateScanView creates the session.
    On success: updates BodyScanSession.qr_code_url with the Cloudinary URL.
    On failure: retries up to 3 times (5s exponential backoff), then logs + silently fails.
    The qr_code_b64 in the API response is the primary display mechanism;
    the Cloudinary URL is for long-term audit and re-retrieval.

    Args:
        session_id: UUID string of the BodyScanSession.
        qr_b64:     Base64-encoded PNG string (without data: prefix).
    """
    logger.info("[upload_qr_code_to_cloudinary] Starting upload for session=%s", session_id)

    try:
        from apps.measurements.services.qr_service import upload_qr_to_cloudinary
        cloudinary_url = upload_qr_to_cloudinary(qr_b64, session_id)

        if cloudinary_url:
            from apps.measurements.models.scan import BodyScanSession
            updated = BodyScanSession.objects.filter(
                session_id=session_id
            ).update(qr_code_url=cloudinary_url)

            if updated:
                logger.info(
                    "[upload_qr_code_to_cloudinary] QR URL saved for session=%s: %s",
                    session_id, cloudinary_url,
                )
            else:
                logger.warning(
                    "[upload_qr_code_to_cloudinary] Session not found for update: %s",
                    session_id,
                )
        else:
            logger.warning(
                "[upload_qr_code_to_cloudinary] Cloudinary returned empty URL for session=%s",
                session_id,
            )

    except Exception as exc:
        logger.warning(
            "[upload_qr_code_to_cloudinary] Failed for session=%s: %s. Retrying...",
            session_id, exc,
        )
        raise self.retry(exc=exc, countdown=5 * (self.request.retries + 1))
