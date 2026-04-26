import os

import shortuuid
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from django.utils.text import slugify


def validate_file_extension(value, field_name):
    ext = os.path.splitext(value.name)[1]
    valid_extensions = {
        "image": [".png", ".jpg", ".jpeg"],
    }
    allowed_extensions = valid_extensions[field_name]
    if ext.lower() not in [extension.lower() for extension in allowed_extensions]:
        raise ValidationError("Unsupported file extension. Only PNG, JPG, and JPEG are allowed.")

    if field_name == "image":
        file_size = value.size
        limit_mb = 5
        max_size = limit_mb * 1024 * 1024
        if file_size > max_size:
            raise ValidationError(f"Maximum file size for image is {limit_mb} MB")


def validate_image_cover_extension(value):
    return validate_file_extension(value, "image")


class Collections(models.Model):
    """Admin-managed merchandising collection for curated catalog discovery."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="catalog_collections",
        db_index=True,
        help_text="Staff user who last created or curated this collection.",
    )
    title = models.CharField(max_length=255, blank=True, null=True)
    sub_title = models.CharField(max_length=255, null=True, blank=True)
    description = models.TextField(null=True, blank=True)
    slug = models.SlugField(unique=True, blank=True, null=True, db_index=True)
    background_image = models.ImageField(
        upload_to="gallery/bg_img/",
        validators=[validate_image_cover_extension],
        null=True,
        blank=True,
    )
    image = models.ImageField(
        upload_to="gallery/product_img/",
        validators=[validate_image_cover_extension],
        null=True,
        blank=True,
    )
    cloudinary_url = models.URLField(
        max_length=800,
        blank=True,
        null=True,
        help_text="Main collection image populated by the media pipeline.",
    )
    background_cloudinary_url = models.URLField(
        max_length=800,
        blank=True,
        null=True,
        help_text="Collection background image populated by the media pipeline.",
    )
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "admin_backend_collections"
        managed = False
        verbose_name = "Catalog Collection"
        verbose_name_plural = "Catalog Collections"

    def __str__(self):
        return self.title or ""

    def collection_product_count(self):
        try:
            from apps.product.models import Product
        except Exception:
            from store.models import Product
        return Product.objects.filter(collection=self).count()

    def collection_products(self):
        try:
            from apps.product.models import Product
        except Exception:
            from store.models import Product
        return Product.objects.filter(collection=self)

    def save(self, *args, **kwargs):
        if not self.slug and self.title:
            uniqueid = shortuuid.uuid()[:4].lower()
            self.slug = f"{slugify(self.title)}-{uniqueid}"
        super().save(*args, **kwargs)


Collection = Collections
