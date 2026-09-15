"""API v1 routers."""

from app.api.v1.public import public_router
from app.api.v1.ai import ai_router
from app.api.v1.customer import customer_router
from app.api.v1.admin import admin_router
from app.api.v1.webhooks import webhook_router

__all__ = [
    "public_router",
    "ai_router",
    "customer_router",
    "admin_router",
    "webhook_router",
]
