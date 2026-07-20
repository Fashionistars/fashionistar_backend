# apps/measurements/apis/sync/scan_views.py
"""
DRF synchronous views for the AI Body Scan endpoints.

Endpoints:
  POST /api/v1/measurements/scan/initiate/
      — Create a BodyScanSession with status=PENDING.
        Returns session_id for frontend polling.
        Fires prepare_scan_session Celery task.

  POST /api/v1/measurements/scan/<session_id>/submit-landmarks/
      — Accepts MediaPipe world landmarks + user height from browser.
        Fires process_body_scan Celery task.
        Frontend polls /api/v1/ninja/ai/scan/<session_id>/status/
        for COMPLETED or FAILED status.

Architecture note:
  - Writes (POST) go through DRF (sync) — consistent with project pattern
  - Reads (GET poll) go through Django Ninja (async) — see measurement_views.py
"""

import logging

from rest_framework import status as http_status
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from rest_framework import serializers as drf_serializers

from apps.common.permissions import IsAuthenticatedAndActive
from apps.common.renderers import CustomJSONRenderer, success_response, error_response
from apps.measurements.models.scan import BodyScanSession
from apps.measurements.services.qr_service import (
    generate_measurement_url,
    generate_qr_code_b64,
)

logger = logging.getLogger(__name__)


# ── Serializers ────────────────────────────────────────────────────────────────

class LandmarkPointSerializer(drf_serializers.Serializer):
    """A single MediaPipe world-coordinate landmark."""
    x          = drf_serializers.FloatField()
    y          = drf_serializers.FloatField()
    z          = drf_serializers.FloatField()
    visibility = drf_serializers.FloatField(min_value=0.0, max_value=1.0)


class LandmarkSubmitSerializer(drf_serializers.Serializer):
    """
    Validates the landmark submission payload from the browser.

    Expected payload (dual-pose):
    {
        "user_height_cm": 175.5,
        "user_weight_kg": 70.0,      // optional — BMI correction layer
        "user_age": 28,              // B-1 FIX: age-based anthropometric anchor
        "device_type": "web",        // optional
        "landmarks": [...],          // 33 front pose landmarks (legacy alias)
        "front_landmarks": [...],    // 33 front pose landmarks (V1 preferred)
        "side_landmarks": [...]      // 33 side pose landmarks (optional — depth estimation)
    }
    """
    user_height_cm = drf_serializers.FloatField(min_value=50.0, max_value=300.0)
    user_weight_kg = drf_serializers.FloatField(
        min_value=10.0, max_value=500.0, required=False, allow_null=True
    )
    # B-1 FIX: user_age accepted — enables age-corrected anthropometric ratios in geometry engine
    user_age = drf_serializers.IntegerField(
        min_value=5, max_value=120, required=False, allow_null=True,
        help_text="Age in years. Improves ratio selection for <25 and >50 age groups."
    )
    device_type = drf_serializers.ChoiceField(
        choices=["web", "ios", "android"],
        default="web",
        required=False,
    )
    # Legacy field — kept for back-compat with existing web clients
    landmarks = drf_serializers.ListField(
        child=LandmarkPointSerializer(),
        min_length=33,
        max_length=33,
        required=False,
    )
    # V1: front_landmarks is the canonical field name
    front_landmarks = drf_serializers.ListField(
        child=LandmarkPointSerializer(),
        min_length=33,
        max_length=33,
        required=False,
        help_text="Front-facing pose. 33 MediaPipe world landmarks."
    )
    # GAP-5 FIX: side_landmarks accepted and forwarded to workflow for depth estimation
    side_landmarks = drf_serializers.ListField(
        child=LandmarkPointSerializer(),
        min_length=33,
        max_length=33,
        required=False,
        allow_null=True,
        help_text="90° right-side pose. Enables ellipse circumference formula for bust/waist."
    )

    def validate(self, attrs):
        """Ensure at least one of landmarks or front_landmarks is provided."""
        if not attrs.get("landmarks") and not attrs.get("front_landmarks"):
            raise drf_serializers.ValidationError(
                {"front_landmarks": "Either 'front_landmarks' or 'landmarks' must be provided."}
            )
        # Normalise: front_landmarks takes precedence over legacy landmarks
        if not attrs.get("front_landmarks") and attrs.get("landmarks"):
            attrs["front_landmarks"] = attrs["landmarks"]
        return attrs


# ── Views ──────────────────────────────────────────────────────────────────────

class InitiateScanView(APIView):
    """
    POST /api/v1/measurements/scan/initiate/

    Creates a BodyScanSession with status=PENDING.
    Returns session_id — the frontend uses this to:
      1. Display a "session ready" indicator to the user
      2. Submit landmark data via SubmitLandmarksView
      3. Poll Ninja API for processing status

    No body required. Optionally accepts:
        { "device_type": "web" | "ios" | "android" }
    """
    permission_classes = [IsAuthenticated, IsAuthenticatedAndActive]
    renderer_classes = [CustomJSONRenderer]

    # ── Rate limiting ─────────────────────────────────────────────────────────
    # Max 3 scan sessions per user per hour (Redis-backed, graceful fallback).
    # Prevents abuse — scan sessions trigger Celery ML tasks (CPU-intensive).
    RATE_LIMIT_MAX   = 30
    RATE_LIMIT_WINDOW = 3600  # 1 hour in seconds

    def _check_rate_limit(self, user_id: int) -> tuple[bool, int]:
        """
        Returns (allowed: bool, remaining: int).
        Uses Django cache (Redis in prod) with key: scan_rate:<user_id>
        If cache is unavailable, allow the request (fail-open).
        """
        try:
            from django.core.cache import cache
            cache_key = f"scan_rate:{user_id}"
            count = cache.get(cache_key, 0)
            if count >= self.RATE_LIMIT_MAX:
                return False, 0
            # Increment; set expiry only on first increment
            new_count = count + 1
            cache.set(cache_key, new_count, timeout=self.RATE_LIMIT_WINDOW)
            return True, self.RATE_LIMIT_MAX - new_count
        except Exception:
            # Cache unavailable — fail open (never block legitimate users)
            return True, self.RATE_LIMIT_MAX

    def post(self, request):
        # ── Rate limit check ──────────────────────────────────────────────────
        allowed, remaining = self._check_rate_limit(request.user.pk)
        if not allowed:
            return error_response(
                f"Scan rate limit reached. You may initiate up to {self.RATE_LIMIT_MAX} "
                f"scans per hour. Please wait before starting a new scan session.",
                http_status.HTTP_429_TOO_MANY_REQUESTS,
            )

        device_type = request.data.get("device_type", "web")
        if device_type not in ("web", "ios", "android"):
            device_type = "web"

        # Get client IP
        ip = (
            request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[0].strip()
            or request.META.get("REMOTE_ADDR")
        )

        session = BodyScanSession.objects.create(
            owner=request.user,
            device_type=device_type,
            scan_provider=BodyScanSession.ScanProvider.AI_CAMERA,
            status=BodyScanSession.Status.PENDING,
            ip_address=ip or None,
            user_agent=request.META.get("HTTP_USER_AGENT", "")[:300],
        )

        # ── Generate measurement URL + QR code (synchronous, < 50 ms) ──────────
        session_id_str   = str(session.session_id)
        measurement_url  = generate_measurement_url(session_id_str)
        qr_code_b64      = generate_qr_code_b64(measurement_url)

        # Persist measurement_url immediately (synchronous DB write)
        BodyScanSession.objects.filter(pk=session.pk).update(
            measurement_url=measurement_url,
        )

        # Upload QR PNG to Cloudinary asynchronously (non-blocking)
        if qr_code_b64:
            try:
                from apps.ai.tasks.measurement_tasks import upload_qr_code_to_cloudinary
                upload_qr_code_to_cloudinary.delay(session_id_str, qr_code_b64)
            except Exception as exc:
                logger.warning(
                    "[InitiateScanView] Cloudinary upload task failed to enqueue: %s", exc
                )

        # Pre-warm the Celery AI worker (non-blocking)
        try:
            from apps.ai.tasks.measurement_tasks import prepare_scan_session
            prepare_scan_session.delay(session_id_str)
        except Exception as exc:
            logger.warning("[InitiateScanView] prepare_scan_session failed: %s", exc)

        return success_response(
            data={
                "session_id":      session_id_str,
                "status":          "pending",
                "measurement_url": measurement_url,
                "qr_code_b64":     qr_code_b64,
                "qr_code_url":     "",  # populated async by Cloudinary upload task
            },
            status=http_status.HTTP_201_CREATED,
            message="Scan session created. Submit your landmarks when ready.",
        )


class SubmitLandmarksView(APIView):
    """
    POST /api/v1/measurements/scan/<session_id>/submit-landmarks/

    Accepts MediaPipe world-coordinate landmarks from the browser.
    Fires the process_body_scan Celery task and returns immediately.

    Frontend should poll:
        GET /api/v1/ninja/measurements/scan/<session_id>/status/
    until status = 'completed' or 'failed'.

    Expected body:
        {
            "user_height_cm": 175.5,
            "user_weight_kg": 70.0,         // optional
            "landmarks": [<33 landmark objects>]
        }

    Success response (202 Accepted):
        {
            "session_id": "...",
            "status": "processing",
            "message": "Scan submitted. Processing in progress..."
        }
    """
    permission_classes = [IsAuthenticated, IsAuthenticatedAndActive]
    renderer_classes = [CustomJSONRenderer]

    def post(self, request, session_id: str):
        # Validate session ownership
        try:
            import uuid
            session_uuid = uuid.UUID(str(session_id))
        except (ValueError, AttributeError):
            return error_response(
                "Invalid session ID.", http_status.HTTP_400_BAD_REQUEST
            )

        try:
            session = BodyScanSession.objects.get(
                session_id=session_uuid,
                owner=request.user,
            )
        except BodyScanSession.DoesNotExist:
            return error_response(
                "Scan session not found.", http_status.HTTP_404_NOT_FOUND
            )

        if session.status not in (
            BodyScanSession.Status.PENDING,
            BodyScanSession.Status.PROCESSING,
        ):
            return error_response(
                f"Session is already {session.status}. Create a new session to scan again.",
                http_status.HTTP_409_CONFLICT,
            )

        # Validate landmark payload
        serializer = LandmarkSubmitSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response(
                "Invalid landmark data.",
                http_status.HTTP_422_UNPROCESSABLE_ENTITY,
                serializer.errors,
            )

        data = serializer.validated_data

        # Resolve front landmarks (V1 front_landmarks preferred; fall back to legacy landmarks)
        front_lms  = data.get("front_landmarks") or data.get("landmarks") or []
        side_lms   = data.get("side_landmarks")  # GAP-5 FIX: forwarded to workflow
        user_age   = data.get("user_age")         # B-1 FIX: forwarded for anthropometric calibration

        # Mark session as PROCESSING
        from django.utils import timezone
        BodyScanSession.objects.filter(pk=session.pk).update(
            status=BodyScanSession.Status.PROCESSING,
            processing_started_at=timezone.now(),
        )

        # Fire Celery task (non-blocking)
        try:
            from apps.ai.tasks.measurement_tasks import process_body_scan
            process_body_scan.delay(
                session_id=str(session.session_id),
                landmarks=front_lms,               # front pose (primary)
                user_height_cm=data["user_height_cm"],
                user_id=request.user.pk,
                user_weight_kg=data.get("user_weight_kg"),
                user_age=user_age,                 # B-1 FIX: age anchor
                side_landmarks=side_lms,           # GAP-5 FIX: side pose for depth
            )
        except Exception as exc:
            logger.exception("[SubmitLandmarksView] Failed to dispatch Celery task")
            BodyScanSession.objects.filter(pk=session.pk).update(
                status=BodyScanSession.Status.FAILED,
                error_message=f"Failed to start processing: {exc}",
                completed_at=timezone.now(),
            )
            return error_response(
                "Failed to start scan processing. Please try again.",
                http_status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        return success_response(
            data={
                "session_id": str(session.session_id),
                "status":     "processing",
            },
            status=http_status.HTTP_202_ACCEPTED,
            message="Scan submitted. AI processing started — this usually takes 5-10 seconds.",
        )
