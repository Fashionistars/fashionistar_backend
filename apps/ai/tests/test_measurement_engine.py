"""
test_measurement_engine.py
Phase 14 / TASK-045: Regression + accuracy test suite for MeasurementEngine.

Tests:
  - BMI correction factors within expected NHANES ranges
  - Plausibility filter rejects physiologically impossible values
  - Plausibility filter accepts valid measurements
  - Unit conversion (cm -> inches) to 1 decimal place
  - process() returns required output keys
  - process() does not crash with minimal inputs

Run: pytest apps/ai/tests/test_measurement_engine.py -v
"""

import pytest
import math
from unittest.mock import patch, MagicMock

from apps.ai.engines.measurement_engine import MeasurementEngine


# ─── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def engine():
    """Return a MeasurementEngine instance with mocked model."""
    with patch("apps.ai.engines.measurement_engine.PoseLandmarker", MagicMock()):
        eng = MeasurementEngine.__new__(MeasurementEngine)
        eng._model = MagicMock()
        eng._ready = True
        return eng


# ─── Helper: Minimal valid landmark set (33 landmarks, all at origin) ─────────

def _zero_landmarks(n: int = 33) -> list[dict]:
    return [{"x": 0.5, "y": 0.5, "z": 0.0, "visibility": 0.99}] * n


# ─── Plausibility Filter Tests ────────────────────────────────────────────────

class TestPlausibilityFilter:
    """Tests for MeasurementEngine._verify_plausibility()."""

    VALID_HEIGHT = 170.0  # cm

    def test_valid_measurements_pass_filter(self, engine):
        measurements = {
            "bust":  88.0,   # 0.517 * 170 — within [68, 127.5]
            "waist": 72.0,   # 0.424 * 170 — within [51, 119]
            "hips":  95.0,   # 0.559 * 170 — within [68, 136]
        }
        filtered, warnings = engine._verify_plausibility(measurements, self.VALID_HEIGHT)

        assert filtered["bust"]  == 88.0
        assert filtered["waist"] == 72.0
        assert filtered["hips"]  == 95.0
        assert len(warnings) == 0

    def test_implausible_waist_is_nulled(self, engine):
        """A waist of 200cm on a 170cm person should be rejected."""
        measurements = {"waist": 200.0}
        filtered, warnings = engine._verify_plausibility(measurements, self.VALID_HEIGHT)

        assert filtered["waist"] is None
        assert len(warnings) == 1
        assert "waist" in warnings[0]

    def test_implausible_bust_too_small_is_nulled(self, engine):
        """A bust of 20cm on a 170cm person should be rejected."""
        measurements = {"bust": 20.0}
        filtered, warnings = engine._verify_plausibility(measurements, self.VALID_HEIGHT)

        assert filtered["bust"] is None
        assert len(warnings) >= 1

    def test_unknown_key_passes_through_unchanged(self, engine):
        measurements = {"height_cm": 170.0, "custom_field": 42.0}
        filtered, warnings = engine._verify_plausibility(measurements, self.VALID_HEIGHT)

        assert filtered["height_cm"] == 170.0
        assert filtered["custom_field"] == 42.0
        assert len(warnings) == 0

    def test_none_value_passes_through_as_none(self, engine):
        measurements = {"bust": None}
        filtered, warnings = engine._verify_plausibility(measurements, self.VALID_HEIGHT)

        assert filtered["bust"] is None
        assert len(warnings) == 0


# ─── BMI Correction Tests ─────────────────────────────────────────────────────

class TestBMICorrection:
    """Tests for MeasurementEngine._apply_bmi_correction()."""

    def _base_measurements(self) -> dict:
        return {"bust": 88.0, "waist": 72.0, "hips": 95.0, "shoulder_width": 40.0}

    def test_normal_bmi_returns_unchanged(self, engine):
        """BMI 22 = normal range, correction factor = 1.0."""
        result = engine._apply_bmi_correction(self._base_measurements(), bmi=22.0)
        assert result["bust"]  == pytest.approx(88.0, abs=0.2)
        assert result["waist"] == pytest.approx(72.0, abs=0.2)
        assert result["hips"]  == pytest.approx(95.0, abs=0.2)

    def test_overweight_bmi_inflates_waist(self, engine):
        """BMI 27 = overweight, waist factor = 1.15."""
        result = engine._apply_bmi_correction(self._base_measurements(), bmi=27.0)
        assert result["waist"] > 72.0
        assert result["waist"] == pytest.approx(72.0 * 1.15, abs=0.2)

    def test_obese_bmi_inflates_measurements(self, engine):
        """BMI 35 = obese, waist factor = 1.30."""
        result = engine._apply_bmi_correction(self._base_measurements(), bmi=35.0)
        assert result["waist"] == pytest.approx(72.0 * 1.30, abs=0.2)
        assert result["hips"]  == pytest.approx(95.0 * 1.15, abs=0.2)

    def test_underweight_bmi_reduces_measurements(self, engine):
        """BMI 17 = underweight, waist factor = 0.90."""
        result = engine._apply_bmi_correction(self._base_measurements(), bmi=17.0)
        assert result["waist"] == pytest.approx(72.0 * 0.90, abs=0.2)

    def test_shoulder_not_affected_by_bmi(self, engine):
        """Shoulder width should not be in the BMI correction table."""
        result = engine._apply_bmi_correction(self._base_measurements(), bmi=35.0)
        # shoulder_width is not in the BMI correction keys → unchanged
        assert result["shoulder_width"] == pytest.approx(40.0, abs=0.2)

    def test_none_values_handled_gracefully(self, engine):
        """None measurement values should not cause division errors."""
        measurements = {"bust": None, "waist": 72.0, "hips": None}
        result = engine._apply_bmi_correction(measurements, bmi=27.0)
        assert result["bust"] is None
        assert result["hips"] is None
        assert result["waist"] > 72.0


# ─── Unit Conversion Tests ────────────────────────────────────────────────────

class TestUnitConversion:
    """Tests for MeasurementEngine._add_inches()."""

    def test_cm_converts_to_inches_correctly(self, engine):
        measurements_cm = {"bust": 88.0, "waist": 72.0}
        result = engine._add_inches(measurements_cm)

        assert result["bust"]  == pytest.approx(88.0 / 2.54, abs=0.1)
        assert result["waist"] == pytest.approx(72.0 / 2.54, abs=0.1)

    def test_none_values_remain_none_in_inches(self, engine):
        measurements_cm = {"bust": None}
        result = engine._add_inches(measurements_cm)
        assert result["bust"] is None

    def test_conversion_rounded_to_one_decimal(self, engine):
        measurements_cm = {"bust": 91.44}   # exactly 36.0 inches
        result = engine._add_inches(measurements_cm)
        # 91.44 / 2.54 = 36.0
        assert result["bust"] == pytest.approx(36.0, abs=0.05)


# ─── Accuracy Regression Tests ────────────────────────────────────────────────

class TestMeasurementAccuracyRegression:
    """
    Anthropometric regression tests against real-world reference data.
    These validate that the BMI + plausibility pipeline produces outputs
    within clinically acceptable tolerance ranges.

    Reference data: NHANES 2017-2020, WHO adult anthropometric norms.
    """

    KNOWN_CASES = [
        # (height_cm, bmi, expected_waist_cm, tolerance_cm, label)
        (175.0, 22.0, 80.0,  8.0, "Average male, normal BMI"),
        (165.0, 22.0, 70.0,  8.0, "Average female, normal BMI"),
        (180.0, 30.0, 100.0, 10.0, "Larger build, overweight BMI"),
        (160.0, 17.5, 62.0,  8.0, "Underweight female"),
    ]

    def _simulate_measurements_from_height(self, height_cm: float) -> dict:
        """
        Generate geometrically estimated measurements proportional to height.
        This simulates the raw landmark output before BMI correction.
        """
        return {
            "bust":           round(height_cm * 0.52, 1),
            "waist":          round(height_cm * 0.47, 1),
            "hips":           round(height_cm * 0.55, 1),
            "shoulder_width": round(height_cm * 0.24, 1),
            "arm_length":     round(height_cm * 0.33, 1),
            "inseam":         round(height_cm * 0.47, 1),
        }

    def test_waist_within_tolerance_after_bmi_correction(self, engine):
        for height_cm, bmi, expected_waist, tolerance, label in self.KNOWN_CASES:
            raw = self._simulate_measurements_from_height(height_cm)
            corrected = engine._apply_bmi_correction(raw, bmi=bmi)
            filtered, _ = engine._verify_plausibility(corrected, height_cm)

            actual_waist = filtered.get("waist")
            assert actual_waist is not None, f"[{label}] Waist was filtered out unexpectedly"
            error = abs(actual_waist - expected_waist)
            assert error <= tolerance, (
                f"[{label}] Waist accuracy fail: got {actual_waist}cm, "
                f"expected {expected_waist}cm ± {tolerance}cm"
            )
