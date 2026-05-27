# apps/global_platform_settings/admin_backend/schemas.py
from datetime import datetime
from ninja import Schema
from pydantic import UUID4

class PlatformSettingsSchema(Schema):
    id: UUID4
    vendor_commission_rate: float
    client_platform_fee_rate: float
    measurement_fee_ngn: float
    advertisement_fee_ngn: float
    min_wallet_topup_ngn: float
    max_wallet_topup_ngn: float
    min_withdrawal_ngn: float
    max_withdrawal_ngn: float
    max_daily_withdrawal_ngn: float
    cod_enabled: bool
    in_store_payment_enabled: bool
    cod_confirmation_window_hours: int
    cod_platform_commission_rate: float
    kyc_max_retry_attempts: int
    kyc_lockout_hours: int
    ngn_usd_rate: float
    platform_name: str
    support_email: str
    support_phone: str
    terms_url: str
    privacy_url: str
    created_at: datetime
    updated_at: datetime
