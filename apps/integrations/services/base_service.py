"""
Base Integration Service for external API providers.
"""

from typing import Dict, Any, Optional
from abc import ABC, abstractmethod
import logging
import time
from django.conf import settings
from django.core.cache import cache
from ..models import IntegrationProvider, IntegrationLog, IntegrationCredential

logger = logging.getLogger(__name__)


class BaseIntegrationService(ABC):
    """
    Abstract Base Class for external API integrations.
    """
    
    def __init__(self, provider_slug: str):
        self.provider_slug = provider_slug
        self._provider = None
        self._credentials = {}
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
    
    @property
    def provider(self) -> IntegrationProvider:
        if not self._provider:
            try:
                self._provider = IntegrationProvider.objects.get(
                    slug=self.provider_slug,
                    status='active'
                )
            except IntegrationProvider.DoesNotExist:
                raise ValueError(f"Provider {self.provider_slug} not found or inactive")
        return self._provider
    
    def get_credential(self, key_name: str, environment: Optional[str] = None, required: bool = True) -> Optional[str]:
        if not environment:
            environment = getattr(settings, 'INTEGRATION_ENVIRONMENT', 'production')
        
        cache_key = f"integration_cred:{self.provider_slug}:{key_name}:{environment}"
        cached_value = cache.get(cache_key)
        if cached_value:
            return cached_value
        
        try:
            credential = IntegrationCredential.objects.get(
                provider=self.provider,
                key_name=key_name,
                environment=environment,
                is_active=True
            )
            
            if not credential.is_valid():
                if required:
                    raise ValueError(f"Credential {key_name} is expired or invalid")
                return None
            
            value = credential.key_value
            cache.set(cache_key, value, 3600)  # 1 hour cache TTL
            return value
            
        except IntegrationCredential.DoesNotExist:
            if required:
                raise ValueError(f"Credential {key_name} not found for {self.provider_slug}")
            return None
    
    def log_activity(self, action: str, log_level: str = 'info',
                    request_data: Optional[Dict] = None,
                    response_data: Optional[Dict] = None,
                    error_message: Optional[str] = None,
                    status_code: Optional[int] = None,
                    duration_ms: Optional[int] = None,
                    user=None, ip_address: Optional[str] = None):
        try:
            IntegrationLog.objects.create(
                provider=self.provider,
                log_level=log_level,
                service_name=self.__class__.__name__,
                action=action,
                request_data=request_data or {},
                response_data=response_data or {},
                error_message=error_message or '',
                status_code=status_code,
                duration_ms=duration_ms,
                user=user,
                ip_address=ip_address
            )
        except Exception as e:
            self.logger.error(f"Failed to log activity: {str(e)}")
    
    def check_rate_limit(self, identifier: str, action: str) -> bool:
        rules = self.provider.rate_limits.filter(
            is_active=True,
            endpoint_pattern__icontains=action
        )
        
        for rule in rules:
            cache_key = f"rate_limit:{self.provider_slug}:{action}:{identifier}"
            current_count = cache.get(cache_key, 0)
            
            if current_count >= rule.max_requests:
                self.log_activity(
                    action=f"rate_limit_exceeded:{action}",
                    log_level='warning',
                    error_message=f"Rate limit exceeded for {identifier}"
                )
                return False
            
            cache.set(cache_key, current_count + 1, rule.time_window_seconds)
        
        return True
    
    @abstractmethod
    def validate_config(self) -> bool:
        pass
    
    @abstractmethod
    def health_check(self) -> Dict[str, Any]:
        pass
    
    def execute_with_retry(self, func: callable, max_retries: int = 3,
                          retry_delay: float = 1.0, *args, **kwargs) -> Any:
        last_exception = None
        
        for attempt in range(max_retries):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                last_exception = e
                self.logger.warning(
                    f"Attempt {attempt + 1} failed: {str(e)}"
                )
                
                if attempt < max_retries - 1:
                    time.sleep(retry_delay * (attempt + 1))
        
        raise last_exception