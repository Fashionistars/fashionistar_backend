# apps/ai/workflows/measurement.py
"""
MeasurementWorkflow — LangGraph state-machine for AI body measurement extraction.

Triggered by: Celery task apps.ai.tasks.measurement_tasks.process_body_scan
Input: MediaPipe world landmarks JSON + user height + optional weight/age/side_landmarks
Output: Completed MeasurementProfile + enriched BodyScanSession

Graph (V2 — Dual-Pose + BMI Correction + Plausibility):
  run_full_pipeline
      ↓ (is_valid)
  apply_bmi_corrections       ← GAP-1 FIX: BMI-weighted circumference scaling
      ↓
  verify_plausibility         ← GAP-2 FIX: Anthropometric sanity checks
      ↓
  save_profile
      ↓
  update_session_completed
      ↓
  trigger_recommendation
      ↓
    END

  run_full_pipeline ─ fail → update_session_failed → END
"""

from __future__ import annotations

import logging

from django.utils import timezone
from langgraph.graph import StateGraph, END

from typing import TypedDict, List, Dict, Any, Optional

logger = logging.getLogger(__name__)


# ── LangGraph state definition ──────────────────────────────────────────────────

class MeasurementState(TypedDict):
    """
    Typed state dictionary for the MeasurementWorkflow graph (V2).

    Keys:
        session_id: str            BodyScanSession UUID
        user_id: int               Owner user PK
        user_height_cm: float      User-provided height in cm (required for calibration)
        user_weight_kg: float|None User-provided weight in kg (optional — BMI correction)
        user_age: int|None         User age in years (B-1 FIX — anthropometric calibration)
        landmarks: list            33 MediaPipe world landmarks — FRONT pose
        side_landmarks: list|None  33 MediaPipe world landmarks — SIDE pose (GAP-5 FIX)
        scale_factor: float        Computed calibration factor
        measurement_result: dict   Full result from geometry pipeline
        bmi: float|None            Computed BMI (if weight provided)
        plausibility_warnings: list Anthropometric flags (GAP-2 FIX)
        correction_applied: str    BMI correction tier applied (GAP-1 FIX)
        profile_id: str|None       Created MeasurementProfile ID
        errors: list               Accumulated error messages
    """
    session_id:             str
    user_id:                int
    user_height_cm:         float
    user_weight_kg:         Optional[float]
    user_age:               Optional[int]           # B-1 FIX
    landmarks:              List[Dict[str, float]]
    side_landmarks:         Optional[List[Dict[str, float]]]  # GAP-5 FIX
    scale_factor:           float
    measurement_result:     Dict[str, Any]
    bmi:                    Optional[float]
    plausibility_warnings:  List[str]               # GAP-2 FIX
    correction_applied:     str                     # GAP-1 FIX
    profile_id:             Optional[str]
    errors:                 List[str]


# ── BMI correction table (NHANES 2017-2020 proxy) ──────────────────────────────
#
# Multiplier applied to circumference measurements (waist, hip, chest, belly_button).
# Source: WHO/NHANES adjusted ratios for optical body scan correction.
#
# BMI Range       | Correction Factor | Rationale
# <18.5 (under)   | 0.92              | Underweight users → narrower proportions
# 18.5-24.9 (norm)| 1.00              | Baseline — geometry engine calibrated here
# 25.0-29.9 (over)| 1.10              | Overweight → extra soft tissue depth
# ≥30.0 (obese)   | 1.22              | Obese → significant depth underestimated by 2D
#
_BMI_CORRECTION_TABLE = [
    (18.5, "underweight",   0.92),
    (25.0, "normal",        1.00),
    (30.0, "overweight",    1.10),
    (float("inf"), "obese", 1.22),
]

# Fields that receive BMI circumference correction
_CIRCUMFERENCE_FIELDS = frozenset({
    "waist_cm", "hip_cm", "chest_cm", "belly_button_cm",
    "waist", "hip", "chest", "belly_button",
})

# ── Plausibility rules (GAP-2 FIX) ─────────────────────────────────────────────
#
# Checks based on WHO Reference Charts + published 3DBody scan validation data.
# Rules expressed as: (field, min_pct_of_height, max_pct_of_height, label)
# e.g. ("bust_cm", 0.45, 0.70, "Bust") → bust must be 45%–70% of height

_PLAUSIBILITY_RULES = [
    # field_key,           min_ratio,  max_ratio,  human_label
    ("shoulder_width_cm",  0.20,       0.38,       "Shoulder width"),
    ("shoulder_width",     0.20,       0.38,       "Shoulder width"),
    ("chest_cm",           0.45,       0.70,       "Chest"),
    ("chest",              0.45,       0.70,       "Chest"),
    ("waist_cm",           0.30,       0.65,       "Waist"),
    ("waist",              0.30,       0.65,       "Waist"),
    ("hip_cm",             0.45,       0.75,       "Hip"),
    ("hip",                0.45,       0.75,       "Hip"),
    ("arm_length_cm",      0.28,       0.55,       "Arm length"),
    ("arm_length",         0.28,       0.55,       "Arm length"),
    ("inseam_cm",          0.40,       0.60,       "Inseam"),
    ("inseam",             0.40,       0.60,       "Inseam"),
]

# Waist-to-hip ratio must be within physiologically plausible range
_WHR_MIN = 0.55
_WHR_MAX = 1.20


# ── Workflow class ──────────────────────────────────────────────────────────────

class MeasurementWorkflow:
    """
    LangGraph workflow (V2) for processing MediaPipe body scan data into
    a persisted MeasurementProfile with BMI correction + plausibility checks.

    Usage (from Celery task):
        workflow = MeasurementWorkflow()
        result = workflow.execute({
            "session_id": "...",
            "user_id": 42,
            "user_height_cm": 175.0,
            "user_weight_kg": 70.0,      # optional
            "user_age": 28,              # optional — B-1 FIX
            "landmarks": [...],           # 33 front pose landmarks
            "side_landmarks": [...],      # optional — GAP-5 FIX
            "celery_task_id": "...",
        })

    Returns:
        {
            "session_id": "...",
            "profile_id": "...",
            "quality_score": 0.85,
            "is_valid": True,
            "plausibility_warnings": [],
            "correction_applied": "normal",
            "bmi": 22.4,
            "errors": [],
        }
    """

    workflow_type = "measurement"
    model_version = "mediapipe-tasks-0.10.14+geometry-v2+bmi+plausibility"

    def __init__(self):
        """Initialize the workflow and build the LangGraph state machine."""
        self.graph = self._build_graph()

    def _build_graph(self) -> StateGraph:
        """Build the LangGraph state machine with nodes and edges (V2)."""
        workflow = StateGraph(MeasurementState)

        # ── Add nodes ───────────────────────────────────────────────────────────
        workflow.add_node("run_full_pipeline",       self._run_full_pipeline)
        workflow.add_node("apply_bmi_corrections",   self._apply_bmi_corrections)   # GAP-1 FIX
        workflow.add_node("verify_plausibility",     self._verify_plausibility)     # GAP-2 FIX
        workflow.add_node("save_profile",            self._save_profile)
        workflow.add_node("update_session_completed", self._update_session_completed)
        workflow.add_node("update_session_failed",   self._update_session_failed)
        workflow.add_node("trigger_recommendation",  self._trigger_recommendation)

        # ── Add edges ───────────────────────────────────────────────────────────
        workflow.set_entry_point("run_full_pipeline")
        workflow.add_conditional_edges(
            "run_full_pipeline",
            self._should_continue,
            {
                "continue": "apply_bmi_corrections",   # GAP-1: now in the chain
                "fail":     "update_session_failed",
            }
        )
        workflow.add_edge("apply_bmi_corrections",   "verify_plausibility")  # GAP-2
        workflow.add_edge("verify_plausibility",     "save_profile")
        workflow.add_edge("save_profile",            "update_session_completed")
        workflow.add_edge("update_session_completed", "trigger_recommendation")
        workflow.add_edge("trigger_recommendation",  END)
        workflow.add_edge("update_session_failed",   END)

        return workflow.compile()

    def _should_continue(self, state: dict) -> str:
        """Determine if workflow should continue or fail based on errors."""
        return "continue" if not state["errors"] else "fail"

    def execute(self, input_data: dict) -> dict:
        """
        Run the full measurement pipeline.
        All LangGraph nodes executed sequentially with state passed through.
        """
        from apps.ai.workflows.base import BaseWorkflow

        base = BaseWorkflow()
        base.workflow_type = self.workflow_type
        base.model_version = self.model_version

        state = {
            "session_id":     input_data["session_id"],
            "user_id":        input_data["user_id"],
            "user_height_cm": float(input_data["user_height_cm"]),
            "user_weight_kg": float(input_data.get("user_weight_kg") or 0) or None,
            "user_age":       input_data.get("user_age"),           # B-1 FIX
            "landmarks":      input_data["landmarks"],
            "side_landmarks": input_data.get("side_landmarks"),     # GAP-5 FIX
            "scale_factor":   1.0,
            "measurement_result": {},
            "bmi":            None,
            "plausibility_warnings": [],
            "correction_applied":    "none",
            "profile_id":     None,
            "errors":         [],
        }

        exec_id = base.start_execution(
            user_id=input_data.get("user_id"),
            input_snapshot={
                "session_id":      input_data["session_id"],
                "user_height_cm":  input_data["user_height_cm"],
                "user_age":        input_data.get("user_age"),
                "has_side_pose":   input_data.get("side_landmarks") is not None,
                "landmark_count":  len(input_data.get("landmarks", [])),
            },
            celery_task_id=input_data.get("celery_task_id", ""),
        )

        try:
            result = self.graph.invoke(state)

            if result["errors"]:
                base.fail_execution("; ".join(result["errors"]))
            else:
                base.complete_execution(output_snapshot={
                    "profile_id":             result.get("profile_id"),
                    "quality_score":          result["measurement_result"].get("quality_score"),
                    "is_valid":               result["measurement_result"].get("is_valid"),
                    "bmi":                    result.get("bmi"),
                    "correction_applied":     result.get("correction_applied"),
                    "plausibility_warnings":  result.get("plausibility_warnings", []),
                })

        except Exception as exc:
            logger.exception(
                "[MeasurementWorkflow] Unexpected error for session %s", state["session_id"]
            )
            state["errors"].append(str(exc))
            self._update_session_failed(state, error=str(exc))
            base.fail_execution(exc)
            result = state

        return self._build_output(result)

    # ── Workflow nodes ──────────────────────────────────────────────────────────

    def _run_full_pipeline(self, state: dict) -> dict:
        """
        Runs the complete geometry pipeline.

        GAP-5 FIX: Now passes side_landmarks to the geometry engine when available.
        The geometry engine uses side pose for ellipse-formula circumference estimation:
            C ≈ π × (a + b) where a = front half-width, b = side half-depth

        If side_landmarks is None, falls back to front-only mode.
        Also passes user_age for age-corrected anthropometric ratios.
        """
        from apps.ai.utils.geometry import run_full_measurement_pipeline

        kwargs: dict = {
            "landmarks":      state["landmarks"],
            "user_height_cm": state["user_height_cm"],
            "user_weight_kg": state.get("user_weight_kg"),
        }

        # GAP-5 FIX: pass side_landmarks when available
        if state.get("side_landmarks"):
            kwargs["side_landmarks"] = state["side_landmarks"]

        # B-1 FIX: pass user_age for anthropometric ratio selection
        if state.get("user_age") is not None:
            kwargs["user_age"] = state["user_age"]

        result = run_full_measurement_pipeline(**kwargs)
        state["measurement_result"] = result
        if not result["is_valid"]:
            state["errors"].append(result["validation_message"])
        return state

    def _apply_bmi_corrections(self, state: dict) -> dict:
        """
        GAP-1 FIX: Apply BMI-based circumference scaling.

        Uses NHANES 2017-2020 proxy correction table:
          - underweight (<18.5):  × 0.92
          - normal (18.5–24.9):   × 1.00 (no change)
          - overweight (25–29.9): × 1.10
          - obese (≥30.0):        × 1.22

        Only applied when user_weight_kg is provided.
        Applied to: waist, hip, chest, belly_button circumference fields.
        """
        weight_kg = state.get("user_weight_kg")
        height_cm = state["user_height_cm"]

        if not weight_kg or weight_kg <= 0:
            state["correction_applied"] = "skipped_no_weight"
            return state

        # Compute BMI
        height_m = height_cm / 100.0
        bmi = weight_kg / (height_m ** 2)
        state["bmi"] = round(bmi, 1)

        # Find correction tier
        correction_factor = 1.00
        tier_name = "normal"
        for threshold, name, factor in _BMI_CORRECTION_TABLE:
            if bmi < threshold:
                correction_factor = factor
                tier_name = name
                break

        state["correction_applied"] = tier_name

        if correction_factor == 1.00:
            logger.debug(
                "[MeasurementWorkflow] BMI=%.1f → normal tier, no correction needed", bmi
            )
            return state

        # Apply correction to circumference fields in measurement_result
        result = state["measurement_result"]
        circumferences = result.get("circumferences", {})
        profile_fields = result.get("profile_fields", {})

        corrected_count = 0
        for field in list(circumferences.keys()):
            if field in _CIRCUMFERENCE_FIELDS:
                original = circumferences[field]
                if isinstance(original, (int, float)) and original > 0:
                    circumferences[field] = round(original * correction_factor, 1)
                    corrected_count += 1

        for field in list(profile_fields.keys()):
            if field in _CIRCUMFERENCE_FIELDS:
                original = profile_fields[field]
                if isinstance(original, (int, float)) and original > 0:
                    profile_fields[field] = round(original * correction_factor, 1)

        logger.info(
            "[MeasurementWorkflow] BMI=%.1f (%s) → correction factor %.2f applied to %d fields",
            bmi, tier_name, correction_factor, corrected_count,
        )
        return state

    def _verify_plausibility(self, state: dict) -> dict:
        """
        GAP-2 FIX: Anthropometric plausibility verification.

        Checks that extracted measurements fall within human-plausible ranges
        relative to user height. Implausible values get WARNING flags (not errors) —
        the scan still saves, but plausibility_warnings is populated so the frontend
        can show a QualityReport alert and ask the user to re-scan if needed.

        Rules (WHO Reference Charts + 3DBody validation data):
          - Shoulder width:  20–38% of height
          - Chest (bust):    45–70% of height
          - Waist:           30–65% of height
          - Hip:             45–75% of height
          - Arm length:      28–55% of height
          - Inseam:          40–60% of height
          - Waist-to-hip ratio: 0.55–1.20
        """
        result      = state["measurement_result"]
        height_cm   = state["user_height_cm"]
        warnings    = state.get("plausibility_warnings", [])
        all_meas    = {
            **result.get("linear", {}),
            **result.get("circumferences", {}),
            **result.get("profile_fields", {}),
        }

        for field_key, min_ratio, max_ratio, label in _PLAUSIBILITY_RULES:
            val = all_meas.get(field_key)
            if val is None or not isinstance(val, (int, float)):
                continue
            min_cm = height_cm * min_ratio
            max_cm = height_cm * max_ratio
            if val < min_cm:
                warnings.append(
                    f"{label} ({val:.1f} cm) seems too small for height {height_cm:.0f} cm "
                    f"— expected ≥{min_cm:.0f} cm. Check pose and retake if needed."
                )
                logger.warning(
                    "[MeasurementWorkflow] Plausibility fail: %s=%.1f < %.1f (%.0f%% of height)",
                    field_key, val, min_cm, min_ratio * 100
                )
            elif val > max_cm:
                warnings.append(
                    f"{label} ({val:.1f} cm) seems too large for height {height_cm:.0f} cm "
                    f"— expected ≤{max_cm:.0f} cm. Check pose and retake if needed."
                )
                logger.warning(
                    "[MeasurementWorkflow] Plausibility fail: %s=%.1f > %.1f (%.0f%% of height)",
                    field_key, val, max_cm, max_ratio * 100
                )

        # Waist-to-hip ratio check
        waist = all_meas.get("waist_cm") or all_meas.get("waist")
        hip   = all_meas.get("hip_cm")   or all_meas.get("hip")
        if waist and hip and isinstance(waist, (int, float)) and isinstance(hip, (int, float)):
            if hip > 0:
                whr = waist / hip
                if whr < _WHR_MIN or whr > _WHR_MAX:
                    warnings.append(
                        f"Waist-to-hip ratio ({whr:.2f}) is outside the expected range "
                        f"({_WHR_MIN}–{_WHR_MAX}). Pose may have shifted during scan."
                    )

        state["plausibility_warnings"] = warnings
        if warnings:
            logger.info(
                "[MeasurementWorkflow] %d plausibility warning(s) for session %s",
                len(warnings), state["session_id"]
            )
        return state

    def _save_profile(self, state: dict) -> dict:
        """
        Create or update MeasurementProfile from extracted measurements.
        Sets the new profile as the user's default.
        """
        result = state["measurement_result"]
        profile_fields = result.get("profile_fields", {})

        if not profile_fields:
            state["errors"].append("No measurements could be extracted from the pose.")
            return state

        try:
            from apps.measurements.services.measurement_service import (
                create_or_update_ai_scan_profile,
            )
            profile = create_or_update_ai_scan_profile(
                user_id=state["user_id"],
                measurements=profile_fields,
                quality_score=result.get("quality_score", 0.0),
                source="ai_camera_scan",
            )
            state["profile_id"] = str(profile.id)
            logger.info(
                "[MeasurementWorkflow] Profile %s saved for user %s",
                state["profile_id"], state["user_id"],
            )
        except Exception as exc:
            logger.exception("[MeasurementWorkflow] _save_profile failed")
            state["errors"].append(f"Profile save failed: {exc}")

        return state

    def _update_session_completed(self, state: dict) -> None:
        """
        Update BodyScanSession to COMPLETED with extracted measurements.
        Includes BMI, correction tier, and plausibility_warnings (GAP-1/GAP-2 FIX).
        """
        try:
            from apps.measurements.models.scan import BodyScanSession
            result = state["measurement_result"]

            # Build measurements_cm dict — union of linear + circumferences
            measurements_cm = {
                **result.get("linear", {}),
                **result.get("circumferences", {}),
            }

            update_fields: dict = {
                "status":               "completed",
                "scan_confidence":      result.get("quality_score", 0.0),
                "extracted_measurements": measurements_cm,
                "completed_at":         timezone.now(),
            }

            # GAP-1 FIX: persist BMI + correction tier
            if state.get("bmi") is not None:
                update_fields["bmi"] = state["bmi"]
            if state.get("correction_applied"):
                update_fields["correction_applied"] = state["correction_applied"]

            # GAP-2 FIX: persist plausibility_warnings as JSON array
            if state.get("plausibility_warnings"):
                update_fields["plausibility_warnings"] = state["plausibility_warnings"]

            BodyScanSession.objects.filter(
                session_id=state["session_id"]
            ).update(**update_fields)

        except Exception as exc:
            logger.warning("[MeasurementWorkflow] _update_session_completed: %s", exc)

    def _update_session_failed(self, state: dict, error: str = "") -> None:
        """Update BodyScanSession to FAILED."""
        try:
            from apps.measurements.models.scan import BodyScanSession
            BodyScanSession.objects.filter(
                session_id=state["session_id"]
            ).update(
                status="failed",
                error_message=error or ("; ".join(state["errors"][:2])),
                completed_at=timezone.now(),
            )
        except Exception as exc:
            logger.warning("[MeasurementWorkflow] _update_session_failed: %s", exc)

    def _trigger_recommendation(self, state: dict) -> None:
        """Fire recommendation pipeline for user's measurement profile."""
        if not state.get("profile_id"):
            return
        try:
            from apps.ai.tasks.recommendation_tasks import run_profile_recommendations
            run_profile_recommendations.delay(
                profile_id=state["profile_id"],
                user_id=state["user_id"],
            )
        except Exception as exc:
            logger.warning("[MeasurementWorkflow] _trigger_recommendation: %s", exc)

    def _build_output(self, state: dict) -> dict:
        result = state.get("measurement_result", {})
        return {
            "session_id":            state["session_id"],
            "profile_id":            state.get("profile_id"),
            "is_valid":              result.get("is_valid", False),
            "quality_score":         result.get("quality_score", 0.0),
            "bmi":                   state.get("bmi"),
            "correction_applied":    state.get("correction_applied", "none"),
            "plausibility_warnings": state.get("plausibility_warnings", []),
            "errors":                state["errors"],
            "profile_fields":        result.get("profile_fields", {}),
        }
