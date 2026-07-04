from __future__ import annotations

import asyncio

from sqlalchemy import select

from app.core.config import settings
from app.core.logging import get_logger
from app.core.security import hash_api_key
from app.db.models import Tenant
from app.db.session import async_session_factory

log = get_logger(__name__)


async def ensure_bootstrap_tenant() -> None:
    key_hash = hash_api_key(settings.bootstrap_api_key)
    async with async_session_factory() as session:
        existing = (
            await session.execute(select(Tenant).where(Tenant.api_key_hash == key_hash))
        ).scalar_one_or_none()
        if existing is not None:
            log.info("bootstrap tenant already present (id=%s)", existing.id)
            return
        tenant = Tenant(name=settings.bootstrap_tenant_name, api_key_hash=key_hash)
        session.add(tenant)
        await session.commit()
        log.info("created bootstrap tenant '%s'", settings.bootstrap_tenant_name)


if __name__ == "__main__":
    asyncio.run(ensure_bootstrap_tenant())
