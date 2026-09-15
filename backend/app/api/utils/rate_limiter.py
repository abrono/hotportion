"""
Simple in-process token-bucket rate limiter.

For multi-worker deployments use Redis + slowapi.
"""

import asyncio
import time
from collections import defaultdict
from typing import Dict, List

from fastapi import HTTPException, Request

from app.config import settings


# ---------- RATE LIMITER ----------
class RateLimiter:
    """Simple in-process token bucket. For multi-worker use Redis + slowapi."""

    def __init__(self, max_requests: int, window_seconds: int):
        self.max = max_requests
        self.window = window_seconds
        self._hits: Dict[str, List[float]] = defaultdict(list)
        self._lock = asyncio.Lock()

    async def check(self, key: str):
        async with self._lock:
            now = time.time()
            bucket = [t for t in self._hits[key] if now - t < self.window]
            if len(bucket) >= self.max:
                raise HTTPException(429, "Rate limit exceeded")
            bucket.append(now)
            self._hits[key] = bucket


_ai_limiter = RateLimiter(
    max_requests=settings.AI_RATE_LIMIT_PER_MIN, window_seconds=60
)


async def ai_rate_limit(request: Request):
    ip = request.client.host if request.client else "unknown"
    await _ai_limiter.check(ip)
