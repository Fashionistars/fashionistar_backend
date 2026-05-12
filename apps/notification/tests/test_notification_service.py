# apps/notification/tests/test_notification_service.py
"""
Unit tests for the Notification domain service layer.

Coverage:
  - create_notification: happy path, opt-out suppression, mandatory bypass
  - mark_as_read / mark_all_as_read
  - send_order_notification
  - bulk_notify
  - NotificationPreference enforcement
"""

import pytest
from django.contrib.auth import get_user_model
from unittest.mock import patch

from apps.notification.models import (
    Notification,
    NotificationChannel,
    NotificationType,
    NotificationPreference,
)
from apps.notification.services import (
    create_notification,
    mark_as_read,
    mark_all_as_read,
    send_order_notification,
    bulk_notify,
)

User = get_user_model()
pytestmark = pytest.mark.django_db


# ─────────────────────────────────────────────────────────────────────────────
# FIXTURES
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def client_user(db):
    return User.objects.create_user(
        email="client@test.com",
        password="Pass1234!",
    )


@pytest.fixture
def vendor_user(db):
    return User.objects.create_user(
        email="vendor@test.com",
        password="Pass1234!",
    )


# ─────────────────────────────────────────────────────────────────────────────
# TESTS: create_notification
# ─────────────────────────────────────────────────────────────────────────────

class TestCreateNotification:
    def test_creates_notification_happy_path(self, client_user):
        with patch("apps.notification.services.notification_service.dispatch_notification_task") as mock_task:
            mock_task.delay = lambda *a: None
            notif = create_notification(
                recipient=client_user,
                notification_type=NotificationType.ORDER_PLACED,
                title="Order Placed",
                body="Your order has been placed.",
                channel=NotificationChannel.IN_APP,
            )
        assert notif is not None
        assert notif.recipient == client_user
        assert notif.notification_type == NotificationType.ORDER_PLACED
        assert not notif.is_read

    def test_suppressed_by_opt_out_preference(self, client_user):
        # User opts out of PROMO notifications
        NotificationPreference.objects.create(
            user=client_user,
            notification_type=NotificationType.PROMO,
            channel=NotificationChannel.IN_APP,
            enabled=False,
        )
        with patch("apps.notification.services.notification_service.dispatch_notification_task") as mock_task:
            mock_task.delay = lambda *a: None
            result = create_notification(
                recipient=client_user,
                notification_type=NotificationType.PROMO,
                title="Sale!",
                body="Big sale.",
                channel=NotificationChannel.IN_APP,
            )
        assert result is None
        assert Notification.objects.filter(
            recipient=client_user,
            notification_type=NotificationType.PROMO,
        ).count() == 0

    def test_mandatory_type_bypasses_opt_out(self, client_user):
        """ORDER_PLACED cannot be suppressed by preference."""
        NotificationPreference.objects.create(
            user=client_user,
            notification_type=NotificationType.ORDER_PLACED,
            channel=NotificationChannel.IN_APP,
            enabled=False,  # Try to disable mandatory type
        )
        with patch("apps.notification.services.notification_service.dispatch_notification_task") as mock_task:
            mock_task.delay = lambda *a: None
            result = create_notification(
                recipient=client_user,
                notification_type=NotificationType.ORDER_PLACED,
                title="Order Placed",
                body="You placed an order.",
                channel=NotificationChannel.IN_APP,
            )
        assert result is not None, "Mandatory notification must not be suppressed."

    def test_metadata_stored_correctly(self, client_user):
        meta = {"order_id": "abc-123", "order_number": "FSN-ORD-001"}
        with patch("apps.notification.services.notification_service.dispatch_notification_task") as mock_task:
            mock_task.delay = lambda *a: None
            notif = create_notification(
                recipient=client_user,
                notification_type=NotificationType.ORDER_PLACED,
                title="T",
                body="B",
                metadata=meta,
            )
        assert notif.metadata == meta


# ─────────────────────────────────────────────────────────────────────────────
# TESTS: mark_as_read / mark_all_as_read
# ─────────────────────────────────────────────────────────────────────────────

class TestMarkRead:
    def test_mark_as_read_sets_read_at(self, client_user):
        notif = Notification.objects.create(
            recipient=client_user,
            notification_type=NotificationType.PROMO,
            channel=NotificationChannel.IN_APP,
            title="Test",
            body="Body",
        )
        assert not notif.is_read
        updated = mark_as_read(user=client_user, notification_id=notif.id)
        assert updated is not None
        assert updated.is_read

    def test_mark_as_read_wrong_user_returns_none(self, client_user, vendor_user):
        notif = Notification.objects.create(
            recipient=client_user,
            notification_type=NotificationType.PROMO,
            channel=NotificationChannel.IN_APP,
            title="Test",
            body="Body",
        )
        result = mark_as_read(user=vendor_user, notification_id=notif.id)
        assert result is None

    def test_mark_all_as_read_counts_correctly(self, client_user):
        for i in range(3):
            Notification.objects.create(
                recipient=client_user,
                notification_type=NotificationType.PROMO,
                channel=NotificationChannel.IN_APP,
                title=f"Notif {i}",
                body="Body",
            )
        count = mark_all_as_read(user=client_user)
        assert count == 3
        remaining_unread = Notification.objects.filter(
            recipient=client_user,
            read_at__isnull=True,
        ).count()
        assert remaining_unread == 0


# ─────────────────────────────────────────────────────────────────────────────
# TESTS: send_order_notification
# ─────────────────────────────────────────────────────────────────────────────

class TestSendOrderNotification:
    def test_creates_order_notification_with_metadata(self, client_user):
        with patch("apps.notification.services.notification_service.dispatch_notification_task") as mock_task:
            mock_task.delay = lambda *a: None
            notif = send_order_notification(
                recipient=client_user,
                notification_type=NotificationType.ORDER_SHIPPED,
                order_number="FSN-001",
                order_id="uuid-123",
            )
        assert notif is not None
        assert notif.metadata["order_number"] == "FSN-001"
        assert notif.metadata["order_id"] == "uuid-123"


# ─────────────────────────────────────────────────────────────────────────────
# TESTS: bulk_notify
# ─────────────────────────────────────────────────────────────────────────────

class TestBulkNotify:
    def test_bulk_creates_for_all_users(self, client_user, vendor_user):
        created = bulk_notify(
            recipients=[client_user, vendor_user],
            notification_type=NotificationType.PROMO,
            title="Big Sale!",
            body="Up to 50% off.",
        )
        assert len(created) == 2

    def test_bulk_excludes_opted_out_users(self, client_user, vendor_user):
        NotificationPreference.objects.create(
            user=client_user,
            notification_type=NotificationType.PROMO,
            channel=NotificationChannel.IN_APP,
            enabled=False,
        )
        created = bulk_notify(
            recipients=[client_user, vendor_user],
            notification_type=NotificationType.PROMO,
            title="Sale",
            body="Sale body",
        )
        assert len(created) == 1
        assert created[0].recipient == vendor_user
