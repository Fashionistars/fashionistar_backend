"""
Analytics Models for metrics storage and activity tracking.
"""

import logging
from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone

logger = logging.getLogger(__name__)
User = get_user_model()


class Metric(models.Model):
    """
    Model for general system telemetry and logging metrics.
    """
    METRIC_TYPE_CHOICES = [
        ('counter', 'Counter'),
        ('gauge', 'Gauge'),
        ('histogram', 'Histogram'),
        ('timer', 'Timer'),
    ]
    
    name = models.CharField(
        max_length=255,
        verbose_name='Metric Name',
        help_text='Name identifier of the metric.'
    )
    metric_type = models.CharField(
        max_length=20,
        choices=METRIC_TYPE_CHOICES,
        default='gauge',
        verbose_name='Metric Type'
    )
    value = models.FloatField(
        verbose_name='Value',
        help_text='Numeric value of the metric.'
    )
    tags = models.JSONField(
        default=dict,
        blank=True,
        verbose_name='Tags',
        help_text='Categorization tags.'
    )
    timestamp = models.DateTimeField(
        default=timezone.now,
        verbose_name='Timestamp'
    )
    
    class Meta:
        verbose_name = 'Metric'
        verbose_name_plural = 'Metrics'
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['name', 'timestamp']),
            models.Index(fields=['metric_type', 'timestamp']),
        ]
    
    def __str__(self):
        return f"{self.name}: {self.value} ({self.timestamp})"


class UserActivity(models.Model):
    """
    Tracks and audits client and vendor interactions on the platform.
    """
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        verbose_name='User'
    )
    action = models.CharField(
        max_length=100,
        verbose_name='Action Performed',
        help_text='Type of action performed by the user.'
    )
    resource = models.CharField(
        max_length=100,
        blank=True,
        verbose_name='Resource Name',
        help_text='Affected resource or area of interaction.'
    )
    resource_id = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name='Resource ID'
    )
    ip_address = models.GenericIPAddressField(
        null=True,
        blank=True,
        verbose_name='IP Address'
    )
    user_agent = models.TextField(
        blank=True,
        verbose_name='User Agent'
    )
    session_id = models.CharField(
        max_length=40,
        blank=True,
        verbose_name='Session ID'
    )
    metadata = models.JSONField(
        default=dict,
        blank=True,
        verbose_name='Metadata'
    )
    timestamp = models.DateTimeField(
        default=timezone.now,
        verbose_name='Action Time'
    )
    
    class Meta:
        verbose_name = 'User Activity'
        verbose_name_plural = 'User Activities'
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['user', 'timestamp']),
            models.Index(fields=['action', 'timestamp']),
            models.Index(fields=['resource', 'timestamp']),
        ]
    
    def __str__(self):
        return f"{self.user.phone_number}: {self.action} ({self.timestamp})"


class PerformanceMetric(models.Model):
    """
    Audits HTTP request durations and API latencies.
    """
    endpoint = models.CharField(
        max_length=255,
        verbose_name='Endpoint Route',
        help_text='Request URL pathway.'
    )
    method = models.CharField(
        max_length=10,
        verbose_name='HTTP Method',
        help_text='HTTP verb used in the request.'
    )
    response_time_ms = models.PositiveIntegerField(
        verbose_name='Response Time (ms)'
    )
    status_code = models.PositiveIntegerField(
        verbose_name='HTTP Status Code'
    )
    user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name='User'
    )
    error_message = models.TextField(
        blank=True,
        verbose_name='Error Message'
    )
    metadata = models.JSONField(
        default=dict,
        blank=True,
        verbose_name='Metadata'
    )
    timestamp = models.DateTimeField(
        default=timezone.now,
        verbose_name='Timestamp'
    )
    
    class Meta:
        verbose_name = 'Performance Metric'
        verbose_name_plural = 'Performance Metrics'
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['endpoint', 'timestamp']),
            models.Index(fields=['status_code', 'timestamp']),
            models.Index(fields=['response_time_ms']),
        ]
    
    def __str__(self):
        return f"{self.method} {self.endpoint}: {self.response_time_ms}ms ({self.status_code})"


class BusinessMetric(models.Model):
    """
    Stores key business aggregates (sales, volume, active listings) over defined intervals.
    """
    metric_name = models.CharField(
        max_length=100,
        verbose_name='Business Metric Name'
    )
    value = models.FloatField(
        verbose_name='Value'
    )
    period_start = models.DateTimeField(
        verbose_name='Period Start'
    )
    period_end = models.DateTimeField(
        verbose_name='Period End'
    )
    metadata = models.JSONField(
        default=dict,
        blank=True,
        verbose_name='Metadata'
    )
    created_at = models.DateTimeField(
        default=timezone.now,
        verbose_name='Created At'
    )
    
    class Meta:
        verbose_name = 'Business Metric'
        verbose_name_plural = 'Business Metrics'
        ordering = ['-created_at']
        unique_together = ['metric_name', 'period_start', 'period_end']
        indexes = [
            models.Index(fields=['metric_name', 'period_start']),
            models.Index(fields=['created_at']),
        ]
    
    def __str__(self):
        return f"{self.metric_name}: {self.value} ({self.period_start.date()})"


class AlertRule(models.Model):
    """
    Defines threshold monitoring and severity guidelines.
    """
    OPERATOR_CHOICES = [
        ('gt', 'Greater Than'),
        ('gte', 'Greater Than or Equal'),
        ('lt', 'Less Than'),
        ('lte', 'Less Than or Equal'),
        ('eq', 'Equal'),
        ('ne', 'Not Equal'),
    ]
    
    SEVERITY_CHOICES = [
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('critical', 'Critical'),
    ]
    
    name = models.CharField(
        max_length=100,
        verbose_name='Rule Name'
    )
    metric_name = models.CharField(
        max_length=255,
        verbose_name='Metric Name'
    )
    operator = models.CharField(
        max_length=5,
        choices=OPERATOR_CHOICES,
        verbose_name='Comparison Operator'
    )
    threshold = models.FloatField(
        verbose_name='Threshold'
    )
    severity = models.CharField(
        max_length=10,
        choices=SEVERITY_CHOICES,
        default='medium',
        verbose_name='Severity'
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name='Is Active'
    )
    description = models.TextField(
        blank=True,
        verbose_name='Description'
    )
    created_at = models.DateTimeField(
        default=timezone.now,
        verbose_name='Created At'
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name='Updated At'
    )
    
    class Meta:
        verbose_name = 'Alert Rule'
        verbose_name_plural = 'Alert Rules'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['metric_name', 'is_active']),
        ]
    
    def __str__(self):
        return f"{self.name}: {self.metric_name} {self.operator} {self.threshold}"


class Alert(models.Model):
    """
    Triggered alerts when rules threshold values are exceeded.
    """
    STATUS_CHOICES = [
        ('firing', 'Firing'),
        ('resolved', 'Resolved'),
        ('suppressed', 'Suppressed'),
    ]
    
    rule = models.ForeignKey(
        AlertRule,
        on_delete=models.CASCADE,
        verbose_name='Alert Rule'
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='firing',
        verbose_name='Status'
    )
    metric_value = models.FloatField(
        verbose_name='Current Value'
    )
    message = models.TextField(
        verbose_name='Alert Message'
    )
    metadata = models.JSONField(
        default=dict,
        blank=True,
        verbose_name='Metadata'
    )
    fired_at = models.DateTimeField(
        default=timezone.now,
        verbose_name='Triggered At'
    )
    resolved_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='Resolved At'
    )
    
    class Meta:
        verbose_name = 'Alert'
        verbose_name_plural = 'Alerts'
        ordering = ['-fired_at']
        indexes = [
            models.Index(fields=['rule', 'status']),
            models.Index(fields=['status', 'fired_at']),
        ]
    
    def __str__(self):
        return f"{self.rule.name}: {self.status} ({self.fired_at})"