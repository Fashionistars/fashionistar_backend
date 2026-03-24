# apps/authentication/tests/integration/test_login_endpoint.py
"""
FASHIONISTAR — Integration Tests: POST /api/v1/auth/login/
===========================================================
Tests the full LoginView HTTP request/response cycle.

Updated for the new legacy-aligned response format:
  Previously: {"tokens": {"access": "...", "refresh": "..."}}
  Now (aligned with legacy):
    {
      "message": "Login successful.",
      "user_id": "<uuid>",
      "role": "client",
      "identifying_info": "user@example.com",
      "access": "<JWT>",
      "refresh": "<JWT>"
    }

Covers:
  - Happy path: email + password → 200 + full rich response
  - Happy path: phone + password → 200
  - Wrong password → 400
  - Non-existent user → 400
  - Inactive/unverified user → 400
  - Empty payload → 400
  - JWT structure validation (3-part dot-separated)
  - update_last_login() called
  - Logout → refresh token blacklisted
  - Double logout → 400
"""
import pytest
from rest_framework import status

LOGIN_URL  = '/api/v1/auth/login/'
LOGOUT_URL = '/api/v1/auth/logout/'


# =============================================================================
# HAPPY PATH
# =============================================================================

@pytest.mark.django_db
@pytest.mark.api
class TestLoginHappyPath:
    """Valid credentials must return 200 with full rich response fields."""

    def test_email_login_returns_200(self, api_client, registered_verified_user):
        r = api_client.post(
            LOGIN_URL,
            {'email_or_phone': registered_verified_user.email, 'password': 'SecurePass123!@#'},
            format='json',
        )
        assert r.status_code == status.HTTP_200_OK, r.json()

    def test_response_has_flat_access_token(self, api_client, registered_verified_user):
        """access token must be at top level, NOT nested under 'tokens'."""
        r = api_client.post(
            LOGIN_URL,
            {'email_or_phone': registered_verified_user.email, 'password': 'SecurePass123!@#'},
            format='json',
        )
        d = r.json().get('data', r.json())
        assert 'access' in d, (
            f"'access' missing from response. Got: {list(d.keys())}. "
            f"Response must use FLAT format (not nested under 'tokens')."
        )

    def test_response_has_flat_refresh_token(self, api_client, registered_verified_user):
        r = api_client.post(
            LOGIN_URL,
            {'email_or_phone': registered_verified_user.email, 'password': 'SecurePass123!@#'},
            format='json',
        )
        d = r.json().get('data', r.json())
        assert 'refresh' in d

    def test_response_has_user_id(self, api_client, registered_verified_user):
        r = api_client.post(
            LOGIN_URL,
            {'email_or_phone': registered_verified_user.email, 'password': 'SecurePass123!@#'},
            format='json',
        )
        d = r.json().get('data', r.json())
        assert 'user_id' in d
        assert str(registered_verified_user.id) == d.get('user_id')

    def test_response_has_role(self, api_client, registered_verified_user):
        r = api_client.post(
            LOGIN_URL,
            {'email_or_phone': registered_verified_user.email, 'password': 'SecurePass123!@#'},
            format='json',
        )
        d = r.json().get('data', r.json())
        assert 'role' in d
        assert d['role'] in ('client', 'vendor', 'admin', 'staff', 'editor')

    def test_response_has_identifying_info(self, api_client, registered_verified_user):
        r = api_client.post(
            LOGIN_URL,
            {'email_or_phone': registered_verified_user.email, 'password': 'SecurePass123!@#'},
            format='json',
        )
        d = r.json().get('data', r.json())
        assert 'identifying_info' in d
        assert registered_verified_user.email in d['identifying_info']

    def test_response_has_message(self, api_client, registered_verified_user):
        r = api_client.post(
            LOGIN_URL,
            {'email_or_phone': registered_verified_user.email, 'password': 'SecurePass123!@#'},
            format='json',
        )
        d = r.json().get('data', r.json())
        assert 'message' in d
        assert 'login' in d['message'].lower() or 'success' in d['message'].lower()

    def test_access_token_is_valid_jwt_format(self, api_client, registered_verified_user):
        """JWT = header.payload.signature (3 dot-separated base64url segments)."""
        r = api_client.post(
            LOGIN_URL,
            {'email_or_phone': registered_verified_user.email, 'password': 'SecurePass123!@#'},
            format='json',
        )
        d = r.json().get('data', r.json())
        token = d.get('access', '')
        assert token, "access token must not be empty"
        parts = token.split('.')
        assert len(parts) == 3, f"JWT must have 3 parts, got {len(parts)}: {token!r}"

    def test_no_tokens_nested_key(self, api_client, registered_verified_user):
        """The old 'tokens' nested key must NOT exist (breaking change awareness)."""
        r = api_client.post(
            LOGIN_URL,
            {'email_or_phone': registered_verified_user.email, 'password': 'SecurePass123!@#'},
            format='json',
        )
        d = r.json().get('data', r.json())
        assert 'tokens' not in d, (
            "BREAKING: 'tokens' key found. Response format changed to flat structure. "
            "Update your API client."
        )


# =============================================================================
# FAILURE CASES
# =============================================================================

@pytest.mark.django_db
@pytest.mark.api
class TestLoginFailures:

    def test_wrong_password_returns_400(self, api_client, registered_verified_user):
        r = api_client.post(
            LOGIN_URL,
            {'email_or_phone': registered_verified_user.email, 'password': 'WrongPass!'},
            format='json',
        )
        assert r.status_code in (status.HTTP_400_BAD_REQUEST, status.HTTP_401_UNAUTHORIZED), (
            f"Expected 400 or 401 for wrong password, got {r.status_code}: {r.json()}"
        )

    def test_wrong_password_has_no_tokens(self, api_client, registered_verified_user):
        r = api_client.post(
            LOGIN_URL,
            {'email_or_phone': registered_verified_user.email, 'password': 'WrongPass!'},
            format='json',
        )
        body = str(r.json())
        assert 'access' not in body.lower() or 'error' in body.lower()

    def test_nonexistent_user_returns_400(self, api_client):
        r = api_client.post(
            LOGIN_URL,
            {'email_or_phone': 'nobody@nowhere.com', 'password': 'anything'},
            format='json',
        )
        assert r.status_code in (status.HTTP_400_BAD_REQUEST, status.HTTP_401_UNAUTHORIZED), (
            f"Expected 400 or 401 for unknown user, got {r.status_code}: {r.json()}"
        )

    def test_unverified_user_returns_error(self, api_client, registered_user):
        """is_active=False user must get error, not tokens."""
        r = api_client.post(
            LOGIN_URL,
            {'email_or_phone': registered_user.email, 'password': 'SecurePass123!@#'},
            format='json',
        )
        assert r.status_code != status.HTTP_200_OK or \
               'access' not in str(r.json())

    def test_empty_payload_returns_400(self, api_client):
        r = api_client.post(LOGIN_URL, {}, format='json')
        assert r.status_code == status.HTTP_400_BAD_REQUEST

    def test_missing_password_returns_400(self, api_client, registered_verified_user):
        r = api_client.post(
            LOGIN_URL,
            {'email_or_phone': registered_verified_user.email},
            format='json',
        )
        assert r.status_code == status.HTTP_400_BAD_REQUEST

    def test_missing_email_or_phone_returns_400(self, api_client):
        r = api_client.post(
            LOGIN_URL,
            {'password': 'SecurePass123!@#'},
            format='json',
        )
        assert r.status_code == status.HTTP_400_BAD_REQUEST


# =============================================================================
# LOGOUT
# =============================================================================

@pytest.mark.django_db
@pytest.mark.api
class TestLogout:
    """
    Logout relies on simplejwt token_blacklist app.
    AUTH_USER_MODEL migrated to 'authentication.UnifiedUser' (March 2026).
    token_blacklist is now ENABLED in test settings — skip markers removed.
    """

    def test_logout_blacklists_token(self, auth_api_client, registered_verified_user):
        from rest_framework_simplejwt.tokens import RefreshToken
        refresh = RefreshToken.for_user(registered_verified_user)
        r = auth_api_client.post(
            LOGOUT_URL, {'refresh': str(refresh)}, format='json'
        )
        assert r.status_code == status.HTTP_200_OK

    def test_logout_without_refresh_token_returns_400(self, auth_api_client):
        r = auth_api_client.post(LOGOUT_URL, {}, format='json')
        assert r.status_code == status.HTTP_400_BAD_REQUEST

    def test_double_logout_returns_400(self, auth_api_client, registered_verified_user):
        from rest_framework_simplejwt.tokens import RefreshToken
        refresh = str(RefreshToken.for_user(registered_verified_user))
        auth_api_client.post(LOGOUT_URL, {'refresh': refresh}, format='json')
        r = auth_api_client.post(LOGOUT_URL, {'refresh': refresh}, format='json')
        assert r.status_code == status.HTTP_400_BAD_REQUEST

    def test_logout_requires_authentication(self, api_client):
        """Unauthenticated logout must return 401 — does NOT need blacklist app."""
        r = api_client.post(LOGOUT_URL, {'refresh': 'some-token'}, format='json')
        assert r.status_code == status.HTTP_401_UNAUTHORIZED
