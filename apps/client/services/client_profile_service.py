# apps/client/services/client_profile_service.py
"""
ClientProfileService — All business logic for client profile CRUD.

Design principles:
  - NEVER call views or serializers directly.
  - Uses Django ORM (NO raw SQL) with select_related/prefetch_related.
  - Emits EventBus events AFTER successful database commits.
  - Raises specific exceptions for the API layer to translate to HTTP errors.
  - Emits audit events via client_audit domain helper (deferred imports,
    never module-level, to prevent circular import during startup).
"""

import logging
from typing import Any
from django.db.models import QuerySet
from django.db import transaction

from apps.common.events import event_bus
from apps.client.models import ClientAddress, ClientProfile

logger = logging.getLogger(__name__)


class ClientProfileService:
    """
    Service layer for client profile operations.

    All public methods are classmethods (no instance needed).
    """

    # ── Retrieve ───────────────────────────────────────────────────

    @classmethod
    def get_profile(cls, user) -> "QuerySet[ClientProfile]":  # noqa: F821
        """
        Get the ClientProfile for `user`, creating one if missing.

        Raises:
            ClientProfile.DoesNotExist — if something is seriously wrong.
        """
        return ClientProfile.get_or_create_for_user(user)

    # ── Update ─────────────────────────────────────────────────────

    @classmethod
    @transaction.atomic
    def update_profile(
        cls, user, data: dict[str, Any]
    ) -> "QuerySet[ClientProfile]":  # noqa: F821
        """
        Partial update of ClientProfile fields from a validated dict.

        Emits: client.profile.updated (after commit)

        Args:
            user:  UnifiedUser instance.
            data:  Dict of validated field names → new values.

        Returns:
            Updated ClientProfile instance.
        """

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
        event_bus.emit_on_commit(
            "client.profile.updated",
            user_id=str(user.pk),
            profile_id=str(profile.pk),
            fields=list(update_fields),
        )

        logger.info(
            "ClientProfileService.update_profile: updated profile %s for user %s",
            profile.pk,
            user.pk,
        )
        # ── Audit event (after commit — won't fire on rollback) ──────────
        _profile_id = str(profile.pk)
        _actor = user
        def _audit_profile_updated():
            try:
                from apps.audit_logs.services.client import client_audit
                client_audit.log_profile_updated(
                    actor=_actor,
                    resource_id=_profile_id,
                    new_values={f: str(data.get(f, "")) for f in update_fields},
                )
            except Exception:
                logger.warning("client_audit.log_profile_updated failed silently", exc_info=True)
        transaction.on_commit(_audit_profile_updated)
        return profile

    # ── Address management ─────────────────────────────────────────

    @classmethod
    @transaction.atomic
    def add_address(
        cls, user, address_data: dict[str, Any]
    ) -> "QuerySet[ClientAddress]":  # noqa: F821
        """
        Add a new shipping address to the client's profile.

        Returns:
            Newly created ClientAddress instance.
        """
        address = user.client_addresses.create(**address_data)
        logger.info(
            "ClientProfileService.add_address: created address %s for client %s",
            address.pk,
            user.pk,
        )
        # ── Audit event ──────────────────────────────────────────────────────────
        try:
            from apps.audit_logs.services.client import client_audit
            client_audit.log_address_saved(
                actor=user,
                address_id=str(address.pk),
                is_default=address_data.get("is_default", False),
            )
        except Exception:
            logger.warning("client_audit.log_address_saved failed silently", exc_info=True)
        return address

    @classmethod
    @transaction.atomic
    def set_default_address(
        cls, user, address_id
    ) -> "QuerySet[ClientAddress]":  # noqa: F821
        """
        Set a specific address as the client's default shipping address.

        Raises:
            ClientAddress.DoesNotExist — if address doesn't belong to user.
        """
        client_profile = user.client_profile

        address = client_profile.client_addresses.get(pk=address_id)
        address.is_default = True
        address.save()  # save() enforces uniqueness of default

        # Mirror to profile shortcut field
        client_profile.update(default_shipping_address=address.street_address)

        logger.info(
            "ClientProfileService.set_default_address: address %s set as default for client %s",
            address.pk,
            user.pk,
        )
        return address

    @classmethod
    def delete_address(cls, user, address_id) -> None:
        """
        Soft-delete a client address.

        Raises:
            ClientAddress.DoesNotExist — if address doesn't belong to user.
        """
        address = user.client_profile.client_addresses.get(pk=address_id)
        address.soft_delete()
        logger.info(
            "ClientProfileService.delete_address: soft-deleted address %s", address.pk
        )
        # ── Audit event ──────────────────────────────────────────────────────────
        try:
            from apps.audit_logs.services.client import client_audit
            client_audit.log_address_saved(
                actor=user,
                address_id=str(address.pk),
                is_default=False,
            )
        except Exception:
            logger.warning("client_audit.delete_address failed silently", exc_info=True)
