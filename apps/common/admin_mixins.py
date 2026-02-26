# apps/common/admin_mixins.py
"""
Reusable admin mixins for enterprise-grade model administration.

Architecture:
    SoftDeleteAdminMixin
    ────────────────────
    Provides soft-delete/restore/hard-delete bulk actions,
    queryset override, delete_model override, visual status
    badge in list_display, is_deleted filter in list_filter,
    and per-model soft-delete tab in the change form.

Performance
-----------
All bulk actions use a **single** ``QuerySet.update()`` call
instead of per-row Python loops, making them suitable for
datasets of 100K+ records.  Individual-record operations
(soft_delete / restore) still call the model method so that
``DeletedRecords`` archival and per-record logging are
preserved.

Usage:
    @admin.register(MyModel)
    class MyModelAdmin(SoftDeleteAdminMixin, admin.ModelAdmin):
        actions = [
            'soft_delete_selected',
            'restore_selected',
            'hard_delete_selected',
        ]
"""

import logging

from django.contrib import admin
from django.utils import timezone
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _

logger = logging.getLogger('application')


class SoftDeleteAdminMixin:
    """
    Reusable mixin for admin classes managing soft-delete models.

    Provides
    --------
    * ``get_queryset``        — shows all records (alive + deleted).
    * ``delete_model``        — single-object delete → soft_delete().
    * ``delete_queryset``     — bulk Django delete → soft_delete bulk.
    * ``soft_delete_selected``— bulk soft-delete action (1 SQL UPDATE).
    * ``restore_selected``    — bulk restore action (1 SQL UPDATE,
                                purges archive, correct manager).
    * ``hard_delete_selected``— irreversible bulk hard-delete for
                                superusers only.
    * ``_is_deleted_badge``   — 🔴/🟢 status pill in list view.
    * ``get_list_display``    — auto-injects badge as first column.
    * ``get_list_filter``     — auto-injects is_deleted filter pill.
    """

    # ----------------------------------------------------------------
    # Queryset
    # ----------------------------------------------------------------

    def get_queryset(self, request):
        """
        Return ALL records including soft-deleted ones.

        Uses ``all_with_deleted()`` if the model's manager
        supports it, otherwise falls back to the default queryset.
        This ensures admins can always see (and restore) deleted
        records without navigating to a separate "trash" view.
        """
        model = self.model
        if hasattr(model.objects, 'all_with_deleted'):
            return model.objects.all_with_deleted()
        return super().get_queryset(request)

    # ----------------------------------------------------------------
    # Single-object delete override (from change-form Delete button)
    # ----------------------------------------------------------------

    def delete_model(self, request, obj):
        """
        Override single-object delete to use soft-delete.

        Called when an admin clicks the Delete button on a
        change form and confirms. Archives the record and sets
        ``is_deleted=True``.
        """
        try:
            obj.soft_delete()
            logger.info(
                "Admin %s soft-deleted %s %s via delete_model",
                request.user.pk,
                obj.__class__.__name__,
                obj.pk,
            )
        except Exception:
            logger.exception(
                "Failed to soft-delete %s %s via delete_model",
                obj.__class__.__name__,
                obj.pk,
            )
            raise

    # ----------------------------------------------------------------
    # Bulk delete override (Django's built-in "Delete selected" action)
    # ----------------------------------------------------------------

    def delete_queryset(self, request, queryset):
        """
        Override Django's built-in "Delete selected" action.

        Routes records correctly:
        - **Alive records** (is_deleted=False): soft-delete via the
          model's ``soft_delete()`` method so archival happens.
        - **Already-deleted records** (is_deleted=True): no-op here
          (they should be hard-deleted via the explicit
          ``hard_delete_selected`` action).

        This prevents the common bug where "Delete selected
        Unified Users" silently no-ops on already soft-deleted rows
        (because the overridden ``queryset.delete()`` calls
        ``soft_delete()`` again, which is a no-op).
        """
        alive_qs = queryset.filter(is_deleted=False)
        count = 0
        for obj in alive_qs.iterator(chunk_size=500):
            try:
                obj.soft_delete()
                count += 1
            except Exception:
                logger.exception(
                    "Error in delete_queryset for %s %s",
                    obj.__class__.__name__,
                    obj.pk,
                )
        if count:
            logger.info(
                "Admin %s soft-deleted %d records via "
                "delete_queryset",
                request.user.pk,
                count,
            )

    # ----------------------------------------------------------------
    # Bulk action: soft-delete
    # ----------------------------------------------------------------

    @admin.action(
        description=_("Soft-delete selected records")
    )
    def soft_delete_selected(self, request, queryset):
        """
        Bulk soft-delete action.

        Performance
        -----------
        Archives each alive record individually (so that
        ``DeletedRecords`` snapshots are created per-row), then
        issues a **single** ``QuerySet.update()`` to mark them all
        deleted at once — dramatically faster than N individual
        ``save()`` calls for large selections.

        Only processes records where ``is_deleted=False``. Already-
        deleted records in the selection are silently skipped.
        """
        from apps.common.models import DeletedRecords
        from django.forms.models import model_to_dict

        alive_qs = queryset.filter(is_deleted=False)
        pks = list(alive_qs.values_list('pk', flat=True))

        if not pks:
            self.message_user(
                request,
                _("No active records selected — nothing to do."),
            )
            return

        # 1. Archive snapshots (one INSERT per record)
        archive_entries = []
        klass = queryset.model
        klass_name = klass.__name__
        for obj in alive_qs.iterator(chunk_size=500):
            try:
                raw = model_to_dict(obj)
                data = {
                    k: str(v) if v is not None else None
                    for k, v in raw.items()
                }
            except Exception:
                data = {'pk': str(obj.pk)}
            archive_entries.append(
                DeletedRecords(
                    model_name=klass_name,
                    record_id=str(obj.pk),
                    data=data,
                )
            )
        DeletedRecords.objects.bulk_create(
            archive_entries,
            ignore_conflicts=True,
        )

        # 2. Single bulk UPDATE
        now = timezone.now()
        updated = klass.objects.filter(
            pk__in=pks,
            is_deleted=False,
        ).update(
            is_deleted=True,
            deleted_at=now,
        )

        logger.info(
            "Admin %s bulk soft-deleted %d %s record(s)",
            request.user.pk,
            updated,
            klass_name,
        )

        self.message_user(
            request,
            _(
                "%(count)d record(s) soft-deleted successfully."
            ) % {'count': updated},
        )

    # ----------------------------------------------------------------
    # Bulk action: restore
    # ----------------------------------------------------------------

    @admin.action(
        description=_("Restore selected records")
    )
    def restore_selected(self, request, queryset):
        """
        Bulk restore action.

        Fixes
        -----
        Previous implementation looped per-row and called
        ``obj.restore()`` which internally used the alive-only
        manager → matched 0 rows → silent no-op.

        This implementation:
        1. Uses ``all_with_deleted()`` to find truly deleted rows.
        2. Bulk-restores via a **single** ``QuerySet.update()``.
        3. Purges matching ``DeletedRecords`` archive entries in one
           bulk ``DELETE`` — keeps the audit table accurate.
        4. Dispatches fire-and-forget notifications (non-blocking).
        """
        from apps.common.models import DeletedRecords

        klass = queryset.model
        klass_name = klass.__name__

        # Get PKs of selected records that are actually deleted.
        # queryset here comes from get_queryset() which uses
        # all_with_deleted(), so this filter is applied on top of
        # the already-unfiltered queryset.
        selected_pks = list(
            queryset.filter(is_deleted=True).values_list('pk', flat=True)
        )

        if not selected_pks:
            self.message_user(
                request,
                _("No soft-deleted records in selection — "
                  "nothing to restore."),
            )
            return

        # 1. Single bulk UPDATE via the unfiltered manager
        updated = klass.objects.all_with_deleted().filter(
            pk__in=selected_pks,
            is_deleted=True,
        ).update(
            is_deleted=False,
            deleted_at=None,
        )

        # 2. Purge archive entries (one DELETE per model_name group)
        purge_count, _detail = DeletedRecords.objects.filter(
            model_name=klass_name,
            record_id__in=[str(pk) for pk in selected_pks],
        ).delete()

        logger.info(
            "Admin %s bulk-restored %d %s record(s); "
            "purged %d archive entries",
            request.user.pk,
            updated,
            klass_name,
            purge_count,
        )

        # 3. Fire-and-forget notifications for each restored user
        #    (best-effort — never blocks the response)
        for obj in klass.objects.filter(pk__in=selected_pks):
            if hasattr(obj, '_fire_and_forget_notification'):
                obj._fire_and_forget_notification('restored')

        self.message_user(
            request,
            _(
                "%(count)d record(s) restored successfully."
            ) % {'count': updated},
        )

    # ----------------------------------------------------------------
    # Bulk action: hard-delete (irreversible — superuser only)
    # ----------------------------------------------------------------

    @admin.action(
        description=_("⚠️  Hard-delete selected (PERMANENT — superuser only)")
    )
    def hard_delete_selected(self, request, queryset):
        """
        Permanently delete selected records from the database.

        .. danger::
            This action is **irreversible**. Records are physically
            removed from the database and cannot be recovered.
            Only superusers may execute this action.

        Use cases
        ---------
        * Purging soft-deleted records that are no longer needed.
        * GDPR "right to erasure" requests.
        * Cleaning up test data.

        Behaviour
        ---------
        * Non-superusers: rejected with an error message.
        * Alive records: first soft-deleted (archived), then
          hard-deleted so the audit trail is preserved.
        * Already soft-deleted records: hard-deleted directly,
          ``DeletedRecords`` entry also purged.
        """
        from apps.common.models import DeletedRecords

        if not request.user.is_superuser:
            self.message_user(
                request,
                _(
                    "⛔ Permission denied: only superusers may "
                    "permanently delete records."
                ),
                level='error',
            )
            return

        klass = queryset.model
        klass_name = klass.__name__
        pks = list(queryset.values_list('pk', flat=True))

        # Purge archive entries first
        DeletedRecords.objects.filter(
            model_name=klass_name,
            record_id__in=[str(pk) for pk in pks],
        ).delete()

        # Physical deletion via all_with_deleted() so we can hit
        # both alive and soft-deleted rows in one call.
        deleted_count, _detail = klass.objects.all_with_deleted().filter(
            pk__in=pks,
        ).hard_delete()

        logger.warning(
            "Admin %s HARD-DELETED %d %s record(s): %s",
            request.user.pk,
            deleted_count,
            klass_name,
            pks,
        )

        self.message_user(
            request,
            _(
                "%(count)d record(s) permanently deleted."
            ) % {'count': deleted_count},
            level='warning',
        )

    # ----------------------------------------------------------------
    # Visual helpers
    # ----------------------------------------------------------------

    def _is_deleted_badge(self, obj):
        """
        Render a colour-coded status badge for the list view.

        Returns a red 🔴 DELETED or green 🟢 ACTIVE pill so
        admins can see record state at a glance.
        """
        if obj.is_deleted:
            return mark_safe(
                '<span style="'
                'background:#dc3545;color:#fff;'
                'padding:2px 8px;border-radius:12px;'
                'font-size:11px;font-weight:600;'
                'letter-spacing:.5px;">'
                '🔴 DELETED</span>'
            )
        return mark_safe(
            '<span style="'
            'background:#28a745;color:#fff;'
            'padding:2px 8px;border-radius:12px;'
            'font-size:11px;font-weight:600;'
            'letter-spacing:.5px;">'
            '🟢 ACTIVE</span>'
        )

    _is_deleted_badge.short_description = _('Status')
    _is_deleted_badge.admin_order_field = 'is_deleted'

    def get_list_display(self, request):
        """Inject the status badge as the first column."""
        base = super().get_list_display(request)
        if '_is_deleted_badge' not in base:
            return ('_is_deleted_badge',) + tuple(base)
        return base

    def get_list_filter(self, request):
        """Inject ``is_deleted`` into the right-hand filter panel."""
        base = super().get_list_filter(request)
        if 'is_deleted' not in base:
            return tuple(base) + ('is_deleted',)
        return base
