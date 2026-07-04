from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated

from arq.connections import ArqRedis
from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_api_key
from app.db.models import Tenant
from app.db.session import get_session
from app.worker.queue import get_arq_pool

SessionDep = Annotated[AsyncSession, Depends(get_session)]


async def get_current_tenant(
    session: SessionDep,
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
) -> Tenant:
    if not x_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing X-API-Key"
        )
    stmt = select(Tenant).where(Tenant.api_key_hash == hash_api_key(x_api_key))
    tenant = (await session.execute(stmt)).scalar_one_or_none()
    if tenant is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key"
        )
    return tenant


TenantDep = Annotated[Tenant, Depends(get_current_tenant)]


async def get_arq() -> AsyncIterator[ArqRedis]:
    pool = await get_arq_pool()
    try:
        yield pool
    finally:
        await pool.aclose()


ArqDep = Annotated[ArqRedis, Depends(get_arq)]
