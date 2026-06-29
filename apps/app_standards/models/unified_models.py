"""
Unified Models for Integration with Unified Services.
"""

from django.db import models
from django.contrib.auth import get_user_model
from .base_models import BaseModel, StatusModel
from decimal import Decimal

User = get_user_model()


class UnifiedAuthIntegration(BaseModel):
    """
    Model for integration with unified authentication providers.
    """
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='auth_integrations',
        verbose_name='User'
    )
    token_type = models.CharField(
        max_length=20,
        choices=[
            ('access', 'Access Token'),
            ('refresh', 'Refresh Token'),
            ('otp', 'OTP Token'),
        ],
        verbose_name='Token Type'
    )
    token_value = models.TextField(
        verbose_name='Token Value'
    )
    expires_at = models.DateTimeField(
        verbose_name='Expires At'
    )
    metadata = models.JSONField(
        default=dict,
        blank=True,
        verbose_name='Metadata'
    )
    
    class Meta:
        verbose_name = 'Unified Auth Integration'
        verbose_name_plural = 'Unified Auth Integrations'
        indexes = [
            models.Index(fields=['user', 'token_type']),
            models.Index(fields=['expires_at']),
        ]


class UnifiedBillingIntegration(StatusModel):
    """
    Model for integration with unified billing providers.
    """
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('refunded', 'Refunded'),
    ]
    
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='billing_transactions',
        verbose_name='User'
    )
    transaction_type = models.CharField(
        max_length=30,
        choices=[
            ('payment', 'Payment'),
            ('withdrawal', 'Withdrawal'),
            ('refund', 'Refund'),
            ('subscription', 'Subscription'),
        ],
        verbose_name='Transaction Type'
    )
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        verbose_name='Amount'
    )
    gateway = models.CharField(
        max_length=20,
        choices=[
            ('stripe', 'Stripe'),
            ('paystack', 'Paystack'),
            ('wallet', 'Wallet'),
            ('other', 'Other'),
        ],
        verbose_name='Payment Gateway'
    )
    reference_id = models.CharField(
        max_length=100,
        unique=True,
        verbose_name='Reference ID'
    )
    gateway_reference = models.CharField(
        max_length=100,
        blank=True,
        verbose_name='Gateway Reference'
    )
    description = models.TextField(
        blank=True,
        verbose_name='Description'
    )
    metadata = models.JSONField(
        default=dict,
        blank=True,
        verbose_name='Metadata'
    )
    
    class Meta:
        verbose_name = 'Unified Billing Transaction'
        verbose_name_plural = 'Unified Billing Transactions'
        indexes = [
            models.Index(fields=['reference_id']),
            models.Index(fields=['user', 'transaction_type', '-created_at']),
        ]
    
    @property
    def amount_display(self):
        """Format amount with standard currency."""
        return f"${self.amount:,.2f}"


class UnifiedAIUsage(BaseModel):
    """
    Model for tracking AI Engine usage (Ollama, CLIP, LangGraph, etc.).
    """
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='ai_usage',
        verbose_name='User'
    )
    service_type = models.CharField(
        max_length=30,
        choices=[
            ('chat', 'Chat Assistant'),
            ('text_generation', 'Text Generation'),
            ('embedding', 'Vector Embedding'),
            ('image_analysis', 'Image Analysis'),
        ],
        verbose_name='Service Type'
    )
    model_name = models.CharField(
        max_length=50,
        verbose_name='Model Name'
    )
    input_tokens = models.IntegerField(
        default=0,
        verbose_name='Input Tokens'
    )
    output_tokens = models.IntegerField(
        default=0,
        verbose_name='Output Tokens'
    )
    processing_time = models.FloatField(
        verbose_name='Processing Time (Seconds)'
    )
    cost = models.DecimalField(
        max_digits=10,
        decimal_places=4,
        default=Decimal('0.0000'),
        verbose_name='Cost'
    )
    request_data = models.JSONField(
        default=dict,
        verbose_name='Request Data'
    )
    response_data = models.JSONField(
        default=dict,
        verbose_name='Response Data'
    )
    success = models.BooleanField(
        default=True,
        verbose_name='Success'
    )
    error_message = models.TextField(
        blank=True,
        verbose_name='Error Message'
    )
    
    class Meta:
        verbose_name = 'Unified AI Usage'
        verbose_name_plural = 'Unified AI Usages'
        indexes = [
            models.Index(fields=['user', 'service_type', '-created_at']),
            models.Index(fields=['model_name', '-created_at']),
        ]
    
    @property
    def total_tokens(self):
        """Calculate total tokens used."""
        return self.input_tokens + self.output_tokens


class UnifiedAccessPermission(BaseModel):
    """
    Model for managing custom resource access permissions.
    """
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='custom_permissions',
        verbose_name='User'
    )
    resource_type = models.CharField(
        max_length=50,
        verbose_name='Resource Type'
    )
    resource_id = models.CharField(
        max_length=100,
        verbose_name='Resource ID'
    )
    permission_type = models.CharField(
        max_length=20,
        choices=[
            ('view', 'View'),
            ('edit', 'Edit'),
            ('delete', 'Delete'),
            ('share', 'Share'),
            ('admin', 'Admin'),
        ],
        verbose_name='Permission Type'
    )
    granted_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='permissions_granted',
        verbose_name='Granted By'
    )
    expires_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='Expires At'
    )
    conditions = models.JSONField(
        default=dict,
        blank=True,
        verbose_name='Conditions'
    )
    
    class Meta:
        verbose_name = 'Unified Access Permission'
        verbose_name_plural = 'Unified Access Permissions'
        unique_together = [['user', 'resource_type', 'resource_id', 'permission_type']]
        indexes = [
            models.Index(fields=['user', 'resource_type']),
            models.Index(fields=['expires_at']),
        ]


class UnifiedNotification(StatusModel):
    """
    Model for system notifications tracking.
    """
    STATUS_CHOICES = [
        ('pending', 'Pending Send'),
        ('sent', 'Sent'),
        ('delivered', 'Delivered'),
        ('read', 'Read'),
        ('failed', 'Failed'),
    ]
    
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='notifications',
        verbose_name='User'
    )
    notification_type = models.CharField(
        max_length=30,
        choices=[
            ('sms', 'SMS'),
            ('email', 'Email'),
            ('push', 'Push Notification'),
            ('in_app', 'In App'),
        ],
        verbose_name='Notification Type'
    )
    title = models.CharField(
        max_length=200,
        verbose_name='Title'
    )
    content = models.TextField(
        verbose_name='Content'
    )
    priority = models.CharField(
        max_length=10,
        choices=[
            ('low', 'Low'),
            ('normal', 'Normal'),
            ('high', 'High'),
            ('urgent', 'Urgent'),
        ],
        default='normal',
        verbose_name='Priority'
    )
    scheduled_for = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='Scheduled For'
    )
    sent_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='Sent At'
    )
    read_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='Read At'
    )
    metadata = models.JSONField(
        default=dict,
        blank=True,
        verbose_name='Metadata'
    )
    
    class Meta:
        verbose_name = 'Unified Notification'
        verbose_name_plural = 'Unified Notifications'
        indexes = [
            models.Index(fields=['user', 'status', '-created_at']),
            models.Index(fields=['notification_type', 'status']),
            models.Index(fields=['scheduled_for']),
        ]
    
    def mark_as_read(self):
        """Mark notification as read."""
        self.status = 'read'
        self.read_at = timezone.now()
        self.save(update_fields=['status', 'read_at', 'updated_at'])


class UnifiedRateLimit(BaseModel):
    """
    Model for request rate limits.
    """
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='rate_limits',
        verbose_name='User'
    )
    endpoint = models.CharField(
        max_length=200,
        verbose_name='Endpoint'
    )
    limit_type = models.CharField(
        max_length=20,
        choices=[
            ('api_call', 'API Call'),
            ('ai_request', 'AI Request'),
            ('file_upload', 'File Upload'),
            ('sms_send', 'SMS Send'),
        ],
        verbose_name='Limit Type'
    )
    window_minutes = models.IntegerField(
        default=60,
        verbose_name='Window (Minutes)'
    )
    max_requests = models.IntegerField(
        verbose_name='Max Requests'
    )
    current_count = models.IntegerField(
        default=0,
        verbose_name='Current Count'
    )
    window_start = models.DateTimeField(
        verbose_name='Window Start'
    )
    
    class Meta:
        verbose_name = 'Unified Rate Limit'
        verbose_name_plural = 'Unified Rate Limits'
        unique_together = [['user', 'endpoint', 'limit_type']]
        indexes = [
            models.Index(fields=['user', 'limit_type']),
            models.Index(fields=['window_start']),
        ]
    
    def is_limit_exceeded(self):
        """Check if request limit is exceeded."""
        window_end = self.window_start + timezone.timedelta(minutes=self.window_minutes)
        if timezone.now() > window_end:
            self.window_start = timezone.now()
            self.current_count = 0
            self.save(update_fields=['window_start', 'current_count'])
            return False
        
        return self.current_count >= self.max_requests
    
    def increment(self):
        """Increment request counter."""
        self.current_count += 1
        self.save(update_fields=['current_count'])


def example_unified_integration():
    """Example of using unified models."""
    user = User.objects.first()
    if not user:
        return
    
    ai_usage = UnifiedAIUsage.objects.create(
        user=user,
        service_type='chat',
        model_name='llama3.2:3b',
        input_tokens=150,
        output_tokens=200,
        processing_time=2.5,
        cost=Decimal('0.0000'),
        request_data={'prompt': 'What fit advice do you have for size M?'},
        response_data={'text': 'For size M, we suggest checking the measurements...'}
    )
    
    transaction = UnifiedBillingIntegration.objects.create(
        user=user,
        transaction_type='payment',
        amount=50.00,
        gateway='stripe',
        reference_id='TX123456',
        description='Payment for custom dress tailoring'
    )
    
    notification = UnifiedNotification.objects.create(
        user=user,
        notification_type='sms',
        title='Order Shipped',
        content='Your dress is on the way!',
        priority='high',
        scheduled_for=timezone.now() + timezone.timedelta(hours=12)
    )