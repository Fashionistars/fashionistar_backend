from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils.text import slugify

import os
import shortuuid
from django.utils import timezone

def validate_file_extension(value, field_name):
    ext = os.path.splitext(value.name)[1]
    valid_extensions = {
        'image': ['.png', '.jpg', '.jpeg'],
    }
    allowed_extensions = valid_extensions[field_name]
    if ext.lower() not in [extension.lower() for extension in allowed_extensions]:
        error_msg = {
            'image': 'Unsupported file extension. Only PNG, JPG, and JPEG are allowed.',
        }
        raise ValidationError(error_msg[field_name])

    if field_name == 'image':
        file_size = value.size
        limit_mb = 5
        max_size = limit_mb * 1024 * 1024
        if file_size > max_size:
            raise ValidationError(f'Maximum file size for image is {limit_mb} MB')


def validate_image_cover_extension(value):
    return validate_file_extension(value, 'image')

class Collections(models.Model):
    """
    Represents a collection of products.
    """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='collections',
        db_index=True
    )
    title = models.CharField(max_length=255, blank=True, null=True)
    sub_title = models.CharField(max_length=255, null=True, blank=True)
    description = models.TextField(null=True, blank=True)
    slug = models.SlugField(unique=True, blank=True, null=True, db_index=True)
    background_image = models.ImageField(
        upload_to='gallery/bg_img/',
        validators=[validate_image_cover_extension]
    )
    image = models.ImageField(
        upload_to='gallery/product_img/',
        validators=[validate_image_cover_extension]
    )
    # created_at = models.DateTimeField(auto_now_add=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "Collections"

    def __str__(self):
        return self.title

    def collection_product_count(self):
        from store.models import Product
        return Product.objects.filter(collection=self).count()

    def collection_products(self):
        from store.models import Product
        return Product.objects.filter(collection=self)

    def save(self, *args, **kwargs):
        if not self.slug:
            uuid_key = shortuuid.uuid()
            uniqueid = uuid_key[:4]
            self.slug = slugify(self.title) + "-" + uniqueid.lower()
        super(Collections, self).save(*args, **kwargs)