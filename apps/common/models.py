# apps/common/models.py
"""
Enterprise abstract base models for the Fashionistar platform.

Architecture:
    - TimeStampedModel: Auto-timestamping (created_at, updated_at).
    - SoftDeleteModel:  Soft-delete with archival, restore, and
                        background notification via Celery tasks.
    - DeletedRecords:   Archive table for soft-deleted record data.
    - HardDeleteMixin:  Protected hard-delete with permission checks
                        and Cloudinary media cleanup.

All abstract models use ``SoftDeleteManager`` as the default
manager so that ``is_deleted=True`` records are filtered out
of normal queries. Admin and audit views use
``all_with_deleted()`` to see everything.
"""

import logging

import uuid6
from django.core.exceptions import PermissionDenied
from django.db import models
from django.utils import timezone

logger = logging.getLogger('application')


# ================================================================
# 1. TIMESTAMPED MODEL
# ================================================================

class TimeStampedModel(models.Model):
    """
    Abstract base class that provides self-updating
    ``created_at`` and ``updated_at`` fields.

    Uses UUID7 as the primary key for globally unique,
    time-ordered identifiers.
    """

    id = models.UUIDField(
        primary_key=True,
        default=uuid6.uuid7,
        editable=False,
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
        help_text="Timestamp when the record was created.",
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        help_text="Timestamp when the record was last updated.",
    )

    class Meta:
        abstract = True


# ================================================================
# 2. SOFT-DELETE MODEL
# ================================================================

class SoftDeleteModel(models.Model):
    """
    Abstract base class that prevents physical deletion.

    Records are marked as deleted (``is_deleted=True``) and
    archived to ``DeletedRecords`` for recovery. The default
    manager (``SoftDeleteManager``) filters out deleted records
    from normal queries.

    On soft-delete and restore, background Celery tasks dispatch
    email/SMS notifications to the affected user via the
    platform's ``EmailManager`` and ``SMSManager``.
    """

    is_deleted = models.BooleanField(
        default=False,
        db_index=True,
        help_text="Flag indicating if the record is soft-deleted.",
    )
    deleted_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Timestamp of soft deletion.",
    )

    class Meta:
        abstract = True

    def soft_delete(self):
        """
        Mark the record as deleted and archive it.

        Steps:
            1. Archive a copy to ``DeletedRecords``.
            2. Set ``is_deleted=True`` and ``deleted_at``.
            3. Dispatch email/SMS notification via Celery.
        """
        try:
            # Lazy import to avoid circular dependencies
            from apps.common.models import DeletedRecords

            # Archive for recovery
            DeletedRecords.objects.create(
                model_name=self.__class__.__name__,
                record_id=str(self.pk),
                data=self.__dict__,  #erialize for recovery
            )

            self.is_deleted = True
            self.deleted_at = timezone.now()
            self.save(update_fields=['is_deleted', 'deleted_at'])

            logger.info(
                "Soft-deleted %s with ID %s",
                self.__class__.__name__,
                self.pk,
            )

            # Dispatch background notifications
            self._dispatch_status_notification('soft_deleted')

        except Exception:
            logger.exception(
                "Error during soft-delete of %s %s",
                self.__class__.__name__,
                self.pk,
            )
            raise

    def restore(self):
        """
        Restore a soft-deleted record.

        Clears ``is_deleted`` and ``deleted_at``, then
        dispatches a restoration notification via Celery.
        """
        try:
            self.is_deleted = False
            self.deleted_at = None
            self.save(update_fields=['is_deleted', 'deleted_at'])

            logger.info(
                "Restored %s with ID %s",
                self.__class__.__name__,
                self.pk,
            )

            # Dispatch background notifications
            self._dispatch_status_notification('restored')

        except Exception:
            logger.exception(
                "Error during restore of %s %s",
                self.__class__.__name__,
                self.pk,
            )
            raise

    def _dispatch_status_notification(self, action):
        """
        Dispatch email and SMS notifications as background
        Celery tasks when the account status changes.

        Only fires if the model instance has ``email`` or
        ``phone`` attributes (i.e., it is a user-like model).
        Non-user models that inherit ``SoftDeleteModel`` will
        silently skip notification.

        Args:
            action (str): One of 'soft_deleted', 'hard_deleted',
                'restored'.
        """
        from apps.common.tasks import (
            send_account_status_email,
            send_account_status_sms,
        )

        email = getattr(self, 'email', None)
        phone = getattr(self, 'phone', None)

        if email:
            send_account_status_email.delay(
                email=str(email),
                action=action,
            )
        if phone:
            send_account_status_sms.delay(
                phone=str(phone),
                action=action,
            )


# ================================================================
# 3. DELETED RECORDS ARCHIVE
# ================================================================

class DeletedRecords(models.Model):
    """
    Archive table for soft-deleted records.

    Stores serialized data from any model that inherits
    ``SoftDeleteModel``, allowing full recovery without
    querying the main table.
    """

    model_name = models.CharField(
        max_length=100,
        help_text="Name of the model that was deleted.",
    )
    record_id = models.CharField(
        max_length=255,
        help_text=(
            "Primary key of the deleted record "
            "(UUID or Int)."
        ),
    )
    data = models.JSONField(
        help_text="Serialized data of the deleted record.",
    )
    deleted_at = models.DateTimeField(
        auto_now_add=True,
        help_text="Timestamp of deletion.",
    )

    class Meta:
        verbose_name = "Deleted Record"
        verbose_name_plural = "Deleted Records"
        indexes = [
            models.Index(
                fields=['model_name', 'record_id'],
                name='idx_deleted_model_record',
            ),
        ]

    def __str__(self):
        return "%s [%s] deleted at %s" % (
            self.model_name,
            self.record_id,
            self.deleted_at,
        )


# ================================================================
# 4. HARD-DELETE MIXIN
# ================================================================

class HardDeleteMixin:
    """
    Mixin for hard-delete functionality, protected for
    admins, vendors, and record owners.

    Handles Cloudinary media deletion and dispatches a
    'hard_deleted' notification via Celery before physical
    deletion.
    """

    def hard_delete(self, user):
        """
        Permanently delete the record from the database.

        Protected: Only admins, vendors (for their own
        records), or owners can perform this operation.

        Steps:
            1. Permission check.
            2. Dispatch 'hard_deleted' notification.
            3. Clean up Cloudinary media.
            4. Physical SQL DELETE.

        Args:
            user: The user performing the deletion.

        Raises:
            PermissionDenied: If user lacks permission.
        """
        try:
            # Permission check
            if not (
                user.is_superuser
                or user.role in ['admin', 'vendor']
                or self.is_owner(user)
            ):
                raise PermissionDenied(
                    "You do not have permission to "
                    "perform hard delete."
                )

            # Dispatch notification BEFORE deletion
            if hasattr(self, '_dispatch_status_notification'):
                self._dispatch_status_notification(
                    'hard_deleted'
                )

            # Handle media deletion (Cloudinary)
            if hasattr(self, 'avatar') and self.avatar:
                from apps.common.utils import (
                    delete_cloudinary_asset,
                )
                delete_cloudinary_asset(self.avatar.name)

            logger.info(
                "Hard-deleting %s with ID %s by user %s",
                self.__class__.__name__,
                self.pk,
                user.pk,
            )

            # Perform physical delete
            super().delete()

        except PermissionDenied:
            raise
        except Exception:
            logger.exception(
                "Error during hard-delete of %s %s",
                self.__class__.__name__,
                self.pk,
            )
            raise

    def is_owner(self, user):
        """
        Check if the user is the owner of this record.

        Override in subclasses for model-specific ownership
        logic.

        Args:
            user: The user to check.

        Returns:
            bool: ``False`` by default.
        """
        return False
