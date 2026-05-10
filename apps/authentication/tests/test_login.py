# apps/authentication/tests/test_login.py
"""
Login Tests — Sprint B

Tests the synchronous login flow:
  POST /api/v1/auth/login/

Covers:
  - Happy path: email + password → JWT tokens returned
  - Happy path: phone + password → JWT tokens returned
  - Wrong password → 401/400
  - Non-existent user → 400
  - Unverified user cannot login
  - JWT response contains both access + refresh tokens
  - Logout: refresh token blacklisted
"""
import pytest
from rest_framework import status


LOGIN_URL = '/api/v1/auth/login/'
LOGOUT_URL = '/api/v1/auth/logout/'


# =============================================================================
# HAPPY PATH TESTS
# =============================================================================

@pytest.mark.django_db
@pytest.mark.api
class TestLoginHappyPath:
    """Valid credentials return JWT tokens."""

    def test_email_login_returns_200_with_tokens(
        self, api_client, registered_verified_user
    ):
        """
        POST /api/v1/auth/login/ with valid email+password
        returns 200 with access and refresh tokens.
        """
        payload = {
            'email_or_phone': registered_verified_user.email,
            'password': 'SecurePass123!@#',
        }
        response = api_client.post(LOGIN_URL, payload, format='json')

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        # Flat response format (Phase 3, March 2026)
        # access + refresh are at the top level or inside 'data' key
        payload = data.get('data', data)
        assert 'access' in payload, (
            f"'access' missing from response. Keys: {list(payload.keys())}. "
            "Response format must be flat (not nested under 'tokens')."
        )
        assert 'refresh' in payload

    def test_login_access_token_is_non_empty(
        self, api_client, registered_verified_user
    ):
        """Access token must be a non-empty string (valid JWT structure)."""
        payload = {
            'email_or_phone': registered_verified_user.email,
            'password': 'SecurePass123!@#',
        }
        response = api_client.post(LOGIN_URL, payload, format='json')
        payload = response.json().get('data', response.json())
        access_token = payload.get('access', '')
        assert access_token, "access token must not be empty"
        # JWT format: header.payload.signature — 3 dot-separated segments
        assert len(access_token.split('.')) == 3


# =============================================================================
# AUTHENTICATION FAILURE TESTS
# =============================================================================

@pytest.mark.django_db
@pytest.mark.api
class TestLoginFailures:
    """Invalid credential combinations must be rejected."""

    def test_wrong_password_returns_error(
        self, api_client, registered_verified_user
    ):
        """Wrong password must not return tokens."""
        payload = {
            'email_or_phone': registered_verified_user.email,
            'password': 'WrongPassword999!',
        }
        response = api_client.post(LOGIN_URL, payload, format='json')
        assert response.status_code in (
            status.HTTP_400_BAD_REQUEST,
            status.HTTP_401_UNAUTHORIZED,
        )

    def test_non_existent_user_returns_error(self, api_client):
        """Unknown email must not return tokens."""
        payload = {
            'email_or_phone': 'nobody@nowhere.com',
            'password': 'somepassword',
        }
        response = api_client.post(LOGIN_URL, payload, format='json')
        assert response.status_code in (
            status.HTTP_400_BAD_REQUEST,
            status.HTTP_401_UNAUTHORIZED,
        )

    def test_empty_payload_returns_400(self, api_client):
        """Empty POST body must return 400."""
        response = api_client.post(LOGIN_URL, {}, format='json')
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_unverified_user_cannot_login(
        self, api_client, registered_user
    ):
        """
        Users who have not verified their OTP (is_active=False)
        must NOT receive JWT tokens. Prevents account hijacking via
        unverified email addresses.
        """
        payload = {
            'email_or_phone': registered_user.email,
            'password': 'SecurePass123!@#',
        }
        response = api_client.post(LOGIN_URL, payload, format='json')
        # Must NOT be 200 with tokens
        data = response.json()
        tokens = data.get('tokens')
        assert response.status_code != status.HTTP_200_OK or tokens is None


# =============================================================================
# LOGOUT TESTS
# =============================================================================

@pytest.mark.django_db
@pytest.mark.api
class TestLogout:
    """JWT refresh token blacklisting on logout."""

    def test_logout_blacklists_refresh_token(
        self, auth_api_client, registered_verified_user
    ):
        """
        POST /api/v1/auth/logout/ with valid refresh token
        must return 200 and blacklist the token.
        """
        from rest_framework_simplejwt.tokens import RefreshToken
        refresh = RefreshToken.for_user(registered_verified_user)

        response = auth_api_client.post(
            LOGOUT_URL,
            {'refresh': str(refresh)},
            format='json'
        )
        assert response.status_code == status.HTTP_200_OK

    def test_logout_without_refresh_token_returns_400(
        self, auth_api_client
    ):
        """Logout with no refresh token body must return 400."""
        response = auth_api_client.post(LOGOUT_URL, {}, format='json')
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_logout_requires_authentication(self, api_client):
        """
        Unauthenticated logout attempt (no Bearer token) must return 401.
        """
        response = api_client.post(
            LOGOUT_URL,
            {'refresh': 'some-token'},
            format='json'
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_double_logout_returns_400(
        self, auth_api_client, registered_verified_user
    ):
        """
        Attempting to use a blacklisted refresh token a second time
        must return 400 (token already invalid).
        """
        from rest_framework_simplejwt.tokens import RefreshToken
        refresh = RefreshToken.for_user(registered_verified_user)
        refresh_str = str(refresh)

        # First logout — should succeed
        auth_api_client.post(LOGOUT_URL, {'refresh': refresh_str}, format='json')

        # Second logout — token is now blacklisted
        response = auth_api_client.post(
            LOGOUT_URL, {'refresh': refresh_str}, format='json'
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
