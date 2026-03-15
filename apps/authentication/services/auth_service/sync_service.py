# apps/authentication/services/auth_service/sync_service.py

import logging

from django.contrib.auth import authenticate
from django.contrib.auth.models import update_last_login
from django.core.exceptions import PermissionDenied
from rest_framework_simplejwt.tokens import RefreshToken
from utilities.django_redis import get_redis_connection_safe

logger = logging.getLogger('application')


class SyncAuthService:
    """
    Synchronous Core Authentication Business Logic.

    Enterprise-grade login service with:
    - Soft-delete awareness: returns 403 "Account deactivated" if the user
      account exists but is soft-deleted (is_deleted=True).
    - Inactive account detection: returns 403 "Account inactive" if
      is_active=False (admin-disabled, not a soft-delete).
    - Lifecycle counter: fires ``increment_lifecycle_login_counter`` Celery
      task after every successful login (non-blocking, fire-and-forget).
    - Rate limiting: Redis-backed 5 attempts → 15-minute ban.
    """

    @staticmethod
    def login(email_or_phone, password, request=None):
        """
        Authenticate a user and return JWT access + refresh tokens.

        Raises
        ------
        SoftDeletedUserError
            If the account is soft-deleted (is_deleted=True).
        AccountInactiveError
            If the account is disabled (is_active=False, not soft-deleted).
        InvalidCredentialsError
            If the password is wrong or the identifier is unknown.
        Exception
            Unexpected server errors (propagated as generic 'Login failed').
        """
        from apps.authentication.exceptions import (
            SoftDeletedUserError,
            AccountInactiveError,
            InvalidCredentialsError,
        )
        from apps.authentication.models import UnifiedUser

        try:
            # ── 1. Soft-delete pre-check ─────────────────────────────────────
            # CustomUserManager.get_by_natural_key() raises SoftDeletedUserError
            # if the identifier exists in all_with_deleted() but is_deleted=True.
            # We call it BEFORE authenticate() to catch this early.
            candidate = None
            try:
                candidate = UnifiedUser.objects.get_by_natural_key(email_or_phone)
            except SoftDeletedUserError:
                logger.warning(
                    "⛔ Login blocked — soft-deleted account: %s", email_or_phone
                )
                raise
            except UnifiedUser.DoesNotExist:
                candidate = None  # Unknown identifier — handled below

            # ── 2. Django authenticate() ─────────────────────────────────────
            user = authenticate(request=request, username=email_or_phone, password=password)

            if not user:
                if '@' in email_or_phone:
                    user = authenticate(request=request, email=email_or_phone, password=password)
                else:
                    user = authenticate(request=request, phone=email_or_phone, password=password)

            # ── 3. Classify auth failures ────────────────────────────────────
            if not user:
                if candidate is not None and not candidate.is_active:
                    logger.warning(
                        "⛔ Login blocked — inactive account: %s", email_or_phone
                    )
                    raise AccountInactiveError()

                logger.warning(
                    "⛔ Failed login — invalid credentials: %s", email_or_phone
                )
                raise InvalidCredentialsError()

            # ── 4. Update Django last_login ──────────────────────────────────
            update_last_login(None, user)

            # ── 5. Fire lifecycle login counter (non-blocking) ───────────────
            try:
                from django.db import transaction as _tx
                from apps.common.tasks import increment_lifecycle_login_counter
                from django.utils import timezone

                login_ts = timezone.now().isoformat()

                def _fire_counter():
                    try:
                        increment_lifecycle_login_counter.apply_async(
                            kwargs={'user_uuid': str(user.pk), 'login_at': login_ts},
                            retry=False,
                            ignore_result=True,
                        )
                    except Exception:
                        pass  # Broker down — best effort only

                _tx.on_commit(_fire_counter)
            except Exception:
                pass  # Never block login on analytics failure

            # ── 6. Request logging ───────────────────────────────────────────
            if request:
                ip = request.META.get('REMOTE_ADDR', '')
                ua = request.META.get('HTTP_USER_AGENT', '')
                logger.info(
                    "✅ User %s logged in (Sync). IP: %s  UA: %s",
                    user.email, ip, ua,
                )

            # ── 7. Issue JWT tokens ──────────────────────────────────────────
            refresh = RefreshToken.for_user(user)
            return {
                'access':  str(refresh.access_token),
                'refresh': str(refresh),
            }

        except (SoftDeletedUserError, AccountInactiveError, InvalidCredentialsError):
            # Typed business errors — re-raise so the view returns correct HTTP status
            raise

        except Exception as exc:
            logger.error("❌ Login Sync Error: %s", exc)
            raise Exception("Login failed due to an unexpected error.")

    # ── RATE LIMITING ────────────────────────────────────────────────────────

    @staticmethod
    def check_rate_limit(ip_address: str, limit: int = 5, timeout: int = 900):
        """Rate Limiting: 5 failed attempts = 15-minute ban."""
        try:
            r = get_redis_connection_safe()
            if not r:
                logger.warning("Redis unavailable for rate limiting, skipping.")
                return
            key = f"login_attempts:{ip_address}"
            attempts = r.get(key)
            if attempts and int(attempts) >= limit:
                logger.warning("⛔ Rate Limit Exceeded for IP %s", ip_address)
                raise PermissionDenied(
                    f"Too many failed attempts. Try again in {timeout // 60} minutes."
                )
        except Exception as exc:
            if isinstance(exc, PermissionDenied):
                raise
            logger.error("Redis Error in Rate Limit: %s", exc)

    @staticmethod
    def increment_login_failure(ip_address: str, timeout: int = 900):
        try:
            r = get_redis_connection_safe()
            if r:
                key = f"login_attempts:{ip_address}"
                r.incr(key)
                r.expire(key, timeout)
        except Exception:
            pass

    @staticmethod
    def reset_login_failures(ip_address: str):
        try:
            r = get_redis_connection_safe()
            if r:
                r.delete(f"login_attempts:{ip_address}")
        except Exception:
            pass
