"""
Standard Base Models for Fashionistar.
"""

from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.core.validators import MinValueValidator, MaxValueValidator
import uuid

User = get_user_model()


class BaseModel(models.Model):
    """
    Base model for all system models.
    Includes standard UUID, timestamp, active status, and creator tracking.
    """
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        verbose_name='UUID'
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Created At'
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name='Updated At'
    )
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='%(class)s_created',
        verbose_name='Created By'
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name='Is Active'
    )
    
    class Meta:
        abstract = True
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['created_at']),
            models.Index(fields=['is_active']),
        ]
    
    def soft_delete(self):
        """Soft delete (deactivation)."""
        self.is_active = False
        self.save(update_fields=['is_active', 'updated_at'])
    
    def restore(self):
        """Restore deleted record."""
        self.is_active = True
        self.save(update_fields=['is_active', 'updated_at'])


class ClientRelatedModel(BaseModel):
    """
    Base model for client-related entities.
    """
    client = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='%(class)s_records',
        limit_choices_to={'role': 'client'},
        verbose_name='Client'
    )
    
    class Meta:
        abstract = True
        indexes = [
            models.Index(fields=['client', '-created_at']),
        ]


class VendorRelatedModel(BaseModel):
    """
    Base model for vendor-related entities.
    """
    vendor = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='%(class)s_records',
        limit_choices_to={'role': 'vendor'},
        verbose_name='Vendor'
    )
    
    class Meta:
        abstract = True
        indexes = [
            models.Index(fields=['vendor', '-created_at']),
        ]


class CommerceRecordModel(BaseModel):
    """
    Base model for commerce records involving clients and vendors.
    """
    client = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='%(class)s_commerce_records',
        limit_choices_to={'role': 'client'},
        verbose_name='Client'
    )
    vendor = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='%(class)s_created_commerce_records',
        limit_choices_to={'role': 'vendor'},
        verbose_name='Vendor'
    )
    is_confidential = models.BooleanField(
        default=False,
        verbose_name='Is Confidential'
    )
    
    class Meta:
        abstract = True
        permissions = [
            ('view_confidential', 'Can view confidential records'),
        ]


class FileAttachmentModel(BaseModel):
    """
    Base model for file attachments.
    """
    file = models.FileField(
        upload_to='attachments/%Y/%m/%d/',
        verbose_name='File'
    )
    file_name = models.CharField(
        max_length=255,
        verbose_name='File Name'
    )
    file_size = models.IntegerField(
        validators=[MinValueValidator(0)],
        verbose_name='File Size (Bytes)'
    )
    file_type = models.CharField(
        max_length=50,
        verbose_name='File Type'
    )
    description = models.TextField(
        blank=True,
        verbose_name='Description'
    )
    
    class Meta:
        abstract = True
    
    def save(self, *args, **kwargs):
        if self.file:
            self.file_name = self.file.name
            self.file_size = self.file.size
        super().save(*args, **kwargs)


class StatusModel(BaseModel):
    """
    Base model for entities with status lifecycle tracking.
    """
    STATUS_CHOICES = []  # Must be defined in child class
    
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending',
        verbose_name='Status'
    )
    status_changed_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='Status Changed At'
    )
    status_changed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='%(class)s_status_changes',
        verbose_name='Status Changed By'
    )
    
    class Meta:
        abstract = True
        indexes = [
            models.Index(fields=['status', '-created_at']),
        ]
    
    def change_status(self, new_status, user=None):
        """Change status, recording timestamp and user."""
        self.status = new_status
        self.status_changed_at = timezone.now()
        self.status_changed_by = user
        self.save(update_fields=['status', 'status_changed_at', 'status_changed_by', 'updated_at'])


class RatingModel(models.Model):
    """
    Base model for ratings and reviews.
    """
    rating = models.IntegerField(
        validators=[
            MinValueValidator(1),
            MaxValueValidator(5)
        ],
        verbose_name='Rating'
    )
    comment = models.TextField(
        blank=True,
        verbose_name='Comment'
    )
    rated_by = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='%(class)s_ratings',
        verbose_name='Rated By'
    )
    rated_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Rated At'
    )
    
    class Meta:
        abstract = True
        indexes = [
            models.Index(fields=['rating']),
            models.Index(fields=['rated_at']),
        ]


class VersionedModel(BaseModel):
    """
    Base model for versioned entities.
    """
    version = models.IntegerField(
        default=1,
        verbose_name='Version'
    )
    is_current = models.BooleanField(
        default=True,
        verbose_name='Is Current Version'
    )
    parent_version = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='child_versions',
        verbose_name='Parent Version'
    )
    
    class Meta:
        abstract = True
        indexes = [
            models.Index(fields=['is_current', '-version']),
        ]
    
    def create_new_version(self):
        """Create new version."""
        # Deactivate current version
        self.is_current = False
        self.save(update_fields=['is_current'])
        
        # Create new version
        new_version = self.__class__.objects.create(
            parent_version=self,
            version=self.version + 1,
            is_current=True,
            # Copy other fields
            **{f.name: getattr(self, f.name) 
               for f in self._meta.fields 
               if f.name not in ['id', 'version', 'is_current', 'parent_version', 'created_at', 'updated_at']}
        )
        return new_version


class AuditLogModel(models.Model):
    """
    Base model for audit logs.
    """
    ACTION_CHOICES = [
        ('create', 'Create'),
        ('update', 'Update'),
        ('delete', 'Delete'),
        ('view', 'View'),
    ]
    
    user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        verbose_name='User'
    )
    action = models.CharField(
        max_length=10,
        choices=ACTION_CHOICES,
        verbose_name='Action'
    )
    timestamp = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Timestamp'
    )
    object_id = models.CharField(
        max_length=255,
        verbose_name='Object ID'
    )
    object_type = models.CharField(
        max_length=100,
        verbose_name='Object Type'
    )
    changes = models.JSONField(
        default=dict,
        verbose_name='Changes'
    )
    ip_address = models.GenericIPAddressField(
        null=True,
        blank=True,
        verbose_name='IP Address'
    )
    user_agent = models.TextField(
        blank=True,
        verbose_name='User Agent'
    )
    
    class Meta:
        abstract = True
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['user', '-timestamp']),
            models.Index(fields=['object_type', 'object_id']),
            models.Index(fields=['action', '-timestamp']),
        ]


class ExampleModel(BaseModel):
    """Example of standard base model usage."""
    title = models.CharField(max_length=200)
    description = models.TextField()
    
    class Meta:
        verbose_name = 'Example'
        verbose_name_plural = 'Examples'