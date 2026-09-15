"""
Customer router — requires Supabase customer JWT.

Endpoints:
    GET  /api/orders/{oid}   (customer-owned)
    POST /api/orders         (requires login, idempotent)
"""

from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException

from app.database import get_supabase, execute_db
from app.models.orders import OrderCreate
from app.auth import get_current_customer
from app.api.integrations.brevo import get_brevo
from app.api.integrations.monnify import get_monnify
from app.api.utils.logging_setup import logger


customer_router = APIRouter()


# =============================================
# ROUTES — customer-owned (Supabase JWT)
# =============================================
@customer_router.get("/api/orders/{oid}")
async def get_order(oid: int, user: dict = Depends(get_current_customer)):
    r = await execute_db(get_supabase().table("orders").select("*").eq("id", oid))
    if not r.data:
        raise HTTPException(404, "Not found")
    order = r.data[0]
    if (order.get("customer_email") or "").lower() != user["email"].lower():
        # Don't leak existence — pretend not found
        raise HTTPException(404, "Not found")
    return order


@customer_router.post("/api/orders", status_code=201)
async def create_order(
    order: OrderCreate,
    bg: BackgroundTasks,
    user: dict = Depends(get_current_customer),
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
):
    """Customer order creation (login required).

    Idempotent via `Idempotency-Key` header or `payment_reference`.
    """
    key = idempotency_key or order.payment_reference

    existing = await execute_db(
        get_supabase().table("orders").select("*").eq("payment_reference", key)
    )
    if existing.data:
        o = existing.data[0]
        return {
            "status": o["status"],
            "order_id": o["id"],
            "payment_reference": key,
            "checkout_url": None,
            "idempotent_replay": True,
        }

    data = order.dict(exclude={"monnify_transaction_ref"})
    data["payment_reference"] = key
    data.setdefault("delivery_fee", 0)

    try:
        result = await execute_db(get_supabase().table("orders").insert(data))
    except Exception as e:
        # Unique constraint race → return existing
        existing = await execute_db(
            get_supabase().table("orders").select("*").eq("payment_reference", key)
        )
        if existing.data:
            o = existing.data[0]
            return {
                "status": o["status"],
                "order_id": o["id"],
                "payment_reference": key,
                "checkout_url": None,
                "idempotent_replay": True,
            }
        raise HTTPException(400, f"Failed to create order: {e}")

    if not result.data:
        raise HTTPException(400, "Failed to create order")

    order_data = result.data[0]

    monnify = get_monnify()
    monnify_result = await monnify.initialize_transaction(
        amount=order.total,
        customer_name=order.customer_name,
        customer_email=order.customer_email,
        customer_phone=order.customer_phone,
        payment_reference=order.payment_reference,
        payment_description="Hot Portion Grill Order",
    )

    if not monnify_result["success"]:
        await execute_db(
            get_supabase().table("orders").delete().eq("id", order_data["id"])
        )
        raise HTTPException(
            400,
            f"Payment init failed: {monnify_result.get('error', 'Unknown')}",
        )

    await execute_db(
        get_supabase().table("orders")
        .update({"monnify_transaction_ref": monnify_result["transaction_reference"]})
        .eq("id", order_data["id"])
    )

    bg.add_task(get_brevo().send_order_confirmation, order_data)

    return {
        "status": "pending_payment",
        "order_id": order_data["id"],
        "payment_reference": order.payment_reference,
        "checkout_url": monnify_result["checkout_url"],
    }
