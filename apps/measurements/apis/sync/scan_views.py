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
        Frontend polls /api/v1/ninja/measurements/scan/<session_id>/status/
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

    Expected payload:
    {
        "user_height_cm": 175.5,
        "user_weight_kg": 70.0,    // optional
        "device_type": "web",      // optional, defaults to "web"
        "landmarks": [             // 33 MediaPipe world landmarks
            {"x": 0.01, "y": -0.5, "z": 0.02, "visibility": 0.98},
            ...
        ]
    }
    """
    user_height_cm = drf_serializers.FloatField(min_value=50.0, max_value=300.0)
    user_weight_kg = drf_serializers.FloatField(
        min_value=10.0, max_value=500.0, required=False, allow_null=True
    )
    device_type = drf_serializers.ChoiceField(
        choices=["web", "ios", "android"],
        default="web",
        required=False,
    )
    landmarks = drf_serializers.ListField(
        child=LandmarkPointSerializer(),
        min_length=33,
        max_length=33,
    )


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

    def post(self, request):
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

        # Pre-warm the Celery AI worker (non-blocking)
        try:
            from apps.ai.tasks.measurement_tasks import prepare_scan_session
            prepare_scan_session.delay(str(session.session_id))
        except Exception as exc:
            logger.warning("[InitiateScanView] prepare_scan_session failed: %s", exc)

        return success_response(
            data={
                "session_id": str(session.session_id),
                "status":     "pending",
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
                landmarks=data["landmarks"],
                user_height_cm=data["user_height_cm"],
                user_id=request.user.pk,
                user_weight_kg=data.get("user_weight_kg"),
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
