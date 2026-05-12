"""
Phase 4 Database Transaction & Atomic Block Regression Tests
"""
from django.test import TestCase, override_settings
from django.db import IntegrityError, transaction
from unittest.mock import patch

from apps.authentication.models import UnifiedUser
from apps.common.tasks.cloudinary import process_cloudinary_upload_webhook

class TestTransactionAtomicRollback(TestCase):
    """
    Verifies that webhook processing operates inside a strict transaction.atomic block.
    If an error occurs mid-way (e.g., AuditEventLog creation fails, or model update fails),
    all previous changes in the transaction MUST be rolled back.
    """

    def setUp(self):
        # Create a real user in the DB
        self.user = UnifiedUser.objects.create(
            email="testatomic@fashionistar.ng",
            password="test",
            avatar="https://old.jpg"
        )
        self.public_id = f"/avatars/user_{self.user.id}/avatar.jpg"
        self.secure_url = "https://new-url.jpg"

    @override_settings(CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}})
    def test_atomic_rollback_on_audit_failure(self):
        """
        If the model updates successfully, but the audit log write fails,
        the model update MUST be rolled back.
        """
        # We patch the inner part of process_cloudinary_upload_webhook.
        # It updates UnifiedUser, then logs audit, then marks processed.
        # We'll make AuditService.log raise ValueError to crash the transaction.
        
        from apps.audit_logs.services.audit import AuditService
        
        payload = {
            "notification_type": "upload",
            "public_id": self.public_id,
            "secure_url": self.secure_url,
            "resource_type": "image",
            "created_at": "2026-01-01T12:00:00Z",
            "bytes": 12345,
            "width": 100,
            "height": 100,
            "format": "jpg",
        }

        with patch.object(AuditService, "log", side_effect=ValueError("Simulated DB Crash")):
            # It should raise the ValueError out
            with self.assertRaises(ValueError):
                process_cloudinary_upload_webhook.apply(kwargs={"payload": payload})

        # FETCH FRESH FROM DB — atomic block should have rolled back
        self.user.refresh_from_db()

        # MUST EQUAL OLD VALUE -> proving full transaction rollback
        self.assertEqual(self.user.avatar, "https://old.jpg")

        # Idempotency must NOT be marked processed (since it was inside atomic block too)
        from apps.common.utils.webhook_idempotency import is_duplicate, generate_idempotency_key
        key = generate_idempotency_key(self.public_id, "unix_ts", "image")
        # Ensure it's not marked processed in DB
        self.assertFalse(is_duplicate(key, check_database=True))
