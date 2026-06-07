# apps/authentication/admin_backend/schemas.py
from datetime import datetime
from typing import Optional, Dict
from ninja import Schema
from pydantic import UUID4

class UnifiedUserListSchema(Schema):
    id: UUID4
    email: Optional[str] = None
    phone: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    role: str
    auth_provider: str
    is_active: bool
    is_verified: bool
    is_deleted: bool
    member_id: Optional[str] = None
    date_joined: datetime

    @staticmethod
    def resolve_phone(obj):
        return str(obj.phone) if obj.phone else None

class UnifiedUserDetailSchema(Schema):
    id: UUID4
    email: Optional[str] = None
    phone: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    role: str
    auth_provider: str
    is_active: bool
    is_verified: bool
    is_deleted: bool
    member_id: Optional[str] = None
    avatar: Optional[str] = None
    bio: Optional[str] = None
    country: Optional[str] = None
    state: Optional[str] = None
    city: Optional[str] = None
    address: Optional[str] = None
    date_joined: datetime
    updated_at: datetime

    @staticmethod
    def resolve_phone(obj):
        return str(obj.phone) if obj.phone else None

    @staticmethod
    def resolve_avatar(obj):
        return obj.avatar.url if obj.avatar else None

class UserMetricsSchema(Schema):
    total_users: int
    active_users: int
    unverified_users: int
    vendors_count: int
    clients_count: int
    staff_count: int
    admins_count: int
    editors_count: int
    supports_count: int
