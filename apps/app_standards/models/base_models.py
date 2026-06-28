"""
مدل‌های پایه استاندارد
Standard Base Models
"""

from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.core.validators import MinValueValidator, MaxValueValidator
import uuid

User = get_user_model()


class BaseModel(models.Model):
    """
    مدل پایه برای تمام مدل‌های سیستم
    شامل فیلدهای استاندارد timestamp و creator
    """
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        verbose_name='شناسه یکتا'
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='تاریخ ایجاد'
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name='تاریخ آخرین تغییر'
    )
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='%(class)s_created',
        verbose_name='ایجادکننده'
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name='فعال'
    )
    
    class Meta:
        abstract = True
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['created_at']),
            models.Index(fields=['is_active']),
        ]
    
    def soft_delete(self):
        """حذف نرم (غیرفعال‌سازی)"""
        self.is_active = False
        self.save(update_fields=['is_active', 'updated_at'])
    
    def restore(self):
        """بازیابی رکورد حذف شده"""
        self.is_active = True
        self.save(update_fields=['is_active', 'updated_at'])


class PatientRelatedModel(BaseModel):
    """
    مدل پایه برای موجودیت‌های مرتبط با بیمار
    """
    patient = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='%(class)s_records',
        limit_choices_to={'user_type': 'patient'},
        verbose_name='بیمار'
    )
    
    class Meta:
        abstract = True
        indexes = [
            models.Index(fields=['patient', '-created_at']),
        ]


class DoctorRelatedModel(BaseModel):
    """
    مدل پایه برای موجودیت‌های مرتبط با پزشک
    """
    doctor = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='%(class)s_records',
        limit_choices_to={'user_type': 'doctor'},
        verbose_name='پزشک'
    )
    
    class Meta:
        abstract = True
        indexes = [
            models.Index(fields=['doctor', '-created_at']),
        ]


class MedicalRecordModel(BaseModel):
    """
    مدل پایه برای سوابق پزشکی
    """
    patient = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='%(class)s_medical_records',
        limit_choices_to={'user_type': 'patient'},
        verbose_name='بیمار'
    )
    doctor = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='%(class)s_created_records',
        limit_choices_to={'user_type': 'doctor'},
        verbose_name='پزشک'
    )
    is_confidential = models.BooleanField(
        default=False,
        verbose_name='محرمانه'
    )
    
    class Meta:
        abstract = True
        permissions = [
            ('view_confidential', 'Can view confidential records'),
        ]


class FileAttachmentModel(BaseModel):
    """
    مدل پایه برای فایل‌های پیوست
    """
    file = models.FileField(
        upload_to='attachments/%Y/%m/%d/',
        verbose_name='فایل'
    )
    file_name = models.CharField(
        max_length=255,
        verbose_name='نام فایل'
    )
    file_size = models.IntegerField(
        validators=[MinValueValidator(0)],
        verbose_name='حجم فایل (بایت)'
    )
    file_type = models.CharField(
        max_length=50,
        verbose_name='نوع فایل'
    )
    description = models.TextField(
        blank=True,
        verbose_name='توضیحات'
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
    مدل پایه برای موجودیت‌های دارای وضعیت
    """
    STATUS_CHOICES = []  # باید در کلاس فرزند تعریف شود
    
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending',
        verbose_name='وضعیت'
    )
    status_changed_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='زمان تغییر وضعیت'
    )
    status_changed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='%(class)s_status_changes',
        verbose_name='تغییردهنده وضعیت'
    )
    
    class Meta:
        abstract = True
        indexes = [
            models.Index(fields=['status', '-created_at']),
        ]
    
    def change_status(self, new_status, user=None):
        """تغییر وضعیت با ثبت تاریخ و کاربر"""
        self.status = new_status
        self.status_changed_at = timezone.now()
        self.status_changed_by = user
        self.save(update_fields=['status', 'status_changed_at', 'status_changed_by', 'updated_at'])


class RatingModel(models.Model):
    """
    مدل پایه برای امتیازدهی
    """
    rating = models.IntegerField(
        validators=[
            MinValueValidator(1),
            MaxValueValidator(5)
        ],
        verbose_name='امتیاز'
    )
    comment = models.TextField(
        blank=True,
        verbose_name='نظر'
    )
    rated_by = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='%(class)s_ratings',
        verbose_name='امتیازدهنده'
    )
    rated_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='تاریخ امتیازدهی'
    )
    
    class Meta:
        abstract = True
        indexes = [
            models.Index(fields=['rating']),
            models.Index(fields=['rated_at']),
        ]


class VersionedModel(BaseModel):
    """
    مدل پایه برای موجودیت‌های دارای نسخه
    """
    version = models.IntegerField(
        default=1,
        verbose_name='نسخه'
    )
    is_current = models.BooleanField(
        default=True,
        verbose_name='نسخه فعلی'
    )
    parent_version = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='child_versions',
        verbose_name='نسخه والد'
    )
    
    class Meta:
        abstract = True
        indexes = [
            models.Index(fields=['is_current', '-version']),
        ]
    
    def create_new_version(self):
        """ایجاد نسخه جدید"""
        # غیرفعال کردن نسخه فعلی
        self.is_current = False
        self.save(update_fields=['is_current'])
        
        # ایجاد نسخه جدید
        new_version = self.__class__.objects.create(
            parent_version=self,
            version=self.version + 1,
            is_current=True,
            # کپی سایر فیلدها
            **{f.name: getattr(self, f.name) 
               for f in self._meta.fields 
               if f.name not in ['id', 'version', 'is_current', 'parent_version', 'created_at', 'updated_at']}
        )
        return new_version


class AuditLogModel(models.Model):
    """
    مدل پایه برای ثبت تغییرات (Audit Log)
    """
    ACTION_CHOICES = [
        ('create', 'ایجاد'),
        ('update', 'بروزرسانی'),
        ('delete', 'حذف'),
        ('view', 'مشاهده'),
    ]
    
    user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        verbose_name='کاربر'
    )
    action = models.CharField(
        max_length=10,
        choices=ACTION_CHOICES,
        verbose_name='عملیات'
    )
    timestamp = models.DateTimeField(
        auto_now_add=True,
        verbose_name='زمان'
    )
    object_id = models.CharField(
        max_length=255,
        verbose_name='شناسه موجودیت'
    )
    object_type = models.CharField(
        max_length=100,
        verbose_name='نوع موجودیت'
    )
    changes = models.JSONField(
        default=dict,
        verbose_name='تغییرات'
    )
    ip_address = models.GenericIPAddressField(
        null=True,
        blank=True,
        verbose_name='آدرس IP'
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


# مثال استفاده
class ExampleModel(BaseModel):
    """نمونه استفاده از مدل پایه"""
    title = models.CharField(max_length=200)
    description = models.TextField()
    
    class Meta:
        verbose_name = 'نمونه'
        verbose_name_plural = 'نمونه‌ها'