"""
Atomic stock management using Postgres RPC functions.

Required SQL (run once in Supabase SQL editor):

    CREATE OR REPLACE FUNCTION reduce_order_stock(p_items JSONB)
    RETURNS VOID LANGUAGE plpgsql AS $$
    DECLARE item RECORD;
    BEGIN
      FOR item IN
        SELECT * FROM jsonb_to_recordset(p_items) AS x(product_id INT, qty INT)
      LOOP
        UPDATE products
        SET stock = GREATEST(0, stock - item.qty)
        WHERE id = item.product_id;
      END LOOP;
    END;
    $$;

    CREATE OR REPLACE FUNCTION restore_order_stock(p_items JSONB)
    RETURNS VOID LANGUAGE plpgsql AS $$
    DECLARE item RECORD;
    BEGIN
      FOR item IN
        SELECT * FROM jsonb_to_recordset(p_items) AS x(product_id INT, qty INT)
      LOOP
        UPDATE products SET stock = stock + item.qty WHERE id = item.product_id;
      END LOOP;
    END;
    $$;
"""

from app.database import get_supabase, execute_db
from app.api.utils.cache import invalidate_stats_cache


# =============================================
# STOCK MANAGEMENT (atomic via Postgres RPC)
# =============================================
async def reduce_order_stock(order: dict):
    items = [
        {"product_id": i.get("product_id"), "qty": i.get("qty", 0)}
        for i in order.get("items", [])
        if i.get("product_id") and i.get("qty", 0) > 0
    ]
    if not items:
        return
    await execute_db(get_supabase().rpc("reduce_order_stock", {"p_items": items}))
    invalidate_stats_cache()


async def restore_order_stock(order: dict):
    items = [
        {"product_id": i.get("product_id"), "qty": i.get("qty", 0)}
        for i in order.get("items", [])
        if i.get("product_id") and i.get("qty", 0) > 0
    ]
    if not items:
        return
    await execute_db(get_supabase().rpc("restore_order_stock", {"p_items": items}))
    invalidate_stats_cache()
