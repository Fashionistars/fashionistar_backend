from apps.audit_logs.models import EventCategory, EventType
from apps.audit_logs.services.audit import AuditService


class CatalogAuditService:
    """Structured audit hook for catalog metadata mutations."""

    @classmethod
    def log_mutation(
        cls,
        *,
        request,
        action: str,
        resource_type: str,
        resource_id: str | int,
        old_values: dict | None = None,
        new_values: dict | None = None,
    ) -> None:
        AuditService.log(
            event_type=EventType.ADMIN_ACTION,
            event_category=EventCategory.DATA_MODIFICATION,
            action=action,
            actor=getattr(request, "user", None),
            request=request,
            resource_type=resource_type,
            resource_id=str(resource_id),
            old_values=old_values,
            new_values=new_values,
            metadata={
                "domain": "catalog",
                "request_path": getattr(request, "path", ""),
                "request_method": getattr(request, "method", ""),
                "correlation_id": getattr(request, "headers", {}).get("X-Correlation-ID", ""),
                "idempotency_key": getattr(request, "headers", {}).get("Idempotency-Key", ""),
            },
            is_compliance=True,
        )
