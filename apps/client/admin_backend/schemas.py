# apps/client/admin_backend/schemas.py
from datetime import datetime
from typing import Optional, List
from ninja import Schema
from pydantic import UUID4

class ClientUserSchema(Schema):
    id: UUID4
    email: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    is_active: bool

class ClientAddressSchema(Schema):
    id: int
    label: str
    full_name: str
    phone: str
    street_address: str
    city: str
    state: str
    country: str
    postal_code: str
    is_default: bool
    created_at: datetime

class ClientProfileListSchema(Schema):
    id: UUID4
    user: ClientUserSchema
    bio: str
    state: str
    country: str
    preferred_size: str
    total_orders: int
    total_spent_ngn: float
    is_profile_complete: bool
    last_active_at: Optional[datetime] = None
    phone_verified: bool = False
    created_at: datetime

class ClientProfileDetailSchema(Schema):
    id: UUID4
    user: ClientUserSchema
    bio: str
    default_shipping_address: str
    state: str
    country: str
    preferred_size: str
    style_preferences: List[str]
    favourite_colours: List[str]
    total_orders: int
    total_spent_ngn: float
    is_profile_complete: bool
    email_notifications_enabled: bool
    sms_notifications_enabled: bool
    last_active_at: Optional[datetime] = None
    phone_verified: bool = False
    client_addresses: List[ClientAddressSchema]
    created_at: datetime
    updated_at: datetime

class ClientMetricsSchema(Schema):
    total_clients: int
    completed_profiles: int
    incomplete_profiles: int
    total_spending_ngn: float
