import logging
import httpx
from django.conf import settings

logger = logging.getLogger('application')

class TermiiSMSProvider:
    """
    Provider implementation for Termii.
    Uses httpx for synchronous HTTP requests.
    """
    def __init__(self):
        self.api_key = settings.TERMII_API_KEY
        self.base_url = "https://api.ng.termii.com/api/sms/send"

    def send_sms(self, to: str, body: str) -> str:
        """
        Sends SMS via Termii API using httpx.
        """
        try:
            payload = {
                "to": to,
                "from": "Fashionistar",
                "sms": body,
                "type": "plain",
                "channel": "generic", # or "dnd"
                "api_key": self.api_key,
            }
            headers = {
                'Content-Type': 'application/json',
            }
            
            with httpx.Client(timeout=10.0) as client:
                response = client.post(self.base_url, json=payload, headers=headers)
                response.raise_for_status()
            
            logger.info(f"Termii Response: {response.text}")
            return response.json().get('message_id', 'sent')
            
        except Exception as e:
            logger.error(f"Termii Error: {e}")
            raise e
