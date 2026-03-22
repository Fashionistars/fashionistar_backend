#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
scripts/create_superuser.py

Non-interactive UnifiedUser superuser creation helper.

Usage (via Makefile):
    make su EMAIL=admin@example.com PASS=MySecret2026!
    make su               # uses defaults

Usage (direct):
    DJANGO_SETTINGS_MODULE=backend.config.development
        venv/Scripts/python scripts/create_superuser.py [email] [password]

Logic:
    1. If a UnifiedUser exists for that email (even soft-deleted) ->
       RESTORE it, reset to superuser, update password.
    2. If no user exists -> CREATE a fresh superuser.

Exit codes: 0 = success, 1 = error
"""
from __future__ import annotations

import io
import os
import sys

# -----------------------------------------------------------
# Windows UTF-8 fix: cp1252 terminals reject non-ASCII chars
# This is a no-op on Linux/Mac (already UTF-8).
# -----------------------------------------------------------
if getattr(sys.stdout, 'encoding', 'utf-8').lower() != 'utf-8':
    try:
        sys.stdout = io.TextIOWrapper(
            sys.stdout.buffer, encoding='utf-8', errors='replace'
        )
    except Exception:
        pass

if getattr(sys.stderr, 'encoding', 'utf-8').lower() != 'utf-8':
    try:
        sys.stderr = io.TextIOWrapper(
            sys.stderr.buffer, encoding='utf-8', errors='replace'
        )
    except Exception:
        pass


# -----------------------------------------------------------
# Bootstrap Django
# -----------------------------------------------------------
def _bootstrap() -> None:
    if not os.environ.get('DJANGO_SETTINGS_MODULE'):
        os.environ['DJANGO_SETTINGS_MODULE'] = 'backend.config.development'
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if root not in sys.path:
        sys.path.insert(0, root)
    import django
    django.setup()


_bootstrap()

# -----------------------------------------------------------
# Models (safe to import after django.setup())
# -----------------------------------------------------------
from apps.authentication.models import UnifiedUser  # noqa: E402


def ok(msg: str) -> None:
    print(f"[OK] {msg}")


def warn(msg: str) -> None:
    print(f"[WARN] {msg}")


def err(msg: str) -> None:
    print(f"[ERROR] {msg}", file=sys.stderr)


def create_or_restore_superuser(
    email: str = 'admin@fashionistar.io',
    password: str = 'FashionAdmin2026!',
) -> int:
    """Create or restore a UnifiedUser superuser. Returns 0/1."""
    try:
        qs = UnifiedUser.objects.all_with_deleted().filter(email=email)

        if qs.exists():
            user = qs.first()
            was_deleted = user.is_deleted
            user.is_deleted = False
            user.deleted_at = None
            user.is_superuser = True
            user.is_staff = True
            user.is_verified = True
            user.is_active = True
            user.role = 'admin'
            # Clear any stale/invalid avatar URLs so full_clean() doesn't reject
            if user.avatar and not user.avatar.startswith(('http://', 'https://')):
                user.avatar = ''
            user.set_password(password)
            user.save(using='default')

            action = 'Restored soft-deleted' if was_deleted else 'Updated existing'
            ok(f"{action} superuser: {user.email} | {user.member_id}")

        else:
            user = UnifiedUser.objects.create_superuser(
                email=email,
                password=password,
                role='admin',
            )
            ok(f"Created new superuser: {user.email} | {user.member_id}")

        # Verify login works
        from django.contrib.auth import authenticate
        auth_user = authenticate(None, username=email, password=password)
        if auth_user:
            ok(f"Login verified: {auth_user.email}")
        else:
            warn("User saved but authenticate() returned None. Check AUTHENTICATION_BACKENDS.")

        return 0

    except Exception as exc:
        err(f"Failed: {exc}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    _email = sys.argv[1] if len(sys.argv) > 1 and sys.argv[1] else 'admin@fashionistar.io'
    _password = sys.argv[2] if len(sys.argv) > 2 and sys.argv[2] else 'FashionAdmin2026!'
    sys.exit(create_or_restore_superuser(_email, _password))
