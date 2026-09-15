
"""
Correlation ID middleware.

Attaches a unique request ID to every request/response and stores it in a
context var so structured logs can include it.
"""

import time
from fastapi import Request

from app.api.utils.logging_setup import (
    set_correlation_id,
    reset_correlation_id,
)


async def add_correlation_id(request: Request, call_next):
    cid = (
        request.headers.get("X-Correlation-ID")
        or f"{int(time.time()*1000)}-{id(request)}"
    )
    token = set_correlation_id(cid)
    try:
        response = await call_next(request)
        response.headers["X-Correlation-ID"] = cid
        return response
    finally:
        reset_correlation_id(token)
