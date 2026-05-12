# apps/audit_logs/mixins.py
"""
AuditedModelAdmin — Drop-in ModelAdmin mixin that captures every Django admin
action (add, change, delete) as an AuditEventLog entry.

Enterprise additions:
  - _safe_model_dict: captures Cloudinary / media URLs in old_values snapshot
    as {"__media_url__": url} so they survive change diffing.
  - revert classmethod + admin action: restore old_values to a model from
    a specific AuditEventLog entry — fully audited revert (creates new event).

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

# Django field types that hold media / Cloudinary URLs
_MEDIA_FIELD_TYPES = None


def _get_media_field_types():
    """Lazily import media field types to avoid early Django setup issues."""
    global _MEDIA_FIELD_TYPES
    if _MEDIA_FIELD_TYPES is None:
        try:
            from django.db.models import ImageField, FileField, URLField
            _MEDIA_FIELD_TYPES = (ImageField, FileField, URLField)
        except Exception:
            _MEDIA_FIELD_TYPES = ()
    return _MEDIA_FIELD_TYPES


def _safe_model_dict(obj, exclude=None) -> dict:
    """
    Serialize a model instance to a dict, with these guarantees:
    - Sensitive fields (password, secret, etc.) → '***REDACTED***'
    - ImageField / FileField values → {"__media_url__": url_str} snapshot
      so Cloudinary URLs are preserved in old_values for revert/diff.
    - URLField cloudinary_url / background_cloudinary_url → preserved as-is.
    - Non-serializable types → str()
    """
    if obj is None:
        return {}
    try:
        data = model_to_dict(obj, exclude=exclude)

        # Also grab URLField / ImageField / FileField values not in model_to_dict
        # (model_to_dict skips auto-fields and some special fields)
        media_types = _get_media_field_types()
        if media_types:
            for field in obj._meta.get_fields():
                if isinstance(field, media_types) and field.name not in data:
                    try:
                        raw_val = getattr(obj, field.name, None)
                        if raw_val:
                            url = getattr(raw_val, 'url', str(raw_val))
                            data[field.name] = {"__media_url__": url}
                    except Exception:
                        pass

        for k in list(data.keys()):
            v = data[k]
            # Redact sensitive fields
            if k in _REDACTED_FIELDS or "password" in k.lower() or "secret" in k.lower():
                data[k] = "***REDACTED***"
                continue
            # Snapshot media URL fields
            if media_types and hasattr(v, 'url'):
                try:
                    data[k] = {"__media_url__": v.url}
                except Exception:
                    data[k] = str(v)
                continue
            # Ensure JSON-serializable types
            if not isinstance(v, (str, int, float, bool, list, dict, type(None))):
                data[k] = str(v)

        return data
    except Exception:
        return {"__error__": "Could not serialize model"}


class AuditedModelAdmin:
    """
    Mixin for Django ModelAdmin that logs every admin action to AuditEventLog.

    Captures:
    - save_model  → ADMIN_ACTION with old_values / new_values diff + media URL snapshots
    - delete_model → ADMIN_ACTION with old_values snapshot
    - delete_queryset → ADMIN_BULK_DELETE
    - revert_last_change admin action → restores old_values and logs ADMIN_ACTION with action="Reverted"

    Simply add this mixin BEFORE admin.ModelAdmin in MRO:
        class MyAdmin(AuditedModelAdmin, admin.ModelAdmin): ...
    """

    def save_model(self, request, obj, form, change):
        """Override save_model to capture before/after state including media URL snapshots."""
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
        """Override delete_model to capture the deleted object's state + media URLs."""
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

    # ── Change Revert — Industrial-grade rollback with full audit trail ────────

    @admin.action(description="↩ Revert selected record(s) to last audited state")
    def revert_last_admin_change(self, request, queryset):
        """
        Admin action: revert each selected object to its old_values from the
        most recent AuditEventLog ADMIN_ACTION entry.

        - Loads old_values from AuditEventLog
        - Applies non-redacted field values back to the model
        - Saves + writes a new AuditEventLog with action="Reverted"
        - Shows success/error message in the Django admin UI
        """
        from apps.audit_logs.models import AuditEventLog, EventType, EventCategory
        from apps.audit_logs.services.audit import AuditService

        reverted = 0
        errors = 0

        for obj in queryset:
            try:
                # Find the most recent ADMIN_ACTION for this object
                last_event = (
                    AuditEventLog.objects
                    .filter(
                        resource_type=obj.__class__.__name__,
                        resource_id=str(obj.pk),
                        event_type=EventType.ADMIN_ACTION,
                    )
                    .exclude(old_values=None)
                    .order_by("-created_at")
                    .first()
                )

                if not last_event or not last_event.old_values:
                    self.message_user(
                        request,
                        f"No revertible audit event found for {obj.__class__.__name__} pk={obj.pk}.",
                        level="warning",
                    )
                    continue

                old_vals = last_event.old_values
                changed_back = []

                for field_name, old_val in old_vals.items():
                    # Skip redacted, error, and meta keys
                    if (
                        old_val == "***REDACTED***"
                        or field_name.startswith("__")
                        or not hasattr(obj, field_name)
                    ):
                        continue

                    # Handle media URL snapshots: {"__media_url__": url}
                    if isinstance(old_val, dict) and "__media_url__" in old_val:
                        old_val = old_val["__media_url__"]

                    try:
                        setattr(obj, field_name, old_val)
                        changed_back.append(field_name)
                    except Exception:
                        pass

                if changed_back:
                    obj.save(update_fields=changed_back)

                    AuditService.log(
                        event_type=EventType.ADMIN_ACTION,
                        event_category=EventCategory.ADMIN,
                        action=(
                            f"Admin reverted {obj.__class__.__name__} pk={obj.pk} "
                            f"to state from audit event {last_event.pk} "
                            f"— fields: {', '.join(changed_back)}"
                        ),
                        severity="warning",
                        request=request,
                        resource_type=obj.__class__.__name__,
                        resource_id=str(obj.pk),
                        old_values=_safe_model_dict(obj),
                        new_values=old_vals,
                        metadata={
                            "reverted_from_audit_event": str(last_event.pk),
                            "reverted_fields": changed_back,
                        },
                        is_compliance=True,
                    )

                    reverted += 1
                else:
                    errors += 1

            except Exception as exc:
                logger.error(
                    "AuditedModelAdmin.revert: failed for pk=%s: %s",
                    obj.pk, exc,
                )
                errors += 1

        if reverted:
            self.message_user(request, f"✅ Reverted {reverted} record(s) successfully.")
        if errors:
            self.message_user(
                request,
                f"⚠ {errors} record(s) could not be reverted — see logs.",
                level="warning",
            )

    # Register the revert action automatically on the admin class
    actions = ['revert_last_admin_change']
