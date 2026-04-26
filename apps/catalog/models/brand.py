import shortuuid
from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.html import mark_safe
from django.utils.text import slugify


class Brand(models.Model):
    """Admin-managed brand metadata used by public catalog discovery."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="catalog_brands",
        db_index=True,
        help_text="Staff user who last created or curated this brand.",
    )
    title = models.CharField(max_length=100)
    description = models.TextField(null=True, blank=True)
    image = models.ImageField(
        upload_to="brand_images/",
        default="brand.jpg",
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
        db_table = "admin_backend_brand"
        managed = False
        verbose_name = "Catalog Brand"
        verbose_name_plural = "Catalog Brands"

    def brand_image(self):
        if not self.image:
            return "No Image"
        return mark_safe(
            f'<img src="{self.image.url}" width="50" height="50" '
            'style="object-fit:cover; border-radius: 6px;" />'
        )

    def __str__(self):
        return self.title or ""

    def save(self, *args, **kwargs):
        if not self.slug and self.title:
            uniqueid = shortuuid.uuid()[:4].lower()
            self.slug = f"{slugify(self.title)}-{uniqueid}"
        super().save(*args, **kwargs)
