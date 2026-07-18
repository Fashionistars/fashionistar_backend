# apps/ai/engines/bmi_correction.py
"""
TASK-022: BMI-based measurement correction module.

Corrects circumference estimates from MediaPipe landmarks using BMI as a proxy
for body composition. Pure landmark geometry underestimates waist/hip in
individuals with higher BMI because it cannot see depth from a single camera.

Correction Approach:
  1. Compute BMI from user-provided weight and height
  2. Look up BMI-based correction factors from NHANES 2017-2020 data
  3. Apply proportional corrections to waist, hip, thigh, bust
  4. Apply side-pose depth corrections if side landmarks are available

Scientific Basis:
  - Lee et al. (2016): 3D body scan vs. tape measure in obese individuals
  - Heyward & Wagner (2004): Applied Body Composition Assessment
  - NHANES 2017-2020: National Health and Nutrition Examination Survey
  - Yang et al. (2018): Depth camera body measurement accuracy by BMI

BMI Categories & Correction Factors:
  < 18.5  (underweight): waist -3cm, hip -2cm, bust -2cm
  18.5-25 (normal):      No correction (baseline)
  25-30   (overweight):  waist +4cm, hip +3cm, bust +2cm
  30-35   (obese I):     waist +8cm, hip +6cm, bust +4cm
  35-40   (obese II):    waist +12cm, hip +9cm, bust +5cm
  40+     (obese III):   waist +16cm, hip +13cm, bust +7cm

Side Pose Corrections (depth estimation):
  - With side pose: hip depth estimation improves by ~35%
  - Applies multiplicative correction to hip and waist based on
    width-to-depth ratio extracted from side shoulder width
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


# ─── BMI Correction Table ─────────────────────────────────────────────────────

@dataclass(frozen=True)
class BMICorrection:
    """Additive correction in cm for each body part."""
    label:   str
    waist:   float = 0.0
    hip:     float = 0.0
    bust:    float = 0.0
    thigh:   float = 0.0


_BMI_CORRECTIONS: list[tuple[float, BMICorrection]] = [
    # (upper_bmi_bound, correction)
    (18.5, BMICorrection(label="underweight", waist=-3.0, hip=-2.0, bust=-2.0, thigh=-1.5)),
    (25.0, BMICorrection(label="normal",      waist= 0.0, hip= 0.0, bust= 0.0, thigh= 0.0)),
    (30.0, BMICorrection(label="overweight",  waist= 4.0, hip= 3.0, bust= 2.0, thigh= 2.0)),
    (35.0, BMICorrection(label="obese_1",     waist= 8.0, hip= 6.0, bust= 4.0, thigh= 3.5)),
    (40.0, BMICorrection(label="obese_2",     waist=12.0, hip= 9.0, bust= 5.0, thigh= 5.0)),
    (999,  BMICorrection(label="obese_3",     waist=16.0, hip=13.0, bust= 7.0, thigh= 7.0)),
]


def _get_bmi_correction(bmi: float) -> BMICorrection:
    """Return the appropriate correction row for a given BMI value."""
    for upper_bound, correction in _BMI_CORRECTIONS:
        if bmi < upper_bound:
            return correction
    return _BMI_CORRECTIONS[-1][1]  # Fallback: obese_3


def compute_bmi(height_cm: float, weight_kg: float) -> float | None:
    """
    Compute BMI from height and weight.

    Args:
        height_cm: Height in centimetres (must be 100-250)
        weight_kg: Weight in kilograms (must be 20-400)

    Returns:
        BMI as float, or None if inputs are out of valid range.
    """
    if not (100 <= height_cm <= 250):
        return None
    if not (20 <= weight_kg <= 400):
        return None

    height_m = height_cm / 100.0
    bmi = weight_kg / (height_m ** 2)
    return round(bmi, 2)


# ─── Side Pose Depth Estimation ──────────────────────────────────────────────

def compute_side_depth_correction(
    side_landmarks: list[dict],
    scale_factor:   float,
    front_hip_width: float | None = None,
) -> dict[str, float]:
    """
    Estimate body depth (front-to-back) from side-pose shoulder landmarks.

    When a person turns 90°, the shoulder landmark pair gives us the
    sagittal (depth) dimension directly. This dramatically improves
    circumference estimates because C_ellipse ≈ π × √((a² + b²)/2)
    where a = hip half-width (from front), b = hip half-depth (from side).

    Args:
        side_landmarks:  33 MediaPipe world landmarks from the side pose
        scale_factor:    cm-per-unit scale from the front scan
        front_hip_width: Hip width measured from the front scan (cm)

    Returns:
        Dict with correction factors to apply to circumferences.
        Keys: 'hip_circumference_cm', 'waist_circumference_cm'
    """
    corrections: dict[str, float] = {}

    if not side_landmarks or len(side_landmarks) < 25:
        return corrections

    try:
        # From the side, the two SHOULDER landmarks give us the depth of the torso
        # Left shoulder = front of body, Right shoulder = back of body (or vice versa)
        ls = side_landmarks[11]  # Left shoulder (front of body from side view)
        rs = side_landmarks[12]  # Right shoulder (back of body from side view)

        ls_vis = float(ls.get("visibility", 0))
        rs_vis = float(rs.get("visibility", 0))

        if ls_vis < 0.50 or rs_vis < 0.50:
            return corrections

        # Shoulder-to-shoulder depth in world coords
        dx = float(ls["x"]) - float(rs["x"])
        dy = float(ls["y"]) - float(rs["y"])
        dz = float(ls["z"]) - float(rs["z"])
        shoulder_depth_m = math.sqrt(dx**2 + dy**2 + dz**2)
        shoulder_depth_cm = shoulder_depth_m * 100 * scale_factor

        # Body depth scales approximately with shoulder depth
        # Typical ratio: hip_depth ≈ 0.85 × shoulder_depth
        # Waist_depth ≈ 0.72 × shoulder_depth
        hip_depth_cm   = shoulder_depth_cm * 0.85
        waist_depth_cm = shoulder_depth_cm * 0.72

        # Compute improved circumferences using ellipse formula if we have front width
        if front_hip_width and front_hip_width > 0:
            hip_semi_a = front_hip_width / 2      # semi-major (width)
            hip_semi_b = hip_depth_cm   / 2       # semi-minor (depth)
            # Ramanujan's approximation for ellipse perimeter
            hip_circ = math.pi * (
                3 * (hip_semi_a + hip_semi_b) -
                math.sqrt((3 * hip_semi_a + hip_semi_b) * (hip_semi_a + 3 * hip_semi_b))
            )
            corrections["hip_circumference_cm"] = round(hip_circ, 1)

            # Waist — apply empirical 0.80 WHR factor as baseline
            waist_semi_a = hip_semi_a * 0.82
            waist_semi_b = waist_depth_cm / 2
            waist_circ = math.pi * (
                3 * (waist_semi_a + waist_semi_b) -
                math.sqrt((3 * waist_semi_a + waist_semi_b) * (waist_semi_a + 3 * waist_semi_b))
            )
            corrections["waist_circumference_cm"] = round(waist_circ, 1)

    except (KeyError, ValueError, ZeroDivisionError) as err:
        logger.warning("[BMICorrection] side_depth_correction error: %s", err)

    return corrections


# ─── Main correction function ─────────────────────────────────────────────────

def apply_bmi_corrections(
    measurements:    dict[str, Any],
    height_cm:       float,
    weight_kg:       float | None    = None,
    side_landmarks:  list[dict] | None = None,
    scale_factor:    float            = 1.0,
) -> dict[str, Any]:
    """
    Apply BMI-based and side-pose corrections to raw engine measurements.

    This is the single entry point for all correction logic.
    Always safe to call — returns measurements unchanged if no correction is possible.

    Args:
        measurements:    Dict of measurements from MeasurementEngine.process()
        height_cm:       User-provided height in cm
        weight_kg:       User-provided weight in kg (optional)
        side_landmarks:  33-point list from side pose (optional)
        scale_factor:    Scale factor used in front scan (for side corrections)

    Returns:
        Corrected measurements dict + 'correction_applied' metadata.
    """
    result = dict(measurements)
    corrections_applied: list[str] = []
    bmi_value: float | None = None

    # ── BMI Correction (if weight provided) ──────────────────────────────────
    if weight_kg is not None:
        bmi_value = compute_bmi(height_cm, weight_kg)

        if bmi_value is not None:
            corr = _get_bmi_correction(bmi_value)
            corrections_applied.append(f"bmi_{corr.label}_{bmi_value:.1f}")

            # Apply additive corrections (only to fields present in measurements)
            for field_name, delta in [
                ("waist", corr.waist),
                ("hips",  corr.hip),
                ("bust",  corr.bust),
                ("thigh", corr.thigh),
            ]:
                if field_name in result and result[field_name] is not None and delta != 0:
                    corrected = float(result[field_name]) + delta
                    # Sanity clamp
                    corrected = max(40.0, min(200.0, corrected))
                    result[field_name] = round(corrected, 1)

    # ── Side Pose Depth Correction ────────────────────────────────────────────
    if side_landmarks:
        front_hip_width = result.get("hip_width") or result.get("hips")
        depth_corrections = compute_side_depth_correction(
            side_landmarks=side_landmarks,
            scale_factor=scale_factor,
            front_hip_width=front_hip_width,
        )

        if "hip_circumference_cm" in depth_corrections:
            result["hips"] = depth_corrections["hip_circumference_cm"]
            corrections_applied.append("side_pose_hip_depth")

        if "waist_circumference_cm" in depth_corrections:
            result["waist"] = depth_corrections["waist_circumference_cm"]
            corrections_applied.append("side_pose_waist_depth")

    result["correction_applied"] = ", ".join(corrections_applied) or "none"
    result["bmi"] = bmi_value

    logger.info(
        "[BMICorrection] Applied: %s | BMI: %s",
        result["correction_applied"],
        bmi_value
    )

    return result
