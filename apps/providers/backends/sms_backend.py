# apps/providers/backends/sms_backend.py
"""
DatabaseConfiguredSMSBackend — production Django SMS backend.

Reads the active SMS provider path from SMSProviderConfig (providers registry)
and delegates every SMS dispatch to the resolved provider class.

Supported provider paths:
  apps.providers.SMS.twilio.TwilioSMSProvider
  apps.providers.SMS.termii.TermiiSMSProvider
  apps.providers.SMS.bulksmsNG.BulksmsNGSMSProvider

Fallback: Twilio (most reliable global carrier).
"""
from __future__ import annotations

import logging
from django.utils.module_loading import import_string

from apps.providers.cache import get_sms_provider_config

application_logger = logging.getLogger("application")

_FALLBACK_PATH = "apps.providers.SMS.twilio.TwilioSMSProvider"


class DatabaseConfiguredSMSBackend:
    """
    Dynamic SMS backend loader / strategy executor.

    Reads provider path from SMSProviderConfig → Redis cache → DB.
    Falls back to Twilio on any failure.
    """

    def __init__(self, *args, **kwargs):
        self.sms_provider = self._load_provider()

    def _load_provider(self):
        provider_path = _FALLBACK_PATH
        try:
            config = get_sms_provider_config()
            if config and config.sms_backend:
                provider_path = config.sms_backend
            else:
                application_logger.warning(
                    "SMSBackend: no SMSProviderConfig found — using default Twilio."
                )

            application_logger.info("SMSBackend: loading provider=%s", provider_path)
            provider_class = import_string(provider_path)
            instance = provider_class(config=config)
            application_logger.info(
                "SMSBackend: ✅ initialized %s", provider_class.__name__
            )
            return instance

        except ImportError as exc:
            application_logger.error(
                "SMSBackend: ImportError loading %s — %s", provider_path, exc, exc_info=True
            )
        except Exception as exc:
            application_logger.error(
                "SMSBackend: unexpected error — %s", exc, exc_info=True
            )

        # Fallback
        application_logger.warning("SMSBackend: falling back to Twilio provider.")
        from apps.providers.SMS.twilio import TwilioSMSProvider
        return TwilioSMSProvider()

    def send_messages(self, sms_messages: list) -> list:
        """
        Send a batch of SMS messages.

        Each item must have 'to' (str) and 'body' (str).
        Returns a list of results; per-message errors do not abort the batch.
        """
        results = []
        for message in sms_messages:
            to = message.get("to")
            body = message.get("body")
            if not to or not body:
                application_logger.warning(
                    "SMSBackend: skipping invalid payload: %s", message
                )
                results.append({"status": "failed", "reason": "invalid_payload"})
                continue
            try:
                result = self.sms_provider.send(to, body)
                results.append(result)
                application_logger.info(
                    "SMSBackend: sent to %s via %s", to, self.sms_provider.__class__.__name__
                )
            except Exception as exc:
                application_logger.error("SMSBackend: error sending to %s — %s", to, exc)
                results.append({"status": "failed", "reason": str(exc)})
        return results
