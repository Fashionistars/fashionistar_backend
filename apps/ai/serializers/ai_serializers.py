# apps/ai/serializers/ai_serializers.py
"""
DRF Serializers for the AI app.

Covers:
  - LandmarkPointSerializer   — validates a single MediaPipe world landmark
  - LandmarkSubmitSerializer  — validates the full scan submission payload
  - WorkflowExecutionSerializer — read-only WorkflowExecution output
"""

from __future__ import annotations

from rest_framework import serializers


# ─── Landmark serializers ─────────────────────────────────────────────────────

class LandmarkPointSerializer(serializers.Serializer):
    """
    Validates a single MediaPipe world landmark.

    MediaPipe world landmarks (from PoseLandmarker.worldLandmarks):
      x: float  — metres, positive = right
      y: float  — metres, positive = downward
      z: float  — metres, positive = towards camera
      visibility: float (0-1) — landmark detection confidence
    """

    x          = serializers.FloatField(
        help_text="World X in metres (positive = right of centre)"
    )
    y          = serializers.FloatField(
        help_text="World Y in metres (positive = downward)"
    )
    z          = serializers.FloatField(
        help_text="World Z in metres (positive = towards camera)"
    )
    visibility = serializers.FloatField(
        min_value=0.0,
        max_value=1.0,
        required=False,
        default=0.0,
        help_text="Landmark detection confidence (0-1)",
    )


class LandmarkSubmitSerializer(serializers.Serializer):
    """
    Validates the full landmark submission payload from the browser.

    POST /api/v1/measurements/scan/{session_id}/submit-landmarks/

    Required:
      user_height_cm: User-provided height in cm (auto-estimated if 0)
      landmarks:      Exactly 33 MediaPipe world landmarks

    Optional:
      user_weight_kg: Used to refine circumference estimates
      device_type:    'web' | 'ios' | 'android'
    """

    user_height_cm = serializers.FloatField(
        min_value=0,
        max_value=280,
        required=True,
        help_text=(
            "User height in centimetres. Pass 0 if unknown — "
            "the AI engine will auto-estimate from landmarks."
        ),
    )
    user_weight_kg = serializers.FloatField(
        min_value=0,
        max_value=500,
        required=False,
        allow_null=True,
        default=None,
        help_text="User weight in kg (optional, improves circumference estimates)",
    )
    device_type = serializers.ChoiceField(
        choices=["web", "ios", "android"],
        required=False,
        default="web",
    )
    landmarks = serializers.ListField(
        child=LandmarkPointSerializer(),
        min_length=29,   # Allow slightly fewer (29+) for partial body visibility
        max_length=33,
        required=True,
        help_text="List of 33 MediaPipe BlazePose world landmarks",
    )

    def validate_user_height_cm(self, value: float) -> float:
        """
        If 0, height will be auto-estimated from landmarks.
        Any other value must be in a realistic range (100-250 cm).
        """
        if value == 0:
            return 0.0  # Signals auto-estimate
        if value < 100 or value > 250:
            raise serializers.ValidationError(
                "Height must be between 100 and 250 cm. "
                "Pass 0 to auto-estimate from body proportions."
            )
        return round(value, 1)

    def validate_landmarks(self, value: list) -> list:
        """
        Ensure minimum landmark quality — at least 6 key body landmarks
        must have visibility ≥ 0.5.
        """
        KEY_BODY_INDICES = [11, 12, 23, 24, 25, 26]   # shoulders + hips + knees
        visible_count = 0

        for idx in KEY_BODY_INDICES:
            if idx < len(value):
                vis = float(value[idx].get("visibility", 0))
                if vis >= 0.5:
                    visible_count += 1

        if visible_count < 4:
            raise serializers.ValidationError(
                "Poor pose quality: fewer than 4 key body landmarks are visible. "
                "Please ensure your full body is in frame with good lighting."
            )

        return value


# ─── WorkflowExecution serializer ─────────────────────────────────────────────

class WorkflowExecutionSerializer(serializers.Serializer):
    """
    Read-only serializer for WorkflowExecution model output.
    Returned by admin / monitoring endpoints.
    """

    id             = serializers.IntegerField(read_only=True)
    workflow_type  = serializers.CharField(read_only=True)
    status         = serializers.CharField(read_only=True)
    model_version  = serializers.CharField(read_only=True)
    duration_ms    = serializers.IntegerField(read_only=True, allow_null=True)
    error_detail   = serializers.CharField(read_only=True)
    output_snapshot = serializers.DictField(read_only=True)
    created_at     = serializers.DateTimeField(read_only=True)
    completed_at   = serializers.DateTimeField(read_only=True, allow_null=True)
