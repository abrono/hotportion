"""Pydantic models for all domains."""

from app.models.products import (
    ProductBase, ProductCreate, ProductUpdate, Product,
)
from app.models.categories import CategoryBase, Category
from app.models.orders import OrderItem, OrderCreate, OrderStatusUpdate
from app.models.banners import (
    BannerBase, BannerCreate, BannerUpdate, Banner, BannerResponse,
)
from app.models.ai import AIChatRequest, AIChatResponse
from app.models.delivery import (
    DeliveryAreaBase, DeliveryAreaCreate, DeliveryAreaUpdate, DeliveryArea,
    DeliveryFeeRule, DeliveryFeeRuleCreate, DeliveryFeeRuleUpdate,
    DeliveryPeakSetting, DeliveryPeakSettingCreate, DeliveryPeakSettingUpdate,
    DeliveryLoyaltySetting, DeliveryLoyaltySettingCreate,
    DeliveryLoyaltySettingUpdate,
    DeliveryItemSurchargeRule, DeliveryItemSurchargeRuleCreate,
    DeliveryItemSurchargeRuleUpdate,
    DeliveryFeeRequest, DeliveryFeeResponse,
)

__all__ = [
    "ProductBase", "ProductCreate", "ProductUpdate", "Product",
    "CategoryBase", "Category",
    "OrderItem", "OrderCreate", "OrderStatusUpdate",
    "BannerBase", "BannerCreate", "BannerUpdate", "Banner", "BannerResponse",
    "AIChatRequest", "AIChatResponse",
    "DeliveryAreaBase", "DeliveryAreaCreate", "DeliveryAreaUpdate", "DeliveryArea",
    "DeliveryFeeRule", "DeliveryFeeRuleCreate", "DeliveryFeeRuleUpdate",
    "DeliveryPeakSetting", "DeliveryPeakSettingCreate", "DeliveryPeakSettingUpdate",
    "DeliveryLoyaltySetting", "DeliveryLoyaltySettingCreate",
    "DeliveryLoyaltySettingUpdate",
    "DeliveryItemSurchargeRule", "DeliveryItemSurchargeRuleCreate",
    "DeliveryItemSurchargeRuleUpdate",
    "DeliveryFeeRequest", "DeliveryFeeResponse",
]
