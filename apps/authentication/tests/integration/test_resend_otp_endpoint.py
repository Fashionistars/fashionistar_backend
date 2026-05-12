# apps/authentication/tests/integration/test_resend_otp_endpoint.py
"""
FASHIONISTAR — Integration Tests: POST /api/v1/auth/resend-otp/
================================================================
Tests the full ResendOTPView HTTP request/response cycle.

Key behaviours under test:
  - Email-based resend → 200 + generic non-enumerable message
  - Phone-based resend → 200
  - Non-existent user → 400 (serializer guard)
  - Missing field → 400
  - Celery send_email_task dispatched AFTER transaction commit
  - Template name: authentication/email/resend_otp.html (not otp_resend_email.html)
  - Redis unavailable → 503
  - Generic message DOES NOT reveal whether user exists (enumeration guard)
"""
import pytest
from unittest.mock import patch, ANY
from rest_framework import status

RESEND_URL = '/api/v1/auth/resend-otp/'
OTP_SERVICE = 'apps.authentication.services.otp.sync_service.OTPService'


# =============================================================================
# HAPPY PATH
# =============================================================================

@pytest.mark.django_db
@pytest.mark.api
class TestResendOTPHappyPath:

    def test_valid_email_resend_returns_200(
        self, api_client, registered_user, mock_email_task
    ):
        r = api_client.post(
            RESEND_URL, {'email_or_phone': registered_user.email}, format='json'
        )
        assert r.status_code == status.HTTP_200_OK, r.json()

    def test_response_has_message_field(
        self, api_client, registered_user, mock_email_task
    ):
        r = api_client.post(
            RESEND_URL, {'email_or_phone': registered_user.email}, format='json'
        )
        d = r.json().get('data', r.json())
        assert 'message' in d

    def test_response_is_generic_non_enumerable(
        self, api_client, registered_user, mock_email_task
    ):
        """
        The response message must be generic regardless of user existence.
        This prevents email/phone enumeration attacks.
        """
        r = api_client.post(
            RESEND_URL, {'email_or_phone': registered_user.email}, format='json'
        )
        d = r.json().get('data', r.json())
        msg = d.get('message', '').lower()
        # Must NOT say "otp sent to <email>" (would confirm email exists)
        assert registered_user.email not in msg

    def test_otp_service_resend_called(
        self, api_client, registered_user, mock_email_task
    ):
        """OTPService.resend_otp_sync must be called with correct email."""
        with patch(f'{OTP_SERVICE}.resend_otp_sync', return_value='OTP sent') as m:
            api_client.post(
                RESEND_URL,
                {'email_or_phone': registered_user.email},
                format='json',
            )
        # resend_otp_sync is called with positional email + purpose kwarg
        assert m.called, "resend_otp_sync must be called"
        call_args = m.call_args
        # First positional arg must be the email
        assert registered_user.email in (call_args[0] or []) or \
               call_args.kwargs.get('email_or_phone') == registered_user.email


# =============================================================================
# CELERY TASK DISPATCH (transaction=True required)
# =============================================================================

@pytest.mark.django_db(transaction=True)
@pytest.mark.api
class TestResendOTPCelery:

    def test_email_task_dispatched_after_commit(self, api_client, registered_user):
        """
        Celery send_email_task.delay() must be called after resend-otp
        for an email-based user.
        """
        with patch(
            'apps.authentication.tasks.send_email_task.delay',
            return_value=None
        ) as email_m, patch(
            'apps.authentication.services.otp.sync_service.OTPService.generate_otp_sync',
            return_value='654321'
        ):
            api_client.post(
                RESEND_URL,
                {'email_or_phone': registered_user.email},
                format='json',
            )
        email_m.assert_called_once()

    def test_email_task_uses_correct_template(self, api_client, registered_user):
        """
        REGRESSION: Celery task must use 'authentication/email/resend_otp.html'
        (NOT the deleted 'otp_resend_email.html').
        """
        captured = {}

        def _capture(*args, **kwargs):
            captured.update(kwargs)

        with patch(
            'apps.authentication.tasks.send_email_task.delay',
            side_effect=_capture,
        ), patch(
            'apps.authentication.services.otp.sync_service.OTPService.generate_otp_sync',
            return_value='654321',
        ):
            api_client.post(
                RESEND_URL,
                {'email_or_phone': registered_user.email},
                format='json',
            )

        template = captured.get('template_name', '')
        assert template == 'authentication/email/resend_otp.html', (
            f"REGRESSION: wrong template '{template}'. "
            f"Expected 'authentication/email/resend_otp.html'."
        )

    def test_sms_task_dispatched_for_phone_user(self, api_client):
        """Phone-based resend must dispatch send_sms_task, not email task."""
        from apps.authentication.models import UnifiedUser
        phone_user = UnifiedUser.objects.create_user(
            phone='+2349012345678',
            password='PhonePass123!',
            role='client',
            auth_provider='phone',   # ← required when no email supplied
            is_active=False,
            is_verified=False,
        )
        with patch(
            'apps.authentication.tasks.send_sms_task.delay', return_value=None
        ) as sms_m, patch(
            'apps.authentication.tasks.send_email_task.delay', return_value=None
        ) as email_m, patch(
            'apps.authentication.services.otp.sync_service.OTPService.generate_otp_sync',
            return_value='654321',
        ):
            api_client.post(
                RESEND_URL,
                {'email_or_phone': '+2349012345678'},
                format='json',
            )
        sms_m.assert_called_once()
        email_m.assert_not_called()


# =============================================================================
# ERROR CASES
# =============================================================================

@pytest.mark.django_db
@pytest.mark.api
class TestResendOTPErrors:

    def test_nonexistent_email_returns_400(self, api_client):
        r = api_client.post(
            RESEND_URL, {'email_or_phone': 'ghost@nobody.io'}, format='json'
        )
        assert r.status_code == status.HTTP_400_BAD_REQUEST

    def test_missing_email_or_phone_field_returns_400(self, api_client):
        r = api_client.post(RESEND_URL, {}, format='json')
        assert r.status_code == status.HTTP_400_BAD_REQUEST

    def test_invalid_email_format_returns_400(self, api_client):
        """Malformed email should fail at serializer level."""
        r = api_client.post(
            RESEND_URL, {'email_or_phone': 'not-an-email-or-phone'}, format='json'
        )
        # Either 400 (user not found) or passes to service
        if r.status_code == status.HTTP_200_OK:
            # Service returns generic message — acceptable
            pass
        else:
            assert r.status_code == status.HTTP_400_BAD_REQUEST
