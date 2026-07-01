# apps/providers/tests/test_sms_providers.py
"""Focused regression tests for SMS provider registration, resolution, cache-busting, and Kudi SMS."""

from __future__ import annotations

from unittest.mock import MagicMock, patch
import pytest
from django.core.cache import cache

from apps.providers.SMS import (
    SMS_BACKEND_CHOICES,
    get_sms_provider_label,
)
from apps.providers.SMS.kudi import KudiSMSProvider
from apps.providers.models import SMSProviderConfig
from apps.providers.backends.sms_backend import DatabaseConfiguredSMSBackend
from apps.common.http import ProviderSyncHTTPClient


def test_sms_providers_registry_metadata():
    """Verify that Termii, Twilio, BulkSMS NG, and Kudi SMS choices are present."""
    choices_dict = dict(SMS_BACKEND_CHOICES)
    assert "apps.providers.SMS.termii.TermiiSMSProvider" in choices_dict
    assert "apps.providers.SMS.twilio.TwilioSMSProvider" in choices_dict
    assert "apps.providers.SMS.bulksmsNG.BulksmsNGSMSProvider" in choices_dict
    assert "apps.providers.SMS.kudi.KudiSMSProvider" in choices_dict


def test_get_sms_provider_label():
    """Verify backend path to label lookup."""
    assert get_sms_provider_label("apps.providers.SMS.kudi.KudiSMSProvider") == "Kudi SMS"
    assert get_sms_provider_label("apps.providers.SMS.twilio.TwilioSMSProvider") == "Twilio (Global / WhatsApp)"
    assert get_sms_provider_label("unknown.backend") == "unknown.backend"


@pytest.mark.django_db
def test_database_configured_sms_backend_fallback_when_empty():
    """Verify that when no configuration is present in the database, the backend falls back to Twilio."""
    cache.delete("sms_provider_config_first")

    backend = DatabaseConfiguredSMSBackend()
    assert backend.sms_provider.__class__.__name__ == "TwilioSMSProvider"


@pytest.mark.django_db
def test_database_configured_sms_backend_resolution_and_cache_bust():
    """Verify that the dynamic SMS backend correctly resolves the database choice and respects cache-busting on save."""
    cache.delete("sms_provider_config_first")
    SMSProviderConfig.objects.all().delete()

    # 1. Create a configuration pointing to Kudi
    config = SMSProviderConfig.objects.create(
        sms_backend="apps.providers.SMS.kudi.KudiSMSProvider",
        api_key="kudi-api-key",
        sender_id="fashionistar",
    )

    backend = DatabaseConfiguredSMSBackend()
    assert backend.sms_provider.__class__.__name__ == "KudiSMSProvider"

    # 2. Update backend to Termii and verify cache bust on save
    config.sms_backend = "apps.providers.SMS.termii.TermiiSMSProvider"
    config.save()

    backend_updated = DatabaseConfiguredSMSBackend()
    assert backend_updated.sms_provider.__class__.__name__ == "TermiiSMSProvider"


@pytest.mark.django_db
@patch("httpx.Client.request")
def test_kudi_sms_provider_success(mock_request):
    """Test successful message sending via Kudi SMS."""
    # Mock httpx response
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.is_error = False
    mock_response.json.return_value = {
        "status": "success",
        "error_code": "000",
        "cost": "5.60",
        "data": [
            "234703xxxxx|fd2913aa-4db0-24ec-8fc7-f46cd397153c"
        ],
        "msg": "Message received Successfully",
    }
    mock_request.return_value = mock_response

    provider = KudiSMSProvider()
    msg_id = provider.send(to="+2347031234567", body="Test message")
    
    assert msg_id == "234703xxxxx|fd2913aa-4db0-24ec-8fc7-f46cd397153c"
    
    # Assert correct parameters were sent
    called_args, called_kwargs = mock_request.call_args
    assert called_args[0] == "POST"
    assert called_args[1] == "/api/sms"
    
    sent_json = called_kwargs.get("json", {})
    assert sent_json["recipients"] == "2347031234567"
    assert sent_json["message"] == "Test message"
    assert sent_json["gateway"] == "2"


@pytest.mark.django_db
@patch("httpx.Client.request")
def test_kudi_sms_provider_failure(mock_request):
    """Test API error handling when Kudi SMS returns error status."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.is_error = False
    mock_response.json.return_value = {
        "status": "error",
        "error_code": "100",
        "msg": "Token provided is invalid.",
    }
    mock_request.return_value = mock_response

    provider = KudiSMSProvider()
    with pytest.raises(RuntimeError) as exc_info:
        provider.send(to="+2347031234567", body="Test message")
    
    assert "Token provided is invalid" in str(exc_info.value)
