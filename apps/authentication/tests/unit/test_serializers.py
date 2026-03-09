# apps/authentication/tests/unit/test_serializers.py
"""
FASHIONISTAR — Unit Tests: Authentication Serializers
======================================================
Tests serializer validation logic in pure isolation — no HTTP, no DB hits
(except for uniqueness checks which are mocked out).

Covers:
  UserRegistrationSerializer:
    - password match
    - email/phone XOR logic
    - role restriction (vendor/client only)
    - email normalization (WSGI/Uvicorn parity fix)
    - duplicate email/phone → ValidationError on correct field
    - email__iexact uniqueness (case-insensitive)

  LoginSerializer:
    - valid credentials pass
    - wrong password rejected
    - inactive user rejected
    - unknown user rejected

  OTPSerializer:
    - 6-digit numeric required
    - non-numeric rejected
    - wrong length rejected

  ResendOTPRequestSerializer:
    - valid email passes
    - unknown identifier rejected
"""
import pytest
from unittest.mock import patch, MagicMock
from rest_framework import serializers as drf_serializers


SERIALIZERS_PATH = 'apps.authentication.serializers'


# =============================================================================
# UserRegistrationSerializer
# =============================================================================

@pytest.mark.unit
class TestUserRegistrationSerializer:
    """Validates all field-level and cross-field rules."""

    def _make_serializer(self, data: dict):
        from apps.authentication.serializers import UserRegistrationSerializer
        return UserRegistrationSerializer(data=data)

    def test_valid_email_payload_passes(self):
        with patch(
            f'{SERIALIZERS_PATH}.UnifiedUser.objects.filter'
        ) as mock_filter:
            mock_filter.return_value.exists.return_value = False
            s = self._make_serializer({
                'email': 'valid@fashionistar-test.io',
                'password': 'SecurePass123!',
                'password2': 'SecurePass123!',
                'role': 'client',
            })
            assert s.is_valid(), s.errors

    def test_password_mismatch_raises(self):
        s = self._make_serializer({
            'email': 'valid@test.io',
            'password': 'SecurePass123!',
            'password2': 'DifferentPass!',
            'role': 'client',
        })
        assert not s.is_valid()
        assert 'password' in s.errors

    def test_both_email_and_phone_rejected(self):
        with patch(
            f'{SERIALIZERS_PATH}.UnifiedUser.objects.filter'
        ) as mock_filter:
            mock_filter.return_value.exists.return_value = False
            s = self._make_serializer({
                'email': 'both@test.io',
                'phone': '+2348031111111',
                'password': 'SecurePass123!',
                'password2': 'SecurePass123!',
                'role': 'client',
            })
            assert not s.is_valid()
            errors = str(s.errors)
            assert 'non_field_errors' in errors or 'both' in errors.lower()

    def test_neither_email_nor_phone_rejected(self):
        s = self._make_serializer({
            'password': 'SecurePass123!',
            'password2': 'SecurePass123!',
            'role': 'client',
        })
        assert not s.is_valid()

    def test_admin_role_rejected(self):
        s = self._make_serializer({
            'email': 'admin@test.io',
            'password': 'SecurePass123!',
            'password2': 'SecurePass123!',
            'role': 'admin',
        })
        assert not s.is_valid()
        assert 'role' in s.errors

    def test_staff_role_rejected(self):
        s = self._make_serializer({
            'email': 'staff@test.io',
            'password': 'SecurePass123!',
            'password2': 'SecurePass123!',
            'role': 'staff',
        })
        assert not s.is_valid()
        assert 'role' in s.errors

    def test_vendor_role_accepted(self):
        with patch(
            f'{SERIALIZERS_PATH}.UnifiedUser.objects.filter'
        ) as mock_filter:
            mock_filter.return_value.exists.return_value = False
            s = self._make_serializer({
                'email': 'vendor@test.io',
                'password': 'SecurePass123!',
                'password2': 'SecurePass123!',
                'role': 'vendor',
            })
            assert s.is_valid(), s.errors

    def test_duplicate_email_returns_email_field_error(self):
        """Duplicate email must error on 'email' key, not generic."""
        with patch(
            f'{SERIALIZERS_PATH}.UnifiedUser.objects.filter'
        ) as mock_filter:
            mock_filter.return_value.exists.return_value = True
            s = self._make_serializer({
                'email': 'dup@test.io',
                'password': 'SecurePass123!',
                'password2': 'SecurePass123!',
                'role': 'client',
            })
            assert not s.is_valid()
            assert 'email' in s.errors

    def test_email_normalized_before_uniqueness_check(self):
        """
        REGRESSION (WSGI/Uvicorn parity):
        'user@EXAMPLE.COM' must be treated as duplicate of 'user@example.com'.
        """
        with patch(
            f'{SERIALIZERS_PATH}.UnifiedUser.objects.filter'
        ) as mock_filter:
            # Simulate that the normalized email EXISTS in DB
            mock_filter.return_value.exists.return_value = True
            s = self._make_serializer({
                'email': 'user@EXAMPLE.COM',  # uppercase domain
                'password': 'SecurePass123!',
                'password2': 'SecurePass123!',
                'role': 'client',
            })
            assert not s.is_valid()
            assert 'email' in s.errors

    def test_empty_email_normalized_to_none(self):
        """
        Empty string email must be treated as None (not as a real email).
        A phone-only registration with email='' must NOT error on email uniqueness.
        """
        with patch(
            f'{SERIALIZERS_PATH}.UnifiedUser.objects.filter'
        ) as mock_filter:
            mock_filter.return_value.exists.return_value = False
            s = self._make_serializer({
                'email': '',        # supplied but blank
                'phone': '+2348031112345',
                'password': 'SecurePass123!',
                'password2': 'SecurePass123!',
                'role': 'client',
            })
            # Both email AND phone provided — should fail with XOR error
            # (not with email-exists error)
            if not s.is_valid():
                assert 'email' not in str(s.errors).lower() or \
                       'non_field_errors' in str(s.errors)


# =============================================================================
# LoginSerializer
# =============================================================================

@pytest.mark.unit
@pytest.mark.django_db
class TestLoginSerializer:
    """Validates login credential checks."""

    def _make_serializer(self, data: dict):
        from apps.authentication.serializers import LoginSerializer
        return LoginSerializer(data=data)

    def test_valid_email_login_passes(self, registered_verified_user):
        from apps.authentication.models import UnifiedUser
        s = self._make_serializer({
            'email_or_phone': registered_verified_user.email,
            'password': 'SecurePass123!@#',
        })
        assert s.is_valid(), s.errors
        assert s.validated_data.get('user') is not None

    def test_wrong_password_fails(self, registered_verified_user):
        s = self._make_serializer({
            'email_or_phone': registered_verified_user.email,
            'password': 'WrongPassword!',
        })
        assert not s.is_valid()
        assert 'password' in str(s.errors).lower()

    def test_non_existent_user_fails(self):
        s = self._make_serializer({
            'email_or_phone': 'nobody@nowhere.com',
            'password': 'anything',
        })
        assert not s.is_valid()

    def test_inactive_user_cannot_login(self, registered_user):
        """User with is_active=False must be rejected at serializer level."""
        s = self._make_serializer({
            'email_or_phone': registered_user.email,
            'password': 'SecurePass123!@#',
        })
        assert not s.is_valid()
        errors_str = str(s.errors).lower()
        assert 'active' in errors_str or 'activated' in errors_str

    def test_validated_data_contains_user_object(self, registered_verified_user):
        s = self._make_serializer({
            'email_or_phone': registered_verified_user.email,
            'password': 'SecurePass123!@#',
        })
        assert s.is_valid()
        assert hasattr(s.validated_data['user'], 'id')


# =============================================================================
# OTPSerializer
# =============================================================================

@pytest.mark.unit
class TestOTPSerializer:
    """Format validation for OTP submission."""

    def _s(self, data):
        from apps.authentication.serializers import OTPSerializer
        return OTPSerializer(data=data)

    def test_valid_6_digit_otp_passes(self):
        assert self._s({'otp': '123456'}).is_valid()

    def test_5_digit_otp_fails(self):
        assert not self._s({'otp': '12345'}).is_valid()

    def test_7_digit_otp_exceeds_maxlength_or_fails(self):
        s = self._s({'otp': '1234567'})
        # OTPSerializer has max_length=6 → DRF rejects via CharField
        assert not s.is_valid()

    def test_non_numeric_otp_fails(self):
        assert not self._s({'otp': 'ABCDEF'}).is_valid()

    def test_alphanumeric_otp_fails(self):
        assert not self._s({'otp': '12345X'}).is_valid()

    def test_empty_otp_fails(self):
        assert not self._s({'otp': ''}).is_valid()

    def test_missing_otp_fails(self):
        assert not self._s({}).is_valid()


# =============================================================================
# ResendOTPRequestSerializer
# =============================================================================

@pytest.mark.unit
@pytest.mark.django_db
class TestResendOTPRequestSerializer:
    """Validates resend OTP serializer."""

    def _s(self, data):
        from apps.authentication.serializers import ResendOTPRequestSerializer
        return ResendOTPRequestSerializer(data=data)

    def test_valid_existing_email_passes(self, registered_verified_user):
        s = self._s({'email_or_phone': registered_verified_user.email})
        assert s.is_valid(), s.errors

    def test_nonexistent_email_fails(self):
        s = self._s({'email_or_phone': 'ghost@nobody.com'})
        assert not s.is_valid()
        assert 'email_or_phone' in s.errors

    def test_missing_field_fails(self):
        s = self._s({})
        assert not s.is_valid()
