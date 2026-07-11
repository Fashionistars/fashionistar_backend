"""
Fixtures for analytics app tests.

Provides reusable test users, mock cache helpers, and patch utilities for the
analytics workflow, tasks, and Ninja endpoints.
"""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model

User = get_user_model()


@pytest.fixture(autouse=True)
def _flush_after_transaction_test(request):
    """Flush DB after transaction=True tests to prevent data leaking
    via shared in-memory SQLite to subsequent TestCase-based tests."""
    yield
    marker = request.node.get_closest_marker("django_db")
    if marker and marker.kwargs.get("transaction"):
        from django.core.management import call_command
        call_command("flush", verbosity=0, interactive=False, reset_sequences=False)


@pytest.fixture
def staff_user(db):
    """Return a staff user for analytics endpoints that require elevated access."""
    return User.objects.create_user(
        email="staff@analytics.test",
        password="testpass123",
        is_staff=True,
        is_active=True,
    )


@pytest.fixture
def superuser(db):
    """Return a superuser for analytics endpoints."""
    return User.objects.create_superuser(
        email="super@analytics.test",
        password="testpass123",
        is_active=True,
    )


@pytest.fixture
def regular_user(db):
    """Return a regular non-staff user."""
    return User.objects.create_user(
        email="regular@analytics.test",
        password="testpass123",
        is_active=True,
    )


@pytest.fixture
def mock_report():
    """Return a minimal valid platform analytics report payload."""
    return {
        "generated_at": "2026-07-10T00:00:00+00:00",
        "days": 7,
        "scope": "platform",
        "order_metrics": {"total_orders": 10, "total_gmv": 1000.0},
        "product_metrics": {"trending_count": 3},
        "user_metrics": {"new_registrations": 5},
        "vendor_metrics": {"total_vendors": 2},
        "anomalies": [],
        "llm_insights": "",
    }


@pytest.fixture
def alert_firing(db):
    """Return a firing Alert instance for resolution tests."""
    from apps.analytics.models import Alert, AlertRule
    from django.utils import timezone

    rule = AlertRule.objects.create(
        name="Test Rule",
        metric_name="response_time",
        threshold=100.0,
        operator="gt",
        severity="warning",
        is_active=True,
    )
    alert = Alert.objects.create(
        rule=rule,
        status="firing",
        metric_value=200.0,
        message="Threshold exceeded",
        fired_at=timezone.now(),
    )
    return alert
