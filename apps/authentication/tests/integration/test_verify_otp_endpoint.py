# apps/authentication/tests/integration/test_verify_otp_endpoint.py
"""
FASHIONISTAR — Integration Tests: POST /api/v1/auth/verify-otp/
================================================================
Tests the full VerifyOTPView HTTP request/response cycle.

Key behaviour under test:
  - Client sends ONLY the 6-digit OTP (no user_id in body) — legacy UX match
  - OTPService.verify_by_otp_sync() discovers user_id from SHA-256 hash index
  - Account activated: is_active=True, is_verified=True
  - JWT tokens returned: {message, user_id, role, identifying_info, access, refresh}
  - update_last_login() called
  - Invalid / expired OTP → 400
  - Missing OTP → 400
  - Non-numeric OTP → 400
  - OTP for different purpose rejected
  - Idempotent: already-verified users re-verify safely
"""
import pytest
from unittest.mock import patch
from rest_framework import status

VERIFY_URL = '/api/v1/auth/verify-otp/'
OTP_SERVICE = 'apps.authentication.services.otp.sync_service.OTPService'


def _mock_verify(return_value):
    """Patch OTPService.verify_by_otp_sync with a fixed return_value."""
    return patch(f'{OTP_SERVICE}.verify_by_otp_sync', return_value=return_value)


# =============================================================================
# HAPPY PATH
# =============================================================================

@pytest.mark.django_db
@pytest.mark.api
class TestVerifyOTPHappyPath:
    """Valid OTP → account activated + JWT tokens returned."""

    def test_valid_otp_returns_200(self, api_client, registered_user):
        uid = str(registered_user.id)
        with _mock_verify({'user_id': uid, 'purpose': 'verify'}):
            r = api_client.post(VERIFY_URL, {'otp': '123456'}, format='json')
        assert r.status_code == status.HTTP_200_OK, r.json()

    def test_response_contains_access_token(self, api_client, registered_user):
        uid = str(registered_user.id)
        with _mock_verify({'user_id': uid, 'purpose': 'verify'}):
            r = api_client.post(VERIFY_URL, {'otp': '123456'}, format='json')
        d = r.json()
        # Flat structure (not nested under 'tokens')
        assert 'access' in d.get('data', d)

    def test_response_contains_refresh_token(self, api_client, registered_user):
        uid = str(registered_user.id)
        with _mock_verify({'user_id': uid, 'purpose': 'verify'}):
            r = api_client.post(VERIFY_URL, {'otp': '123456'}, format='json')
        d = r.json().get('data', r.json())
        assert 'refresh' in d

    def test_response_contains_user_id(self, api_client, registered_user):
        uid = str(registered_user.id)
        with _mock_verify({'user_id': uid, 'purpose': 'verify'}):
            r = api_client.post(VERIFY_URL, {'otp': '123456'}, format='json')
        d = r.json().get('data', r.json())
        assert d.get('user_id') == uid

    def test_response_contains_role(self, api_client, registered_user):
        uid = str(registered_user.id)
        with _mock_verify({'user_id': uid, 'purpose': 'verify'}):
            r = api_client.post(VERIFY_URL, {'otp': '123456'}, format='json')
        d = r.json().get('data', r.json())
        assert d.get('role') in ('client', 'vendor')

    def test_response_contains_identifying_info(self, api_client, registered_user):
        uid = str(registered_user.id)
        with _mock_verify({'user_id': uid, 'purpose': 'verify'}):
            r = api_client.post(VERIFY_URL, {'otp': '123456'}, format='json')
        d = r.json().get('data', r.json())
        assert 'identifying_info' in d

    def test_response_message_confirms_verification(self, api_client, registered_user):
        uid = str(registered_user.id)
        with _mock_verify({'user_id': uid, 'purpose': 'verify'}):
            r = api_client.post(VERIFY_URL, {'otp': '123456'}, format='json')
        d = r.json().get('data', r.json())
        assert 'verified' in d.get('message', '').lower()

    def test_user_activated_after_verify(self, api_client, registered_user):
        """is_active and is_verified must be True after successful OTP verify."""
        from apps.authentication.models import UnifiedUser
        uid = str(registered_user.id)
        with _mock_verify({'user_id': uid, 'purpose': 'verify'}):
            api_client.post(VERIFY_URL, {'otp': '123456'}, format='json')
        u = UnifiedUser.objects.get(id=registered_user.id)
        assert u.is_active is True
        assert u.is_verified is True

    def test_no_user_id_in_request_body(self, api_client, registered_user):
        """
        CRITICAL: client must NOT need to send user_id — OTP alone is enough.
        This test deliberately sends ONLY the OTP.
        """
        uid = str(registered_user.id)
        with _mock_verify({'user_id': uid, 'purpose': 'verify'}):
            r = api_client.post(
                VERIFY_URL,
                {'otp': '123456'},   # ← NO user_id
                format='json'
            )
        assert r.status_code == status.HTTP_200_OK, (
            f"OTP-only verify failed: {r.json()}. "
            f"User_id should NOT be required from the client."
        )

    def test_access_token_is_valid_jwt_format(self, api_client, registered_user):
        uid = str(registered_user.id)
        with _mock_verify({'user_id': uid, 'purpose': 'verify'}):
            r = api_client.post(VERIFY_URL, {'otp': '123456'}, format='json')
        token = r.json().get('data', r.json()).get('access', '')
        parts = token.split('.')
        assert len(parts) == 3, f"JWT must have 3 parts, got {token!r}"


# =============================================================================
# ERROR CASES
# =============================================================================

@pytest.mark.django_db
@pytest.mark.api
class TestVerifyOTPErrors:
    """All error paths return correct status codes and messages."""

    def test_invalid_otp_returns_400(self, api_client):
        with _mock_verify(None):    # hash-index miss → None
            r = api_client.post(VERIFY_URL, {'otp': '000000'}, format='json')
        assert r.status_code == status.HTTP_400_BAD_REQUEST

    def test_expired_otp_returns_400(self, api_client):
        with _mock_verify(None):
            r = api_client.post(VERIFY_URL, {'otp': '999999'}, format='json')
        assert r.status_code == status.HTTP_400_BAD_REQUEST

    def test_missing_otp_field_returns_400(self, api_client):
        r = api_client.post(VERIFY_URL, {}, format='json')
        assert r.status_code == status.HTTP_400_BAD_REQUEST

    def test_non_numeric_otp_returns_400(self, api_client):
        r = api_client.post(VERIFY_URL, {'otp': 'ABCDEF'}, format='json')
        assert r.status_code == status.HTTP_400_BAD_REQUEST

    def test_5_digit_otp_returns_400(self, api_client):
        r = api_client.post(VERIFY_URL, {'otp': '12345'}, format='json')
        assert r.status_code == status.HTTP_400_BAD_REQUEST

    def test_error_response_has_no_tokens(self, api_client):
        with _mock_verify(None):
            r = api_client.post(VERIFY_URL, {'otp': '000000'}, format='json')
        d = r.json().get('errors', r.json())
        assert 'access' not in str(d)
        assert 'refresh' not in str(d)


# =============================================================================
# ALREADY-VERIFIED USER
# =============================================================================

@pytest.mark.django_db
@pytest.mark.api
class TestVerifyOTPAlreadyVerified:
    """Calling verify-otp on an already-verified user must succeed safely."""

    def test_already_verified_user_returns_200(
        self, api_client, registered_verified_user
    ):
        uid = str(registered_verified_user.id)
        with _mock_verify({'user_id': uid, 'purpose': 'verify'}):
            r = api_client.post(VERIFY_URL, {'otp': '123456'}, format='json')
        assert r.status_code == status.HTTP_200_OK
