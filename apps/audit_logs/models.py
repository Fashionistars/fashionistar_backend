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
    - NEVER blocks the HTTP request — writes go via Celery apply_async() dispatch
    - NEVER raises exceptions to callers — all errors are logged as WARNING
    - 7-year retention for financial compliance (configurable per-event)
    - Immutable once written (no update/delete permission in admin)
    - actor_email snapshot survives even if UnifiedUser is hard-deleted
    - legal_hold=True rows are NEVER deleted by any cleanup path (PCI-DSS freeze)
    - data_subject_id links GDPR Subject Access Requests to raw audit rows
    - tenant_id enables future multi-tenant isolation without a DB schema split

Phase 9 Fields (2026 GDPR/NDPR/PCI-DSS compliance expansion):
    request_size_bytes  — Request payload size for anomaly detection
    response_size_bytes — Response size for bandwidth auditing
    tls_version         — TLS version string for security compliance (TLSv1.3, etc.)
    session_fingerprint — SHA-256 of device+browser signature for session correlation
    api_version         — API version extracted from path (/v1/, /v2/, etc.)
    tenant_id           — UUIDField for future multi-tenant partition expansion
    legal_hold          — Prevents deletion by any cleanup task or management command
    data_subject_id     — GDPR data-subject reference UUID (maps to UnifiedUser.pk)
    geo_country_code    — ISO 3166-1 alpha-2 from GeoIP (mirrors existing country_code)
    geo_city            — City from GeoIP (mirrors existing city field)"""

import logging
import uuid6

from django.db import models
from django.utils.translation import gettext_lazy as _

logger = logging.getLogger(__name__)


# ================================================================
# CHOICES
# ================================================================

class EventCategory(models.TextChoices):
    """Top-level domain groupings for audit events across all 19 apps."""

    AUTHENTICATION   = "authentication",    _("Authentication")
    AUTHORIZATION    = "authorization",     _("Authorization")
    ACCOUNT          = "account",           _("Account Management")
    PROFILE          = "profile",           _("Profile")
    SECURITY         = "security",          _("Security")
    ADMIN            = "admin",             _("Admin Action")
    DATA_ACCESS      = "data_access",       _("Data Access")
    DATA_MODIFICATION= "data_modification", _("Data Modification")
    SYSTEM           = "system",            _("System")
    NOTIFICATION     = "notification",      _("Notification")
    COMPLIANCE       = "compliance",        _("Compliance")
    ORDER            = "order",             _("Order")
    PAYMENT          = "payment",           _("Payment")
    CART             = "cart",              _("Cart & Checkout")
    MEASUREMENT      = "measurement",       _("AI Measurement")
    # ── New domains (Wave A consolidation) ────────────────────────────
    WALLET           = "wallet",            _("Wallet & Ledger")
    KYC              = "kyc",               _("KYC & Identity")
    VENDOR           = "vendor",            _("Vendor")
    CATALOG          = "catalog",           _("Catalog & Products")
    SUPPORT          = "support",           _("Customer Support")
    CHAT             = "chat",              _("Chat & Messaging")
    TRANSACTIONS     = "transactions",      _("Transactions & Ledger")
    PROVIDER         = "provider",          _("Payment Providers")
    CLIENT           = "client",            _("Client / Consumer")
    SETTINGS         = "settings",          _("Platform Settings")
    CHATBOT          = "chatbot",           _("Chatbot & AI Assistant")
    SEARCH           = "search",            _("Search & Discovery")
    ANALYTICS        = "analytics",         _("Analytics & Telemetry")
    DEVOPS           = "devops",            _("DevOps & Infrastructure")


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
    # ── Aliases used by Wave H audit hooks ──
    USER_REGISTERED        = "user_registered",      _("User Registered")
    REGISTRATION_FAILED    = "registration_failed",  _("Registration Failed (Hook)")
    # First-ever OTP verification + JWT auto-issuance (distinct from EMAIL_VERIFIED
    # which is a profile event). Required for CBN/NDPR auth compliance trail.
    ACCOUNT_VERIFIED       = "account_verified",     _("Account Verified (OTP + Auto-Login)")

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
    PASSWORD_CHANGED       = "password_changed",       _("Password Changed")
    PASSWORD_RESET_REQUEST   = "password_reset_request",   _("Password Reset Requested")
    PASSWORD_RESET_DONE      = "password_reset_done",      _("Password Reset Completed")
    PASSWORD_RESET_FAILED    = "password_reset_failed",    _("Password Reset Failed")
    MFA_ENABLED            = "mfa_enabled",          _("MFA Enabled")
    MFA_DISABLED           = "mfa_DISABLED",         _("MFA Disabled")
    OTP_GENERATED          = "otp_generated",        _("OTP Generated")
    OTP_VERIFIED           = "otp_verified",         _("OTP Verified")
    OTP_FAILED             = "otp_failed",           _("OTP Verification Failed")
    BIOMETRIC_REGISTERED   = "biometric_registered", _("Biometric Device Registered")
    BIOMETRIC_AUTH_SUCCESS = "biometric_auth_success",_("Biometric Authentication Success")
    BIOMETRIC_AUTH_FAILED  = "biometric_auth_failed", _("Biometric Authentication Failed")
    SUSPICIOUS_ACTIVITY    = "suspicious_activity",  _("Suspicious Activity")
    IP_BLOCKED             = "ip_blocked",           _("IP Blocked")
    FAILED_LOGINS_EXCEEDED = "failed_logins_exceeded",_("Failed Login Limit Exceeded")

    # ── Session lifecycle events ───────────────────────────────────────────
    SESSION_REVOKED     = "session_revoked",     _("Single Session Revoked")
    SESSION_REVOKE_ALL  = "session_revoke_all",  _("All Other Sessions Revoked")

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
    CART_ITEM_ADDED        = "cart_item_added",       _("Cart Item Added")
    CART_ITEM_REMOVED      = "cart_item_removed",     _("Cart Item Removed")
    CHECKOUT_INITIATED     = "checkout_initiated",    _("Checkout Initiated")
    CHECKOUT_STARTED       = "checkout_started",      _("Checkout Started")
    CHECKOUT_COMPLETED     = "checkout_completed",    _("Checkout Completed")
    CHECKOUT_ABANDONED     = "checkout_abandoned",    _("Checkout Abandoned")
    COUPON_APPLIED         = "coupon_applied",        _("Coupon Applied")

    # ── AI Measurement ────────────────────────────────────────────────
    MEASUREMENT_CREATED    = "measurement_created",  _("Measurement Created")
    MEASUREMENT_UPDATED    = "measurement_updated",  _("Measurement Updated")
    MEASUREMENT_DELETED    = "measurement_deleted",  _("Measurement Deleted")
    AI_ANALYSIS_STARTED    = "ai_analysis_started",  _("AI Analysis Started")
    AI_ANALYSIS_COMPLETED  = "ai_analysis_completed",_("AI Analysis Completed")
    AI_ANALYSIS_FAILED     = "ai_analysis_failed",   _("AI Analysis Failed")

    # ── Wallet & Ledger ───────────────────────────────────────────────
    WALLET_TOPUP               = "wallet_topup",               _("Wallet Top-Up")
    WALLET_WITHDRAWAL          = "wallet_withdrawal",          _("Wallet Withdrawal")
    WALLET_WITHDRAWAL_REQUESTED= "wallet_withdrawal_requested",_("Wallet Withdrawal Requested")
    WALLET_ESCROW_HOLD         = "wallet_escrow_hold",         _("Escrow Hold")
    WALLET_ESCROW_RELEASE      = "wallet_escrow_release",      _("Escrow Released")
    WALLET_ESCROW_REFUNDED     = "wallet_escrow_refunded",     _("Escrow Refunded")
    WALLET_CREATED             = "wallet_created",             _("Wallet Created")
    WALLET_PIN_SET             = "wallet_pin_set",             _("Wallet PIN Set")
    WALLET_PIN_CHANGED         = "wallet_pin_changed",         _("Wallet PIN Changed")
    WALLET_TRANSFER            = "wallet_transfer",            _("Wallet Transfer")

    # ── KYC & Identity ────────────────────────────────────────────────
    KYC_SUBMITTED          = "kyc_submitted",         _("KYC Submitted")
    KYC_VERIFIED           = "kyc_verified",          _("KYC Verified")
    KYC_APPROVED           = "kyc_approved",          _("KYC Approved")
    KYC_REJECTED           = "kyc_rejected",          _("KYC Rejected")
    KYC_DOCUMENT_UPLOADED  = "kyc_document_uploaded", _("KYC Document Uploaded")
    KYC_WEBHOOK            = "kyc_webhook",           _("KYC Webhook Received")
    KYC_RETRY              = "kyc_retry",             _("KYC Retry")
    BVN_VERIFIED           = "bvn_verified",          _("BVN Verified")
    NIN_VERIFIED           = "nin_verified",          _("NIN Verified")

    # ── Vendor ────────────────────────────────────────────────────────
    VENDOR_REGISTERED         = "vendor_registered",          _("Vendor Registered")
    VENDOR_PROVISIONED        = "vendor_provisioned",          _("Vendor Provisioned")
    VENDOR_PROFILE_UPDATED    = "vendor_profile_updated",      _("Vendor Profile Updated")
    VENDOR_KYC_GATE_PASSED    = "vendor_kyc_gate_passed",      _("Vendor KYC Gate Passed")
    VENDOR_COMMISSION_CHANGED = "vendor_commission_changed",   _("Vendor Commission Changed")
    VENDOR_SUSPENDED          = "vendor_suspended",            _("Vendor Suspended")
    VENDOR_RESTORED           = "vendor_restored",             _("Vendor Restored")

    # ── Catalog & Products ────────────────────────────────────────────
    PRODUCT_CREATED        = "product_created",       _("Product Created")
    PRODUCT_UPDATED        = "product_updated",       _("Product Updated")
    PRODUCT_DELETED        = "product_deleted",       _("Product Deleted")
    PRODUCT_PUBLISHED      = "product_published",     _("Product Published")
    PRODUCT_UNPUBLISHED    = "product_unpublished",   _("Product Unpublished")
    REVIEW_CREATED         = "review_created",        _("Review Created")
    REVIEW_POSTED          = "review_posted",         _("Review Posted")
    REVIEW_FLAGGED         = "review_flagged",        _("Review Flagged")
    CLOUDINARY_WEBHOOK     = "cloudinary_webhook",    _("Cloudinary Webhook")

    # ── Catalog: Collections, Brands, Categories ──────────────────────
    COLLECTION_CREATED     = "collection_created",    _("Collection Created")
    COLLECTION_UPDATED     = "collection_updated",    _("Collection Updated")
    COLLECTION_DELETED     = "collection_deleted",    _("Collection Deleted")
    BRAND_CREATED          = "brand_created",         _("Brand Created")
    BRAND_UPDATED          = "brand_updated",         _("Brand Updated")
    BRAND_DELETED          = "brand_deleted",         _("Brand Deleted")
    CATEGORY_CREATED       = "category_created",      _("Category Created")
    CATEGORY_UPDATED       = "category_updated",      _("Category Updated")
    CATEGORY_DELETED       = "category_deleted",      _("Category Deleted")
    BLOG_POST_CREATED      = "blog_post_created",     _("Blog Post Created")
    BLOG_POST_UPDATED      = "blog_post_updated",     _("Blog Post Updated")
    BLOG_POST_DELETED      = "blog_post_deleted",     _("Blog Post Deleted")

    # ── Customer Support ──────────────────────────────────────────────
    TICKET_CREATED         = "ticket_created",        _("Support Ticket Created")
    TICKET_ESCALATED       = "ticket_escalated",      _("Support Ticket Escalated")
    TICKET_RESOLVED        = "ticket_resolved",       _("Support Ticket Resolved")
    TICKET_CLOSED          = "ticket_closed",         _("Support Ticket Closed")
    SLA_BREACH             = "sla_breach",            _("SLA Breach")

    # ── Chat & Messaging ──────────────────────────────────────────────
    CHAT_STARTED           = "chat_started",          _("Chat Conversation Started")
    CHAT_MESSAGE_FLAGGED   = "chat_message_flagged",  _("Chat Message Flagged")
    CONVERSATION_STARTED   = "conversation_started",  _("Conversation Started")
    MESSAGE_SENT           = "message_sent",          _("Message Sent")
    MESSAGE_DELETED        = "message_deleted",       _("Message Deleted")
    WEBSOCKET_CONNECTED    = "websocket_connected",   _("WebSocket Connected")
    WEBSOCKET_DISCONNECTED = "websocket_disconnected",_("WebSocket Disconnected")

    # ── Chatbot & AI Assistant ─────────────────────────────────────────
    CHATBOT_MESSAGE_SENT           = "chatbot_message_sent",           _("Chatbot Message Sent")
    CHATBOT_SESSION_STARTED        = "chatbot_session_started",        _("Chatbot Session Started")
    CHATBOT_SESSION_ENDED          = "chatbot_session_ended",          _("Chatbot Session Ended")
    CHATBOT_CONVERSATION_CREATED   = "chatbot_conversation_created",   _("Chatbot Conversation Created")
    CHATBOT_CONVERSATION_UPDATED   = "chatbot_conversation_updated",   _("Chatbot Conversation Updated")
    CHATBOT_RESPONSE_TRIGGERED     = "chatbot_response_triggered",     _("Chatbot Predefined Response Triggered")
    CHATBOT_AI_RESPONSE_GENERATED = "chatbot_ai_response_generated", _("Chatbot AI Response Generated")
    CHATBOT_STYLE_ASSESSMENT_STARTED = "chatbot_style_assessment_started", _("Style Assessment Started")
    CHATBOT_STYLE_ASSESSMENT_COMPLETED = "chatbot_style_assessment_completed", _("Style Assessment Completed")
    CHATBOT_APPOINTMENT_REQUESTED  = "chatbot_appointment_requested",  _("Bespoke Tailoring Appointment Requested")

    # ── Search & Discovery ─────────────────────────────────────────────────
    SEARCH_QUERY_EXECUTED      = "search_query_executed",      _("Search Query Executed")
    SEARCH_RESULT_RETURNED     = "search_result_returned",     _("Search Results Returned")
    SEARCH_ZERO_RESULTS        = "search_zero_results",        _("Search Returned Zero Results")
    SEARCH_CACHE_HIT           = "search_cache_hit",           _("Search Cache Hit")
    SEARCH_CACHE_MISS          = "search_cache_miss",          _("Search Cache Miss")
    SEARCH_INDEX_UPDATED       = "search_index_updated",       _("Search Index Updated")
    SEARCH_INDEX_FAILED        = "search_index_failed",        _("Search Index Operation Failed")
    SEARCH_FILTER_APPLIED      = "search_filter_applied",      _("Search Filter Applied")
    SEARCH_SORT_APPLIED        = "search_sort_applied",        _("Search Sort Applied")
    SEARCH_PAGINATION_APPLIED = "search_pagination_applied", _("Search Pagination Applied")

    # ── Analytics & Telemetry ───────────────────────────────────────────────
    ANALYTICS_METRIC_RECORDED      = "analytics_metric_recorded",      _("Analytics Metric Recorded")
    ANALYTICS_USER_ACTIVITY_LOGGED  = "analytics_user_activity_logged",  _("User Activity Logged")
    ANALYTICS_PERFORMANCE_TRACKED   = "analytics_performance_tracked",   _("Performance Metric Tracked")
    ANALYTICS_BUSINESS_METRIC_CALC  = "analytics_business_metric_calc",  _("Business Metric Calculated")
    ANALYTICS_ALERT_RULE_EVALUATED = "analytics_alert_rule_evaluated", _("Alert Rule Evaluated")
    ANALYTICS_ALERT_TRIGGERED       = "analytics_alert_triggered",       _("Alert Triggered")
    ANALYTICS_ALERT_RESOLVED        = "analytics_alert_resolved",        _("Alert Resolved")
    ANALYTICS_DASHBOARD_VIEWED      = "analytics_dashboard_viewed",      _("Analytics Dashboard Viewed")
    ANALYTICS_REPORT_GENERATED      = "analytics_report_generated",      _("Analytics Report Generated")
    ANALYTICS_DATA_EXPORTED         = "analytics_data_exported",         _("Analytics Data Exported")

    # ── DevOps & Infrastructure ───────────────────────────────────────────────
    DEVOPS_ENVIRONMENT_CREATED     = "devops_environment_created",     _("Environment Created")
    DEVOPS_ENVIRONMENT_UPDATED     = "devops_environment_updated",     _("Environment Updated")
    DEVOPS_ENVIRONMENT_DELETED     = "devops_environment_deleted",     _("Environment Deleted")
    DEVOPS_SECRET_CREATED          = "devops_secret_created",          _("Secret Created")
    DEVOPS_SECRET_UPDATED          = "devops_secret_updated",          _("Secret Updated")
    DEVOPS_SECRET_DELETED          = "devops_secret_deleted",          _("Secret Deleted")
    DEVOPS_SECRET_ROTATED          = "devops_secret_rotated",          _("Secret Rotated")
    DEVOPS_DEPLOYMENT_STARTED      = "devops_deployment_started",      _("Deployment Started")
    DEVOPS_DEPLOYMENT_SUCCESS      = "devops_deployment_success",      _("Deployment Success")
    DEVOPS_DEPLOYMENT_FAILED       = "devops_deployment_failed",       _("Deployment Failed")
    DEVOPS_DEPLOYMENT_ROLLED_BACK  = "devops_deployment_rolled_back",  _("Deployment Rolled Back")
    DEVOPS_HEALTH_CHECK_PASSED     = "devops_health_check_passed",     _("Health Check Passed")
    DEVOPS_HEALTH_CHECK_FAILED     = "devops_health_check_failed",     _("Health Check Failed")
    DEVOPS_SERVICE_MONITORING_ENABLED = "devops_service_monitoring_enabled", _("Service Monitoring Enabled")
    DEVOPS_SERVICE_MONITORING_DISABLED = "devops_service_monitoring_disabled", _("Service Monitoring Disabled")
    DEVOPS_INFRASTRUCTURE_SCALING  = "devops_infrastructure_scaling",  _("Infrastructure Scaling")
    DEVOPS_CONFIG_CHANGE_APPLIED   = "devops_config_change_applied",   _("Configuration Change Applied")

    # ── Transactions & Ledger ─────────────────────────────────────────
    LEDGER_ENTRY_CREATED   = "ledger_entry_created",  _("Ledger Entry Created")
    COMMISSION_CALCULATED  = "commission_calculated", _("Commission Calculated")
    PAYOUT_INITIATED       = "payout_initiated",      _("Payout Initiated")
    PAYOUT_SUCCESS         = "payout_success",        _("Payout Success")
    PAYOUT_FAILED          = "payout_failed",         _("Payout Failed")
    TRANSACTION_CREATED    = "transaction_created",   _("Transaction Created")

    # ── Provider / Gateway ────────────────────────────────────────────
    PROVIDER_CONFIG_CHANGED    = "provider_config_changed",    _("Provider Config Changed")
    PROVIDER_WEBHOOK_RECEIVED  = "provider_webhook_received",  _("Provider Webhook Received")
    PROVIDER_WEBHOOK_FAILED    = "provider_webhook_failed",    _("Provider Webhook Failed")
    PROVIDER_HEALTH_CHECK      = "provider_health_check",      _("Provider Health Check")
    PROVIDER_SWITCHED          = "provider_switched",          _("Provider Switched")
    CIRCUIT_BREAKER_OPENED     = "circuit_breaker_opened",     _("Circuit Breaker Opened")
    CIRCUIT_BREAKER_CLOSED     = "circuit_breaker_closed",     _("Circuit Breaker Closed")

    # ── Client / Consumer ─────────────────────────────────────────────
    CLIENT_REGISTERED      = "client_registered",    _("Client Registered")
    CLIENT_ADDRESS_ADDED   = "client_address_added", _("Client Address Added")
    CLIENT_MEASUREMENT_LINKED = "client_measurement_linked", _("Measurement Linked")

    # ── Notification ──────────────────────────────────────────────────
    NOTIFICATION_SENT      = "notification_sent",    _("Notification Sent")
    NOTIFICATION_FAILED    = "notification_failed",  _("Notification Delivery Failed")

    # ── Platform Settings ─────────────────────────────────────────────
    SETTINGS_UPDATED       = "settings_updated",     _("Platform Settings Updated")
    # SETTINGS_CHANGED already declared in Admin section (line ~104) — reused there
    FEATURE_FLAG_CHANGED   = "feature_flag_changed", _("Feature Flag Changed")

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

    Columns (core)
    ---------------
    event_type          Business event (login_success, password_changed, …)
    event_category      Grouping (authentication, security, admin, …)
    severity            info / warning / error / critical
    action              Human-readable description of what happened
    actor               FK to UnifiedUser (null-safe: survives user deletion)
    actor_email         Snapshot of actor email at event time
    ip_address          Client IP (or None for system events)
    user_agent          Full UA string
    device_type         desktop / mobile / tablet / api / unknown
    browser_family      Chrome / Firefox / Safari / …
    os_family           Windows / macOS / Android / iOS / …
    country             IP-geolocated country name (full)
    country_code        ISO 3166-1 alpha-2 (2-char, e.g. 'NG', 'US')
    city                GeoIP resolved city name
    resource_type       Affected model class name (e.g. 'UnifiedUser')
    resource_id         Affected object PK
    request_method      HTTP method (GET / POST / PUT / DELETE)
    request_path        API endpoint path
    response_status     HTTP status code
    duration_ms         Handler execution time in milliseconds
    old_values          Before-state snapshot (JSON) — enables forensic restore
    new_values          After-state snapshot (JSON)
    metadata            Extra context (arbitrary JSON)
    error_message       Error text if event represents a failure
    is_compliance       Flags events requiring compliance audit trail
    retention_days      How long to keep this row (default 7 years = 2555 days)
    created_at          Auto-set immutable timestamp

    Phase 9 Compliance Columns (2026 GDPR/NDPR/PCI-DSS)
    -----------------------------------------------------
    request_size_bytes  Incoming payload size in bytes (anomaly detection)
    response_size_bytes Outgoing payload size in bytes (bandwidth audit)
    tls_version         TLS version negotiated for this request (TLSv1.3, etc.)
    session_fingerprint SHA-256 of browser device signature for cross-session linking
    api_version         API version extracted from path (/v1/, /v2/, …)
    tenant_id           UUID for future multi-tenant expansion (null for now)
    legal_hold          True = this row is frozen; NEVER deleted by any cleanup task
    data_subject_id     GDPR data-subject UUID — maps to the affected UnifiedUser.pk
    geo_country_code    ISO 3166-1 alpha-2 from GeoIP enrichment (2-char)
    geo_city            City from GeoIP enrichment

    Design
    ------
    * Rows are NEVER updated or deleted by application code — immutable audit trail.
    * Writes are always async (direct Celery ``apply_async()`` dispatch) to avoid
      blocking the HTTP request path.
    * actor_email snapshot ensures the audit trail is preserved even after
      GDPR hard-delete of the live account.
    * legal_hold=True overrides ALL retention policies — these rows survive forever
      until a superuser explicitly clears the flag via Django admin.
    * data_subject_id enables GDPR Subject Access Request (SAR) queries without
      a FK join — the UnifiedUser.pk is denormalised here for performance and
      survives a hard-delete of the UnifiedUser row.
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
    actor_role = models.CharField(
        max_length=50,
        null=True,
        blank=True,
        db_index=True,
        help_text="Role/type snapshot of actor at event time (client, vendor, admin, system).",
    )
    session_id = models.CharField(
        max_length=128,
        null=True,
        blank=True,
        db_index=True,
        help_text="JWT jti or session key — enables grouping all events in one session.",
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
    country_code = models.CharField(
        max_length=3,
        null=True,
        blank=True,
        db_index=True,
        help_text="ISO 3166-1 alpha-2 country code (e.g. 'NG', 'GB', 'US').",
    )
    city = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        help_text="GeoIP resolved city.",
    )

    # ── Frontend-enriched device and geo context ──────────────────────────────
    # These fields are populated from X-Client-* HTTP headers sent by the
    # frontend audit header builder (fashionista_frontend/src/lib/audit-headers.ts).
    # They ENRICH server-derived values — they do NOT replace them.
    #
    # WHY DUAL-SOURCE:
    #   Server-derived: REMOTE_ADDR, HTTP_USER_AGENT → good for API/webhook requests
    #   Frontend-sourced: X-Device-ID, X-Client-Timezone → accurate even behind VPN/NAT
    #   Together: 95%+ field completeness target for all audit rows
    client_device_id = models.CharField(
        max_length=64,
        null=True,
        blank=True,
        db_index=True,
        help_text=(
            "Stable UUID v4 generated by the browser frontend. Persisted in localStorage "
            "so the same device ID appears across sessions. Enables cross-session device "
            "correlation — e.g. detecting an account accessed from a new device. "
            "Source: X-Device-ID request header."
        ),
    )
    client_timezone = models.CharField(
        max_length=64,
        null=True,
        blank=True,
        help_text=(
            "IANA timezone identifier from the client browser (e.g. 'Africa/Lagos', "
            "'Europe/London'). More accurate than IP-based timezone inference, especially "
            "when the user is on a VPN or behind a NAT. "
            "Source: X-Client-Timezone request header → Intl.DateTimeFormat()."
        ),
    )
    client_locale = models.CharField(
        max_length=20,
        null=True,
        blank=True,
        help_text=(
            "Browser language/locale (e.g. 'en-NG', 'en-US', 'yo-NG'). "
            "Used for locale-specific fraud pattern detection and user experience analytics. "
            "Source: X-Client-Locale request header → navigator.language."
        ),
    )
    client_platform = models.CharField(
        max_length=80,
        null=True,
        blank=True,
        help_text=(
            "OS platform as reported by the browser (e.g. 'Win32', 'MacIntel', 'Linux armv8l'). "
            "Modern browsers use navigator.userAgentData.platform; legacy browsers fall back to "
            "navigator.platform. Enriches the server-parsed os_family field. "
            "Source: X-Client-Platform request header."
        ),
    )
    client_geo_lat = models.DecimalField(
        max_digits=10,
        decimal_places=7,
        null=True,
        blank=True,
        help_text=(
            "GPS latitude from the browser Geolocation API. "
            "Only populated when the user has EXPLICITLY granted geolocation permission. "
            "Never populated without user consent — the frontend only sends this header "
            "after confirming permission state === 'granted'. "
            "Source: X-Client-Geo-Lat request header."
        ),
    )
    client_geo_lng = models.DecimalField(
        max_digits=10,
        decimal_places=7,
        null=True,
        blank=True,
        help_text=(
            "GPS longitude from the browser Geolocation API. "
            "See client_geo_lat for consent and accuracy notes. "
            "Source: X-Client-Geo-Lng request header."
        ),
    )
    client_geo_accuracy_m = models.FloatField(
        null=True,
        blank=True,
        help_text=(
            "GPS position accuracy in metres. "
            "< 50m indicates high-accuracy mobile GPS. "
            "> 5000m indicates IP-based approximation or WiFi triangulation. "
            "Use accuracy to qualify any geographic assertions made from this data. "
            "Source: X-Client-Geo-Accuracy request header."
        ),
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
        help_text="Days to retain this log entry. -1 = infinite.",
    )

    # ── Phase 9: 2026 GDPR/NDPR/PCI-DSS Compliance Fields ────────────
    # These fields extend AuditEventLog to satisfy the 2026 regulatory
    # framework: GDPR Art. 30 (records of processing activities),
    # NDPR § 2.1 (data security obligations), and PCI-DSS v4 Req. 10
    # (audit log integrity and payload capture requirements).

    request_size_bytes = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text=(
            "Size of the incoming HTTP request body in bytes. "
            "Used for anomaly detection — unusually large requests may "
            "indicate data exfiltration attempts or malformed payload attacks."
        ),
    )
    response_size_bytes = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text=(
            "Size of the outgoing HTTP response body in bytes. "
            "Used for bandwidth auditing and detecting abnormally large "
            "data exports (potential GDPR data breach indicator)."
        ),
    )
    tls_version = models.CharField(
        max_length=10,
        null=True,
        blank=True,
        help_text=(
            "TLS version negotiated for this request (e.g. 'TLSv1.3', 'TLSv1.2'). "
            "PCI-DSS v4 Req. 10.3 mandates logging transport security details. "
            "Populated from the 'SSL_PROTOCOL' server variable via Nginx/Gunicorn."
        ),
    )
    session_fingerprint = models.CharField(
        max_length=64,
        null=True,
        blank=True,
        db_index=True,
        help_text=(
            "SHA-256 fingerprint computed from the device+browser signature "
            "(User-Agent + Accept-Language + screen resolution + timezone). "
            "Enables cross-session device correlation for fraud detection without "
            "storing raw PII device identifiers. Populated by the frontend "
            "audit-headers builder via X-Session-Fingerprint header."
        ),
    )
    api_version = models.CharField(
        max_length=10,
        null=True,
        blank=True,
        db_index=True,
        help_text=(
            "API version extracted from the request path (e.g. 'v1', 'v2'). "
            "Enables per-version security and performance analysis. "
            "Auto-extracted from request_path by AuditContextMiddleware."
        ),
    )
    tenant_id = models.UUIDField(
        null=True,
        blank=True,
        db_index=True,
        help_text=(
            "Reserved for future multi-tenant expansion. When Fashionistar moves "
            "to a multi-tenant architecture, this field partitions audit rows by "
            "tenant without requiring a DB schema split. Currently null for all rows."
        ),
    )
    legal_hold = models.BooleanField(
        default=False,
        db_index=True,
        help_text=(
            "When True, this row is under legal hold and MUST NOT be deleted by "
            "any automated cleanup task, management command, or Celery beat job. "
            "Set by a superuser via Django admin when a row is subject to "
            "regulatory investigation, litigation, or CBN/SEC audit freeze. "
            "PCI-DSS v4 Req. 10.5: audit log records must be protected from modification."
        ),
    )
    data_subject_id = models.UUIDField(
        null=True,
        blank=True,
        db_index=True,
        help_text=(
            "UUID of the GDPR/NDPR data subject (typically UnifiedUser.pk). "
            "Denormalised here so it survives a hard-delete of the UnifiedUser row. "
            "Used to fulfil GDPR Art. 15 Subject Access Requests (SARs) and "
            "Art. 17 Right-to-Erasure queries without a live FK join. "
            "Populated automatically from actor.pk when is_compliance=True."
        ),
    )
    geo_country_code = models.CharField(
        max_length=2,
        null=True,
        blank=True,
        db_index=True,
        help_text=(
            "ISO 3166-1 alpha-2 country code from GeoIP enrichment "
            "(e.g. 'NG', 'GB', 'US'). Strictly 2-char for PCI-DSS compliant "
            "geographic segmentation. Distinct from country_code which may vary "
            "in length across GeoIP providers."
        ),
    )
    geo_city = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        help_text=(
            "City from GeoIP enrichment (e.g. 'Lagos', 'London'). "
            "Dedicated Phase 9 field for new compliance queries without "
            "mixing old and new GeoIP provider results."
        ),
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
            # ── Core query indexes ──────────────────────────────────────────────
            models.Index(fields=["-created_at"],                    name="idx_ael_created"),
            models.Index(fields=["actor", "-created_at"],           name="idx_ael_actor"),
            models.Index(fields=["event_type", "-created_at"],      name="idx_ael_etype"),
            models.Index(fields=["event_category", "-created_at"],  name="idx_ael_ecat"),
            models.Index(fields=["severity", "-created_at"],        name="idx_ael_sev"),
            models.Index(fields=["ip_address", "-created_at"],      name="idx_ael_ip"),
            models.Index(fields=["resource_type", "resource_id"],   name="idx_ael_resource"),
            models.Index(fields=["is_compliance", "-created_at"],   name="idx_ael_compliance"),
            models.Index(fields=["actor_email", "-created_at"],     name="idx_ael_email"),
            models.Index(fields=["correlation_id"],                  name="idx_ael_corr"),
            models.Index(fields=["country", "-created_at"],         name="idx_ael_country"),
            models.Index(fields=["country_code", "-created_at"],    name="idx_ael_country_code"),
            models.Index(fields=["actor_role", "-created_at"],      name="idx_ael_actor_role"),
            models.Index(fields=["session_id"],                      name="idx_ael_session"),
            # ── Phase 9: 2026 Compliance indexes ───────────────────────────────
            # GDPR SAR queries — find all rows for a specific data subject in O(log n)
            models.Index(
                fields=["data_subject_id", "-created_at"],
                name="idx_ael_data_subject",
            ),
            # Legal hold admin — surface frozen rows without full-table scan
            models.Index(
                fields=["legal_hold", "-created_at"],
                name="idx_ael_legal_hold",
            ),
            # Multi-tenant expansion — partition reads without FK joins
            models.Index(
                fields=["tenant_id", "-created_at"],
                name="idx_ael_tenant",
            ),
            # Session fingerprint — cross-session device correlation for fraud
            models.Index(
                fields=["session_fingerprint", "-created_at"],
                name="idx_ael_sess_fp",
            ),
            # API version + actor — per-version security segmentation
            models.Index(
                fields=["api_version", "actor_email"],
                name="idx_ael_api_actor",
            ),
            # Actor + time — fastest path for per-user audit timeline queries
            models.Index(
                fields=["actor", "-created_at"],
                name="idx_ael_actor_time",
                # NOTE: duplicate of idx_ael_actor above but named explicitly
                # for Phase 9 query profiling separation. Remove idx_ael_actor
                # in next migration if DBA confirms this is superseded.
            ),
        ]

    def __str__(self):
        actor = self.actor_email or "system"
        return f"[{self.event_type}] {actor} @ {self.created_at:%Y-%m-%d %H:%M:%S}"

    def save(self, *args, **kwargs):
        """
        E2 — IMMUTABILITY GUARD.

        AuditEventLog rows are append-only. Once written they can NEVER be
        updated — this is a core compliance requirement (PCI-DSS v4 Req. 10.5,
        GDPR Art. 30).

        Raises
        ------
        PermissionError
            If any code attempts to UPDATE (i.e., save an existing PK).
            Write operations ONLY succeed for new inserts (_state.adding=True).

        Note: admin.py already sets has_change_permission → False so the admin
        UI cannot call save() on existing rows. This guard is a second line of
        defense against programmatic tampering.

        Phase 9 note:
            legal_hold=True rows receive an ADDITIONAL check — they are excluded
            from ALL batch delete paths (cleanup_audit_logs Celery task and
            purge_audit_logs management command). See tasks.py and
            management/commands/purge_audit_logs.py for enforcement.
        """
        if not self._state.adding:
            raise PermissionError(
                "AuditEventLog records are immutable — updates are forbidden. "
                f"Attempted update on pk={self.pk}. "
                "Create a new AuditEventLog entry instead."
            )
        super().save(*args, **kwargs)

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
