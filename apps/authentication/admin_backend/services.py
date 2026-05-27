# apps/authentication/admin_backend/services.py
"""
Admin-only service layer for the authentication domain.

Rules:
  - All mutations use transaction.atomic
  - All post-commit side effects use event_bus.emit_on_commit()
  - Financial fields are never mutated here (handled by wallet domain)
  - Superuser accounts protected from ban operations
"""

from __future__ import annotations

import logging

from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from django.core.exceptions import ValidationError
from django.db import transaction

from apps.common.events import event_bus

User = get_user_model()
logger = logging.getLogger(__name__)


class AdminUserService:
    """Admin-only orchestration for UnifiedUser governance."""

    # ─────────────────────────────────────────────────── suspend / reactivate ──

    @classmethod
    @transaction.atomic
    def suspend_user(
        cls,
        *,
        user_id: str,
        reason: str,
        admin_user,
    ) -> "User":
        """
        Deactivate (suspend) a user account.

        Guards:
          - Cannot suspend a superuser
          - Cannot suspend an already-inactive account

        Post-commit: emits user.suspended on event bus.
        """
        user = User.objects.all_with_deleted().get(pk=user_id)

        if getattr(user, "is_superuser", False):
            raise ValidationError(
                "Superuser accounts cannot be suspended via admin API."
            )
        if not user.is_active:
            raise ValidationError(
                f"User {user.identifying_info} is already suspended/inactive."
            )

        user.is_active = False
        user.save(update_fields=["is_active", "updated_at"])

        logger.info(
            "Admin %s suspended user %s (reason: %s)",
            admin_user.pk,
            user.identifying_info,
            reason,
        )

        event_bus.emit_on_commit(
            "user.suspended",
            user_id=str(user.pk),
            reason=reason,
            admin_user_id=str(admin_user.pk),
        )

        return user

    @classmethod
    @transaction.atomic
    def reactivate_user(
        cls,
        *,
        user_id: str,
        admin_user,
    ) -> "User":
        """
        Reactivate a previously suspended user account.

        Post-commit: emits user.reactivated on event bus.
        """
        user = User.objects.all_with_deleted().get(pk=user_id)

        if user.is_active:
            raise ValidationError(
                f"User {user.identifying_info} is already active."
            )

        user.is_active = True
        user.save(update_fields=["is_active", "updated_at"])

        logger.info(
            "Admin %s reactivated user %s",
            admin_user.pk,
            user.identifying_info,
        )

        event_bus.emit_on_commit(
            "user.reactivated",
            user_id=str(user.pk),
            admin_user_id=str(admin_user.pk),
        )

        return user

    # ─────────────────────────────────────────────────── verify / unverify ──

    @classmethod
    @transaction.atomic
    def admin_verify_user(
        cls,
        *,
        user_id: str,
        admin_user,
    ) -> "User":
        """Force-verify a user's account (bypasses OTP flow)."""
        user = User.objects.all_with_deleted().get(pk=user_id)

        if user.is_verified:
            raise ValidationError(
                f"User {user.identifying_info} is already verified."
            )

        user.is_verified = True
        user.save(update_fields=["is_verified", "updated_at"])

        logger.info(
            "Admin %s force-verified user %s",
            admin_user.pk,
            user.identifying_info,
        )

        event_bus.emit_on_commit(
            "user.verified",
            user_id=str(user.pk),
            admin_user_id=str(admin_user.pk),
            source="admin_force",
        )

        return user

    # ─────────────────────────────────────────────────── password reset ──

    @classmethod
    @transaction.atomic
    def admin_force_reset_password(
        cls,
        *,
        user_id: str,
        new_password: str,
        admin_user,
    ) -> "User":
        """
        Force-set a new password for a user (superuser only operation).
        Invalidates all existing sessions by rotating the password.
        """
        user = User.objects.all_with_deleted().get(pk=user_id)

        if len(new_password) < 8:
            raise ValidationError(
                "New password must be at least 8 characters long."
            )

        user.password = make_password(new_password)
        user.save(update_fields=["password", "updated_at"])

        logger.warning(
            "Admin %s force-reset password for user %s",
            admin_user.pk,
            user.identifying_info,
        )

        event_bus.emit_on_commit(
            "user.password_force_reset",
            user_id=str(user.pk),
            admin_user_id=str(admin_user.pk),
        )

        return user

    # ─────────────────────────────────────────────────── role update ──

    @classmethod
    @transaction.atomic
    def admin_update_user_role(
        cls,
        *,
        user_id: str,
        new_role: str,
        admin_user,
    ) -> "User":
        """
        Update a user's role. Superuser-only operation.
        Note: this bypasses the model-level immutability guard by using update().
        """
        if not getattr(admin_user, "is_superuser", False):
            raise ValidationError(
                "Only superusers can update user roles."
            )

        valid_roles = dict(User.ROLE_CHOICES).keys()
        if new_role not in valid_roles:
            raise ValidationError(f"Invalid role: {new_role}")

        # Use queryset update to bypass model-level clean() immutability guard
        updated = User.objects.all_with_deleted().filter(pk=user_id).update(
            role=new_role
        )
        if not updated:
            raise User.DoesNotExist(f"User {user_id} not found.")

        user = User.objects.all_with_deleted().get(pk=user_id)

        logger.warning(
            "Admin %s changed role of user %s to %s",
            admin_user.pk,
            user.identifying_info,
            new_role,
        )

        event_bus.emit_on_commit(
            "user.role_updated",
            user_id=str(user.pk),
            new_role=new_role,
            admin_user_id=str(admin_user.pk),
        )

        return user
