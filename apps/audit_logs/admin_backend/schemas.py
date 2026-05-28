# apps/audit_logs/admin_backend/schemas.py
from __future__ import annotations
from datetime import datetime
from uuid import UUID
from typing import Optional, Dict, Any
from ninja import Schema

class AdminAuditEventSchema(Schema):
    id: UUID
    event_type: str
    event_category: str
    severity: str
    action: str
    actor_email: Optional[str] = None
    actor_role: Optional[str] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    device_type: Optional[str] = None
    browser_family: Optional[str] = None
    os_family: Optional[str] = None
    country: Optional[str] = None
    country_code: Optional[str] = None
    city: Optional[str] = None
    client_device_id: Optional[str] = None
    client_timezone: Optional[str] = None
    client_locale: Optional[str] = None
    client_platform: Optional[str] = None
    correlation_id: Optional[str] = None
    resource_type: Optional[str] = None
    resource_id: Optional[str] = None
    request_method: Optional[str] = None
    request_path: Optional[str] = None
    response_status: Optional[int] = None
    duration_ms: Optional[float] = None
    old_values: Optional[Dict[str, Any]] = None
    new_values: Optional[Dict[str, Any]] = None
    metadata: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    is_compliance: bool
    retention_days: int
    created_at: datetime
