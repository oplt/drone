from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config.runtime import settings
from backend.core.database.session import get_db
from backend.modules.analytics.api.analytics_route_deps import get_redis_client
from backend.modules.analytics.api.analytics_route_schemas import AnalyticsOverviewResponse
from backend.modules.analytics.cache import get_cached_overview, set_cached_overview
from backend.modules.analytics.service.overview import build_analytics_overview
from backend.modules.identity.dependencies import OrgUser, require_org_user

router = APIRouter(tags=["analytics"])


@router.get("/overview", response_model=AnalyticsOverviewResponse)
async def overview(
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_user),
) -> dict[str, Any]:
    org_id = org_user.org_id
    redis = get_redis_client()
    cached = await get_cached_overview(redis, org_id)
    if cached is not None:
        return cached

    response = await build_analytics_overview(db, org_id)
    await set_cached_overview(
        redis,
        org_id,
        response,
        ttl=max(1, int(settings.analytics_cache_ttl_sec)),
    )
    return response
