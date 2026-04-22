# apps/client/models/client_profile.py
"""
ClientProfile — 1:1 Profile for role='client' users.

MIGRATION NOTE: Originally in apps.authentication.models.client_profile.
Moved here as part of Phase 2 domain-driven architecture migration.

The `db_table` is intentionally kept as 'authentication_client_profile'
to avoid a destructive DB rename migration (the schema is compatible).

On a fresh database, this table is simply created new.
"""
import logging

from django.db import models
from django.db.models import F

from apps.common.models import TimeStampedModel, SoftDeleteModel

logger = logging.getLogger(__name__)


class ClientProfile(TimeStampedModel, SoftDeleteModel):
    """
    Extended profile for client-role users.

    Linked 1:1 to UnifiedUser (role='client').
    Stores shopping preferences, shipping defaults, style data,
    and spend/order analytics.

    Access:
        user.client_profile  — reverse OneToOne relation
        ClientProfile.objects.get(user=user) — direct lookup
    """

    # ── Identity link ──────────────────────────────────────────────
    user = models.OneToOneField(
        "authentication.UnifiedUser",
        on_delete=models.CASCADE,
        related_name="client_profile",
        limit_choices_to={"role": "client"},
        help_text="The client user this profile belongs to.",
    )

    # ── Personal Details ───────────────────────────────────────────
    bio = models.TextField(
        blank=True,
        default="",
        max_length=500,
        help_text="Short personal bio (max 500 chars).",
    )

    # ── Shipping / Location ────────────────────────────────────────
    default_shipping_address = models.TextField(
        blank=True,
        default="",
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
        max_length=10,
        choices=SIZE_CHOICES,
        blank=True,
        default="",
        help_text="Preferred clothing size.",
    )
    style_preferences = models.JSONField(
        default=list,
        blank=True,
        help_text='Style tags: ["casual", "afrocentric", "formal"]. Used by AI engine.',
    )
    favourite_colours = models.JSONField(
        default=list,
        blank=True,
        help_text="Favourite colour hex codes or names.",
    )

    # ── Shopping Behaviour ─────────────────────────────────────────
    total_orders    = models.PositiveIntegerField(default=0)
    total_spent_ngn = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=0,
    )

    # ── Profile Completeness ───────────────────────────────────────
    is_profile_complete = models.BooleanField(
        default=False,
        help_text="True once size, address, and style preferences are filled in.",
    )

    # ── Notification preferences ──────────────────────────────────
    email_notifications_enabled = models.BooleanField(
        default=True,
        help_text="Receive order and promo email notifications.",
    )
    sms_notifications_enabled = models.BooleanField(
        default=False,
        help_text="Receive SMS alerts for order updates.",
    )

    class Meta:
        verbose_name        = "Client Profile"
        verbose_name_plural = "Client Profiles"
        db_table            = "client_profile"
        indexes = [
            models.Index(fields=["user"], name="client_profile_user_idx"),
            models.Index(fields=["country"], name="client_profile_country_idx"),
        ]

    def __str__(self) -> str:
        identifier = (
            getattr(self.user, "email", None)
            or getattr(self.user, "phone", None)
            or str(self.user.pk)
        )
        return f"ClientProfile({identifier})"

    # ── Profile completeness ───────────────────────────────────────

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

    # ── Shopping analytics helpers ─────────────────────────────────

    def increment_orders(self, amount_ngn: float | int = 0) -> None:
        """
        Atomically increment total_orders and total_spent_ngn.
        Safe under concurrent load — uses F() expressions.
        """
        try:
            ClientProfile.objects.filter(pk=self.pk).update(
                total_orders=F("total_orders") + 1,
                total_spent_ngn=F("total_spent_ngn") + amount_ngn,
            )
            self.refresh_from_db(fields=["total_orders", "total_spent_ngn"])
        except Exception:
            logger.exception(
                "Failed to increment orders for ClientProfile %s", self.pk
            )

    # ── Idempotent factory ─────────────────────────────────────────

    @classmethod
    def get_or_create_for_user(cls, user) -> "ClientProfile":
        """
        Idempotent — returns existing profile or creates a blank one.
        Used in LoginView to populate has_client_profile in the JWT response.
        """
        profile, _ = cls.objects.get_or_create(user=user)
        return profile
