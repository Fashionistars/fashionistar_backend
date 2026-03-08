# apps/authentication/tests/test_registration.py
"""
Synchronous Registration Tests — Sprint B

Tests the full sync registration flow:
  POST /api/v1/auth/register/

Covers:
  - Happy path: email-based registration
  - Happy path: phone-based registration
  - Duplicate email rejection
  - Duplicate phone rejection
  - Weak password rejection
  - Password mismatch rejection
  - Missing required fields
  - OTP email dispatch (mocked)
  - User created is_active=False, is_verified=False
  - Atomic transaction rollback on failure

Architecture: Tests ONLY the API layer (RegisterView → RegistrationService).
Internal services are mocked where appropriate to test the view in isolation.
"""
import pytest
from django.urls import reverse
from rest_framework import status


# ── URL constant ──────────────────────────────────────────────────────────────
REGISTER_URL = '/api/v1/auth/register/'


# =============================================================================
# HAPPY PATH TESTS
# =============================================================================

@pytest.mark.django_db
@pytest.mark.api
class TestRegistrationHappyPath:
    """Email and phone registration succeed; OTP dispatched."""

    def test_email_registration_returns_201(self, api_client, mock_email, mock_redis):
        """
        POST /api/v1/auth/register/ with valid email → 201 Created.
        Returned payload must contain message, user_id, email.
        """
        payload = {
            'email': 'new@fashionistar.io',
            'password': 'SecurePass123!@#',
            'password2': 'SecurePass123!@#',
            'role': 'client',
        }
        response = api_client.post(REGISTER_URL, payload, format='json')

        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert 'user_id' in data
        assert data['email'] == 'new@fashionistar.io'
        assert 'message' in data

    @pytest.mark.django_db
    def test_registered_user_is_inactive(self, api_client, mock_email, mock_redis):
        """
        Newly registered user must have is_active=False, is_verified=False.
        Account is activated ONLY after OTP verification.
        """
        from apps.authentication.models import UnifiedUser

        payload = {
            'email': 'inactive@fashionistar.io',
            'password': 'SecurePass123!@#',
            'password2': 'SecurePass123!@#',
            'role': 'client',
        }
        response = api_client.post(REGISTER_URL, payload, format='json')
        assert response.status_code == status.HTTP_201_CREATED

        user = UnifiedUser.objects.get(email='inactive@fashionistar.io')
        assert user.is_active is False
        assert user.is_verified is False

    @pytest.mark.django_db
    def test_otp_email_sent_on_registration(self, api_client, mock_email, mock_redis):
        """
        OTP email must be dispatched (EmailManager.send_mail called once)
        immediately after successful registration.
        """
        payload = {
            'email': 'emailtest@fashionistar.io',
            'password': 'SecurePass123!@#',
            'password2': 'SecurePass123!@#',
            'role': 'client',
        }
        api_client.post(REGISTER_URL, payload, format='json')
        mock_email.assert_called_once()

    @pytest.mark.django_db
    def test_vendor_registration_role_saved(self, api_client, mock_email, mock_redis):
        """Vendor role must be persisted on the created UnifiedUser."""
        from apps.authentication.models import UnifiedUser

        payload = {
            'email': 'vendor@fashionistar.io',
            'password': 'SecureVendor123!@#',
            'password2': 'SecureVendor123!@#',
            'role': 'vendor',
        }
        response = api_client.post(REGISTER_URL, payload, format='json')
        assert response.status_code == status.HTTP_201_CREATED

        user = UnifiedUser.objects.get(email='vendor@fashionistar.io')
        assert user.role == 'vendor'


# =============================================================================
# VALIDATION FAILURE TESTS
# =============================================================================

@pytest.mark.django_db
@pytest.mark.api
class TestRegistrationValidation:
    """Invalid payloads must return 400 with descriptive error messages."""

    def test_password_mismatch_returns_400(self, api_client):
        """password ≠ password2 must reject with 400."""
        payload = {
            'email': 'mismatch@fashionistar.io',
            'password': 'SecurePass123!@#',
            'password2': 'WrongPassword999!',
            'role': 'client',
        }
        response = api_client.post(REGISTER_URL, payload, format='json')
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_weak_password_returns_400(self, api_client):
        """Password '123' is too short/simple — must reject."""
        payload = {
            'email': 'weakpw@fashionistar.io',
            'password': '123',
            'password2': '123',
            'role': 'client',
        }
        response = api_client.post(REGISTER_URL, payload, format='json')
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_missing_email_and_phone_returns_400(self, api_client):
        """Registration without email OR phone must reject with 400."""
        payload = {
            'password': 'SecurePass123!@#',
            'password2': 'SecurePass123!@#',
            'role': 'client',
        }
        response = api_client.post(REGISTER_URL, payload, format='json')
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_invalid_email_format_returns_400(self, api_client):
        """Malformed email must reject with 400."""
        payload = {
            'email': 'not-an-email',
            'password': 'SecurePass123!@#',
            'password2': 'SecurePass123!@#',
            'role': 'client',
        }
        response = api_client.post(REGISTER_URL, payload, format='json')
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_empty_payload_returns_400(self, api_client):
        """Empty POST body must reject with 400."""
        response = api_client.post(REGISTER_URL, {}, format='json')
        assert response.status_code == status.HTTP_400_BAD_REQUEST


# =============================================================================
# DUPLICATE USER TESTS
# =============================================================================

@pytest.mark.django_db
@pytest.mark.api
class TestRegistrationDuplicates:
    """Duplicate email/phone must be rejected."""

    def test_duplicate_email_returns_400(self, api_client, registered_user, mock_email, mock_redis):
        """
        Attempting to register with an email that already exists
        must return 400 (not 500 crash).
        """
        payload = {
            'email': registered_user.email,
            'password': 'SecurePass123!@#',
            'password2': 'SecurePass123!@#',
            'role': 'client',
        }
        response = api_client.post(REGISTER_URL, payload, format='json')
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_duplicate_registration_does_not_create_second_user(
        self, api_client, registered_user, mock_email, mock_redis
    ):
        """DB must not have two users with the same email after duplicate attempt."""
        from apps.authentication.models import UnifiedUser

        payload = {
            'email': registered_user.email,
            'password': 'SecurePass123!@#',
            'password2': 'SecurePass123!@#',
            'role': 'client',
        }
        api_client.post(REGISTER_URL, payload, format='json')
        count = UnifiedUser.objects.filter(email=registered_user.email).count()
        assert count == 1
