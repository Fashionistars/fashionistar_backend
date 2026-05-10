# apps/authentication/tests/test_registration.py
"""
Synchronous Registration Tests — Updated for All 7 Bug Fixes

Covers:
  - Happy path: email registration → 201
  - Happy path: phone registration → 201
  - Regression: second phone-only user → 201 (was failing with email-exists error)
  - User created with is_active=False, is_verified=False
  - Duplicate email → 400 email field error (not 500)
  - Duplicate phone → 400 phone field error (NOT email error)
  - Race-condition duplicate (model-level ValidationError) → 400
  - Weak password → 400
  - Password mismatch → 400
  - Missing email AND phone → 400
  - Both email AND phone → 400
  - Invalid email format → 400
  - Empty payload → 400
  - Admin role rejected → 400 (only vendor/client allowed)
  - Missing role → 400
  - Missing password → 400
  - Celery email task dispatched after email registration
  - Celery SMS task dispatched after phone registration (NOT email task)
  - SITE_URL in email task context
  - Vendor role saved correctly
  - Multipart form submission works

NOTE on transaction.on_commit() + mocking:
  Celery tasks are dispatched via transaction.on_commit() so the mock must
  patch the task's .delay method at module import level. Since Django's
  TestCase wraps each test in a transaction that never commits, on_commit()
  callbacks never fire in standard @pytest.mark.django_db tests.
  We use @pytest.mark.django_db(transaction=True) for tests that assert
  on Celery dispatch, and mock the task at the service module level.
"""
import pytest
from unittest.mock import patch, ANY, call
from rest_framework import status

REGISTER_URL = '/api/v1/auth/register/'


# =============================================================================
# LOCAL FIXTURES
# =============================================================================

@pytest.fixture
def mock_email_task():
    """
    Patch send_email_task.delay at the tasks module level.
    Works with transaction.on_commit() when used with transaction=True DB.
    """
    with patch('apps.authentication.tasks.send_email_task.delay',
               return_value=None) as m:
        yield m


@pytest.fixture
def mock_sms_task():
    """Patch send_sms_task.delay at the tasks module level."""
    with patch('apps.authentication.tasks.send_sms_task.delay',
               return_value=None) as m:
        yield m


@pytest.fixture
def mock_both_tasks(mock_email_task, mock_sms_task):
    """Convenience fixture: patch both email + SMS tasks."""
    return mock_email_task, mock_sms_task


# =============================================================================
# HAPPY PATH TESTS
# =============================================================================

@pytest.mark.django_db
@pytest.mark.api
class TestHappyPath:

    def test_email_registration_201(self, api_client, mock_email_task):
        r = api_client.post(REGISTER_URL, {
            'email': 'happy_email@test.io',
            'password': 'SecurePass123!',
            'password2': 'SecurePass123!',
            'role': 'client',
        }, format='json')
        assert r.status_code == status.HTTP_201_CREATED, r.json()
        d = r.json().get('data', r.json())  # response may be {success, data:{...}} or flat
        assert d.get('email') == 'happy_email@test.io'
        assert d.get('phone') is None

    def test_phone_registration_201(self, api_client, mock_sms_task):
        """Phone-only registration must return 201 (not email-exists 400)."""
        r = api_client.post(REGISTER_URL, {
            'phone': '+2348031111111',
            'password': 'SecurePass123!',
            'password2': 'SecurePass123!',
            'role': 'vendor',
        }, format='json')
        assert r.status_code == status.HTTP_201_CREATED, r.json()
        d = r.json()
        assert d.get('data', {}).get('email') is None
        assert d.get('data', {}).get('phone') is not None

    def test_second_phone_user_201_regression(self, api_client, mock_sms_task):
        """
        BUG-1 REGRESSION: A second phone-only user must also get 201.
        Previously: second phone registration returned 400
        {'email': 'Unified User with this Email address already exists.'}
        because AbstractUser.clean() converted email=None → ''.
        """
        # First phone user
        r1 = api_client.post(REGISTER_URL, {
            'phone': '+2348031112222',
            'password': 'SecurePass123!',
            'password2': 'SecurePass123!',
            'role': 'vendor',
        }, format='json')
        assert r1.status_code == status.HTTP_201_CREATED, r1.json()

        # Second phone user must ALSO succeed, not get email-exists error
        r2 = api_client.post(REGISTER_URL, {
            'phone': '+2348031113333',
            'password': 'SecurePass123!',
            'password2': 'SecurePass123!',
            'role': 'client',
        }, format='json')
        assert r2.status_code == status.HTTP_201_CREATED, (
            f"BUG-1 REGRESSION: second phone user returned {r2.status_code} "
            f"with errors={r2.json().get('errors')}. "
            f"Expected 201. Root cause: AbstractUser.clean() → normalize_email(None) → ''"
        )

    def test_new_user_is_inactive_and_unverified(self, api_client, mock_email_task):
        from apps.authentication.models import UnifiedUser
        api_client.post(REGISTER_URL, {
            'email': 'inactive_check@test.io',
            'password': 'SecurePass123!',
            'password2': 'SecurePass123!',
            'role': 'client',
        }, format='json')
        u = UnifiedUser.objects.get(email='inactive_check@test.io')
        assert u.is_active is False
        assert u.is_verified is False

    def test_vendor_role_saved(self, api_client, mock_email_task):
        from apps.authentication.models import UnifiedUser
        api_client.post(REGISTER_URL, {
            'email': 'vendor_role@test.io',
            'password': 'SecurePass123!',
            'password2': 'SecurePass123!',
            'role': 'vendor',
        }, format='json')
        u = UnifiedUser.objects.get(email='vendor_role@test.io')
        assert u.role == 'vendor'

    def test_multipart_form_201(self, api_client, mock_email_task):
        r = api_client.post(REGISTER_URL, {
            'email': 'multipart@test.io',
            'password': 'SecurePass123!',
            'password2': 'SecurePass123!',
            'role': 'client',
        }, format='multipart')
        assert r.status_code == status.HTTP_201_CREATED, r.json()


# =============================================================================
# VALIDATION FAILURE TESTS
# =============================================================================

@pytest.mark.django_db
@pytest.mark.api
class TestValidationErrors:

    def test_password_mismatch_400(self, api_client):
        r = api_client.post(REGISTER_URL, {
            'email': 'mismatch@test.io',
            'password': 'SecurePass123!',
            'password2': 'DifferentPass99!',
            'role': 'client',
        }, format='json')
        assert r.status_code == status.HTTP_400_BAD_REQUEST

    def test_weak_password_400(self, api_client):
        r = api_client.post(REGISTER_URL, {
            'email': 'weakpw@test.io',
            'password': '123',
            'password2': '123',
            'role': 'client',
        }, format='json')
        assert r.status_code == status.HTTP_400_BAD_REQUEST

    def test_missing_email_and_phone_400(self, api_client):
        r = api_client.post(REGISTER_URL, {
            'password': 'SecurePass123!',
            'password2': 'SecurePass123!',
            'role': 'client',
        }, format='json')
        assert r.status_code == status.HTTP_400_BAD_REQUEST

    def test_both_email_and_phone_400(self, api_client, mock_both_tasks):
        """Providing both email AND phone must be rejected."""
        r = api_client.post(REGISTER_URL, {
            'email': 'both@test.io',
            'phone': '+2348031114444',
            'password': 'SecurePass123!',
            'password2': 'SecurePass123!',
            'role': 'client',
        }, format='json')
        assert r.status_code == status.HTTP_400_BAD_REQUEST

    def test_invalid_email_format_400(self, api_client):
        r = api_client.post(REGISTER_URL, {
            'email': 'not-an-email',
            'password': 'SecurePass123!',
            'password2': 'SecurePass123!',
            'role': 'client',
        }, format='json')
        assert r.status_code == status.HTTP_400_BAD_REQUEST

    def test_empty_payload_400(self, api_client):
        r = api_client.post(REGISTER_URL, {}, format='json')
        assert r.status_code == status.HTTP_400_BAD_REQUEST

    def test_admin_role_rejected_400(self, api_client):
        """BUG-6: Admin role must be rejected from public endpoint."""
        r = api_client.post(REGISTER_URL, {
            'email': 'admin_attempt@test.io',
            'password': 'SecurePass123!',
            'password2': 'SecurePass123!',
            'role': 'admin',
        }, format='json')
        assert r.status_code == status.HTTP_400_BAD_REQUEST
        d = r.json()
        errors = str(d.get('errors', d))
        assert 'role' in errors.lower() or 'valid choice' in errors.lower()

    def test_missing_role_400(self, api_client):
        r = api_client.post(REGISTER_URL, {
            'email': 'norole@test.io',
            'password': 'SecurePass123!',
            'password2': 'SecurePass123!',
        }, format='json')
        assert r.status_code == status.HTTP_400_BAD_REQUEST

    def test_missing_password_400(self, api_client):
        r = api_client.post(REGISTER_URL, {
            'email': 'nopwd@test.io',
            'role': 'client',
        }, format='json')
        assert r.status_code == status.HTTP_400_BAD_REQUEST


# =============================================================================
# DUPLICATE TESTS — BUG-1 fix coverage
# =============================================================================

@pytest.mark.django_db
@pytest.mark.api
class TestDuplicates:

    def test_duplicate_email_returns_400_not_500(
        self, api_client, registered_user, mock_email_task
    ):
        """Duplicate email must return 400, NOT 500."""
        r = api_client.post(REGISTER_URL, {
            'email': registered_user.email,
            'password': 'SecurePass123!',
            'password2': 'SecurePass123!',
            'role': 'client',
        }, format='json')
        assert r.status_code == status.HTTP_400_BAD_REQUEST, (
            f"Duplicate email returned {r.status_code}. Body={r.json()}"
        )
        assert r.status_code != status.HTTP_500_INTERNAL_SERVER_ERROR

    def test_duplicate_email_error_is_field_specific(
        self, api_client, registered_user, mock_email_task
    ):
        """Duplicate email error must be on 'email' key, not a generic message."""
        r = api_client.post(REGISTER_URL, {
            'email': registered_user.email,
            'password': 'SecurePass123!',
            'password2': 'SecurePass123!',
            'role': 'client',
        }, format='json')
        errors_str = str(r.json().get('errors', r.json()))
        assert 'email' in errors_str.lower()

    def test_duplicate_phone_returns_400_with_phone_error(self, api_client, mock_sms_task):
        """
        BUG-1 CRITICAL: Duplicate phone must return 400 with 'phone' field error,
        NOT 'email already exists' error.
        """
        from apps.authentication.models import UnifiedUser
        UnifiedUser.objects.create_user(
            phone='+2348099990000',
            password='ExistPass123!',
            role='client',
            auth_provider='phone',
            is_active=False,
            is_verified=False,
        )
        r = api_client.post(REGISTER_URL, {
            'phone': '+2348099990000',
            'password': 'SecurePass123!',
            'password2': 'SecurePass123!',
            'role': 'client',
        }, format='json')
        assert r.status_code == status.HTTP_400_BAD_REQUEST, r.json()
        errors = r.json().get('errors', {})
        # Must say 'phone' not 'email'
        assert 'phone' in errors, (
            f"BUG-1 REGRESSION: duplicate phone returned errors on wrong field: {errors}. "
            f"Expected {{'phone': [...]}}, got {errors}"
        )
        assert 'email' not in errors, (
            f"BUG-1 REGRESSION: duplicate phone returned EMAIL error instead of phone: {errors}"
        )

    def test_duplicate_phone_no_second_user_created(self, api_client, mock_sms_task):
        """DB must have exactly 1 user after failed duplicate phone attempt."""
        from apps.authentication.models import UnifiedUser
        UnifiedUser.objects.create_user(
            phone='+2348099991111',
            password='ExistPass123!',
            role='client',
            auth_provider='phone',
            is_active=False,
            is_verified=False,
        )
        api_client.post(REGISTER_URL, {
            'phone': '+2348099991111',
            'password': 'SecurePass123!',
            'password2': 'SecurePass123!',
            'role': 'client',
        }, format='json')
        assert UnifiedUser.objects.filter(phone='+2348099991111').count() == 1

    def test_race_condition_returns_400(self, api_client, mock_email_task):
        """
        Simulate DB-level race condition (uniqueness passes serializer but
        fails in model.full_clean()). Must return 400, not 500.
        """
        from django.core.exceptions import ValidationError as DjangoVE
        with patch(
            'apps.authentication.models.UnifiedUser.objects.create_user',
            side_effect=DjangoVE({'email': ['Already exists.']})
        ):
            r = api_client.post(REGISTER_URL, {
                'email': 'race@test.io',
                'password': 'SecurePass123!',
                'password2': 'SecurePass123!',
                'role': 'client',
            }, format='json')
        assert r.status_code == status.HTTP_400_BAD_REQUEST, (
            f"Race-condition ValidationError should map to 400, got {r.status_code}"
        )


# =============================================================================
# CELERY TASK DISPATCH TESTS
# (transaction=True required: on_commit() fires only on real commit)
# =============================================================================

@pytest.mark.django_db(transaction=True)
@pytest.mark.api
class TestCeleryDispatch:

    def test_email_task_dispatched_for_email_registration(self, api_client):
        """send_email_task.delay() must be called after email registration."""
        with patch('apps.authentication.tasks.send_email_task.delay',
                   return_value=None) as m:
            api_client.post(REGISTER_URL, {
                'email': 'celery_email@test.io',
                'password': 'SecurePass123!',
                'password2': 'SecurePass123!',
                'role': 'client',
            }, format='json')
            m.assert_called_once()

    def test_sms_task_dispatched_for_phone_registration(self, api_client):
        """send_sms_task.delay() (NOT email) must be called for phone registration."""
        with patch('apps.authentication.tasks.send_email_task.delay',
                   return_value=None) as email_m, \
             patch('apps.authentication.tasks.send_sms_task.delay',
                   return_value=None) as sms_m:
            api_client.post(REGISTER_URL, {
                'phone': '+2348031115555',
                'password': 'SecurePass123!',
                'password2': 'SecurePass123!',
                'role': 'client',
            }, format='json')
            email_m.assert_not_called()
            sms_m.assert_called_once()

    def test_email_task_context_has_site_url(self, api_client):
        """SITE_URL must be in email task context (template CTA fix)."""
        with patch('apps.authentication.tasks.send_email_task.delay',
                   return_value=None) as m:
            api_client.post(REGISTER_URL, {
                'email': 'siteurl@test.io',
                'password': 'SecurePass123!',
                'password2': 'SecurePass123!',
                'role': 'client',
            }, format='json')
        m.assert_called_once()
        _, kwargs = m.call_args
        assert 'SITE_URL' in kwargs.get('context', {}), (
            "SITE_URL missing from Celery email context"
        )

    def test_no_task_dispatched_on_failed_registration(self, api_client):
        """On 400 validation failure, NO Celery task must be queued."""
        with patch('apps.authentication.tasks.send_email_task.delay',
                   return_value=None) as email_m, \
             patch('apps.authentication.tasks.send_sms_task.delay',
                   return_value=None) as sms_m:
            api_client.post(REGISTER_URL, {
                'email': 'invalid-email',   # invalid — will fail
                'password': 'SecurePass123!',
                'password2': 'SecurePass123!',
                'role': 'client',
            }, format='json')
        email_m.assert_not_called()
        sms_m.assert_not_called()
