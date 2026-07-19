# apps/ai/tests/test_measurement_loophole_fixes.py
"""
E-1 — E-4: pytest tests for all 4 backend loophole fixes.

Tests:
  E-1: test_bmi_correction_applied_for_obese_user
  E-2: test_plausibility_rejects_22cm_waist
  E-3: test_age_forwarded_to_workflow
  E-4: test_side_landmarks_accepted_by_serializer
"""

import pytest
from unittest.mock import patch, MagicMock, call
from apps.ai.workflows.measurement import MeasurementWorkflow, _BMI_CORRECTION_TABLE


# ─── Shared fixtures ──────────────────────────────────────────────────────────

def _make_landmarks(count: int = 33) -> list:
    """Generate N dummy landmark dicts."""
    return [{"x": 0.5, "y": float(i) / 100, "z": 0.01, "visibility": 0.95}
            for i in range(count)]


def _make_base_state(**overrides) -> dict:
    """
    Build a minimal MeasurementState-compatible dict.
    `measurement_result` must already be populated (simulates post-pipeline state).
    """
    state = {
        "session_id":     "test-session-001",
        "user_id":        42,
        "user_height_cm": 175.0,
        "user_weight_kg": None,
        "user_age":       None,
        "landmarks":      _make_landmarks(),
        "side_landmarks": None,
        "scale_factor":   1.0,
        "measurement_result": {
            "is_valid":   True,
            "is_valid":   True,
            "quality_score": 0.90,
            "validation_message": "",
            "linear": {
                "shoulder_width_cm": 44.0,
                "arm_length_cm":     64.0,
                "inseam_cm":         80.0,
                "height_cm":         175.0,
            },
            "circumferences": {
                "chest_cm":    92.0,
                "waist_cm":    78.0,
                "hip_cm":      96.0,
                "thigh_cm":    56.0,
            },
            "profile_fields": {
                "shoulder_width_cm": 44.0,
                "chest_cm":    92.0,
                "waist_cm":    78.0,
                "hip_cm":      96.0,
            },
        },
        "bmi":                   None,
        "plausibility_warnings": [],
        "correction_applied":    "none",
        "profile_id":            None,
        "errors":                [],
    }
    state.update(overrides)
    return state


# ─── E-1: BMI Correction ──────────────────────────────────────────────────────

class TestBmiCorrectionNode:
    """E-1: test_bmi_correction_applied_for_obese_user"""

    def setup_method(self):
        self.workflow = MeasurementWorkflow.__new__(MeasurementWorkflow)

    def test_no_correction_without_weight(self):
        """If user_weight_kg is None, correction must be skipped."""
        state = _make_base_state(user_weight_kg=None)
        result = self.workflow._apply_bmi_corrections(state)
        assert result["correction_applied"] == "skipped_no_weight"
        assert result["bmi"] is None
        # Circumferences should be unchanged
        assert result["measurement_result"]["circumferences"]["waist_cm"] == 78.0

    def test_obese_user_waist_scaled_up(self):
        """E-1: Obese user (BMI ≥ 30) should get waist corrected by ×1.22."""
        # height=175cm, weight=120kg → BMI = 120 / 1.75² = 39.2 (obese)
        state = _make_base_state(user_height_cm=175.0, user_weight_kg=120.0)
        result = self.workflow._apply_bmi_corrections(state)

        assert result["correction_applied"] == "obese"
        assert result["bmi"] == pytest.approx(39.2, abs=0.2)

        # waist was 78.0 → 78.0 × 1.22 = 95.16
        corrected_waist = result["measurement_result"]["circumferences"]["waist_cm"]
        assert corrected_waist == pytest.approx(78.0 * 1.22, abs=0.2)

    def test_overweight_user_correction(self):
        """Overweight user (BMI 25–29.9) → ×1.10 correction."""
        # height=175, weight=85 → BMI = 27.8 (overweight)
        state = _make_base_state(user_height_cm=175.0, user_weight_kg=85.0)
        result = self.workflow._apply_bmi_corrections(state)
        assert result["correction_applied"] == "overweight"
        assert result["measurement_result"]["circumferences"]["chest_cm"] == pytest.approx(
            92.0 * 1.10, abs=0.2
        )

    def test_underweight_user_correction(self):
        """Underweight user (BMI <18.5) → ×0.92 correction (narrower proportions)."""
        # height=175, weight=50 → BMI = 16.3 (underweight)
        state = _make_base_state(user_height_cm=175.0, user_weight_kg=50.0)
        result = self.workflow._apply_bmi_corrections(state)
        assert result["correction_applied"] == "underweight"
        assert result["measurement_result"]["circumferences"]["waist_cm"] == pytest.approx(
            78.0 * 0.92, abs=0.2
        )

    def test_normal_bmi_no_change(self):
        """Normal BMI (18.5–24.9) → correction factor 1.0, no change."""
        # height=175, weight=70 → BMI = 22.9 (normal)
        state = _make_base_state(user_height_cm=175.0, user_weight_kg=70.0)
        result = self.workflow._apply_bmi_corrections(state)
        assert result["correction_applied"] == "normal"
        assert result["measurement_result"]["circumferences"]["waist_cm"] == 78.0


# ─── E-2: Plausibility Verification ──────────────────────────────────────────

class TestPlausibilityNode:
    """E-2: test_plausibility_rejects_22cm_waist"""

    def setup_method(self):
        self.workflow = MeasurementWorkflow.__new__(MeasurementWorkflow)

    def test_22cm_waist_flagged_as_implausible(self):
        """E-2: A 22 cm waist on a 175 cm person must be flagged as implausible."""
        state = _make_base_state()
        state["measurement_result"]["circumferences"]["waist_cm"] = 22.0
        state["measurement_result"]["profile_fields"]["waist_cm"] = 22.0

        result = self.workflow._verify_plausibility(state)

        warnings = result["plausibility_warnings"]
        assert len(warnings) >= 1
        waist_warnings = [w for w in warnings if "Waist" in w]
        assert len(waist_warnings) >= 1
        assert "22.0" in waist_warnings[0]

    def test_normal_measurements_no_warnings(self):
        """Standard measurements should produce zero plausibility warnings."""
        state = _make_base_state()
        result = self.workflow._verify_plausibility(state)
        assert result["plausibility_warnings"] == []

    def test_implausible_shoulder_width_flagged(self):
        """A 5cm shoulder width is physiologically impossible — must warn."""
        state = _make_base_state()
        state["measurement_result"]["linear"]["shoulder_width_cm"] = 5.0
        state["measurement_result"]["profile_fields"]["shoulder_width_cm"] = 5.0

        result = self.workflow._verify_plausibility(state)
        shoulder_warnings = [w for w in result["plausibility_warnings"] if "Shoulder" in w]
        assert len(shoulder_warnings) >= 1

    def test_whr_out_of_range_flagged(self):
        """An extreme waist-to-hip ratio must produce a warning."""
        state = _make_base_state()
        # waist=78, hip=50 → WHR = 1.56 (exceeds 1.20 max)
        state["measurement_result"]["circumferences"]["hip_cm"] = 50.0
        state["measurement_result"]["profile_fields"]["hip_cm"] = 50.0

        result = self.workflow._verify_plausibility(state)
        whr_warnings = [w for w in result["plausibility_warnings"] if "Waist-to-hip" in w]
        assert len(whr_warnings) >= 1


# ─── E-3: Age forwarded to workflow ──────────────────────────────────────────

class TestAgeForwarding:
    """E-3: test_age_forwarded_to_workflow"""

    @patch("apps.ai.workflows.measurement.MeasurementWorkflow._build_graph")
    def test_execute_populates_user_age_in_state(self, mock_build_graph):
        """user_age in execute() input must be stored in the workflow state."""
        # Build a mock graph that captures state
        captured_states = []

        class FakeGraph:
            def invoke(self, state):
                captured_states.append(dict(state))
                state["errors"] = []
                state["measurement_result"] = {
                    "is_valid": True, "quality_score": 0.85,
                    "profile_fields": {"height_cm": 175}, "linear": {}, "circumferences": {},
                }
                state["profile_id"] = "profile-123"
                return state

        mock_build_graph.return_value = FakeGraph()

        workflow = MeasurementWorkflow()

        with patch("apps.ai.workflows.base.BaseWorkflow") as MockBase:
            mock_base_instance = MagicMock()
            MockBase.return_value = mock_base_instance

            workflow.execute({
                "session_id":     "test-001",
                "user_id":        42,
                "user_height_cm": 175.0,
                "user_age":       28,
                "landmarks":      _make_landmarks(),
                "celery_task_id": "",
            })

        assert len(captured_states) == 1
        assert captured_states[0]["user_age"] == 28, (
            "user_age was not forwarded to the LangGraph state"
        )

    @patch("apps.ai.workflows.measurement.MeasurementWorkflow._build_graph")
    def test_execute_without_age_defaults_to_none(self, mock_build_graph):
        """If user_age is not in input, state["user_age"] should be None."""
        captured_states = []

        class FakeGraph:
            def invoke(self, state):
                captured_states.append(dict(state))
                state["errors"] = []
                state["measurement_result"] = {
                    "is_valid": True, "quality_score": 0.85,
                    "profile_fields": {"height_cm": 175}, "linear": {}, "circumferences": {},
                }
                state["profile_id"] = "profile-123"
                return state

        mock_build_graph.return_value = FakeGraph()
        workflow = MeasurementWorkflow()

        with patch("apps.ai.workflows.base.BaseWorkflow") as MockBase:
            MockBase.return_value = MagicMock()
            workflow.execute({
                "session_id":     "test-002",
                "user_id":        42,
                "user_height_cm": 175.0,
                "landmarks":      _make_landmarks(),
                "celery_task_id": "",
            })

        assert captured_states[0]["user_age"] is None


# ─── E-4: Side landmarks in serializer ───────────────────────────────────────

class TestSideLandmarksSerializer:
    """E-4: test_side_landmarks_accepted_by_serializer"""

    def _make_landmark_data(self) -> dict:
        return {"x": 0.5, "y": 0.5, "z": 0.01, "visibility": 0.95}

    def test_serializer_accepts_side_landmarks(self):
        """LandmarkSubmitSerializer must accept side_landmarks without error."""
        from apps.measurements.apis.sync.scan_views import LandmarkSubmitSerializer

        front_lms = [self._make_landmark_data() for _ in range(33)]
        side_lms  = [self._make_landmark_data() for _ in range(33)]

        data = {
            "user_height_cm": 175.0,
            "front_landmarks": front_lms,
            "side_landmarks":  side_lms,
        }
        serializer = LandmarkSubmitSerializer(data=data)
        assert serializer.is_valid(), (
            f"Serializer rejected valid side_landmarks payload: {serializer.errors}"
        )
        assert "side_landmarks" in serializer.validated_data

    def test_serializer_accepts_user_age(self):
        """LandmarkSubmitSerializer must accept user_age field."""
        from apps.measurements.apis.sync.scan_views import LandmarkSubmitSerializer

        front_lms = [self._make_landmark_data() for _ in range(33)]
        data = {
            "user_height_cm": 175.0,
            "user_age": 28,
            "front_landmarks": front_lms,
        }
        serializer = LandmarkSubmitSerializer(data=data)
        assert serializer.is_valid(), (
            f"Serializer rejected user_age: {serializer.errors}"
        )
        assert serializer.validated_data["user_age"] == 28

    def test_serializer_normalises_legacy_landmarks(self):
        """Legacy 'landmarks' field must be normalised into 'front_landmarks'."""
        from apps.measurements.apis.sync.scan_views import LandmarkSubmitSerializer

        front_lms = [self._make_landmark_data() for _ in range(33)]
        data = {
            "user_height_cm": 175.0,
            "landmarks": front_lms,  # legacy field
        }
        serializer = LandmarkSubmitSerializer(data=data)
        assert serializer.is_valid(), serializer.errors
        # After validate(), front_landmarks should be set from landmarks
        assert serializer.validated_data.get("front_landmarks") is not None

    def test_serializer_rejects_empty_payload(self):
        """Serializer must reject a payload with neither landmarks nor front_landmarks."""
        from apps.measurements.apis.sync.scan_views import LandmarkSubmitSerializer

        data = {"user_height_cm": 175.0}
        serializer = LandmarkSubmitSerializer(data=data)
        assert not serializer.is_valid()
        assert "front_landmarks" in serializer.errors or "non_field_errors" in serializer.errors
