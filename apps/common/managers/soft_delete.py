# apps/common/managers/soft_delete.py
"""
Enterprise-grade QuerySet and Manager for soft-delete models.

Architecture:
    - SoftDeleteQuerySet: Custom queryset with alive/dead/restore/
      hard_delete chainable methods.
    - SoftDeleteManager: Default manager that excludes deleted
      records from normal queries, with explicit methods to
      include them when needed.

Usage:
    class MyModel(SoftDeleteModel):
        objects = SoftDeleteManager()       # default: alive only
        all_objects = SoftDeleteManager(    # unfiltered
            alive_only=False,
        )

    MyModel.objects.all()               # alive records
    MyModel.objects.all_with_deleted()  # everything
    MyModel.objects.deleted_only()      # only soft-deleted
    MyModel.objects.all().dead()        # queryset chain
"""

import logging

from django.db import models
from django.utils import timezone

logger = logging.getLogger('application')


# ================================================================
# 1. QUERYSET
# ================================================================

class SoftDeleteQuerySet(models.QuerySet):
    """
    Custom queryset providing chainable soft-delete operations.

    Every method returns a new queryset (immutable chaining),
    keeping Django's lazy-evaluation model intact.
    """

    def alive(self):
        """
        Return only non-deleted records.

        Returns:
            SoftDeleteQuerySet: Filtered to ``is_deleted=False``.
        """
        return self.filter(is_deleted=False)

    def dead(self):
        """
        Return only soft-deleted records.

        Returns:
            SoftDeleteQuerySet: Filtered to ``is_deleted=True``.
        """
        return self.filter(is_deleted=True)

    def soft_delete(self):
        """
        Bulk soft-delete all records in this queryset.

        Sets ``is_deleted=True`` and ``deleted_at`` to the
        current timestamp via a single UPDATE query. Does NOT
        call ``Model.soft_delete()`` per-row, so the
        ``DeletedRecords`` archive is not populated. Use the
        model method directly when archival is required.

        Returns:
            int: Number of rows updated.
        """
        count = self.update(
            is_deleted=True,
            deleted_at=timezone.now(),
        )
        logger.info(
            "Bulk soft-deleted %d record(s) via queryset",
            count,
        )
        return count

    def restore(self):
        """
        Bulk restore all soft-deleted records in this queryset.

        Clears ``is_deleted`` and ``deleted_at`` via a single
        UPDATE query.

        Returns:
            int: Number of rows updated.
        """
        count = self.update(
            is_deleted=False,
            deleted_at=None,
        )
        logger.info(
            "Bulk restored %d record(s) via queryset",
            count,
        )
        return count

    def hard_delete(self):
        """
        Permanently delete all records in this queryset.

        Bypasses soft-delete and performs a physical SQL DELETE.
        Use with extreme caution — this is irreversible.

        Returns:
            tuple: (count, {model: count}) as returned by
                Django's ``QuerySet.delete()``.
        """
        logger.warning(
            "Hard-deleting %d record(s) via queryset — "
            "this is irreversible",
            self.count(),
        )
        return super().delete()

    def delete(self):
        """
        Override default ``delete()`` to soft-delete instead.

        This prevents accidental hard-deletion via standard
        Django ORM calls (e.g., ``queryset.delete()``).
        Callers who need physical deletion must use
        ``hard_delete()`` explicitly.

        Returns:
            int: Number of rows soft-deleted.
        """
        return self.soft_delete()


# ================================================================
# 2. MANAGER
# ================================================================

class SoftDeleteManager(models.Manager):
    """
    Custom manager for models using ``SoftDeleteModel``.

    By default, all queries exclude soft-deleted records. This
    mirrors the typical business expectation that "deleted"
    records are invisible unless explicitly requested.

    Args:
        alive_only (bool): If ``True`` (default), the default
            queryset filters out soft-deleted records. Set to
            ``False`` for an unfiltered manager.

    Example:
        class MyModel(SoftDeleteModel):
            objects = SoftDeleteManager()
            all_objects = SoftDeleteManager(alive_only=False)
    """

    def __init__(self, *args, alive_only=True, **kwargs):
        self._alive_only = alive_only
        super().__init__(*args, **kwargs)

    def get_queryset(self):
        """
        Return the base queryset, optionally filtered to
        exclude soft-deleted records.

        Returns:
            SoftDeleteQuerySet: The base queryset.
        """
        qs = SoftDeleteQuerySet(self.model, using=self._db)
        if self._alive_only:
            return qs.alive()
        return qs

    def all_with_deleted(self):
        """
        Return ALL records including soft-deleted ones.

        This bypasses the default alive-only filter. Use this
        in admin views, data exports, and audit queries.

        Returns:
            SoftDeleteQuerySet: Unfiltered queryset.
        """
        return SoftDeleteQuerySet(
            self.model,
            using=self._db,
        )

    def deleted_only(self):
        """
        Return only soft-deleted records.

        Useful for admin "trash" views and recovery workflows.

        Returns:
            SoftDeleteQuerySet: Filtered to
                ``is_deleted=True``.
        """
        return SoftDeleteQuerySet(
            self.model,
            using=self._db,
        ).dead()
