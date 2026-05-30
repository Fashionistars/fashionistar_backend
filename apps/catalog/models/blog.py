from cloudinary.models import CloudinaryField
from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.text import slugify

from apps.common.models import SoftDeleteModel, TimeStampedModel


class BlogPostStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    REVIEW = "review", "Review"
    PUBLISHED = "published", "Published"
    ARCHIVED = "archived", "Archived"


class BlogPost(TimeStampedModel, SoftDeleteModel):
    """Catalog-owned editorial content for SEO, styling education, and commerce discovery."""

    # ── Authorship ────────────────────────────────────────────────────────
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="catalog_blog_posts",
        help_text="Author is retained as nullable to preserve published history.",
    )
    category = models.ForeignKey(
        "catalog.Category",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="blog_posts",
        help_text="Optional catalog category used for discovery and SEO.",
    )

    # ── Content ───────────────────────────────────────────────────────────
    title = models.CharField(max_length=255, db_index=True)
    slug = models.SlugField(max_length=280, unique=True, db_index=True)
    excerpt = models.TextField(blank=True)
    content = models.TextField()

    # ── Cloudinary-powered images ─────────────────────────────────────────
    featured_image = CloudinaryField(
        "featured_image",
        folder="fashionistar/catalog/blog/featured/",
        blank=True,
        null=True,
        help_text="Featured post image (public_id).",
    )
    author_avatar = CloudinaryField(
        "author_avatar",
        folder="fashionistar/catalog/blog/authors/",
        blank=True,
        null=True,
        help_text="Author profile photo for post card display.",
    )
    og_image = CloudinaryField(
        "og_image",
        folder="fashionistar/catalog/blog/og/",
        blank=True,
        null=True,
        help_text="Open Graph image used for social sharing (1200×630 recommended).",
    )

    # ── Publishing metadata ───────────────────────────────────────────────
    status = models.CharField(
        max_length=20,
        choices=BlogPostStatus.choices,
        default=BlogPostStatus.DRAFT,
        db_index=True,
    )
    tags = models.JSONField(default=list, blank=True)
    seo_title = models.CharField(max_length=180, blank=True)
    seo_description = models.CharField(max_length=320, blank=True)
    canonical_url = models.URLField(blank=True, help_text="Canonical URL for SEO de-duplication.")
    is_featured = models.BooleanField(default=False, db_index=True)
    published_at = models.DateTimeField(null=True, blank=True, db_index=True)

    # ── Related posts ─────────────────────────────────────────────────────
    related_posts = models.ManyToManyField(
        "self",
        blank=True,
        symmetrical=True,
        help_text="Manually curated related blog posts (bi-directional).",
    )

    # ── Engagement counters ───────────────────────────────────────────────
    view_count = models.PositiveBigIntegerField(default=0)
    comment_count = models.PositiveIntegerField(
        default=0, help_text="Cached comment count. Updated by Celery task."
    )
    likes_count = models.PositiveIntegerField(
        default=0, help_text="Cached likes count. Updated by Celery task."
    )
    read_time_minutes = models.PositiveSmallIntegerField(
        default=0,
        help_text="Auto-calculated reading time (content word count ÷ 200 wpm).",
    )

    class Meta:
        verbose_name = "Catalog Blog Post"
        verbose_name_plural = "Catalog Blog Posts"
        indexes = [
            models.Index(fields=["status", "published_at"], name="catalog_blog_publish_idx"),
            models.Index(fields=["slug"], name="catalog_blog_slug_idx"),
            models.Index(fields=["is_featured", "published_at"], name="catalog_blog_featured_idx"),
        ]
        ordering = ("-published_at", "-created_at")

    def __str__(self):
        return self.title

    def _calculate_read_time(self) -> int:
        """Estimate reading time: total words ÷ 200 words per minute, min 1."""
        word_count = len(self.content.split()) if self.content else 0
        return max(1, round(word_count / 200))

    def save(self, *args, **kwargs):
        if not self.slug and self.title:
            base = slugify(self.title)[:240]
            timestamp = timezone.now().strftime("%Y%m%d%H%M%S")
            self.slug = f"{base}-{timestamp}"
        if self.status == BlogPostStatus.PUBLISHED and self.published_at is None:
            self.published_at = timezone.now()
        # Auto-calculate read time on every save
        self.read_time_minutes = self._calculate_read_time()
        super().save(*args, **kwargs)

    @property
    def featured_image_url(self):
        """Return the full Cloudinary secure_url."""
        if self.featured_image:
            return self.featured_image.url
        return ""

    @property
    def author_avatar_url(self):
        """Return the author avatar Cloudinary URL."""
        if self.author_avatar:
            return self.author_avatar.url
        return ""

    @property
    def og_image_url(self):
        """Return the Open Graph image Cloudinary URL."""
        if self.og_image:
            return self.og_image.url
        return ""


class BlogMedia(TimeStampedModel, SoftDeleteModel):
    """Gallery media attached to a catalog blog post."""

    post = models.ForeignKey(
        BlogPost,
        on_delete=models.CASCADE,
        related_name="gallery_media",
    )
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="catalog_blog_media_uploads",
    )

    # ── Cloudinary-powered media ──────────────────────────────────────────
    image = CloudinaryField(
        "image",
        folder="fashionistar/catalog/blog/gallery/",
        blank=True,
        null=True,
        help_text="Gallery image (public_id).",
    )

    alt_text = models.CharField(max_length=180, blank=True)
    sort_order = models.PositiveIntegerField(default=0, db_index=True)

    class Meta:
        verbose_name = "Catalog Blog Media"
        verbose_name_plural = "Catalog Blog Media"
        ordering = ("sort_order", "created_at")

    def __str__(self):
        return f"{self.post_id}:{self.sort_order}"

    @property
    def image_url(self):
        """Return the full Cloudinary secure_url."""
        if self.image:
            return self.image.url
        return ""
