import os
from cloudinary.models import CloudinaryField
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
        raise ValidationError(
            "Unsupported file extension. Only PNG, JPG, and JPEG are allowed."
        )

    if field_name == "image":
        file_size = value.size
        limit_mb = 5
        max_size = limit_mb * 1024 * 1024
        if file_size > max_size:
            raise ValidationError(f"Maximum file size for image is {limit_mb} MB")


def validate_image_cover_extension(value):
    return validate_file_extension(value, "image")


class Collection(models.Model):
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

    # --- Cloudinary-powered images ---
    image = CloudinaryField(
        "image",
        folder="fashionistar/catalog/collections/",
        blank=True,
        null=True,
        help_text="Main collection image (public_id).",
    )
    background_image = CloudinaryField(
        "background_image",
        folder="fashionistar/catalog/collections/backgrounds/",
        blank=True,
        null=True,
        help_text="Hero background image (public_id).",
    )

    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        managed = True
        db_table = "catalog_collections"
        verbose_name = "Catalog Collection"
        verbose_name_plural = "Catalog Collections"

    def __str__(self):
        return self.title or ""

    def collection_vendor_count(self):
        from apps.vendor.models import VendorProfile

        try:
            return VendorProfile.objects.filter(collection=self).count()
        except Exception:
            return 0

    def collection_vendors(self):
        from apps.vendor.models import VendorProfile

        try:
            return VendorProfile.objects.filter(collection=self)
        except Exception:
            return []

    def save(self, *args, **kwargs):
        if not self.slug and self.title:
            import shortuuid

            uniqueid = shortuuid.uuid()[:4].lower()
            self.slug = f"{slugify(self.title)}-{uniqueid}"
        super().save(*args, **kwargs)


# Backward-compatible alias used by legacy imports and package exports.
Collections = Collection
