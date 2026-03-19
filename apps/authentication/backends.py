from django.contrib.auth.backends import BaseBackend, ModelBackend
from apps.authentication.models import UnifiedUser
import logging

logger = logging.getLogger('application')

class UnifiedUserBackend(BaseBackend):
    """
    Authentication backend for the new UnifiedUser model.
    This allows authentication against our new user model while keeping
    the old system running in parallel. Supports both sync and async methods
    natively for Django 5.0+ / 6.0 readiness.
    """

    def authenticate(self, request, username=None, password=None, **kwargs):
        """
        Authenticate a user against the UnifiedUser model (sync version).
        
        Args:
            request: The HTTP request object.
            username: Email or phone identifier.
            password: User's password.
            **kwargs: Additional keyword arguments.
            
        Returns:
            User instance if authenticated, None otherwise.
        """
        try:
            # Try to find user by email or phone
            user = None
            if username:
                if '@' in username:
                    # Email login: Check strictly against email field
                    try:
                        user = UnifiedUser.objects.get(email=username, is_deleted=False)
                    except UnifiedUser.DoesNotExist:
                        return None
                else:
                    # Phone login: Check strictly against phone field
                    try:
                        user = UnifiedUser.objects.get(phone=username, is_deleted=False)
                    except UnifiedUser.DoesNotExist:
                        return None

            if user and user.check_password(password) and user.is_active:
                logger.info(f"User {user} authenticated via UnifiedUser backend (Sync)")
                return user
            logger.warning(f"Authentication failed for {username}")
            return None
        except Exception as e:
            # Catch SoftDeletedUserError (and any other custom exception) —
            # return None so Django auth tries the next backend or shows
            # a generic "invalid credentials" message (no 500).
            logger.error(f"Error in UnifiedUser authentication: {str(e)}")
            return None

    async def aauthenticate(self, request, username=None, password=None, **kwargs):
        """
        Authenticate a user against the UnifiedUser model (async version).
        
        Uses native Django async ORM methods (aget) to avoid thread blocking
        and sync_to_async wrappers, ensuring compatibility with modern async views.
        
        Args:
            request: The HTTP request object.
            username: Email or phone identifier.
            password: User's password.
            **kwargs: Additional keyword arguments.
            
        Returns:
            User instance if authenticated, None otherwise.
        """
        try:
            user = None
            if username:
                if '@' in username:
                    # Email login: Async lookup
                    try:
                        user = await UnifiedUser.objects.aget(email=username, is_deleted=False)
                    except UnifiedUser.DoesNotExist:
                        logger.warning(f"User with email {username} not found (async)")
                        return None
                else:
                    # Phone login: Async lookup
                    try:
                        user = await UnifiedUser.objects.aget(phone=username, is_deleted=False)
                    except UnifiedUser.DoesNotExist:
                        logger.warning(f"User with phone {username} not found (async)")
                        return None

            if user and user.check_password(password) and user.is_active:
                logger.info(f"User {user} authenticated via UnifiedUser backend (Async)")
                return user
            logger.warning(f"Authentication failed for {username} (async)")
            return None
        except Exception as e:
            logger.error(f"Error in UnifiedUser authentication (async): {str(e)}")
            return None

    def get_user(self, user_id):
        """
        Get a user by ID from the UnifiedUser model (sync version).
        
        Args:
            user_id: The user's primary key.
            
        Returns:
            User instance or None.
        """
        try:
            return UnifiedUser.objects.get(pk=user_id, is_deleted=False)
        except UnifiedUser.DoesNotExist:
            logger.warning(f"User {user_id} not found")
            return None
        except Exception as e:
            logger.error(f"Error getting UnifiedUser {user_id}: {str(e)}")
            return None

    async def aget_user(self, user_id):
        """
        Get a user by ID from the UnifiedUser model (async version).
        
        Uses native aget() for fully non-blocking DB retrieval.
        
        Args:
            user_id: The user's primary key.
            
        Returns:
            User instance or None.
        """
        try:
            return await UnifiedUser.objects.aget(pk=user_id, is_deleted=False)
        except UnifiedUser.DoesNotExist:
            return None
        except Exception as e:
            logger.error(f"Error getting UnifiedUser (async): {str(e)}")
            return None


class SoftDeleteAwareModelBackend(ModelBackend):
    """
    Drop-in replacement for Django's ``ModelBackend`` that handles
    ``SoftDeletedUserError`` gracefully.

    Problem
    -------
    ``ModelBackend.authenticate()`` calls
    ``UserModel._default_manager.get_by_natural_key(username)`` which, in our
    ``CustomUserManager``, raises ``SoftDeletedUserError`` when the identifier
    belongs to a soft-deleted account. This is an ``APIException`` subclass
    that Django's admin ``AuthenticationForm`` cannot catch, resulting in an
    unhandled 500 Internal Server Error on the admin login page.

    Solution
    --------
    Override ``authenticate()`` to catch ``SoftDeletedUserError`` and return
    ``None`` (meaning "this backend cannot authenticate this user"). Django's
    auth framework then falls through and the admin form shows the standard
    "Please enter the correct email and password" validation error.
    """

    def authenticate(self, request, username=None, password=None, **kwargs):
        """
        Wrap ``ModelBackend.authenticate()`` with soft-delete safety.

        Catches ``SoftDeletedUserError`` from ``get_by_natural_key()`` and
        returns ``None`` so the Django admin login form displays a validation
        error instead of crashing with a 500.
        """
        try:
            return super().authenticate(request, username=username, password=password, **kwargs)
        except Exception as exc:
            # Import lazily to avoid circular imports at module load time
            from apps.authentication.exceptions import SoftDeletedUserError
            if isinstance(exc, SoftDeletedUserError):
                logger.warning(
                    "SoftDeleteAwareModelBackend: caught SoftDeletedUserError "
                    "for identifier '%s' — returning None (admin-safe).",
                    username,
                )
                return None
            # Any other unexpected exception — log and return None (never crash login)
            logger.error(
                "SoftDeleteAwareModelBackend: unexpected error during "
                "authenticate(): %s",
                exc, exc_info=True,
            )
            return None
