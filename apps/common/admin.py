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

from apps.common.models import DeletedRecords

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
