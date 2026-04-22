# apps/vendor/models/vendor_profile.py
"""
VendorProfile — 1:1 Profile for role='vendor' users.

The canonical source of truth for a vendor's public-facing identity:
store name, tagline, description, logo, cover image, social links,
and location.

All Cloudinary media uses the apps.common.cloudinary utilities.
"""
import logging

from django.db import models

from apps.common.models import TimeStampedModel, SoftDeleteModel

logger = logging.getLogger(__name__)


class VendorProfile(TimeStampedModel, SoftDeleteModel):
    """
    Extended profile for vendor-role users.

    Linked 1:1 to UnifiedUser (role='vendor').

    Access:
        user.vendor_profile   — reverse OneToOne relation
        VendorProfile.objects.get(user=user) — direct lookup
    """

    # ── Identity Link ──────────────────────────────────────────────
    user = models.OneToOneField(
        "authentication.UnifiedUser",
        on_delete=models.CASCADE,
        related_name="vendor_profile",
        limit_choices_to={"role": "vendor"},
        help_text="The vendor user this profile belongs to.",
    )

    # ── Store Identity ─────────────────────────────────────────────
    store_name = models.CharField(
        max_length=150,
        blank=True,
        default="",
        help_text="Public-facing store name shown on the marketplace.",
    )
    store_slug = models.SlugField(
        max_length=160,
        unique=True,
        blank=True,
        db_index=True,
        help_text="URL-safe unique store identifier. Auto-generated if blank.",
    )
    tagline = models.CharField(
        max_length=200,
        blank=True,
        default="",
        help_text="Short store tagline shown below store name.",
    )
    description = models.TextField(
        max_length=2000,
        blank=True,
        default="",
        help_text="Full store description (markdown-safe).",
    )

    # ── Media (Cloudinary URLs stored as text) ────────────────────
    logo_url = models.URLField(
        blank=True,
        default="",
        help_text="Cloudinary URL of the store logo.",
    )
    cover_url = models.URLField(
        blank=True,
        default="",
        help_text="Cloudinary URL of the store banner / cover image.",
    )

    # ── Location ───────────────────────────────────────────────────
    city    = models.CharField(max_length=100, blank=True, default="")
    state   = models.CharField(max_length=100, blank=True, default="")
    country = models.CharField(max_length=100, blank=True, default="Nigeria")

    # ── Social Links ───────────────────────────────────────────────
    instagram_url = models.URLField(blank=True, default="")
    tiktok_url    = models.URLField(blank=True, default="")
    twitter_url   = models.URLField(blank=True, default="")
    website_url   = models.URLField(blank=True, default="")

    # ── Analytics ─────────────────────────────────────────────────
    total_products = models.PositiveIntegerField(default=0)
    total_sales    = models.PositiveIntegerField(default=0)
    total_revenue  = models.DecimalField(max_digits=16, decimal_places=2, default=0)
    average_rating = models.DecimalField(max_digits=3, decimal_places=2, default=0)
    review_count   = models.PositiveIntegerField(default=0)

    # ── Verification & Visibility ──────────────────────────────────
    is_verified    = models.BooleanField(
        default=False,
        help_text="Vendor has been manually verified by Fashionistar staff.",
    )
    is_active      = models.BooleanField(
        default=True,
        help_text="Vendor store is publicly visible on the marketplace.",
    )
    is_featured    = models.BooleanField(
        default=False,
        help_text="Pin this store to the homepage featured section.",
    )

    class Meta:
        verbose_name        = "Vendor Profile"
        verbose_name_plural = "Vendor Profiles"
        db_table            = "vendor_profile"
        indexes = [
            models.Index(fields=["user"],        name="vendor_profile_user_idx"),
            models.Index(fields=["store_slug"],   name="vendor_profile_slug_idx"),
            models.Index(fields=["is_verified"],  name="vendor_profile_verified_idx"),
            models.Index(fields=["country"],      name="vendor_profile_country_idx"),
        ]

    def __str__(self) -> str:
        return f"VendorProfile({self.store_name or self.user.pk})"

    # ── Slug generation ────────────────────────────────────────────

    def save(self, *args, **kwargs) -> None:
        if not self.store_slug and self.store_name:
            from django.utils.text import slugify
            base_slug = slugify(self.store_name)
            slug = base_slug
            n = 1
            while VendorProfile.objects.filter(store_slug=slug).exclude(pk=self.pk).exists():
                slug = f"{base_slug}-{n}"
                n += 1
            self.store_slug = slug
        super().save(*args, **kwargs)

    # ── Idempotent factory ─────────────────────────────────────────

    @classmethod
    def get_or_create_for_user(cls, user) -> "VendorProfile":
        """
        Idempotent — returns existing profile or creates a blank one.
        """
        profile, _ = cls.objects.get_or_create(user=user)
        return profile
