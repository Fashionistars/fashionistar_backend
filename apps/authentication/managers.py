# apps/authentication/managers.py
"""
Enterprise-grade custom user manager with:
  ● Soft-delete awareness     — default queryset excludes deleted users
  ● Typed UNIQUE error guard  — distinguishes 'already exists' vs
                                 'exists but was deactivated'
  ● Soft-delete login guard   — get_by_natural_key checks all_with_deleted()
                                 and raises SoftDeletedUserError so login views
                                 can return 403 instead of 404
  ● Async parity              — every method ships a native async twin
"""

import logging

from django.contrib.auth.base_user import BaseUserManager
from django.db import IntegrityError
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from apps.common.managers.soft_delete import SoftDeleteQuerySet

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Helper: import exceptions lazily to avoid circular-import issues
# ─────────────────────────────────────────────────────────────────────────────

def _get_exc():
    """Lazy import so managers.py does not depend on exceptions.py at load time."""
    from apps.authentication.exceptions import (
        DuplicateUserError,
        SoftDeletedUserExistsError,
        SoftDeletedUserError,
    )
    return DuplicateUserError, SoftDeletedUserExistsError, SoftDeletedUserError


# ─────────────────────────────────────────────────────────────────────────────
# Manager
# ─────────────────────────────────────────────────────────────────────────────

class CustomUserManager(BaseUserManager):
    """
    Custom user model manager with soft-delete awareness.

    Default queryset
    ----------------
    Excludes ``is_deleted=True`` records so that normal ORM queries
    (``filter()``, ``get()``, ``authenticate()``) never return deactivated
    users.

    Explicit accessors
    ------------------
    ``all_with_deleted()``  — returns every row, including soft-deleted.
    ``deleted_only()``      — returns only soft-deleted rows.

    Error handling
    --------------
    ``create_user`` catches ``IntegrityError`` (UNIQUE violations) and
    distinguishes between:
      * Email/phone belongs to an *active* user  → ``DuplicateUserError``
      * Email/phone belongs to a *soft-deleted* user → ``SoftDeletedUserExistsError``

    ``get_by_natural_key`` checks ``all_with_deleted()`` after a miss and
    raises ``SoftDeletedUserError`` so login views can return 403 instead
    of the generic 404/401 that an un-aware manager would surface.
    """

    # ── Default queryset (alive users only) ──────────────────────────────────

    def get_queryset(self):
        """
        Return only alive (non-deleted) users by default.

        Returns:
            SoftDeleteQuerySet: Filtered to ``is_deleted=False``.
        """
        return SoftDeleteQuerySet(self.model, using=self._db).alive()

    # ── Unfiltered accessors ─────────────────────────────────────────────────

    def all_with_deleted(self):
        """
        Return ALL users including soft-deleted ones.

        Returns:
            SoftDeleteQuerySet: Unfiltered queryset.
        """
        return SoftDeleteQuerySet(self.model, using=self._db)

    def deleted_only(self):
        """
        Return only soft-deleted users.

        Returns:
            SoftDeleteQuerySet: Filtered to
                ``is_deleted=True``.
        """
        return SoftDeleteQuerySet(self.model, using=self._db).dead()

    # ─────────────────────────────────────────────────────────────────────────
    # create_user (sync)
    # ─────────────────────────────────────────────────────────────────────────

    def create_user(self, email=None, phone=None, password=None, **extra_fields):
        """
        Create a regular user (sync).

        Raises
        ------
        ValueError
            If neither email nor phone is provided.
        DuplicateUserError
            If the email/phone already belongs to an active user.
        SoftDeletedUserExistsError
            If the email/phone belongs to a previously deactivated user.
        """
        DuplicateUserError, SoftDeletedUserExistsError, _ = _get_exc()

        if not email and not phone:
            raise ValueError(_('Either an email address or phone number must be set'))

        email = self.normalize_email(email) if email else None

        try:
            user = self.model(email=email, phone=phone, **extra_fields)
            user.set_password(password)
            user.save(using=self._db)
            logger.info("✅ Created user: email=%s", email or phone)
            return user

        except IntegrityError as exc:
            exc_str = str(exc).upper()
            if 'UNIQUE' in exc_str or 'ALREADY EXISTS' in exc_str:
                # Secondary lookup: is this a soft-deleted account?
                existing = self.all_with_deleted().filter(
                    Q(email=email) | Q(phone=phone)
                ).first()

                if existing and existing.is_deleted:
                    logger.warning(
                        "Registration blocked — soft-deleted account exists: %s",
                        email or phone,
                    )
                    raise SoftDeletedUserExistsError() from exc

                logger.warning(
                    "Registration blocked — active account exists: %s",
                    email or phone,
                )
                raise DuplicateUserError() from exc

            # Unexpected integrity error — re-raise as-is
            logger.error("Unexpected IntegrityError creating user: %s", exc)
            raise

        except Exception as exc:
            logger.error("Error creating user: %s", exc)
            raise

    # ─────────────────────────────────────────────────────────────────────────
    # create_user (async)
    # ─────────────────────────────────────────────────────────────────────────

    async def acreate_user(self, email=None, phone=None, password=None, **extra_fields):
        """
        Create a regular user (async, native ``asave()``).

        Native async implementation using `asave()` to prevent I/O blocking.
        This fits perfectly with async views and consumers.
        Same UNIQUE guard as the sync version.
        """
        DuplicateUserError, SoftDeletedUserExistsError, _ = _get_exc()

        if not email and not phone:
            raise ValueError(_('Either an email address or phone number must be set'))

        email = self.normalize_email(email) if email else None

        try:
            user = self.model(email=email, phone=phone, **extra_fields)
            user.set_password(password)
            
            # Using native async save
            await user.asave(using=self._db)
            logger.info("✅ Created user (async): email=%s", email or phone)
            return user

        except IntegrityError as exc:
            exc_str = str(exc).upper()
            if 'UNIQUE' in exc_str or 'ALREADY EXISTS' in exc_str:
                existing = await self.all_with_deleted().filter(
                    Q(email=email) | Q(phone=phone)
                ).afirst()

                if existing and existing.is_deleted:
                    raise SoftDeletedUserExistsError() from exc
                raise DuplicateUserError() from exc

            logger.error("Unexpected IntegrityError creating user (async): %s", exc)
            raise

        except Exception as exc:
            logger.error("Error creating user (async): %s", exc)
            raise

    # ─────────────────────────────────────────────────────────────────────────
    # create_superuser (sync)
    # ─────────────────────────────────────────────────────────────────────────

    def create_superuser(self, email=None, phone=None, password=None, **extra_fields):
        """Create a superuser (sync). Auto-sets is_staff/is_superuser/is_verified/role."""
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_active', True)
        extra_fields.setdefault('is_verified', True)    # Auto-verify superusers
        extra_fields.setdefault('role', 'admin')    # Default to Admin role

        if extra_fields.get('is_staff') is not True:
            raise ValueError(_('Superuser must have is_staff=True.'))
        if extra_fields.get('is_superuser') is not True:
            raise ValueError(_('Superuser must have is_superuser=True.'))
        if extra_fields.get('is_verified') is not True:
            raise ValueError(_('Superuser must have is_verified=True.'))
        if extra_fields.get('role') != 'admin':
            raise ValueError(_('Superuser must have role=admin.'))

        try:
            return self.create_user(email, phone, password, **extra_fields)
        except Exception as exc:
            logger.error("Error creating superuser: %s", exc)
            raise

    # ─────────────────────────────────────────────────────────────────────────
    # create_superuser (async)
    # ─────────────────────────────────────────────────────────────────────────

    async def acreate_superuser(self, email=None, phone=None, password=None, **extra_fields):
        """
        Create a superuser (async version).
        
        Leverages `acreate_user` internally to reuse the async creation logic
        while enforcing superuser privileges.
        """
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_active', True)
        extra_fields.setdefault('is_verified', True)
        extra_fields.setdefault('role', 'admin')

        if extra_fields.get('is_staff') is not True:
            raise ValueError(_('Superuser must have is_staff=True.'))
        if extra_fields.get('is_superuser') is not True:
            raise ValueError(_('Superuser must have is_superuser=True.'))
        if extra_fields.get('is_verified') is not True:
            raise ValueError(_('Superuser must have is_verified=True.'))
        if extra_fields.get('role') != 'admin':
            raise ValueError(_('Superuser must have role=admin.'))

        try:
            return await self.acreate_user(email, phone, password, **extra_fields)
        except Exception as exc:
            logger.error("Error creating superuser (async): %s", exc)
            raise



    # ─────────────────────────────────────────────────────────────────────────
    # get_by_natural_key — soft-delete aware (sync)
    # ─────────────────────────────────────────────────────────────────────────

    def get_by_natural_key(self, identifier):
        """
        Look up a user by email OR phone.

        On the first miss (alive-only), a secondary lookup on
        ``all_with_deleted()`` checks whether the account was soft-deleted.
        If so, ``SoftDeletedUserError`` is raised so the login view can
        return a 403 with a helpful message instead of a generic 404.

        Raises
        ------
        SoftDeletedUserError
            If the identifier belongs to a soft-deleted account.
        self.model.DoesNotExist
            If the identifier is completely unknown.
        """
        _, __, SoftDeletedUserError = _get_exc()

        try:
            return self.get(Q(email=identifier) | Q(phone=identifier))
        except self.model.DoesNotExist:
            pass  # Might be soft-deleted — do the secondary check

        # Secondary: check archived accounts
        ghost = self.all_with_deleted().filter(
            Q(email=identifier) | Q(phone=identifier),
            is_deleted=True,
        ).first()

        if ghost:
            logger.warning(
                "Login blocked — soft-deleted user attempted login: %s",
                identifier,
            )
            raise SoftDeletedUserError()

        logger.warning("No user found for identifier: %s", identifier)
        raise self.model.DoesNotExist(
            _('No active user with this email or phone number.')
        )

    # ─────────────────────────────────────────────────────────────────────────
    # get_by_natural_key — soft-delete aware (async)
    # ─────────────────────────────────────────────────────────────────────────

    async def aget_by_natural_key(self, identifier):
        """Async twin of ``get_by_natural_key``."""
        _, __, SoftDeletedUserError = _get_exc()

        try:
            return await self.aget(Q(email=identifier) | Q(phone=identifier))
        except self.model.DoesNotExist:
            pass

        ghost = await self.all_with_deleted().filter(
            Q(email=identifier) | Q(phone=identifier),
            is_deleted=True,
        ).afirst()

        if ghost:
            logger.warning(
                "Login blocked (async) — soft-deleted user: %s", identifier
            )
            raise SoftDeletedUserError()

        raise self.model.DoesNotExist(
            _('No active user with this email or phone number.')
        )
