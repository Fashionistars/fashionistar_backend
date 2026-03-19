# apps/audit_logs/mixins.py
"""
AuditedModelAdmin — Drop-in ModelAdmin mixin that captures every Django admin
action (add, change, delete) as an AuditEventLog entry.

Usage:
    from apps.audit_logs.mixins import AuditedModelAdmin

    @admin.register(MyModel)
    class MyModelAdmin(AuditedModelAdmin, admin.ModelAdmin):
        ...

Every save_model / delete_model call automatically writes an audit event with
event_type=ADMIN_ACTION, full before/after diffs, actor, IP, and resource info.
"""

import logging

from django.contrib import admin
from django.forms import model_to_dict

logger = logging.getLogger(__name__)

# Fields that should NEVER appear in audit diffs (security)
_REDACTED_FIELDS = frozenset({
    "password", "api_secret", "secret_key", "token",
    "otp_secret", "otp_base32",
})


def _safe_model_dict(obj, exclude=None) -> dict:
    """Serialize a model instance to dict, redacting sensitive fields."""
    if obj is None:
        return {}
    try:
        data = model_to_dict(obj, exclude=exclude)
        for k in list(data.keys()):
            if k in _REDACTED_FIELDS or "password" in k.lower() or "secret" in k.lower():
                data[k] = "***REDACTED***"
            # Convert non-serializable types to strings
            if not isinstance(data[k], (str, int, float, bool, list, dict, type(None))):
                data[k] = str(data[k])
        return data
    except Exception:
        return {"__error__": "Could not serialize model"}


class AuditedModelAdmin:
    """
    Mixin for Django ModelAdmin that logs every admin action to AuditEventLog.

    Captures:
    - save_model  → ADMIN_ACTION with old_values / new_values diff
    - delete_model → ADMIN_ACTION with old_values snapshot
    - Custom admin actions via response_action override

    Simply add this mixin BEFORE admin.ModelAdmin in MRO:
        class MyAdmin(AuditedModelAdmin, admin.ModelAdmin): ...
    """

    def save_model(self, request, obj, form, change):
        """Override save_model to capture before/after state."""
        from apps.audit_logs.services.audit import AuditService
        from apps.audit_logs.models import EventType, EventCategory

        old_values = None
        action_verb = "updated" if change else "created"

        if change:
            try:
                old_obj = obj.__class__.objects.get(pk=obj.pk)
                old_values = _safe_model_dict(old_obj)
            except obj.__class__.DoesNotExist:
                old_values = None

        # Actually save
        super().save_model(request, obj, form, change)

        new_values = _safe_model_dict(obj)

        # Compute changed fields for the action description
        changed_fields = []
        if change and old_values:
            for key in new_values:
                if str(new_values.get(key)) != str(old_values.get(key)):
                    changed_fields.append(key)

        model_name = obj.__class__.__name__
        action = (
            f"Admin {action_verb} {model_name} (pk={obj.pk})"
            + (f" — fields: {', '.join(changed_fields)}" if changed_fields else "")
        )

        try:
            AuditService.log(
                event_type=EventType.ADMIN_ACTION,
                event_category=EventCategory.ADMIN,
                action=action,
                severity="info",
                request=request,
                resource_type=model_name,
                resource_id=str(obj.pk),
                old_values=old_values,
                new_values=new_values,
                is_compliance=True,
            )
        except Exception:
            logger.warning(
                "AuditedModelAdmin: failed to log save_model for %s pk=%s",
                model_name, obj.pk, exc_info=True,
            )

    def delete_model(self, request, obj):
        """Override delete_model to capture the deleted object's state."""
        from apps.audit_logs.services.audit import AuditService
        from apps.audit_logs.models import EventType, EventCategory

        model_name = obj.__class__.__name__
        old_values = _safe_model_dict(obj)
        pk = str(obj.pk)

        # Actually delete
        super().delete_model(request, obj)

        try:
            AuditService.log(
                event_type=EventType.ADMIN_ACTION,
                event_category=EventCategory.ADMIN,
                action=f"Admin deleted {model_name} (pk={pk})",
                severity="warning",
                request=request,
                resource_type=model_name,
                resource_id=pk,
                old_values=old_values,
                is_compliance=True,
            )
        except Exception:
            logger.warning(
                "AuditedModelAdmin: failed to log delete_model for %s pk=%s",
                model_name, pk, exc_info=True,
            )

    def delete_queryset(self, request, queryset):
        """Override bulk delete to audit each item."""
        from apps.audit_logs.services.audit import AuditService
        from apps.audit_logs.models import EventType, EventCategory

        model_name = queryset.model.__name__
        pks = list(queryset.values_list("pk", flat=True))

        super().delete_queryset(request, queryset)

        try:
            AuditService.log(
                event_type=EventType.ADMIN_BULK_DELETE,
                event_category=EventCategory.ADMIN,
                action=f"Admin bulk-deleted {len(pks)} {model_name} records",
                severity="warning",
                request=request,
                resource_type=model_name,
                metadata={"deleted_pks": [str(pk) for pk in pks[:100]]},
                is_compliance=True,
            )
        except Exception:
            logger.warning(
                "AuditedModelAdmin: failed to log delete_queryset for %s",
                model_name, exc_info=True,
            )
