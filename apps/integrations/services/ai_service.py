"""
سرویس یکپارچه‌سازی با سیستم‌های هوش مصنوعی
"""
from typing import Dict, Any, Optional, List
import requests
import logging
import time
import json
from django.conf import settings
from integrations.services.base_service import BaseIntegrationService

logger = logging.getLogger(__name__)


class AIIntegrationService(BaseIntegrationService):
    """
    سرویس یکپارچه‌سازی با LLM ها و سرویس‌های AI
    """
    
    def __init__(self, provider_slug: str = 'openai'):
        """
        Args:
            provider_slug: شناسه ارائه‌دهنده (openai, talkbot, etc.)
        """
        super().__init__(provider_slug)
        self._api_key = None
        self._base_url = None
        self._model = None
    
    @property
    def api_key(self) -> str:
        """دریافت API key"""
        if not self._api_key:
            self._api_key = self.get_credential('api_key')
        return self._api_key
    
    @property
    def base_url(self) -> str:
        """دریافت آدرس پایه API"""
        if not self._base_url:
            self._base_url = self.provider.api_base_url or self._get_default_base_url()
        return self._base_url
    
    @property
    def default_model(self) -> str:
        """دریافت مدل پیش‌فرض"""
        if not self._model:
            self._model = self.get_credential('default_model', required=False) or 'gpt-4'
        return self._model
    
    def _get_default_base_url(self) -> str:
        """دریافت آدرس پایه پیش‌فرض بر اساس ارائه‌دهنده"""
        urls = {
            'openai': 'https://api.openai.com/v1',
            'talkbot': 'https://api.talkbot.ir/v1',
            'anthropic': 'https://api.anthropic.com/v1'
        }
        return urls.get(self.provider_slug, '')
    
    def validate_config(self) -> bool:
        """اعتبارسنجی تنظیمات"""
        try:
            # بررسی وجود API key
            if not self.api_key:
                return False
            
            # تست ساده با لیست مدل‌ها
            if self.provider_slug == 'openai':
                response = self._make_request('GET', 'models')
                return response.get('success', False)
            
            return True
            
        except Exception as e:
            logger.error(f"Config validation failed: {str(e)}")
            return False
    
    def health_check(self) -> Dict[str, Any]:
        """بررسی سلامت سرویس"""
        start_time = time.time()
        
        try:
            # تست با یک پرامپت ساده
            response = self.generate_text(
                prompt="Say 'OK' if you're working",
                max_tokens=10,
                temperature=0
            )
            
            if response.get('success'):
                return {
                    'status': 'healthy',
                    'response_time_ms': int((time.time() - start_time) * 1000),
                    'provider': self.provider_slug,
                    'model': self.default_model
                }
            else:
                return {
                    'status': 'unhealthy',
                    'error': response.get('error', 'Unknown error')
                }
                
        except Exception as e:
            return {
                'status': 'unhealthy',
                'error': str(e),
                'response_time_ms': int((time.time() - start_time) * 1000)
            }
    
    def generate_text(self, prompt: str, model: Optional[str] = None,
                     max_tokens: int = 1000, temperature: float = 0.7,
                     system_prompt: Optional[str] = None,
                     **kwargs) -> Dict[str, Any]:
        """
        تولید متن با AI
        
        Args:
            prompt: متن ورودی
            model: مدل مورد استفاده
            max_tokens: حداکثر توکن‌های خروجی
            temperature: میزان خلاقیت (0-2)
            system_prompt: پرامپت سیستم
            **kwargs: پارامترهای اضافی
            
        Returns:
            نتیجه تولید متن
        """
        # بررسی rate limit
        if not self.check_rate_limit('generate', 'text_generation'):
            return {
                'success': False,
                'error': 'تعداد درخواست‌ها بیش از حد مجاز است'
            }
        
        model = model or self.default_model
        start_time = time.time()
        
        try:
            # آماده‌سازی داده‌ها بر اساس ارائه‌دهنده
            if self.provider_slug == 'openai':
                data = self._prepare_openai_request(
                    prompt, model, max_tokens, temperature, system_prompt, **kwargs
                )
                endpoint = 'chat/completions'
            else:
                # سایر ارائه‌دهندگان
                data = {
                    'prompt': prompt,
                    'model': model,
                    'max_tokens': max_tokens,
                    'temperature': temperature,
                    **kwargs
                }
                endpoint = 'completions'
            
            response = self._make_request('POST', endpoint, data)
            duration = int((time.time() - start_time) * 1000)
            
            # ثبت لاگ
            self.log_activity(
                action='generate_text',
                request_data={
                    'model': model,
                    'prompt_length': len(prompt),
                    'max_tokens': max_tokens
                },
                response_data={
                    'success': response.get('success'),
                    'tokens_used': response.get('usage', {})
                },
                duration_ms=duration
            )
            
            if response.get('success'):
                return self._parse_generation_response(response)
            else:
                return {
                    'success': False,
                    'error': response.get('error', 'خطا در تولید متن')
                }
                
        except Exception as e:
            duration = int((time.time() - start_time) * 1000)
            
            # ثبت لاگ خطا
            self.log_activity(
                action='generate_text',
                log_level='error',
                request_data={'model': model, 'prompt_length': len(prompt)},
                error_message=str(e),
                duration_ms=duration
            )
            
            return {
                'success': False,
                'error': f'خطا در ارتباط با سرویس AI: {str(e)}'
            }
    
    def analyze_medical_text(self, text: str, analysis_type: str = 'general',
                           patient_context: Optional[Dict] = None) -> Dict[str, Any]:
        """
        تحلیل متن پزشکی
        
        Args:
            text: متن برای تحلیل
            analysis_type: نوع تحلیل (general, symptoms, diagnosis, etc.)
            patient_context: اطلاعات بیمار
            
        Returns:
            نتیجه تحلیل
        """
        # ساخت پرامپت تخصصی پزشکی
        system_prompt = self._get_medical_system_prompt(analysis_type)
        
        # اضافه کردن context بیمار به پرامپت
        if patient_context:
            context_str = self._format_patient_context(patient_context)
            prompt = f"Patient Context:\n{context_str}\n\nText to analyze:\n{text}"
        else:
            prompt = text
        
        # اضافه کردن دستورالعمل‌های خاص
        if analysis_type == 'symptoms':
            prompt += "\n\nPlease identify and categorize all symptoms mentioned."
        elif analysis_type == 'diagnosis':
            prompt += "\n\nProvide possible differential diagnoses based on the information."
        elif analysis_type == 'prescription':
            prompt += "\n\nAnalyze the prescription for drug interactions and dosing."
        
        return self.generate_text(
            prompt=prompt,
            system_prompt=system_prompt,
            temperature=0.3,  # دقت بیشتر برای متون پزشکی
            max_tokens=1500
        )
    
    def transcribe_audio(self, audio_file_path: str, language: str = 'fa',
                       medical_mode: bool = False) -> Dict[str, Any]:
        """
        تبدیل صوت به متن
        
        Args:
            audio_file_path: مسیر فایل صوتی
            language: زبان صوت
            medical_mode: حالت پزشکی
            
        Returns:
            نتیجه رونویسی
        """
        # بررسی rate limit
        if not self.check_rate_limit('transcribe', 'audio_transcription'):
            return {
                'success': False,
                'error': 'تعداد درخواست‌ها بیش از حد مجاز است'
            }
        
        start_time = time.time()
        
        try:
            # خواندن فایل صوتی
            with open(audio_file_path, 'rb') as audio_file:
                files = {'file': audio_file}
                data = {
                    'model': 'whisper-1',
                    'language': language
                }
                
                if medical_mode:
                    data['prompt'] = self._get_medical_transcription_prompt()
                
                response = self._make_request(
                    'POST',
                    'audio/transcriptions',
                    data=data,
                    files=files
                )
            
            duration = int((time.time() - start_time) * 1000)
            
            # ثبت لاگ
            self.log_activity(
                action='transcribe_audio',
                request_data={
                    'language': language,
                    'medical_mode': medical_mode
                },
                response_data={'success': response.get('success')},
                duration_ms=duration
            )
            
            if response.get('success'):
                return {
                    'success': True,
                    'text': response.get('text', ''),
                    'duration': duration
                }
            else:
                return {
                    'success': False,
                    'error': response.get('error', 'خطا در رونویسی')
                }
                
        except Exception as e:
            duration = int((time.time() - start_time) * 1000)
            
            # ثبت لاگ خطا
            self.log_activity(
                action='transcribe_audio',
                log_level='error',
                error_message=str(e),
                duration_ms=duration
            )
            
            return {
                'success': False,
                'error': f'خطا در رونویسی: {str(e)}'
            }
    
    def _prepare_openai_request(self, prompt: str, model: str, max_tokens: int,
                              temperature: float, system_prompt: Optional[str],
                              **kwargs) -> Dict[str, Any]:
        """آماده‌سازی درخواست برای OpenAI API"""
        messages = []
        
        if system_prompt:
            messages.append({
                'role': 'system',
                'content': system_prompt
            })
        
        messages.append({
            'role': 'user',
            'content': prompt
        })
        
        return {
            'model': model,
            'messages': messages,
            'max_tokens': max_tokens,
            'temperature': temperature,
            **kwargs
        }
    
    def _parse_generation_response(self, response: Dict) -> Dict[str, Any]:
        """تجزیه پاسخ تولید متن"""
        if self.provider_slug == 'openai':
            choices = response.get('data', {}).get('choices', [])
            if choices:
                return {
                    'success': True,
                    'text': choices[0].get('message', {}).get('content', ''),
                    'usage': response.get('data', {}).get('usage', {}),
                    'model': response.get('data', {}).get('model')
                }
        else:
            # سایر ارائه‌دهندگان
            return {
                'success': True,
                'text': response.get('data', {}).get('text', ''),
                'usage': response.get('data', {}).get('usage', {})
            }
        
        return {
            'success': False,
            'error': 'Invalid response format'
        }
    
    def _get_medical_system_prompt(self, analysis_type: str) -> str:
        """دریافت پرامپت سیستم برای تحلیل‌های پزشکی"""
        prompts = {
            'general': """You are a medical AI assistant. Provide accurate, evidence-based medical information. 
                         Always recommend consulting with healthcare professionals for definitive diagnosis and treatment.""",
            
            'symptoms': """You are a medical symptom analyzer. Identify and categorize symptoms mentioned in the text. 
                          Group them by body system and severity. Flag any red flags or emergency symptoms.""",
            
            'diagnosis': """You are a diagnostic assistant. Based on the presented information, provide possible 
                           differential diagnoses ranked by likelihood. Include relevant follow-up questions.""",
            
            'prescription': """You are a prescription analysis assistant. Check for drug interactions, appropriate 
                             dosing, and contraindications. Flag any potential issues."""
        }
        
        return prompts.get(analysis_type, prompts['general'])
    
    def _get_medical_transcription_prompt(self) -> str:
        """دریافت پرامپت برای رونویسی پزشکی"""
        return """Medical consultation transcription. Common medical terms in Persian include:
                 سردرد، تب، سرفه، درد قفسه سینه، تنگی نفس، تهوع، استفراغ، اسهال، یبوست،
                 فشار خون، دیابت، آنتی‌بیوتیک، مسکن، آزمایش، سی‌تی اسکن، ام‌آر‌آی"""
    
    def _format_patient_context(self, context: Dict) -> str:
        """فرمت کردن اطلاعات بیمار"""
        lines = []
        
        if 'age' in context:
            lines.append(f"Age: {context['age']}")
        if 'gender' in context:
            lines.append(f"Gender: {context['gender']}")
        if 'medical_history' in context:
            lines.append(f"Medical History: {', '.join(context['medical_history'])}")
        if 'medications' in context:
            lines.append(f"Current Medications: {', '.join(context['medications'])}")
        if 'allergies' in context:
            lines.append(f"Allergies: {', '.join(context['allergies'])}")
        
        return '\n'.join(lines)
    
    def _make_request(self, method: str, endpoint: str, data: Optional[Dict] = None,
                     files: Optional[Dict] = None) -> Dict[str, Any]:
        """ارسال درخواست به API"""
        url = f"{self.base_url}/{endpoint}"
        headers = {
            'Authorization': f'Bearer {self.api_key}'
        }
        
        # اضافه کردن Content-Type برای JSON
        if not files and data:
            headers['Content-Type'] = 'application/json'
        
        try:
            if method == 'GET':
                response = requests.get(url, headers=headers, timeout=30)
            elif method == 'POST':
                if files:
                    response = requests.post(
                        url, headers=headers, data=data, files=files, timeout=60
                    )
                else:
                    response = requests.post(
                        url, headers=headers, json=data, timeout=30
                    )
            else:
                raise ValueError(f"Unsupported method: {method}")
            
            # بررسی وضعیت پاسخ
            if response.status_code == 200:
                return {
                    'success': True,
                    'data': response.json()
                }
            else:
                error_data = response.json() if response.content else {}
                return {
                    'success': False,
                    'error': error_data.get('error', {}).get('message', f'HTTP {response.status_code}'),
                    'status_code': response.status_code
                }
                
        except requests.exceptions.Timeout:
            raise Exception(f'Timeout while connecting to {self.provider_slug}')
        except requests.exceptions.RequestException as e:
            raise Exception(f'Network error: {str(e)}')
        except ValueError as e:
            raise Exception(f'Invalid response: {str(e)}')