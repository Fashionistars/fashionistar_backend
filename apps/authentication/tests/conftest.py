# apps/authentication/tests/conftest.py
"""
apps.authentication — Test fixtures
=====================================
App-specific fixtures for authentication tests.
Complements the root conftest.py (which provides api_client, auth_api_client, etc.)

Provides:
  - otp_user: user with a pending OTP token
  - blocked_user: user with too many failed attempts
  - google_oauth_payload: mock Google OAuth2 payload
  - biometric_user: user with biometric credential set
  - password_reset_user: user with a valid password reset token
"""
import pytest
from unittest.mock import patch, MagicMock


@pytest.fixture
@pytest.mark.django_db
def otp_user(db):
    """
    A registered but unverified user with a pending OTP.
    Use this to test OTP verification endpoints.
    """
    from apps.authentication.models import UnifiedUser, OTPToken
    user = UnifiedUser.objects.create_user(
        email='otp@fashionistar-test.io',
        password='OtpTest!234',
        role='client',
        is_active=False,
        is_verified=False,
    )
    # Create a pending OTP token
    OTPToken.objects.create(
        user=user,
        otp_code='123456',
        is_used=False,
    )
    return user


@pytest.fixture
@pytest.mark.django_db
def google_oauth_payload():
    """
    Mock Google OAuth2 ID token payload (as returned by Google's tokeninfo API).
    Use to test the Google OAuth2 registration/login endpoints.
    """
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
    """
    Mock Google token verification so tests never hit Google's API.
    """
    with patch(
        'apps.authentication.services.google_service.sync_service.verify_google_token',
        return_value=google_oauth_payload,
    ) as mock_verify:
        yield mock_verify


@pytest.fixture
@pytest.mark.django_db
def password_reset_token(db, registered_verified_user):
    """
    User with a valid password reset token.
    Returns (user, token_string) tuple.
    """
    from rest_framework_simplejwt.tokens import RefreshToken
    # Use JWT-based reset token (simulated)
    refresh = RefreshToken.for_user(registered_verified_user)
    token = str(refresh.access_token)
    return registered_verified_user, token


@pytest.fixture
def mock_otp_dispatch():
    """
    Mock OTP email/SMS dispatch — prevents real emails during tests.
    Returns the mock so tests can assert .called, .call_args, etc.
    """
    with patch(
        'apps.authentication.services.otp_service.OTPService.dispatch_otp',
        return_value=True,
    ) as mock_dispatch:
        yield mock_dispatch


@pytest.fixture
def mock_sms_otp():
    """Mock the SMS OTP sender specifically."""
    with patch(
        'apps.common.managers.sms.SMSManager.send',
        return_value={'status': 'success'},
    ) as mock_sms:
        yield mock_sms
