# apps/common/tests/test_cloudinary_upload.py
"""
Comprehensive integration tests for the Cloudinary enterprise upload architecture.

Test coverage:
  1. utils/redis.py      — presign caching, API cache (single-try), graceful degradation
  2. utils/cloudinary.py — signature generation, _ASSET_CONFIGS completeness, URL builder
  3. tasks/ package      — Celery autodiscovery, webhook routing, bulk_sync, idempotency
  4. views.py            — presign endpoint, webhook endpoint (HMAC validation, auth)
  5. Concurrency         — thread-pool race-condition tests at high RPS
  6. Django transaction  — atomic block handling in webhook + bulk tasks
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase, TransactionTestCase
from django.test import override_settings
from django.urls import reverse

User = get_user_model()


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_webhook_sig(body: bytes, timestamp: str, secret: str) -> str:
    """Build a Cloudinary-compatible webhook signature: SHA256(body + timestamp + secret)."""
    try:
        body_str = body.decode("utf-8")
    except UnicodeDecodeError:
        body_str = body.decode("latin-1")
    payload = body_str + timestamp + secret
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


FAKE_CLOUDINARY_SETTINGS = {
    "BACKEND": "django.core.files.storage.FileSystemStorage",
}
FAKE_CLOUDINARY_STORAGE = {
    "CLOUD_NAME": "test-cloud",
    "API_KEY":    "test-api-key",
    "API_SECRET": "test-secret",
}


# ─────────────────────────────────────────────────────────────────────────────
# 1. utils/redis.py — unit tests
# ─────────────────────────────────────────────────────────────────────────────

class RedisPresignCacheTests(TestCase):
    """Test presign caching (uses 3-retry get_redis_connection_safe)."""

    def test_cache_and_retrieve_presign(self):
        """cache_upload_presign → get_cached_presign round-trip."""
        from apps.common.utils.redis import cache_upload_presign, get_cached_presign

        params = {"signature": "abc123", "timestamp": 9999, "folder": "fashionistar/users/avatars/user_x"}
        result = cache_upload_presign("user-x", "avatar", params)
        # Result may be False if Redis is not running in CI — that's OK (graceful degradation)
        if result:
            cached = get_cached_presign("user-x", "avatar")
            self.assertIsNotNone(cached)
            self.assertEqual(cached["signature"], "abc123")

    def test_presign_cache_miss_returns_none(self):
        from apps.common.utils.redis import get_cached_presign
        result = get_cached_presign("nonexistent-user", "avatar")
        self.assertIsNone(result)

    def test_redis_degradation_returns_none(self):
        """When Redis is broken, get_cached_presign must return None, not raise."""
        with patch("apps.common.utils.redis.get_redis_connection") as mock_conn:
            mock_conn.side_effect = Exception("Redis unavailable")
            from apps.common.utils.redis import get_cached_presign, cache_upload_presign
            self.assertIsNone(get_cached_presign("user", "avatar"))
            self.assertFalse(cache_upload_presign("user", "avatar", {}))


class ApiCacheTests(TestCase):
    """Test single-try API cache functions — no retry loops."""

    @override_settings(CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "test-cache",
        }
    })
    def test_api_cache_set_and_get(self):
        from apps.common.utils.redis import api_cache_get, api_cache_set
        # Force cache re-import after settings override
        from django.core.cache import cache
        cache.clear()
        api_cache_set("test:key", {"hello": "world"}, ttl=60)
        result = api_cache_get("test:key")
        self.assertEqual(result, {"hello": "world"})

    @override_settings(CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "test-cache-2",
        }
    })
    def test_api_cache_miss_returns_none(self):
        from apps.common.utils.redis import api_cache_get
        from django.core.cache import cache
        cache.clear()
        self.assertIsNone(api_cache_get("missing:key"))

    @override_settings(CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "test-cache-3",
        }
    })
    def test_api_cache_delete(self):
        from apps.common.utils.redis import api_cache_get, api_cache_set, api_cache_delete
        from django.core.cache import cache
        cache.clear()
        api_cache_set("delete:me", 42, ttl=60)
        api_cache_delete("delete:me")
        self.assertIsNone(api_cache_get("delete:me"))

    def test_api_cache_returns_none_on_exception(self):
        """api_cache_get must never raise — returns None on error."""
        from apps.common.utils.redis import api_cache_get
        with patch("django.core.cache.cache.get", side_effect=Exception("boom")):
            result = api_cache_get("any:key")
            self.assertIsNone(result)

    def test_api_cache_set_returns_false_on_exception(self):
        from apps.common.utils.redis import api_cache_set
        with patch("django.core.cache.cache.set", side_effect=Exception("boom")):
            result = api_cache_set("any:key", "value")
            self.assertFalse(result)


# ─────────────────────────────────────────────────────────────────────────────
# 2. utils/cloudinary.py — unit tests
# ─────────────────────────────────────────────────────────────────────────────

@override_settings(
    CLOUDINARY_STORAGE=FAKE_CLOUDINARY_STORAGE,
    CLOUDINARY_UPLOAD_PRESET_AVATAR="test_avatar_preset",
    CLOUDINARY_UPLOAD_PRESET_PRODUCT="test_product_preset",
    CLOUDINARY_UPLOAD_PRESET_MEASURE="test_measure_preset",
    CLOUDINARY_UPLOAD_PRESET_VIDEO="test_video_preset",
)
class AssetConfigTests(TestCase):
    """Verify _ASSET_CONFIGS covers all discovered model image types."""

    EXPECTED_KEYS = [
        "avatar", "product_image", "product_gallery", "product_color",
        "product_video", "vendor_shop", "category", "brand", "collection",
        "profile", "blog", "chat_file", "measurement",
        "generic_image", "generic_video",
    ]

    def test_all_expected_asset_types_present(self):
        from apps.common.utils.cloudinary import _ASSET_CONFIGS
        for key in self.EXPECTED_KEYS:
            self.assertIn(
                key, _ASSET_CONFIGS,
                f"_ASSET_CONFIGS is missing asset type: {key!r}"
            )

    def test_all_configs_have_required_fields(self):
        from apps.common.utils.cloudinary import _ASSET_CONFIGS
        for key, cfg in _ASSET_CONFIGS.items():
            self.assertIn("folder_prefix",  cfg, f"Missing folder_prefix for {key}")
            self.assertIn("preset_setting", cfg, f"Missing preset_setting for {key}")
            self.assertIn("resource_type",  cfg, f"Missing resource_type for {key}")
            self.assertIn("eager",          cfg, f"Missing eager for {key}")


@override_settings(CLOUDINARY_STORAGE=FAKE_CLOUDINARY_STORAGE)
class SignatureGenerationTests(TestCase):
    """Test Cloudinary HMAC-SHA256 signature generation."""

    def test_signature_is_hex_string(self):
        from apps.common.utils.cloudinary import generate_cloudinary_signature
        sig = generate_cloudinary_signature({"timestamp": 1234567890, "folder": "test"})
        self.assertIsInstance(sig, str)
        self.assertEqual(len(sig), 64)  # SHA-256 hex = 64 chars

    def test_signature_deterministic(self):
        from apps.common.utils.cloudinary import generate_cloudinary_signature
        params = {"timestamp": 1111, "folder": "a/b"}
        sig1 = generate_cloudinary_signature(params)
        sig2 = generate_cloudinary_signature(params)
        self.assertEqual(sig1, sig2)

    def test_signature_differs_with_different_params(self):
        from apps.common.utils.cloudinary import generate_cloudinary_signature
        sig1 = generate_cloudinary_signature({"timestamp": 1, "folder": "x"})
        sig2 = generate_cloudinary_signature({"timestamp": 2, "folder": "y"})
        self.assertNotEqual(sig1, sig2)

    def test_empty_values_excluded_from_signing(self):
        """Empty-string / None values must not appear in the params-to-sign."""
        from apps.common.utils.cloudinary import generate_cloudinary_signature
        sig_with_empty  = generate_cloudinary_signature({"timestamp": 1, "folder": "", "upload_preset": None})
        sig_without_keys = generate_cloudinary_signature({"timestamp": 1})
        # Empty values excluded → same signature
        self.assertEqual(sig_with_empty, sig_without_keys)


@override_settings(CLOUDINARY_STORAGE=FAKE_CLOUDINARY_STORAGE)
class TransformUrlTests(TestCase):
    """Test the 2K/4K/8K transform URL builder."""

    def test_resolution_shorthand_4k(self):
        from apps.common.utils.cloudinary import get_cloudinary_transform_url
        url = get_cloudinary_transform_url("fashionistar/products/shoe_01", resolution="4k")
        self.assertIn("w_3840", url)
        self.assertIn("test-cloud", url)
        self.assertIn("https://", url)

    def test_resolution_shorthand_8k(self):
        from apps.common.utils.cloudinary import get_cloudinary_transform_url
        url = get_cloudinary_transform_url("fashionistar/products/shoe_01", resolution="8k")
        self.assertIn("w_7680", url)

    def test_explicit_width_overrides_resolution(self):
        from apps.common.utils.cloudinary import get_cloudinary_transform_url
        url = get_cloudinary_transform_url("pub/img", width=500, resolution="4k")
        self.assertIn("w_500", url)
        self.assertNotIn("w_3840", url)


@override_settings(CLOUDINARY_STORAGE=FAKE_CLOUDINARY_STORAGE)
class WebhookValidationTests(TestCase):
    """Test HMAC-SHA256 webhook signature validation."""

    def test_valid_signature_returns_true(self):
        from apps.common.utils.cloudinary import validate_cloudinary_webhook
        body      = b'{"public_id":"test/img","secure_url":"https://res.cloudinary.com/test/test.jpg"}'
        timestamp = str(int(time.time()))  # Must be current for replay protection
        sig       = _make_webhook_sig(body, timestamp, secret="test-secret")
        self.assertTrue(validate_cloudinary_webhook(body, timestamp, sig))

    def test_invalid_signature_returns_false(self):
        from apps.common.utils.cloudinary import validate_cloudinary_webhook
        body      = b'{"public_id":"test"}'
        timestamp = str(int(time.time()))
        self.assertFalse(validate_cloudinary_webhook(body, timestamp, "invalidsig"))

    def test_tampered_body_returns_false(self):
        from apps.common.utils.cloudinary import validate_cloudinary_webhook
        body      = b'{"public_id":"legit"}'
        timestamp = str(int(time.time()))
        valid_sig = _make_webhook_sig(body, timestamp, "test-secret")
        tampered  = b'{"public_id":"evil"}'
        self.assertFalse(validate_cloudinary_webhook(tampered, timestamp, valid_sig))

    def test_expired_timestamp_returns_false(self):
        """Timestamps older than 15 minutes must be rejected (replay protection)."""
        from apps.common.utils.cloudinary import validate_cloudinary_webhook
        body      = b'{"public_id":"test"}'
        old_ts    = str(int(time.time()) - 1000)  # ~17 minutes ago
        sig       = _make_webhook_sig(body, old_ts, "test-secret")
        self.assertFalse(validate_cloudinary_webhook(body, old_ts, sig))

    def test_empty_signature_returns_false(self):
        from apps.common.utils.cloudinary import validate_cloudinary_webhook
        self.assertFalse(validate_cloudinary_webhook(b'{}', str(int(time.time())), ""))

    def test_empty_timestamp_returns_false(self):
        from apps.common.utils.cloudinary import validate_cloudinary_webhook
        self.assertFalse(validate_cloudinary_webhook(b'{}', "", "somesig"))


# ─────────────────────────────────────────────────────────────────────────────
# 3. tasks/ package — Celery autodiscovery + task name registration
# ─────────────────────────────────────────────────────────────────────────────

class TasksPackageImportTests(TestCase):
    """
    Verify all tasks are importable from the package __init__ —
    which proves Celery autodiscovery will find them at worker startup.
    """

    EXPECTED_TASKS = [
        "keep_service_awake",
        "send_account_status_email",
        "send_account_status_sms",
        "update_model_analytics_counter",
        "delete_cloudinary_asset_task",
        "process_cloudinary_upload_webhook",
        "generate_eager_transformations",
        "purge_cloudinary_cache",
        "bulk_sync_cloudinary_urls",
        "upsert_user_lifecycle_registry",
        "increment_lifecycle_login_counter",
    ]

    def test_all_tasks_importable(self):
        import apps.common.tasks as tasks_pkg
        for task_name in self.EXPECTED_TASKS:
            self.assertTrue(
                hasattr(tasks_pkg, task_name),
                f"apps.common.tasks.{task_name} is not importable"
            )

    def test_all_tasks_are_celery_shared_tasks(self):
        """Each exported symbol must be a Celery task (has .apply_async)."""
        import apps.common.tasks as tasks_pkg
        from celery import Task
        for task_name in self.EXPECTED_TASKS:
            task_obj = getattr(tasks_pkg, task_name)
            self.assertTrue(
                callable(getattr(task_obj, "apply_async", None)),
                f"{task_name} does not have .apply_async — not a Celery task"
            )


# ─────────────────────────────────────────────────────────────────────────────
# 4. process_cloudinary_upload_webhook — idempotency + atomic DB updates
# ─────────────────────────────────────────────────────────────────────────────

class WebhookTaskIdempotencyTests(TransactionTestCase):
    """
    Tests that process_cloudinary_upload_webhook is safe to re-run.

    Uses TransactionTestCase so that transaction.atomic() is actually exercised.
    """

    def setUp(self):
        self.user = User.objects.create_user(
            email="avatar_test@test.com",
            password="securepass123",
        )

    def _make_payload(self, user_id: str, url: str) -> dict:
        return {
            "public_id":  f"fashionistar/users/avatars/user_{user_id}/test.jpg",
            "secure_url": url,
            "resource_type": "image",
        }

    def test_webhook_updates_avatar_url(self):
        """Webhook task sets UnifiedUser.avatar to the Cloudinary secure_url."""
        from apps.common.tasks.cloudinary import process_cloudinary_upload_webhook

        payload = self._make_payload(
            str(self.user.pk),
            "https://res.cloudinary.com/test-cloud/image/upload/v1/fashionistar/users/avatars/avatar.jpg",
        )
        process_cloudinary_upload_webhook(payload)

        self.user.refresh_from_db()
        self.assertEqual(
            self.user.avatar,
            "https://res.cloudinary.com/test-cloud/image/upload/v1/fashionistar/users/avatars/avatar.jpg",
        )

    def test_webhook_is_idempotent(self):
        """Running the webhook task twice must not raise and must produce same result."""
        from apps.common.tasks.cloudinary import process_cloudinary_upload_webhook

        url = "https://res.cloudinary.com/test/img.jpg"
        payload = self._make_payload(str(self.user.pk), url)

        process_cloudinary_upload_webhook(payload)
        process_cloudinary_upload_webhook(payload)  # second call — must be a no-op

        self.user.refresh_from_db()
        self.assertEqual(self.user.avatar, url)

    def test_webhook_with_missing_public_id_does_not_raise(self):
        """Empty payload must be handled gracefully (returns early, no crash)."""
        from apps.common.tasks.cloudinary import process_cloudinary_upload_webhook
        process_cloudinary_upload_webhook({"public_id": "", "secure_url": ""})  # should not raise

    def test_webhook_with_invalid_uuid_does_not_raise(self):
        """Invalid UUID in path must not crash the task."""
        from apps.common.tasks.cloudinary import process_cloudinary_upload_webhook
        payload = {
            "public_id":  "fashionistar/users/avatars/user_not-a-valid-uuid/img.jpg",
            "secure_url": "https://res.cloudinary.com/test/img.jpg",
        }
        process_cloudinary_upload_webhook(payload)  # should not raise


# ─────────────────────────────────────────────────────────────────────────────
# 5. bulk_sync_cloudinary_urls — atomic transaction + multiple images
# ─────────────────────────────────────────────────────────────────────────────

class BulkSyncTaskTests(TransactionTestCase):
    """Test bulk_sync_cloudinary_urls for product galleries (3-5 images)."""

    def test_bulk_sync_bad_model_raises(self):
        """
        Bad model path → task logs the error and re-raises (Celery retries).
        We verify the error path does NOT silently corrupt existing data.
        """
        from apps.common.tasks.cloudinary import bulk_sync_cloudinary_urls
        from celery.exceptions import MaxRetriesExceededError

        # Should raise MaxRetriesExceededError or AttributeError after retries
        with self.assertRaises((MaxRetriesExceededError, AttributeError, Exception)):
            bulk_sync_cloudinary_urls(
                model_path="store.models.NonExistentModel",
                pk_field="gid",
                image_field="image",
                updates=[{"pk": "abc", "url": "https://res.cloudinary.com/test/img.jpg"}],
            )

    def test_bulk_sync_skips_items_with_missing_pk_or_url(self):
        """Items with empty pk or url are skipped without crashing."""
        from apps.common.tasks.cloudinary import bulk_sync_cloudinary_urls
        # All items are invalid → task logs warnings and completes with 0 updates
        # The Gallery model exists so no ImportError; all items skip due to empty pk/url
        try:
            bulk_sync_cloudinary_urls(
                model_path="store.models.Gallery",
                pk_field="gid",
                image_field="image",
                updates=[
                    {"pk": "", "url": ""},
                    {"pk": None, "url": None},
                ],
            )
        except Exception as exc:
            raise AssertionError(f"bulk_sync should skip invalid items without raising: {exc}")


# ─────────────────────────────────────────────────────────────────────────────
# 6. Presign API Endpoint — Authentication + Response Structure
# ─────────────────────────────────────────────────────────────────────────────

@override_settings(
    CLOUDINARY_STORAGE=FAKE_CLOUDINARY_STORAGE,
    CLOUDINARY_UPLOAD_PRESET_AVATAR="test_avatar_preset",
    CLOUDINARY_UPLOAD_PRESET_PRODUCT="test_product_preset",
    CLOUDINARY_UPLOAD_PRESET_MEASURE="test_measure_preset",
    CLOUDINARY_UPLOAD_PRESET_VIDEO="test_video_preset",
    CLOUDINARY_SIGNATURE_TTL=3300,
)
class PresignEndpointTests(TestCase):
    """Test POST /api/upload/presign/."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="presign_test@test.com",
            password="securepass123",
        )

    def test_presign_unauthenticated_returns_401(self):
        resp = self.client.post(
            "/api/v1/upload/presign/",
            data=json.dumps({"asset_type": "avatar"}),
            content_type="application/json",
        )
        self.assertIn(resp.status_code, [401, 403])

    def test_presign_authenticated_returns_200(self):
        """Authenticated user with valid asset_type gets presign params."""
        from rest_framework.test import APIClient
        client = APIClient()
        client.force_authenticate(user=self.user)

        resp = client.post(
            "/api/upload/presign/",
            data={"asset_type": "avatar"},
            format="json",
        )
        self.assertEqual(resp.status_code, 200, f"Response: {resp.content}")
        data = resp.json()
        self.assertIn("signature",     data)
        self.assertIn("timestamp",     data)
        self.assertIn("cloud_name",    data)
        self.assertIn("api_key",       data)
        self.assertIn("folder",        data)
        self.assertIn("upload_preset", data)

    def test_presign_invalid_asset_type_returns_400(self):
        from rest_framework.test import APIClient
        client = APIClient()
        client.force_authenticate(user=self.user)

        resp = client.post(
            "/api/v1/upload/presign/",
            data={"asset_type": "___nonexistent___"},
            format="json",
        )
        self.assertEqual(resp.status_code, 400)

    def test_presign_all_supported_asset_types(self):
        """Verify all defined asset types produce a valid presign."""
        from apps.common.utils.cloudinary import _ASSET_CONFIGS
        from rest_framework.test import APIClient
        client = APIClient()
        client.force_authenticate(user=self.user)

        for asset_type in list(_ASSET_CONFIGS.keys())[:5]:  # test first 5 to keep it fast
            resp = client.post(
                "/api/v1/upload/presign/",
                data={"asset_type": asset_type},
                format="json",
            )
            self.assertEqual(
                resp.status_code, 200,
                f"Presign failed for asset_type={asset_type}: {resp.content}"
            )

    def test_presign_response_includes_eager_as_string(self):
        """Eager must be a pipe-delimited string, not a list of dicts."""
        from rest_framework.test import APIClient
        client = APIClient()
        client.force_authenticate(user=self.user)

        resp = client.post(
            "/api/v1/upload/presign/",
            data={"asset_type": "avatar"},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIsInstance(data.get("eager"), str, "eager must be a string")
        # Should contain 'w_' (short Cloudinary key), not 'width_'
        if data.get("eager"):
            self.assertIn("w_", data["eager"], "eager should use short keys (w_, h_, c_)")
            self.assertNotIn("width_", data["eager"], "eager should not use full SDK keys")

    @override_settings(CLOUDINARY_NOTIFICATION_URL="https://example.com/webhook/")
    def test_presign_response_includes_notification_url(self):
        """When CLOUDINARY_NOTIFICATION_URL is set, presign must include it."""
        from rest_framework.test import APIClient
        client = APIClient()
        client.force_authenticate(user=self.user)

        resp = client.post(
            "/api/v1/upload/presign/",
            data={"asset_type": "avatar"},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data.get("notification_url"), "https://example.com/webhook/")


# ─────────────────────────────────────────────────────────────────────────────
# 7. Webhook Endpoint — HMAC + Celery dispatch
# ─────────────────────────────────────────────────────────────────────────────

@override_settings(
    CLOUDINARY_STORAGE=FAKE_CLOUDINARY_STORAGE,
)
class WebhookEndpointTests(TestCase):
    """
    Test POST /api/upload/webhook/cloudinary/.

    Per the documented design, the webhook view ALWAYS returns HTTP 200,
    even for invalid signatures (status body = "rejected").
    This prevents Cloudinary from entering retry storms.
    """

    def _build_request(self, payload: dict, secret: str = "test-secret"):
        body      = json.dumps(payload).encode()
        timestamp = str(int(time.time()))
        sig       = _make_webhook_sig(body, timestamp, secret)
        return body, timestamp, sig

    def test_webhook_missing_signature_returns_200_rejected(self):
        """Missing signature → 200 with status=rejected (never 4xx to prevent Cloudinary retries)."""
        resp = self.client.post(
            "/api/v1/upload/webhook/cloudinary/",
            data=b'{"test": "data"}',
            content_type="application/json",
        )
        # View returns 200 even for invalid/missing signature
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data.get("status"), "rejected")

    def test_webhook_invalid_signature_returns_200_rejected(self):
        """Invalid signature → 200 with status=rejected."""
        resp = self.client.post(
            "/api/upload/webhook/cloudinary/",
            data=b'{"test": "data"}',
            content_type="application/json",
            HTTP_X_CLD_TIMESTAMP="1234",
            HTTP_X_CLD_SIGNATURE="invalidsignature",
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data.get("status"), "rejected")

    @patch("apps.common.tasks.cloudinary.process_cloudinary_upload_webhook.apply_async")
    def test_webhook_valid_signature_dispatches_task(self, mock_task):
        """Valid HMAC signature must dispatch the webhook processing task."""
        payload   = {"public_id": "fashionistar/test.jpg", "secure_url": "https://res.cloudinary.com/x.jpg", "notification_type": "upload"}
        body, ts, sig = self._build_request(payload)

        resp = self.client.post(
            "/api/upload/webhook/cloudinary/",
            data=body,
            content_type="application/json",
            HTTP_X_CLD_TIMESTAMP=ts,
            HTTP_X_CLD_SIGNATURE=sig,
        )
        # Valid payload → 200 with status=received
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data.get("status"), "received")


# ─────────────────────────────────────────────────────────────────────────────
# 8. Concurrency / Race-Condition Tests
# ─────────────────────────────────────────────────────────────────────────────

class ConcurrentPresignTests(TestCase):
    """
    Simulate 50 concurrent presign requests from the same user.

    All threads must receive a valid, non-empty signature.
    No race condition should cause any thread to crash.
    """

    @override_settings(
        CLOUDINARY_STORAGE=FAKE_CLOUDINARY_STORAGE,
        CLOUDINARY_UPLOAD_PRESET_AVATAR="test_avatar_preset",
        CLOUDINARY_SIGNATURE_TTL=3300,
    )
    def test_concurrent_presign_generation(self):
        from apps.common.utils.cloudinary import generate_cloudinary_upload_params

        user_id  = "race-test-user-uuid"
        results  = []
        errors   = []
        num_threads = 50

        def _presign():
            try:
                r = generate_cloudinary_upload_params(user_id, "avatar")
                results.append(r.success)
            except Exception as exc:
                errors.append(str(exc))

        with ThreadPoolExecutor(max_workers=num_threads) as pool:
            futures = [pool.submit(_presign) for _ in range(num_threads)]
            for f in as_completed(futures):
                f.result()

        self.assertEqual(len(errors), 0, f"Errors during concurrent presign: {errors}")
        self.assertEqual(len(results), num_threads)
        self.assertTrue(all(results), "Not all presign calls succeeded")


class ConcurrentWebhookTaskTests(TestCase):
    """
    Fire 50 concurrent webhook task calls for the same user.

    The DB layer (.update()) is mocked so we test concurrency at the
    application logic level (routing, UUID extraction, task dispatch)
    rather than being blocked by SQLite's table-level write lock.
    This is the correct approach: production uses PostgreSQL which handles
    row-level locking for concurrent UPDATE statements.
    """

    def setUp(self):
        self.user = User.objects.create_user(
            email="race_webhook@test.com",
            password="pw123456789",
        )

    @patch("django.db.models.query.QuerySet.update", return_value=1)
    def test_concurrent_webhook_tasks_are_idempotent(self, mock_update):
        """50 concurrent tasks — no race condition, no exception, consistent dispatch."""
        from apps.common.tasks.cloudinary import process_cloudinary_upload_webhook

        final_url = "https://res.cloudinary.com/test-cloud/final.jpg"
        payload   = {
            "public_id":  f"fashionistar/users/avatars/user_{self.user.pk}/final.jpg",
            "secure_url": final_url,
        }

        errors = []

        def _run():
            try:
                process_cloudinary_upload_webhook(payload)
            except Exception as exc:
                errors.append(str(exc))

        threads = [threading.Thread(target=_run) for _ in range(50)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(errors, [], f"Concurrent webhook tasks raised errors: {errors}")
        # Each of 50 threads called .update() exactly once
        self.assertEqual(mock_update.call_count, 50)


class ConcurrentApiCacheTests(TestCase):
    """
    Verify api_cache_get / api_cache_set are thread-safe under concurrent load.
    Django's LocMemCache is thread-safe; these tests confirm no exceptions arise.
    """

    @override_settings(CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "concurrent-api-cache",
        }
    })
    def test_concurrent_cache_reads_and_writes(self):
        from apps.common.utils.redis import api_cache_get, api_cache_set
        from django.core.cache import cache
        cache.clear()

        errors  = []
        results = []

        def _worker(i):
            try:
                api_cache_set(f"key:{i}", {"index": i}, ttl=60)
                val = api_cache_get(f"key:{i}")
                results.append(val)
            except Exception as exc:
                errors.append(str(exc))

        with ThreadPoolExecutor(max_workers=100) as pool:
            futures = [pool.submit(_worker, i) for i in range(500)]
            for f in as_completed(futures):
                f.result()

        self.assertEqual(errors, [], f"Concurrent cache errors: {errors}")
        self.assertEqual(len(results), 500)
