"""
Integrations Models for Fashionistar.
"""

from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.core.validators import RegexValidator
import uuid

User = get_user_model()


class IntegrationProvider(models.Model):
    """
    Integration Provider model representing external APIs and third-party services.
    """
    PROVIDER_TYPES = [
        ('sms', 'SMS'),
        ('payment', 'Payment Gateway'),
        ('ai', 'Artificial Intelligence'),
        ('storage', 'Cloud Storage'),
        ('notification', 'Notification Services'),
        ('analytics', 'Analytics Platforms'),
        ('other', 'Other Services'),
    ]
    
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('inactive', 'Inactive'),
        ('maintenance', 'Under Maintenance'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(
        max_length=100,
        unique=True,
        verbose_name='Provider Name'
    )
    slug = models.SlugField(
        max_length=50,
        unique=True,
        verbose_name='Unique Slug'
    )
    provider_type = models.CharField(
        max_length=20,
        choices=PROVIDER_TYPES,
        verbose_name='Service Type'
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='active',
        verbose_name='Status'
    )
    description = models.TextField(
        blank=True,
        verbose_name='Description'
    )
    api_base_url = models.URLField(
        blank=True,
        verbose_name='API Base URL'
    )
    documentation_url = models.URLField(
        blank=True,
        verbose_name='Documentation URL'
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Created At')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Updated At')
    
    class Meta:
        verbose_name = 'Integration Provider'
        verbose_name_plural = 'Integration Providers'
        ordering = ['name']
    
    def __str__(self):
        return f"{self.name} ({self.get_provider_type_display()})"


class IntegrationCredential(models.Model):
    """
    Credentials and API keys storage for Integration Providers.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    provider = models.ForeignKey(
        IntegrationProvider,
        on_delete=models.CASCADE,
        related_name='credentials',
        verbose_name='Provider'
    )
    key_name = models.CharField(
        max_length=100,
        verbose_name='Key Name'
    )
    key_value = models.TextField(
        verbose_name='Key Value',
        help_text='Stored in encrypted format.'
    )
    is_encrypted = models.BooleanField(
        default=True,
        verbose_name='Is Encrypted'
    )
    environment = models.CharField(
        max_length=20,
        choices=[
            ('development', 'Development'),
            ('staging', 'Staging'),
            ('production', 'Production'),
        ],
        default='production',
        verbose_name='Environment'
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name='Is Active'
    )
    expires_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='Expires At'
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Created At')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Updated At')
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_credentials',
        verbose_name='Created By'
    )
    
    class Meta:
        verbose_name = 'Integration Credential'
        verbose_name_plural = 'Integration Credentials'
        unique_together = ['provider', 'key_name', 'environment']
        ordering = ['provider', 'key_name']
    
    def __str__(self):
        return f"{self.provider.name} - {self.key_name}"
    
    def is_valid(self) -> bool:
        if not self.is_active:
            return False
        if self.expires_at and self.expires_at < timezone.now():
            return False
        return True


class IntegrationLog(models.Model):
    """
    Logs API calls and transactions with integration providers.
    """
    LOG_LEVELS = [
        ('debug', 'Debug'),
        ('info', 'Info'),
        ('warning', 'Warning'),
        ('error', 'Error'),
        ('critical', 'Critical'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    provider = models.ForeignKey(
        IntegrationProvider,
        on_delete=models.CASCADE,
        related_name='logs',
        verbose_name='Provider'
    )
    log_level = models.CharField(
        max_length=20,
        choices=LOG_LEVELS,
        default='info',
        verbose_name='Log Level'
    )
    service_name = models.CharField(
        max_length=100,
        verbose_name='Service Name'
    )
    action = models.CharField(
        max_length=100,
        verbose_name='Action'
    )
    request_data = models.JSONField(
        default=dict,
        blank=True,
        verbose_name='Request Data'
    )
    response_data = models.JSONField(
        default=dict,
        blank=True,
        verbose_name='Response Data'
    )
    error_message = models.TextField(
        blank=True,
        verbose_name='Error Message'
    )
    status_code = models.IntegerField(
        null=True,
        blank=True,
        verbose_name='Status Code'
    )
    duration_ms = models.IntegerField(
        null=True,
        blank=True,
        verbose_name='Duration (ms)'
    )
    user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='integration_logs',
        verbose_name='User'
    )
    ip_address = models.GenericIPAddressField(
        null=True,
        blank=True,
        verbose_name='IP Address'
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Logged At',
        db_index=True
    )
    
    class Meta:
        verbose_name = 'Integration Log'
        verbose_name_plural = 'Integration Logs'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['provider', 'created_at']),
            models.Index(fields=['log_level', 'created_at']),
        ]
    
    def __str__(self):
        return f"{self.provider.name} - {self.action} - {self.created_at}"


class WebhookEndpoint(models.Model):
    """
    Webhook endpoints configured to receive external callbacks.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    provider = models.ForeignKey(
        IntegrationProvider,
        on_delete=models.CASCADE,
        related_name='webhooks',
        verbose_name='Provider'
    )
    name = models.CharField(
        max_length=100,
        verbose_name='Webhook Name'
    )
    endpoint_url = models.CharField(
        max_length=255,
        unique=True,
        verbose_name='Endpoint URL',
        validators=[
            RegexValidator(
                regex=r'^[a-zA-Z0-9-_/]+$',
                message='Endpoint URL can only contain letters, numbers, hyphens and underscores.'
            )
        ]
    )
    secret_key = models.CharField(
        max_length=255,
        verbose_name='Secret Key',
        help_text='Used to verify webhook payload signatures.'
    )
    events = models.JSONField(
        default=list,
        verbose_name='Subscribed Events',
        help_text='List of event slugs this webhook processes.'
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name='Is Active'
    )
    retry_count = models.IntegerField(
        default=3,
        verbose_name='Retry Count'
    )
    timeout_seconds = models.IntegerField(
        default=30,
        verbose_name='Timeout (Seconds)'
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Created At')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Updated At')
    
    class Meta:
        verbose_name = 'Webhook Endpoint'
        verbose_name_plural = 'Webhook Endpoints'
        ordering = ['provider', 'name']
    
    def __str__(self):
        return f"{self.provider.name} - {self.name}"


class WebhookEvent(models.Model):
    """
    Captured webhook event data for processing.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    webhook = models.ForeignKey(
        WebhookEndpoint,
        on_delete=models.CASCADE,
        related_name='events_received',
        verbose_name='Webhook'
    )
    event_type = models.CharField(
        max_length=100,
        verbose_name='Event Type'
    )
    payload = models.JSONField(
        default=dict,
        verbose_name='Payload'
    )
    headers = models.JSONField(
        default=dict,
        verbose_name='Headers'
    )
    signature = models.CharField(
        max_length=255,
        blank=True,
        verbose_name='Signature'
    )
    is_valid = models.BooleanField(
        default=True,
        verbose_name='Is Signature Valid'
    )
    is_processed = models.BooleanField(
        default=False,
        verbose_name='Is Processed'
    )
    processed_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='Processed At'
    )
    error_message = models.TextField(
        blank=True,
        verbose_name='Error Message'
    )
    retry_count = models.IntegerField(
        default=0,
        verbose_name='Retry Count'
    )
    received_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Received At'
    )
    
    class Meta:
        verbose_name = 'Webhook Event'
        verbose_name_plural = 'Webhook Events'
        ordering = ['-received_at']
        indexes = [
            models.Index(fields=['webhook', 'received_at']),
            models.Index(fields=['is_processed', 'received_at']),
        ]
    
    def __str__(self):
        return f"{self.webhook.name} - {self.event_type} - {self.received_at}"


class RateLimitRule(models.Model):
    """
    System rules configuration for rate limiting external API integrations.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    provider = models.ForeignKey(
        IntegrationProvider,
        on_delete=models.CASCADE,
        related_name='rate_limits',
        verbose_name='Provider'
    )
    name = models.CharField(
        max_length=100,
        verbose_name='Rule Name'
    )
    endpoint_pattern = models.CharField(
        max_length=255,
        verbose_name='Endpoint Pattern',
        help_text='Supports wildcards like *'
    )
    max_requests = models.IntegerField(
        verbose_name='Max Requests'
    )
    time_window_seconds = models.IntegerField(
        verbose_name='Time Window (Seconds)'
    )
    scope = models.CharField(
        max_length=20,
        choices=[
            ('global', 'Global'),
            ('user', 'User'),
            ('ip', 'IP Address'),
        ],
        default='user',
        verbose_name='Scope'
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name='Is Active'
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Created At')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Updated At')
    
    class Meta:
        verbose_name = 'Rate Limit Rule'
        verbose_name_plural = 'Rate Limit Rules'
        ordering = ['provider', 'name']
    
    def __str__(self):
        return f"{self.provider.name} - {self.name} ({self.max_requests}/{self.time_window_seconds}s)"