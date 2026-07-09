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
            details={
                'metric_name': metric_name,
                'metric_type': metric_type,
                'value': value,
            },
        )
    
    @staticmethod
    def log_user_activity_logged(actor, action, resource, request=None):
        """Log when user activity is logged."""
        AuditService.log(
            event_type=EventType.ANALYTICS_USER_ACTIVITY_LOGGED,
            event_category=EventCategory.ANALYTICS,
            actor=actor,
            action="User activity logged",
            request=request,
            details={
                'action': action,
                'resource': resource,
            },
        )
    
    @staticmethod
    def log_performance_tracked(actor, endpoint, method, response_time_ms, status_code, request=None):
        """Log when performance metric is tracked."""
        AuditService.log(
            event_type=EventType.ANALYTICS_PERFORMANCE_TRACKED,
            event_category=EventCategory.ANALYTICS,
            actor=actor,
            action="Performance metric tracked",
            request=request,
            details={
                'endpoint': endpoint,
                'method': method,
                'response_time_ms': response_time_ms,
                'status_code': status_code,
            },
        )
    
    @staticmethod
    def log_business_metric_calculated(actor, metric_name, period_start, period_end, request=None):
        """Log when business metric is calculated."""
        AuditService.log(
            event_type=EventType.ANALYTICS_BUSINESS_METRIC_CALC,
            event_category=EventCategory.ANALYTICS,
            actor=actor,
            action="Business metric calculated",
            request=request,
            details={
                'metric_name': metric_name,
                'period_start': period_start.isoformat() if period_start else None,
                'period_end': period_end.isoformat() if period_end else None,
            },
        )
    
    @staticmethod
    def log_alert_rule_evaluated(actor, rule_name, metric_name, request=None):
        """Log when alert rule is evaluated."""
        AuditService.log(
            event_type=EventType.ANALYTICS_ALERT_RULE_EVALUATED,
            event_category=EventCategory.ANALYTICS,
            actor=actor,
            action="Alert rule evaluated",
            request=request,
            details={
                'rule_name': rule_name,
                'metric_name': metric_name,
            },
        )
    
    @staticmethod
    def log_alert_triggered(actor, rule_name, metric_value, threshold, request=None):
        """Log when alert is triggered."""
        AuditService.log(
            event_type=EventType.ANALYTICS_ALERT_TRIGGERED,
            event_category=EventCategory.ANALYTICS,
            actor=actor,
            action="Alert triggered",
            request=request,
            details={
                'rule_name': rule_name,
                'metric_value': metric_value,
                'threshold': threshold,
            },
        )
    
    @staticmethod
    def log_alert_resolved(actor, rule_name, request=None):
        """Log when alert is resolved."""
        AuditService.log(
            event_type=EventType.ANALYTICS_ALERT_RESOLVED,
            event_category=EventCategory.ANALYTICS,
            actor=actor,
            action="Alert resolved",
            request=request,
            details={
                'rule_name': rule_name,
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
            details={
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
            details={
                'report_type': report_type,
                'period_start': period_start.isoformat() if period_start else None,
                'period_end': period_end.isoformat() if period_end else None,
            },
        )
    
    @staticmethod
    def log_data_exported(actor, export_type, record_count, request=None):
        """Log when analytics data is exported."""
        AuditService.log(
            event_type=EventType.ANALYTICS_DATA_EXPORTED,
            event_category=EventCategory.ANALYTICS,
            actor=actor,
            action="Analytics data exported",
            request=request,
            details={
                'export_type': export_type,
                'record_count': record_count,
            },
        )
