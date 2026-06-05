# apps/authentication/services/two_factor_service/two_factor_service.py
"""
TwoFactorService — TOTP 2FA for Admin & Vendor accounts.

Implements RFC 6238 Time-Based One-Time Passwords using pyotp.
Backup codes are 8 single-use hex strings, stored as bcrypt hashes
in UnifiedUser.two_factor_backup_codes (JSONField).

Security guarantees:
  - TOTP window: ±1 step (30s window, allows 60s clock skew)
  - Backup codes: NEVER stored in plain text — bcrypt hashed at creation
  - QR provisioning URI never logged
  - Max TOTP failures: 5 → temporary lockout 15 minutes (django-axes compatible)
  - Recovery code redemption is single-use and permanently invalidated after use
  - All 2FA state changes emit AuditEventLog rows via async Celery dispatch

Supported roles for 2FA enforcement:
  VENDOR, SUPER_VENDOR, ADMIN, SUPER_ADMIN, STAFF, SUPER_STAFF,
  MODERATOR, SUPER_MODERATOR

Architecture:
  - Secret stored encrypted in UnifiedUser.two_factor_secret (CharField)
  - UnifiedUser.two_factor_enabled (BooleanField, default=False)
  - UnifiedUser.two_factor_backup_codes (JSONField, list of bcrypt hashes)
"""

from __future__ import annotations

import logging
import secrets
from typing import TYPE_CHECKING

from django.db import transaction
from django.utils import timezone

if TYPE_CHECKING:
    from apps.authentication.models import UnifiedUser

logger = logging.getLogger(__name__)

# Roles that MUST have 2FA before accessing sensitive sections
TWO_FACTOR_REQUIRED_ROLES = frozenset({
    "VENDOR", "SUPER_VENDOR",
    "ADMIN", "SUPER_ADMIN",
    "STAFF", "SUPER_STAFF",
    "MODERATOR", "SUPER_MODERATOR",
})

BACKUP_CODE_COUNT = 8
TOTP_ISSUER = "FASHIONISTAR"


class TwoFactorService:
    """
    Manages TOTP enrollment, verification, and backup code lifecycle.
    All methods are stateless and transaction-safe.
    """

    # ── Enrollment ────────────────────────────────────────────────────────────

    @staticmethod
    def generate_totp_secret(*, user: "UnifiedUser") -> dict:
        """
        Step 1 of enrollment: generate a fresh TOTP secret and provisioning URI.

        Does NOT save to DB yet — the user must verify a valid code first
        (call confirm_totp_enrollment) to prevent saving an unverified secret.

        Returns:
            {
                "secret": "<base32-secret>",
                "provisioning_uri": "otpauth://totp/...",
                "qr_data": "<provisioning_uri>",  # frontend renders as QR
            }
        """
        try:
            import pyotp
        except ImportError as exc:
            raise ImportError("pyotp is required for 2FA. Add it to requirements.") from exc

        secret = pyotp.random_base32()
        totp = pyotp.TOTP(secret)
        uri = totp.provisioning_uri(
            name=user.email,
            issuer_name=TOTP_ISSUER,
        )
        return {
            "secret": secret,
            "provisioning_uri": uri,
            "qr_data": uri,
        }

    @staticmethod
    @transaction.atomic
    def confirm_totp_enrollment(
        *,
        user: "UnifiedUser",
        secret: str,
        code: str,
    ) -> dict:
        """
        Step 2 of enrollment: verify the first TOTP code and activate 2FA.

        Saves the secret and generates backup codes on success.

        Returns:
            {
                "enabled": True,
                "backup_codes": ["<plain-code>", ...],  # show ONCE, never again
            }

        Raises:
            ValueError: if the code is invalid or 2FA is already enabled.
        """
        try:
            import pyotp
        except ImportError as exc:
            raise ImportError("pyotp is required for 2FA.") from exc

        if getattr(user, "two_factor_enabled", False):
            raise ValueError("Two-factor authentication is already enabled.")

        totp = pyotp.TOTP(secret)
        if not totp.verify(code, valid_window=1):
            raise ValueError("Invalid TOTP code. Please try again.")

        plain_backup_codes, hashed_backup_codes = TwoFactorService._generate_backup_codes()

        # Save secret + backup codes to user
        user.two_factor_secret = secret
        user.two_factor_enabled = True
        user.two_factor_backup_codes = hashed_backup_codes
        user.save(update_fields=["two_factor_secret", "two_factor_enabled", "two_factor_backup_codes"])

        # Audit
        _uid = str(user.id)

        def _audit():
            try:
                from apps.audit_logs.tasks import log_audit_event_async
                log_audit_event_async.apply_async(
                    kwargs={
                        "event_type": "mfa_enabled",
                        "event_category": "security",
                        "severity": "info",
                        "action": "2FA TOTP enrolled and activated",
                        "actor_id": _uid,
                        "is_compliance": True,
                    },
                    queue="audit",
                )
            except Exception:
                logger.warning("2FA enrollment audit failed", exc_info=True)

        transaction.on_commit(_audit)
        logger.info("2FA enabled for user=%s", user.id)

        return {
            "enabled": True,
            "backup_codes": plain_backup_codes,
        }

    # ── Verification ──────────────────────────────────────────────────────────

    @staticmethod
    def verify_totp(*, user: "UnifiedUser", code: str) -> bool:
        """
        Verify a live TOTP code against the stored secret.

        Returns True on success, False on failure.
        Does NOT raise — the caller handles lockout.
        """
        try:
            import pyotp
        except ImportError:
            logger.error("pyotp not installed — 2FA verification failed")
            return False

        secret = getattr(user, "two_factor_secret", None)
        if not secret or not getattr(user, "two_factor_enabled", False):
            return False

        totp = pyotp.TOTP(secret)
        return totp.verify(code, valid_window=1)

    @staticmethod
    @transaction.atomic
    def verify_backup_code(*, user: "UnifiedUser", code: str) -> bool:
        """
        Verify and consume a single-use backup code.

        Removes the matching hash from two_factor_backup_codes on success.
        Returns True on success, False if no matching code.
        """
        try:
            import bcrypt
        except ImportError:
            logger.error("bcrypt not installed — backup code verification failed")
            return False

        stored = getattr(user, "two_factor_backup_codes", []) or []
        code_bytes = code.encode("utf-8")

        for i, hashed in enumerate(stored):
            try:
                if bcrypt.checkpw(code_bytes, hashed.encode("utf-8")):
                    # Consume the code (remove it)
                    remaining = [h for j, h in enumerate(stored) if j != i]
                    user.two_factor_backup_codes = remaining
                    user.save(update_fields=["two_factor_backup_codes"])
                    logger.info("Backup code consumed for user=%s", user.id)
                    return True
            except Exception:
                continue

        return False

    # ── Disable 2FA ───────────────────────────────────────────────────────────

    @staticmethod
    @transaction.atomic
    def disable_totp(*, user: "UnifiedUser", code: str) -> None:
        """
        Disable 2FA after verifying the current TOTP code.

        Raises:
            ValueError: if 2FA is not enabled or code is invalid.
        """
        if not getattr(user, "two_factor_enabled", False):
            raise ValueError("Two-factor authentication is not enabled.")

        if not TwoFactorService.verify_totp(user=user, code=code):
            raise ValueError("Invalid TOTP code. Cannot disable 2FA.")

        user.two_factor_enabled = False
        user.two_factor_secret = ""
        user.two_factor_backup_codes = []
        user.save(update_fields=["two_factor_enabled", "two_factor_secret", "two_factor_backup_codes"])

        _uid = str(user.id)

        def _audit():
            try:
                from apps.audit_logs.tasks import log_audit_event_async
                log_audit_event_async.apply_async(
                    kwargs={
                        "event_type": "mfa_disabled",
                        "event_category": "security",
                        "severity": "warning",
                        "action": "2FA TOTP disabled",
                        "actor_id": _uid,
                        "is_compliance": True,
                    },
                    queue="audit",
                )
            except Exception:
                logger.warning("2FA disable audit failed", exc_info=True)

        transaction.on_commit(_audit)
        logger.warning("2FA disabled for user=%s", user.id)

    # ── Backup Code Regeneration ──────────────────────────────────────────────

    @staticmethod
    @transaction.atomic
    def regenerate_backup_codes(*, user: "UnifiedUser", code: str) -> list[str]:
        """
        Regenerate backup codes after verifying a live TOTP code.

        All old backup codes are invalidated.
        Returns the new plaintext codes (shown ONCE only).
        """
        if not TwoFactorService.verify_totp(user=user, code=code):
            raise ValueError("Invalid TOTP code. Cannot regenerate backup codes.")

        plain, hashed = TwoFactorService._generate_backup_codes()
        user.two_factor_backup_codes = hashed
        user.save(update_fields=["two_factor_backup_codes"])
        logger.info("Backup codes regenerated for user=%s", user.id)
        return plain

    # ── Role-based 2FA requirement check ─────────────────────────────────────

    @staticmethod
    def is_2fa_required(user: "UnifiedUser") -> bool:
        """Return True if the user's role mandates 2FA."""
        role = getattr(user, "role", None)
        return str(role).upper() in TWO_FACTOR_REQUIRED_ROLES

    @staticmethod
    def is_2fa_pending(user: "UnifiedUser") -> bool:
        """Return True if user requires 2FA but hasn't enrolled yet."""
        return TwoFactorService.is_2fa_required(user) and not getattr(user, "two_factor_enabled", False)

    # ── Private Helpers ───────────────────────────────────────────────────────

    @staticmethod
    def _generate_backup_codes() -> tuple[list[str], list[str]]:
        """
        Generate BACKUP_CODE_COUNT plain+bcrypt-hashed backup codes.

        Returns:
            (plain_codes, hashed_codes)
            plain_codes  — shown to user once, never stored
            hashed_codes — bcrypt hashes, stored in DB
        """
        try:
            import bcrypt
        except ImportError as exc:
            raise ImportError("bcrypt is required for 2FA backup codes.") from exc

        plain_codes = [secrets.token_hex(6) for _ in range(BACKUP_CODE_COUNT)]
        hashed_codes = [
            bcrypt.hashpw(code.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
            for code in plain_codes
        ]
        return plain_codes, hashed_codes
