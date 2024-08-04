from django.db import models
from django.utils.html import mark_safe
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils.text import slugify

import os
import shortuuid

def validate_file_extension(value, field_name):
    ext = os.path.splitext(value.name)[1]
    valid_extensions = {
        'image': ['.png', '.jpg', '.jpeg'],
    }
    allowed_extensions = valid_extensions[field_name]
    if not ext.lower() in [extension.lower() for extension in allowed_extensions]:
        error_msg = {
            'image': 'Unsupported file extension for image. Only PNG, JPG, and JPEG are allowed.',
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
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='collections', db_index=True)
    title = models.CharField(max_length=255)
    sub_title = models.CharField(max_length=255, null=True, blank=True)
    description = models.TextField(null=True, blank=True)
    slug = models.SlugField(null=True, blank=True, unique=True, db_index=True)
    background_image = models.ImageField(
        upload_to='Gallery/bg_img/',
        validators=[validate_image_cover_extension]
    )
    image = models.ImageField(
        upload_to='Gallery/product_img/',
        validators=[validate_image_cover_extension]
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

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

class Category(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='categories', db_index=True)
    title = models.CharField(max_length=100)
    image = models.ImageField(upload_to='category_images/', default="category.jpg", null=True, blank=True)
    active = models.BooleanField(default=True)
    slug = models.SlugField(null=True, blank=True, unique=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "Categories"

    def thumbnail(self):
        if self.image:
            return mark_safe(f'<img src="{self.image.url}" width="50" height="50" style="object-fit:cover; border-radius: 6px;" />')
        return "No Image"

    def __str__(self):
        return self.title

    def product_count(self):
        from store.models import Product
        return Product.objects.filter(category=self).count()

    def cat_products(self):
        from store.models import Product
        return Product.objects.filter(category=self)

    def save(self, *args, **kwargs):
        if not self.slug:
            uuid_key = shortuuid.uuid()
            uniqueid = uuid_key[:4]
            self.slug = slugify(self.title) + "-" + uniqueid.lower()
        super(Category, self).save(*args, **kwargs)

class Brand(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='brands', db_index=True)
    title = models.CharField(max_length=100)
    description = models.TextField(null=True, blank=True)
    image = models.ImageField(upload_to='brand_images/', default="brand.jpg", null=True, blank=True)
    active = models.BooleanField(default=True)
    slug = models.SlugField(null=True, blank=True, unique=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "Brands"

    def brand_image(self):
        if self.image:
            return mark_safe(f'<img src="{self.image.url}" width="50" height="50" style="object-fit:cover; border-radius: 6px;" />')
        return "No Image"

    def __str__(self):
        return self.title
