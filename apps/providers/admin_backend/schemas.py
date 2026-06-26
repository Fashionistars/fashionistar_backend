# apps/providers/admin_backend/schemas.py
from datetime import datetime
from typing import Optional, Dict, Any
from ninja import Schema
from pydantic import UUID4

class BaseProviderConfigSchema(Schema):
    id: UUID4
    health_status: str
    last_health_check: Optional[datetime] = None
    circuit_state: str
    failure_count: int
    last_failure_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

class EmailProviderConfigSchema(BaseProviderConfigSchema):
    email_backend: str
    sender_email: str
    extra_config: Optional[Dict[str, Any]] = None

class SMSProviderConfigSchema(BaseProviderConfigSchema):
    sms_backend: str
    sender_id: str
    extra_config: Optional[Dict[str, Any]] = None

class KYCProviderConfigSchema(BaseProviderConfigSchema):
    provider_slug: str
    sandbox_mode: bool
    base_url: Optional[str] = None
    webhook_idempotency_ttl_seconds: int
    extra_config: Optional[Dict[str, Any]] = None

class CloudinaryProviderConfigSchema(BaseProviderConfigSchema):
    enabled: bool
    upload_preset_images: str
    upload_preset_videos: str
    signature_ttl_seconds: int
    max_image_bytes: int
    max_video_bytes: int



class AllProvidersSummarySchema(Schema):
    email: Optional[EmailProviderConfigSchema] = None
    sms: Optional[SMSProviderConfigSchema] = None
    kyc: Optional[KYCProviderConfigSchema] = None
    cloudinary: Optional[CloudinaryProviderConfigSchema] = None
