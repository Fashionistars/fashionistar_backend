from django.db import models
from django.utils.html import mark_safe
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils.text import slugify

import os
import shortuuid
from django.utils import timezone
import uuid

class Category(models.Model):
    """
    Represents a product category.
    """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='categories',
        db_index=True
    )
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100, unique=True, db_index=True)
    image = models.ImageField(upload_to='category_images/', default="category.jpg", null=True, blank=True)
    active = models.BooleanField(default=True)
    slug = models.SlugField(unique=True, blank=True, null=True, db_index=True)
    # created_at = models.DateTimeField(auto_now_add=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "Categories"
        indexes = [
            models.Index(fields=['name'], name='category_name_idx'),
            models.Index(fields=['slug'], name='category_slug_idx'),
        ]

    def category_image(self):
        """
        Returns an HTML image tag for the category image, used in Django Admin.
        """
        return mark_safe(f'<img src="{self.image.url}" width="50" height="50" style="object-fit:cover; border-radius: 6px;" />') if self.image else "No Image"

    def __str__(self):
        return self.name  or ""

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
            self.slug = slugify(self.name) + "-" + uniqueid.lower()
        super(Category, self).save(*args, **kwargs)