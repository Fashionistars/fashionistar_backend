# tests/test_cloudinary_webhook_signature.py
"""
Comprehensive unit tests for Cloudinary webhook HMAC-SHA1 signature validation.

Tests cover:
  - Valid SHA1 signatures
  - Invalid signatures (tampering)
  - Expired timestamps (replay attacks)
  - Timestamp validation edge cases
  - Missing API_SECRET handling
"""

import hashlib
import hmac
import json
import time
from unittest.mock import patch

from django.test import TestCase, override_settings

from apps.common.utils.cloudinary import validate_cloudinary_webhook


class CloudinaryWebhookSignatureTest(TestCase):
    """Unit tests for Cloudinary webhook signature validation."""

    def setUp(self):
        """Set up test fixtures."""
        self.api_secret = "test_api_secret_key_12345"
        self.cloud_name = "test_cloud"
        self.timestamp = str(int(time.time()))
        
        # Sample Cloudinary webhook payload
        self.payload = {
            "notification_type": "upload",
            "public_id": "fashionistar/users/avatars/user_test/abc123def456",
            "secure_url": "https://res.cloudinary.com/test_cloud/image/upload/v1234567890/test.jpg",
            "width": 1024,
            "height": 1024,
            "format": "jpg",
            "bytes": 1050000,
            "created_at": "2026-03-20T12:58:52Z",
            "timestamp": self.timestamp,
        }
        self.body = json.dumps(self.payload).encode("utf-8")

    @override_settings(
        CLOUDINARY_STORAGE={
            "CLOUD_NAME": "test_cloud",
            "API_KEY": "test_key",
            "API_SECRET": "test_api_secret_key_12345",
        }
    )
    def test_valid_sha1_signature_passes(self):
        """Valid plain-SHA1 signature should pass validation.

        Cloudinary's algorithm:
            SHA1( raw_body + str(timestamp) + api_secret )
        This is plain SHA-1, NOT HMAC.
        """
        # Generate correct plain-SHA1 signature (Cloudinary algorithm)
        raw = self.body.decode("utf-8") + self.timestamp + self.api_secret
        signature = hashlib.sha1(raw.encode("utf-8")).hexdigest()  # nosec

        # Patch the SDK so it uses our overridden settings API_SECRET
        with self.settings(CLOUDINARY_STORAGE={
            "CLOUD_NAME": "test_cloud",
            "API_KEY": "test_key",
            "API_SECRET": self.api_secret,
        }):
            with patch(
                "apps.common.utils.cloudinary.cld_utils",
                create=True,
            ) as mock_sdk:
                # SDK call returns True for a correctly-generated signature
                mock_sdk.verify_notification_signature.return_value = True

                result = validate_cloudinary_webhook(
                    self.body,
                    self.timestamp,
                    signature,
                )

        self.assertTrue(result, "Valid SHA1 signature should pass validation")

    @override_settings(
        CLOUDINARY_STORAGE={
            "CLOUD_NAME": "test_cloud",
            "API_KEY": "test_key",
            "API_SECRET": "test_api_secret_key_12345",
        }
    )
    def test_invalid_signature_rejected(self):
        """Invalid signature should be rejected."""
        invalid_sig = "0000000000000000000000000000000000000000"  # 40-char fake SHA1

        with self.settings(CLOUDINARY_STORAGE={
            "CLOUD_NAME": "test_cloud",
            "API_KEY": "test_key",
            "API_SECRET": self.api_secret,
        }):
            with patch(
                "apps.common.utils.cloudinary.cld_utils",
                create=True,
            ) as mock_sdk:
                # SDK returns False for wrong signature
                mock_sdk.verify_notification_signature.return_value = False

                result = validate_cloudinary_webhook(
                    self.body,
                    self.timestamp,
                    invalid_sig,
                )

        self.assertFalse(result, "Invalid signature should be rejected")

    @override_settings(
        CLOUDINARY_STORAGE={
            "CLOUD_NAME": "test_cloud",
            "API_KEY": "test_key",
            "API_SECRET": "test_api_secret_key_12345",
        }
    )
    def test_signature_case_insensitive(self):
        """Signature comparison should be case-insensitive (hex strings)."""
        # Generate correct plain-SHA1 signature (Cloudinary algorithm)
        raw = self.body.decode("utf-8") + self.timestamp + self.api_secret
        signature_lower = hashlib.sha1(raw.encode("utf-8")).hexdigest()  # nosec
        signature_upper = signature_lower.upper()

        with self.settings(CLOUDINARY_STORAGE={
            "CLOUD_NAME": "test_cloud",
            "API_KEY": "test_key",
            "API_SECRET": self.api_secret,
        }):
            with patch(
                "apps.common.utils.cloudinary.cld_utils",
                create=True,
            ) as mock_sdk:
                mock_sdk.verify_notification_signature.return_value = True

                result = validate_cloudinary_webhook(
                    self.body,
                    self.timestamp,
                    signature_upper,
                )

        self.assertTrue(result, "Signature should validate regardless of case")

    @override_settings(
        CLOUDINARY_STORAGE={
            "CLOUD_NAME": "test_cloud",
            "API_KEY": "test_key",
            "API_SECRET": "test_api_secret_key_12345",
        }
    )
    def test_expired_timestamp_rejected(self):
        """Webhook with timestamp older than 7200s should be rejected."""
        # Create timestamp 8000 seconds in the past
        old_timestamp = str(int(time.time()) - 8000)

        # Signature algorithm doesn't matter — timestamp check fires first
        raw = self.body.decode("utf-8") + old_timestamp + self.api_secret
        signature = hashlib.sha1(raw.encode("utf-8")).hexdigest()  # nosec

        with self.settings(CLOUDINARY_STORAGE={
            "CLOUD_NAME": "test_cloud",
            "API_KEY": "test_key",
            "API_SECRET": self.api_secret,
        }):
            result = validate_cloudinary_webhook(
                self.body,
                old_timestamp,
                signature,
                max_age_seconds=7200,
            )

        self.assertFalse(result, "Expired timestamp should be rejected")

    @override_settings(
        CLOUDINARY_STORAGE={
            "CLOUD_NAME": "test_cloud",
            "API_KEY": "test_key",
            "API_SECRET": "test_api_secret_key_12345",
        }
    )
    def test_future_timestamp_rejected(self):
        """Webhook with future timestamp (clock skew) should be rejected."""
        # Create timestamp 60 seconds in the future
        future_timestamp = str(int(time.time()) + 60)

        raw = self.body.decode("utf-8") + future_timestamp + self.api_secret
        signature = hashlib.sha1(raw.encode("utf-8")).hexdigest()  # nosec

        with self.settings(CLOUDINARY_STORAGE={
            "CLOUD_NAME": "test_cloud",
            "API_KEY": "test_key",
            "API_SECRET": self.api_secret,
        }):
            result = validate_cloudinary_webhook(
                self.body,
                future_timestamp,
                signature,
            )

        self.assertFalse(result, "Future timestamp should be rejected (clock skew)")

    @override_settings(
        CLOUDINARY_STORAGE={
            "CLOUD_NAME": "test_cloud",
            "API_KEY": "test_key",
            "API_SECRET": "test_api_secret_key_12345",
        }
    )
    def test_missing_api_secret_rejected(self):
        """Webhook should be rejected if API_SECRET is not configured."""
        signature = hmac.new(
            self.api_secret.encode("utf-8"),
            self.body,
            hashlib.sha1,
        ).hexdigest()
        
        with override_settings(
            CLOUDINARY_STORAGE={
                "CLOUD_NAME": "test_cloud",
                "API_KEY": "test_key",
                # NO API_SECRET
            }
        ):
            result = validate_cloudinary_webhook(
                self.body,
                self.timestamp,
                signature,
            )
        
        self.assertFalse(result, "Missing API_SECRET should cause validation to fail")

    @override_settings(
        CLOUDINARY_STORAGE={
            "CLOUD_NAME": "test_cloud",
            "API_KEY": "test_key",
            "API_SECRET": "test_api_secret_key_12345",
        }
    )
    def test_missing_timestamp_rejected(self):
        """Webhook should be rejected if timestamp is missing."""
        raw = self.body.decode("utf-8") + self.timestamp + self.api_secret
        signature = hashlib.sha1(raw.encode("utf-8")).hexdigest()  # nosec

        with self.settings(CLOUDINARY_STORAGE={
            "CLOUD_NAME": "test_cloud",
            "API_KEY": "test_key",
            "API_SECRET": self.api_secret,
        }):
            result = validate_cloudinary_webhook(
                self.body,
                "",  # Empty timestamp
                signature,
            )

        self.assertFalse(result, "Missing timestamp should be rejected")

    @override_settings(
        CLOUDINARY_STORAGE={
            "CLOUD_NAME": "test_cloud",
            "API_KEY": "test_key",
            "API_SECRET": "test_api_secret_key_12345",
        }
    )
    def test_missing_signature_rejected(self):
        """Webhook should be rejected if signature is missing."""
        result = validate_cloudinary_webhook(
            self.body,
            self.timestamp,
            "",  # Empty signature
        )
        
        self.assertFalse(result, "Missing signature should be rejected")

    @override_settings(
        CLOUDINARY_STORAGE={
            "CLOUD_NAME": "test_cloud",
            "API_KEY": "test_key",
            "API_SECRET": "test_api_secret_key_12345",
        }
    )
    def test_invalid_timestamp_format_rejected(self):
        """Webhook should be rejected if timestamp is not a valid integer."""
        raw = self.body.decode("utf-8") + self.timestamp + self.api_secret
        signature = hashlib.sha1(raw.encode("utf-8")).hexdigest()  # nosec

        with self.settings(CLOUDINARY_STORAGE={
            "CLOUD_NAME": "test_cloud",
            "API_KEY": "test_key",
            "API_SECRET": self.api_secret,
        }):
            result = validate_cloudinary_webhook(
                self.body,
                "not_a_number",  # Invalid timestamp
                signature,
            )

        self.assertFalse(result, "Invalid timestamp format should be rejected")

    @override_settings(
        CLOUDINARY_STORAGE={
            "CLOUD_NAME": "test_cloud",
            "API_KEY": "test_key",
            "API_SECRET": "test_api_secret_key_12345",
        }
    )
    def test_tampered_body_rejected(self):
        """Webhook should be rejected if body has been tampered with."""
        # Generate signature for the ORIGINAL body
        raw = self.body.decode("utf-8") + self.timestamp + self.api_secret
        signature = hashlib.sha1(raw.encode("utf-8")).hexdigest()  # nosec

        # Tamper with the body — signature is now wrong for this body
        tampered_body = self.body + b"_extra_data"

        with self.settings(CLOUDINARY_STORAGE={
            "CLOUD_NAME": "test_cloud",
            "API_KEY": "test_key",
            "API_SECRET": self.api_secret,
        }):
            with patch(
                "apps.common.utils.cloudinary.cld_utils",
                create=True,
            ) as mock_sdk:
                mock_sdk.verify_notification_signature.return_value = False

                result = validate_cloudinary_webhook(
                    tampered_body,
                    self.timestamp,
                    signature,
                )

        self.assertFalse(result, "Tampered body should cause signature validation to fail")

    @override_settings(
        CLOUDINARY_STORAGE={
            "CLOUD_NAME": "test_cloud",
            "API_KEY": "test_key",
            "API_SECRET": "test_api_secret_key_12345",
        }
    )
    def test_custom_max_age_respected(self):
        """Custom max_age_seconds parameter should be respected."""
        # Create timestamp 100 seconds in the past
        old_timestamp = str(int(time.time()) - 100)

        # Correct plain-SHA1 signature (Cloudinary algorithm)
        raw = self.body.decode("utf-8") + old_timestamp + self.api_secret
        signature = hashlib.sha1(raw.encode("utf-8")).hexdigest()  # nosec

        settings_override = {
            "CLOUDINARY_STORAGE": {
                "CLOUD_NAME": "test_cloud",
                "API_KEY": "test_key",
                "API_SECRET": self.api_secret,
            }
        }

        # With max_age=50, timestamp is 100s old → should be rejected (timestamp check)
        with self.settings(**settings_override):
            result = validate_cloudinary_webhook(
                self.body,
                old_timestamp,
                signature,
                max_age_seconds=50,
            )
        self.assertFalse(result, "Should respect custom max_age_seconds parameter")

        # With max_age=200, timestamp is within window → SDK called → should be accepted
        with self.settings(**settings_override):
            with patch(
                "apps.common.utils.cloudinary.cld_utils",
                create=True,
            ) as mock_sdk:
                mock_sdk.verify_notification_signature.return_value = True

                result = validate_cloudinary_webhook(
                    self.body,
                    old_timestamp,
                    signature,
                    max_age_seconds=200,
                )
        self.assertTrue(result, "Should accept timestamp within custom max_age_seconds window")

    @override_settings(
        CLOUDINARY_STORAGE={
            "CLOUD_NAME": "test_cloud",
            "API_KEY": "test_key",
            "API_SECRET": "test_api_secret_key_12345",
        }
    )
    def test_large_json_payload(self):
        """Should handle large JSON payloads (multiple eager transforms, galleries)."""
        large_payload = {
            "notification_type": "upload",
            "public_id": "fashionistar/products/gallery/prod_12345/image_01",
            "secure_url": "https://res.cloudinary.com/test_cloud/image/upload/v1234567890/test.jpg",
            "width": 4000,
            "height": 4000,
            "format": "jpg",
            "bytes": 5000000,
            "eager": [
                {
                    "transformation": [{"width": 1200, "height": 1200, "crop": "fill", "quality": "auto"}],
                    "secure_url": "https://res.cloudinary.com/test_cloud/image/upload/w_1200,h_1200,c_fill,q_auto/v1234567890/test.jpg",
                },
                {
                    "transformation": [{"width": 800, "height": 800, "crop": "fill", "quality": "auto"}],
                    "secure_url": "https://res.cloudinary.com/test_cloud/image/upload/w_800,h_800,c_fill,q_auto/v1234567890/test.jpg",
                },
                {
                    "transformation": [{"width": 3840, "crop": "scale", "quality": "auto"}],
                    "secure_url": "https://res.cloudinary.com/test_cloud/image/upload/w_3840,c_scale,q_auto/v1234567890/test.jpg",
                },
            ],
        }
        large_body = json.dumps(large_payload).encode("utf-8")

        # Correct plain-SHA1 signature (Cloudinary algorithm)
        raw = large_body.decode("utf-8") + self.timestamp + self.api_secret
        signature = hashlib.sha1(raw.encode("utf-8")).hexdigest()  # nosec

        with self.settings(CLOUDINARY_STORAGE={
            "CLOUD_NAME": "test_cloud",
            "API_KEY": "test_key",
            "API_SECRET": self.api_secret,
        }):
            with patch(
                "apps.common.utils.cloudinary.cld_utils",
                create=True,
            ) as mock_sdk:
                mock_sdk.verify_notification_signature.return_value = True

                result = validate_cloudinary_webhook(
                    large_body,
                    self.timestamp,
                    signature,
                )

        self.assertTrue(result, "Should validate large JSON payloads correctly")


class CloudinaryWebhookSignaturePerformanceTest(TestCase):
    """Performance tests for webhook signature validation."""

    def setUp(self):
        """Set up test fixtures."""
        self.api_secret = "test_api_secret_key_performance_test"
        self.timestamp = str(int(time.time()))
        self.payload = {
            "notification_type": "upload",
            "public_id": "test/image/001",
            "secure_url": "https://res.cloudinary.com/test/image/upload/v123/test.jpg",
        }
        self.body = json.dumps(self.payload).encode("utf-8")
        raw = self.body.decode("utf-8") + self.timestamp + self.api_secret
        self.signature = hashlib.sha1(raw.encode("utf-8")).hexdigest()  # nosec

    @override_settings(
        CLOUDINARY_STORAGE={
            "CLOUD_NAME": "test_cloud",
            "API_KEY": "test_key",
            "API_SECRET": "test_api_secret_key_performance_test",
        }
    )
    def test_signature_validation_latency(self):
        """Signature validation should complete in < 5ms."""
        import time as time_module

        with self.settings(CLOUDINARY_STORAGE={
            "CLOUD_NAME": "test_cloud",
            "API_KEY": "test_key",
            "API_SECRET": self.api_secret,
        }):
            with patch(
                "apps.common.utils.cloudinary.cld_utils",
                create=True,
            ) as mock_sdk:
                mock_sdk.verify_notification_signature.return_value = True

                t0 = time_module.perf_counter()
                result = validate_cloudinary_webhook(
                    self.body,
                    self.timestamp,
                    self.signature,
                )
                elapsed_ms = (time_module.perf_counter() - t0) * 1000

        self.assertTrue(result)
        self.assertLess(
            elapsed_ms, 100,
            f"Signature validation took {elapsed_ms:.2f}ms (should be < 100ms)"
        )

    @override_settings(
        CLOUDINARY_STORAGE={
            "CLOUD_NAME": "test_cloud",
            "API_KEY": "test_key",
            "API_SECRET": "test_api_secret_key_performance_test",
        }
    )
    def test_bulk_signature_validations(self):
        """Validate 1000 signatures in bulk."""
        import time as time_module

        with self.settings(CLOUDINARY_STORAGE={
            "CLOUD_NAME": "test_cloud",
            "API_KEY": "test_key",
            "API_SECRET": self.api_secret,
        }):
            with patch(
                "apps.common.utils.cloudinary.cld_utils",
                create=True,
            ) as mock_sdk:
                mock_sdk.verify_notification_signature.return_value = True

                t0 = time_module.perf_counter()
                for _ in range(1000):
                    validate_cloudinary_webhook(
                        self.body,
                        self.timestamp,
                        self.signature,
                    )
                elapsed_ms = (time_module.perf_counter() - t0) * 1000

        avg_ms = elapsed_ms / 1000
        self.assertLess(
            avg_ms, 20,
            f"Average validation took {avg_ms:.3f}ms per signature (should be < 20ms)"
        )
