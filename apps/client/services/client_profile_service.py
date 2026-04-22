# apps/client/services/client_profile_service.py
"""
ClientProfileService — All business logic for client profile CRUD.

Design principles:
  - NEVER call views or serializers directly.
  - Uses Django ORM (NO raw SQL) with select_related/prefetch_related.
  - Emits EventBus events AFTER successful database commits.
  - Raises specific exceptions for the API layer to translate to HTTP errors.
"""
import logging
from typing import Any

from django.db import transaction

from apps.common.events import EventBus

logger = logging.getLogger(__name__)


class ClientProfileService:
    """
    Service layer for client profile operations.

    All public methods are classmethods (no instance needed).
    """

    # ── Retrieve ───────────────────────────────────────────────────

    @classmethod
    def get_profile(cls, user) -> "ClientProfile":  # noqa: F821
        """
        Get the ClientProfile for `user`, creating one if missing.

        Raises:
            ClientProfile.DoesNotExist — if something is seriously wrong.
        """
        from apps.client.models import ClientProfile
        return ClientProfile.get_or_create_for_user(user)

    # ── Update ─────────────────────────────────────────────────────

    @classmethod
    @transaction.atomic
    def update_profile(cls, user, data: dict[str, Any]) -> "ClientProfile":  # noqa: F821
        """
        Partial update of ClientProfile fields from a validated dict.

        Emits: client.profile.updated (after commit)

        Args:
            user:  UnifiedUser instance.
            data:  Dict of validated field names → new values.

        Returns:
            Updated ClientProfile instance.
        """
        from apps.client.models import ClientProfile

        profile = ClientProfile.get_or_create_for_user(user)

        allowed_fields = {
            "bio",
            "default_shipping_address",
            "state",
            "country",
            "preferred_size",
            "style_preferences",
            "favourite_colours",
            "email_notifications_enabled",
            "sms_notifications_enabled",
        }

        update_fields = ["updated_at"]
        for field, value in data.items():
            if field in allowed_fields:
                setattr(profile, field, value)
                update_fields.append(field)

        profile.save(update_fields=update_fields)
        profile.update_completeness()

        # ── Emit event after DB commit ───────────────────────────
        transaction.on_commit(lambda: EventBus.emit(
            "client.profile.updated",
            {
                "user_id": str(user.pk),
                "profile_id": str(profile.pk),
                "fields": list(data.keys()),
            },
        ))

        logger.info(
            "ClientProfileService.update_profile: updated profile %s for user %s",
            profile.pk, user.pk,
        )
        return profile

    # ── Address management ─────────────────────────────────────────

    @classmethod
    @transaction.atomic
    def add_address(cls, user, address_data: dict[str, Any]) -> "ClientAddress":  # noqa: F821
        """
        Add a new shipping address to the client's profile.

        Returns:
            Newly created ClientAddress instance.
        """
        from apps.client.models import ClientProfile, ClientAddress

        profile = ClientProfile.get_or_create_for_user(user)
        address = ClientAddress.objects.create(client=profile, **address_data)
        logger.info(
            "ClientProfileService.add_address: created address %s for client %s",
            address.pk, profile.pk,
        )
        return address

    @classmethod
    @transaction.atomic
    def set_default_address(cls, user, address_id) -> "ClientAddress":  # noqa: F821
        """
        Set a specific address as the client's default shipping address.

        Raises:
            ClientAddress.DoesNotExist — if address doesn't belong to user.
        """
        from apps.client.models import ClientProfile, ClientAddress

        profile = ClientProfile.get_or_create_for_user(user)
        address = ClientAddress.objects.get(pk=address_id, client=profile)
        address.is_default = True
        address.save()  # save() enforces uniqueness of default

        # Mirror to profile shortcut field
        ClientProfile.objects.filter(pk=profile.pk).update(
            default_shipping_address=address.street_address
        )

        logger.info(
            "ClientProfileService.set_default_address: address %s set as default for client %s",
            address.pk, profile.pk,
        )
        return address

    @classmethod
    def delete_address(cls, user, address_id) -> None:
        """
        Soft-delete a client address.

        Raises:
            ClientAddress.DoesNotExist — if address doesn't belong to user.
        """
        from apps.client.models import ClientProfile, ClientAddress

        profile = ClientProfile.get_or_create_for_user(user)
        address = ClientAddress.objects.get(pk=address_id, client=profile)
        address.soft_delete()
        logger.info(
            "ClientProfileService.delete_address: soft-deleted address %s", address.pk
        )
