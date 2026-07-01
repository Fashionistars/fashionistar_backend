"""
AI Integration Service for external LLM APIs.
"""

from typing import Dict, Any, Optional
import requests
import logging
import time
from .base_service import BaseIntegrationService

logger = logging.getLogger(__name__)


class AIIntegrationService(BaseIntegrationService):
    """
    Service for integrating with external LLMs and AI APIs.
    """
    

    def __init__(self, provider_slug: str = 'openai'):
        super().__init__(provider_slug)
        self._api_key = None
        self._base_url = None
        self._model = None
    
    @property
    def api_key(self) -> str:
        if not self._api_key:
            try:
                self._api_key = self.get_credential('api_key')
            except ValueError:
                # If running self-hosted, we don't need a real OpenAI key; fall back to setting or dummy
                from django.conf import settings
                self._api_key = getattr(settings, 'OPENAI_API_KEY', '') or 'self-hosted-dummy-key'
        return self._api_key
    
    @property
    def base_url(self) -> str:
        if not self._base_url:
            self._base_url = self.provider.api_base_url or self._get_default_base_url()
        return self._base_url
    
    @property
    def default_model(self) -> str:
        if not self._model:
            try:
                self._model = self.get_credential('default_model', required=False)
            except ValueError:
                self._model = None
            if not self._model:
                from django.conf import settings
                self._model = getattr(settings, 'OPENAI_DEFAULT_MODEL', 'llama3.2:3b') or 'llama3.2:3b'
        return self._model
    
    def _get_default_base_url(self) -> str:
        from django.conf import settings
        default_openai = getattr(settings, 'OPENAI_API_BASE_URL', 'http://localhost:11434/v1')
        urls = {
            'openai': default_openai,
            'openrouter': 'https://openrouter.ai/api/v1',
            'talkbot': 'https://api.talkbot.ir/v1',  # Keep for compatibility in tests
            'anthropic': 'https://api.anthropic.com/v1'
        }
        return urls.get(self.provider_slug, '')
    
    def validate_config(self) -> bool:
        try:
            if self.provider_slug == 'openai':
                # Bypass validation key check for local Ollama server if no key required
                response = self._make_request('GET', 'models')
                return response.get('success', False)
            if not self.api_key:
                return False
            return True
            
        except Exception as e:
            logger.error(f"Config validation failed: {str(e)}")
            return False

    def health_check(self) -> Dict[str, Any]:
        start_time = time.time()
        
        try:
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
        if not self.check_rate_limit('generate', 'text_generation'):
            return {
                'success': False,
                'error': 'Rate limit exceeded.'
            }
        
        model = model or self.default_model
        start_time = time.time()
        
        try:
            if self.provider_slug == 'openai':
                data = self._prepare_openai_request(
                    prompt, model, max_tokens, temperature, system_prompt, **kwargs
                )
                endpoint = 'chat/completions'
            else:
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
                    'error': response.get('error', 'Error generating text')
                }
                
        except Exception as e:
            duration = int((time.time() - start_time) * 1000)
            
            self.log_activity(
                action='generate_text',
                log_level='error',
                request_data={'model': model, 'prompt_length': len(prompt)},
                error_message=str(e),
                duration_ms=duration
            )
            
            return {
                'success': False,
                'error': f'Error connecting to AI Service: {str(e)}'
            }
    
    def analyze_fashion_text(self, text: str, analysis_type: str = 'general',
                            client_context: Optional[Dict] = None) -> Dict[str, Any]:
        """
        Analyze fashion, styling or sizing text query.
        """
        system_prompt = self._get_fashion_system_prompt(analysis_type)
        
        if client_context:
            context_str = self._format_client_context(client_context)
            prompt = f"Client Context:\n{context_str}\n\nText to analyze:\n{text}"
        else:
            prompt = text
        
        if analysis_type == 'sizing':
            prompt += "\n\nPlease identify and categorize all sizing options and fit details."
        elif analysis_type == 'styling':
            prompt += "\n\nProvide style recommendations and coordinate outfit matches."
        elif analysis_type == 'catalog':
            prompt += "\n\nMap product descriptions to categories and suggest standard retail pricing."
        
        return self.generate_text(
            prompt=prompt,
            system_prompt=system_prompt,
            temperature=0.3,
            max_tokens=1500
        )
    
    def transcribe_audio(self, audio_file_path: str, language: str = 'en',
                        fashion_mode: bool = False) -> Dict[str, Any]:
        if not self.check_rate_limit('transcribe', 'audio_transcription'):
            return {
                'success': False,
                'error': 'Rate limit exceeded.'
            }
        
        start_time = time.time()
        
        try:
            with open(audio_file_path, 'rb') as audio_file:
                files = {'file': audio_file}
                data = {
                    'model': 'whisper-1',
                    'language': language
                }
                
                if fashion_mode:
                    data['prompt'] = self._get_fashion_transcription_prompt()
                
                response = self._make_request(
                    'POST',
                    'audio/transcriptions',
                    data=data,
                    files=files
                )
            
            duration = int((time.time() - start_time) * 1000)
            
            self.log_activity(
                action='transcribe_audio',
                request_data={
                    'language': language,
                    'fashion_mode': fashion_mode
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
                    'error': response.get('error', 'Error transcribing audio')
                }
                
        except Exception as e:
            duration = int((time.time() - start_time) * 1000)
            
            self.log_activity(
                action='transcribe_audio',
                log_level='error',
                error_message=str(e),
                duration_ms=duration
            )
            
            return {
                'success': False,
                'error': f'Transcription failed: {str(e)}'
            }
    
    def _prepare_openai_request(self, prompt: str, model: str, max_tokens: int,
                              temperature: float, system_prompt: Optional[str],
                              **kwargs) -> Dict[str, Any]:
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
            return {
                'success': True,
                'text': response.get('data', {}).get('text', ''),
                'usage': response.get('data', {}).get('usage', {})
            }
        
        return {
            'success': False,
            'error': 'Invalid response format'
        }
    
    def _get_fashion_system_prompt(self, analysis_type: str) -> str:
        prompts = {
            'general': """You are a fashion AI assistant. Provide stylish, accurate advice on trends, sizes and clothing.""",
            'sizing': """You are a sizing assistant. Recommend accurate size categories based on client body measurements and preferences.""",
            'styling': """You are a professional personal stylist. Create coordinated outfit suggestions and style advice.""",
            'catalog': """You are a retail product catalog organizer. Categorize items and suggest appropriate pricing tiers."""
        }
        return prompts.get(analysis_type, prompts['general'])
    
    def _get_fashion_transcription_prompt(self) -> str:
        return """Fashion consultation and tailoring transcription. Common terms include: shirt, sizing, fit, tailoring, measurements, suit, gown, jacket, fabric, design."""
    
    def _format_client_context(self, context: Dict) -> str:
        lines = []
        if 'height' in context:
            lines.append(f"Height: {context['height']}")
        if 'size' in context:
            lines.append(f"Size: {context['size']}")
        if 'style_preferences' in context:
            lines.append(f"Style Preferences: {', '.join(context['style_preferences'])}")
        if 'budget' in context:
            lines.append(f"Budget: {context['budget']}")
        return '\n'.join(lines)
    
    def _make_request(self, method: str, endpoint: str, data: Optional[Dict] = None,
                      files: Optional[Dict] = None) -> Dict[str, Any]:
        url = f"{self.base_url}/{endpoint}"
        headers = {
            'Authorization': f'Bearer {self.api_key}'
        }
        
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