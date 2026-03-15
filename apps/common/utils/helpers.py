# apps/common/utils/helpers.py
"""
General-purpose helper utilities for Fashionistar.

Contents
────────
- OTP cryptography   — Fernet encrypt / decrypt for OTP values stored in Redis.
- OTP generation     — Numeric OTP strings.
- OTP expiry         — Timezone-aware expiry datetime.
- user_directory_path — Cloudinary-compatible upload path generator used by
                        model ``FileField`` / ``ImageField`` instances.
"""
from __future__ import annotations

import base64
import datetime
import logging
import random
import time
from typing import Optional

from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# 1. Fernet cipher initialisation
# ─────────────────────────────────────────────────────────────────────────────

try:
    from cryptography.fernet import Fernet

    _base_key   = settings.SECRET_KEY.encode()
    _base_key   = _base_key.ljust(32, b"\0")[:32]
    cipher_suite = Fernet(base64.urlsafe_b64encode(_base_key))
except Exception as _exc:
    logger.critical("Failed to initialise Fernet encryption key: %s", _exc)
    cipher_suite = None  # type: ignore[assignment]


# ─────────────────────────────────────────────────────────────────────────────
# 2. OTP Cryptography
# ─────────────────────────────────────────────────────────────────────────────

def encrypt_otp(otp: str) -> str:
    """
    Encrypt a plain-text OTP using Fernet symmetric encryption.

    Args:
        otp: The plain-text OTP string.

    Returns:
        URL-safe base64-encoded ciphertext.

    Raises:
        RuntimeError: If the encryption suite failed to initialise at boot.
    """
    if not cipher_suite:
        raise RuntimeError("Encryption suite not initialised.")
    try:
        return cipher_suite.encrypt(otp.encode()).decode()
    except Exception as exc:
        logger.error("OTP encryption failed: %s", exc)
        raise


def decrypt_otp(encrypted_otp: str) -> str:
    """
    Decrypt a Fernet-encrypted OTP back to plain text.

    Args:
        encrypted_otp: The ciphertext string produced by ``encrypt_otp``.

    Returns:
        Plain-text OTP string.

    Raises:
        RuntimeError: If the encryption suite failed to initialise at boot.
    """
    if not cipher_suite:
        raise RuntimeError("Encryption suite not initialised.")
    try:
        return cipher_suite.decrypt(encrypted_otp.encode()).decode()
    except Exception as exc:
        logger.error("OTP decryption failed: %s", exc)
        raise


# ─────────────────────────────────────────────────────────────────────────────
# 3. OTP Generation & Expiry
# ─────────────────────────────────────────────────────────────────────────────

def generate_numeric_otp(length: int = 6) -> str:
    """
    Generate a cryptographically random numeric OTP.

    Uses ``random.choices`` — acceptable for OTP codes because the
    real secret is the encryption layer and the short TTL, not the
    PRNG itself.  For higher entropy use ``secrets.choice`` instead.

    Args:
        length: Number of digits (default 6).

    Returns:
        Numeric OTP string of the requested length.
    """
    return "".join(random.choices("0123456789", k=length))


def get_otp_expiry_datetime(seconds: int = 300) -> datetime.datetime:
    """
    Return a timezone-aware datetime ``seconds`` from now as the OTP expiry.

    Args:
        seconds: TTL in seconds (default 300 = 5 minutes).

    Returns:
        Timezone-aware datetime object.
    """
    return timezone.now() + datetime.timedelta(seconds=seconds)


# ─────────────────────────────────────────────────────────────────────────────
# 4. Upload path generator
# ─────────────────────────────────────────────────────────────────────────────

def user_directory_path(instance, filename: str) -> str:
    """
    Generate a Cloudinary-compatible upload path for a model file field.

    Path structure:
        uploads/{role_folder}/{domain}/user_{user_id}/{pk}_{timestamp}.{ext}

    Where ``role_folder`` is derived from the user's ``role`` field and
    ``domain`` from the instance's model class name.

    This function is used as the ``upload_to`` argument on model
    ``FileField`` / ``ImageField`` instances that still use Django's
    storage layer (i.e., legacy fields not yet migrated to the URL pattern).

    Args:
        instance: The Django model instance being saved.
        filename: The original filename provided by the client.

    Returns:
        Relative path string for Cloudinary storage.

    Raises:
        ``django.core.exceptions.ValidationError`` on internal error.
    """
    from django.core.exceptions import ValidationError

    try:
        user        = None
        domain      = "other"
        model_name  = instance.__class__.__name__.lower()

        # ── Domain detection ──────────────────────────────────────────────
        if "product" in model_name:
            domain = "products"
        elif "vendor" in model_name:
            domain = "vendors"
        elif "category" in model_name:
            domain = "categories"
        elif "brand" in model_name:
            domain = "brands"
        elif "user" in model_name or "profile" in model_name:
            domain = "users"

        # ── User resolution ───────────────────────────────────────────────
        if hasattr(instance, "user") and instance.user:
            user = instance.user
        elif hasattr(instance, "vendor") and hasattr(instance.vendor, "user") and instance.vendor.user:
            user = instance.vendor.user
        elif (
            hasattr(instance, "product")
            and hasattr(instance.product, "vendor")
            and hasattr(instance.product.vendor, "user")
        ):
            user = getattr(instance.product.vendor, "user", None)

        # ── RBAC folder ───────────────────────────────────────────────────
        role_folder = "general"
        if user and hasattr(user, "role") and user.role:
            role = str(user.role).lower()
            if role in ("admin", "staff", "support", "reviewer", "assistant"):
                role_folder = "internal_staff"
            elif role == "vendor":
                role_folder = "vendors"
            elif role == "client":
                role_folder = "clients"

        # ── Safe filename ─────────────────────────────────────────────────
        ext          = filename.rsplit(".", 1)[-1] if "." in filename else ""
        pk           = getattr(instance, "pk", "new")
        ts           = int(time.time())
        safe_filename = f"{pk}_{ts}.{ext}" if ext else f"{pk}_{ts}"

        if user:
            return f"uploads/{role_folder}/{domain}/user_{user.id}/{safe_filename}"
        return f"uploads/system/{domain}/general/{safe_filename}"

    except Exception as exc:
        raise ValidationError(f"Error generating upload path: {exc}") from exc
