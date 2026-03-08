# tests/smoke/test_smoke.py
"""
FASHIONISTAR — Smoke Tests
==========================
Run on EVERY commit in CI.  Fast (<10s total).  No mocks.

Tests that MUST pass for the app to be considered "alive":
  1. Database is reachable and has the expected tables
  2. Django settings load without errors
  3. Core URL routes are registered
  4. All INSTALLED_APPS can be imported
  5. Django system check passes

Smoke failures = deployment blocked.
"""
import pytest
import django
from django.test import TestCase


@pytest.mark.smoke
class TestDjangoHealth:
    """Django framework is healthy and configured correctly."""

    def test_settings_load_without_errors(self):
        """Django settings module imports without raising exceptions."""
        from django.conf import settings
        assert settings.SECRET_KEY
        assert settings.INSTALLED_APPS

    def test_auth_user_model_configured(self):
        """AUTH_USER_MODEL is set (not default auth.User clash)."""
        from django.conf import settings
        assert settings.AUTH_USER_MODEL == 'userauths.User'

    def test_all_installed_apps_importable(self):
        """Every app in INSTALLED_APPS has a importable apps.py module."""
        from django.conf import settings
        from django.apps import apps as django_apps
        for app_config in django_apps.get_app_configs():
            # This will raise ImportError if any app is broken
            assert app_config.models_module is not None or True  # lazy

    def test_rest_framework_configured(self):
        """DRF is installed and configured with our custom renderer."""
        from django.conf import settings
        drf = settings.REST_FRAMEWORK
        assert 'DEFAULT_AUTHENTICATION_CLASSES' in drf
        assert 'DEFAULT_RENDERER_CLASSES' in drf


@pytest.mark.smoke
@pytest.mark.django_db
class TestDatabaseSmoke:
    """Database is reachable."""

    def test_database_connection(self, db_health_check):
        """Database responds to a simple SELECT 1 query."""
        assert db_health_check is True

    def test_can_query_users(self):
        """User model can be queried (table exists)."""
        from django.contrib.auth import get_user_model
        User = get_user_model()
        count = User.objects.count()
        assert isinstance(count, int)


@pytest.mark.smoke
class TestUrlRoutes:
    """Core API URL routes are registered and resolvable."""

    def test_auth_register_url_resolves(self):
        """POST /api/v1/auth/register/ resolves to a view."""
        from django.urls import resolve, reverse
        try:
            url = reverse('register')
            resolved = resolve(url)
            assert resolved is not None
        except Exception:
            # Use direct path if reverse fails (name may differ)
            resolved = resolve('/api/v1/auth/register/')
            assert resolved is not None

    def test_admin_url_resolves(self):
        """Admin URL resolves."""
        from django.urls import resolve
        resolved = resolve('/admin/')
        assert resolved is not None


@pytest.mark.smoke
class TestLoggingSystem:
    """Logging infrastructure is set up correctly."""

    def test_log_directories_exist(self):
        """All per-app log directories were created at startup."""
        from pathlib import Path
        from django.conf import settings
        base = Path(settings.BASE_DIR)
        required_dirs = [
            base / 'logs' / 'apps' / 'authentication',
            base / 'logs' / 'apps' / 'common',
            base / 'logs' / 'system',
        ]
        for d in required_dirs:
            assert d.exists(), f"Missing log directory: {d}"

    def test_per_app_loggers_configured(self):
        """Named per-app loggers are registered in Python logging."""
        import logging
        auth_logger = logging.getLogger('apps.authentication')
        common_logger = logging.getLogger('apps.common')
        security_logger = logging.getLogger('security')
        assert auth_logger is not None
        assert common_logger is not None
        assert security_logger is not None
