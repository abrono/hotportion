"""
In-process TTL cache for the admin dashboard statistics endpoint.
"""

import asyncio
import time

from app.config import settings
from app.database import get_supabase, execute_db


# ---------- CACHE ----------
_stats_cache = {"data": None, "timestamp": 0}


async def get_cached_stats():
    now = time.time()
    if (now - _stats_cache["timestamp"] < settings.STATS_CACHE_TTL_SECONDS
            and _stats_cache["data"] is not None):
        return _stats_cache["data"]

    db = get_supabase()
    products, categories, orders, revenue = await asyncio.gather(
        execute_db(db.table("products").select("id", count="exact")),
        execute_db(db.table("categories").select("id", count="exact")),
        execute_db(db.table("orders").select("id", count="exact")),
        execute_db(db.table("orders").select("total")),
    )
    result = {
        "totalProducts": products.count,
        "totalCategories": categories.count,
        "totalOrders": orders.count,
        "totalRevenue": sum(o["total"] for o in revenue.data),
    }
    _stats_cache["data"] = result
    _stats_cache["timestamp"] = now
    return result


def invalidate_stats_cache():
    _stats_cache["timestamp"] = 0
