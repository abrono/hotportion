"""
Hot Portion Grill — FastAPI entry point.

Fixes applied vs previous versions:
  ✓ JWT-based staff RBAC (tier1 / tier2 / tier3)
  ✓ Supabase JWT auth on customer-owned order reads (IDOR fix)
  ✓ Monnify webhook signature computed over RAW request body
  ✓ hmac.compare_digest everywhere
  ✓ Idempotent POST /api/orders (Idempotency-Key header + UNIQUE constraint)
  ✓ Atomic stock reduction via Postgres RPC (kills N+1)
  ✓ AI endpoint per-IP rate limiting
  ✓ setup_database() removed (use proper migrations)
  ✓ AWS Location Service geocoding (replaces Nominatim)

Required Supabase SQL (run once, in the SQL editor):

    ALTER TABLE orders
      ADD CONSTRAINT orders_payment_reference_unique
      UNIQUE (payment_reference);

    -- See services/stock.py and auth.py for the full SQL snippets that
    -- create the reduce/restore stock RPCs and the profiles table.

Run:
    uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1 --log-level info
"""

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.database import get_executor
from app.api.integrations.brevo import get_brevo
from app.api.integrations.monnify import get_monnify
from app.api.middleware.correlation import add_correlation_id
from app.api.utils.logging_setup import logger, get_correlation_id

from app.api.v1.public import public_router
from app.api.v1.ai import ai_router
from app.api.v1.customer import customer_router
from app.api.v1.admin import admin_router
from app.api.v1.webhooks import webhook_router


# ---------- LIFESPAN ----------
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Hot Portion Grill")
    results = await asyncio.gather(
        get_brevo().initialize(),
        get_monnify().initialize(),
        return_exceptions=True,
    )
    for i, r in enumerate(results):
        if isinstance(r, Exception):
            logger.error(f"Init service {i} failed: {r}")
    logger.info("All services ready (degraded mode allowed)")
    yield
    logger.info("Shutting down...")
    if get_brevo()._session:
        await get_brevo()._session.close()
    if get_monnify()._session:
        await get_monnify()._session.close()
    get_executor().shutdown(wait=True)


# ---------- APP ----------
app = FastAPI(
    title="Hot Portion Grill",
    version="1.1.0",
    lifespan=lifespan,
    docs_url="/docs",
)


@app.middleware("http")
async def _add_correlation_id(request: Request, call_next):
    return await add_correlation_id(request, call_next)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    cid = get_correlation_id()
    logger.error(f"Unhandled: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "type": "internal-server-error",
            "title": "An unexpected error occurred",
            "status": 500,
            "trace_id": cid,
            "detail": str(exc) if settings.DEBUG else None,
        },
    )


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------- ROUTERS ----------
app.include_router(public_router)
app.include_router(ai_router)
app.include_router(customer_router)
app.include_router(admin_router)
app.include_router(webhook_router)


# ---------- RUN ----------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, workers=1, log_level="info")
