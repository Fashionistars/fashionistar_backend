import uuid
from cloudinary.models import CloudinaryField
from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.html import mark_safe
from django.utils.text import slugify
from apps.common.models import TimeStampedModel, SoftDeleteModel


class Category(TimeStampedModel, SoftDeleteModel):
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
    name = models.CharField(max_length=100, unique=True, db_index=True)
    image = CloudinaryField(
        "image",
        folder="fashionistar/catalog/categories/",
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
            return self.category_products.count()
        except Exception:
            return 0

    def cat_products(self):
        try:
            return self.category_products.all()
        except Exception:
            return []

    def save(self, *args, **kwargs):
        # pyrefly: ignore [missing-import]
        import shortuuid

        if not self.slug and self.name:
            uniqueid = shortuuid.uuid()[:4].lower()
            self.slug = f"{slugify(self.name)}-{uniqueid}"
        super().save(*args, **kwargs)
