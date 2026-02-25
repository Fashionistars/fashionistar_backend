# apps/common/admin_mixins.py
"""
Reusable admin mixins for enterprise-grade model administration.

Architecture:
    - SoftDeleteAdminMixin: Provides soft-delete/restore bulk
      actions, queryset override, delete_model override,
      visual deleted badge in list_display, is_deleted filter
      in list_filter, and per-model soft-delete tab in
      ModelAdmin change form for any ModelAdmin that manages
      SoftDeleteModel subclasses.

Usage:
    @admin.register(MyModel)
    class MyModelAdmin(SoftDeleteAdminMixin, admin.ModelAdmin):
        ...
"""

import logging

from django.contrib import admin
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

logger = logging.getLogger('application')


class SoftDeleteAdminMixin:
    """
    Reusable mixin for admin classes managing soft-delete models.

    Provides:
        - ``get_queryset``: Includes soft-deleted records so
          admins can see and restore them.
        - ``delete_model``: Overrides single-object delete to
          use the model's ``soft_delete()`` method.
        - ``soft_delete_selected``: Bulk action to soft-delete
          selected records.
        - ``restore_selected``: Bulk action to restore
          soft-deleted records.
        - ``_is_deleted_badge``: Visual 🔴/🟢 badge column
          in the list view.
        - ``get_list_display``: Injects the badge as the first
          column in every list view automatically.
        - ``get_list_filter``: Injects ``is_deleted`` filter
          pill to the right panel automatically.

    To use, add ``SoftDeleteAdminMixin`` as the first parent
    in your admin class's MRO, and include the actions in
    your ``actions`` list or leave the default.
    """

    def get_queryset(self, request):
        """
        Return all records including soft-deleted ones.

        Uses ``all_with_deleted()`` if the model's manager
        supports it, otherwise falls back to the default
        ``all()`` queryset.

        Args:
            request: The current HTTP request.

        Returns:
            QuerySet: All records (alive + deleted).
        """
        model = self.model
        if hasattr(model.objects, 'all_with_deleted'):
            return model.objects.all_with_deleted()
        return super().get_queryset(request)

    def delete_model(self, request, obj):
        """
        Override single-object delete to use soft-delete.

        Instead of permanently removing the record, delegates
        to the model's ``soft_delete()`` method for safe
        archival and audit trail preservation.

        Args:
            request: The current HTTP request.
            obj: The model instance to soft-delete.
        """
        try:
            obj.soft_delete()
            logger.info(
                "Admin %s soft-deleted %s %s via delete",
                request.user.pk,
                obj.__class__.__name__,
                obj.pk,
            )
        except Exception:
            logger.exception(
                "Failed to soft-delete %s %s via delete",
                obj.__class__.__name__,
                obj.pk,
            )
            raise

    @admin.action(
        description=_("Soft-delete selected records")
    )
    def soft_delete_selected(self, request, queryset):
        """
        Bulk soft-delete action for the admin list view.

        Iterates over selected alive records and calls each
        model's ``soft_delete()`` method to ensure archival
        in ``DeletedRecords`` and proper audit logging.

        Args:
            request: The current HTTP request.
            queryset: Selected model records.
        """
        count = 0
        for obj in queryset.filter(is_deleted=False):
            try:
                obj.soft_delete()
                count += 1
                logger.info(
                    "Admin %s soft-deleted %s %s",
                    request.user.pk,
                    obj.__class__.__name__,
                    obj.pk,
                )
            except Exception:
                logger.exception(
                    "Failed to soft-delete %s %s",
                    obj.__class__.__name__,
                    obj.pk,
                )

        self.message_user(
            request,
            _("%(count)d record(s) soft-deleted "
              "successfully.") % {'count': count},
        )

    @admin.action(
        description=_("Restore selected records")
    )
    def restore_selected(self, request, queryset):
        """
        Bulk restore action for the admin list view.

        Restores soft-deleted records via each model's
        ``restore()`` method, clearing the ``is_deleted``
        flag and ``deleted_at`` timestamp.

        Args:
            request: The current HTTP request.
            queryset: Selected model records.
        """
        count = 0
        for obj in queryset.filter(is_deleted=True):
            try:
                obj.restore()
                count += 1
                logger.info(
                    "Admin %s restored %s %s",
                    request.user.pk,
                    obj.__class__.__name__,
                    obj.pk,
                )
            except Exception:
                logger.exception(
                    "Failed to restore %s %s",
                    obj.__class__.__name__,
                    obj.pk,
                )

        self.message_user(
            request,
            _("%(count)d record(s) restored "
              "successfully.") % {'count': count},
        )

    # ─── Visual Helpers ───────────────────────────────────

    def _is_deleted_badge(self, obj):
        """
        Render a colour-coded status badge for the list view.

        Shows 🔴 DELETED for soft-deleted records and a
        green ACTIVE badge for live records, so admins can
        immediately identify record state without opening the
        change form.

        Args:
            obj: The model instance.

        Returns:
            str: Safe HTML badge markup.
        """
        if obj.is_deleted:
            return format_html(
                '<span style="'
                'background:#dc3545;color:#fff;'
                'padding:2px 8px;border-radius:12px;'
                'font-size:11px;font-weight:600;'
                'letter-spacing:.5px;">'
                '🔴 DELETED</span>'
            )
        return format_html(
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
        """
        Inject the status badge as the FIRST column.

        Ensures every admin using this mixin shows the
        soft-delete state at a glance without requiring
        the subclass to manually add it to ``list_display``.

        Args:
            request: The current HTTP request.

        Returns:
            tuple: Prepended list_display with badge.
        """
        base = super().get_list_display(request)
        if '_is_deleted_badge' not in base:
            return ('_is_deleted_badge',) + tuple(base)
        return base

    def get_list_filter(self, request):
        """
        Inject ``is_deleted`` into the right-hand filter panel.

        Automatically adds the soft-delete filter pill so that
        admins can click "Yes / No" to show only deleted or
        only alive records.

        Args:
            request: The current HTTP request.

        Returns:
            tuple: list_filter with is_deleted injected.
        """
        base = super().get_list_filter(request)
        if 'is_deleted' not in base:
            return tuple(base) + ('is_deleted',)
        return base
