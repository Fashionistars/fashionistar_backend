# apps/audit_logs/models.py
"""
Enterprise audit log models for the Fashionistar platform.

Architecture:
    AuditEventLog — structured, high-value business events (login, password
    change, admin actions, payments, etc.) with full request context, IP,
    device info, before/after diffs, and 7-year compliance retention.

This complements django-auditlog (which auto-tracks every field change at the
ORM level) by providing STRUCTURED, QUERYABLE, human-readable audit events
with enriched context that the ORM-level log cannot capture.

Design Principles:
    - NEVER blocks the HTTP request — writes go via direct Celery dispatch
    - NEVER raises exceptions to callers — all errors are logged as WARNING
    - 7-year retention for financial compliance (configurable per-event)
    - Immutable once written (no update/delete permission in admin)
    - actor_email snapshot survives even if UnifiedUser is hard-deleted
"""

import logging
import uuid6

from django.db import models
from django.utils.translation import gettext_lazy as _

logger = logging.getLogger(__name__)


# ================================================================
# CHOICES
# ================================================================

class EventCategory(models.TextChoices):
    AUTHENTICATION   = "authentication",   _("Authentication")
    AUTHORIZATION    = "authorization",    _("Authorization")
    ACCOUNT          = "account",          _("Account Management")
    PROFILE          = "profile",          _("Profile")
    SECURITY         = "security",         _("Security")
    ADMIN            = "admin",            _("Admin Action")
    DATA_ACCESS      = "data_access",      _("Data Access")
    DATA_MODIFICATION= "data_modification",_("Data Modification")
    SYSTEM           = "system",           _("System")
    NOTIFICATION     = "notification",     _("Notification")
    COMPLIANCE       = "compliance",       _("Compliance")
    ORDER            = "order",            _("Order")
    PAYMENT          = "payment",          _("Payment")
    CART             = "cart",             _("Cart & Checkout")
    MEASUREMENT      = "measurement",     _("AI Measurement")


class EventType(models.TextChoices):
    # ── Authentication ────────────────────────────────────────────────
    LOGIN_SUCCESS          = "login_success",        _("Login Success")
    LOGIN_FAILED           = "login_failed",         _("Login Failed")
    LOGIN_BLOCKED          = "login_blocked",        _("Login Blocked")
    LOGOUT                 = "logout",               _("Logout")
    TOKEN_REFRESHED        = "token_refreshed",      _("Token Refreshed")
    GOOGLE_LOGIN           = "google_login",         _("Google OAuth Login")
    REGISTER_SUCCESS       = "register_success",     _("Registration Success")
    REGISTER_FAILED        = "register_failed",      _("Registration Failed")

    # ── Account / Profile ─────────────────────────────────────────────
    ACCOUNT_CREATED        = "account_created",      _("Account Created")
    ACCOUNT_UPDATED        = "account_updated",      _("Account Updated")
    ACCOUNT_SOFT_DELETED   = "account_soft_deleted", _("Account Soft-Deleted")
    ACCOUNT_RESTORED       = "account_restored",     _("Account Restored")
    ACCOUNT_HARD_DELETED   = "account_hard_deleted", _("Account Permanently Deleted")
    EMAIL_VERIFIED         = "email_verified",       _("Email Verified")
    PHONE_VERIFIED         = "phone_verified",       _("Phone Verified")
    AVATAR_UPLOADED        = "avatar_uploaded",      _("Avatar Uploaded")
    AVATAR_CLOUDINARY_HOOK = "avatar_cloudinary",    _("Avatar Cloudinary Webhook")

    # ── Security ──────────────────────────────────────────────────────
    PASSWORD_CHANGED       = "password_changed",     _("Password Changed")
    PASSWORD_RESET_REQUEST = "password_reset_request",_("Password Reset Requested")
    PASSWORD_RESET_DONE    = "password_reset_done",  _("Password Reset Completed")
    MFA_ENABLED            = "mfa_enabled",          _("MFA Enabled")
    MFA_DISABLED           = "mfa_disabled",         _("MFA Disabled")
    SUSPICIOUS_ACTIVITY    = "suspicious_activity",  _("Suspicious Activity")
    IP_BLOCKED             = "ip_blocked",           _("IP Blocked")
    FAILED_LOGINS_EXCEEDED = "failed_logins_exceeded",_("Failed Login Limit Exceeded")

    # ── Admin ─────────────────────────────────────────────────────────
    ADMIN_ACTION           = "admin_action",         _("Admin Action")
    ADMIN_BULK_EXPORT      = "admin_bulk_export",    _("Admin Bulk Export")
    ADMIN_BULK_IMPORT      = "admin_bulk_import",    _("Admin Bulk Import")
    ADMIN_BULK_DELETE      = "admin_bulk_delete",    _("Admin Bulk Delete")
    SETTINGS_CHANGED       = "settings_changed",     _("Settings Changed")

    # ── Data Access ───────────────────────────────────────────────────
    DATA_VIEWED            = "data_viewed",          _("Data Viewed")
    DATA_EXPORTED          = "data_exported",        _("Data Exported")
    SENSITIVE_DATA_ACCESS  = "sensitive_data_access",_("Sensitive Data Accessed")

    # ── E-Commerce: Orders ────────────────────────────────────────────
    ORDER_CREATED          = "order_created",        _("Order Created")
    ORDER_UPDATED          = "order_updated",        _("Order Updated")
    ORDER_CANCELLED        = "order_cancelled",      _("Order Cancelled")
    ORDER_FULFILLED        = "order_fulfilled",      _("Order Fulfilled")
    ORDER_RETURNED         = "order_returned",       _("Order Returned")

    # ── E-Commerce: Payments (financial compliance critical) ──────────
    PAYMENT_INITIATED      = "payment_initiated",    _("Payment Initiated")
    PAYMENT_SUCCESS        = "payment_success",      _("Payment Success")
    PAYMENT_FAILED         = "payment_failed",       _("Payment Failed")
    REFUND_INITIATED       = "refund_initiated",     _("Refund Initiated")
    REFUND_COMPLETED       = "refund_completed",     _("Refund Completed")
    DISPUTE_OPENED         = "dispute_opened",       _("Dispute Opened")
    DISPUTE_RESOLVED       = "dispute_resolved",     _("Dispute Resolved")

    # ── E-Commerce: Cart & Checkout ───────────────────────────────────
    CART_UPDATED           = "cart_updated",         _("Cart Updated")
    CHECKOUT_STARTED       = "checkout_started",     _("Checkout Started")
    CHECKOUT_COMPLETED     = "checkout_completed",   _("Checkout Completed")
    CHECKOUT_ABANDONED     = "checkout_abandoned",   _("Checkout Abandoned")

    # ── AI Measurement ────────────────────────────────────────────────
    MEASUREMENT_CREATED    = "measurement_created",  _("Measurement Created")
    MEASUREMENT_UPDATED    = "measurement_updated",  _("Measurement Updated")
    MEASUREMENT_DELETED    = "measurement_deleted",  _("Measurement Deleted")
    AI_ANALYSIS_STARTED    = "ai_analysis_started",  _("AI Analysis Started")
    AI_ANALYSIS_COMPLETED  = "ai_analysis_completed",_("AI Analysis Completed")
    AI_ANALYSIS_FAILED     = "ai_analysis_failed",   _("AI Analysis Failed")

    # ── System ───────────────────────────────────────────────────────
    SYSTEM_ERROR           = "system_error",         _("System Error")
    API_CALL               = "api_call",             _("API Call")
    WEBHOOK_RECEIVED       = "webhook_received",     _("Webhook Received")
    CELERY_TASK_FAILED     = "celery_task_failed",   _("Celery Task Failed")


class SeverityLevel(models.TextChoices):
    DEBUG    = "debug",    _("Debug")
    INFO     = "info",     _("Info")
    WARNING  = "warning",  _("Warning")
    ERROR    = "error",    _("Error")
    CRITICAL = "critical", _("Critical")


# ================================================================
# AUDIT EVENT LOG
# ================================================================

class AuditEventLog(models.Model):
    """
    Structured, high-value business event log for the Fashionistar platform.

    Columns
    -------
    event_type      Business event (login_success, password_changed, …)
    event_category  Grouping (authentication, security, admin, …)
    severity        info / warning / error / critical
    action          Human-readable description of what happened
    actor           FK to UnifiedUser (null-safe: survives user deletion)
    actor_email     Snapshot of actor email at event time
    ip_address      Client IP (or None for system events)
    user_agent      Full UA string
    device_type     desktop / mobile / tablet / api / unknown
    browser_family  Chrome / Firefox / Safari / …
    os_family       Windows / macOS / Android / iOS / …
    country         IP-geolocated country (if available)
    resource_type   Affected model class name (e.g. 'UnifiedUser')
    resource_id     Affected object PK
    request_method  HTTP method (GET / POST / PUT / DELETE)
    request_path    API endpoint path
    response_status HTTP status code
    duration_ms     Handler execution time in milliseconds
    old_values      Before-state snapshot (JSON) — enables forensic restore
    new_values      After-state snapshot (JSON)
    metadata        Extra context (arbitrary JSON)
    error_message   Error text if event represents a failure
    is_compliance   Flags events requiring compliance audit trail
    retention_days  How long to keep this row (default 7 years = 2555 days)
    created_at      Auto-set immutable timestamp

    Design
    ------
    * Rows are NEVER updated or deleted by application code — immutable audit trail.
    * Writes are always async (direct Celery ``apply_async()`` dispatch) to avoid
      blocking the HTTP request path.
    * actor_email snapshot ensures the audit trail is preserved even after
      GDPR hard-delete of the live account.
    """

    # ── PK ────────────────────────────────────────────────────────────
    id = models.UUIDField(
        primary_key=True,
        default=uuid6.uuid7,
        editable=False,
    )

    # ── Event classification ──────────────────────────────────────────
    event_type = models.CharField(
        max_length=60,
        choices=EventType.choices,
        db_index=True,
        help_text="Type of business event.",
    )
    event_category = models.CharField(
        max_length=60,
        choices=EventCategory.choices,
        db_index=True,
        help_text="Event category / domain.",
    )
    severity = models.CharField(
        max_length=20,
        choices=SeverityLevel.choices,
        default=SeverityLevel.INFO,
        db_index=True,
        help_text="Severity level of the event.",
    )
    action = models.TextField(
        help_text="Human-readable description of what happened.",
    )

    # ── Actor (who) ───────────────────────────────────────────────────
    actor = models.ForeignKey(
        "authentication.UnifiedUser",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_events",
        help_text="User who triggered this event. Null for unauthenticated/system events.",
    )
    actor_email = models.EmailField(
        null=True,
        blank=True,
        db_index=True,
        help_text="Email snapshot at event time — preserved even if the user is deleted.",
    )

    # ── Request context ───────────────────────────────────────────────
    ip_address = models.GenericIPAddressField(
        null=True,
        blank=True,
        db_index=True,
        help_text="Client IP address.",
    )
    user_agent = models.TextField(
        null=True,
        blank=True,
        help_text="Full User-Agent string.",
    )
    device_type = models.CharField(
        max_length=30,
        null=True,
        blank=True,
        help_text="desktop / mobile / tablet / api / unknown",
    )
    browser_family = models.CharField(
        max_length=80,
        null=True,
        blank=True,
        help_text="Browser family (Chrome, Firefox, Safari, …)",
    )
    os_family = models.CharField(
        max_length=80,
        null=True,
        blank=True,
        help_text="OS family (Windows, macOS, Android, iOS, …)",
    )
    country = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        db_index=True,
        help_text="GeoIP country or request origin (if resolved).",
    )

    # ── Distributed tracing ───────────────────────────────────────────
    correlation_id = models.CharField(
        max_length=64,
        null=True,
        blank=True,
        db_index=True,
        help_text="Unique request / trace ID for cross-service correlation.",
    )

    # ── Resource affected ─────────────────────────────────────────────
    resource_type = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        db_index=True,
        help_text="Model class name of the affected resource (e.g. 'UnifiedUser').",
    )
    resource_id = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        db_index=True,
        help_text="PK of the affected resource.",
    )

    # ── HTTP context ──────────────────────────────────────────────────
    request_method = models.CharField(
        max_length=10,
        null=True,
        blank=True,
        help_text="HTTP method (GET, POST, PUT, PATCH, DELETE).",
    )
    request_path = models.CharField(
        max_length=500,
        null=True,
        blank=True,
        help_text="Request URL path.",
    )
    response_status = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        help_text="HTTP response status code.",
    )
    duration_ms = models.FloatField(
        null=True,
        blank=True,
        help_text="Handler execution time in milliseconds.",
    )

    # ── Diff / forensic restore ───────────────────────────────────────
    old_values = models.JSONField(
        null=True,
        blank=True,
        help_text="Before-state snapshot (sanitised — no raw passwords).",
    )
    new_values = models.JSONField(
        null=True,
        blank=True,
        help_text="After-state snapshot.",
    )
    metadata = models.JSONField(
        null=True,
        blank=True,
        help_text="Extra contextual data (arbitrary key-value).",
    )

    # ── Error / failure ───────────────────────────────────────────────
    error_message = models.TextField(
        null=True,
        blank=True,
        help_text="Error message if event represents a failure.",
    )

    # ── Compliance ────────────────────────────────────────────────────
    is_compliance = models.BooleanField(
        default=False,
        db_index=True,
        help_text="Flag events that must be retained for compliance audit.",
    )
    retention_days = models.PositiveIntegerField(
        default=2555,  # 7 years — financial + GDPR compliance
        help_text="Days to retain this log entry.",
    )

    # ── Immutable timestamp ───────────────────────────────────────────
    created_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
        help_text="When this event was recorded. Immutable.",
    )

    class Meta:
        verbose_name = "Audit Event Log"
        verbose_name_plural = "Audit Event Logs"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["-created_at"],               name="idx_ael_created"),
            models.Index(fields=["actor", "-created_at"],      name="idx_ael_actor"),
            models.Index(fields=["event_type", "-created_at"], name="idx_ael_etype"),
            models.Index(fields=["event_category", "-created_at"], name="idx_ael_ecat"),
            models.Index(fields=["severity", "-created_at"],   name="idx_ael_sev"),
            models.Index(fields=["ip_address", "-created_at"], name="idx_ael_ip"),
            models.Index(fields=["resource_type", "resource_id"], name="idx_ael_resource"),
            models.Index(fields=["is_compliance", "-created_at"],  name="idx_ael_compliance"),
            models.Index(fields=["actor_email", "-created_at"], name="idx_ael_email"),
            models.Index(fields=["correlation_id"],             name="idx_ael_corr"),
            models.Index(fields=["country", "-created_at"],     name="idx_ael_country"),
        ]

    def __str__(self):
        actor = self.actor_email or "system"
        return f"[{self.event_type}] {actor} @ {self.created_at:%Y-%m-%d %H:%M:%S}"

    @property
    def is_security_event(self) -> bool:
        return self.event_category in (
            EventCategory.SECURITY,
            EventCategory.AUTHENTICATION,
        ) or self.severity in (SeverityLevel.ERROR, SeverityLevel.CRITICAL)

    @property
    def is_failure(self) -> bool:
        return self.event_type in (
            EventType.LOGIN_FAILED,
            EventType.LOGIN_BLOCKED,
            EventType.REGISTER_FAILED,
            EventType.SYSTEM_ERROR,
            EventType.CELERY_TASK_FAILED,
        )
