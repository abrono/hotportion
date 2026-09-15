"""
Supabase client and thread-pool executor.

The Supabase Python client is synchronous, so all DB calls are pushed onto
a dedicated ThreadPoolExecutor via `execute_db`.
"""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

from supabase import create_client, Client

from app.config import settings


# ---------- DATABASE ----------
_executor = ThreadPoolExecutor(max_workers=settings.MAX_DB_THREADS)
_supabase_client: Optional[Client] = None


def get_supabase() -> Client:
    global _supabase_client
    if _supabase_client is None:
        _supabase_client = create_client(
            settings.SUPABASE_URL, settings.SUPABASE_SERVICE_KEY
        )
    return _supabase_client


async def execute_db(query):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(_executor, query.execute)


def get_executor() -> ThreadPoolExecutor:
    return _executor


def shutdown_executor(wait: bool = True) -> None:
    _executor.shutdown(wait=wait)
