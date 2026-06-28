# apps/providers/tests/test_email_providers.py
"""Focused regression tests for email provider registration, resolution, cache-busting, and fallback."""

from __future__ import annotations

import pytest
from django.core.cache import cache
from django.core.mail.backends.smtp import EmailBackend as SmtpEmailBackend
from django.core.mail.backends.console import EmailBackend as ConsoleEmailBackend

from apps.providers.SMTP import (
    BREVO_PROVIDER,
    MAILGUN_PROVIDER,
    ZOHO_PROVIDER,
    get_email_backend_label,
)
from apps.providers.models import EmailProviderConfig
from apps.providers.backends.email_backend import DatabaseConfiguredEmailBackend


def test_email_providers_registry_metadata():
    """Verify that Brevo, Mailgun, and Zoho providers have all required metadata keys."""
    for provider in [BREVO_PROVIDER, MAILGUN_PROVIDER, ZOHO_PROVIDER]:
        assert "slug" in provider
        assert "backend_path" in provider
        assert "display_name" in provider
        assert "health_label" in provider
        assert "settings_prefix" in provider
        assert "help_text" in provider


def test_get_email_backend_label():
    """Verify backend path to label lookup."""
    assert get_email_backend_label("anymail.backends.brevo.EmailBackend") == "Brevo (Sendinblue)"
    assert get_email_backend_label("anymail.backends.mailgun.EmailBackend") == "Mailgun"
    assert (
        get_email_backend_label("zoho_zeptomail.backend.zeptomail_backend.ZohoZeptoMailEmailBackend")
        == "Zoho ZeptoMail"
    )
    assert get_email_backend_label("django.core.mail.backends.console.EmailBackend") == "Console (dev only)"
    assert get_email_backend_label("unknown.backend") == "unknown.backend"


@pytest.mark.django_db
def test_database_configured_email_backend_fallback_when_empty():
    """Verify that when no configuration is present in the database, the backend falls back to standard SMTP."""
    # Ensure cache is clean
    cache.delete("email_provider_config_first")

    backend = DatabaseConfiguredEmailBackend()
    assert isinstance(backend.email_backend, SmtpEmailBackend)


@pytest.mark.django_db
def test_database_configured_email_backend_resolution_and_cache_bust():
    """Verify that the dynamic email backend correctly resolves the database choice and respects cache-busting on save."""
    # Clear cache first
    cache.delete("email_provider_config_first")
    # Delete pre-seeded singletons to guarantee our created instance is the first/only one
    EmailProviderConfig.objects.all().delete()

    # 1. Create a configuration pointing to Console backend
    config = EmailProviderConfig.objects.create(
        email_backend="django.core.mail.backends.console.EmailBackend",
        sender_email="noreply@fashionistar.test",
    )

    backend = DatabaseConfiguredEmailBackend()
    assert isinstance(backend.email_backend, ConsoleEmailBackend)

    # 2. Update backend to SMTP and verify cache bust on save
    config.email_backend = "django.core.mail.backends.smtp.EmailBackend"
    config.save()

    backend_updated = DatabaseConfiguredEmailBackend()
    assert isinstance(backend_updated.email_backend, SmtpEmailBackend)
