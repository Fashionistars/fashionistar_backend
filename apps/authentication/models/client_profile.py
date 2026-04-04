# apps/authentication/models/client_profile.py
"""
ClientProfile — 1:1 Profile for role='client' users.

Mirrors the VendorProfile design pattern. Stores shopping preferences,
shipping address, style preferences, and spend tracking.

Import: from apps.authentication.models import ClientProfile
"""
from apps.common.models import TimeStampedModel
from django.db import models


class ClientProfile(TimeStampedModel):
    """
    Extended profile for client-role users.

    Linked 1:1 to UnifiedUser (role='client').
    Stores shopping preferences, shipping defaults, and style data.

    Access:
        user.client_profile  — reverse OneToOne relation
        ClientProfile.objects.get(user=user) — direct lookup
    """

    # ── Identity link ─────────────────────────────────────────────
    user = models.OneToOneField(
        "authentication.UnifiedUser",
        on_delete=models.CASCADE,
        related_name="client_profile",
        limit_choices_to={"role": "client"},
        help_text="The client user this profile belongs to.",
    )

    # ── Personal Details ──────────────────────────────────────────
    bio = models.TextField(
        blank=True, default="", max_length=500,
        help_text="Short personal bio (max 500 chars).",
    )

    # ── Shipping / Location ───────────────────────────────────────
    default_shipping_address = models.TextField(
        blank=True, default="",
        help_text="Default shipping address for checkout.",
    )
    state   = models.CharField(max_length=100, blank=True, default="")
    country = models.CharField(max_length=100, blank=True, default="Nigeria")

    # ── Style & Size Preferences ───────────────────────────────────
    SIZE_CHOICES = [
        ("XS", "XS"), ("S", "S"), ("M", "M"),
        ("L", "L"), ("XL", "XL"), ("XXL", "XXL"), ("XXXL", "XXXL"),
    ]
    preferred_size = models.CharField(
        max_length=10, choices=SIZE_CHOICES, blank=True, default="",
        help_text="Preferred clothing size.",
    )
    style_preferences = models.JSONField(
        default=list, blank=True,
        help_text='Style tags: ["casual", "afrocentric", "formal"]. Used by AI engine.',
    )
    favourite_colours = models.JSONField(
        default=list, blank=True,
        help_text="Favourite colour hex codes or names.",
    )

    # ── Shopping Behaviour ─────────────────────────────────────────
    total_orders    = models.PositiveIntegerField(default=0)
    total_spent_ngn = models.DecimalField(max_digits=14, decimal_places=2, default=0)

    # ── Profile Completeness ───────────────────────────────────────
    is_profile_complete = models.BooleanField(
        default=False,
        help_text="True once size, address, and style preferences are filled in.",
    )

    class Meta:
        verbose_name        = "Client Profile"
        verbose_name_plural = "Client Profiles"
        db_table            = "authentication_client_profile"
        indexes = [
            models.Index(fields=["user"], name="client_profile_user_idx"),
        ]

    def __str__(self) -> str:
        identifier = self.user.email or self.user.phone or str(self.user.pk)
        return f"ClientProfile({identifier})"

    def update_completeness(self) -> None:
        """Recalculates is_profile_complete and saves if changed."""
        complete = all([
            self.preferred_size,
            self.default_shipping_address,
            bool(self.style_preferences),
        ])
        if self.is_profile_complete != complete:
            self.is_profile_complete = complete
            self.save(update_fields=["is_profile_complete", "updated_at"])

    @classmethod
    def get_or_create_for_user(cls, user) -> "ClientProfile":
        """
        Idempotent — returns existing profile or creates a blank one.
        Used in LoginView to populate has_client_profile in the JWT response.
        """
        profile, _ = cls.objects.get_or_create(user=user)
        return profile
