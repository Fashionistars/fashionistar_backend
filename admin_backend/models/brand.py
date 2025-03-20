from django.db import models
from django.utils.html import mark_safe
from django.conf import settings
from django.utils import timezone
from django.utils.text import slugify

class Brand(models.Model):
    """
    Represents a brand.
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









        