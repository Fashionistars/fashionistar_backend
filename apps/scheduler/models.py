# apps/scheduler/models.py
"""
Scheduler app models.
Manages tasks, scheduled runs, execution logs, and performance metrics.
"""

from __future__ import annotations

import uuid
from django.db import models
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.core.validators import MinValueValidator
from apps.common.models import SoftDeleteModel

User = get_user_model()


class TaskDefinition(SoftDeleteModel):
    """
    Definitions of tasks available for execution in the system.
    """
    TASK_TYPES = [
        ('cleanup', 'Cleanup'),
        ('report', 'Reporting'),
        ('notification', 'Notification'),
        ('backup', 'Backup'),
        ('sync', 'Synchronization'),
        ('analytics', 'Analytics'),
        ('health_check', 'Health Check'),
        ('custom', 'Custom'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(
        max_length=200,
        unique=True,
        verbose_name='Task Name'
    )
    task_path = models.CharField(
        max_length=500,
        verbose_name='Function Path',
        help_text='Example: app_name.tasks.function_name'
    )
    task_type = models.CharField(
        max_length=20,
        choices=TASK_TYPES,
        default='custom',
        verbose_name='Task Type'
    )
    description = models.TextField(
        blank=True,
        verbose_name='Description'
    )
    default_params = models.JSONField(
        default=dict,
        blank=True,
        verbose_name='Default Parameters'
    )
    queue_name = models.CharField(
        max_length=100,
        default='default',
        verbose_name='Queue Name'
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name='Is Active'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_task_definitions',
        verbose_name='Created By'
    )
    
    class Meta:
        verbose_name = 'Task Definition'
        verbose_name_plural = 'Task Definitions'
        ordering = ['task_type', 'name']
    
    def __str__(self):
        return f"{self.name} ({self.get_task_type_display()})"


class ScheduledTask(SoftDeleteModel):
    """
    Scheduled task configurations.
    """
    SCHEDULE_TYPES = [
        ('once', 'Once'),
        ('interval', 'Interval'),
        ('cron', 'Cron Expression'),
        ('daily', 'Daily'),
        ('weekly', 'Weekly'),
        ('monthly', 'Monthly'),
    ]
    
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('paused', 'Paused'),
        ('expired', 'Expired'),
        ('disabled', 'Disabled'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    task_definition = models.ForeignKey(
        TaskDefinition,
        on_delete=models.CASCADE,
        related_name='scheduled_tasks',
        verbose_name='Task Definition'
    )
    name = models.CharField(
        max_length=200,
        verbose_name='Schedule Name'
    )
    schedule_type = models.CharField(
        max_length=20,
        choices=SCHEDULE_TYPES,
        verbose_name='Schedule Type'
    )
    
    # One-off schedule
    one_off_datetime = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='Execution Time'
    )
    
    # Interval schedule
    interval_seconds = models.IntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1)],
        verbose_name='Interval (seconds)'
    )
    
    # Cron schedule
    cron_expression = models.CharField(
        max_length=200,
        blank=True,
        verbose_name='Cron Expression',
        help_text='Example: 0 0 * * * (Every day at midnight)'
    )
    
    # Execution parameters
    params = models.JSONField(
        default=dict,
        blank=True,
        verbose_name='Parameters'
    )
    
    # Status and controls
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='active',
        verbose_name='Status'
    )
    priority = models.IntegerField(
        default=5,
        validators=[MinValueValidator(1)],
        verbose_name='Priority',
        help_text='1=Highest, 10=Lowest'
    )
    max_retries = models.IntegerField(
        default=3,
        validators=[MinValueValidator(0)],
        verbose_name='Max Retries'
    )
    retry_delay = models.IntegerField(
        default=60,
        validators=[MinValueValidator(1)],
        verbose_name='Retry Delay (seconds)'
    )
    
    # Start and end boundaries
    start_datetime = models.DateTimeField(
        default=timezone.now,
        verbose_name='Start Time'
    )
    end_datetime = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='End Time'
    )
    
    # Execution statistics
    last_run_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='Last Run'
    )
    next_run_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='Next Run'
    )
    total_run_count = models.IntegerField(
        default=0,
        verbose_name='Total Run Count'
    )
    success_count = models.IntegerField(
        default=0,
        verbose_name='Successful Run Count'
    )
    failure_count = models.IntegerField(
        default=0,
        verbose_name='Failed Run Count'
    )
    
    # Celery Beat ID (for database sync lookup)
    celery_beat_id = models.IntegerField(
        null=True,
        blank=True,
        verbose_name='Celery Beat ID'
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_scheduled_tasks',
        verbose_name='Created By'
    )
    
    class Meta:
        verbose_name = 'Scheduled Task'
        verbose_name_plural = 'Scheduled Tasks'
        ordering = ['-priority', 'name']
        indexes = [
            models.Index(fields=['status', 'next_run_at']),
            models.Index(fields=['task_definition', 'status']),
        ]
    
    def __str__(self):
        return f"{self.name} ({self.get_schedule_type_display()})"


class TaskExecution(models.Model):
    """
    Task execution history.
    """
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('running', 'Running'),
        ('success', 'Success'),
        ('failed', 'Failed'),
        ('retrying', 'Retrying'),
        ('cancelled', 'Cancelled'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    scheduled_task = models.ForeignKey(
        ScheduledTask,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='executions',
        verbose_name='Scheduled Task'
    )
    task_definition = models.ForeignKey(
        TaskDefinition,
        on_delete=models.CASCADE,
        related_name='executions',
        verbose_name='Task Definition'
    )
    celery_task_id = models.CharField(
        max_length=255,
        unique=True,
        verbose_name='Celery Task ID'
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending',
        verbose_name='Status'
    )
    params = models.JSONField(
        default=dict,
        blank=True,
        verbose_name='Execution Parameters'
    )
    
    # Times
    queued_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Queued Time'
    )
    started_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='Start Time'
    )
    completed_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='Completion Time'
    )
    
    # Results
    result = models.JSONField(
        null=True,
        blank=True,
        verbose_name='Result'
    )
    error_message = models.TextField(
        blank=True,
        verbose_name='Error Message'
    )
    traceback = models.TextField(
        blank=True,
        verbose_name='Error Details'
    )
    
    # Stats
    retry_count = models.IntegerField(
        default=0,
        verbose_name='Retry Count'
    )
    duration_seconds = models.FloatField(
        null=True,
        blank=True,
        verbose_name='Duration (seconds)'
    )
    
    # Infrastructure info
    worker_name = models.CharField(
        max_length=200,
        blank=True,
        verbose_name='Worker Name'
    )
    queue_name = models.CharField(
        max_length=100,
        blank=True,
        verbose_name='Queue Name'
    )
    
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_task_executions',
        verbose_name='Executed By'
    )
    
    class Meta:
        verbose_name = 'Task Execution'
        verbose_name_plural = 'Task Executions'
        ordering = ['-queued_at']
        indexes = [
            models.Index(fields=['status', 'queued_at']),
            models.Index(fields=['scheduled_task', 'status']),
            models.Index(fields=['celery_task_id']),
        ]
    
    def __str__(self):
        return f"{self.task_definition.name} - {self.get_status_display()} ({self.queued_at})"
    
    def calculate_duration(self):
        """Calculate execution duration."""
        if self.started_at and self.completed_at:
            duration = (self.completed_at - self.started_at).total_seconds()
            self.duration_seconds = duration
            self.save(update_fields=['duration_seconds'])
            return duration
        return None


class TaskLog(models.Model):
    """
    Detailed logs for task executions.
    """
    LOG_LEVELS = [
        ('debug', 'Debug'),
        ('info', 'Info'),
        ('warning', 'Warning'),
        ('error', 'Error'),
        ('critical', 'Critical'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    execution = models.ForeignKey(
        TaskExecution,
        on_delete=models.CASCADE,
        related_name='logs',
        verbose_name='Execution'
    )
    level = models.CharField(
        max_length=20,
        choices=LOG_LEVELS,
        default='info',
        verbose_name='LogLevel'
    )
    message = models.TextField(
        verbose_name='Message'
    )
    extra_data = models.JSONField(
        default=dict,
        blank=True,
        verbose_name='Extra Data'
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Logged Time'
    )
    
    class Meta:
        verbose_name = 'Task Log'
        verbose_name_plural = 'Task Logs'
        ordering = ['execution', 'created_at']
        indexes = [
            models.Index(fields=['execution', 'level']),
        ]
    
    def __str__(self):
        return f"{self.get_level_display()}: {self.message[:50]}..."


class TaskAlert(models.Model):
    """
    Alerts generated by execution failures or timeouts.
    """
    ALERT_TYPES = [
        ('failure', 'Execution Failure'),
        ('timeout', 'Timeout'),
        ('threshold', 'Threshold Breached'),
        ('missing', 'Missed Run'),
        ('performance', 'Performance Degradation'),
    ]
    
    SEVERITY_LEVELS = [
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('critical', 'Critical'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    task_definition = models.ForeignKey(
        TaskDefinition,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='alerts',
        verbose_name='Task Definition'
    )
    scheduled_task = models.ForeignKey(
        ScheduledTask,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='alerts',
        verbose_name='Scheduled Task'
    )
    execution = models.ForeignKey(
        TaskExecution,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='alerts',
        verbose_name='Execution'
    )
    
    alert_type = models.CharField(
        max_length=20,
        choices=ALERT_TYPES,
        verbose_name='Alert Type'
    )
    severity = models.CharField(
        max_length=20,
        choices=SEVERITY_LEVELS,
        default='medium',
        verbose_name='Severity'
    )
    title = models.CharField(
        max_length=200,
        verbose_name='Title'
    )
    message = models.TextField(
        verbose_name='Message'
    )
    details = models.JSONField(
        default=dict,
        blank=True,
        verbose_name='Details'
    )
    
    # Alert state
    is_resolved = models.BooleanField(
        default=False,
        verbose_name='Is Resolved'
    )
    resolved_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='Resolved Time'
    )
    resolved_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='resolved_task_alerts',
        verbose_name='Resolved By'
    )
    resolution_note = models.TextField(
        blank=True,
        verbose_name='Resolution Note'
    )
    
    # Notifications
    notified_users = models.ManyToManyField(
        User,
        blank=True,
        related_name='task_alert_notifications',
        verbose_name='Notified Users'
    )
    notification_sent_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='Notification Sent Time'
    )
    
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Created Time'
    )
    
    class Meta:
        verbose_name = 'Task Alert'
        verbose_name_plural = 'Task Alerts'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['severity', 'is_resolved']),
            models.Index(fields=['alert_type', 'created_at']),
        ]
    
    def __str__(self):
        return f"{self.get_severity_display()}: {self.title}"