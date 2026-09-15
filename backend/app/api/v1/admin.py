"""
Admin router — JWT-based RBAC.

Tier mapping (hierarchical; a user with tier >= required is allowed):
    Tier 1 — view orders, update order status, view products.
    Tier 2 — Tier 1 + manage products, categories, banners, view stats,
             confirm offline orders.
    Tier 3 — Tier 2 + manage delivery areas, delivery rules, peak settings,
             loyalty settings, item surcharge rules.
"""

import json
from datetime import datetime, date
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.database import get_supabase, execute_db
from app.auth import require_role
from app.models.products import Product, ProductCreate, ProductUpdate
from app.models.categories import Category, CategoryBase
from app.models.orders import OrderStatusUpdate
from app.models.banners import Banner, BannerCreate, BannerUpdate
from app.models.delivery import (
    DeliveryArea, DeliveryAreaCreate, DeliveryAreaUpdate,
    DeliveryFeeRule, DeliveryFeeRuleCreate, DeliveryFeeRuleUpdate,
    DeliveryPeakSetting, DeliveryPeakSettingCreate, DeliveryPeakSettingUpdate,
    DeliveryLoyaltySetting, DeliveryLoyaltySettingCreate,
    DeliveryLoyaltySettingUpdate,
    DeliveryItemSurchargeRule, DeliveryItemSurchargeRuleCreate,
    DeliveryItemSurchargeRuleUpdate,
)
from app.services.banner_service import BannerService
from app.services.stock import reduce_order_stock, restore_order_stock
from app.api.utils.cache import get_cached_stats, invalidate_stats_cache
from app.api.utils.datetime_helpers import convert_datetime_to_iso
from app.api.utils.logging_setup import logger


admin_router = APIRouter()


# =============================================
# ROUTES — admin (Tier 2)
# =============================================

# ---- Products (Tier 2) ----
@admin_router.post("/api/products", response_model=Product, status_code=201,
                   dependencies=[Depends(require_role(2))])
async def create_product(p: ProductCreate):
    r = await execute_db(get_supabase().table("products").insert(p.dict()))
    if not r.data:
        raise HTTPException(400, "Failed")
    return r.data[0]


@admin_router.put("/api/products/{pid}", dependencies=[Depends(require_role(2))])
async def update_product(pid: int, p: ProductUpdate):
    r = await execute_db(
        get_supabase().table("products").update(p.dict()).eq("id", pid)
    )
    if not r.data:
        raise HTTPException(404, "Not found")
    return r.data[0]


@admin_router.delete("/api/products/{pid}", status_code=204,
                     dependencies=[Depends(require_role(2))])
async def delete_product(pid: int):
    r = await execute_db(get_supabase().table("products").delete().eq("id", pid))
    if not r.data:
        raise HTTPException(404, "Not found")


# ---- Categories (Tier 2) ----
@admin_router.post("/api/categories", response_model=Category, status_code=201,
                   dependencies=[Depends(require_role(2))])
async def create_category(c: CategoryBase):
    r = await execute_db(get_supabase().table("categories").insert(c.dict()))
    if not r.data:
        raise HTTPException(400, "Failed")
    return r.data[0]


@admin_router.put("/api/categories/{cid}", dependencies=[Depends(require_role(2))])
async def update_category(cid: int, c: CategoryBase):
    r = await execute_db(
        get_supabase().table("categories").update(c.dict()).eq("id", cid)
    )
    if not r.data:
        raise HTTPException(404, "Not found")
    return r.data[0]


@admin_router.delete("/api/categories/{cid}", status_code=204,
                     dependencies=[Depends(require_role(2))])
async def delete_category(cid: int):
    r = await execute_db(get_supabase().table("categories").delete().eq("id", cid))
    if not r.data:
        raise HTTPException(404, "Not found")


# ---- Orders (Tier 1 for view/status, Tier 2 for confirm-offline) ----
@admin_router.get("/api/orders", response_model=List[Dict],
                  dependencies=[Depends(require_role(1))])
async def get_orders(since: Optional[str] = Query(None)):
    query = get_supabase().table("orders").select("*").order("created_at", desc=True)
    if since:
        query = query.gt("created_at", since)
    r = await execute_db(query)
    for o in r.data:
        o["itemCount"] = len(o.get("items", []))
    return r.data


@admin_router.patch("/api/orders/{oid}/status",
                    dependencies=[Depends(require_role(1))])
async def update_order_status(oid: int, upd: OrderStatusUpdate):
    order_result = await execute_db(
        get_supabase().table("orders").select("*").eq("id", oid)
    )
    if not order_result.data:
        raise HTTPException(404, "Order not found")
    order = order_result.data[0]
    current_status = order.get("status")

    update_data = {"status": upd.status}
    if upd.reason is not None:
        update_data["cancellation_reason"] = upd.reason

    if upd.status == "cancelled" and current_status != "cancelled":
        await restore_order_stock(order)

    if upd.status in ("confirmed", "paid") and current_status not in ("confirmed", "paid"):
        await reduce_order_stock(order)

    result = await execute_db(
        get_supabase().table("orders").update(update_data).eq("id", oid)
    )
    if not result.data:
        raise HTTPException(404, "Order not found")
    invalidate_stats_cache()
    return result.data[0]


@admin_router.post("/api/orders/{oid}/confirm-offline",
                   dependencies=[Depends(require_role(2))])
async def confirm_order_offline(oid: int):
    order_result = await execute_db(
        get_supabase().table("orders").select("*").eq("id", oid)
    )
    if not order_result.data:
        raise HTTPException(404, "Order not found")
    order = order_result.data[0]

    if order.get("status") in ("confirmed", "paid"):
        raise HTTPException(400, "Order
