# apps/audit_logs/tests/conftest.py
"""
Audit Logs Test Conftest
========================
Shared fixtures for audit_logs test suite.
"""
from __future__ import annotations

import pytest


@pytest.fixture
def audit_request(rf):
    """
    Fake Django request with sensible defaults for audit tests.
    Uses pytest-django's `rf` (RequestFactory).
    """
    request = rf.get("/api/v1/test/")
    request.META["REMOTE_ADDR"] = "1.2.3.4"
    request.META["HTTP_USER_AGENT"] = "TestBrowser/1.0"
    return request


@pytest.fixture
def superuser(db):
    """Create a superuser for admin-related tests."""
    from apps.authentication.models import UnifiedUser
    return UnifiedUser.objects.create_superuser(
        email="superuser@fashionistar.io",
        password="SuperPass123!",
    )
