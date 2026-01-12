# apps/common/providers/SMS/termii.py
import httpx
import logging
from django.conf import settings

logger = logging.getLogger('application')

class TermiiSMSProvider:
    """
    SMS provider using Termii API.
    Uses httpx for non-blocking async HTTP calls.
    """

    BASE_URL = "https://api.ng.termii.com/api/sms/send"

    def __init__(self):
        """
        Initialize Termii provider with API key from settings or admin config.
        """
        self.api_key = getattr(settings, 'TERMII_API_KEY', '')
        self.sender_id = getattr(settings, 'TERMII_SENDER_ID', 'Fashionistar')

    def send(self, to: str, body: str) -> str:
        """
        Send SMS synchronously via Termii.

        Args:
            to (str): Recipient phone number.
            body (str): Message body.

        Returns:
            str: Message ID from Termii.

        Raises:
            Exception: If SMS sending fails.
        """
        try:
            payload = {
                'to': to,
                'from': self.sender_id,
                'sms': body,
                'type': 'plain',
                'channel': 'generic',
                'api_key': self.api_key
            }
            
            response = httpx.post(self.BASE_URL, json=payload, timeout=30)
            response.raise_for_status()
            data = response.json()
            
            if data.get('code') == '20' or data.get('status') == 'success':
                message_id = data.get('message_id')
                logger.info(f"SMS sent via Termii to {to}, Message ID: {message_id}")
                return message_id
            else:
                raise Exception(f"Termii API error: {data.get('message', 'Unknown error')}")
        except Exception as e:
            logger.error(f"Error sending SMS via Termii to {to}: {str(e)}")
            raise

    async def asend(self, to: str, body: str) -> str:
        """
        Send SMS asynchronously via Termii.
        Uses httpx.AsyncClient for non-blocking HTTP calls.

        Args:
            to (str): Recipient phone number.
            body (str): Message body.

        Returns:
            str: Message ID from Termii.

        Raises:
            Exception: If SMS sending fails.
        """
        try:
            payload = {
                'to': to,
                'from': self.sender_id,
                'sms': body,
                'type': 'plain',
                'channel': 'generic',
                'api_key': self.api_key
            }
            
            async with httpx.AsyncClient() as client:
                response = await client.post(self.BASE_URL, json=payload, timeout=30)
                response.raise_for_status()
                data = response.json()
                
                if data.get('code') == '20' or data.get('status') == 'success':
                    message_id = data.get('message_id')
                    logger.info(f"SMS sent (async) via Termii to {to}, Message ID: {message_id}")
                    return message_id
                else:
                    raise Exception(f"Termii API error: {data.get('message', 'Unknown error')}")
        except Exception as e:
            logger.error(f"Error sending SMS (async) via Termii to {to}: {str(e)}")
            raise
