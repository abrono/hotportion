"""
Public webhooks — verified by signature.

Endpoints:
    POST /api/v1/webhooks/monnify
"""

import json

from fastapi import APIRouter, HTTPException, Request

from app.config import settings
from app.database import get_supabase, execute_db
from app.services.stock import reduce_order_stock
from app.api.integrations.monnify import MonnifyIntegration
from app.api.utils.cache import invalidate_stats_cache
from app.api.utils.logging_setup import logger


webhook_router = APIRouter()


# =============================================
# WEBHOOKS — public but signature-verified
# =============================================
@webhook_router.post("/api/v1/webhooks/monnify")
async def monnify_webhook(request: Request):
    raw_body = await request.body()
    signature = (
        request.headers.get(settings.MONNIFY_WEBHOOK_HEADER)
        or request.headers.get("x-monnify-signature")
        or request.headers.get("X-Signature")
    )

    if not MonnifyIntegration.verify_signature(raw_body, signature):
        logger.warning("Monnify webhook signature mismatch")
        raise HTTPException(400, "Invalid signature")

    try:
        payload = json.loads(raw_body)
    except json.JSONDecodeError:
        raise HTTPException(400, "Invalid JSON")

    if payload.get("eventType") != "SUCCESSFUL_TRANSACTION":
        return {"status": "ignored"}

    data = payload.get("data", {})
    payment_ref = data.get("paymentReference")
    trans_ref = data.get("transactionReference")

    q = get_supabase().table("orders").select("*")
    if payment_ref:
        q = q.eq("payment_reference", payment_ref)
    elif trans_ref:
        q = q.eq("monnify_transaction_ref", trans_ref)
    else:
        return {"status": "ignored"}

    order_result = await execute_db(q)
    if not order_result.data:
        logger.warning(f"Webhook order not found: {payment_ref or trans_ref}")
        return {"status": "ignored"}

    order = order_result.data[0]
    if order.get("status") == "paid":
        return {"status": "already_paid"}

    await reduce_order_stock(order)
    await execute_db(
        get_supabase().table("orders").update({"status": "paid"}).eq("id", order["id"])
    )
    invalidate_stats_cache()
    return {"status": "received"}
