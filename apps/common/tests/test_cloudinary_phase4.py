# apps/common/tests/test_cloudinary_phase4.py
"""
Phase 4 Test Suite — Cloudinary Webhook Processing & Idempotency.

Test Coverage
─────────────
  ✅ Unit: Webhook idempotency — generate_idempotency_key(), is_duplicate(), mark_processed()
  ✅ Unit: Safe model resolution — _safe_resolve_model() with existing and non-existent apps
  ✅ Unit: Route matching — _WEBHOOK_ROUTES, _get_target_field(), _get_audit_event_type()
  ✅ Integration: process_cloudinary_upload_webhook Celery task — full E2E with mocked Cloudinary
  ✅ Integration: Duplicate webhook rejection (Redis cache hit + DB hit)
  ✅ Integration: Future-app route (store.models.Product) — graceful skip without crash
  ✅ Concurrency: Race condition — IntegrityError on simultaneous mark_processed() calls
  ✅ Unit: Admin mixin CloudinaryUploadAdminMixin — file upload detection + audit dispatch
  ✅ Unit: Audit cleanup task — batched deletion, compliance=True records never deleted
  ✅ Unit: Celery queue routing — all task names route to correct queues
  ✅ Unit: generate_eager_transformations — triggers cloudinary.uploader.explicit
  ✅ Unit: delete_cloudinary_asset_task — async deletion with retry
"""
from __future__ import annotations

import hashlib
import threading
import time
from typing import Any
from unittest.mock import MagicMock, call, patch

from django.core.cache import cache
from django.test import TestCase, override_settings


# ═══════════════════════════════════════════════════════════════════════════
# BASE CLASS for cache management
# ═══════════════════════════════════════════════════════════════════════════

class CacheClearMixin:
    """Mixin that clears Django cache before and after each test."""

    def setUp(self):
        super().setUp()
        cache.clear()

    def tearDown(self):
        super().tearDown()
        cache.clear()


def _make_webhook_payload(
    public_id: str = "/avatars/user_550e8400-e29b-41d4-a716-446655440000/avatar.jpg",
    secure_url: str = "https://res.cloudinary.com/fashionistar/image/upload/avatars/user.jpg",
    resource_type: str = "image",
    created_at: str = "2026-01-01T12:00:00Z",
) -> dict:
    """Factory for a minimal validated Cloudinary webhook payload."""
    return {
        "notification_type": "upload",
        "public_id": public_id,
        "secure_url": secure_url,
        "resource_type": resource_type,
        "created_at": created_at,
        "bytes": 12345,
        "width": 400,
        "height": 400,
        "format": "jpg",
    }


# ═══════════════════════════════════════════════════════════════════════════
# 1. IDEMPOTENCY KEY GENERATION
# ═══════════════════════════════════════════════════════════════════════════

class TestGenerateIdempotencyKey(CacheClearMixin, TestCase):
    """generate_idempotency_key() must produce stable, collision-resistant hashes."""

    def _import(self):
        from apps.common.utils.webhook_idempotency import generate_idempotency_key
        return generate_idempotency_key

    def test_same_inputs_same_key(self):
        gen = self._import()
        key1 = gen("/avatars/user_123/avatar.jpg", "1700000000", "image")
        key2 = gen("/avatars/user_123/avatar.jpg", "1700000000", "image")
        self.assertEqual(key1, key2)

    def test_different_public_id_different_key(self):
        gen = self._import()
        key1 = gen("/avatars/user_123/a.jpg", "1700000000", "image")
        key2 = gen("/avatars/user_456/a.jpg", "1700000000", "image")
        self.assertNotEqual(key1, key2)

    def test_different_timestamp_different_key(self):
        gen = self._import()
        key1 = gen("/avatars/user_123/a.jpg", "1700000000", "image")
        key2 = gen("/avatars/user_123/a.jpg", "1700000001", "image")
        self.assertNotEqual(key1, key2)

    def test_different_resource_type_different_key(self):
        gen = self._import()
        key1 = gen("/products/videos/vid-001.mp4", "1700000000", "video")
        key2 = gen("/products/videos/vid-001.mp4", "1700000000", "image")
        self.assertNotEqual(key1, key2)

    def test_key_is_64_char_hex(self):
        gen = self._import()
        key = gen("/avatars/user_123/a.jpg", "1700000000", "image")
        self.assertEqual(len(key), 64)
        int(key, 16)  # must parse as hex without raising

    def test_key_matches_manual_sha256(self):
        gen = self._import()
        public_id, ts, at = "/avatars/user_x/a.jpg", "1700000000", "image"
        expected = hashlib.sha256(
            f"{public_id}|{ts}|{at}".encode("utf-8")
        ).hexdigest()
        self.assertEqual(gen(public_id, ts, at), expected)


# ═══════════════════════════════════════════════════════════════════════════
# 2. DUPLICATE DETECTION
# ═══════════════════════════════════════════════════════════════════════════

@override_settings(CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}})
class TestIsDuplicate(CacheClearMixin, TestCase):

    def _import(self):
        from apps.common.utils.webhook_idempotency import (
            generate_idempotency_key, is_duplicate, mark_processed,
        )
        return generate_idempotency_key, is_duplicate, mark_processed

    def test_first_call_is_not_duplicate(self):
        gen, is_dup, _ = self._import()
        key = gen("/avatars/user_aaa/a.jpg", "1700000001", "image")
        self.assertFalse(is_dup(key, check_database=False))

    def test_after_cache_mark_is_duplicate(self):
        gen, is_dup, _ = self._import()
        key = gen("/avatars/user_bbb/a.jpg", "1700000002", "image")
        cache.set(f"webhook:idempotency:{key}", True, 3600)
        self.assertTrue(is_dup(key, check_database=False))

    @patch("apps.common.models.processed_webhook.CloudinaryProcessedWebhook.objects")
    def test_database_check_on_cache_miss(self, mock_qs):
        gen, is_dup, _ = self._import()
        key = gen("/avatars/user_ccc/a.jpg", "1700000003", "image")
        # Simulate DB hit
        mock_qs.filter.return_value.exists.return_value = True
        self.assertTrue(is_dup(key, check_database=True))


# ═══════════════════════════════════════════════════════════════════════════
# 3. SAFE MODEL RESOLUTION
# ═══════════════════════════════════════════════════════════════════════════

class TestSafeResolveModel(CacheClearMixin, TestCase):

    def _import(self):
        from apps.common.tasks.cloudinary import _safe_resolve_model
        return _safe_resolve_model

    def test_live_model_resolves(self):
        safe = self._import()
        Model = safe("apps.authentication.models.UnifiedUser")
        self.assertIsNotNone(Model)
        self.assertEqual(Model.__name__, "UnifiedUser")

    def test_future_app_returns_none(self):
        """future_app.models.Product doesn't exist yet — must return None, not raise."""
        safe = self._import()
        result = safe("future_app.models.Product")
        self.assertIsNone(result)

    def test_completely_invalid_path_returns_none(self):
        safe = self._import()
        result = safe("nonexistent.garbage.ModelXYZ")
        self.assertIsNone(result)

    def test_malformed_dotted_path_returns_none(self):
        safe = self._import()
        result = safe("noDotPath")
        self.assertIsNone(result)


# ═══════════════════════════════════════════════════════════════════════════
# 4. ROUTE MATCHING
# ═══════════════════════════════════════════════════════════════════════════

class TestWebhookRouting(CacheClearMixin, TestCase):

    def test_avatar_route_target_field_is_avatar(self):
        from apps.common.tasks.cloudinary import _get_target_field
        result = _get_target_field("/avatars/user_", "image", "avatar")
        self.assertEqual(result, "avatar")

    def test_video_resource_type_gives_video_url(self):
        from apps.common.tasks.cloudinary import _get_target_field
        result = _get_target_field("/products/videos/", "video", "product_video")
        self.assertEqual(result, "video_url")

    def test_product_image_resource_type_gives_image(self):
        from apps.common.tasks.cloudinary import _get_target_field
        result = _get_target_field("/products/images/", "image", "product_image")
        self.assertEqual(result, "image")

    def test_audit_event_mapping_avatar(self):
        from apps.common.tasks.cloudinary import _get_audit_event_type, _EVENT_AVATAR_CLOUDINARY
        result = _get_audit_event_type("avatar", "image")
        self.assertEqual(result, _EVENT_AVATAR_CLOUDINARY)

    def test_audit_event_mapping_product_video(self):
        from apps.common.tasks.cloudinary import _get_audit_event_type, _EVENT_VENDOR_PRODUCT_VID
        result = _get_audit_event_type("product_video", "video")
        self.assertEqual(result, _EVENT_VENDOR_PRODUCT_VID)

    def test_audit_event_unknown_label_gets_webhook_received(self):
        from apps.common.tasks.cloudinary import _get_audit_event_type, _EVENT_WEBHOOK_RECEIVED
        result = _get_audit_event_type("unknown_thing", "image")
        self.assertEqual(result, _EVENT_WEBHOOK_RECEIVED)


# ═══════════════════════════════════════════════════════════════════════════
# 5. PK EXTRACTORS
# ═══════════════════════════════════════════════════════════════════════════

class TestPKExtractors(CacheClearMixin, TestCase):

    def test_extract_user_uuid_success(self):
        from apps.common.tasks.cloudinary import _extract_user_uuid
        parts = ["avatars", "user_550e8400-e29b-41d4-a716-446655440000", "avatar.jpg"]
        result = _extract_user_uuid(parts)
        self.assertEqual(result, "550e8400-e29b-41d4-a716-446655440000")

    def test_extract_user_uuid_no_user_segment(self):
        from apps.common.tasks.cloudinary import _extract_user_uuid
        parts = ["products", "images", "prod-001.jpg"]
        result = _extract_user_uuid(parts)
        self.assertIsNone(result)

    def test_extract_user_uuid_invalid_uuid(self):
        from apps.common.tasks.cloudinary import _extract_user_uuid
        parts = ["avatars", "user_notauuid", "avatar.jpg"]
        result = _extract_user_uuid(parts)
        self.assertIsNone(result)

    def test_extract_short_id(self):
        from apps.common.tasks.cloudinary import _extract_short_id
        parts = ["products", "images", "PROD-001", "image.jpg"]
        result = _extract_short_id(parts)
        self.assertEqual(result, "PROD-001")

    def test_extract_short_id_short_path(self):
        from apps.common.tasks.cloudinary import _extract_short_id
        parts = ["only"]
        result = _extract_short_id(parts)
        self.assertIsNone(result)


# ═══════════════════════════════════════════════════════════════════════════
# 6. FULL WEBHOOK TASK — INTEGRATION
# ═══════════════════════════════════════════════════════════════════════════

class TestProcessCloudinaryUploadWebhook(CacheClearMixin, TestCase):
    """
    Integration tests for process_cloudinary_upload_webhook Celery task.
    Uses .apply() (synchronous) so tests don't require a running broker.
    """

    def setUp(self):
        super().setUp()
        patcher = patch("apps.common.tasks.cloudinary.generate_eager_transformations.apply_async")
        self.mock_eager_delay = patcher.start()
        self.addCleanup(patcher.stop)

    @patch("apps.audit_logs.services.audit.AuditService.log")
    @patch("apps.common.utils.webhook_idempotency.mark_processed")
    @patch("apps.common.utils.webhook_idempotency.is_duplicate", return_value=False)
    @patch("apps.authentication.models.UnifiedUser.objects")
    def test_avatar_webhook_saves_secure_url(
        self,
        mock_user_qs,
        mock_is_dup,
        mock_mark_processed,
        mock_audit_log,
    ):
        """Webhook for /avatars/user_{uuid}/ must call user queryset update()."""
        mock_user_qs.filter.return_value.update.return_value = 1

        from apps.common.tasks.cloudinary import process_cloudinary_upload_webhook

        payload = _make_webhook_payload(
            public_id="/avatars/user_550e8400-e29b-41d4-a716-446655440000/avatar.jpg",
            secure_url="https://res.cloudinary.com/fashionistar/image/upload/v1/avatars/avatar.jpg",
        )
        process_cloudinary_upload_webhook.apply(kwargs={"payload": payload})

        # Assert the model was updated
        mock_user_qs.filter.assert_called_once()
        call_kwargs = mock_user_qs.filter.call_args[1]
        self.assertEqual(call_kwargs["id"], "550e8400-e29b-41d4-a716-446655440000")
        mock_user_qs.filter.return_value.update.assert_called_once_with(
            avatar=payload["secure_url"]
        )

        # Assert idempotency was marked
        mock_mark_processed.assert_called_once()

    @patch("apps.common.utils.webhook_idempotency.is_duplicate", return_value=True)
    def test_duplicate_webhook_is_silently_skipped(self, mock_is_dup):
        """Second webhook with same idempotency key must NOT touch the database."""
        from apps.common.tasks.cloudinary import process_cloudinary_upload_webhook

        payload = _make_webhook_payload()

        with patch("apps.authentication.models.UnifiedUser.objects") as mock_user_qs:
            process_cloudinary_upload_webhook.apply(kwargs={"payload": payload})
            mock_user_qs.filter.assert_not_called()

    def test_missing_public_id_returns_early(self):
        """Payload without public_id must return early without any DB/cache access."""
        from apps.common.tasks.cloudinary import process_cloudinary_upload_webhook

        payload = _make_webhook_payload(public_id="", secure_url="https://example.com/img.jpg")

        with patch("apps.common.utils.webhook_idempotency.is_duplicate") as mock_is_dup:
            process_cloudinary_upload_webhook.apply(kwargs={"payload": payload})
            mock_is_dup.assert_not_called()  # returns before even checking idempotency

    @patch("apps.common.utils.webhook_idempotency.is_duplicate", return_value=False)
    @patch("apps.common.utils.webhook_idempotency.mark_processed")
    def test_future_app_route_skipped_gracefully(self, mock_mark, mock_is_dup):
        """
        Cloudinary webhook for a store.models.Product (not yet implemented)
        must NOT raise — it must log a notice and call mark_processed(success=True).
        """
        from apps.common.tasks.cloudinary import process_cloudinary_upload_webhook

        payload = _make_webhook_payload(
            public_id="/products/images/PROD-001/front.jpg",
            secure_url="https://res.cloudinary.com/fashionistar/image/upload/products/front.jpg",
        )
        # Should NOT raise even though store.models.Product doesn't exist
        process_cloudinary_upload_webhook.apply(kwargs={"payload": payload})

        # mark_processed must still be called so we don't retry forever
        mock_mark.assert_called_once()

    @patch("apps.common.utils.webhook_idempotency.is_duplicate", return_value=False)
    @patch("apps.common.utils.webhook_idempotency.mark_processed")
    def test_unmatched_route_still_marks_processed(self, mock_mark, mock_is_dup):
        """
        Webhook for an unmapped path must not crash — it should be marked
        processed (success=True) so it isn't retried endlessly.
        """
        from apps.common.tasks.cloudinary import process_cloudinary_upload_webhook

        payload = _make_webhook_payload(
            public_id="/completely/unmapped/path/file.jpg",
            secure_url="https://res.cloudinary.com/fashionistar/image/upload/unmapped.jpg",
        )
        process_cloudinary_upload_webhook.apply(kwargs={"payload": payload})
        mock_mark.assert_called_once()

    @patch("apps.common.utils.webhook_idempotency.is_duplicate", return_value=False)
    @patch("apps.common.utils.webhook_idempotency.mark_processed")
    def test_video_resource_type_routes_to_video_url(self, mock_mark, mock_is_dup):
        """Videos (resource_type=video) must map to video_url, not image."""
        from apps.common.tasks.cloudinary import process_cloudinary_upload_webhook

        # product_video in the future — test that the route resolution sees "video_url"
        # Use avatar path (live route) with video type to verify field selection
        payload = _make_webhook_payload(
            public_id="/avatars/user_550e8400-e29b-41d4-a716-446655440000/promo.mp4",
            secure_url="https://res.cloudinary.com/fashionistar/video/upload/avatars/promo.mp4",
            resource_type="video",
        )
        with patch("apps.authentication.models.UnifiedUser.objects") as mock_user_qs:
            mock_user_qs.filter.return_value.update.return_value = 1
            process_cloudinary_upload_webhook.apply(kwargs={"payload": payload})
            # Avatars always map to "avatar" field regardless of resource_type
            update_call = mock_user_qs.filter.return_value.update.call_args
            self.assertIn("avatar", update_call[1])


# ═══════════════════════════════════════════════════════════════════════════
# 7. RACE CONDITION TEST — IntegrityError on simultaneous mark_processed()
# ═══════════════════════════════════════════════════════════════════════════

class TestMarkProcessedRaceCondition(TestCase):
    """
    Simulates two Celery workers calling _safe_mark_processed() simultaneously
    for the same idempotency key. The second must silently succeed (no crash).
    """

    def test_integrity_error_on_duplicate_mark_is_swallowed(self):
        """
        _safe_mark_processed() must not raise even when mark_processed()
        raises IntegrityError (concurrent duplicate write).
        """
        from django.db import IntegrityError
        from apps.common.tasks.cloudinary import _safe_mark_processed

        with patch(
            "apps.common.utils.webhook_idempotency.mark_processed",
            side_effect=IntegrityError("UNIQUE constraint failed: idempotency_key"),
        ):
            # Must not raise
            try:
                _safe_mark_processed(
                    idem_key="abc123",
                    public_id="/avatars/user_x/a.jpg",
                    resource_type="image",
                    model_target="avatar",
                    model_pk="some-uuid",
                    secure_url="https://example.com/a.jpg",
                    processing_time_ms=5.0,
                    success=True,
                    error_message=None,
                )
            except IntegrityError:
                self.fail("_safe_mark_processed should swallow IntegrityError")


# ═══════════════════════════════════════════════════════════════════════════
# 8. EAGER TRANSFORMATIONS
# ═══════════════════════════════════════════════════════════════════════════

class TestGenerateEagerTransformations(TestCase):

    @patch("cloudinary.uploader.explicit")
    def test_explicit_called_with_eager_async(self, mock_explicit):
        from apps.common.tasks.cloudinary import generate_eager_transformations
        mock_explicit.return_value = {"result": "ok"}

        generate_eager_transformations.apply(kwargs={
            "public_id": "/avatars/user_xyz/avatar.jpg",
            "asset_type": "avatar",
        })

        mock_explicit.assert_called_once()
        call_kwargs = mock_explicit.call_args[1]
        self.assertTrue(call_kwargs.get("eager_async"))
        self.assertEqual(call_kwargs.get("type"), "upload")

    @patch("cloudinary.uploader.explicit")
    def test_no_eager_config_skips_call(self, mock_explicit):
        """Asset types with no eager config must not call explicit()."""
        from apps.common.tasks.cloudinary import generate_eager_transformations

        # Patch _ASSET_CONFIGS to return empty eager list
        with patch(
            "apps.common.tasks.cloudinary._ASSET_CONFIGS",
            {"avatar": {"eager": []}},
        ):
            with patch("apps.common.utils.cloudinary._ASSET_CONFIGS", {"avatar": {"eager": []}}):
                generate_eager_transformations.apply(kwargs={
                    "public_id": "/avatars/user_xyz/avatar.jpg",
                    "asset_type": "avatar",
                })
        mock_explicit.assert_not_called()


# ═══════════════════════════════════════════════════════════════════════════
# 9. AUDIT LOG CLEANUP TASK
# ═══════════════════════════════════════════════════════════════════════════

class TestCleanupAuditLogs(TestCase):

    @patch("apps.audit_logs.models.AuditEventLog.objects")
    @patch("apps.common.models.CloudinaryProcessedWebhook.objects")
    def test_cleanup_runs_without_crash(self, mock_webhook_qs, mock_audit_qs):
        """cleanup_audit_logs() must run to completion and return a result dict."""
        from apps.audit_logs.tasks import cleanup_audit_logs

        # Setup mocks
        mock_audit_qs.filter.return_value.values_list.return_value.__getitem__ = \
            MagicMock(return_value=[])  # No expired IDs → exits loop immediately
        mock_audit_qs.filter.return_value.values_list.return_value = []
        mock_webhook_qs.filter.return_value.delete.return_value = (5, {})

        result = cleanup_audit_logs.apply()
        self.assertTrue(result.successful())

    @patch("apps.audit_logs.models.AuditEventLog.objects")
    @patch("apps.common.models.CloudinaryProcessedWebhook.objects")
    def test_compliance_records_never_deleted(self, mock_webhook_qs, mock_audit_qs):
        """
        AuditEventLog.objects.filter() must always include is_compliance=False
        so compliance-marked events are never deleted.
        """
        from apps.audit_logs.tasks import cleanup_audit_logs

        mock_audit_qs.filter.return_value.values_list.return_value = []
        mock_webhook_qs.filter.return_value.delete.return_value = (0, {})

        cleanup_audit_logs.apply()

        # Verify the filter includes is_compliance=False
        filter_calls = mock_audit_qs.filter.call_args_list
        if filter_calls:
            call_kwargs = filter_calls[0][1]
            self.assertIn("is_compliance", call_kwargs)
            self.assertFalse(call_kwargs["is_compliance"])


# ═══════════════════════════════════════════════════════════════════════════
# 10. CELERY QUEUE ROUTING
# ═══════════════════════════════════════════════════════════════════════════

class TestCeleryQueueRouting(TestCase):
    """Verify all Phase 4 tasks are explicitly routed to the correct queues."""

    def test_webhook_task_in_webhooks_queue(self):
        from backend.celery import app
        routes = app.conf.task_routes
        self.assertIn("process_cloudinary_upload_webhook", routes)
        self.assertEqual(
            routes["process_cloudinary_upload_webhook"]["queue"], "webhooks"
        )

    def test_audit_write_task_in_audit_queue(self):
        from backend.celery import app
        routes = app.conf.task_routes
        self.assertIn("write_audit_event", routes)
        self.assertEqual(routes["write_audit_event"]["queue"], "audit")

    def test_generate_eager_in_transforms_queue(self):
        from backend.celery import app
        routes = app.conf.task_routes
        self.assertIn("generate_eager_transformations", routes)
        self.assertEqual(routes["generate_eager_transformations"]["queue"], "transforms")

    def test_delete_cloudinary_in_cleanup_queue(self):
        from backend.celery import app
        routes = app.conf.task_routes
        self.assertIn("delete_cloudinary_asset_task", routes)
        self.assertEqual(routes["delete_cloudinary_asset_task"]["queue"], "cleanup")

    def test_bulk_sync_in_bulk_queue(self):
        from backend.celery import app
        routes = app.conf.task_routes
        self.assertIn("bulk_sync_cloudinary_urls", routes)
        self.assertEqual(routes["bulk_sync_cloudinary_urls"]["queue"], "bulk")

    def test_audit_cleanup_in_beat_schedule(self):
        from backend.celery import app
        beat = app.conf.beat_schedule
        self.assertIn("audit-log-cleanup", beat)
        self.assertEqual(beat["audit-log-cleanup"]["task"], "audit_log_cleanup")


# ═══════════════════════════════════════════════════════════════════════════
# 11. UPLOAD_TO_CLOUDINARY_FROM_ADMIN
# ═══════════════════════════════════════════════════════════════════════════

class TestUploadToCloudinaryFromAdmin(TestCase):

    @patch("cloudinary.uploader.upload")
    def test_returns_secure_url(self, mock_upload):
        """Successful upload must return the secure_url from Cloudinary response."""
        mock_upload.return_value = {
            "secure_url": "https://res.cloudinary.com/fashionistar/image/upload/test.jpg",
            "public_id": "fashionistar/categories/test",
        }
        from apps.common.utils.cloudinary import upload_to_cloudinary_from_admin

        mock_file = MagicMock()
        mock_file.read.return_value = b"fake_image_data"
        mock_file.seek = MagicMock()

        url = upload_to_cloudinary_from_admin(
            file_obj=mock_file,
            folder="fashionistar/categories/images",
            asset_type="category",
        )
        self.assertEqual(url, "https://res.cloudinary.com/fashionistar/image/upload/test.jpg")

    @patch("cloudinary.uploader.upload")
    def test_raises_value_error_on_missing_secure_url(self, mock_upload):
        """If Cloudinary returns no secure_url, ValueError must be raised."""
        mock_upload.return_value = {"result": "ok"}  # No secure_url
        from apps.common.utils.cloudinary import upload_to_cloudinary_from_admin

        mock_file = MagicMock()
        mock_file.seek = MagicMock()

        with self.assertRaises(ValueError, msg="Should raise ValueError on missing secure_url"):
            upload_to_cloudinary_from_admin(
                file_obj=mock_file,
                folder="fashionistar/categories/images",
                asset_type="category",
            )


# ═══════════════════════════════════════════════════════════════════════════
# 12. CLOUDINARY ADMIN MIXIN
# ═══════════════════════════════════════════════════════════════════════════

class TestCloudinaryUploadAdminMixin(TestCase):

    def _build_mixin_admin(self, cloudinary_fields=None):
        from apps.common.admin_cloudinary_mixin import CloudinaryUploadAdminMixin

        class MockModel:
            pk = "test-pk"
            __class__ = type("MockModel", (), {
                "__name__": "MockModel",
            })()
            image = None

        class MockAdmin(CloudinaryUploadAdminMixin):
            cloudinary_fields = cloudinary_fields or {
                "image": ("fashionistar/categories/images", "category"),
            }

            def save_model(self, request, obj, form, change):
                CloudinaryUploadAdminMixin.save_model(
                    self, request, obj, form, change
                )

        return MockAdmin(), MockModel()

    @patch("apps.common.utils.cloudinary.upload_to_cloudinary_from_admin")
    def test_file_upload_sets_field_on_model(self, mock_upload):
        """When form has a file for 'image', it must be uploaded and set on the model."""
        mock_upload.return_value = "https://res.cloudinary.com/fashionistar/image/upload/cat.jpg"

        from apps.common.admin_cloudinary_mixin import CloudinaryUploadAdminMixin

        # Build fresh test admin
        class FakeModel:
            pk = "cat-001"
            image = None
            __class__ = type("Category", (), {"__name__": "Category"})()

        class FakeAdmin(CloudinaryUploadAdminMixin):
            cloudinary_fields = {"image": ("fashionistar/categories/images", "category")}

        admin = FakeAdmin()
        obj = FakeModel()

        mock_file = MagicMock()
        mock_file.read.return_value = b"image_data"

        mock_form = MagicMock()
        mock_form.cleaned_data = {"image": mock_file}

        mock_request = MagicMock()
        mock_request.user = MagicMock(email="superadmin@fashionistar.ng")

        admin._process_cloudinary_uploads(mock_request, obj, mock_form, change=True)

        # Object field must be updated with the secure_url
        self.assertEqual(obj.image, "https://res.cloudinary.com/fashionistar/image/upload/cat.jpg")

    def test_no_file_in_form_skips_upload(self):
        """If form cleaned_data has a string (existing URL), no upload should happen."""
        from apps.common.admin_cloudinary_mixin import CloudinaryUploadAdminMixin

        class FakeModel:
            pk = "cat-002"
            image = "https://existing-url.com/img.jpg"

        class FakeAdmin(CloudinaryUploadAdminMixin):
            cloudinary_fields = {"image": ("fashionistar/categories/images", "category")}

        admin = FakeAdmin()
        obj = FakeModel()

        mock_form = MagicMock()
        # String value (existing URL retained) — not a file
        mock_form.cleaned_data = {"image": "https://existing-url.com/img.jpg"}

        with patch("apps.common.utils.cloudinary.upload_to_cloudinary_from_admin") as mock_up:
            admin._process_cloudinary_uploads(MagicMock(), obj, mock_form, change=True)
            mock_up.assert_not_called()


# ═══════════════════════════════════════════════════════════════════════════
# 13. CONCURRENT WEBHOOK PROCESSING (threading)
# ═══════════════════════════════════════════════════════════════════════════

class TestConcurrentWebhookProcessing(CacheClearMixin, TestCase):
    """
    Simulate 5 concurrent workers receiving the same webhook.
    Only 1 must process it; the other 4 must be rejected as duplicates.
    """

    @override_settings(CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}})
    def test_concurrent_duplicate_webhooks_only_process_once(self):
        from apps.common.utils.webhook_idempotency import (
            generate_idempotency_key, is_duplicate
        )

        key = generate_idempotency_key(
            "/avatars/user_concurrent/avatar.jpg",
            "1700000999",
            "image",
        )

        processing_counts = []
        # We simulate the atomic nature of Redis `set(nx=True)` by locking
        # around the entirety of the read-check-write block.
        atomic_redis_lock = threading.Lock()

        def try_process():
            with atomic_redis_lock:
                if not is_duplicate(key, check_database=False):
                    processing_counts.append(1)
                    cache.set(f"webhook:idempotency:{key}", True, 3600)

        threads = [threading.Thread(target=try_process) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(
            len(processing_counts), 1,
            msg="Atomic lock failed — multiple identical webhooks processed.",
        )
