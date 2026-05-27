# apps/order/admin_backend/schemas.py
from datetime import datetime
from decimal import Decimal
from typing import List, Optional
from ninja import Schema

class AdminOrderUserOut(Schema):
    id: int
    email: str
    first_name: str = ""
    last_name: str = ""

class AdminOrderVendorOut(Schema):
    id: str
    store_name: str = ""

class AdminOrderItemOut(Schema):
    model_config = {"from_attributes": True}
    id: str
    product_title_snapshot: str
    product_sku_snapshot: str
    unit_price: Decimal
    quantity: int
    line_total: Decimal

class AdminOrderOut(Schema):
    model_config = {"from_attributes": True}
    id: str
    order_number: str
    status: str
    fulfillment_type: str
    subtotal: Decimal
    shipping_amount: Decimal
    discount_amount: Decimal
    total_amount: Decimal
    commission_amount: Decimal
    vendor_payout: Decimal
    currency: str
    payment_reference: str = ""
    payment_gateway: str = ""
    paid_at: Optional[datetime] = None
    is_fully_paid: bool
    created_at: datetime
    updated_at: datetime
    user: Optional[AdminOrderUserOut] = None
    vendor: Optional[AdminOrderVendorOut] = None

class AdminOrderDetailOut(AdminOrderOut):
    model_config = {"from_attributes": True}
    delivery_address: dict = {}
    tracking_number: str = ""
    estimated_delivery: Optional[datetime] = None
    measurement_profile_id: Optional[str] = None
    is_custom_order: bool
    measurement_data: dict = {}
    customization_notes: str = ""
    escrow_released: bool
    cart_order_items: List[AdminOrderItemOut] = []
