"""
Banner CRUD service.

Handles the banners table plus its many-to-many join tables
(banner_categories, banner_products).
"""

from datetime import datetime, date
from typing import List, Optional

from fastapi import HTTPException

from app.database import get_supabase, execute_db
from app.models.banners import (
    Banner, BannerCreate, BannerUpdate, BannerResponse,
)
from app.api.utils.datetime_helpers import convert_datetime_to_iso


# ---------- BANNER SERVICE ----------
class BannerService:
    def __init__(self):
        self.db = get_supabase()
        self.table = "banners"

    async def _get_categories(self, bid):
        r = await execute_db(
            self.db.table("banner_categories").select("category_id").eq("banner_id", bid)
        )
        return [x["category_id"] for x in r.data]

    async def _get_products(self, bid):
        r = await execute_db(
            self.db.table("banner_products").select("product_id").eq("banner_id", bid)
        )
        return [x["product_id"] for x in r.data]

    def _in_date_range(self, banner) -> bool:
        now = datetime.now().isoformat()
        start, end = banner.get("start_date"), banner.get("end_date")
        if start and start > now:
            return False
        if end and end < now:
            return False
        return True

    async def get_banners(self, is_active=None, is_hero=None,
                          is_featured=None, category=None, limit=50, offset=0):
        query = self.db.table(self.table).select("*", count="exact")
        if is_active is not None:
            query = query.eq("is_active", is_active)
        if is_hero is not None:
            query = query.eq("is_hero", is_hero)
        if is_featured is not None:
            query = query.eq("is_featured", is_featured)

        result = await execute_db(
            query.order("display_order").range(offset, offset + limit - 1)
        )
        data = [b for b in result.data if self._in_date_range(b)]
        for b in data:
            b["categories"] = await self._get_categories(b["id"])
            b["products"] = await self._get_products(b["id"])
        data = [convert_datetime_to_iso(b) for b in data]

        return BannerResponse(
            banners=data,
            total=len(data),
            active_count=sum(1 for x in data if x.get("is_active", True)),
            hero_count=sum(1 for x in data if x.get("is_hero", False)),
            featured_count=sum(1 for x in data if x.get("is_featured", False)),
        )

    async def get_active(self, is_hero=None, is_featured=None):
        query = self.db.table(self.table).select("*").eq("is_active", True)
        if is_hero is not None:
            query = query.eq("is_hero", is_hero)
        if is_featured is not None:
            query = query.eq("is_featured", is_featured)
        result = await execute_db(query.order("display_order"))
        data = [b for b in result.data if self._in_date_range(b)]
        for b in data:
            b["categories"] = await self._get_categories(b["id"])
            b["products"] = await self._get_products(b["id"])
        return [convert_datetime_to_iso(b) for b in data]

    async def get_banner(self, banner_id: int):
        result = await execute_db(
            self.db.table(self.table).select("*").eq("id", banner_id)
        )
        if not result.data:
            return None
        b = result.data[0]
        b["categories"] = await self._get_categories(b["id"])
        b["products"] = await self._get_products(b["id"])
        return convert_datetime_to_iso(b)

    async def create_banner(self, banner: BannerCreate):
        data = banner.dict(exclude={"categories", "products"})
        data["created_at"] = data["updated_at"] = datetime.now().isoformat()
        data = convert_datetime_to_iso(data)
        result = await execute_db(self.db.table(self.table).insert(data))
        if not result.data:
            raise HTTPException(400, "Create failed")
        bid = result.data[0]["id"]
        if banner.categories:
            for cid in banner.categories:
                await execute_db(self.db.table("banner_categories").insert(
                    {"banner_id": bid, "category_id": cid}
                ))
        if banner.products:
            for pid in banner.products:
                await execute_db(self.db.table("banner_products").insert(
                    {"banner_id": bid, "product_id": pid}
                ))
        return result.data[0]

    async def update_banner(self, banner_id: int, banner: BannerUpdate):
        data = banner.dict(exclude={"categories", "products"}, exclude_unset=True)
        data["updated_at"] = datetime.now().isoformat()
        data = convert_datetime_to_iso(data)
        result = await execute_db(
            self.db.table(self.table).update(data).eq("id", banner_id)
        )
        if not result.data:
            raise HTTPException(404, "Not found")
        if banner.categories is not None:
            await execute_db(
                self.db.table("banner_categories").delete().eq("banner_id", banner_id)
            )
            for cid in banner.categories:
                await execute_db(self.db.table("banner_categories").insert(
                    {"banner_id": banner_id, "category_id": cid}
                ))
        if banner.products is not None:
            await execute_db(
                self.db.table("banner_products").delete().eq("banner_id", banner_id)
            )
            for pid in banner.products:
                await execute_db(self.db.table("banner_products").insert(
                    {"banner_id": banner_id, "product_id": pid}
                ))
        return result.data[0]

    async def delete_banner(self, banner_id: int):
        await execute_db(
            self.db.table("banner_categories").delete().eq("banner_id", banner_id)
        )
        await execute_db(
            self.db.table("banner_products").delete().eq("banner_id", banner_id)
        )
        result = await execute_db(
            self.db.table(self.table).delete().eq("id", banner_id)
        )
        if not result.data:
            raise HTTPException(404, "Not found")

    async def toggle_banner(self, banner_id: int):
        b = await self.get_banner(banner_id)
        if not b:
            raise HTTPException(404, "Not found")
        new_status = not b["is_active"]
        await execute_db(
            self.db.table(self.table)
            .update({"is_active": new_status, "updated_at": datetime.now().isoformat()})
            .eq("id", banner_id)
        )
        return {"id": banner_id, "is_active": new_status}

    async def duplicate_banner(self, banner_id: int):
        original = await self.get_banner(banner_id)
        if not original:
            raise HTTPException(404, "Not found")
        copy = {k: v for k, v in original.items()
                if k not in ["id", "created_at", "updated_at"]}
        copy["title"] = f"{copy['title']} (Copy)"
        copy["is_active"] = False
        result = await execute_db(self.db.table(self.table).insert(copy))
        return result.data[0]

    async def reorder_banners(self, banner_ids: List[int]):
        for idx, bid in enumerate(banner_ids):
            await execute_db(
                self.db.table(self.table)
                .update({"display_order": idx, "updated_at": datetime.now().isoformat()})
                .eq("id", bid)
            )
        return {"success": True}
