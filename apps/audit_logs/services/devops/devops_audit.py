# apps/audit_logs/services/devops/devops_audit.py
"""
Audit logging helpers for DevOps domain.
Follows vendor pattern with thin wrappers delegating to AuditService.
"""

from apps.audit_logs.services import AuditService
from apps.audit_logs.models import EventType, EventCategory


class DevOpsAuditService:
    """Audit service for DevOps domain events."""
    
    @staticmethod
    def log_environment_created(actor, environment_name, environment_type, request=None):
        """Log when environment is created."""
        AuditService.log(
            event_type=EventType.DEVOPS_ENVIRONMENT_CREATED,
            event_category=EventCategory.DEVOPS,
            actor=actor,
            action="Environment created",
            request=request,
            details={
                'environment_name': environment_name,
                'environment_type': environment_type,
            },
        )
    
    @staticmethod
    def log_environment_updated(actor, environment_name, request=None):
        """Log when environment is updated."""
        AuditService.log(
            event_type=EventType.DEVOPS_ENVIRONMENT_UPDATED,
            event_category=EventCategory.DEVOPS,
            actor=actor,
            action="Environment updated",
            request=request,
            details={
                'environment_name': environment_name,
            },
        )
    
    @staticmethod
    def log_environment_deleted(actor, environment_name, request=None):
        """Log when environment is deleted."""
        AuditService.log(
            event_type=EventType.DEVOPS_ENVIRONMENT_DELETED,
            event_category=EventCategory.DEVOPS,
            actor=actor,
            action="Environment deleted",
            request=request,
            details={
                'environment_name': environment_name,
            },
        )
    
    @staticmethod
    def log_secret_created(actor, key_name, category, environment_name, request=None):
        """Log when secret is created."""
        AuditService.log(
            event_type=EventType.DEVOPS_SECRET_CREATED,
            event_category=EventCategory.DEVOPS,
            actor=actor,
            action="Secret created",
            request=request,
            details={
                'key_name': key_name,
                'category': category,
                'environment_name': environment_name,
            },
        )
    
    @staticmethod
    def log_secret_updated(actor, key_name, environment_name, request=None):
        """Log when secret is updated."""
        AuditService.log(
            event_type=EventType.DEVOPS_SECRET_UPDATED,
            event_category=EventCategory.DEVOPS,
            actor=actor,
            action="Secret updated",
            request=request,
            details={
                'key_name': key_name,
                'environment_name': environment_name,
            },
        )
    
    @staticmethod
    def log_secret_deleted(actor, key_name, environment_name, request=None):
        """Log when secret is deleted."""
        AuditService.log(
            event_type=EventType.DEVOPS_SECRET_DELETED,
            event_category=EventCategory.DEVOPS,
            actor=actor,
            action="Secret deleted",
            request=request,
            details={
                'key_name': key_name,
                'environment_name': environment_name,
            },
        )
    
    @staticmethod
    def log_secret_rotated(actor, key_name, environment_name, request=None):
        """Log when secret is rotated."""
        AuditService.log(
            event_type=EventType.DEVOPS_SECRET_ROTATED,
            event_category=EventCategory.DEVOPS,
            actor=actor,
            action="Secret rotated",
            request=request,
            details={
                'key_name': key_name,
                'environment_name': environment_name,
            },
        )
    
    @staticmethod
    def log_deployment_started(actor, environment_name, version, branch, request=None):
        """Log when deployment is started."""
        AuditService.log(
            event_type=EventType.DEVOPS_DEPLOYMENT_STARTED,
            event_category=EventCategory.DEVOPS,
            actor=actor,
            action="Deployment started",
            request=request,
            details={
                'environment_name': environment_name,
                'version': version,
                'branch': branch,
            },
        )
    
    @staticmethod
    def log_deployment_success(actor, environment_name, version, duration_seconds, request=None):
        """Log when deployment succeeds."""
        AuditService.log(
            event_type=EventType.DEVOPS_DEPLOYMENT_SUCCESS,
            event_category=EventCategory.DEVOPS,
            actor=actor,
            action="Deployment success",
            request=request,
            details={
                'environment_name': environment_name,
                'version': version,
                'duration_seconds': duration_seconds,
            },
        )
    
    @staticmethod
    def log_deployment_failed(actor, environment_name, version, error_message, request=None):
        """Log when deployment fails."""
        AuditService.log(
            event_type=EventType.DEVOPS_DEPLOYMENT_FAILED,
            event_category=EventCategory.DEVOPS,
            actor=actor,
            action="Deployment failed",
            request=request,
            details={
                'environment_name': environment_name,
                'version': version,
                'error_message': error_message,
            },
        )
    
    @staticmethod
    def log_deployment_rolled_back(actor, environment_name, version, from_version, request=None):
        """Log when deployment is rolled back."""
        AuditService.log(
            event_type=EventType.DEVOPS_DEPLOYMENT_ROLLED_BACK,
            event_category=EventCategory.DEVOPS,
            actor=actor,
            action="Deployment rolled back",
            request=request,
            details={
                'environment_name': environment_name,
                'version': version,
                'from_version': from_version,
            },
        )
    
    @staticmethod
    def log_health_check_passed(actor, service_name, environment_name, response_time_ms, request=None):
        """Log when health check passes."""
        AuditService.log(
            event_type=EventType.DEVOPS_HEALTH_CHECK_PASSED,
            event_category=EventCategory.DEVOPS,
            actor=actor,
            action="Health check passed",
            request=request,
            details={
                'service_name': service_name,
                'environment_name': environment_name,
                'response_time_ms': response_time_ms,
            },
        )
    
    @staticmethod
    def log_health_check_failed(actor, service_name, environment_name, error_message, request=None):
        """Log when health check fails."""
        AuditService.log(
            event_type=EventType.DEVOPS_HEALTH_CHECK_FAILED,
            event_category=EventCategory.DEVOPS,
            actor=actor,
            action="Health check failed",
            request=request,
            details={
                'service_name': service_name,
                'environment_name': environment_name,
                'error_message': error_message,
            },
        )
    
    @staticmethod
    def log_service_monitoring_enabled(actor, service_name, environment_name, request=None):
        """Log when service monitoring is enabled."""
        AuditService.log(
            event_type=EventType.DEVOPS_SERVICE_MONITORING_ENABLED,
            event_category=EventCategory.DEVOPS,
            actor=actor,
            action="Service monitoring enabled",
            request=request,
            details={
                'service_name': service_name,
                'environment_name': environment_name,
            },
        )
    
    @staticmethod
    def log_service_monitoring_disabled(actor, service_name, environment_name, request=None):
        """Log when service monitoring is disabled."""
        AuditService.log(
            event_type=EventType.DEVOPS_SERVICE_MONITORING_DISABLED,
            event_category=EventCategory.DEVOPS,
            actor=actor,
            action="Service monitoring disabled",
            request=request,
            details={
                'service_name': service_name,
                'environment_name': environment_name,
            },
        )
    
    @staticmethod
    def log_infrastructure_scaling(actor, scaling_type, scale_from, scale_to, request=None):
        """Log when infrastructure is scaled."""
        AuditService.log(
            event_type=EventType.DEVOPS_INFRASTRUCTURE_SCALING,
            event_category=EventCategory.DEVOPS,
            actor=actor,
            action="Infrastructure scaling",
            request=request,
            details={
                'scaling_type': scaling_type,
                'scale_from': scale_from,
                'scale_to': scale_to,
            },
        )
    
    @staticmethod
    def log_config_change_applied(actor, config_type, environment_name, request=None):
        """Log when configuration change is applied."""
        AuditService.log(
            event_type=EventType.DEVOPS_CONFIG_CHANGE_APPLIED,
            event_category=EventCategory.DEVOPS,
            actor=actor,
            action="Configuration change applied",
            request=request,
            details={
                'config_type': config_type,
                'environment_name': environment_name,
            },
        )
