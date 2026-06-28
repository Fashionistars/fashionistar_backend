"""
سرویس یکپارچه‌سازی با کاوه‌نگار برای ارسال پیامک
"""
from typing import Dict, Any, Optional, List
import requests
import logging
import time
from django.conf import settings
from integrations.services.base_service import BaseIntegrationService

logger = logging.getLogger(__name__)


class KavenegarService(BaseIntegrationService):
    """
    سرویس ارسال پیامک با کاوه‌نگار
    """
    
    def __init__(self):
        super().__init__('kavenegar')
        self.base_url = "https://api.kavenegar.com/v1"
        self._api_key = None
        self._sender = None
    
    @property
    def api_key(self) -> str:
        """دریافت API key"""
        if not self._api_key:
            self._api_key = self.get_credential('api_key')
        return self._api_key
    
    @property
    def sender(self) -> str:
        """دریافت شماره فرستنده"""
        if not self._sender:
            self._sender = self.get_credential('sender_number')
        return self._sender
    
    def validate_config(self) -> bool:
        """اعتبارسنجی تنظیمات"""
        try:
            # بررسی وجود API key
            if not self.api_key:
                return False
            
            # بررسی اعتبار API key با یک درخواست ساده
            response = self._make_request('account/info')
            return response.get('success', False)
            
        except Exception as e:
            logger.error(f"Config validation failed: {str(e)}")
            return False
    
    def health_check(self) -> Dict[str, Any]:
        """بررسی سلامت سرویس"""
        start_time = time.time()
        
        try:
            # درخواست اطلاعات حساب
            response = self._make_request('account/info')
            
            if response.get('success'):
                return {
                    'status': 'healthy',
                    'response_time_ms': int((time.time() - start_time) * 1000),
                    'balance': response.get('entries', {}).get('remaincredit', 0),
                    'details': {
                        'api_level': response.get('entries', {}).get('apilevel'),
                        'daily_send': response.get('entries', {}).get('dailysend', 0)
                    }
                }
            else:
                return {
                    'status': 'unhealthy',
                    'error': 'Invalid response from API'
                }
                
        except Exception as e:
            return {
                'status': 'unhealthy',
                'error': str(e),
                'response_time_ms': int((time.time() - start_time) * 1000)
            }
    
    def send_otp(self, receptor: str, token: str, 
                template: Optional[str] = None) -> Dict[str, Any]:
        """
        ارسال پیامک OTP
        
        Args:
            receptor: شماره گیرنده (09123456789)
            token: کد OTP
            template: نام قالب (اختیاری)
            
        Returns:
            نتیجه ارسال
        """
        # بررسی rate limit
        if not self.check_rate_limit(receptor, 'send_otp'):
            return {
                'success': False,
                'error': 'تعداد درخواست‌ها بیش از حد مجاز است'
            }
        
        # تنظیم قالب پیش‌فرض
        if not template:
            template = self.get_credential('otp_template', required=False) or 'verify'
        
        start_time = time.time()
        
        try:
            data = {
                'receptor': receptor,
                'token': token,
                'template': template
            }
            
            response = self._make_request('verify/lookup', data)
            duration = int((time.time() - start_time) * 1000)
            
            # ثبت لاگ
            self.log_activity(
                action='send_otp',
                request_data={'receptor': receptor, 'template': template},
                response_data=response,
                status_code=200 if response.get('success') else 400,
                duration_ms=duration
            )
            
            if response.get('success'):
                return {
                    'success': True,
                    'message_id': response.get('entries', [{}])[0].get('messageid'),
                    'cost': response.get('entries', [{}])[0].get('cost', 0)
                }
            else:
                return {
                    'success': False,
                    'error': response.get('message', 'خطا در ارسال پیامک')
                }
                
        except Exception as e:
            duration = int((time.time() - start_time) * 1000)
            
            # ثبت لاگ خطا
            self.log_activity(
                action='send_otp',
                log_level='error',
                request_data={'receptor': receptor},
                error_message=str(e),
                duration_ms=duration
            )
            
            return {
                'success': False,
                'error': 'خطا در ارتباط با سرویس پیامک'
            }
    
    def send_pattern(self, receptor: str, template: str,
                    tokens: Dict[str, str]) -> Dict[str, Any]:
        """
        ارسال پیامک با قالب
        
        Args:
            receptor: شماره گیرنده
            template: نام قالب
            tokens: دیکشنری توکن‌ها
            
        Returns:
            نتیجه ارسال
        """
        # بررسی rate limit
        if not self.check_rate_limit(receptor, 'send_pattern'):
            return {
                'success': False,
                'error': 'تعداد درخواست‌ها بیش از حد مجاز است'
            }
        
        start_time = time.time()
        
        try:
            data = {
                'receptor': receptor,
                'template': template,
                **tokens  # token, token2, token3, etc.
            }
            
            response = self._make_request('verify/lookup', data)
            duration = int((time.time() - start_time) * 1000)
            
            # ثبت لاگ
            self.log_activity(
                action='send_pattern',
                request_data={
                    'receptor': receptor,
                    'template': template,
                    'tokens_count': len(tokens)
                },
                response_data=response,
                status_code=200 if response.get('success') else 400,
                duration_ms=duration
            )
            
            if response.get('success'):
                return {
                    'success': True,
                    'message_id': response.get('entries', [{}])[0].get('messageid'),
                    'cost': response.get('entries', [{}])[0].get('cost', 0)
                }
            else:
                return {
                    'success': False,
                    'error': response.get('message', 'خطا در ارسال پیامک')
                }
                
        except Exception as e:
            duration = int((time.time() - start_time) * 1000)
            
            # ثبت لاگ خطا
            self.log_activity(
                action='send_pattern',
                log_level='error',
                request_data={'receptor': receptor, 'template': template},
                error_message=str(e),
                duration_ms=duration
            )
            
            return {
                'success': False,
                'error': 'خطا در ارتباط با سرویس پیامک'
            }
    
    def send_bulk(self, receptors: List[str], message: str) -> Dict[str, Any]:
        """
        ارسال پیامک گروهی
        
        Args:
            receptors: لیست شماره‌های گیرنده
            message: متن پیام
            
        Returns:
            نتیجه ارسال
        """
        # بررسی rate limit برای ارسال گروهی
        if not self.check_rate_limit('bulk', 'send_bulk'):
            return {
                'success': False,
                'error': 'تعداد درخواست‌های گروهی بیش از حد مجاز است'
            }
        
        start_time = time.time()
        
        try:
            data = {
                'receptor': ','.join(receptors),
                'message': message,
                'sender': self.sender
            }
            
            response = self._make_request('sms/send', data)
            duration = int((time.time() - start_time) * 1000)
            
            # ثبت لاگ
            self.log_activity(
                action='send_bulk',
                request_data={
                    'receptors_count': len(receptors),
                    'message_length': len(message)
                },
                response_data=response,
                status_code=200 if response.get('success') else 400,
                duration_ms=duration
            )
            
            if response.get('success'):
                return {
                    'success': True,
                    'message_ids': [e.get('messageid') for e in response.get('entries', [])],
                    'total_cost': sum(e.get('cost', 0) for e in response.get('entries', []))
                }
            else:
                return {
                    'success': False,
                    'error': response.get('message', 'خطا در ارسال پیامک گروهی')
                }
                
        except Exception as e:
            duration = int((time.time() - start_time) * 1000)
            
            # ثبت لاگ خطا
            self.log_activity(
                action='send_bulk',
                log_level='error',
                request_data={'receptors_count': len(receptors)},
                error_message=str(e),
                duration_ms=duration
            )
            
            return {
                'success': False,
                'error': 'خطا در ارتباط با سرویس پیامک'
            }
    
    def get_status(self, message_id: str) -> Dict[str, Any]:
        """
        دریافت وضعیت پیامک
        
        Args:
            message_id: شناسه پیامک
            
        Returns:
            وضعیت پیامک
        """
        try:
            data = {'messageid': message_id}
            response = self._make_request('sms/status', data)
            
            if response.get('success'):
                entry = response.get('entries', [{}])[0]
                return {
                    'success': True,
                    'status': entry.get('status'),
                    'statustext': entry.get('statustext'),
                    'sender': entry.get('sender'),
                    'receptor': entry.get('receptor'),
                    'date': entry.get('date'),
                    'cost': entry.get('cost')
                }
            else:
                return {
                    'success': False,
                    'error': response.get('message', 'خطا در دریافت وضعیت')
                }
                
        except Exception as e:
            return {
                'success': False,
                'error': f'خطا در دریافت وضعیت: {str(e)}'
            }
    
    def _make_request(self, endpoint: str, data: Optional[Dict] = None) -> Dict[str, Any]:
        """
        ارسال درخواست به API کاوه‌نگار
        
        Args:
            endpoint: نقطه پایانی API
            data: داده‌های درخواست
            
        Returns:
            پاسخ API
        """
        url = f"{self.base_url}/{self.api_key}/{endpoint}.json"
        
        try:
            response = requests.post(
                url,
                data=data or {},
                timeout=30
            )
            
            result = response.json()
            
            # بررسی وضعیت پاسخ
            if result.get('return', {}).get('status') == 200:
                return {
                    'success': True,
                    'entries': result.get('entries', []),
                    'message': result.get('return', {}).get('message')
                }
            else:
                return {
                    'success': False,
                    'message': result.get('return', {}).get('message', 'Unknown error'),
                    'status': result.get('return', {}).get('status')
                }
                
        except requests.exceptions.Timeout:
            raise Exception('Timeout while connecting to Kavenegar')
        except requests.exceptions.RequestException as e:
            raise Exception(f'Network error: {str(e)}')
        except ValueError:
            raise Exception('Invalid JSON response from Kavenegar')