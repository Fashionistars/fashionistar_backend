import hashlib
import logging
from typing import Any, Optional, Dict
from asgiref.sync import sync_to_async

from django.db.models import Q
from django.db import transaction

from apps.common.utils import (
    get_redis_connection_safe,
    generate_numeric_otp,
    encrypt_otp,
    decrypt_otp,
)
from apps.authentication.models import UnifiedUser
from apps.audit_logs.services.authentication import auth_audit

# Configure logger for application-level events
logger = logging.getLogger(__name__)


def _sha256(plain: str) -> str:
    """Return lowercase hex SHA-256 digest of *plain*."""
    return hashlib.sha256(plain.encode()).hexdigest()


class OTPService:
    """
    Centralised OTP Management Service.

    Handles Generation, Storage (Redis), Encryption, and Verification of OTPs.
    Supports both Synchronous and Asynchronous execution.
    """

    # ------------------------------------------------------------------
    # GENERATE
    # ------------------------------------------------------------------

    @staticmethod
    def generate_otp_sync(
        user_id: Any, purpose: str = "verify", request: Any = None
    ) -> str:
        """
        Generates, encrypts, and stores an OTP in Redis (Synchronous).

        This method generates a cryptographically secure 6-digit OTP, encrypts it
        using Fernet (symmetric encryption), and stores it in Redis with a 5-minute TTL.
        It also maintains a secondary SHA-256 hash index for O(1) reverse lookup.

        Args:
            user_id: The user's primary key (UUID, int, or str).
            purpose: Context for the OTP ('verify', 'reset', 'login').
            request: Optional Django HttpRequest for audit metadata (IP/UA).

        Returns:
            str: The plain-text 6-digit OTP.

        Raises:
            Exception: If Redis connection fails or storage fails.
        """
        try:
            otp = generate_numeric_otp()
            otp_hash = _sha256(otp)  # Deterministic hash for indexing
            encrypted = encrypt_otp(otp)  # Non-deterministic encryption for storage

            redis_conn = get_redis_connection_safe()
            if not redis_conn:
                logger.error("Redis unavailable for OTP generation (User: %s)", user_id)
                raise Exception("Service unavailable")

            # ── Storage Configuration ──────────────────────────────────────
            # Snippet prevents key collision if multiple OTPs exist for one purpose
            snippet = encrypted[:16]
            primary_key = f"otp:{user_id}:{purpose}:{snippet}"
            value = f"{encrypted}|{otp_hash}"
            hash_key = f"otp_hash:{otp_hash}"

            # ── Atomic Redis Execution ─────────────────────────────────────
            pipe = redis_conn.pipeline()
            pipe.setex(primary_key, 300, value)
            pipe.setex(hash_key, 300, primary_key)
            pipe.execute()

            logger.info("OTP generated for User %s (Purpose: %s)", user_id, purpose)

            # ── Audit Trail ────────────────────────────────────────────────
            # Record the generation event for security monitoring.
            try:
                transaction.on_commit(
                    lambda: auth_audit.log_otp_generated(
                        user_id=user_id, purpose=purpose, request=request
                    )
                )
            except Exception as audit_exc:
                logger.warning(
                    "⚠️ OTPService: audit log failed (generate) — %s", audit_exc
                )

            return otp

        except Exception as exc:
            logger.error("❌ OTP Generation Failed: %s", exc, exc_info=True)
            raise

    # ------------------------------------------------------------------
    # VERIFY — by user_id (internal / backward-compat)
    # ------------------------------------------------------------------

    @staticmethod
    def verify_otp_sync(
        user_id: Any, otp: str, purpose: str = "verify", request: Any = None
    ) -> bool:
        """
        Verifies an OTP when user_id is already known (Synchronous).

        Implements strict validation by searching Redis for keys matching the user
        and purpose. On successful match, the OTP is atomically deleted to
        prevent replay attacks.

        Args:
            user_id: The primary key of the user verifying the OTP.
            otp: The plain-text OTP submitted for verification.
            purpose: The context (must match generation purpose).
            request: Optional Django HttpRequest for audit metadata (IP/UA).

        Returns:
            bool: True if verified successfully, False otherwise.
        """
        try:
            redis_conn = get_redis_connection_safe()
            if not redis_conn:
                logger.error("Redis unavailable for OTP verification (User: %s)", user_id)
                return False

            pattern = f"otp:{user_id}:{purpose}:*"
            keys = redis_conn.keys(pattern)

            for key in keys:
                raw = redis_conn.get(key)
                if not raw:
                    continue

                raw_str = raw.decode()

                # Support both "encrypted|hash" and legacy "bare encrypted" formats
                if "|" in raw_str:
                    encrypted_part, stored_hash = raw_str.rsplit("|", 1)
                else:
                    encrypted_part = raw_str
                    stored_hash = None

                decrypted = decrypt_otp(encrypted_part)
                if decrypted == str(otp):
                    # ── Atomic Consumption ─────────────────────────────────
                    with transaction.atomic():
                        pipe = redis_conn.pipeline()
                        pipe.delete(key)
                        if stored_hash:
                            pipe.delete(f"otp_hash:{stored_hash}")
                        pipe.execute()

                        logger.info("✅ OTP Verified: User %s (Purpose: %s)", user_id, purpose)

                        # ── Audit Trail (Success) ──────────────────────────────
                        # Atomic dispatch on commit to prevent ghost logs.
                        # Guarded with try/except: unit-test contexts without
                        # a DB transaction silently skip the audit dispatch.
                        try:
                            transaction.on_commit(
                                lambda: auth_audit.log_otp_verified(
                                    user_id=user_id, purpose=purpose, request=request
                                )
                            )
                        except Exception as audit_exc:
                            logger.warning(
                                "⚠️ OTPService: audit log failed (verify_otp_sync) — %s",
                                audit_exc,
                            )
                    return True

            # ── Audit Trail (Failure) ──────────────────────────────────────
            logger.warning("OTP Verification Failed: User %s (Purpose: %s)", user_id, purpose)
            auth_audit.log_otp_failed(
                identifier=str(user_id),
                purpose=purpose,
                reason="invalid_or_expired",
                request=request,
            )
            return False

        except Exception as exc:
            logger.error("❌ OTP Verification Error: %s", exc, exc_info=True)
            return False

    # ------------------------------------------------------------------
    # VERIFY — by OTP only  (O(1) — no user_id needed in request)
    # ------------------------------------------------------------------

    @staticmethod
    def verify_by_otp_sync(
        otp: str, purpose: str = "verify", request: Any = None
    ) -> Optional[Dict[str, str]]:
        """
        Verifies an OTP without requiring user_id in the request (Synchronous).

        This enables O(1) reverse lookup of users based on the OTP code alone.

        Args:
            otp: Plain-text 6-digit OTP submitted by the client.
            purpose: Expected context ('verify', 'reset', 'login').
            request: Optional Django HttpRequest for audit metadata (IP/UA).

        Returns:
            Optional[Dict[str, str]]: {user_id, purpose} on success, None on failure.
        """
        try:
            redis_conn = get_redis_connection_safe()
            if not redis_conn:
                logger.error("Redis unavailable during OTP-only verification")
                return None

            otp_hash = _sha256(otp)
            hash_key = f"otp_hash:{otp_hash}"

            # ── WATCH/MULTI/EXEC optimistic locking ─────────────────────────
            # Retry up to 3 times on WatchError (concurrent collision).
            max_retries = 3
            user_id = None
            stored_purpose = None

            with redis_conn.pipeline() as pipe:
                for attempt in range(max_retries):
                    try:
                        pipe.watch(hash_key)
                        primary_raw = pipe.get(hash_key)

                        if not primary_raw:
                            pipe.unwatch()
                            logger.warning("OTP-only verify failed: hash index miss")

                            # Audit failure (identifier unknown) — guarded to prevent
                            # DB errors from blocking the verification return path.
                            try:
                                auth_audit.log_otp_failed(
                                    identifier="unknown_via_hash",
                                    purpose=purpose,
                                    reason="not_found",
                                    request=request,
                                )
                            except Exception as audit_exc:
                                logger.warning(
                                    "⚠️ OTPService: audit log failed (hash miss) — %s",
                                    audit_exc,
                                )
                            return None

                        primary_key = primary_raw.decode()
                        parts = primary_key.split(":")
                        if len(parts) < 4 or parts[0] != "otp":
                            pipe.unwatch()
                            logger.warning(
                                "OTP-only verify failed: malformed key '%s'",
                                primary_key,
                            )
                            return None

                        user_id = parts[1]
                        stored_purpose = parts[2]

                        if stored_purpose != purpose:
                            pipe.unwatch()
                            logger.warning(
                                "OTP purpose mismatch: expected=%s got=%s user=%s",
                                purpose,
                                stored_purpose,
                                user_id,
                            )
                            try:
                                auth_audit.log_otp_failed(
                                    identifier=str(user_id),
                                    purpose=purpose,
                                    reason="purpose_mismatch",
                                    request=request,
                                )
                            except Exception as audit_exc:
                                logger.warning(
                                    "⚠️ OTPService: audit log failed (purpose mismatch) — %s",
                                    audit_exc,
                                )
                            return None

                        primary_val = pipe.get(primary_key)
                        if not primary_val:
                            pipe.unwatch()
                            redis_conn.delete(hash_key)  # clean orphaned index
                            logger.warning(
                                "OTP-only verify: primary key expired for user %s",
                                user_id,
                            )
                            try:
                                auth_audit.log_otp_failed(
                                    identifier=str(user_id),
                                    purpose=purpose,
                                    reason="expired",
                                    request=request,
                                )
                            except Exception as audit_exc:
                                logger.warning(
                                    "⚠️ OTPService: audit log failed (expired) — %s",
                                    audit_exc,
                                )
                            return None

                        # ── Step 7: MULTI/EXEC -- atomic compare-and-delete ───
                        pipe.multi()
                        pipe.delete(primary_key)
                        pipe.delete(hash_key)
                        pipe.execute()

                        logger.info(
                            "✅ OTP verified (TOCTOU-safe): user=%s purpose=%s",
                            user_id,
                            purpose,
                        )

                        # Audit success: Atomic dispatch on commit.
                        # Guarded with try/except: unit-test contexts without
                        # a DB transaction silently skip the audit dispatch.
                        try:
                            transaction.on_commit(
                                lambda: auth_audit.log_otp_verified(
                                    user_id=user_id, purpose=purpose, request=request
                                )
                            )
                        except Exception as audit_exc:
                            logger.warning(
                                "⚠️ OTPService: audit log failed (verify_by_otp_sync) — %s",
                                audit_exc,
                            )

                        return {"user_id": user_id, "purpose": stored_purpose}

                    except Exception as watch_exc:
                        exc_name = type(watch_exc).__name__
                        if "WatchError" in exc_name:
                            if attempt < max_retries - 1:
                                continue
                            else:
                                logger.warning(
                                    "OTP WatchError exhausted %d retries", max_retries
                                )
                                return None
                        raise

            return None

        except Exception as exc:
            logger.error("❌ OTP-only Verification Error: %s", exc, exc_info=True)
            return None

    # ------------------------------------------------------------------
    # RESEND
    # ------------------------------------------------------------------

    @staticmethod
    def resend_otp_sync(
        email_or_phone: str, purpose: str = "verify", request: Any = None
    ) -> str:
        """
        Resends an OTP — invalidates previous ones, generates a fresh OTP (Sync).

        Security: Returns a generic message regardless of whether the user
        exists to prevent account enumeration attacks.

        Args:
            email_or_phone (str): Registered email or phone.
            purpose (str): context for the OTP.
            request (HttpRequest, optional): Context for auditing.

        Returns:
            str: Generic non-enumerable success message.
        """
        from apps.authentication.tasks import send_email_task, send_sms_task

        try:
            # ── User Lookup ────────────────────────────────────────────────
            user = UnifiedUser.objects.filter(
                Q(email=email_or_phone)
                if "@" in email_or_phone
                else Q(phone=email_or_phone)
            ).first()

            if not user:
                logger.warning("OTP resend requested for non-existent: %s", email_or_phone)
                return "If an account exists, a new OTP has been sent."

            # ── Invalidate Existing OTPs ───────────────────────────────────
            redis_conn = get_redis_connection_safe()
            if redis_conn:
                pattern = f"otp:{user.id}:{purpose}:*"
                old_keys = redis_conn.keys(pattern)
                if old_keys:
                    pipe = redis_conn.pipeline()
                    for key in old_keys:
                        raw = redis_conn.get(key)
                        if raw:
                            raw_str = raw.decode()
                            if "|" in raw_str:
                                _, old_hash = raw_str.rsplit("|", 1)
                                pipe.delete(f"otp_hash:{old_hash}")
                        pipe.delete(key)
                    pipe.execute()

            # ── Generate New OTP ───────────────────────────────────────────
            otp = OTPService.generate_otp_sync(user.id, purpose, request=request)

            # ── Dispatch Notification ──────────────────────────────────────
            _user_id = str(user.id)
            _otp = otp

            if user.email:
                from django.conf import settings as _settings
                from datetime import datetime as _dt

                _email_context = {
                    "user_id": _user_id,
                    "otp": _otp,
                    "user_name": (
                        getattr(user, "first_name", None) or user.email.split("@")[0]
                    ),
                    "support_email": "support@fashionistar.io",
                    "SITE_URL": getattr(_settings, "SITE_URL", "https://fashionistar.io"),
                    "time": _dt.utcnow().strftime("%H:%M UTC"),
                }
                transaction.on_commit(
                    lambda: send_email_task.delay(
                        subject="🔐 Your New Fashionistar Verification OTP",
                        recipients=[user.email],
                        template_name="authentication/email/resend_otp.html",
                        context=_email_context,
                    )
                )

            elif user.phone:
                _phone_body = (
                    f"Your new Fashionistar verification OTP: {_otp}\n"
                    "Valid for 5 minutes. Do not share this code."
                )
                transaction.on_commit(
                    lambda: send_sms_task.delay(to=str(user.phone), body=_phone_body)
                )

            return "If an account exists, a new OTP has been sent."

        except Exception as exc:
            logger.error("❌ OTP Resend Failed: %s", exc, exc_info=True)
            raise

    @staticmethod
    async def resend_otp_async(
        email_or_phone: str, purpose: str = "verify", request: Any = None
    ) -> str:
        """
        Asynchronous wrapper for resending OTP.

        Args:
            email_or_phone (str): Registered email or phone.
            purpose (str): context for the OTP.
            request (HttpRequest, optional): Context for auditing.

        Returns:
            str: Generic success message.
        """
        try:
            if "@" in email_or_phone:
                user = await UnifiedUser.objects.filter(email=email_or_phone).afirst()
            else:
                user = await UnifiedUser.objects.filter(phone=email_or_phone).afirst()

            if not user:
                return "If an account exists, a new OTP has been sent."

            # Invalidate old OTPs
            redis_conn = get_redis_connection_safe()
            if redis_conn:
                pattern = f"otp:{user.id}:{purpose}:*"
                old_keys = await sync_to_async(redis_conn.keys)(pattern)
                if old_keys:
                    keys_to_del = list(old_keys)
                    for key in old_keys:
                        raw = await sync_to_async(redis_conn.get)(key)
                        if raw:
                            raw_str = raw.decode()
                            if "|" in raw_str:
                                _, old_hash = raw_str.rsplit("|", 1)
                                keys_to_del.append(f"otp_hash:{old_hash}".encode())
                    if keys_to_del:
                        await sync_to_async(redis_conn.delete)(*keys_to_del)

            # Generate new OTP (Async)
            # Note: generate_otp_async should also handle auditing if it existed,
            # but we'll use sync_to_async for the generation call here.
            otp = await sync_to_async(OTPService.generate_otp_sync)(
                user.id, purpose, request=request
            )

            from apps.authentication.tasks import send_email_task, send_sms_task
            from django.conf import settings as _settings
            from datetime import datetime as _dt

            if user.email:
                _email_context = {
                    "user_id": str(user.id),
                    "otp": otp,
                    "user_name": (
                        getattr(user, "first_name", None) or user.email.split("@")[0]
                    ),
                    "support_email": "support@fashionistar.io",
                    "SITE_URL": getattr(_settings, "SITE_URL", "https://fashionistar.io"),
                    "time": _dt.utcnow().strftime("%H:%M UTC"),
                }
                send_email_task.delay(
                    subject="🔐 Your New Fashionistar Verification OTP",
                    recipients=[user.email],
                    template_name="authentication/email/resend_otp.html",
                    context=_email_context,
                )
            elif user.phone:
                _phone_body = (
                    f"Your new Fashionistar verification OTP: {otp}\n"
                    "Valid for 5 minutes. Do not share this code."
                )
                send_sms_task.delay(to=str(user.phone), body=_phone_body)

            return "If an account exists, a new OTP has been sent."

        except Exception as exc:
            logger.error("❌ OTP Resend Async Failed: %s", exc, exc_info=True)
            raise

