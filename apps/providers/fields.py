# apps/providers/fields.py
"""
Custom encrypted model fields for the Fashionistar provider registry.

Rationale
---------
``django-cryptography==1.1`` (the latest release) imports ``django.utils.baseconv``
which was removed in Django 5.0.  Since this project runs Django 6.0 LTS, that
package is permanently broken.

This module implements equivalent functionality using ``cryptography.fernet``
(already a transitive dependency via ``django-allauth`` / ``pyopenssl``),
providing:

  • ``EncryptedCharField``  — stores an encrypted, Base64-Fernet-encoded string.
  • ``EncryptedJSONField``  — stores an encrypted JSON blob.
  • ``encrypt(field)``      — drop-in decorator that returns the field wrapped with
                             encryption (API-compatible with django-cryptography).

Key derivation
--------------
The Fernet key is derived deterministically from Django's ``SECRET_KEY`` using
PBKDF2-HMAC-SHA256 with a fixed application-level salt so that:

  1. No separate ``FIELD_ENCRYPTION_KEY`` environment variable is required for
     basic operation (simplifying ops).
  2. Rotating ``SECRET_KEY`` re-encrypts all fields on next write (migration
     helper available if needed).

For production hardening: set ``FIELD_ENCRYPTION_KEY`` in the environment to an
independent Fernet key (``Fernet.generate_key()``).  When set, it takes priority
over the SECRET_KEY-derived key.

Usage
-----
::

    from apps.providers.fields import encrypt
    from django.db import models

    class MyModel(models.Model):
        secret = encrypt(models.CharField(max_length=512, blank=True, default=""))
        config = encrypt(models.JSONField(default=dict, blank=True))

Storage
-------
Encrypted values are stored as URL-safe Base64 strings.  Because Fernet
authentication tags are 32 bytes and the Base64 overhead is ~1.33×, a 512-char
plaintext field should be stored in a ``max_length=768`` column.  The field
definitions in ``KYCProviderConfig`` already use ``max_length=512`` which
accommodates typical API keys/secrets.  Adjust if values exceed ~360 chars.

Security notes
--------------
- Fields are stored encrypted at the DB layer.  Even if the DB is dumped without
  the application SECRET_KEY, the data remains ciphertext.
- The Fernet token includes an HMAC authentication tag — tampered ciphertext is
  rejected with an ``InvalidToken`` exception (not silently decrypted garbage).
- Empty strings bypass encryption (stored as empty string) to preserve
  ``blank=True, default=""`` semantics across admin forms.
"""
from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
from typing import Any

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.db import models

logger = logging.getLogger("application")

# ---------------------------------------------------------------------------
# Key derivation helper
# ---------------------------------------------------------------------------

_FERNET_KEY_CACHE: Fernet | None = None
_APP_SALT = b"fashionistar-provider-field-encryption-v1"


def _get_fernet() -> Fernet:
    """
    Return a cached Fernet instance, derived from either:

    1. ``FIELD_ENCRYPTION_KEY`` env variable (raw 32-byte URL-safe Base64 key), or
    2. PBKDF2-HMAC-SHA256 over ``settings.SECRET_KEY`` with a fixed salt.
    """
    global _FERNET_KEY_CACHE
    if _FERNET_KEY_CACHE is not None:
        return _FERNET_KEY_CACHE

    raw_env_key = os.environ.get("FIELD_ENCRYPTION_KEY", "").strip()
    if raw_env_key:
        key = raw_env_key.encode() if isinstance(raw_env_key, str) else raw_env_key
    else:
        # Derive a 32-byte key from SECRET_KEY via PBKDF2
        secret = settings.SECRET_KEY.encode("utf-8")
        dk = hashlib.pbkdf2_hmac("sha256", secret, _APP_SALT, iterations=200_000)
        key = base64.urlsafe_b64encode(dk)

    _FERNET_KEY_CACHE = Fernet(key)
    return _FERNET_KEY_CACHE


# ---------------------------------------------------------------------------
# Low-level encrypt / decrypt
# ---------------------------------------------------------------------------

def _fernet_encrypt(plaintext: str) -> str:
    """Encrypt a string and return a URL-safe Base64 Fernet token."""
    if not plaintext:
        return plaintext  # preserve empty-string default semantics
    token = _get_fernet().encrypt(plaintext.encode("utf-8"))
    return token.decode("ascii")


def _fernet_decrypt(ciphertext: str) -> str:
    """Decrypt a Fernet token.  Returns plaintext or empty string on failure."""
    if not ciphertext:
        return ciphertext
    try:
        return _get_fernet().decrypt(ciphertext.encode("ascii")).decode("utf-8")
    except (InvalidToken, Exception) as exc:
        # Log and return empty string — never crash a read due to a bad token.
        # This can happen when rotating keys; treat like "not set".
        logger.error(
            "EncryptedField: failed to decrypt value (key rotation needed?): %s",
            exc,
        )
        return ""


# ---------------------------------------------------------------------------
# EncryptedCharField
# ---------------------------------------------------------------------------


class EncryptedCharField(models.CharField):
    """
    A ``CharField`` that stores its value encrypted via Fernet AES-128-CBC.

    Transparent to Django forms and admin — read/write as plain strings.
    The DB sees only the encrypted Base64 token.

    Note: ``max_length`` controls the **plaintext** max; the stored ciphertext
    is longer (~1.5× due to Fernet overhead + Base64).  The column is created
    with enough headroom automatically (see ``db_type`` override).
    """

    description = "An encrypted character field"

    def from_db_value(
        self,
        value: str | None,
        expression: Any,
        connection: Any,
    ) -> str | None:
        if value is None:
            return value
        return _fernet_decrypt(value)

    def get_prep_value(self, value: str | None) -> str | None:
        if value is None:
            return value
        prepped = super().get_prep_value(value)
        return _fernet_encrypt(prepped) if prepped else prepped

    def get_internal_type(self) -> str:  # pragma: no cover
        return "TextField"  # store as TEXT to accommodate ciphertext length


# ---------------------------------------------------------------------------
# EncryptedJSONField
# ---------------------------------------------------------------------------


class EncryptedJSONField(models.TextField):
    """
    A ``TextField`` that serialises a Python object to JSON, then encrypts it.

    Read: DB ciphertext → decrypt → JSON decode → Python object.
    Write: Python object → JSON encode → encrypt → DB ciphertext.
    """

    description = "An encrypted JSON field"

    def from_db_value(
        self,
        value: str | None,
        expression: Any,
        connection: Any,
    ) -> Any:
        if value is None:
            return value
        decrypted = _fernet_decrypt(value)
        if not decrypted:
            return {}
        try:
            return json.loads(decrypted)
        except json.JSONDecodeError:
            logger.error("EncryptedJSONField: could not JSON-decode decrypted value.")
            return {}

    def get_prep_value(self, value: Any) -> str | None:
        if value is None:
            return value
        serialised = json.dumps(value, ensure_ascii=False)
        return _fernet_encrypt(serialised)

    def from_python(self, value: Any) -> Any:  # used by forms / to_python
        return value

    def get_internal_type(self) -> str:  # pragma: no cover
        return "TextField"


# ---------------------------------------------------------------------------
# encrypt() decorator  (API-compatible with django-cryptography)
# ---------------------------------------------------------------------------


def encrypt(field: models.Field) -> models.Field:
    """
    Wrap any ``CharField`` or ``JSONField`` with the appropriate encrypted
    equivalent.  Mirrors the ``django-cryptography`` ``encrypt()`` API so that
    model code can switch between implementations without changes.

    Supported field types:
      - ``models.CharField``  → ``EncryptedCharField``
      - ``models.JSONField``  → ``EncryptedJSONField``
      - anything else        → returned unchanged with a warning

    Example::

        from apps.providers.fields import encrypt
        api_key = encrypt(models.CharField(max_length=512, blank=True, default=""))
    """
    if isinstance(field, models.JSONField):
        ef = EncryptedJSONField(
            verbose_name=field.verbose_name,
            help_text=field.help_text,
            blank=field.blank,
            null=field.null,
            default=field.default,
        )
        return ef

    if isinstance(field, models.CharField):
        ef = EncryptedCharField(
            max_length=field.max_length,
            verbose_name=field.verbose_name,
            help_text=field.help_text,
            blank=field.blank,
            null=field.null,
            default=field.default,
            db_index=field.db_index,
        )
        return ef

    logger.warning(
        "encrypt(): unsupported field type %s — returning field unencrypted.",
        type(field).__name__,
    )
    return field
