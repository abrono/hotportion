"""
Authentication + Role-Based Access Control (RBAC).

Staff roles are stored in a `profiles` table (linked 1:1 to auth.users)
with a text `role` column. Tiers are hierarchical:
    tier1  -> Basic staff
    tier2  -> Manager
    tier3  -> Admin (highest)

Customers authenticate with Supabase Auth JWTs as well; their profile row
is not required for order creation / read.

Required Supabase SQL (run once in SQL editor):

    CREATE TABLE IF NOT EXISTS profiles (
        id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
        email TEXT,
        role TEXT NOT NULL DEFAULT 'tier1',
        created_at TIMESTAMPTZ DEFAULT NOW(),
        updated_at TIMESTAMPTZ DEFAULT NOW()
    );

    ALTER TABLE profiles ENABLE ROW LEVEL SECURITY;

    CREATE POLICY "Service role full access to profiles"
        ON profiles FOR ALL
        USING (auth.role() = 'service_role');

    -- Seed the first admin (tier3) — replace with the actual auth user UUID
    -- INSERT INTO profiles (id, email, role)
    -- VALUES ('<uuid>', 'admin@example.com', 'tier3');
"""

import secrets
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import (
    APIKeyHeader, HTTPBearer, HTTPAuthorizationCredentials,
)

from app.config import settings
from app.database import get_supabase, execute_db
from app.api.utils.logging_setup import logger


# ---------- AUTH ----------
_admin_key_header = APIKeyHeader(name="X-Admin-API-Key", auto_error=False)
_bearer_scheme = HTTPBearer(auto_error=False)


ROLE_TIERS = {
    "tier1": 1,
    "tier2": 2,
    "tier3": 3,
}


def _tier_of(role: Optional[str]) -> int:
    if not role:
        return 0
    return ROLE_TIERS.get(role.strip().lower(), 0)


async def require_admin(api_key: str = Depends(_admin_key_header)) -> bool:
    """Legacy static API-key guard.

    Retained for backward compatibility with callers that still pass
    `X-Admin-API-Key`. New routes should use `Depends(require_role(N))`.
    """
    if not api_key or not secrets.compare_digest(api_key, settings.ADMIN_API_KEY):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Admin key required",
        )
    return True


async def get_current_customer(
    creds: HTTPAuthorizationCredentials = Depends(_bearer_scheme),
) -> dict:
    """Verify Supabase JWT and return {id, email}."""
    if not creds:
        raise HTTPException(401, "Missing bearer token")
    try:
        user_resp = get_supabase().auth.get_user(creds.credentials)
        if not user_resp or not user_resp.user:
            raise HTTPException(401, "Invalid token")
        return {"id": user_resp.user.id, "email": user_resp.user.email}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(401, f"Auth failed: {e}")


async def _staff_profile(user: dict = Depends(get_current_customer)) -> dict:
    """Look up the staff profile for the authenticated user.

    Returns {id, email, role, tier}.
    """
    try:
        r = await execute_db(
            get_supabase().table("profiles").select("*").eq("id", user["id"])
        )
    except Exception as e:
        logger.error(f"Profile lookup failed: {e}")
        raise HTTPException(500, "Profile lookup failed")
    if not r.data:
        raise HTTPException(403, "Staff profile not found")
    profile = r.data[0]
    tier = _tier_of(profile.get("role"))
    if tier <= 0:
        raise HTTPException(403, "Invalid staff role")
    return {
        "id": user["id"],
        "email": user["email"],
        "role": profile.get("role"),
        "tier": tier,
    }


def require_role(min_tier: int):
    """Dependency factory — allows users whose tier is >= `min_tier`."""
    if min_tier not in (1, 2, 3):
        raise ValueError("min_tier must be 1, 2, or 3")

    async def _dependency(profile: dict = Depends(_staff_profile)) -> dict:
        if profile["tier"] < min_tier:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires tier {min_tier} or higher",
            )
        return profile

    return _dependency
