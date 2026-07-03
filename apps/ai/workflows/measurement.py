# apps/ai/workflows/measurement.py
"""
MeasurementWorkflow — LangGraph state-machine for AI body measurement extraction.

Triggered by: Celery task apps.ai.tasks.measurement_tasks.process_body_scan
Input: MediaPipe world landmarks JSON + user height + session_id
Output: Completed MeasurementProfile

Graph:
  validate_quality
      ↓ pass
  calibrate
      ↓
  extract_measurements
      ↓
  save_profile
      ↓
  trigger_recommendation
      ↓
    END

  validate_quality ─ fail → update_session_failed → END
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
    Typed state dictionary for the MeasurementWorkflow graph.
    """
    session_id: str
    user_id: int
    user_height_cm: float
    user_weight_kg: Optional[float]
    landmarks: List[Dict[str, float]]
    scale_factor: float
    measurement_result: Dict[str, Any]
    profile_id: Optional[str]
    errors: List[str]


# ── Workflow class ──────────────────────────────────────────────────────────────

class MeasurementWorkflow:
    """
    LangGraph workflow for processing MediaPipe body scan data into
    a persisted MeasurementProfile.

    Usage (from Celery task):
        workflow = MeasurementWorkflow()
        result = workflow.execute({
            "session_id": "...",
            "user_id": 42,
            "user_height_cm": 175.0,
            "user_weight_kg": 70.0,  # optional
            "landmarks": [...],       # 33 MediaPipe world landmarks
            "celery_task_id": "...", # optional
        })

    Returns:
        {
            "session_id": "...",
            "profile_id": "...",    # or None on failure
            "quality_score": 0.85,
            "is_valid": True,
            "errors": [],
        }
    """

    workflow_type = "measurement"
    model_version = "mediapipe-tasks-0.10.14+geometry-1.0"

    def __init__(self):
        """Initialize the workflow and build the LangGraph state machine."""
        self.graph = self._build_graph()

    def _build_graph(self) -> StateGraph:
        """Build the LangGraph state machine with nodes and edges."""
        workflow = StateGraph(MeasurementState)

        # Add nodes
        workflow.add_node("run_full_pipeline", self._run_full_pipeline)
        workflow.add_node("save_profile", self._save_profile)
        workflow.add_node("update_session_completed", self._update_session_completed)
        workflow.add_node("update_session_failed", self._update_session_failed)
        workflow.add_node("trigger_recommendation", self._trigger_recommendation)

        # Add edges
        workflow.set_entry_point("run_full_pipeline")
        workflow.add_conditional_edges(
            "run_full_pipeline",
            self._should_continue,
            {
                "continue": "save_profile",
                "fail": "update_session_failed"
            }
        )
        workflow.add_edge("save_profile", "update_session_completed")
        workflow.add_edge("update_session_completed", "trigger_recommendation")
        workflow.add_edge("trigger_recommendation", END)
        workflow.add_edge("update_session_failed", END)

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
            "session_id":    input_data["session_id"],
            "user_id":       input_data["user_id"],
            "user_height_cm": float(input_data["user_height_cm"]),
            "user_weight_kg": float(input_data.get("user_weight_kg") or 0) or None,
            "landmarks":     input_data["landmarks"],
            "scale_factor":  1.0,
            "measurement_result": {},
            "profile_id":    None,
            "errors":        [],
        }

        exec_id = base.start_execution(
            user_id=input_data.get("user_id"),
            input_snapshot={
                "session_id": input_data["session_id"],
                "user_height_cm": input_data["user_height_cm"],
                "landmark_count": len(input_data.get("landmarks", [])),
            },
            celery_task_id=input_data.get("celery_task_id", ""),
        )

        try:
            # Execute the LangGraph state machine
            result = self.graph.invoke(state)

            # Update workflow execution tracking
            if result["errors"]:
                base.fail_execution("; ".join(result["errors"]))
            else:
                base.complete_execution(output_snapshot={
                    "profile_id":    result.get("profile_id"),
                    "quality_score": result["measurement_result"].get("quality_score"),
                    "is_valid":      result["measurement_result"].get("is_valid"),
                })

        except Exception as exc:
            logger.exception("[MeasurementWorkflow] Unexpected error for session %s", state["session_id"])
            state["errors"].append(str(exc))
            self._update_session_failed(state, error=str(exc))
            base.fail_execution(exc)
            result = state

        return self._build_output(result)

    # ── Workflow nodes ──────────────────────────────────────────────────────────

    def _run_full_pipeline(self, state: dict) -> dict:
        """
        Runs the complete geometry pipeline:
        1. validate_pose_quality
        2. compute_scale_factor
        3. extract_linear_measurements
        4. estimate_circumferences_geometric
        """
        from apps.ai.utils.geometry import run_full_measurement_pipeline

        result = run_full_measurement_pipeline(
            landmarks=state["landmarks"],
            user_height_cm=state["user_height_cm"],
            user_weight_kg=state.get("user_weight_kg"),
        )
        state["measurement_result"] = result
        if not result["is_valid"]:
            state["errors"].append(result["validation_message"])
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
        """Update BodyScanSession to COMPLETED with extracted measurements."""
        try:
            from apps.measurements.models.scan import BodyScanSession
            result = state["measurement_result"]

            BodyScanSession.objects.filter(
                session_id=state["session_id"]
            ).update(
                status="completed",
                scan_confidence=result.get("quality_score", 0.0),
                extracted_measurements={
                    **result.get("linear", {}),
                    **result.get("circumferences", {}),
                },
                completed_at=timezone.now(),
            )
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
            "session_id":    state["session_id"],
            "profile_id":    state.get("profile_id"),
            "is_valid":      result.get("is_valid", False),
            "quality_score": result.get("quality_score", 0.0),
            "errors":        state["errors"],
            "profile_fields": result.get("profile_fields", {}),
        }
