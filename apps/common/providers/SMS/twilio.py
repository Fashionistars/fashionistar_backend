import asyncio
import logging
from twilio.rest import Client
from django.conf import settings

logger = logging.getLogger('application')

class TwilioSMSProvider:
    """
    SMS provider using Twilio.
    Twilio SDK is synchronous, so we wrap it with asyncio.to_thread for async support.
    """

    def __init__(self):
        """
        Initialize Twilio client.
        """
        self.client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
        self.phone_number = settings.TWILIO_PHONE_NUMBER

    def send(self, to: str, body: str) -> str:
        """
        Send SMS synchronously via Twilio.

        Args:
            to (str): Recipient phone number.
            body (str): Message body.

        Returns:
            str: Message SID from Twilio.

        Raises:
            Exception: If SMS sending fails.
        """
        try:
            message = self.client.messages.create(
                body=body,
                from_=self.phone_number,
                to=to
            )
            logger.info(f"SMS sent via Twilio to {to}, SID: {message.sid}")
            return message.sid
        except Exception as e:
            logger.error(f"Error sending SMS via Twilio to {to}: {str(e)}")
            raise

    async def asend(self, to: str, body: str) -> str:
        """
        Send SMS asynchronously via Twilio.
        Wraps the synchronous send method using asyncio.to_thread.

        Args:
            to (str): Recipient phone number.
            body (str): Message body.

        Returns:
            str: Message SID from Twilio.

        Raises:
            Exception: If SMS sending fails.
        """
        try:
            message_sid = await asyncio.to_thread(self.send, to, body)
            logger.info(f"SMS sent (async) via Twilio to {to}")
            return message_sid
        except Exception as e:
            logger.error(f"Error sending SMS (async) via Twilio to {to}: {str(e)}")
            raise
