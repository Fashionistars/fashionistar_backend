# apps/authentication/tests/conftest.py
"""
FASHIONISTAR — Authentication Test Fixtures
============================================
App-scoped fixtures for authentication tests.
Complements the root conftest.py (api_client, auth_api_client,
registered_user, registered_verified_user, etc.)

Key autouse fixtures:
  - no_throttle         : Disables BurstRateThrottle + SustainedRateThrottle
  - mock_otp_generation : Patches OTPService.generate_otp_sync() to avoid real
                          Redis calls (returns fixed '123456') AND stores the
                          SHA-256 hash index in a local dict for test-side lookup
  - mock_otp_verify     : Patches OTPService.verify_by_otp_sync() for tests
                          that exercise the full verify-otp endpoint without Redis

Updated: now patches the new service path
  apps.authentication.services.otp.sync_service.OTPService
"""
import hashlib
import pytest
from unittest.mock import patch, MagicMock

FIXED_OTP = '123456'
_OTP_STORE: dict = {}   # {sha256(otp): {'user_id': ..., 'purpose': ...}}


# ─── Throttle bypass (autouse) ───────────────────────────────────────────────

@pytest.fixture(autouse=True)
def no_throttle(mocker):
    """Disable all throttle classes for every test in this package."""
    mocker.patch(
        'apps.authentication.throttles.BurstRateThrottle.allow_request',
        return_value=True,
    )
    mocker.patch(
        'apps.authentication.throttles.SustainedRateThrottle.allow_request',
        return_value=True,
    )


# ─── OTP generate: NO real Redis (autouse) ────────────────────────────────────

@pytest.fixture(autouse=True)
def mock_otp_generation(mocker):
    """
    Patch OTPService.generate_otp_sync() to avoid real Redis.

    Returns the fixed OTP '123456' and side-effect stores the SHA256 hash
    index so verify_by_otp_sync() can look it up in unit tests that patch
    Redis via the _OTP_STORE dict.
    """
    _OTP_STORE.clear()

    def _fake_generate(user_id, purpose='verify'):
        otp_hash = hashlib.sha256(FIXED_OTP.encode()).hexdigest()
        primary_key = f"otp:{user_id}:{purpose}:FAKESNPT"
        _OTP_STORE[otp_hash] = {
            'user_id': str(user_id),
            'purpose': purpose,
            'primary_key': primary_key,
        }
        return FIXED_OTP

    mocker.patch(
        'apps.authentication.services.otp.sync_service.OTPService.generate_otp_sync',
        side_effect=_fake_generate,
    )
    # Also patch the async wrapper to avoid sync_to_async in async tests
    mocker.patch(
        'apps.authentication.services.otp.sync_service.OTPService.generate_otp_async',
        side_effect=_fake_generate,
    )
    return _OTP_STORE


# ─── Optional: mock Celery tasks (used in tests with transaction=True) ─────────

@pytest.fixture
def mock_email_task():
    """Patch send_email_task.delay at the tasks module level."""
    with patch(
        'apps.authentication.tasks.send_email_task.delay', return_value=None
    ) as m:
        yield m


@pytest.fixture
def mock_sms_task():
    """Patch send_sms_task.delay at the tasks module level."""
    with patch(
        'apps.authentication.tasks.send_sms_task.delay', return_value=None
    ) as m:
        yield m


@pytest.fixture
def mock_both_tasks(mock_email_task, mock_sms_task):
    """Convenience: both email + SMS tasks patched."""
    return mock_email_task, mock_sms_task


# ─── OTP store helper — inject a known OTP into the fake store ─────────────────

@pytest.fixture
def seed_otp_for_user(mock_otp_generation):
    """
    Helper fixture: call seed(user, otp, purpose) to put an entry in
    _OTP_STORE so verify_by_otp_sync() can find it in tests.

    Usage:
        def test_verify(seed_otp_for_user, ...):
            seed_otp_for_user(user, '123456')
    """
    def _seed(user, otp: str = FIXED_OTP, purpose: str = 'verify'):
        otp_hash = hashlib.sha256(otp.encode()).hexdigest()
        primary_key = f"otp:{user.id}:{purpose}:FAKESNPT"
        mock_otp_generation[otp_hash] = {
            'user_id': str(user.id),
            'purpose': purpose,
            'primary_key': primary_key,
        }
    return _seed


# ─── google_oauth_payload (keep for biometric / OAuth tests) ───────────────────

@pytest.fixture
def google_oauth_payload():
    return {
        'sub': 'google-user-id-1234567890',
        'email': 'googleuser@gmail.com',
        'email_verified': True,
        'given_name': 'Google',
        'family_name': 'User',
        'picture': 'https://lh3.googleusercontent.com/a/photo.jpg',
        'iss': 'accounts.google.com',
        'aud': 'your-google-client-id.apps.googleusercontent.com',
    }


@pytest.fixture
def mock_google_verify(google_oauth_payload):
    with patch(
        'apps.authentication.services.google_service.sync_service.verify_google_token',
        return_value=google_oauth_payload,
    ) as mock_verify:
        yield mock_verify


@pytest.fixture
def password_reset_token(db, registered_verified_user):
    from rest_framework_simplejwt.tokens import RefreshToken
    refresh = RefreshToken.for_user(registered_verified_user)
    return registered_verified_user, str(refresh.access_token)
