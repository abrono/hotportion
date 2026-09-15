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
        raise HTTPException(400, "Order already confirmed")

    await reduce_order_stock(order)
    await execute_db(
        get_supabase().table("orders").update({"status": "confirmed"}).eq("id", oid)
    )
    invalidate_stats_cache()
    return {"message": "Order confirmed offline", "status": "confirmed"}


# ---- Stats (Tier 2) ----
@admin_router.get("/api/stats", dependencies=[Depends(require_role(2))])
async def get_stats():
    return await get_cached_stats()


# ---- Banners (Tier 2) ----
@admin_router.post("/api/v1/banners", response_model=Banner, status_code=201,
                   dependencies=[Depends(require_role(2))])
async def create_banner(banner: BannerCreate):
    return await BannerService().create_banner(banner)


@admin_router.put("/api/v1/banners/{banner_id}", response_model=Banner,
                  dependencies=[Depends(require_role(2))])
async def update_banner(banner_id: int, banner: BannerUpdate):
    return await BannerService().update_banner(banner_id, banner)


@admin_router.delete("/api/v1/banners/{banner_id}", status_code=204,
                     dependencies=[Depends(require_role(2))])
async def delete_banner(banner_id: int):
    await BannerService().delete_banner(banner_id)


@admin_router.patch("/api/v1/banners/{banner_id}/toggle",
                    dependencies=[Depends(require_role(2))])
async def toggle_banner(banner_id: int):
    return await BannerService().toggle_banner(banner_id)


@admin_router.post("/api/v1/banners/{banner_id}/duplicate",
                   dependencies=[Depends(require_role(2))])
async def duplicate_banner(banner_id: int):
    return await BannerService().duplicate_banner(banner_id)


@admin_router.patch("/api/v1/banners/reorder",
                    dependencies=[Depends(require_role(2))])
async def reorder_banners(banner_ids: List[int]):
    return await BannerService().reorder_banners(banner_ids)


# =============================================
# ROUTES — admin delivery management (Tier 3)
# =============================================

# ---- Delivery areas ----
@admin_router.get("/api/delivery-areas", response_model=List[DeliveryArea],
                  dependencies=[Depends(require_role(3))])
async def get_all_delivery_areas():
    try:
        db = get_supabase()
        result = await execute_db(db.rpc("get_delivery_areas_geojson", {}))
        areas = []
        for a in result.data:
            d = dict(a)
            for k in ("created_at", "updated_at"):
                if k in d and isinstance(d[k], (datetime, date)):
                    d[k] = d[k].isoformat()
            if isinstance(d.get("polygon"), str):
                d["polygon"] = json.loads(d["polygon"])
            areas.append(d)
        return areas
    except Exception as e:
        logger.error(f"Fetch delivery areas error: {e}", exc_info=True)
        raise HTTPException(500, "Error fetching delivery areas")


@admin_router.post("/api/delivery-areas", response_model=DeliveryArea,
                   status_code=201, dependencies=[Depends(require_role(3))])
async def create_delivery_area(area: DeliveryAreaCreate):
    if area.polygon.get("type") != "Polygon" or not area.polygon.get("coordinates"):
        raise HTTPException(400, "Invalid polygon")
    if len(area.polygon["coordinates"][0]) < 4:
        raise HTTPException(400, "Polygon must have ≥4 points")

    db = get_supabase()
    result = await execute_db(db.rpc("insert_delivery_area", {
        "_name": area.name,
        "_fee": area.fee,
        "_geojson": json.dumps(area.polygon),
    }))
    if not result.data:
        raise HTTPException(400, "Failed to create delivery area")
    created = dict(result.data[0])
    created["polygon"] = area.polygon
    return convert_datetime_to_iso(created)


@admin_router.put("/api/delivery-areas/{area_id}", response_model=DeliveryArea,
                  dependencies=[Depends(require_role(3))])
async def update_delivery_area(area_id: int, area: DeliveryAreaUpdate):
    if area.polygon.get("type") != "Polygon" or not area.polygon.get("coordinates"):
        raise HTTPException(400, "Invalid polygon")
    db = get_supabase()
    result = await execute_db(db.rpc("update_delivery_area", {
        "_id": area_id,
        "_name": area.name,
        "_fee": area.fee,
        "_geojson": json.dumps(area.polygon),
    }))
    if not result.data:
        raise HTTPException(404, f"Area {area_id} not found")
    updated = dict(result.data[0])
    updated["polygon"] = area.polygon
    return convert_datetime_to_iso(updated)


@admin_router.delete("/api/delivery-areas/{area_id}", status_code=204,
                     dependencies=[Depends(require_role(3))])
async def delete_delivery_area(area_id: int):
    db = get_supabase()
    check = await execute_db(db.table("delivery_areas").select("id").eq("id", area_id))
    if not check.data:
        raise HTTPException(404, f"Area {area_id} not found")
    await execute_db(db.table("delivery_areas").delete().eq("id", area_id))


# ---- Admin delivery rules ----
@admin_router.get("/api/admin/delivery-rules",
                  response_model=List[DeliveryFeeRule],
                  dependencies=[Depends(require_role(3))])
async def get_delivery_rules():
    r = await execute_db(
        get_supabase().table("delivery_fee_rules").select("*").order("min_order_value")
    )
    return r.data


@admin_router.post("/api/admin/delivery-rules", response_model=DeliveryFeeRule,
                   status_code=201, dependencies=[Depends(require_role(3))])
async def create_delivery_rule(rule: DeliveryFeeRuleCreate):
    data = rule.dict(exclude={"id", "created_at", "updated_at"})
    data["created_at"] = data["updated_at"] = datetime.now().isoformat()
    r = await execute_db(get_supabase().table("delivery_fee_rules").insert(data))
    if not r.data:
        raise HTTPException(400, "Failed to create rule")
    return r.data[0]


@admin_router.put("/api/admin/delivery-rules/{rule_id}",
                  response_model=DeliveryFeeRule,
                  dependencies=[Depends(require_role(3))])
async def update_delivery_rule(rule_id: int, rule: DeliveryFeeRuleUpdate):
    data = rule.dict(exclude={"id", "created_at", "updated_at"}, exclude_unset=True)
    data["updated_at"] = datetime.now().isoformat()
    r = await execute_db(
        get_supabase().table("delivery_fee_rules").update(data).eq("id", rule_id)
    )
    if not r.data:
        raise HTTPException(404, "Rule not found")
    return r.data[0]


@admin_router.delete("/api/admin/delivery-rules/{rule_id}", status_code=204,
                     dependencies=[Depends(require_role(3))])
async def delete_delivery_rule(rule_id: int):
    r = await execute_db(
        get_supabase().table("delivery_fee_rules").delete().eq("id", rule_id)
    )
    if not r.data:
        raise HTTPException(404, "Rule not found")


# ---- Peak settings ----
@admin_router.get("/api/admin/peak-settings",
                  response_model=List[DeliveryPeakSetting],
                  dependencies=[Depends(require_role(3))])
async def get_peak_settings_admin():
    r = await execute_db(
        get_supabase().table("delivery_peak_settings").select("*").order("day_of_week")
    )
    return r.data


@admin_router.post("/api/admin/peak-settings",
                   response_model=DeliveryPeakSetting, status_code=201,
                   dependencies=[Depends(require_role(3))])
async def create_peak_setting(setting: DeliveryPeakSettingCreate):
    data = setting.dict(exclude={"id", "created_at", "updated_at"})
    data["created_at"] = data["updated_at"] = datetime.now().isoformat()
    r = await execute_db(get_supabase().table("delivery_peak_settings").insert(data))
    if not r.data:
        raise HTTPException(400, "Failed")
    return r.data[0]


@admin_router.put("/api/admin/peak-settings/{setting_id}",
                  response_model=DeliveryPeakSetting,
                  dependencies=[Depends(require_role(3))])
async def update_peak_setting(setting_id: int, setting: DeliveryPeakSettingUpdate):
    data = setting.dict(exclude={"id", "created_at", "updated_at"}, exclude_unset=True)
    data["updated_at"] = datetime.now().isoformat()
    r = await execute_db(
        get_supabase().table("delivery_peak_settings").update(data).eq("id", setting_id)
    )
    if not r.data:
        raise HTTPException(404, "Not found")
    return r.data[0]


@admin_router.delete("/api/admin/peak-settings/{setting_id}", status_code=204,
                     dependencies=[Depends(require_role(3))])
async def delete_peak_setting(setting_id: int):
    r = await execute_db(
        get_supabase().table("delivery_peak_settings").delete().eq("id", setting_id)
    )
    if not r.data:
        raise HTTPException(404, "Not found")


# ---- Loyalty settings ----
@admin_router.get("/api/admin/loyalty-settings",
                  response_model=List[DeliveryLoyaltySetting],
                  dependencies=[Depends(require_role(3))])
async def get_loyalty_settings_admin():
    r = await execute_db(get_supabase().table("delivery_loyalty_settings").select("*"))
    return r.data


@admin_router.post("/api/admin/loyalty-settings",
                   response_model=DeliveryLoyaltySetting, status_code=201,
                   dependencies=[Depends(require_role(3))])
async def create_loyalty_setting(setting: DeliveryLoyaltySettingCreate):
    data = setting.dict(exclude={"id", "created_at", "updated_at"})
    data["created_at"] = data["updated_at"] = datetime.now().isoformat()
    r = await execute_db(get_supabase().table("delivery_loyalty_settings").insert(data))
    if not r.data:
        raise HTTPException(400, "Failed")
    return r.data[0]


@admin_router.put("/api/admin/loyalty-settings/{setting_id}",
                  response_model=DeliveryLoyaltySetting,
                  dependencies=[Depends(require_role(3))])
async def update_loyalty_setting(setting_id: int,
                                  setting: DeliveryLoyaltySettingUpdate):
    data = setting.dict(exclude={"id", "created_at", "updated_at"}, exclude_unset=True)
    data["updated_at"] = datetime.now().isoformat()
    r = await execute_db(
        get_supabase().table("delivery_loyalty_settings").update(data).eq("id", setting_id)
    )
    if not r.data:
        raise HTTPException(404, "Not found")
    return r.data[0]


@admin_router.delete("/api/admin/loyalty-settings/{setting_id}", status_code=204,
                     dependencies=[Depends(require_role(3))])
async def delete_loyalty_setting(setting_id: int):
    r = await execute_db(
        get_supabase().table("delivery_loyalty_settings").delete().eq("id", setting_id)
    )
    if not r.data:
        raise HTTPException(404, "Not found")


# ---- Item surcharge rules ----
@admin_router.get("/api/admin/item-surcharge-rules",
                  response_model=List[DeliveryItemSurchargeRule],
                  dependencies=[Depends(require_role(3))])
async def get_item_surcharge_rules_admin():
    r = await execute_db(
        get_supabase().table("delivery_item_surcharge_rules")
        .select("*").order("min_main_items")
    )
    return r.data


@admin_router.post("/api/admin/item-surcharge-rules",
                   response_model=DeliveryItemSurchargeRule, status_code=201,
                   dependencies=[Depends(require_role(3))])
async def create_item_surcharge_rule(rule: DeliveryItemSurchargeRuleCreate):
    data = rule.dict(exclude={"id", "created_at", "updated_at"})
    data["created_at"] = data["updated_at"] = datetime.now().isoformat()
    r = await execute_db(
        get_supabase().table("delivery_item_surcharge_rules").insert(data)
    )
    if not r.data:
        raise HTTPException(400, "Failed")
    return r.data[0]


@admin_router.put("/api/admin/item-surcharge-rules/{rule_id}",
                  response_model=DeliveryItemSurchargeRule,
                  dependencies=[Depends(require_role(3))])
async def update_item_surcharge_rule(rule_id: int,
                                      rule: DeliveryItemSurchargeRuleUpdate):
    data = rule.dict(exclude={"id", "created_at", "updated_at"}, exclude_unset=True)
    data["updated_at"] = datetime.now().isoformat()
    r = await execute_db(
        get_supabase().table("delivery_item_surcharge_rules")
        .update(data).eq("id", rule_id)
    )
    if not r.data:
        raise HTTPException(404, "Not found")
    return r.data[0]


@admin_router.delete("/api/admin/item-surcharge-rules/{rule_id}", status_code=204,
                     dependencies=[Depends(require_role(3))])
async def delete_item_surcharge_rule(rule_id: int):
    r = await execute_db(
        get_supabase().table("delivery_item_surcharge_rules")
        .delete().eq("id", rule_id)
    )
    if not r.data:
        raise HTTPException(404, "Not found")
