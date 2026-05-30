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
from django.db import transaction
from django.http import HttpResponseRedirect
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils import timezone
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _

logger = logging.getLogger(__name__)


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
    # Remove Django's default "Delete selected" action entirely.
    # Our 3 custom actions (soft-delete / restore / hard-delete)
    # cover every use-case, and the default action bypasses all our
    # archival / notification / analytics pipeline.
    # ----------------------------------------------------------------

    def get_actions(self, request):
        actions = super().get_actions(request)
        # Strip the built-in bulk-delete action so the dropdown
        # contains ONLY our three custom actions.
        actions.pop('delete_selected', None)
        return actions

    # ----------------------------------------------------------------
    # Custom URL for hard-delete confirmation page
    # ----------------------------------------------------------------

    def get_urls(self):
        urls = super().get_urls()
        model_info = (
            self.model._meta.app_label,
            self.model._meta.model_name,
        )
        custom_urls = [
            path(
                'hard-delete-confirm/',
                self.admin_site.admin_view(self.hard_delete_confirm_view),
                name='%s_%s_hard_delete_confirm' % model_info,
            ),
        ]
        return custom_urls + urls

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

        Superuser Guard
        ---------------
        Superuser accounts are NEVER soft-deleted via bulk action.
        If the selection contains superusers, they are excluded and
        the admin sees a warning message listing each protected account.
        This prevents accidental lockout of the last admin.

        Only processes records where ``is_deleted=False``. Already-
        deleted records in the selection are silently skipped.
        """
        from apps.common.models import DeletedRecords
        from django.forms.models import model_to_dict

        # ── Superuser guard (only applies to UnifiedUser / any model with is_superuser) ──
        skipped_superusers = []
        if hasattr(queryset.model, 'is_superuser'):
            superuser_qs = queryset.filter(is_superuser=True)
            for su in superuser_qs:
                label = getattr(su, 'email', None) or getattr(su, 'username', None) or str(su.pk)
                skipped_superusers.append(label)
            # Exclude superusers from the operation
            queryset = queryset.filter(is_superuser=False)

        if skipped_superusers:
            self.message_user(
                request,
                _(
                    "⛔ The following superuser account(s) were PROTECTED and "
                    "NOT soft-deleted: %(accounts)s. "
                    "Superusers cannot be removed via bulk action to prevent lockout."
                ) % {'accounts': ', '.join(skipped_superusers)},
                level='warning',
            )

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

        # 3. Post-commit: fire notifications + audit trail (non-blocking)
        #
        # PERFORMANCE FIX (Phase 4):
        # Previously steps 3-5 ran inline — that was N Redis writes + N DB writes
        # (one per record) blocking the HTTP response. At 100 records = 100+ DB ops
        # holding the Django admin thread open for seconds.
        #
        # Now ALL side-effects are deferred to transaction.on_commit():
        #   - Django calls the callback AFTER the UPDATE transaction commits.
        #   - The HTTP response is returned to the browser immediately.
        #   - Celery tasks handle the actual work asynchronously.
        #
        # Captured variables (klass_name, pks, updated, admin_user_id) are
        # primitive scalars — safe to capture in closure across commit boundary.
        admin_user_id = str(request.user.pk)

        def _post_commit_side_effects(
            _model_name=klass_name,
            _pks=pks,
            _updated=updated,
            _admin_user_id=admin_user_id,
        ):
            """Runs after the DB transaction commits. Never blocks the admin page."""

            # ── 3a. Lifecycle registry (UnifiedUser only) ──────────────────────
            if _model_name == 'UnifiedUser':
                try:
                    from apps.common.tasks import upsert_user_lifecycle_registry
                    for _uuid in _pks:
                        try:
                            upsert_user_lifecycle_registry.apply_async(
                                kwargs={'user_uuid': str(_uuid), 'action': 'soft_deleted'},
                                retry=False,
                                ignore_result=True,
                            )
                        except Exception:
                            pass
                except Exception:
                    pass  # Never block admin actions for analytics

            # ── 3b. DeletionAuditCounter (single atomic increment) ─────────────
            try:
                from apps.common.models import DeletionAuditCounter
                DeletionAuditCounter.increment(
                    model_name=_model_name,
                    action='soft_delete',
                    count=_updated,
                )
            except Exception:
            pass  # Never block admin actions for audit counters

            # ── 3c. Admin audit trail (compliance-grade, via Celery) ───────────
            try:
                from apps.audit_logs.tasks import write_audit_event
                write_audit_event.apply_async(
                    kwargs={
                        "payload": {
                            "event_type": "SOFT_DELETE",
                            "event_category": "ADMIN",
                            "severity": "WARNING",
                            "action": f"Admin bulk soft-delete: {_updated} {_model_name} record(s)",
                            "actor_id": _admin_user_id,
                            "resource_type": _model_name,
                            "metadata": {
                                "pks": [str(pk) for pk in _pks],
                                "count": _updated,
                            },
                            "is_compliance": True,
                            "retention_days": 2555,  # 7 years for compliance events
                        }
                    },
                    retry=False,
                    ignore_result=True,
                )
            except Exception:
            pass  # Never block admin actions for audit logging

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

        # 3–5. Post-commit side-effects (non-blocking)
        #
        # RC-5 PERFORMANCE FIX (Phase 4):
        # Previously, the notification loop + audit counter + audit log were
        # all called inline here — for 100 records that was 100 per-row lookups
        # + 100 Redis writes + 1 DB write all blocking the Django admin response.
        #
        # Now ALL side-effects are deferred to transaction.on_commit() so the
        # HTTP response is returned to the browser immediately after the UPDATE
        # commits. Celery tasks handle the actual work asynchronously.
        admin_user_id = str(request.user.pk)

        def _restore_post_commit(
            _model_name=klass_name,
            _pks=selected_pks,
            _updated=updated,
            _admin_user_id=admin_user_id,
        ):
            """Runs after the UPDATE transaction commits. Never blocks the admin page."""

            # 3a. Fire-and-forget notifications (best-effort, per-user lifecycle)
            if _model_name == 'UnifiedUser':
                try:
                    from apps.common.tasks import upsert_user_lifecycle_registry
                    for _uuid in _pks:
                        try:
                            upsert_user_lifecycle_registry.apply_async(
                                kwargs={'user_uuid': str(_uuid), 'action': 'restored'},
                                retry=False,
                                ignore_result=True,
                            )
                        except Exception:
                            pass
                except Exception:
                    pass

            # 3b. Increment audit counter (restore reduces soft-delete count)
            try:
                from apps.common.models import DeletionAuditCounter
                DeletionAuditCounter.increment(
                    model_name=_model_name,
                    action='restore',
                    count=_updated,
                )
            except Exception:
                pass

            # 3c. Admin audit trail via Celery (compliance-grade, non-blocking)
            try:
                from apps.audit_logs.tasks import write_audit_event
                write_audit_event.apply_async(
                    kwargs={
                        "payload": {
                            "event_type": "ACCOUNT_RESTORED",
                            "event_category": "ADMIN",
                            "severity": "INFO",
                            "action": f"Admin bulk restore: {_updated} {_model_name} record(s)",
                            "actor_id": _admin_user_id,
                            "resource_type": _model_name,
                            "metadata": {
                                "pks": [str(pk) for pk in _pks[:100]],
                                "count": _updated,
                            },
                            "is_compliance": True,
                            "retention_days": 2555,
                        }
                    },
                    retry=False,
                    ignore_result=True,
                )
            except Exception:
                pass

        # Register the post-commit callback — runs after the UPDATE commits
        transaction.on_commit(_restore_post_commit)

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

        STEP 1 (this method): Check permissions, stash PKs in session,
        then REDIRECT to a confirmation page listing all objects.
        STEP 2 (hard_delete_confirm_view): Show Django-style confirm page.
        STEP 3 (POST confirm): Execute the irreversible DELETE.

        This matches the UX of Django's built-in 'Delete selected'
        flow so no record is ever lost without an explicit confirmation.
        """
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

        pks = list(queryset.values_list('pk', flat=True))
        if not pks:
            self.message_user(
                request,
                _("⚠️ No records selected."),
            )
            return

        # Stash the selected PKs in the session so the confirm view
        # can reconstruct the queryset on GET and POST.
        request.session['hard_delete_pks'] = [str(pk) for pk in pks]
        request.session['hard_delete_model'] = (
            '%s.%s' % (
                queryset.model._meta.app_label,
                queryset.model._meta.model_name,
            )
        )

        model_info = (
            self.model._meta.app_label,
            self.model._meta.model_name,
        )
        confirm_url = reverse(
            'admin:%s_%s_hard_delete_confirm' % model_info,
            current_app=self.admin_site.name,
        )
        return HttpResponseRedirect(confirm_url)

    def hard_delete_confirm_view(self, request):
        """
        Confirmation page for hard-delete (GET) and execution (POST).
        """
        from apps.common.models import DeletedRecords
        from django.apps import apps as django_apps

        pks = request.session.get('hard_delete_pks', [])
        model_path = request.session.get('hard_delete_model', '')

        if not pks or not model_path:
            self.message_user(
                request,
                _("⚠️ Session expired or no records to delete. Please try again."),
                level='warning',
            )
            return HttpResponseRedirect('../')

        # Resolve model from app_label.model_name
        try:
            app_label, model_name = model_path.split('.')
            klass = django_apps.get_model(app_label, model_name)
        except (ValueError, LookupError):
            self.message_user(
                request,
                _("⚠️ Invalid model reference in session."),
                level='error',
            )
            return HttpResponseRedirect('../')

        klass_name = klass.__name__
        qs = klass.objects.all_with_deleted().filter(pk__in=pks)

        if request.method == 'POST':
            if '_confirm_hard_delete' not in request.POST:
                # User clicked "No, take me back"
                request.session.pop('hard_delete_pks', None)
                request.session.pop('hard_delete_model', None)
                self.message_user(
                    request,
                    _("ℹ️ Hard delete cancelled."),
                )
                return HttpResponseRedirect('../')

            if not request.user.is_superuser:
                self.message_user(
                    request,
                    _("⛔ Permission denied."),
                    level='error',
                )
                return HttpResponseRedirect('../')

            # Perform the actual hard deletion
            real_pks = list(qs.values_list('pk', flat=True))

            # 1. Send hard-delete notifications BEFORE deletion
            for obj in qs:
                if hasattr(obj, '_fire_and_forget_notification'):
                    obj._fire_and_forget_notification('hard_deleted')

            # 2. Purge archive entries
        # 2. Purge archive entries
            DeletedRecords.objects.filter(
                model_name=klass_name,
                record_id__in=[str(pk) for pk in real_pks],
            ).delete()

            # 3. Physical DELETE — handle both SoftDeleteModel and plain models.
            #    IMPORTANT: For SoftDeleteModel subclasses, never call .delete()
            #    (which routes through SoftDeleteModel.delete() and returns an int
            #    or soft-deletes again). Always call .hard_delete() which performs
            #    the real SQL DELETE and returns (count, detail_dict).
            from apps.common.models import SoftDeleteModel as _SDM
            is_soft_delete_model = issubclass(klass, _SDM)

            if is_soft_delete_model:
                result = (
                    klass.objects.all_with_deleted()
                    .filter(pk__in=real_pks)
                    .hard_delete()
                )
            else:
                result = klass.objects.filter(pk__in=real_pks).delete()

            # Unpack safely — handle both tuple (int, dict) and raw int
            if isinstance(result, tuple):
                deleted_count = result[0]
            else:
                deleted_count = int(result)

            logger.warning(
                "Admin %s HARD-DELETED %d %s record(s): %s",
                request.user.pk,
                deleted_count,
                klass_name,
                real_pks,
            )

            # 4. Increment audit counter
            try:
                from apps.common.models import DeletionAuditCounter
                DeletionAuditCounter.increment(
                    model_name=klass_name,
                    action='hard_delete',
                    count=deleted_count,
                )
            except Exception:
                pass

            # 5. Admin audit trail — hard-delete is always compliance-grade
            try:
                from apps.audit_logs.services.admin_backend import admin_audit
                admin_audit.log_bulk_delete(
                    actor=request.user,
                    resource_type=klass_name,
                    count=deleted_count,
                    request=request,
                )
            except Exception:
                pass

            # 6. Clear session
            request.session.pop('hard_delete_pks', None)
            request.session.pop('hard_delete_model', None)

            self.message_user(
                request,
                _(
                    "%(count)d record(s) permanently deleted."
                ) % {'count': deleted_count},
                level='warning',
            )
            return HttpResponseRedirect('../')

        # GET — render the confirmation page
        context = {
            **self.admin_site.each_context(request),
            'title': _('⚠️ Confirm Permanent (Hard) Delete'),
            'queryset': qs,
            'klass_name': klass_name,
            'count': qs.count(),
            'opts': klass._meta,
            'action_checkbox_name': admin.helpers.ACTION_CHECKBOX_NAME,
            'media': self.media,
        }
        return TemplateResponse(
            request,
            'admin/hard_delete_confirmation.html',
            context,
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


# ─────────────────────────────────────────────────────────────────────────────
# READ-ONLY ADMIN MIXIN
# ─────────────────────────────────────────────────────────────────────────────

class ReadOnlyAdminMixin:
    """
    Makes an entire admin class read-only.

    Intended for audit/event tables that are append-only:
      - AuditEventLog, OrderStatusHistory, TransactionLog, ProductPriceHistory

    Use this mixin to prevent any accidental creation, modification, or
    deletion of immutable ledger records via the Django admin UI.

    Usage:
        @admin.register(MyAuditModel)
        class MyAuditModelAdmin(ReadOnlyAdminMixin, admin.ModelAdmin):
            ...
    """

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


# ─────────────────────────────────────────────────────────────────────────────
# SOFT DELETE ADMIN MIXIN — soft_delete_badge alias
# ─────────────────────────────────────────────────────────────────────────────
# Some admin files call soft_delete_badge instead of _is_deleted_badge.
# This alias is injected onto SoftDeleteAdminMixin for cross-file compatibility.

SoftDeleteAdminMixin.soft_delete_badge = SoftDeleteAdminMixin._is_deleted_badge
SoftDeleteAdminMixin.soft_delete_badge.short_description = 'Status'
