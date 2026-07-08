# apps/audit_logs/services/app_standards/app_standards_audit.py
"""
Audit logging helpers for App Standards domain.
Follows vendor pattern with thin wrappers delegating to AuditService.
"""

from apps.audit_logs.services import AuditService
from apps.audit_logs.models import EventType, EventCategory


class AppStandardsAuditService:
    """Audit service for App Standards domain events."""
    
    @staticmethod
    def log_ai_usage(actor, usage_id, service_type, model_name, input_tokens, output_tokens, cost, request=None):
        """Log when AI service is used."""
        AuditService.log(
            event_type=EventType.AI_ANALYSIS_COMPLETED,
            event_category=EventCategory.MEASUREMENT,
            actor=actor,
            action="AI service usage recorded",
            request=request,
            details={
                'usage_id': str(usage_id),
                'service_type': service_type,
                'model_name': model_name,
                'input_tokens': input_tokens,
                'output_tokens': output_tokens,
                'cost': str(cost),
            },
        )
    
    @staticmethod
    def log_billing_transaction(actor, transaction_id, transaction_type, amount, gateway, request=None):
        """Log when a billing transaction occurs."""
        AuditService.log(
            event_type=EventType.PAYMENT_INITIATED if transaction_type == 'payment' else EventType.WALLET_TRANSFER,
            event_category=EventCategory.PAYMENT,
            actor=actor,
            action=f"Billing transaction: {transaction_type}",
            request=request,
            details={
                'transaction_id': str(transaction_id),
                'transaction_type': transaction_type,
                'amount': str(amount),
                'gateway': gateway,
            },
        )
    
    @staticmethod
    def log_notification_sent(actor, notification_id, notification_type, priority, request=None):
        """Log when a notification is sent."""
        AuditService.log(
            event_type=EventType.NOTIFICATION,
            event_category=EventCategory.NOTIFICATION,
            actor=actor,
            action=f"Notification sent: {notification_type}",
            request=request,
            details={
                'notification_id': str(notification_id),
                'notification_type': notification_type,
                'priority': priority,
            },
        )
    
    @staticmethod
    def log_notification_read(actor, notification_id, request=None):
        """Log when a notification is read."""
        AuditService.log(
            event_type=EventType.NOTIFICATION,
            event_category=EventCategory.NOTIFICATION,
            actor=actor,
            action="Notification read",
            request=request,
            details={
                'notification_id': str(notification_id),
            },
        )
    
    @staticmethod
    def log_rate_limit_exceeded(actor, endpoint, limit_type, current_count, max_requests, request=None):
        """Log when rate limit is exceeded."""
        AuditService.log(
            event_type=EventType.SUSPICIOUS_ACTIVITY,
            event_category=EventCategory.SECURITY,
            actor=actor,
            action="Rate limit exceeded",
            request=request,
            details={
                'endpoint': endpoint,
                'limit_type': limit_type,
                'current_count': current_count,
                'max_requests': max_requests,
            },
        )
    
    @staticmethod
    def log_access_permission_granted(actor, permission_id, resource_type, resource_id, permission_type, request=None):
        """Log when access permission is granted."""
        AuditService.log(
            event_type=EventType.ADMIN_ACTION,
            event_category=EventCategory.AUTHORIZATION,
            actor=actor,
            action="Access permission granted",
            request=request,
            details={
                'permission_id': str(permission_id),
                'resource_type': resource_type,
                'resource_id': str(resource_id),
                'permission_type': permission_type,
            },
        )
    
    @staticmethod
    def log_access_permission_revoked(actor, permission_id, resource_type, resource_id, request=None):
        """Log when access permission is revoked."""
        AuditService.log(
            event_type=EventType.ADMIN_ACTION,
            event_category=EventCategory.AUTHORIZATION,
            actor=actor,
            action="Access permission revoked",
            request=request,
            details={
                'permission_id': str(permission_id),
                'resource_type': resource_type,
                'resource_id': str(resource_id),
            },
        )
    
    @staticmethod
    def log_unified_auth_integration(actor, integration_id, token_type, request=None):
        """Log when unified auth integration is created."""
        AuditService.log(
            event_type=EventType.ACCOUNT_CREATED,
            event_category=EventCategory.AUTHENTICATION,
            actor=actor,
            action="Unified auth integration created",
            request=request,
            details={
                'integration_id': str(integration_id),
                'token_type': token_type,
            },
        )
