# apps/audit_logs/services/authentication/__init__.py

"""Authentication audit helper exports.

This package is imported from multiple auth services using both styles:

    from apps.audit_logs.services.authentication import auth_audit
    from apps.audit_logs.services.authentication import log_login_success

The direct function imports are part of the live login path, so this barrel
must re-export the auth audit helpers instead of leaving the package empty.
"""

from . import auth_audit
from .auth_audit import (
    log_account_updated,
    log_account_verified,
    log_biometric_auth,
    log_biometric_registered,
    log_login_blocked,
    log_login_failed,
    log_login_success,
    log_logout,
    log_mfa_enabled,
    log_otp_failed,
    log_otp_generated,
    log_otp_verified,
    log_password_changed,
    log_password_reset_completed,
    log_password_reset_failed,
    log_password_reset_requested,
    log_register_failed,
    log_register_success,
    log_suspicious_activity,
    log_token_refreshed,
)

__all__ = [
    "auth_audit",
    "log_account_updated",
    "log_account_verified",
    "log_biometric_auth",
    "log_biometric_registered",
    "log_login_blocked",
    "log_login_failed",
    "log_login_success",
    "log_logout",
    "log_mfa_enabled",
    "log_otp_failed",
    "log_otp_generated",
    "log_otp_verified",
    "log_password_changed",
    "log_password_reset_completed",
    "log_password_reset_failed",
    "log_password_reset_requested",
    "log_register_failed",
    "log_register_success",
    "log_suspicious_activity",
    "log_token_refreshed",
]

