from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Query
from sqlalchemy import select

from app.api.deps import SessionDep, TenantDep
from app.api.schemas import EventOut
from app.db.models import Event, Product

router = APIRouter(prefix="/v1/events", tags=["events"])


@router.get("", response_model=list[EventOut])
async def list_events(
    tenant: TenantDep,
    session: SessionDep,
    type: str | None = None,
    product_id: int | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    # Join Product to enforce tenant ownership.
    stmt = (
        select(Event)
        .join(Product, Event.product_id == Product.id)
        .where(Product.tenant_id == tenant.id)
    )
    if type is not None:
        stmt = stmt.where(Event.type == type)
    if product_id is not None:
        stmt = stmt.where(Event.product_id == product_id)
    if since is not None:
        stmt = stmt.where(Event.created_at >= since)
    if until is not None:
        stmt = stmt.where(Event.created_at <= until)
    stmt = stmt.order_by(Event.created_at.desc()).limit(limit).offset(offset)
    return list((await session.execute(stmt)).scalars().all())
