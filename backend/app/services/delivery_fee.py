"""
Intelligent delivery fee engine.

Caches delivery fee rules, peak settings, loyalty settings, and item
surcharge rules for _CACHE_TTL seconds.
"""

import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from app.config import settings
from app.database import get_supabase, execute_db
from app.models.orders import OrderItem
from app.api.utils.logging_setup import logger


# =============================================
# DELIVERY FEE ENGINE
# =============================================
_rules_cache = {"data": None, "timestamp": 0}
_peak_cache = {"data": None, "timestamp": 0}
_loyalty_cache = {"data": None, "timestamp": 0}
_item_surcharge_cache = {"data": None, "timestamp": 0}
_CACHE_TTL = 60


async def get_delivery_fee_rules() -> List[Dict]:
    now = time.time()
    if now - _rules_cache["timestamp"] < _CACHE_TTL and _rules_cache["data"] is not None:
        return _rules_cache["data"]
    db = get_supabase()
    result = await execute_db(
        db.table("delivery_fee_rules").select("*").order("min_order_value")
    )
    _rules_cache["data"] = result.data or []
    _rules_cache["timestamp"] = now
    return _rules_cache["data"]


async def get_peak_settings() -> List[Dict]:
    now = time.time()
    if now - _peak_cache["timestamp"] < _CACHE_TTL and _peak_cache["data"] is not None:
        return _peak_cache["data"]
    db = get_supabase()
    result = await execute_db(
        db.table("delivery_peak_settings").select("*").eq("is_active", True)
    )
    _peak_cache["data"] = result.data or []
    _peak_cache["timestamp"] = now
    return _peak_cache["data"]


async def get_loyalty_setting() -> Optional[Dict]:
    now = time.time()
    if now - _loyalty_cache["timestamp"] < _CACHE_TTL and _loyalty_cache["data"] is not None:
        return _loyalty_cache["data"]
    db = get_supabase()
    result = await execute_db(
        db.table("delivery_loyalty_settings").select("*").eq("is_active", True).limit(1)
    )
    _loyalty_cache["data"] = result.data[0] if result.data else None
    _loyalty_cache["timestamp"] = now
    return _loyalty_cache["data"]


async def get_item_surcharge_rules() -> List[Dict]:
    now = time.time()
    if (now - _item_surcharge_cache["timestamp"] < _CACHE_TTL
            and _item_surcharge_cache["data"] is not None):
        return _item_surcharge_cache["data"]
    db = get_supabase()
    result = await execute_db(
        db.table("delivery_item_surcharge_rules").select("*").order("min_main_items")
    )
    _item_surcharge_cache["data"] = result.data or []
    _item_surcharge_cache["timestamp"] = now
    return _item_surcharge_cache["data"]


def is_peak_hour(order_time: datetime, peak_settings: List[Dict]) -> bool:
    if not order_time:
        order_time = datetime.now()
    dow = order_time.weekday()
    hour_min = order_time.strftime("%H:%M")
    for s in peak_settings:
        if s.get("day_of_week") is not None and s["day_of_week"] != dow:
            continue
        start, end = s.get("start_time"), s.get("end_time")
        if start and end and start <= hour_min <= end:
            return True
    return False


async def calculate_intelligent_delivery_fee(
    base_fee: int,
    order_value: int,
    items: List[OrderItem],
    order_time: Optional[datetime] = None,
    customer_email: Optional[str] = None,
) -> Dict[str, Any]:
    fee = base_fee
    value_discount = item_surcharge = peak_surcharge = 0
    loyalty_discount = volume_surcharge = 0
    minimum_fee = settings.MINIMUM_DELIVERY_FEE

    # 1. Product details
    product_ids = [i.product_id for i in items]
    db = get_supabase()
    try:
        result = await execute_db(
            db.table("products")
            .select("id, is_main_item, weight_kg, is_bulky")
            .in_("id", product_ids)
        )
        product_map = {p["id"]: p for p in result.data} if result.data else {}
    except Exception as e:
        logger.warning(f"Could not fetch product delivery details: {e}")
        product_map = {}

    # 2. Metrics
    main_count = 0
    total_weight = 0.0
    bulky_count = 0
    total_items = sum(i.qty for i in items)

    for item in items:
        prod = product_map.get(item.product_id)
        if prod:
            is_main = prod.get("is_main_item")
            if is_main is None:
                is_main = True
            if is_main:
                main_count += item.qty
            weight = prod.get("weight_kg")
            if weight is None:
                weight = 0.5
            total_weight += float(weight) * item.qty
            is_bulky = prod.get("is_bulky")
            if is_bulky is None:
                is_bulky = False
            if is_bulky:
                bulky_count += item.qty
        else:
            main_count += item.qty
            total_weight += 0.5 * item.qty

    # 3. Volume surcharge
    t = settings.VOLUME_SURCHARGE_THRESHOLDS
    a = settings.VOLUME_SURCHARGE_AMOUNTS
    if total_items >= t.get("xxlarge", 10):
        volume_surcharge += a.get("xxlarge", 500)
    elif total_items >= t.get("xlarge", 6):
        volume_surcharge += a.get("xlarge", 300)
    elif total_items >= t.get("large", 4):
        volume_surcharge += a.get("large", 150)

    # 4. Weight surcharge
    if total_weight > settings.WEIGHT_THRESHOLD_KG:
        extra_kg = total_weight - settings.WEIGHT_THRESHOLD_KG
        volume_surcharge += int(extra_kg * settings.WEIGHT_SURCHARGE_PER_KG)

    # 5. Bulky surcharge
    if bulky_count > 0:
        volume_surcharge += bulky_count * settings.BULKY_ITEM_SURCHARGE

    # 6. Item surcharge rules
    try:
        surcharge_rules = await get_item_surcharge_rules()
        for rule in surcharge_rules:
            mn, mx = rule.get("min_main_items"), rule.get("max_main_items")
            if ((mn is None or main_count >= mn) and (mx is None or main_count <= mx)):
                item_surcharge += rule.get("surcharge_amount", 0)
                break
        for rule in surcharge_rules:
            th, per_kg = rule.get("weight_threshold_kg"), rule.get("surcharge_per_kg")
            if th is not None and per_kg is not None and total_weight > th:
                item_surcharge += int((total_weight - th) * per_kg)
                break
    except Exception as e:
        logger.warning(f"Item surcharge error: {e}")

    # 7. Peak surcharge
    try:
        peak_settings = await get_peak_settings()
        if is_peak_hour(order_time or datetime.now(), peak_settings):
            peak_surcharge = settings.PEAK_SURCHARGE
    except Exception as e:
        logger.warning(f"Peak surcharge error: {e}")

    # 8. Loyalty discount
    try:
        if customer_email:
            loyalty = await get_loyalty_setting()
            if loyalty:
                min_orders = loyalty.get("min_orders", 5)
                discount_pct = min(
                    loyalty.get("discount_percentage", 20),
                    settings.MAX_LOYALTY_DISCOUNT_PERCENT,
                )
                count_result = await execute_db(
                    db.table("orders")
                    .select("id", count="exact")
                    .eq("customer_email", customer_email)
                    .in_("status", ["paid", "confirmed", "completed"])
                )
                if (count_result.count or 0) >= min_orders and fee > 0:
                    loyalty_discount = int(fee * discount_pct / 100)
                    fee -= loyalty_discount
    except Exception as e:
        logger.warning(f"Loyalty discount error: {e}")

    # 9. Apply surcharges
    fee += volume_surcharge + item_surcharge + peak_surcharge

    # 10. Value discount rules
    try:
        rules = await get_delivery_fee_rules()
        for rule in rules:
            mn = rule.get("min_order_value", 0)
            mx = rule.get("max_order_value")
            if order_value >= mn and (mx is None or order_value <= mx):
                if rule.get("free_delivery", False):
                    value_discount = fee
                    fee = 0
                else:
                    mult = rule.get("fee_multiplier", 1.0)
                    disc = rule.get("fee_discount", 0)
                    new_fee = fee * mult - disc
                    value_discount = fee - new_fee
                    fee = max(0, new_fee)
                break
    except Exception as e:
        logger.warning(f"Value discount error: {e}")

    # 11. Minimum fee
    if 0 < fee < minimum_fee:
        fee = minimum_fee

    # 12. Round
    return {
        "base_fee": base_fee,
        "volume_surcharge": round(volume_surcharge),
        "value_discount": round(value_discount),
        "item_surcharge": round(item_surcharge),
        "peak_surcharge": round(peak_surcharge),
        "loyalty_discount": round(loyalty_discount),
        "final_fee": max(0, round(fee)),
        "breakdown": {
            "base": base_fee,
            "volume_surcharge": round(volume_surcharge),
            "item_surcharge": round(item_surcharge),
            "peak_surcharge": round(peak_surcharge),
            "loyalty_discount": -round(loyalty_discount),
            "value_discount": -round(value_discount),
            "final": max(0, round(fee)),
        },
    }
