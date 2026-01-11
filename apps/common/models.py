from django.db import models
from django.utils import timezone
from django.core.exceptions import PermissionDenied
import uuid6
import logging

logger = logging.getLogger('application')

class TimeStampedModel(models.Model):
    """
    Abstract base class that provides self-updating
    'created_at' and 'updated_at' fields.
    
    This ensures all models have automatic timestamping for audit trails.
    """
    id = models.UUIDField(primary_key=True, default=uuid6.uuid7, editable=False)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True, help_text="Timestamp when the record was created.")
    updated_at = models.DateTimeField(auto_now=True, help_text="Timestamp when the record was last updated.")

    class Meta:
        abstract = True

class SoftDeleteModel(models.Model):
    """
    Abstract base class that prevents physical deletion of records.
    Instead, it marks them as deleted for Audit/Recovery purposes.
    
    Soft-deleted records are stored in a separate 'DeletedRecords' model for retrieval without breaking layers.
    """
    is_deleted = models.BooleanField(default=False, db_index=True, help_text="Flag indicating if the record is soft-deleted.")
    deleted_at = models.DateTimeField(null=True, blank=True, help_text="Timestamp of soft deletion.")

    class Meta:
        abstract = True

    def soft_delete(self):
        """
        Marks the record as deleted and timestamps it.
        Also saves to DeletedRecords for recovery.
        """
        try:
            from apps.common.models import DeletedRecords  # Lazy import to avoid circular
            # Save a copy to DeletedRecords
            DeletedRecords.objects.create(
                model_name=self.__class__.__name__,
                record_id=self.pk,
                data=self.__dict__  # Serialize for recovery
            )
            self.is_deleted = True
            self.deleted_at = timezone.now()
            self.save()
            logger.info(f"Soft-deleted {self.__class__.__name__} with ID {self.pk}")
        except Exception as e:
            logger.error(f"Error during soft delete: {str(e)}")
            raise Exception("Failed to soft delete record.")

    def restore(self):
        """
        Restores a soft-deleted record.
        """
        try:
            self.is_deleted = False
            self.deleted_at = None
            self.save()
            logger.info(f"Restored {self.__class__.__name__} with ID {self.pk}")
        except Exception as e:
            logger.error(f"Error during restore: {str(e)}")
            raise Exception("Failed to restore record.")

class DeletedRecords(models.Model):
    """
    Model to store soft-deleted records for recovery.
    This allows retrieval without querying the main table.
    """
    model_name = models.CharField(max_length=100, help_text="Name of the model that was deleted.")
    record_id = models.CharField(max_length=255, help_text="Primary key of the deleted record (UUID or Int).")
    data = models.JSONField(help_text="Serialized data of the deleted record.")
    deleted_at = models.DateTimeField(auto_now_add=True, help_text="Timestamp of deletion.")

    class Meta:
        indexes = [models.Index(fields=['model_name', 'record_id'])]

class HardDeleteMixin:
    """
    Mixin for hard delete functionality, protected for admins/vendors/owners.
    Handles Cloudinary media deletion properly.
    """

    def hard_delete(self, user):
        """
        PERMANENTLY deletes the record from the database.
        Protected: Only admins, vendors (for their own records), or owners can perform.
        
        Args:
            user: The user performing the deletion.
            
        Raises:
            PermissionDenied: If user lacks permission.
        """
        try:
            # Check permissions
            if not (user.is_superuser or user.role in ['admin', 'vendor'] or self.is_owner(user)):
                raise PermissionDenied("You do not have permission to perform hard delete.")
            
            # Handle media deletion (Cloudinary)
            if hasattr(self, 'avatar') and self.avatar:
                from apps.common.utils import delete_cloudinary_asset
                delete_cloudinary_asset(self.avatar.name)  # Async task for Cloudinary
            
            # Log before deletion
            logger.info(f"Hard-deleting {self.__class__.__name__} with ID {self.pk} by user {user.email}")
            
            # Perform hard delete
            super().delete()
            
        except Exception as e:
            logger.error(f"Error during hard delete: {str(e)}")
            raise Exception("Failed to hard delete record.")

    def is_owner(self, user):
        """
        Check if the user is the owner of this record.
        Override in subclasses.
        """
        return False  # Default implementation
