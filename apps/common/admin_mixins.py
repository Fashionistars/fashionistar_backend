# apps/common/admin_mixins.py
"""
Reusable admin mixins for enterprise-grade model administration.

Architecture:
    - SoftDeleteAdminMixin: Provides soft-delete/restore bulk
      actions, queryset override, and delete_model override
      for any ModelAdmin that manages SoftDeleteModel subclasses.

Usage:
    @admin.register(MyModel)
    class MyModelAdmin(SoftDeleteAdminMixin, admin.ModelAdmin):
        ...
"""

import logging

from django.contrib import admin
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
