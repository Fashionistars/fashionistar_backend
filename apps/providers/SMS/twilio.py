# apps/providers/SMS/twilio.py
"""
Twilio SMS provider — Global carrier with the strongest delivery guarantees.

Required Django settings:
    TWILIO_ACCOUNT_SID = env("TWILIO_ACCOUNT_SID")
    TWILIO_AUTH_TOKEN  = env("TWILIO_AUTH_TOKEN")
    TWILIO_PHONE_NUMBER = env("TWILIO_PHONE_NUMBER")

Twilio docs: https://www.twilio.com/docs/sms/api
"""
import asyncio
import logging

from django.conf import settings

logger = logging.getLogger("application")


class TwilioSMSProvider:
    """
    SMS provider using Twilio.
    Twilio SDK is synchronous; asend() wraps it via asyncio.to_thread.
    """

    def __init__(self, config=None) -> None:
        from twilio.rest import Client  # lazy import to avoid startup failure if not installed

        account_sid = getattr(config, "api_key", "") or settings.TWILIO_ACCOUNT_SID
        auth_token = getattr(config, "api_secret", "") or settings.TWILIO_AUTH_TOKEN
        self.phone_number = getattr(config, "sender_id", "") or settings.TWILIO_PHONE_NUMBER
        self.client = Client(account_sid, auth_token)

    def send(self, to: str, body: str) -> str:
        try:
            message = self.client.messages.create(body=body, from_=self.phone_number, to=to)
            logger.info("SMS sent via Twilio to %s, SID: %s", to, message.sid)
            return message.sid
        except Exception as exc:
            logger.error("Error sending SMS via Twilio to %s: %s", to, exc)
            raise

    async def asend(self, to: str, body: str) -> str:
        try:
            sid = await asyncio.to_thread(self.send, to, body)
            logger.info("SMS sent (async) via Twilio to %s", to)
            return sid
        except Exception as exc:
            logger.error("Error sending SMS (async) via Twilio to %s: %s", to, exc)
            raise
