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
    
    # Async class methods
    @classmethod
    async def aget_by_id(cls, metric_id: int):
        try:
            return await cls.objects.aget(id=metric_id)
        except cls.DoesNotExist:
            return None
    
    @classmethod
    async def aget_by_name(
        cls, name: str, date_from=None, date_to=None, limit: int = 100
    ):
        queryset = cls.objects.filter(name=name)
        if date_from:
            queryset = queryset.filter(timestamp__gte=date_from)
        if date_to:
            queryset = queryset.filter(timestamp__lte=date_to)
        return [m async for m in queryset.order_by('-timestamp')[:limit]]
    
    @classmethod
    async def aget_by_type(
        cls, metric_type: str, date_from=None, date_to=None, limit: int = 100
    ):
        queryset = cls.objects.filter(metric_type=metric_type)
        if date_from:
            queryset = queryset.filter(timestamp__gte=date_from)
        if date_to:
            queryset = queryset.filter(timestamp__lte=date_to)
        return [m async for m in queryset.order_by('-timestamp')[:limit]]
    
    @classmethod
    async def aget_latest(cls, limit: int = 10):
        return [m async for m in cls.objects.order_by('-timestamp')[:limit]]
    
    @classmethod
    async def acreate_from_dict(cls, data: dict):
        return await cls.objects.acreate(**data)
    
    @classmethod
    async def aget_recent_metrics(cls, hours: int = 24, limit: int = 100):
        from datetime import timedelta
        since = timezone.now() - timedelta(hours=hours)
        queryset = cls.objects.filter(timestamp__gte=since).order_by('-timestamp')[:limit]
        return [m async for m in queryset]


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
        user_ident = self.user.email or self.user.phone or "Unknown"
        return f"{user_ident}: {self.action} ({self.timestamp})"
    
    # Async class methods
    @classmethod
    async def aget_by_id(cls, activity_id: int):
        try:
            return await cls.objects.aget(id=activity_id)
        except cls.DoesNotExist:
            return None
    
    @classmethod
    async def aget_by_user(
        cls, user_id: str, date_from=None, date_to=None, limit: int = 100
    ):
        queryset = cls.objects.filter(user_id=user_id)
        if date_from:
            queryset = queryset.filter(timestamp__gte=date_from)
        if date_to:
            queryset = queryset.filter(timestamp__lte=date_to)
        return [a async for a in queryset.order_by('-timestamp')[:limit]]
    
    @classmethod
    async def aget_by_action(
        cls, action: str, date_from=None, date_to=None, limit: int = 100
    ):
        queryset = cls.objects.filter(action=action)
        if date_from:
            queryset = queryset.filter(timestamp__gte=date_from)
        if date_to:
            queryset = queryset.filter(timestamp__lte=date_to)
        return [a async for a in queryset.order_by('-timestamp')[:limit]]
    
    @classmethod
    async def aget_analytics_summary(cls, date_from, date_to):
        from django.db.models import Count
        queryset = cls.objects.filter(timestamp__range=(date_from, date_to))
        result = await queryset.aaggregate(
            total_activities=Count('id'),
            unique_users=Count('user', distinct=True),
            unique_actions=Count('action', distinct=True)
        )
        return result
    
    @classmethod
    async def aget_recent_activities(cls, hours: int = 24, limit: int = 100):
        from datetime import timedelta
        since = timezone.now() - timedelta(hours=hours)
        queryset = cls.objects.filter(timestamp__gte=since).order_by('-timestamp')[:limit]
        return [a async for a in queryset]


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
    
    # Async class methods
    @classmethod
    async def aget_by_id(cls, metric_id: int):
        try:
            return await cls.objects.aget(id=metric_id)
        except cls.DoesNotExist:
            return None
    
    @classmethod
    async def aget_by_endpoint(
        cls, endpoint: str, date_from=None, date_to=None, limit: int = 100
    ):
        queryset = cls.objects.filter(endpoint=endpoint)
        if date_from:
            queryset = queryset.filter(timestamp__gte=date_from)
        if date_to:
            queryset = queryset.filter(timestamp__lte=date_to)
        return [p async for p in queryset.order_by('-timestamp')[:limit]]
    
    @classmethod
    async def aget_slow_queries(
        cls, threshold_ms: int, date_from=None, date_to=None, limit: int = 50
    ):
        queryset = cls.objects.filter(response_time_ms__gte=threshold_ms)
        if date_from:
            queryset = queryset.filter(timestamp__gte=date_from)
        if date_to:
            queryset = queryset.filter(timestamp__lte=date_to)
        return [p async for p in queryset.order_by('-response_time_ms')[:limit]]
    
    @classmethod
    async def aget_performance_summary(cls, date_from, date_to):
        from django.db.models import Count, Avg, Max, Q
        queryset = cls.objects.filter(timestamp__range=(date_from, date_to))
        result = await queryset.aaggregate(
            total_requests=Count('id'),
            avg_response_time=Avg('response_time_ms'),
            max_response_time=Max('response_time_ms'),
            error_rate=Count('id', filter=~Q(status_code__range=(200, 299)))
        )
        return result
    
    @classmethod
    async def aget_by_user(cls, user_id: str, limit: int = 100):
        queryset = cls.objects.filter(user_id=user_id).order_by('-timestamp')[:limit]
        return [m async for m in queryset]
    
    @classmethod
    async def aget_recent_metrics(cls, hours: int = 24, limit: int = 100):
        from datetime import timedelta
        since = timezone.now() - timedelta(hours=hours)
        queryset = cls.objects.filter(timestamp__gte=since).order_by('-timestamp')[:limit]
        return [m async for m in queryset]


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
    
    # Async class methods
    @classmethod
    async def aget_by_id(cls, metric_id: int):
        try:
            return await cls.objects.aget(id=metric_id)
        except cls.DoesNotExist:
            return None
    
    @classmethod
    async def aget_by_name(
        cls, metric_name: str, period_start=None, period_end=None
    ):
        queryset = cls.objects.filter(metric_name=metric_name)
        if period_start:
            queryset = queryset.filter(period_start__gte=period_start)
        if period_end:
            queryset = queryset.filter(period_end__lte=period_end)
        return [b async for b in queryset.order_by('-period_start')]
    
    @classmethod
    async def aget_trend(cls, metric_name: str, periods: int = 12):
        queryset = cls.objects.filter(metric_name=metric_name).order_by('-period_start')[:periods]
        return [b async for b in queryset]
    
    @classmethod
    async def aget_by_period(cls, period_start, period_end):
        queryset = cls.objects.filter(
            period_start=period_start,
            period_end=period_end
        )
        return [m async for m in queryset]
    
    @classmethod
    async def aget_recent_metrics(cls, days: int = 30, limit: int = 100):
        from datetime import timedelta
        since = timezone.now() - timedelta(days=days)
        queryset = cls.objects.filter(created_at__gte=since).order_by('-created_at')[:limit]
        return [m async for m in queryset]


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
    
    # Async class methods
    @classmethod
    async def aget_by_id(cls, rule_id: int):
        try:
            return await cls.objects.aget(id=rule_id)
        except cls.DoesNotExist:
            return None
    
    @classmethod
    async def aget_active_rules(cls):
        queryset = cls.objects.filter(is_active=True).order_by('-created_at')
        return [r async for r in queryset]
    
    @classmethod
    async def aget_by_severity(cls, severity: str):
        return [r async for r in cls.objects.filter(severity=severity, is_active=True)]
    
    @classmethod
    async def aget_by_metric(cls, metric_name: str):
        queryset = cls.objects.filter(metric_name=metric_name)
        return [r async for r in queryset]


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
    
    # Async class methods
    @classmethod
    async def aget_by_id(cls, alert_id: int):
        try:
            return await cls.objects.aget(id=alert_id)
        except cls.DoesNotExist:
            return None
    
    @classmethod
    async def aget_by_rule(
        cls, rule_id: int, date_from=None, date_to=None, limit: int = 100
    ):
        queryset = cls.objects.filter(rule_id=rule_id)
        if date_from:
            queryset = queryset.filter(fired_at__gte=date_from)
        if date_to:
            queryset = queryset.filter(fired_at__lte=date_to)
        return [a async for a in queryset.order_by('-fired_at')[:limit]]
    
    @classmethod
    async def aget_by_status(cls, status: str, limit: int = 100):
        queryset = cls.objects.filter(status=status).order_by('-fired_at')[:limit]
        return [a async for a in queryset]
    
    @classmethod
    async def aget_firing_alerts(cls, limit: int = 100):
        queryset = cls.objects.filter(status='firing').order_by('-fired_at')[:limit]
        return [a async for a in queryset]
    
    async def aresolve(self, resolution_notes: str = None):
        self.status = 'resolved'
        self.resolved_at = timezone.now()
        if resolution_notes:
            self.message = resolution_notes
        await self.asave(update_fields=['status', 'resolved_at', 'message'])