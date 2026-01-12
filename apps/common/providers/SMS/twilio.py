import logging
from django.conf import settings
from twilio.rest import Client

logger = logging.getLogger('application')

class TwilioSMSProvider:
    """
    Provider implementation for Twilio.
    Strictly handles synchronous requests via Twilio SDK.
    """
    def __init__(self):
        self.account_sid = settings.TWILIO_ACCOUNT_SID
        self.auth_token = settings.TWILIO_AUTH_TOKEN
        self.from_number = settings.TWILIO_PHONE_NUMBER
        self.client = Client(self.account_sid, self.auth_token)

    def send_sms(self, to: str, body: str) -> str:
        """
        Sends SMS via Twilio SDK.
        """
        try:
            message = self.client.messages.create(
                body=body,
                from_=self.from_number,
                to=to
            )
            logger.info(f"Twilio SMS sent SID: {message.sid}")
            return message.sid
            
        except Exception as e:
            logger.error(f"Twilio Error: {e}")
            raise e
