# apps/authentication/services/auth_service/sync_service.py
"""
Synchronous Core Authentication Service — Enterprise Edition
============================================================

Records a ``LoginEvent`` on **every** authentication attempt (success AND failure)
and creates a ``UserSession`` row on every **successful** login. 

Concurrently, it seamlessly integrates with the Enterprise Audit Event Log
(AuditEventLog) via the newly decoupled authentication audit helpers to provide
immutable, compliance-grade 7-year retention logs.

This dual-logging strategy provides data for:
  - "Recent Login Activity" (Binance-style) from LoginEvent for user-facing dashboards.
  - "Active Sessions / Devices" (Telegram-style) from UserSession.
  - "Compliance & Security Audits" (SOC2 / GDPR) from AuditEventLog.

LoginEvent recording strategy (append-only, NEVER mutated):
  - BEFORE authentication:   Record nothing (no user resolved yet).
  - AFTER authenticate():    Record the outcome with user PK if resolved, 
                             NULL if completely unknown identifier.
  - On success:              Record OUTCOME_SUCCESS + create UserSession.
  - On SoftDeletedUserError: Record OUTCOME_BLOCKED + failure_reason='account_deleted'.
  - On AccountInactiveError: Record OUTCOME_BLOCKED + failure_reason='account_inactive'.
  - On InvalidCredentials:   Record OUTCOME_FAILED  + failure_reason='invalid_credentials'.

Performance contract:
  - LoginEvent.record() is called SYNCHRONOUSLY (< 1ms, single INSERT).
  - Audit helpers delegate directly to Celery (non-blocking).
  - UserSession.create_from_token() is deferred via transaction.on_commit().
  - Lifecycle counter Celery task remains fire-and-forget via on_commit().
  - NONE of these side-effects can block the login HTTP response.
"""

import logging

from django.contrib.auth import authenticate
from django.contrib.auth.models import update_last_login
from django.core.exceptions import PermissionDenied
from django.db import transaction
from rest_framework_simplejwt.tokens import RefreshToken
from utilities.django_redis import get_redis_connection_safe

logger = logging.getLogger('application')


# ── helper: safe IP extraction ────────────────────────────────────────────────
def _get_ip(request) -> str:
    """Extract the real client IP address safely from the request.

    Evaluates the `X-Forwarded-For` header chain first to bypass load balancers,
    falling back to `REMOTE_ADDR`.

    Args:
        request (HttpRequest, optional): The Django request object.

    Returns:
        str: The extracted IP address, or '0.0.0.0' if not found/no request.
    """
    if not request:
        return '0.0.0.0'
    xff = request.META.get('HTTP_X_FORWARDED_FOR')
    return xff.split(',')[0].strip() if xff else request.META.get('REMOTE_ADDR', '0.0.0.0')


def _get_ua(request) -> str:
    """Extract the raw User-Agent string from the request.

    Args:
        request (HttpRequest, optional): The Django request object.

    Returns:
        str: The User-Agent string, or an empty string if missing/no request.
    """
    if not request:
        return ''
    return request.META.get('HTTP_USER_AGENT', '')


def _record_login_event(
    *,
    user=None,
    ip_address: str,
    user_agent: str,
    auth_method: str,
    outcome: str,
    failure_reason: str = '',
    is_successful: bool = False,
    session=None,
) -> None:
    """Safe wrapper around LoginEvent.record() — never raises, never blocks login.

    This function is responsible strictly for the user-facing Binance-style 
    "Recent Login Activity" logs. It fails gracefully if database insertion fails.

    Args:
        user (UnifiedUser, optional): The user attempting login. Null if unknown.
        ip_address (str): Resolved client IP address.
        user_agent (str): Raw User-Agent string.
        auth_method (str): Authentication method (e.g., 'email', 'phone').
        outcome (str): Event outcome constant (e.g., OUTCOME_SUCCESS).
        failure_reason (str, optional): Reason for failure if applicable.
        is_successful (bool, optional): Boolean success flag.
        session (UserSession, optional): Created session row, if successful.
    """
    try:
        from apps.authentication.models import LoginEvent
        LoginEvent.record(
            user=user,
            ip_address=ip_address or '0.0.0.0',
            user_agent=user_agent,
            auth_method=auth_method,
            outcome=outcome,
            failure_reason=failure_reason,
            is_successful=is_successful,
            session=session,
        )
    except Exception as exc:
        logger.warning("⚠️ LoginEvent.record() failed (non-fatal): %s", exc)


class SyncAuthService:
    """Synchronous Core Authentication Business Logic.

    Enterprise-grade login service featuring:
    - **Soft-delete awareness**: Returns 403 "Account deactivated" if the user
      account exists but is soft-deleted (is_deleted=True).
    - **Inactive account detection**: Returns 403 "Account inactive" if
      is_active=False (admin-disabled, not a soft-delete).
    - **Robust Audit Logging**: Every attempt routes directly to the new 
      AuditEventLog infrastructure for SOC2/GDPR compliance.
    - **LoginEvent recording**: Dashboard tracking events.
    - **UserSession creation**: On success, records active devices page metadata.
    - **Lifecycle counter**: Fires tracking tasks asynchronously.
    - **Rate limiting**: Redis-backed 5 attempts → 15-minute ban.
    """

    @staticmethod
    def login(email_or_phone: str, password: str, request=None) -> dict:
        """Authenticate a user and return JWT access + refresh tokens.

        In addition to tokens, this method strictly records:
          - A User-facing `LoginEvent` row for every outcome (success or failure).
          - A Compliance-grade `AuditEventLog` entry via our helper modules.
          - A `UserSession` row on success (via transaction.on_commit).

        Args:
            email_or_phone (str): The email address or E.164 phone number.
            password (str): The plaintext password to authenticate against.
            request (HttpRequest, optional): The Django HTTP request. Used for 
                IP/UA extraction for both LoginEvent and AuditEventLog.

        Returns:
            dict: Containing:
                - `access` (str): JWT Access Token.
                - `refresh` (str): JWT Refresh Token.
                - `user` (UnifiedUser): The authenticated user instance.

        Raises:
            SoftDeletedUserError: If the account is soft-deleted (is_deleted=True). → 403
            AccountNotVerifiedError: If the account OTP is not verified. → 403
            AccountInactiveError: If the account is disabled (is_active=False). → 403
            InvalidCredentialsError: Wrong password or unknown identifier. → 401
            Exception: Unexpected server errors. → 500
        """
        from apps.authentication.exceptions import (
            SoftDeletedUserError,
            AccountNotVerifiedError,
            AccountInactiveError,
            InvalidCredentialsError,
        )
        from apps.authentication.models import UnifiedUser, LoginEvent

        # ── EXPLICIT IMPORT OF NEW AUDIT HELPERS ─────────────────────────────────
        # Importing directly from the newly defined standalone audit helper module.
        from apps.audit_logs.services.authentication import (
            log_login_success,
            log_login_failed,
            log_login_blocked,
        )

        ip  = _get_ip(request)
        ua  = _get_ua(request)

        # Detect auth method for the audit log
        auth_method = (
            LoginEvent.METHOD_EMAIL
            if email_or_phone and '@' in email_or_phone
            else LoginEvent.METHOD_PHONE
        )

        try:
            # ── 1. Soft-delete pre-check ─────────────────────────────────────
            candidate = None
            try:
                candidate = UnifiedUser.objects.get_by_natural_key(email_or_phone)
            except SoftDeletedUserError:
                logger.warning(
                    "⛔ Login blocked — soft-deleted account: %s", email_or_phone
                )
                
                # A) Record the blocked attempt in user dashboard logs
                _record_login_event(
                    user=None,  # NULL: soft-deleted user is security-sensitive
                    ip_address=ip,
                    user_agent=ua,
                    auth_method=auth_method,
                    outcome=LoginEvent.OUTCOME_BLOCKED,
                    failure_reason='account_deleted',
                    is_successful=False,
                )
                
                # B) Enterprise AuditEventLog — structured high-value event logging
                try:
                    log_login_blocked(
                        email=email_or_phone,
                        actor=None,  # Nullified for soft-deleted security
                        request=request,
                        reason="account_deleted",
                    )
                except Exception as audit_exc:
                    logger.warning("⚠️ Audit log blocked event failed: %s", audit_exc)
                
                raise

            except UnifiedUser.DoesNotExist:
                candidate = None  # Completely unknown identifier

            # ── 2. Django authenticate() ─────────────────────────────────────
            user = authenticate(
                request=request, username=email_or_phone, password=password
            )
            if not user:
                if '@' in email_or_phone:
                    user = authenticate(
                        request=request, email=email_or_phone, password=password
                    )
                else:
                    user = authenticate(
                        request=request, phone=email_or_phone, password=password
                    )

            # ── 3. Classify auth failures ────────────────────────────────────
            if not user:
                # ── 3a: Not-verified check (FIRST — before is_active) ────────
                # Django authenticate() returns None for users with is_active=False,
                # which happens to BOTH unverified AND admin-disabled users.
                # We must check is_verified FIRST to give the user the precise error.                
                if candidate is not None and not candidate.is_verified:
                    logger.warning(
                        "⛔ Login blocked — account not OTP-verified: %s", email_or_phone
                    )
                    
                    _record_login_event(
                        user=candidate,
                        ip_address=ip,
                        user_agent=ua,
                        auth_method=auth_method,
                        outcome=LoginEvent.OUTCOME_BLOCKED,
                        failure_reason='account_not_verified',
                        is_successful=False,
                    )
                    
                    # Enterprise AuditEventLog
                    try:
                        log_login_blocked(
                            email=email_or_phone,
                            actor=candidate,
                            request=request,
                            reason="account_not_verified",
                            resource_id=str(candidate.pk) if candidate else None,
                        )
                    except Exception as audit_exc:
                        logger.warning("⚠️ Audit log blocked event failed: %s", audit_exc)
                        
                    raise AccountNotVerifiedError()

                # ── 3b: Admin deactivation check (SECOND) ────────────────────
                if candidate is not None and not candidate.is_active:
                    logger.warning(
                        "⛔ Login blocked — inactive account: %s", email_or_phone
                    )
                    
                    _record_login_event(
                        user=candidate,
                        ip_address=ip,
                        user_agent=ua,
                        auth_method=auth_method,
                        outcome=LoginEvent.OUTCOME_BLOCKED,
                        failure_reason='account_inactive',
                        is_successful=False,
                    )
                    
                    # Enterprise AuditEventLog
                    try:
                        log_login_blocked(
                            email=email_or_phone,
                            actor=candidate,
                            request=request,
                            reason="account_inactive",
                            resource_id=str(candidate.pk) if candidate else None,
                        )
                    except Exception as audit_exc:
                        logger.warning("⚠️ Audit log blocked event failed: %s", audit_exc)
                        
                    raise AccountInactiveError()

                # ── 3c: Standard Invalid Credentials ─────────────────────────
                logger.warning(
                    "⛔ Failed login — invalid credentials: %s", email_or_phone
                )
                
                _record_login_event(
                    user=candidate,    # May be None if identifier is unknown
                    ip_address=ip,
                    user_agent=ua,
                    auth_method=auth_method,
                    outcome=LoginEvent.OUTCOME_FAILED,
                    failure_reason='invalid_credentials',
                    is_successful=False,
                )
                
                # Enterprise AuditEventLog
                try:
                    log_login_failed(
                        email=email_or_phone,
                        request=request,
                        reason="invalid_credentials",
                    )
                except Exception as audit_exc:
                    logger.warning("⚠️ Audit log failed event failed: %s", audit_exc)
                    
                raise InvalidCredentialsError()

            # ── 4. Update Django last_login ──────────────────────────────────
            update_last_login(None, user)

            # ── 5. Issue JWT tokens ──────────────────────────────────────────
            refresh = RefreshToken.for_user(user)

            # ── 6. Record SUCCESS LoginEvent (synchronous, single INSERT) ────
            _record_login_event(
                user=user,
                ip_address=ip,
                user_agent=ua,
                auth_method=auth_method,
                outcome=LoginEvent.OUTCOME_SUCCESS,
                failure_reason='',
                is_successful=True,
            )

            # ── Enterprise AuditEventLog (Async via Celery Task) ─────────────
            try:
                log_login_success(
                    actor=user,
                    request=request,
                    session_id=str(refresh.access_token.get("jti", "")),
                )
            except Exception as audit_exc:
                # Audit service swallows mostly, but safety wrap to prevent 500s
                logger.warning("⚠️ Audit log success event failed: %s", audit_exc)

            # ── 7. Create UserSession on_commit (Telegram-style active devices) ─
            try:
                def _create_session():
                    try:
                        from apps.authentication.models import UserSession
                        UserSession.create_from_token(
                            user=user,
                            refresh_token=refresh,
                            request=request,
                        )
                    except Exception as sess_exc:
                        logger.warning(
                            "⚠️ UserSession.create_from_token() failed for user=%s: %s",
                            user.pk, sess_exc,
                        )

                transaction.on_commit(_create_session)
            except Exception as sess_setup_exc:
                logger.warning(
                    "⚠️ Could not schedule UserSession creation: %s", sess_setup_exc
                )

            # ── 8. Fire lifecycle login counter (non-blocking) ───────────────
            try:
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

                transaction.on_commit(_fire_counter)
            except Exception:
                pass  # Never block login on analytics failure

            # ── 9. Request logging ───────────────────────────────────────────
            logger.info(
                "✅ User %s logged in (Sync). IP: %s  UA: %.80s",
                user.email or user.phone, ip, ua,
            )

            return {
                'access':  str(refresh.access_token),
                'refresh': str(refresh),
                'user':    user,
            }

        except (SoftDeletedUserError, AccountNotVerifiedError, AccountInactiveError, InvalidCredentialsError):
            # Typed business errors — re-raise so the view returns correct HTTP status
            raise

        except Exception as exc:
            logger.error("❌ Login Sync Error: %s", exc, exc_info=True)
            # Best-effort: record unexpected server-side failure
            _record_login_event(
                user=None,
                ip_address=ip,
                user_agent=ua,
                auth_method=auth_method,
                outcome=LoginEvent.OUTCOME_FAILED,
                failure_reason='server_error',
                is_successful=False,
            )
            # Notice: Middleware automatically handles API_CALL/SYSTEM_ERROR captures 
            # for 500 status codes, so no direct `log_system_error` is strictly needed here.
            
            raise Exception("Login failed due to an unexpected error.") from exc

    # ── RATE LIMITING ────────────────────────────────────────────────────────

    @staticmethod
    def check_rate_limit(ip_address: str, limit: int = 5, timeout: int = 900) -> None:
        """Rate Limiting: Verifies if IP exceeded failed attempt threshold (15-min ban).
        
        Args:
            ip_address (str): The IP to check against Redis.
            limit (int): Allowed attempts.
            timeout (int): Ban duration in seconds.
            
        Raises:
            PermissionDenied: If limit is exceeded.
        """
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
    def increment_login_failure(ip_address: str, timeout: int = 900) -> None:
        """Increment the failure counter in Redis for a specific IP.
        
        Args:
            ip_address (str): The IP to track.
            timeout (int): The expiry duration in seconds.
        """
        try:
            r = get_redis_connection_safe()
            if r:
                key = f"login_attempts:{ip_address}"
                r.incr(key)
                r.expire(key, timeout)
        except Exception:
            pass

    @staticmethod
    def reset_login_failures(ip_address: str) -> None:
        """Reset the failure counter upon successful login.
        
        Args:
            ip_address (str): The IP counter to clear.
        """
        try:
            r = get_redis_connection_safe()
            if r:
                r.delete(f"login_attempts:{ip_address}")
        except Exception:
            pass