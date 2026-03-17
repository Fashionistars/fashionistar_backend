"""
apps/audit_logs — Enterprise audit log application.

Two-layer audit coverage:
  Layer 1: django-auditlog LogEntry — auto-tracks every model field change
  Layer 2: AuditEventLog — structured business events with full request context
"""
