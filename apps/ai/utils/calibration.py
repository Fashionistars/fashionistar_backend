# apps/ai/utils/calibration.py
"""
Pixel-to-cm calibration utilities for the FASHIONISTAR AI Measurement Engine.

These functions are used when working with 2D pixel coordinates
(e.g., from a single RGB camera without depth information).

For MediaPipe Tasks Vision world landmarks (in metres), use geometry.py instead.
calibration.py is used when:
  - Applying a known reference object (credit card, A4 paper, etc.)
  - Computing focal length from user height
  - Converting from normalised landmark coords to real-world cm

Key concept:
  pixel_to_cm_ratio = real_world_reference_cm / pixel_size_of_reference
  real_distance_cm  = pixel_distance × pixel_to_cm_ratio
"""

from __future__ import annotations

import math
from typing import NamedTuple


# ─── Standard reference object sizes ─────────────────────────────────────────

class ReferenceObject(NamedTuple):
    name:       str
    width_cm:   float
    height_cm:  float


REFERENCE_OBJECTS = {
    "credit_card":  ReferenceObject("Credit Card",      8.56,  5.40),
    "a4_paper":     ReferenceObject("A4 Paper",         29.7,  21.0),
    "a5_paper":     ReferenceObject("A5 Paper",         21.0,  14.85),
    "iphone_14":    ReferenceObject("iPhone 14",        14.67,  7.15),
    "us_dollar":    ReferenceObject("US Dollar Bill",   15.6,   6.63),
}


# ─── Core calibration class ───────────────────────────────────────────────────

class CameraCalibrator:
    """
    Compute pixel-to-cm scale using a known reference object or user height.

    Priority:
    1. Reference object (highest accuracy — 1-2% error)
    2. User height + detected body height (3-5% error)
    3. Default focal length estimate (5-8% error)
    """

    # Assumed camera focal length in pixels (for a 1920×1080 sensor)
    # This is an approximation — actual focal length varies by device
    DEFAULT_FOCAL_LENGTH_PX = 1200.0

    # Typical camera-to-subject distance in metres (for 1.5m standing distance)
    DEFAULT_SUBJECT_DISTANCE_M = 1.5

    def __init__(self, image_width_px: int = 1280, image_height_px: int = 720) -> None:
        self.image_width  = image_width_px
        self.image_height = image_height_px
        self._scale_cm_per_px: float | None = None

    def calibrate_from_reference(
        self,
        reference_name: str,
        reference_width_px: float,
    ) -> float:
        """
        Calibrate scale from a known reference object's pixel width.

        Args:
            reference_name:     Key from REFERENCE_OBJECTS dict
            reference_width_px: Detected pixel width of the reference object

        Returns:
            cm_per_pixel scale factor

        Example:
            calibrator.calibrate_from_reference("credit_card", 320)
            → 8.56 / 320 = 0.02675 cm/pixel
        """
        ref = REFERENCE_OBJECTS.get(reference_name)
        if not ref:
            raise ValueError(f"Unknown reference object: {reference_name}")
        if reference_width_px <= 0:
            raise ValueError("reference_width_px must be positive")

        scale = ref.width_cm / reference_width_px
        self._scale_cm_per_px = scale
        return scale

    def calibrate_from_user_height(
        self,
        user_height_cm: float,
        body_height_px: float,
    ) -> float:
        """
        Calibrate scale from the user's known height and the detected body
        height in pixels.

        Args:
            user_height_cm: User-provided or auto-estimated height (cm)
            body_height_px: Pixel distance from head to feet in the image

        Returns:
            cm_per_pixel scale factor
        """
        if body_height_px <= 0:
            raise ValueError("body_height_px must be positive")
        if user_height_cm <= 0 or user_height_cm > 300:
            raise ValueError("user_height_cm must be between 1 and 300")

        scale = user_height_cm / body_height_px
        self._scale_cm_per_px = scale
        return scale

    def pixels_to_cm(
        self,
        pixel_distance: float,
        scale_cm_per_px: float | None = None,
    ) -> float:
        """
        Convert a pixel distance to centimetres.

        Args:
            pixel_distance:  Distance in pixels
            scale_cm_per_px: Override scale (uses stored scale if None)

        Returns:
            Distance in centimetres
        """
        scale = scale_cm_per_px or self._scale_cm_per_px
        if scale is None:
            raise RuntimeError("No calibration performed. Call calibrate_* first.")
        return pixel_distance * scale

    def estimate_distance_from_focal_length(
        self,
        object_real_height_cm: float,
        object_height_px: float,
        focal_length_px: float = DEFAULT_FOCAL_LENGTH_PX,
    ) -> float:
        """
        Estimate camera-to-object distance using the pinhole camera model.

        Formula: distance = (focal_length × real_height) / pixel_height

        Args:
            object_real_height_cm: Known real-world height of the object (cm)
            object_height_px:      Object's height in pixels
            focal_length_px:       Camera focal length in pixels

        Returns:
            Estimated distance in centimetres
        """
        if object_height_px <= 0:
            raise ValueError("object_height_px must be positive")
        return (focal_length_px * object_real_height_cm) / object_height_px


# ─── Standalone helper functions ──────────────────────────────────────────────

def pixel_euclidean(x1: float, y1: float, x2: float, y2: float) -> float:
    """2D Euclidean distance between two pixel points."""
    return math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)


def normalised_to_pixel(
    nx: float,
    ny: float,
    image_width: int,
    image_height: int,
) -> tuple[float, float]:
    """
    Convert MediaPipe normalised landmark coordinates (0-1) to pixel coordinates.

    Note: MediaPipe world landmarks (x, y, z in metres) do NOT need this
    conversion. Only use for the normalised 2D landmarks when drawing on canvas.
    """
    return nx * image_width, ny * image_height


def world_to_pixel_approximate(
    world_x_m: float,
    world_y_m: float,
    focal_length_px: float = 1200.0,
    cx: float = 640.0,
    cy: float = 360.0,
    depth_m: float = 1.5,
) -> tuple[float, float]:
    """
    Project a MediaPipe world coordinate (in metres) to approximate pixel
    position using a pinhole camera model.

    Useful for drawing world landmarks onto a 2D canvas.

    Args:
        world_x_m:       World X in metres
        world_y_m:       World Y in metres
        focal_length_px: Camera focal length in pixels
        cx, cy:          Principal point (image centre)
        depth_m:         Assumed depth / distance from camera

    Returns:
        (px, py) in pixels
    """
    if depth_m <= 0:
        depth_m = 1.5

    px = (world_x_m / depth_m) * focal_length_px + cx
    py = (world_y_m / depth_m) * focal_length_px + cy
    return px, py
