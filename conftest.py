# fashionistar_backend/conftest.py
"""
Fashionistar — Root pytest conftest.

Provides shared fixtures for the entire test suite.
Import order: fixtures defined here are available in ALL test modules.

Fixture scopes:
  - session: Created once per test session (expensive setup: DB, test users)
  - module:  Created once per test module
  - function: Created fresh for every test (default, most common)

Usage pattern:
    def test_something(api_client, registered_user):
        response = api_client.post('/api/v1/auth/login/', {...})
        assert response.status_code == 200
"""
import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient


# ─────────────────────────────────────────────────────────────────────────────
#  CORE FIXTURES
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def api_client():
    """
    Unauthenticated DRF APIClient.
    Use for testing public endpoints (register, login, verify-otp, etc.)
    """
    return APIClient()


@pytest.fixture
def auth_api_client(registered_verified_user):
    """
    Authenticated APIClient: JWT access token pre-set in Authorization header.
    Use for testing endpoints that require IsAuthenticated.
    """
    from rest_framework_simplejwt.tokens import RefreshToken
    client = APIClient()
    user = registered_verified_user
    refresh = RefreshToken.for_user(user)
    client.credentials(HTTP_AUTHORIZATION=f'Bearer {str(refresh.access_token)}')
    return client


# ─────────────────────────────────────────────────────────────────────────────
#  UNIFIEDUSER FIXTURES
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def unverified_user_data():
    """Dict of valid registration payload (email-based)."""
    return {
        'email': 'testuser@fashionistar.io',
        'password': 'SecurePass123!@#',
        'password2': 'SecurePass123!@#',
        'role': 'client',
    }


@pytest.fixture
def vendor_registration_data():
    """Dict of valid vendor registration payload (email-based)."""
    return {
        'email': 'vendor@fashionistar.io',
        'password': 'SecureVendor456!@#',
        'password2': 'SecureVendor456!@#',
        'role': 'vendor',
    }


@pytest.fixture
def phone_registration_data():
    """Dict of valid phone-based registration payload."""
    return {
        'phone': '+2348012345678',
        'password': 'SecurePhone789!@#',
        'password2': 'SecurePhone789!@#',
        'role': 'client',
    }


@pytest.fixture
@pytest.mark.django_db
def registered_user(db):
    """
    UnifiedUser: created, is_active=False, is_verified=False.
    Simulates a user who just registered but hasn't verified OTP yet.
    """
    from apps.authentication.models import UnifiedUser
    user = UnifiedUser.objects.create_user(
        email='registered@fashionistar.io',
        password='SecurePass123!@#',
        role='client',
        is_active=False,
        is_verified=False,
    )
    return user


@pytest.fixture
@pytest.mark.django_db
def registered_verified_user(db):
    """
    UnifiedUser: created, is_active=True, is_verified=True.
    Simulates a fully onboarded user. Use for authenticated endpoint tests.
    """
    from apps.authentication.models import UnifiedUser
    user = UnifiedUser.objects.create_user(
        email='verified@fashionistar.io',
        password='SecurePass123!@#',
        role='client',
        is_active=True,
        is_verified=True,
    )
    return user


@pytest.fixture
@pytest.mark.django_db
def vendor_user(db):
    """Active, verified vendor UnifiedUser."""
    from apps.authentication.models import UnifiedUser
    user = UnifiedUser.objects.create_user(
        email='vendor@fashionistar.io',
        password='VendorPass456!@#',
        role='vendor',
        is_active=True,
        is_verified=True,
    )
    return user


# ─────────────────────────────────────────────────────────────────────────────
#  REDIS MOCK FIXTURE
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_redis(mocker):
    """
    Replace get_redis_connection_safe with an in-memory mock.
    Prevents tests from requiring a live Redis instance.

    Returns a MagicMock pre-configured with common Redis operations.
    """
    mock_client = mocker.MagicMock()
    mock_client.exists.return_value = True
    mock_client.get.return_value = b'mockdata'
    mock_client.set.return_value = True
    mock_client.delete.return_value = True
    mock_client.setex.return_value = True

    mocker.patch(
        'apps.common.utils.get_redis_connection_safe',
        return_value=mock_client,
    )
    return mock_client


# ─────────────────────────────────────────────────────────────────────────────
#  EMAIL MOCK FIXTURE
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_email(mocker):
    """
    Suppress email sending in tests (patches EmailManager.send_mail).
    Returns the mock so tests can assert on call count / args.
    """
    return mocker.patch('apps.common.managers.email.EmailManager.send_mail')


@pytest.fixture
def mock_sms(mocker):
    """Suppress SMS sending in tests (patches SMSManager.send_sms)."""
    return mocker.patch('apps.common.managers.sms.SMSManager.send_sms')
