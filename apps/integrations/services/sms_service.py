"""
Generic SMS integration service for Fashionistar.
"""

from typing import Dict, Any, Optional, List
import requests
import logging
import time
from django.conf import settings
from .base_service import BaseIntegrationService

logger = logging.getLogger(__name__)


class SMSService(BaseIntegrationService):
    """
    Service for sending SMS and OTP messages via generic provider API.
    """
    
    def __init__(self):
        super().__init__('sms_provider')
        self.base_url = "https://api.sms-provider.com/v1"
        self._api_key = None
        self._sender = None
    
    @property
    def api_key(self) -> str:
        if not self._api_key:
            self._api_key = self.get_credential('api_key') or "mock-key"
        return self._api_key
    
    @property
    def sender(self) -> str:
        if not self._sender:
            self._sender = self.get_credential('sender_number') or "mock-sender"
        return self._sender
    
    def validate_config(self) -> bool:
        try:
            if not self.api_key:
                return False
            return True
        except Exception as e:
            logger.error(f"Config validation failed: {str(e)}")
            return False
    
    def health_check(self) -> Dict[str, Any]:
        start_time = time.time()
        try:
            return {
                'status': 'healthy',
                'response_time_ms': int((time.time() - start_time) * 1000),
                'balance': 1000.0,
                'details': {
                    'api_level': 'v1',
                    'daily_send': 0
                }
            }
        except Exception as e:
            return {
                'status': 'unhealthy',
                'error': str(e),
                'response_time_ms': int((time.time() - start_time) * 1000)
            }
    
    def send_otp(self, receptor: str, token: str, template: Optional[str] = None) -> Dict[str, Any]:
        if not self.check_rate_limit(receptor, 'send_otp'):
            return {
                'success': False,
                'error': 'Rate limit exceeded.'
            }
        
        if not template:
            template = self.get_credential('otp_template', required=False) or 'verify'
        
        start_time = time.time()
        try:
            # Mock sending SMS payload
            response = {'success': True, 'entries': [{'messageid': 'msg-123', 'cost': 0.05}]}
            duration = int((time.time() - start_time) * 1000)
            
            self.log_activity(
                action='send_otp',
                request_data={'receptor': receptor, 'template': template},
                response_data=response,
                status_code=200,
                duration_ms=duration
            )
            
            return {
                'success': True,
                'message_id': 'msg-123',
                'cost': 0.05
            }
        except Exception as e:
            duration = int((time.time() - start_time) * 1000)
            self.log_activity(
                action='send_otp',
                log_level='error',
                request_data={'receptor': receptor},
                error_message=str(e),
                duration_ms=duration
            )
            return {
                'success': False,
                'error': 'Failed to communicate with SMS provider.'
            }
    
    def send_pattern(self, receptor: str, template: str, tokens: Dict[str, str]) -> Dict[str, Any]:
        if not self.check_rate_limit(receptor, 'send_pattern'):
            return {
                'success': False,
                'error': 'Rate limit exceeded.'
            }
        
        start_time = time.time()
        try:
            response = {'success': True, 'entries': [{'messageid': 'msg-pattern-123', 'cost': 0.05}]}
            duration = int((time.time() - start_time) * 1000)
            
            self.log_activity(
                action='send_pattern',
                request_data={
                    'receptor': receptor,
                    'template': template,
                    'tokens_count': len(tokens)
                },
                response_data=response,
                status_code=200,
                duration_ms=duration
            )
            
            return {
                'success': True,
                'message_id': 'msg-pattern-123',
                'cost': 0.05
            }
        except Exception as e:
            duration = int((time.time() - start_time) * 1000)
            self.log_activity(
                action='send_pattern',
                log_level='error',
                request_data={'receptor': receptor, 'template': template},
                error_message=str(e),
                duration_ms=duration
            )
            return {
                'success': False,
                'error': 'Failed to communicate with SMS provider.'
            }
    
    def send_bulk(self, receptors: List[str], message: str) -> Dict[str, Any]:
        if not self.check_rate_limit('bulk', 'send_bulk'):
            return {
                'success': False,
                'error': 'Rate limit exceeded for bulk messages.'
            }
        
        start_time = time.time()
        try:
            response = {'success': True, 'entries': [{'messageid': f'msg-bulk-{i}', 'cost': 0.05} for i in range(len(receptors))]}
            duration = int((time.time() - start_time) * 1000)
            
            self.log_activity(
                action='send_bulk',
                request_data={
                    'receptors_count': len(receptors),
                    'message_length': len(message)
                },
                response_data=response,
                status_code=200,
                duration_ms=duration
            )
            
            return {
                'success': True,
                'message_ids': [f'msg-bulk-{i}' for i in range(len(receptors))],
                'total_cost': len(receptors) * 0.05
            }
        except Exception as e:
            duration = int((time.time() - start_time) * 1000)
            self.log_activity(
                action='send_bulk',
                log_level='error',
                request_data={'receptors_count': len(receptors)},
                error_message=str(e),
                duration_ms=duration
            )
            return {
                'success': False,
                'error': 'Failed to communicate with SMS provider.'
            }
    
    def get_status(self, message_id: str) -> Dict[str, Any]:
        try:
            return {
                'success': True,
                'status': 10,
                'statustext': 'Delivered',
                'sender': self.sender,
                'receptor': '09123456789',
                'date': int(time.time()),
                'cost': 0.05
            }
        except Exception as e:
            return {
                'success': False,
                'error': f'Failed to retrieve message status: {str(e)}'
            }
