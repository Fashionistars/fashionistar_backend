"""
Shared role constants and helpers for Fashionistar.

This module is the backend source of truth for role-group checks outside the
authentication model itself. It deliberately avoids importing the user model so
common utilities can use it without circular dependencies.
"""

from __future__ import annotations

from typing import Iterable

# ── Canonical raw role values ──────────────────────────────────────────────
ROLE_VENDOR = "vendor"
ROLE_CLIENT = "client"
ROLE_STAFF = "staff"
ROLE_ADMIN = "admin"
ROLE_EDITOR = "editor"
ROLE_SUPPORT = "support"
ROLE_ASSISTANT = "assistant"
ROLE_MODERATOR = "moderator"
ROLE_SUPER_ADMIN = "super_admin"
ROLE_SUPER_VENDOR = "super_vendor"
ROLE_SUPER_CLIENT = "super_client"
ROLE_SUPER_STAFF = "super_staff"
ROLE_SUPER_EDITOR = "super_editor"
ROLE_SUPER_SUPPORT = "super_support"
ROLE_SUPER_ASSISTANT = "super_assistant"
ROLE_SUPER_MODERATOR = "super_moderator"

# Compatibility aliases that still appear in some legacy guards.
ROLE_REVIEWER_ALIAS = "reviewer"

CLIENT_ROLES = frozenset({ROLE_CLIENT, ROLE_SUPER_CLIENT})
VENDOR_ROLES = frozenset({ROLE_VENDOR, ROLE_SUPER_VENDOR})
SUPPORT_ROLES = frozenset({ROLE_SUPPORT, ROLE_SUPER_SUPPORT})
EDITOR_ROLES = frozenset({ROLE_EDITOR, ROLE_SUPER_EDITOR, ROLE_REVIEWER_ALIAS})
MODERATOR_ROLES = frozenset({ROLE_MODERATOR, ROLE_SUPER_MODERATOR})
SALES_ROLES = frozenset({ROLE_ASSISTANT, ROLE_SUPER_ASSISTANT})
ADMIN_ROLES = frozenset({ROLE_ADMIN, ROLE_SUPER_ADMIN})
STAFF_ROLES = frozenset(
    {
        ROLE_STAFF,
        ROLE_SUPER_STAFF,
        *ADMIN_ROLES,
        *SUPPORT_ROLES,
        *EDITOR_ROLES,
        *SALES_ROLES,
        *MODERATOR_ROLES,
    }
)


def normalize_role(role: str | None) -> str:
    """Return a trimmed lowercase role string."""

    return str(role or "").strip().lower()


def has_any_role(role: str | None, allowed_roles: Iterable[str]) -> bool:
    """Return True when the supplied role is inside the allowed group."""

    return normalize_role(role) in {normalize_role(item) for item in allowed_roles}


def is_client_role(role: str | None) -> bool:
    """Return True for client and super-client accounts."""

    return has_any_role(role, CLIENT_ROLES)


def is_vendor_role(role: str | None) -> bool:
    """Return True for vendor and super-vendor accounts."""

    return has_any_role(role, VENDOR_ROLES)


def is_support_role(role: str | None) -> bool:
    """Return True for support and super-support accounts."""

    return has_any_role(role, SUPPORT_ROLES)


def is_editor_role(role: str | None) -> bool:
    """Return True for editor-role accounts and compatibility aliases."""

    return has_any_role(role, EDITOR_ROLES)


def is_moderator_role(role: str | None) -> bool:
    """Return True for moderator and super-moderator accounts."""

    return has_any_role(role, MODERATOR_ROLES)


def is_sales_role(role: str | None) -> bool:
    """Return True for assistant-role accounts."""

    return has_any_role(role, SALES_ROLES)


def is_admin_role(role: str | None) -> bool:
    """Return True for admin and super-admin accounts."""

    return has_any_role(role, ADMIN_ROLES)


def is_staff_role(role: str | None) -> bool:
    """Return True for any internal staff-facing account role."""

    return has_any_role(role, STAFF_ROLES)


__all__ = [
    "ADMIN_ROLES",
    "CLIENT_ROLES",
    "EDITOR_ROLES",
    "MODERATOR_ROLES",
    "ROLE_ADMIN",
    "ROLE_ASSISTANT",
    "ROLE_CLIENT",
    "ROLE_EDITOR",
    "ROLE_MODERATOR",
    "ROLE_REVIEWER_ALIAS",
    "ROLE_STAFF",
    "ROLE_SUPPORT",
    "ROLE_SUPER_ADMIN",
    "ROLE_SUPER_ASSISTANT",
    "ROLE_SUPER_CLIENT",
    "ROLE_SUPER_EDITOR",
    "ROLE_SUPER_MODERATOR",
    "ROLE_SUPER_STAFF",
    "ROLE_SUPER_SUPPORT",
    "ROLE_SUPER_VENDOR",
    "ROLE_VENDOR",
    "SALES_ROLES",
    "STAFF_ROLES",
    "SUPPORT_ROLES",
    "VENDOR_ROLES",
    "has_any_role",
    "is_admin_role",
    "is_client_role",
    "is_editor_role",
    "is_moderator_role",
    "is_sales_role",
    "is_staff_role",
    "is_support_role",
    "is_vendor_role",
    "normalize_role",
]
