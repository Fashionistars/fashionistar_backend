# apps/audit_logs/services/analytics/analytics_audit.py
"""
Audit logging helpers for Analytics domain.
Follows vendor pattern with thin wrappers delegating to AuditService.
"""

from apps.audit_logs.services import AuditService
from apps.audit_logs.models import EventType, EventCategory


class AnalyticsAuditService:
    """Audit service for Analytics domain events."""
    
    @staticmethod
    def log_metric_recorded(actor, metric_name, metric_type, value, request=None):
        """Log when analytics metric is recorded."""
        AuditService.log(
            event_type=EventType.ANALYTICS_METRIC_RECORDED,
            event_category=EventCategory.ANALYTICS,
            actor=actor,
            action="Analytics metric recorded",
            request=request,
            metadata={
                'metric_name': metric_name,
                'metric_type': metric_type,
                'value': value,
            },
        )

    @staticmethod
    def log_user_activity_logged(actor, user_id, action, resource, request=None):
        """Log when user activity is logged."""
        AuditService.log(
            event_type=EventType.ANALYTICS_USER_ACTIVITY_LOGGED,
            event_category=EventCategory.ANALYTICS,
            actor=actor,
            action="User activity logged",
            request=request,
            metadata={
                'user_id': user_id,
                'action': action,
                'resource': resource,
            },
        )

    @staticmethod
    def log_performance_metric_recorded(
        actor, endpoint, response_time_ms, status_code, request=None
    ):
        """Log when performance metric is recorded."""
        AuditService.log(
            event_type=EventType.ANALYTICS_PERFORMANCE_TRACKED,
            event_category=EventCategory.ANALYTICS,
            actor=actor,
            action="Performance metric recorded",
            request=request,
            metadata={
                'endpoint': endpoint,
                'response_time_ms': response_time_ms,
                'status_code': status_code,
            },
        )

    @staticmethod
    def log_business_metric_updated(
        actor, metric_name, value, period, request=None
    ):
        """Log when business metric is updated."""
        AuditService.log(
            event_type=EventType.ANALYTICS_BUSINESS_METRIC_CALC,
            event_category=EventCategory.ANALYTICS,
            actor=actor,
            action="Business metric updated",
            request=request,
            metadata={
                'metric_name': metric_name,
                'value': value,
                'period': period,
            },
        )

    @staticmethod
    def log_alert_triggered(
        actor, alert_rule_id, metric_value, severity, request=None
    ):
        """Log when alert is triggered."""
        AuditService.log(
            event_type=EventType.ANALYTICS_ALERT_TRIGGERED,
            event_category=EventCategory.ANALYTICS,
            actor=actor,
            action="Alert triggered",
            request=request,
            metadata={
                'alert_rule_id': alert_rule_id,
                'metric_value': metric_value,
                'severity': severity,
            },
        )

    @staticmethod
    def log_alert_resolved(actor, alert_id, resolution_notes, request=None):
        """Log when alert is resolved."""
        AuditService.log(
            event_type=EventType.ANALYTICS_ALERT_RESOLVED,
            event_category=EventCategory.ANALYTICS,
            actor=actor,
            action="Alert resolved",
            request=request,
            metadata={
                'alert_id': alert_id,
                'resolution_notes': resolution_notes,
            },
        )

    @staticmethod
    def log_analytics_query_executed(
        actor, query_type, time_range, request=None
    ):
        """Log when an analytics query is executed."""
        AuditService.log(
            event_type=EventType.ANALYTICS_QUERY_EXECUTED,
            event_category=EventCategory.ANALYTICS,
            actor=actor,
            action="Analytics query executed",
            request=request,
            metadata={
                'query_type': query_type,
                'time_range': time_range,
            },
        )

    @staticmethod
    def log_dashboard_viewed(actor, dashboard_type, request=None):
        """Log when analytics dashboard is viewed."""
        AuditService.log(
            event_type=EventType.ANALYTICS_DASHBOARD_VIEWED,
            event_category=EventCategory.ANALYTICS,
            actor=actor,
            action="Analytics dashboard viewed",
            request=request,
            metadata={
                'dashboard_type': dashboard_type,
            },
        )

    @staticmethod
    def log_report_generated(actor, report_type, period_start, period_end, request=None):
        """Log when analytics report is generated."""
        AuditService.log(
            event_type=EventType.ANALYTICS_REPORT_GENERATED,
            event_category=EventCategory.ANALYTICS,
            actor=actor,
            action="Analytics report generated",
            request=request,
            metadata={
                'report_type': report_type,
                'period_start': period_start.isoformat() if period_start else None,
                'period_end': period_end.isoformat() if period_end else None,
            },
        )

    @staticmethod
    def log_metric_aggregation_executed(
        actor, aggregation_window, record_count, request=None
    ):
        """Log when metric aggregation is executed."""
        AuditService.log(
            event_type=EventType.METRIC_AGGREGATION_EXECUTED,
            event_category=EventCategory.ANALYTICS,
            actor=actor,
            action="Metric aggregation executed",
            request=request,
            metadata={
                'aggregation_window': aggregation_window,
                'record_count': record_count,
            },
        )

    @staticmethod
    def log_data_retention_applied(
        actor, retention_days, deleted_count, request=None
    ):
        """Log when data retention policy is applied."""
        AuditService.log(
            event_type=EventType.DATA_RETENTION_APPLIED,
            event_category=EventCategory.ANALYTICS,
            actor=actor,
            action="Data retention applied",
            request=request,
            metadata={
                'retention_days': retention_days,
                'deleted_count': deleted_count,
            },
        )
