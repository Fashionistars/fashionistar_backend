import httpx
import logging
from django.conf import settings

logger = logging.getLogger('application')

class BulksmsNGSMSProvider:
    """
    SMS provider using BulkSMS Nigeria API.
    Uses httpx for non-blocking async HTTP calls.
    """

    BASE_URL = "https://www.bulksmsnigeria.com/api/v1/sms/create"

    def __init__(self):
        """
        Initialize BulkSMS NG provider with API credentials from settings.
        """
        self.api_token = getattr(settings, 'BULKSMS_NG_API_TOKEN', '')
        self.sender_id = getattr(settings, 'BULKSMS_NG_SENDER_ID', 'Fashionistar')

    def send(self, to: str, body: str) -> str:
        """
        Send SMS synchronously via BulkSMS Nigeria.

        Args:
            to (str): Recipient phone number.
            body (str): Message body.

        Returns:
            str: Message ID from BulkSMS NG.

        Raises:
            Exception: If SMS sending fails.
        """
        try:
            payload = {
                'api_token': self.api_token,
                'to': to,
                'from': self.sender_id,
                'body': body,
                'dnd': 1  # Skip DND (Do Not Disturb) numbers
            }
            
            response = httpx.post(self.BASE_URL, json=payload, timeout=30)
            # Raise error for bad status codes (4xx/5xx)
            response.raise_for_status()
            data = response.json()
            
            if data.get('status') == 'success':
                message_id = data.get('data', {}).get('id')
                logger.info(f"SMS sent via BulkSMS NG to {to}, Message ID: {message_id}")
                return str(message_id)
            else:
                error_msg = data.get('message', 'Unknown error')
                raise Exception(f"BulkSMS NG API error: {error_msg}")
        except Exception as e:
            logger.error(f"Error sending SMS via BulkSMS NG to {to}: {str(e)}")
            raise

    async def asend(self, to: str, body: str) -> str:
        """
        Send SMS asynchronously via BulkSMS Nigeria.
        Uses httpx.AsyncClient for non-blocking HTTP calls.

        Args:
            to (str): Recipient phone number.
            body (str): Message body.

        Returns:
            str: Message ID from BulkSMS NG.

        Raises:
            Exception: If SMS sending fails.
        """
        try:
            payload = {
                'api_token': self.api_token,
                'to': to,
                'from': self.sender_id,
                'body': body,
                'dnd': 1  # Skip DND (Do Not Disturb) numbers
            }
            
            async with httpx.AsyncClient() as client:
                response = await client.post(self.BASE_URL, json=payload, timeout=30)
                response.raise_for_status()
                data = response.json()
                
                if data.get('status') == 'success':
                    message_id = data.get('data', {}).get('id')
                    logger.info(f"SMS sent (async) via BulkSMS NG to {to}, Message ID: {message_id}")
                    return str(message_id)
                else:
                    error_msg = data.get('message', 'Unknown error')
                    raise Exception(f"BulkSMS NG API error: {error_msg}")
        except Exception as e:
            logger.error(f"Error sending SMS (async) via BulkSMS NG to {to}: {str(e)}")
            raise
