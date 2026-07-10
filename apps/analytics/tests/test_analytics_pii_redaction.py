"""
Tests for PII redaction (Phase 7.7 verification).

Verifies that _redact_user_activity helper removes or masks
personally identifiable information from user activity records.
"""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

User = get_user_model()


@pytest.mark.django_db
class TestPIIRedaction:
    """Verify PII redaction is applied to user activity data."""

    def test_redact_function_exists(self):
        """_redact_user_activity helper is importable."""
        from apps.analytics.apis.async_.analytics_views import _redact_user_activity

        assert callable(_redact_user_activity)

    def test_redact_removes_email(self):
        """Email field is redacted from user activity."""
        from apps.analytics.apis.async_.analytics_views import _redact_user_activity

        user = User.objects.create_user(
            email="pii@test.com",
            password="testpass123",
        )
        from apps.analytics.models import UserActivity

        activity = UserActivity.objects.create(
            user=user,
            action="login",
            timestamp=timezone.now(),
            ip_address="192.168.1.100",
            user_agent="Mozilla/5.0",
        )

        redacted = _redact_user_activity(activity)

        # Email should not appear in redacted output
        assert "pii@test.com" not in str(redacted)
        assert "192.168.1.100" not in str(redacted)

    def test_redact_preserves_non_pii_fields(self):
        """Non-PII fields like action and timestamp are preserved."""
        from apps.analytics.apis.async_.analytics_views import _redact_user_activity
        from apps.analytics.models import UserActivity

        user = User.objects.create_user(
            email="preserve@test.com",
            password="testpass123",
        )
        activity = UserActivity.objects.create(
            user=user,
            action="page_view",
            timestamp=timezone.now(),
        )

        redacted = _redact_user_activity(activity)

        assert redacted.get("action") == "page_view"
        assert "timestamp" in redacted

    def test_redact_handles_missing_fields_gracefully(self):
        """Redaction handles records with missing optional fields."""
        from apps.analytics.apis.async_.analytics_views import _redact_user_activity
        from apps.analytics.models import UserActivity

        user = User.objects.create_user(
            email="missing@test.com",
            password="testpass123",
        )
        activity = UserActivity.objects.create(
            user=user,
            action="click",
            timestamp=timezone.now(),
        )

        # Should not raise
        redacted = _redact_user_activity(activity)
        assert redacted is not None
        assert isinstance(redacted, dict)

    def test_redact_user_id_is_not_email(self):
        """Redacted output uses user_id (integer) not email string."""
        from apps.analytics.apis.async_.analytics_views import _redact_user_activity
        from apps.analytics.models import UserActivity

        user = User.objects.create_user(
            email="userid@test.com",
            password="testpass123",
        )
        activity = UserActivity.objects.create(
            user=user,
            action="login",
            timestamp=timezone.now(),
        )

        redacted = _redact_user_activity(activity)

        # Should have user_id as integer, not the email
        if "user" in redacted:
            assert redacted["user"] != "userid@test.com"
        if "user_id" in redacted:
            assert isinstance(redacted["user_id"], int)
