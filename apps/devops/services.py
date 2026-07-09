# apps/devops/services.py
"""
DevOps Services for environment management, deployment tracking, and health monitoring with Redis caching.
"""

import logging
import hashlib
import json
from typing import Dict, Any, List, Optional
from django.db.models import Count, Avg
from django.conf import settings
from django.core.cache import cache
from django.utils import timezone
from datetime import timedelta

from .models import EnvironmentConfig, SecretConfig, DeploymentHistory, HealthCheck, ServiceMonitoring


logger = logging.getLogger(__name__)


class DevOpsService:
    """
    Main service for DevOps operations with Redis caching.
    """
    
    def __init__(self):
        # Cache TTL in seconds (default 5 minutes for configs, 1 hour for deployments)
        self.config_cache_ttl = getattr(settings, 'DEVOPS_CONFIG_CACHE_TTL', 300)
        self.deployment_cache_ttl = getattr(settings, 'DEVOPS_DEPLOYMENT_CACHE_TTL', 3600)
        self.health_cache_ttl = getattr(settings, 'DEVOPS_HEALTH_CACHE_TTL', 60)  # 1 minute for health
        self.cache_prefix = 'devops:v1:'
    
    def _generate_cache_key(self, prefix: str, **kwargs) -> str:
        """Generate a unique cache key for devops parameters."""
        cache_data = {k: v for k, v in sorted(kwargs.items())}
        cache_hash = hashlib.md5(json.dumps(cache_data, sort_keys=True).encode()).hexdigest()
        return f"{self.cache_prefix}{prefix}:{cache_hash}"
    
    def get_environment_summary(self, environment_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Get environment summary with Redis caching.
        """
        cache_key = self._generate_cache_key('env_summary', environment_id=environment_id)
        cached_result = cache.get(cache_key)
        if cached_result:
            return cached_result
        
        queryset = EnvironmentConfig.objects.all()
        if environment_id:
            queryset = queryset.filter(id=environment_id)
        
        environments = list(queryset)
        active_count = sum(1 for env in environments if env.is_active)
        
        result = {
            'total_environments': len(environments),
            'active_environments': active_count,
            'inactive_environments': len(environments) - active_count,
            'environments': [
                {
                    'id': str(env.id),
                    'name': env.name,
                    'environment_type': env.environment_type,
                    'is_active': env.is_active,
                }
                for env in environments
            ]
        }
        
        cache.set(cache_key, result, self.config_cache_ttl)
        return result
    
    def get_deployment_summary(self, environment_id: Optional[str] = None, days: int = 30) -> Dict[str, Any]:
        """
        Get deployment summary with Redis caching.
        """
        cache_key = self._generate_cache_key('deployment_summary', environment_id=environment_id, days=days)
        cached_result = cache.get(cache_key)
        if cached_result:
            return cached_result
        
        since = timezone.now() - timedelta(days=days)
        queryset = DeploymentHistory.objects.filter(started_at__gte=since)
        
        if environment_id:
            queryset = queryset.filter(environment_id=environment_id)
        
        deployments = list(queryset)
        
        # Calculate statistics
        successful = sum(1 for d in deployments if d.status == 'success')
        failed = sum(1 for d in deployments if d.status == 'failed')
        running = sum(1 for d in deployments if d.status == 'running')
        pending = sum(1 for d in deployments if d.status == 'pending')
        
        # Average deployment duration
        completed_deployments = [d for d in deployments if d.completed_at]
        if completed_deployments:
            total_duration = sum((d.completed_at - d.started_at).total_seconds() for d in completed_deployments)
            avg_duration_seconds = total_duration / len(completed_deployments)
        else:
            avg_duration_seconds = 0
        
        result = {
            'period_days': days,
            'total_deployments': len(deployments),
            'successful_deployments': successful,
            'failed_deployments': failed,
            'running_deployments': running,
            'pending_deployments': pending,
            'success_rate_percent': round(successful / len(deployments) * 100, 2) if deployments else 0,
            'avg_duration_seconds': round(avg_duration_seconds, 2),
        }
        
        cache.set(cache_key, result, self.deployment_cache_ttl)
        return result
    
    def get_health_summary(self, environment_id: Optional[str] = None, hours: int = 24) -> Dict[str, Any]:
        """
        Get health check summary with Redis caching.
        """
        cache_key = self._generate_cache_key('health_summary', environment_id=environment_id, hours=hours)
        cached_result = cache.get(cache_key)
        if cached_result:
            return cached_result
        
        since = timezone.now() - timedelta(hours=hours)
        queryset = HealthCheck.objects.filter(checked_at__gte=since)
        
        if environment_id:
            queryset = queryset.filter(environment_id=environment_id)
        
        health_checks = list(queryset)
        
        # Calculate statistics
        healthy = sum(1 for h in health_checks if h.status == 'healthy')
        warning = sum(1 for h in health_checks if h.status == 'warning')
        critical = sum(1 for h in health_checks if h.status == 'critical')
        unknown = sum(1 for h in health_checks if h.status == 'unknown')
        
        # Average response time
        response_times = [h.response_time for h in health_checks if h.response_time]
        avg_response_time = sum(response_times) / len(response_times) if response_times else 0
        
        result = {
            'period_hours': hours,
            'total_checks': len(health_checks),
            'healthy_checks': healthy,
            'warning_checks': warning,
            'critical_checks': critical,
            'unknown_checks': unknown,
            'health_rate_percent': round(healthy / len(health_checks) * 100, 2) if health_checks else 0,
            'avg_response_time_ms': round(avg_response_time, 2),
        }
        
        cache.set(cache_key, result, self.health_cache_ttl)
        return result
    
    def get_secret_summary(self, environment_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Get secret summary with Redis caching.
        """
        cache_key = self._generate_cache_key('secret_summary', environment_id=environment_id)
        cached_result = cache.get(cache_key)
        if cached_result:
            return cached_result
        
        queryset = SecretConfig.objects.all()
        if environment_id:
            queryset = queryset.filter(environment_id=environment_id)
        
        secrets = list(queryset)
        
        # Calculate statistics
        active = sum(1 for s in secrets if s.is_active)
        expired = sum(1 for s in secrets if s.is_expired)
        
        # Group by category
        category_counts = {}
        for secret in secrets:
            category_counts[secret.category] = category_counts.get(secret.category, 0) + 1
        
        result = {
            'total_secrets': len(secrets),
            'active_secrets': active,
            'expired_secrets': expired,
            'category_counts': category_counts,
        }
        
        cache.set(cache_key, result, self.config_cache_ttl)
        return result


# Singleton instance for easy import
devops_service = DevOpsService()


class DevOpsSecurityService:
    """
    Security service for DevOps operations including secret rotation and validation.
    """
    
    def __init__(self):
        self.rotation_interval_days = getattr(settings, 'DEVOPS_SECRET_ROTATION_DAYS', 90)
    
    async def acheck_secret_expiration(self, environment_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Check for expired or expiring secrets (async).
        Returns list of secrets that need attention.
        """
        queryset = SecretConfig.objects.filter(is_active=True)
        if environment_id:
            queryset = queryset.filter(environment_id=environment_id)
        
        secrets_needing_attention = []
        warning_threshold = timezone.now() + timedelta(days=7)  # 7 days warning
        
        async for secret in queryset:
            if secret.is_expired:
                secrets_needing_attention.append({
                    'id': str(secret.id),
                    'key_name': secret.key_name,
                    'environment': secret.environment.name,
                    'status': 'expired',
                    'expires_at': secret.expires_at.isoformat() if secret.expires_at else None,
                })
            elif secret.expires_at and secret.expires_at <= warning_threshold:
                secrets_needing_attention.append({
                    'id': str(secret.id),
                    'key_name': secret.key_name,
                    'environment': secret.environment.name,
                    'status': 'expiring_soon',
                    'expires_at': secret.expires_at.isoformat(),
                })
        
        return secrets_needing_attention
    
    async def avalidate_secret_strength(self, secret_value: str, category: str) -> Dict[str, Any]:
        """
        Validate secret strength based on category (async).
        Returns validation result with recommendations.
        """
        import re
        
        result = {
            'is_valid': True,
            'strength': 'weak',
            'issues': [],
            'recommendations': [],
        }
        
        # Basic length check
        if len(secret_value) < 16:
            result['issues'].append('Secret is too short (minimum 16 characters recommended)')
            result['recommendations'].append('Use longer secrets for better security')
        
        # Complexity check
        if not re.search(r'[A-Z]', secret_value):
            result['issues'].append('Missing uppercase letters')
        if not re.search(r'[a-z]', secret_value):
            result['issues'].append('Missing lowercase letters')
        if not re.search(r'[0-9]', secret_value):
            result['issues'].append('Missing numbers')
        if not re.search(r'[^A-Za-z0-9]', secret_value):
            result['issues'].append('Missing special characters')
        
        # Category-specific checks
        if category == 'api_key' and not re.search(r'^[A-Za-z0-9_-]+$', secret_value):
            result['issues'].append('API key should only contain alphanumeric characters, underscores, and hyphens')
        
        # Determine strength
        if len(result['issues']) == 0:
            result['strength'] = 'strong'
        elif len(result['issues']) <= 2:
            result['strength'] = 'medium'
        else:
            result['strength'] = 'weak'
            result['is_valid'] = False
        
        return result
    
    async def aget_security_summary(self, environment_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Get overall security summary for environments (async).
        """
        expired_secrets = await self.acheck_secret_expiration(environment_id)
        
        # Count by status
        expired_count = sum(1 for s in expired_secrets if s['status'] == 'expired')
        expiring_soon_count = sum(1 for s in expired_secrets if s['status'] == 'expiring_soon')
        
        # Get active environments
        environments = await EnvironmentConfig.aget_active_environments()
        
        # Get recent deployments
        recent_deployments = await DeploymentHistory.aget_recent_deployments(limit=10)
        
        # Check for failed deployments (potential security issues)
        failed_deployments = [d for d in recent_deployments if d.status == 'failed']
        
        return {
            'expired_secrets_count': expired_count,
            'expiring_soon_secrets_count': expiring_soon_count,
            'total_secrets_needing_attention': len(expired_secrets),
            'active_environments_count': len(environments),
            'recent_failed_deployments': len(failed_deployments),
            'security_score': self._calculate_security_score(
                expired_count,
                expiring_soon_count,
                len(environments),
                len(failed_deployments)
            ),
        }
    
    def _calculate_security_score(self, expired_count: int, expiring_count: int, env_count: int, failed_count: int) -> int:
        """Calculate overall security score (0-100)."""
        score = 100
        
        # Deduct for expired secrets
        score -= expired_count * 20
        
        # Deduct for expiring secrets
        score -= expiring_count * 5
        
        # Deduct for failed deployments
        score -= failed_count * 2
        
        # Ensure score is within bounds
        return max(0, min(100, score))


# Singleton instance for easy import
devops_security_service = DevOpsSecurityService()
