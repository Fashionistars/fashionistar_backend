# utilities/managers/sms
import logging
from django.conf import settings

from twilio.rest import Client  # Import the Twilio Client

application_logger = logging.getLogger('application')







class SMSManagerError(Exception):
    """Raise an exception if an error occurs in the SMS manager"""

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
            SMSManagerError: If an error occurs during SMS sending.
        """
        try:
            client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
            message = client.messages.create(
                body=body,
                from_=settings.TWILIO_PHONE_NUMBER,
                to=to
            )
            application_logger.info(f"SMS sent successfully to {to} with SID: {message.sid}")
            return message.sid
        except Exception as error:
            application_logger.error(f"Failed to send SMS to {to}: {error}", exc_info=True)
            raise SMSManagerError(f"Failed to send SMS to {to}: {error}")
