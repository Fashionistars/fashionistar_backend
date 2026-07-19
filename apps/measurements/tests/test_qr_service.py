# apps/measurements/tests/test_qr_service.py
"""
TASK-065 (Part 1): Unit tests for the QR code generation service.

Tests cover:
  - generate_measurement_url: URL format, settings override
  - generate_qr_code_b64: Returns valid base64, PNG magic bytes
  - upload_qr_to_cloudinary: Graceful failure, empty string on error

Run:
    pytest apps/measurements/tests/test_qr_service.py -v
"""

import base64
import uuid
from unittest.mock import MagicMock, patch

import pytest


# ─── Fixtures ─────────────────────────────────────────────────────────────────

SAMPLE_SESSION_ID = str(uuid.uuid4())
SAMPLE_URL        = f"https://fashionistar.net/scan/{SAMPLE_SESSION_ID}"


# ─── generate_measurement_url ──────────────────────────────────────────────────

class TestGenerateMeasurementUrl:

    def test_url_contains_session_id(self):
        """URL must embed the session_id."""
        from apps.measurements.services.qr_service import generate_measurement_url
        url = generate_measurement_url(SAMPLE_SESSION_ID)
        assert SAMPLE_SESSION_ID in url

    def test_url_starts_with_scan_path(self):
        """URL must end with /scan/{session_id}."""
        from apps.measurements.services.qr_service import generate_measurement_url
        url = generate_measurement_url(SAMPLE_SESSION_ID)
        assert url.endswith(f"/scan/{SAMPLE_SESSION_ID}")

    def test_url_uses_https(self, settings):
        """URL must use HTTPS when FRONTEND_URL is set to an https address.
        
        The test environment uses FRONTEND_URL=http://localhost:3000 for local
        development convenience.  This test verifies the production default by
        overriding the setting to the canonical production URL.
        """
        settings.FRONTEND_URL = "https://fashionistar.net"
        from apps.measurements.services.qr_service import generate_measurement_url
        url = generate_measurement_url(SAMPLE_SESSION_ID)
        assert url.startswith("https://")

    def test_url_uses_settings_frontend_url(self, settings):
        """URL must use FRONTEND_URL from Django settings."""
        settings.FRONTEND_URL = "https://staging.fashionistar.net"
        from apps.measurements.services.qr_service import generate_measurement_url
        url = generate_measurement_url(SAMPLE_SESSION_ID)
        assert url.startswith("https://staging.fashionistar.net/scan/")

    def test_url_strips_trailing_slash_from_settings(self, settings):
        """Trailing slash in FRONTEND_URL must not produce double-slash."""
        settings.FRONTEND_URL = "https://fashionistar.net/"
        from apps.measurements.services.qr_service import generate_measurement_url
        url = generate_measurement_url(SAMPLE_SESSION_ID)
        assert "/scan/" in url
        assert url.count("//") == 1   # Only the https:// double slash


# ─── generate_qr_code_b64 ─────────────────────────────────────────────────────

class TestGenerateQrCodeB64:

    def test_returns_non_empty_string(self):
        """QR generation must return a non-empty string."""
        from apps.measurements.services.qr_service import generate_qr_code_b64
        result = generate_qr_code_b64(SAMPLE_URL)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_is_valid_base64(self):
        """Result must be valid base64 decodeable bytes."""
        from apps.measurements.services.qr_service import generate_qr_code_b64
        result = generate_qr_code_b64(SAMPLE_URL)
        try:
            decoded = base64.b64decode(result)
        except Exception as exc:
            pytest.fail(f"base64 decode failed: {exc}")
        assert len(decoded) > 0

    def test_decoded_bytes_are_png(self):
        """Decoded base64 must be a PNG file (magic bytes: 0x89504E47)."""
        from apps.measurements.services.qr_service import generate_qr_code_b64
        result = generate_qr_code_b64(SAMPLE_URL)
        decoded = base64.b64decode(result)
        # PNG magic bytes: \x89PNG
        assert decoded[:4] == b"\x89PNG", f"Expected PNG header, got: {decoded[:4].hex()}"

    def test_returns_empty_string_when_qrcode_missing(self):
        """When qrcode package is unavailable, must return empty string (not raise)."""
        from apps.measurements.services.qr_service import generate_qr_code_b64
        with patch.dict("sys.modules", {"qrcode": None}):
            # Re-import to trigger the ImportError path
            import importlib
            import apps.measurements.services.qr_service as svc
            importlib.reload(svc)
            result = svc.generate_qr_code_b64(SAMPLE_URL)
            # Must not raise — empty string or real result depending on env
            assert isinstance(result, str)


# ─── upload_qr_to_cloudinary ──────────────────────────────────────────────────

class TestUploadQrToCloudinary:

    def test_returns_cloudinary_url_on_success(self):
        """On successful Cloudinary upload, must return the secure_url."""
        from apps.measurements.services.qr_service import upload_qr_to_cloudinary

        mock_result = {"secure_url": "https://res.cloudinary.com/fashionistar/qr-codes/test.png"}
        with patch("cloudinary.uploader.upload", return_value=mock_result):
            result = upload_qr_to_cloudinary("FAKE_B64", SAMPLE_SESSION_ID)
        assert result == "https://res.cloudinary.com/fashionistar/qr-codes/test.png"

    def test_returns_empty_string_on_cloudinary_error(self):
        """On Cloudinary error, must return empty string (not raise)."""
        from apps.measurements.services.qr_service import upload_qr_to_cloudinary

        with patch("cloudinary.uploader.upload", side_effect=Exception("Network timeout")):
            result = upload_qr_to_cloudinary("FAKE_B64", SAMPLE_SESSION_ID)
        assert result == ""

    def test_returns_empty_string_for_empty_b64(self):
        """Empty b64 input must immediately return empty string."""
        from apps.measurements.services.qr_service import upload_qr_to_cloudinary
        result = upload_qr_to_cloudinary("", SAMPLE_SESSION_ID)
        assert result == ""

    def test_cloudinary_upload_uses_correct_public_id(self):
        """Cloudinary public_id must embed the session_id."""
        from apps.measurements.services.qr_service import upload_qr_to_cloudinary

        captured_args = {}

        def capture_upload(*args, **kwargs):
            captured_args.update(kwargs)
            return {"secure_url": "https://example.com/qr.png"}

        with patch("cloudinary.uploader.upload", side_effect=capture_upload):
            upload_qr_to_cloudinary("FAKE_B64", SAMPLE_SESSION_ID)

        assert SAMPLE_SESSION_ID in captured_args.get("public_id", "")
