# apps/client/models/client_address.py
"""
ClientAddress — Multiple shipping addresses per client.

Supports a primary flag so checkout always has a fast
default_shipping_address without a full-table scan.
"""
from apps.common.models import TimeStampedModel, SoftDeleteModel
from django.db import models


class ClientAddress(TimeStampedModel, SoftDeleteModel):
    """
    A saved shipping address belonging to a ClientProfile.

    Clients may have many addresses; exactly one can be flagged
    as `is_default=True`.  The save() method enforces uniqueness
    of the default per-client at the ORM level.
    """

    client = models.ForeignKey(
        "client.ClientProfile",
        on_delete=models.CASCADE,
        related_name="addresses",
        help_text="The client profile this address belongs to.",
    )

    label = models.CharField(
        max_length=80,
        blank=True,
        default="Home",
        help_text="Short label: 'Home', 'Office', or 'Mum\\'s place'.",
    )

    # ── Address fields ────────────────────────────────────────────
    full_name      = models.CharField(max_length=150, blank=True, default="")
    phone          = models.CharField(max_length=30, blank=True, default="")
    street_address = models.TextField(help_text="Street, house number, landmark.")
    city           = models.CharField(max_length=100)
    state          = models.CharField(max_length=100)
    country        = models.CharField(max_length=100, default="Nigeria")
    postal_code    = models.CharField(max_length=20, blank=True, default="")

    is_default = models.BooleanField(
        default=False,
        db_index=True,
        help_text="True if this is the primary address shown at checkout.",
    )

    class Meta:
        verbose_name        = "Client Address"
        verbose_name_plural = "Client Addresses"
        db_table            = "client_address"
        ordering            = ["-is_default", "-created_at"]
        indexes = [
            models.Index(fields=["client", "is_default"], name="client_addr_default_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.label} — {self.street_address[:40]}"

    def save(self, *args, **kwargs) -> None:
        """
        If this address is marked as default, clear the default flag
        from all other addresses of the same client atomically before saving.
        """
        if self.is_default:
            ClientAddress.objects.filter(
                client=self.client,
                is_default=True,
            ).exclude(pk=self.pk).update(is_default=False)
        super().save(*args, **kwargs)
