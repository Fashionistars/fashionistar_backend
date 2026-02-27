# apps/common/admin.py
"""
Admin registrations for shared ``apps.common`` models.

Registers:
    DeletedRecords — Forensic archive of all soft-deleted records.
        • Read-only (no accidental edits).
        • Search by model_name, record_id.
        • Filter by model_name, deleted_at.
        • Pretty-printed JSON data preview.
        • Date hierarchy for temporal browsing.
        • Superuser-only delete — with CASCADE to the original
          source record (permanent purge).
        • ``restore_from_archive`` action — restores the source
          record back to alive state and removes the archive entry.
"""

import json
import logging

from django.contrib import admin
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from apps.common.models import (
    DeletedRecords,
    DeletionAuditCounter,
    ModelAnalytics,
)

logger = logging.getLogger('application')


@admin.register(DeletedRecords)
class DeletedRecordsAdmin(admin.ModelAdmin):
    """
    Forensic archive admin for globally soft-deleted records.

    This admin intentionally blocks edits (it is an immutable
    audit log). Superusers may:
        1. **Delete** an archive entry — this also permanently
           deletes the corresponding source record from its
           original model table (irreversible hard-delete cascade).
        2. **Restore** an archive entry via the bulk action —
           this marks the source record ``is_deleted=False`` and
           removes the archive entry.
    """

    list_display = (
        'model_name',
        'record_id',
        'deleted_at',
    )
    list_filter = (
        'model_name',
        'deleted_at',
    )
    search_fields = (
        'model_name',
        'record_id',
    )
    readonly_fields = (
        'model_name',
        'record_id',
        'deleted_at',
        'data_pretty',
    )
    date_hierarchy = 'deleted_at'
    ordering = ('-deleted_at',)
    exclude = ('data',)     # replaced by data_pretty
    actions = [
        'restore_from_archive',
    ]

    # ----------------------------------------------------------------
    # Custom display
    # ----------------------------------------------------------------

    def data_pretty(self, obj):
        """
        Render archived JSON data as indented, coloured HTML.
        """
        try:
            pretty = json.dumps(obj.data, indent=2, default=str)
        except Exception:
            pretty = str(obj.data)
        return format_html(
            '<pre style="'
            'background:#1e1e1e;color:#d4d4d4;'
            'padding:12px;border-radius:6px;'
            'font-size:12px;max-height:400px;'
            'overflow:auto;white-space:pre-wrap;'
            '">{}</pre>',
            pretty,
        )

    data_pretty.short_description = _('Archived Data (JSON)')

    # ----------------------------------------------------------------
    # Permissions
    # ----------------------------------------------------------------

    def has_add_permission(self, request):
        """Block manual creation — records are auto-archived only."""
        return False

    def has_change_permission(self, request, obj=None):
        """Block edits — forensic audit tables are immutable."""
        return False

    def has_delete_permission(self, request, obj=None):
        """Only superusers may purge archive entries."""
        return request.user.is_superuser

    # ----------------------------------------------------------------
    # Delete with cascade to original model (Bug 5 fix)
    # ----------------------------------------------------------------

    def delete_queryset(self, request, queryset):
        """
        Override default delete to also permanently remove the
        corresponding source records from their original tables.

        When a superuser deletes entries from the DeletedRecords
        admin, this method:
            1. Looks up the original model via ``resolve_original_model()``.
            2. Hard-deletes the source records (physical SQL DELETE).
            3. Then deletes the archive entries themselves.

        This implements the "purge from DeletedRecords also purges
        the original record" behaviour requested by the user.

        .. warning::
            This is completely irreversible.  The source record is
            physically removed from the database.
        """
        for archive_obj in queryset.iterator(chunk_size=200):
            model_class = archive_obj.resolve_original_model()
            if model_class is None:
                logger.warning(
                    "DeletedRecords.delete_queryset: could not "
                    "resolve model '%s' — skipping source delete "
                    "for record_id=%s",
                    archive_obj.model_name,
                    archive_obj.record_id,
                )
                continue

            # Hard-delete the source row via all_with_deleted()
            # so we can reach is_deleted=True rows.
            try:
                if hasattr(model_class.objects, 'all_with_deleted'):
                    deleted_count, _ = (
                        model_class.objects
                        .all_with_deleted()
                        .filter(pk=archive_obj.record_id)
                        .hard_delete()
                    )
                else:
                    deleted_count, _ = (
                        model_class.objects
                        .filter(pk=archive_obj.record_id)
                        .delete()
                    )
                logger.warning(
                    "HARD-DELETED %d source %s record(s) "
                    "(record_id=%s) via DeletedRecords admin",
                    deleted_count,
                    archive_obj.model_name,
                    archive_obj.record_id,
                )
            except Exception:
                logger.exception(
                    "Failed to hard-delete source record %s[%s]",
                    archive_obj.model_name,
                    archive_obj.record_id,
                )

        # Now delete the archive entries themselves
        queryset.delete()

    # ----------------------------------------------------------------
    # Restore from archive action (Bug 5 — read-path)
    # ----------------------------------------------------------------

    @admin.action(
        description=_("♻️  Restore selected records to their original model")
    )
    def restore_from_archive(self, request, queryset):
        """
        Restore source records from the archive back to alive state.

        For each selected archive entry:
            1. Looks up the original model.
            2. Uses ``all_with_deleted().filter(pk=...).update(
               is_deleted=False, deleted_at=None)`` to un-delete.
            3. Deletes the archive entry (restore = no longer deleted).

        Does NOT cascade — it only un-deletes; it does NOT call
        ``save()`` or trigger ``full_clean()``.
        """
        if not request.user.is_superuser:
            self.message_user(
                request,
                _("⛔ Only superusers may restore from archive."),
                level='error',
            )
            return

        restored = 0
        failed = 0
        archive_pks_to_delete = []

        for archive_obj in queryset.iterator(chunk_size=200):
            model_class = archive_obj.resolve_original_model()
            if model_class is None:
                logger.warning(
                    "Could not resolve model '%s' for restore",
                    archive_obj.model_name,
                )
                failed += 1
                continue

            try:
                if hasattr(model_class.objects, 'all_with_deleted'):
                    updated = (
                        model_class.objects
                        .all_with_deleted()
                        .filter(pk=archive_obj.record_id)
                        .update(is_deleted=False, deleted_at=None)
                    )
                else:
                    updated = (
                        model_class.objects
                        .filter(pk=archive_obj.record_id)
                        .update(is_deleted=False, deleted_at=None)
                    )
                if updated:
                    archive_pks_to_delete.append(archive_obj.pk)
                    restored += 1
                    logger.info(
                        "Restored %s[%s] from archive",
                        archive_obj.model_name,
                        archive_obj.record_id,
                    )
                else:
                    logger.warning(
                        "Restore matched 0 rows for %s[%s]",
                        archive_obj.model_name,
                        archive_obj.record_id,
                    )
                    failed += 1
            except Exception:
                logger.exception(
                    "Failed to restore %s[%s]",
                    archive_obj.model_name,
                    archive_obj.record_id,
                )
                failed += 1

        # Bulk delete the archive entries for successfully restored records
        if archive_pks_to_delete:
            DeletedRecords.objects.filter(
                pk__in=archive_pks_to_delete,
            ).delete()

        msg_parts = []
        if restored:
            msg_parts.append(
                _("%(n)d record(s) restored.") % {'n': restored}
            )
        if failed:
            msg_parts.append(
                _("%(n)d record(s) failed (see server logs).") % {'n': failed}
            )
        self.message_user(
            request,
            " ".join(str(p) for p in msg_parts) or _("Nothing to restore."),
            level='warning' if failed else 'info',
        )


# ================================================================
# DELETION AUDIT COUNTER ADMIN (Superadmin only)
# ================================================================

@admin.register(DeletionAuditCounter)
class DeletionAuditCounterAdmin(admin.ModelAdmin):
    """
    Superadmin-only analytics view for deletion/restore counters.

    Each row shows the cumulative count of a specific action
    (soft delete, hard delete, restore) for a specific Django
    model.  This gives superadmins a real-time dashboard of:

    * Total accounts ever soft-deleted vs restored (churn signal).
    * Total accounts permanently purged (GDPR compliance audit).
    * Per-model breakdown for non-user models in future.

    Access control
    --------------
    Only superusers can view this admin. Staff who are not
    superusers are entirely blocked from seeing this module.

    Data management
    ---------------
    Counters are auto-managed by ``DeletionAuditCounter.increment()``.
    No add / edit / delete via the admin — this is a read-only
    analytics dashboard. Counters reset only via direct DB access.
    """

    list_display = (
        'model_name',
        'action_display',
        'colored_total',
        'last_updated',
    )
    list_filter = (
        'model_name',
        'action',
    )
    search_fields = ('model_name',)
    ordering = ('model_name', 'action')
    readonly_fields = (
        'model_name',
        'action',
        'total',
        'last_updated',
    )

    def action_display(self, obj):
        """Human-readable action label."""
        return obj.get_action_display()
    action_display.short_description = _('Action')
    action_display.admin_order_field = 'action'

    def colored_total(self, obj):
        """
        Render the total with a colour-coded badge:
          🔴 hard_delete  — permanent purges
          🟠 soft_delete  — recoverable deletions
          🟢 restore      — recoveries / customer retention
        """
        colors = {
            'hard_delete': '#dc3545',
            'soft_delete': '#fd7e14',
            'restore':     '#28a745',
        }
        badges = {
            'hard_delete': '🔴',
            'soft_delete': '🟠',
            'restore':     '🟢',
        }
        color = colors.get(obj.action, '#6c757d')
        badge = badges.get(obj.action, '⚪')
        return format_html(
            '<span style="'
            'background:{};color:#fff;'
            'padding:2px 10px;border-radius:12px;'
            'font-size:13px;font-weight:700;">'
            '{} {}</span>',
            color,
            badge,
            obj.total,
        )
    colored_total.short_description = _('Total Count')
    colored_total.admin_order_field = 'total'

    # ── Permission overrides: strictly superadmin only ────────────

    def has_module_perms(self, request, app_label=None):
        """Block entire module from non-superusers."""
        return request.user.is_superuser

    def has_view_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_add_permission(self, request):
        """Counters are system-managed — no manual creation."""
        return False

    def has_change_permission(self, request, obj=None):
        """Counters are immutable from the admin UI."""
        return False

    def has_delete_permission(self, request, obj=None):
        """Only superusers may reset a counter (rare)."""
        return request.user.is_superuser


# ================================================================
# MODEL ANALYTICS ADMIN (Superadmin only)
# ================================================================

@admin.register(ModelAnalytics)
class ModelAnalyticsAdmin(admin.ModelAdmin):
    """
    Superadmin-only real-time analytics dashboard.

    One row per Django model. Shows:
    * total_created  — every record ever created
    * total_active   — currently alive records
    * total_soft_deleted — recoverable deletions
    * total_hard_deleted — permanent purges
    * identity_check — total_created == active + soft + hard?

    Access control: superadmin only (same policy as
    DeletionAuditCounterAdmin).
    """

    list_display = (
        'model_name',
        'app_label',
        'colored_created',
        'colored_active',
        'colored_soft_deleted',
        'colored_hard_deleted',
        'balance_check',
        'last_updated',
    )
    list_filter = ('app_label',)
    search_fields = ('model_name', 'app_label')
    ordering = ('app_label', 'model_name')
    readonly_fields = (
        'model_name',
        'app_label',
        'total_created',
        'total_active',
        'total_soft_deleted',
        'total_hard_deleted',
        'last_updated',
    )

    # ── Colored column methods ────────────────────────────────────

    def _badge(self, value, color):
        return format_html(
            '<span style="'
            'background:{c};color:#fff;'
            'padding:2px 9px;border-radius:10px;'
            'font-size:12px;font-weight:700;">'
            '{v}</span>',
            c=color,
            v=value,
        )

    def colored_created(self, obj):
        return self._badge(obj.total_created, '#6f42c1')
    colored_created.short_description = _('Total Created')
    colored_created.admin_order_field = 'total_created'

    def colored_active(self, obj):
        return self._badge(obj.total_active, '#28a745')
    colored_active.short_description = _('Active')
    colored_active.admin_order_field = 'total_active'

    def colored_soft_deleted(self, obj):
        return self._badge(obj.total_soft_deleted, '#fd7e14')
    colored_soft_deleted.short_description = _('Soft-Deleted')
    colored_soft_deleted.admin_order_field = 'total_soft_deleted'

    def colored_hard_deleted(self, obj):
        return self._badge(obj.total_hard_deleted, '#dc3545')
    colored_hard_deleted.short_description = _('Hard-Deleted')
    colored_hard_deleted.admin_order_field = 'total_hard_deleted'

    def balance_check(self, obj):
        """
        Algebraic identity check:
          total_created == total_active + total_soft_deleted +
                           total_hard_deleted

        Green ✅ = balanced. Red ❌ = drift detected (should
        never happen — indicates a missing signal or manual
        DB edit).
        """
        expected = (
            obj.total_active
            + obj.total_soft_deleted
            + obj.total_hard_deleted
        )
        ok = (obj.total_created == expected)
        if ok:
            return format_html(
                '<span style="color:#28a745;font-weight:700;">'
                '✅ OK</span>'
            )
        return format_html(
            '<span style="color:#dc3545;font-weight:700;">'
            '❌ Drift {diff}</span>',
            diff=obj.total_created - expected,
        )
    balance_check.short_description = _('Balance Check')

    # ── Permission overrides: strictly superadmin only ────────────

    def has_module_perms(self, request, app_label=None):
        return request.user.is_superuser

    def has_view_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser

