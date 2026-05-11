# pyrefly: ignore [missing-import]
from cloudinary.models import CloudinaryField

# pyrefly: ignore [missing-import]
from django.conf import settings

# pyrefly: ignore [missing-import]
from django.db import models
from django.utils import timezone
from django.utils.html import mark_safe

# pyrefly: ignore [missing-import]
from django.utils.text import slugify

from apps.common.models import SoftDeleteModel, TimeStampedModel


class Brand(SoftDeleteModel, TimeStampedModel):
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
    image = CloudinaryField(
        "image",
        folder="fashionistar/catalog/brands/",
        blank=True,
        null=True,
        help_text=(
            "Cloudinary image public_id. "
            "Set via the /api/v1/upload/presign/ → direct upload → webhook flow. "
            "Use .url in serializers to retrieve the full HTTPS secure_url."
        ),
    )
    active = models.BooleanField(default=True, db_index=True)
    slug = models.SlugField(unique=True, blank=True, null=True, db_index=True)

    class Meta:
        managed = True
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
            import shortuuid

            uniqueid = shortuuid.uuid()[:4].lower()
            self.slug = f"{slugify(self.title)}-{uniqueid}"
        super().save(*args, **kwargs)
