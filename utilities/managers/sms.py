# utilities/managers/sms
import logging
from django.conf import settings

from twilio.rest import Client  # Import the Twilio Client
from twilio.base.exceptions import TwilioRestException

application_logger = logging.getLogger('application')


class SMSManagerError(Exception):
    """Base exception if an error occurs in the SMS manager"""

class SMSClientError(SMSManagerError):
    """Raised when the provider rejects the request (e.g. 400 Bad Request, unverified number). Should NOT be retried."""

class SMSServerError(SMSManagerError):
    """Raised when the provider has an internal server error (e.g. 500). Should be retried."""


class SMSManager:
    """
    Manages the sending of SMS messages using Twilio.
    """

    @classmethod
    def send_sms(cls, to: str, body: str) -> str:
        """
        Sends an SMS using Twilio.

        Args:
            to (str): Recipient's phone number (in E.164 format).
            body (str): SMS message body.

        Returns:
            str: Message SID (string).

        Raises:
            SMSClientError: If a client-side (400) error occurs.
            SMSServerError: If a server-side (5xx) error occurs.
            SMSManagerError: If any other unexpected error occurs.
        """
        try:
            client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
            message = client.messages.create(
                body=body,
                from_=settings.TWILIO_PHONE_NUMBER,
                to=to
            )
            application_logger.info(f"✅ SMS sent successfully to {to} with SID: {message.sid}")
            return message.sid

        except TwilioRestException as error:
            # Catch 4xx errors (e.g. Unverified Number, Invalid format) cleanly
            if 400 <= error.status < 500:
                clean_msg = f"Twilio rejected SMS to {to}. Reason: {error.msg}"
                application_logger.warning(f"🚫 {clean_msg}")
                raise SMSClientError(clean_msg)
            else:
                application_logger.error(f"❌ Twilio Server Error delivering to {to}: {error.msg}", exc_info=True)
                raise SMSServerError(f"Provider error: {error.msg}")

        except Exception as error:
            application_logger.error(f"❌ Unexpected error sending SMS to {to}: {error}", exc_info=True)
            raise SMSManagerError(f"Failed to send SMS to {to}: {error}")
