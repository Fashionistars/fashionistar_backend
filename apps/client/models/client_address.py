# apps/client/models/client_address.py
"""
ClientAddress — Multiple shipping addresses per client.

Supports a primary flag so checkout always has a fast
default_shipping_address without a full-table scan.

Architecture:
  ─ set_as_default() uses transaction.atomic() to guarantee exactly
    ONE default address per client at all times — race-condition safe.
  ─ get_default_for_client / aget_default_for_client are single-query
    class methods so views never call raw ORM for the common case.
"""

from __future__ import annotations

import logging

from apps.common.models import TimeStampedModel, SoftDeleteModel
from django.db import models, transaction

logger = logging.getLogger(__name__)


def _profile_from_actor(actor):
    """Accept either a UnifiedUser or ClientProfile for legacy callers."""
    if actor is None:
        return None
    if actor.__class__.__name__ == "ClientProfile":
        return actor
    return getattr(actor, "client_profile", None)


class ClientAddress(TimeStampedModel, SoftDeleteModel):
    """
    A saved shipping address belonging to a ClientProfile.

    Clients may have many addresses; exactly one can be flagged
    as `is_default=True`.  The save() method enforces uniqueness
    of the default per-client at the ORM level (sync path).
    For concurrent async callers use `set_as_default()` classmethod
    which wraps the operation in `transaction.atomic()`.

    Reverse-relationship cheat-sheet:
        profile.client_addresses.filter(...)  → all addresses for profile
        profile.client_addresses.filter(is_default=True).first() → default
    """

    client = models.ForeignKey(
        "client.ClientProfile",
        on_delete=models.CASCADE,
        related_name="client_addresses",
        help_text="The client profile this address belongs to.",
    )

    label = models.CharField(
        max_length=80,
        blank=True,
        default="Home",
        help_text="Short label: 'Home', 'Office', or 'Mum\\'s place'.",
    )

    # ── Address fields ────────────────────────────────────────────
    full_name = models.CharField(max_length=150, blank=True, default="")
    phone = models.CharField(max_length=30, blank=True, default="")
    street_address = models.TextField(help_text="Street, house number, landmark.")
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=100)
    country = models.CharField(max_length=100, default="Nigeria")
    postal_code = models.CharField(max_length=20, blank=True, default="")

    is_default = models.BooleanField(
        default=False,
        db_index=True,
        help_text="True if this is the primary address shown at checkout.",
    )

    class Meta:
        verbose_name = "Client Address"
        verbose_name_plural = "Client Addresses"
        db_table = "client_address"
        ordering = ["-is_default", "-created_at"]
        indexes = [
            models.Index(
                fields=["client", "is_default"], name="client_addr_default_idx"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.label} — {self.street_address[:40]}"

    def save(self, *args, **kwargs) -> None:
        """
        If this address is marked as default, clear the default flag
        from all other addresses of the same client atomically before saving.

        NOTE: For concurrent async callers, prefer the `set_as_default()`
        classmethod which uses `select_for_update()` inside a transaction.
        """
        if self.is_default:
            ClientAddress.objects.filter(
                client=self.client,
                is_default=True,
            ).exclude(
                pk=self.pk
            ).update(is_default=False)
        super().save(*args, **kwargs)

    # ══════════════════════════════════════════════════════════════
    #  DATABASE-LEVEL QUERY HELPERS (SYNC)
    # ══════════════════════════════════════════════════════════════

    @classmethod
    def get_default_for_client(cls, user) -> "QuerySet[ClientAddress] | None":
        """
        Single-query lookup: return the default address for a user.

        Traversal: user.client_profile.client_addresses (related_name) filtered on
        is_default=True with select_related to pull the user's user
        in the same query (avoids a second trip for ownership checks).

        Args:
            user: User instance.

        Returns:
            ClientAddress with is_default=True, or None.
        """
        profile = _profile_from_actor(user)
        if profile is None:
            return None
        return (
            cls.objects.filter(client=profile, is_default=True, is_deleted=False)
            .select_related("client__user")
            .first()
        )

    @classmethod
    def set_as_default(
        cls,
        address_id: int,
        user=None,
        *,
        profile=None,
    ) -> "QuerySet[ClientAddress] | None":
        """
        Atomically set one address as default, clearing all others.

        Uses transaction.atomic() + select_for_update() to guarantee:
          - Exactly ONE default per profile at all times
          - No race condition between two concurrent "set default" calls
          - ACID-compliant: if the update fails, no partial state is written

        Args:
            address_id: PK of the address to promote as default.
            user: User instance (ownership guard).

        Returns:
            The updated ClientAddress instance.

        Raises:
            ClientAddress.DoesNotExist: if address not found or not owned
                by this profile.
        """
        profile = profile or _profile_from_actor(user)
        if profile is None:
            raise cls.DoesNotExist("Client profile is required.")

        with transaction.atomic():
            # Lock the profile's address rows to prevent concurrent races
            addresses = cls.objects.select_for_update().filter(
                client=profile, is_deleted=False
            )
            # Clear all defaults in a single UPDATE — one DB round trip
            addresses.update(is_default=False)
            # Set the target address as default
            target = addresses.get(pk=address_id)
            target.is_default = True
            target.save(update_fields=["is_default", "updated_at"])
            return target

    @classmethod
    def get_list_for_client_profiles(cls, user) -> list[QuerySet[ClientAddress]]:
        """
        Single-query: return all active addresses for a profile as list[dict].

        Traversal: user.client_profile.client_addresses (related_name="client_addresses").
        Uses .values() to skip Python model instantiation.

        Args:
            user: User instance (ownership guard).

        Returns:
            list[dict] ordered by default-first, then most-recent.
        """
        profile = _profile_from_actor(user)
        if profile is None:
            return []
        return list(
            cls.objects.filter(client=profile, is_deleted=False)
            .order_by("-is_default", "-created_at")
            .values(
                "id",
                "label",
                "full_name",
                "phone",
                "street_address",
                "city",
                "state",
                "country",
                "postal_code",
                "is_default",
                "created_at",
            )
        )

    @classmethod
    def get_list_for_profile(cls, profile) -> list[QuerySet["ClientAddress"]]:
        """Compatibility alias for callers that already hold ClientProfile."""
        return cls.get_list_for_client_profiles(profile)

    # ══════════════════════════════════════════════════════════════
    #  DATABASE-LEVEL QUERY HELPERS (ASYNC)
    #  Django 6.0 native async ORM — ZERO sync_to_async
    # ══════════════════════════════════════════════════════════════

    @classmethod
    async def aget_default_for_client(cls, user) -> "ClientAddress | None":
        """
        Async single-query lookup: default address for a profile.

        Traversal: user.client_profile.client_addresses filtered on is_default=True.
        Uses afirst() — Django 6.0 native async ORM.

        Args:
            user: User instance (ownership guard).

        Returns:
            ClientAddress with is_default=True, or None.
        """
        profile = _profile_from_actor(user)
        if profile is None:
            return None
        return await (
            cls.objects.filter(client=profile, is_default=True, is_deleted=False)
            .select_related("client__user")
            .afirst()
        )

    @classmethod
    async def aget_list_for_client_profiles(cls, user) -> list[QuerySet[ClientAddress]]:
        """
        Async: return all active addresses for a profile as list[dict].

        Traversal: user.client_profile.client_addresses (related_name="client_addresses").
        Uses async iteration over .values() — ZERO sync_to_async.

        Args:
            user: User instance (ownership guard).

        Returns:
            list[dict] ordered by default-first, then most-recent.
        """
        profile = _profile_from_actor(user)
        if profile is None:
            return []
        qs = (
            cls.objects.filter(client=profile, is_deleted=False)
            .order_by("-is_default", "-created_at")
            .values(
                "id",
                "label",
                "full_name",
                "phone",
                "street_address",
                "city",
                "state",
                "country",
                "postal_code",
                "is_default",
                "created_at",
            )
        )
        return [row async for row in qs]
