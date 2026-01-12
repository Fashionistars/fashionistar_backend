import logging
import httpx
from django.conf import settings

logger = logging.getLogger('application')

class BulkSMSNGProvider:
    """
    Provider implementation for BulkSMS Nigeria.
    Uses httpx for synchronous HTTP requests.
    """
    def __init__(self):
        self.api_token = settings.BULKSMSNG_API_TOKEN
        self.base_url = "https://www.bulksmsnigeria.com/api/v1/sms/create"

    def send_sms(self, to: str, body: str) -> str:
        """
        Sends SMS via BulkSMS Nigeria API using httpx.
        Returns: Message ID or Status string.
        """
        try:
            payload = {
                'api_token': self.api_token,
                'from': "Fashionistar", 
                'to': to,
                'body': body,
                'dnd': 2  # 2 = Direct Route (bypass DND)
            }
            with httpx.Client(timeout=10.0) as client:
                response = client.post(self.base_url, data=payload)
                response.raise_for_status()
            
            logger.info(f"BulkSMSNG Response: {response.text}")
            return response.json().get('data', {}).get('message_id', 'sent')
            
        except Exception as e:
            logger.error(f"BulkSMSNG Error: {e}")
            raise e
