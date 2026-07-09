# apps/devops/models.py
"""
DevOps and Environment Configuration models.
"""

from __future__ import annotations

import uuid
from typing import Optional
from django.db import models
from django.conf import settings
from django.core.validators import RegexValidator
from django.utils import timezone
from django.core.exceptions import ValidationError
from encrypted_model_fields.fields import EncryptedTextField

from apps.common.models import SoftDeleteModel



class EnvironmentConfig(SoftDeleteModel):
    """
    Manages settings and configurations for different environments.
    """
    
    ENVIRONMENT_CHOICES = [
        ('development', 'Development'),
        ('staging', 'Staging'),
        ('production', 'Production'),
        ('testing', 'Testing'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(
        max_length=100,
        unique=True,
        verbose_name="Environment Name",
        validators=[RegexValidator(
            regex=r'^[a-zA-Z0-9_-]+$',
            message='Environment name can only contain letters, numbers, underscores, and dashes.'
        )]
    )
    environment_type = models.CharField(
        max_length=20,
        choices=ENVIRONMENT_CHOICES,
        verbose_name="Environment Type"
    )
    description = models.TextField(
        blank=True,
        verbose_name="Description"
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name="Is Active"
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Created At"
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="Updated At"
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Created By"
    )
    
    class Meta:
        verbose_name = "Environment Config"
        verbose_name_plural = "Environment Configs"
        ordering = ['-created_at']
        
    def __str__(self) -> str:
        return f"{self.name} ({self.get_environment_type_display()})"
    
    # Async class methods
    @classmethod
    async def aget_by_id(cls, env_id: str):
        try:
            return await cls.objects.aget(id=env_id)
        except cls.DoesNotExist:
            return None
    
    @classmethod
    async def aget_by_name(cls, name: str):
        try:
            return await cls.objects.aget(name=name)
        except cls.DoesNotExist:
            return None
    
    @classmethod
    async def aget_active_environments(cls):
        queryset = cls.objects.filter(is_active=True)
        return [env async for env in queryset]
    
    @classmethod
    async def aget_by_type(cls, environment_type: str):
        queryset = cls.objects.filter(environment_type=environment_type)
        return [env async for env in queryset]


class SecretConfig(SoftDeleteModel):
    """
    Manages encrypted secrets and API keys.
    """
    
    CATEGORY_CHOICES = [
        ('database', 'Database'),
        ('api_key', 'API Key'),
        ('oauth', 'OAuth'),
        ('smtp', 'SMTP'),
        ('sms', 'SMS'),
        ('payment', 'Payment Gateway'),
        ('ssl', 'SSL Certificate'),
        ('encryption', 'Encryption Key'),
        ('other', 'Other'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    environment = models.ForeignKey(
        EnvironmentConfig,
        on_delete=models.CASCADE,
        related_name='secrets',
        verbose_name="Environment"
    )
    key_name = models.CharField(
        max_length=100,
        verbose_name="Key Name",
        validators=[RegexValidator(
            regex=r'^[A-Z][A-Z0-9_]*$',
            message='Key name must start with an uppercase letter and only contain uppercase letters, numbers, and underscores.'
        )]
    )
    encrypted_value = EncryptedTextField(
        verbose_name="Encrypted Value"
    )
    category = models.CharField(
        max_length=20,
        choices=CATEGORY_CHOICES,
        default='other',
        verbose_name="Category"
    )
    description = models.TextField(
        blank=True,
        verbose_name="Description"
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name="Is Active"
    )
    expires_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Expiration Date"
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Created At"
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="Updated At"
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Created By"
    )
    
    class Meta:
        verbose_name = "Secret Config"
        verbose_name_plural = "Secret Configs"
        unique_together = [['environment', 'key_name']]
        ordering = ['-created_at']
        
    def __str__(self) -> str:
        return f"{self.key_name} ({self.environment.name})"
    
    def clean(self):
        """Model validation."""
        if self.expires_at and self.expires_at <= timezone.now():
            raise ValidationError("Expiration date cannot be in the past.")
    
    @property
    def is_expired(self) -> bool:
        """Check if the secret is expired."""
        return bool(self.expires_at and self.expires_at <= timezone.now())
    
    # Async class methods
    @classmethod
    async def aget_by_id(cls, secret_id: str):
        try:
            return await cls.objects.aget(id=secret_id)
        except cls.DoesNotExist:
            return None
    
    @classmethod
    async def aget_by_environment(cls, environment_id: str):
        queryset = cls.objects.filter(environment_id=environment_id)
        return [secret async for secret in queryset]
    
    @classmethod
    async def aget_by_category(cls, category: str):
        queryset = cls.objects.filter(category=category)
        return [secret async for secret in queryset]
    
    @classmethod
    async def aget_active_secrets(cls):
        queryset = cls.objects.filter(is_active=True)
        return [secret async for secret in queryset]


class DeploymentHistory(models.Model):
    """
    History of application deployments.
    """
    
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('running', 'Running'),
        ('success', 'Success'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
        ('rollback', 'Rollback'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    environment = models.ForeignKey(
        EnvironmentConfig,
        on_delete=models.CASCADE,
        related_name='deployments',
        verbose_name="Environment"
    )
    version = models.CharField(
        max_length=50,
        verbose_name="Version"
    )
    commit_hash = models.CharField(
        max_length=40,
        blank=True,
        verbose_name="Commit Hash",
        validators=[RegexValidator(
            regex=r'^[a-f0-9]{40}$',
            message='Commit hash must be a 40-character hexadecimal string.'
        )]
    )
    branch = models.CharField(
        max_length=100,
        default='main',
        verbose_name="Branch"
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending',
        verbose_name="Status"
    )
    started_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Started At"
    )
    completed_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Completed At"
    )
    deployed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Deployed By"
    )
    deployment_logs = models.TextField(
        blank=True,
        verbose_name="Deployment Logs"
    )
    rollback_from = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='rollbacks',
        verbose_name="Rollback From"
    )
    artifacts_url = models.URLField(
        blank=True,
        verbose_name="Artifacts URL"
    )
    
    class Meta:
        verbose_name = "Deployment History"
        verbose_name_plural = "Deployment Histories"
        ordering = ['-started_at']
        
    def __str__(self) -> str:
        return f"{self.environment.name} - {self.version} ({self.get_status_display()})"
    
    @property
    def duration(self) -> Optional[timezone.timedelta]:
        """Deployment duration."""
        if self.completed_at:
            return self.completed_at - self.started_at
        return None
    
    # Async class methods
    @classmethod
    async def aget_by_id(cls, deployment_id: str):
        try:
            return await cls.objects.aget(id=deployment_id)
        except cls.DoesNotExist:
            return None
    
    @classmethod
    async def aget_by_environment(cls, environment_id: str, limit: int = 50):
        queryset = cls.objects.filter(environment_id=environment_id).order_by('-started_at')[:limit]
        return [deployment async for deployment in queryset]
    
    @classmethod
    async def aget_by_status(cls, status: str, limit: int = 50):
        queryset = cls.objects.filter(status=status).order_by('-started_at')[:limit]
        return [deployment async for deployment in queryset]
    
    @classmethod
    async def aget_recent_deployments(cls, limit: int = 50):
        queryset = cls.objects.all().order_by('-started_at')[:limit]
        return [deployment async for deployment in queryset]


class HealthCheck(models.Model):
    """
    Results of system health checks.
    """
    
    STATUS_CHOICES = [
        ('healthy', 'Healthy'),
        ('warning', 'Warning'),
        ('critical', 'Critical'),
        ('unknown', 'Unknown'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    environment = models.ForeignKey(
        EnvironmentConfig,
        on_delete=models.CASCADE,
        related_name='health_checks',
        verbose_name="Environment"
    )
    service_name = models.CharField(
        max_length=100,
        verbose_name="Service Name"
    )
    endpoint_url = models.URLField(
        verbose_name="Endpoint URL"
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        verbose_name="Status"
    )
    response_time = models.FloatField(
        null=True,
        blank=True,
        verbose_name="Response Time (ms)"
    )
    status_code = models.IntegerField(
        null=True,
        blank=True,
        verbose_name="HTTP Status Code"
    )
    response_data = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="Response Data"
    )
    error_message = models.TextField(
        blank=True,
        verbose_name="Error Message"
    )
    checked_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Checked At"
    )
    
    class Meta:
        verbose_name = "Health Check"
        verbose_name_plural = "Health Checks"
        ordering = ['-checked_at']
        indexes = [
            models.Index(fields=['environment', 'service_name', '-checked_at']),
            models.Index(fields=['status', '-checked_at']),
        ]
        
    def __str__(self) -> str:
        return f"{self.service_name} ({self.environment.name}) - {self.get_status_display()}"
    
    # Async class methods
    @classmethod
    async def aget_by_id(cls, check_id: str):
        try:
            return await cls.objects.aget(id=check_id)
        except cls.DoesNotExist:
            return None
    
    @classmethod
    async def aget_by_environment(cls, environment_id: str, limit: int = 100):
        queryset = cls.objects.filter(environment_id=environment_id).order_by('-checked_at')[:limit]
        return [check async for check in queryset]
    
    @classmethod
    async def aget_by_service(cls, service_name: str, limit: int = 100):
        queryset = cls.objects.filter(service_name=service_name).order_by('-checked_at')[:limit]
        return [check async for check in queryset]
    
    @classmethod
    async def aget_by_status(cls, status: str, limit: int = 100):
        queryset = cls.objects.filter(status=status).order_by('-checked_at')[:limit]
        return [check async for check in queryset]
    
    @classmethod
    async def aget_recent_checks(cls, limit: int = 100):
        queryset = cls.objects.all().order_by('-checked_at')[:limit]
        return [check async for check in queryset]


class ServiceMonitoring(models.Model):
    """
    Configuration for services being monitored.
    """
    
    SERVICE_TYPES = [
        ('web', 'Web Server'),
        ('database', 'Database'),
        ('cache', 'Cache'),
        ('queue', 'Message Queue'),
        ('storage', 'Object Storage'),
        ('proxy', 'Reverse Proxy'),
        ('monitoring', 'Monitoring'),
        ('external', 'External Service'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    environment = models.ForeignKey(
        EnvironmentConfig,
        on_delete=models.CASCADE,
        related_name='monitored_services',
        verbose_name="Environment"
    )
    service_name = models.CharField(
        max_length=100,
        verbose_name="Service Name"
    )
    service_type = models.CharField(
        max_length=20,
        choices=SERVICE_TYPES,
        verbose_name="Service Type"
    )
    health_check_url = models.URLField(
        verbose_name="Health Check URL"
    )
    check_interval = models.PositiveIntegerField(
        default=300,
        verbose_name="Check Interval (seconds)"
    )
    timeout = models.PositiveIntegerField(
        default=30,
        verbose_name="Timeout (seconds)"
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name="Is Active"
    )
    alert_on_failure = models.BooleanField(
        default=True,
        verbose_name="Alert On Failure"
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Created At"
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="Updated At"
    )
    
    class Meta:
        verbose_name = "Service Monitoring"
        verbose_name_plural = "Service Monitorings"
        unique_together = [['environment', 'service_name']]
        ordering = ['service_name']
        
    def __str__(self) -> str:
        return f"{self.service_name} ({self.environment.name})"
    
    # Async class methods
    @classmethod
    async def aget_by_id(cls, monitoring_id: str):
        try:
            return await cls.objects.aget(id=monitoring_id)
        except cls.DoesNotExist:
            return None
    
    @classmethod
    async def aget_by_environment(cls, environment_id: str):
        queryset = cls.objects.filter(environment_id=environment_id)
        return [monitoring async for monitoring in queryset]
    
    @classmethod
    async def aget_by_service_type(cls, service_type: str):
        queryset = cls.objects.filter(service_type=service_type)
        return [monitoring async for monitoring in queryset]
    
    @classmethod
    async def aget_active_monitoring(cls):
        queryset = cls.objects.filter(is_active=True)
        return [monitoring async for monitoring in queryset]