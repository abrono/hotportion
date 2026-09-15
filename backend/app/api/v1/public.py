"""
Public router — no authentication.

Endpoints:
    GET  /health
    GET  /api/products
    GET  /api/categories
    GET  /api/top-products
    GET  /api/v1/banners/active
    GET  /api/v1/banners/{banner_id}
    GET  /api/v1/banners
    POST /api/delivery-fee
    GET  /api/delivery-areas/point
"""

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query

from app.database import get_supabase, execute_db
from app.models.products import Product
from app.models.categories import Category
from app.models.banners import Banner, BannerResponse
from app.models.delivery import DeliveryFeeRequest, DeliveryFeeResponse
from app.services.banner_service import BannerService
from app.services.delivery_fee import calculate_intelligent_delivery_fee
from app.api.integrations.aws_location import get_aws_location
from app.api.utils.logging_setup import logger


public_router = APIRouter()


@app.get("/health")
async def health():
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}


@public_router.get("/api/products", response_model=List[Product])
async def get_products():
    r = await execute_db(get_supabase().table("products").select("*").order("name"))
    return r.data


@public_router.get("/api/categories", response_model=List[Category])
async def get_categories():
    r = await execute_db(get_supabase().table("categories").select("*").order("name"))
    return r.data


@public_router.get("/api/top-products")
async def get_top_products(limit: int = 20):
    r = await execute_db(
        get_supabase().table("orders").select("items")
        .in_("status", ["paid", "confirmed", "completed"])
    )
    totals = {}
    for order in r.data:
        for item in order.get("items", []):
            pid = item.get("product_id")
            if pid is None:
                continue
            qty = item.get("qty", 0)
            price = item.get("price", 0)
            totals.setdefault(pid, {"qty": 0, "revenue": 0})
            totals[pid]["qty"] += qty
            totals[pid]["revenue"] += price * qty

    sorted_items = sorted(totals.items(), key=lambda x: x[1]["qty"], reverse=True)[:limit]
    product_ids = [pid for pid, _ in sorted_items]

    products_map = {}
    if product_ids:
        prod_res = await execute_db(
            get_supabase().table("products")
            .select("id, name, price, emoji")
            .in_("id", product_ids)
        )
        products_map = {p["id"]: p for p in prod_res.data}

    return [
        {
            "product_id": pid,
            "name": products_map.get(pid, {}).get("name", "Unknown"),
            "emoji": products_map.get(pid, {}).get("emoji", "🍽️"),
            "quantity_sold": data["qty"],
            "revenue": data["revenue"],
        }
        for pid, data in sorted_items
    ]


# ---- Public banner reads ----
@public_router.get("/api/v1/banners/active", response_model=List[Banner])
async def list_active_banners(
    is_hero: Optional[bool] = Query(None),
    is_featured: Optional[bool] = Query(None),
):
    return await BannerService().get_active(is_hero, is_featured)


@public_router.get("/api/v1/banners/{banner_id}", response_model=Banner)
async def get_banner(banner_id: int):
    b = await BannerService().get_banner(banner_id)
    if not b:
        raise HTTPException(404, "Not found")
    return b


@public_router.get("/api/v1/banners", response_model=BannerResponse)
async def list_banners(
    is_active: Optional[bool] = Query(None),
    is_hero: Optional[bool] = Query(None),
    is_featured: Optional[bool] = Query(None),
    category: Optional[str] = Query(None),
    limit: int = 50,
    offset: int = 0,
):
    return await BannerService().get_banners(
        is_active, is_hero, is_featured, category, limit, offset
    )


# ---- Public delivery endpoints ----
@public_router.post("/api/delivery-fee", response_model=DeliveryFeeResponse)
async def get_delivery_fee(request: DeliveryFeeRequest):
    try:
        loc = get_aws_location()
        geo = await loc.geocode(request.address)
        if not geo:
            return DeliveryFeeResponse(
                covered=False,
                message="Address not found. Please check and try again.",
            )

        lat, lng = geo["lat"], geo["lng"]
        logger.info(f"Geocoded '{request.address}' → {geo['label']} ({lat},{lng})")

        db = get_supabase()
        result = await execute_db(
            db.rpc("find_delivery_area", {"lat": lat, "lng": lng})
        )
        if not result.data:
            return DeliveryFeeResponse(
                covered=False,
                message="Address not in any delivery area.",
            )

        area = result.data[0]
        base_fee = area.get("fee", 0)
        area_name = area.get("name", "Unknown Area")

        calc = await calculate_intelligent_delivery_fee(
            base_fee=base_fee,
            order_value=request.order_total,
            items=request.items,
            order_time=request.order_time or datetime.now(),
            customer_email=request.customer_email,
        )

        return DeliveryFeeResponse(
            covered=True,
            base_fee=base_fee,
            area_name=area_name,
            volume_surcharge=calc["volume_surcharge"],
            value_discount=calc["value_discount"],
            item_surcharge=calc["item_surcharge"],
            peak_surcharge=calc["peak_surcharge"],
            loyalty_discount=calc["loyalty_discount"],
            total_fee=calc["final_fee"],
            breakdown=calc["breakdown"],
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Delivery fee error: {e}", exc_info=True)
        raise HTTPException(500, "Error processing delivery fee request")


@public_router.get("/api/delivery-areas/point")
async def get_area_by_point(lat: float, lng: float):
    try:
        db = get_supabase()
        result = await execute_db(
            db.rpc("find_delivery_area", {"lat": lat, "lng": lng})
        )
        if result.data:
            return {"covered": True, "area": result.data[0]}
        return {"covered": False, "message": "Point not in any delivery area"}
    except Exception as e:
        logger.error(f"Point check error: {e}", exc_info=True)
        raise HTTPException(500, "Error checking delivery area coverage")
