# apps/common/tests/conftest.py
"""
apps.common — Test fixtures
============================
Fixtures for testing:
  - BaseSelector (ORM read helpers)
  - Middleware (RequestID, Timing, SecurityAudit)
  - Custom permissions
  - Throttling classes
  - Renderers (FashionistarRenderer)
  - Custom exceptions / exception handler
  - Email manager
  - SMS manager
"""
import pytest
from unittest.mock import MagicMock, patch


@pytest.fixture
def mock_request(rf):
    """
    A fake Django request with all headers the middleware expects.
    `rf` is pytest-django's RequestFactory fixture.
    """
    request = rf.get('/', HTTP_X_REQUEST_ID='test-req-id-001')
    request.META['HTTP_X_FORWARDED_FOR'] = '192.168.1.100'
    request.META['HTTP_USER_AGENT'] = 'pytest-test-agent/1.0'
    return request


@pytest.fixture
def mock_email_backend(settings):
    """Override email backend to console for all common tests."""
    settings.EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'
    return settings


@pytest.fixture
def mock_sms_client():
    """
    Mock the SMS provider client so tests never hit Twilio/Termii/BulkSMS.
    """
    with patch('apps.common.managers.sms.SMSManager.send') as mock_send:
        mock_send.return_value = {'status': 'success', 'message': 'sent'}
        yield mock_send


@pytest.fixture
def mock_email_manager():
    """
    Mock the email manager send so tests never hit SMTP.
    """
    with patch('apps.common.managers.email.EmailManager.send') as mock_send:
        mock_send.return_value = True
        yield mock_send


@pytest.fixture
def django_request_factory(rf):
    """Alias for pytest-django RequestFactory."""
    return rf
