import uuid

import shortuuid
from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.html import mark_safe
from django.utils.text import slugify


class Category(models.Model):
    """Admin-managed public product category metadata owned by catalog."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="catalog_categories",
        db_index=True,
        help_text="Staff user who last created or curated this category.",
    )
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100, unique=True, db_index=True)
    image = models.ImageField(
        upload_to="category_images/",
        default="category.jpg",
        null=True,
        blank=True,
    )
    cloudinary_url = models.URLField(
        max_length=800,
        blank=True,
        null=True,
        help_text="Canonical Cloudinary URL populated by the media pipeline.",
    )
    active = models.BooleanField(default=True, db_index=True)
    slug = models.SlugField(unique=True, blank=True, null=True, db_index=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "admin_backend_category"
        managed = False
        verbose_name = "Catalog Category"
        verbose_name_plural = "Catalog Categories"
        indexes = [
            models.Index(fields=["name"], name="category_name_idx"),
            models.Index(fields=["slug"], name="category_slug_idx"),
        ]

    def category_image(self):
        if not self.image:
            return "No Image"
        return mark_safe(
            f'<img src="{self.image.url}" width="50" height="50" '
            'style="object-fit:cover; border-radius: 6px;" />'
        )

    def __str__(self):
        return self.name or ""

    def product_count(self):
        try:
            from apps.product.models import Product
        except Exception:
            from store.models import Product
        return Product.objects.filter(category=self).count()

    def cat_products(self):
        try:
            from apps.product.models import Product
        except Exception:
            from store.models import Product
        return Product.objects.filter(category=self)

    def save(self, *args, **kwargs):
        if not self.slug and self.name:
            uniqueid = shortuuid.uuid()[:4].lower()
            self.slug = f"{slugify(self.name)}-{uniqueid}"
        super().save(*args, **kwargs)
