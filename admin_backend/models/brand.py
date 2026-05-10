from django.db import models
from django.utils.html import mark_safe
from django.conf import settings
from django.utils import timezone
from django.utils.text import slugify


class Brand(models.Model):
    """
    Represents a brand.

    Image strategy:
        - ``image``          — Legacy local ImageField (kept for backward compat).
        - ``cloudinary_url`` — Populated automatically by the Cloudinary webhook
                               after a presign+direct-upload flow. This is the
                               canonical production image URL.
    """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='brands',
        db_index=True
    )
    title = models.CharField(max_length=100)
    description = models.TextField(null=True, blank=True)
    image = models.ImageField(upload_to='brand_images/', default="brand.jpg", null=True, blank=True)
    # ── Cloudinary URL (populated by webhook after presign direct-upload) ──────
    cloudinary_url = models.URLField(
        max_length=800,
        blank=True,
        null=True,
        help_text="Auto-populated by Cloudinary webhook after presign upload.",
    )
    active = models.BooleanField(default=True)
    slug = models.SlugField(unique=True, blank=True, null=True, db_index=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "Brands"

    def brand_image(self):
        """
        Returns an HTML image tag for the brand's image, used in Django Admin.
        """
        return mark_safe(f'<img src="{self.image.url}" width="50" height="50" style="object-fit:cover; border-radius: 6px;" />') if self.image else "No Image"

    def __str__(self):
        return self.title









        