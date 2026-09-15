"""Delivery area, fee rule, and delivery fee request/response models."""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel

from app.models.orders import OrderItem


# ---- Delivery areas ----
class DeliveryAreaBase(BaseModel):
    name: str
    fee: int


class DeliveryAreaCreate(DeliveryAreaBase):
    polygon: Dict[str, Any]


class DeliveryAreaUpdate(DeliveryAreaBase):
    polygon: Dict[str, Any]


class DeliveryArea(DeliveryAreaBase):
    id: int
    polygon: Dict[str, Any]
    created_at: datetime
    updated_at: datetime


class DeliveryFeeRule(BaseModel):
    id: Optional[int] = None
    min_order_value: int
    max_order_value: Optional[int] = None
    fee_multiplier: float = 1.0
    fee_discount: int = 0
    free_delivery: bool = False
    description: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class DeliveryFeeRuleCreate(DeliveryFeeRule):
    pass


class DeliveryFeeRuleUpdate(DeliveryFeeRule):
    pass


class DeliveryPeakSetting(BaseModel):
    id: Optional[int] = None
    day_of_week: Optional[int] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    surcharge_amount: int = 200
    is_active: bool = True
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class DeliveryPeakSettingCreate(DeliveryPeakSetting):
    pass


class DeliveryPeakSettingUpdate(DeliveryPeakSetting):
    pass


class DeliveryLoyaltySetting(BaseModel):
    id: Optional[int] = None
    min_orders: int = 5
    discount_percentage: int = 20
    is_active: bool = True
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class DeliveryLoyaltySettingCreate(DeliveryLoyaltySetting):
    pass


class DeliveryLoyaltySettingUpdate(DeliveryLoyaltySetting):
    pass


class DeliveryItemSurchargeRule(BaseModel):
    id: Optional[int] = None
    min_main_items: Optional[int] = None
    max_main_items: Optional[int] = None
    surcharge_amount: int = 0
    weight_threshold_kg: Optional[float] = None
    surcharge_per_kg: Optional[int] = None
    description: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class DeliveryItemSurchargeRuleCreate(DeliveryItemSurchargeRule):
    pass


class DeliveryItemSurchargeRuleUpdate(DeliveryItemSurchargeRule):
    pass


class DeliveryFeeRequest(BaseModel):
    address: str
    items: List[OrderItem]
    order_total: int
    order_time: Optional[datetime] = None
    customer_email: Optional[str] = None


class DeliveryFeeResponse(BaseModel):
    covered: bool
    base_fee: Optional[int] = None
    area_name: Optional[str] = None
    volume_surcharge: int = 0
    value_discount: int = 0
    item_surcharge: int = 0
    peak_surcharge: int = 0
    loyalty_discount: int = 0
    total_fee: int = 0
    breakdown: Optional[Dict[str, Any]] = None
    message: Optional[str] = None
