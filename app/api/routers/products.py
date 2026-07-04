from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.api.deps import ArqDep, SessionDep, TenantDep
from app.api.schemas import (
    BulkCheckRequest,
    BulkCheckResponse,
    CheckResponse,
    CrawlLogOut,
    PricePoint,
    ProductCreate,
    ProductDetail,
    ProductOut,
    ProductUpdate,
    SnapshotOut,
)
from app.core.config import settings
from app.db.models import CrawlLog, Product, Snapshot
from app.parse.urls import InvalidProductUrl, canonical_url, parse_product_ref
from app.worker.queue import enqueue_check

router = APIRouter(prefix="/v1/products", tags=["products"])


async def _get_owned(session: SessionDep, tenant_id: int, product_id: int) -> Product:
    product = await session.get(Product, product_id)
    if product is None or product.tenant_id != tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Product not found")
    return product


async def _latest(session: SessionDep, product_id: int) -> Snapshot | None:
    stmt = (
        select(Snapshot)
        .where(Snapshot.product_id == product_id)
        .order_by(Snapshot.captured_at.desc())
        .limit(1)
    )
    return (await session.execute(stmt)).scalar_one_or_none()


@router.post("", response_model=ProductDetail, status_code=status.HTTP_201_CREATED)
async def create_product(payload: ProductCreate, tenant: TenantDep, session: SessionDep):
    try:
        vi_id, slug = parse_product_ref(payload.ref)
    except InvalidProductUrl as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc

    product = Product(
        tenant_id=tenant.id,
        vi_product_id=vi_id,
        slug=slug,
        url=canonical_url(vi_id, slug),
        city=settings.target_city,
        check_interval_seconds=payload.check_interval_seconds,
        next_check_at=datetime.now(timezone.utc),  # due immediately on first add
    )
    session.add(product)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        existing = (
            await session.execute(
                select(Product).where(
                    Product.tenant_id == tenant.id, Product.vi_product_id == vi_id
                )
            )
        ).scalar_one()
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={"message": "Product already tracked", "id": existing.id},
        ) from None
    await session.refresh(product)
    detail = ProductDetail.model_validate(product)
    return detail


@router.get("", response_model=list[ProductOut])
async def list_products(
    tenant: TenantDep,
    session: SessionDep,
    is_active: bool | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    stmt = select(Product).where(Product.tenant_id == tenant.id)
    if is_active is not None:
        stmt = stmt.where(Product.is_active.is_(is_active))
    stmt = stmt.order_by(Product.id).limit(limit).offset(offset)
    rows = (await session.execute(stmt)).scalars().all()
    return list(rows)


@router.get("/{product_id}", response_model=ProductDetail)
async def get_product(product_id: int, tenant: TenantDep, session: SessionDep):
    product = await _get_owned(session, tenant.id, product_id)
    detail = ProductDetail.model_validate(product)
    snap = await _latest(session, product_id)
    if snap is not None:
        detail.current = SnapshotOut.model_validate(snap)
    return detail


@router.patch("/{product_id}", response_model=ProductOut)
async def update_product(
    product_id: int, payload: ProductUpdate, tenant: TenantDep, session: SessionDep
):
    product = await _get_owned(session, tenant.id, product_id)
    if payload.check_interval_seconds is not None:
        product.check_interval_seconds = payload.check_interval_seconds
    if payload.is_active is not None:
        product.is_active = payload.is_active
    await session.commit()
    await session.refresh(product)
    return product


@router.delete("/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_product(product_id: int, tenant: TenantDep, session: SessionDep):
    product = await _get_owned(session, tenant.id, product_id)
    await session.delete(product)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/check", response_model=BulkCheckResponse)
async def bulk_check(
    payload: BulkCheckRequest, tenant: TenantDep, session: SessionDep, arq: ArqDep
):
    stmt = select(Product.id).where(
        Product.tenant_id == tenant.id, Product.is_active.is_(True)
    )
    if payload.product_ids:
        stmt = stmt.where(Product.id.in_(payload.product_ids))
    ids = list((await session.execute(stmt)).scalars().all())

    job_ids: list[str] = []
    for pid in ids:
        job_id = await enqueue_check(arq, pid)
        if job_id:
            job_ids.append(job_id)
    return BulkCheckResponse(enqueued=len(job_ids), job_ids=job_ids)


@router.post("/{product_id}/check", response_model=CheckResponse)
async def check_product_now(
    product_id: int, tenant: TenantDep, session: SessionDep, arq: ArqDep
):
    product = await _get_owned(session, tenant.id, product_id)
    job_id = await enqueue_check(arq, product.id)
    return CheckResponse(job_id=job_id, product_id=product.id)


@router.get("/{product_id}/snapshots", response_model=list[SnapshotOut])
async def list_snapshots(
    product_id: int,
    tenant: TenantDep,
    session: SessionDep,
    since: datetime | None = None,
    until: datetime | None = None,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    await _get_owned(session, tenant.id, product_id)
    stmt = select(Snapshot).where(Snapshot.product_id == product_id)
    if since is not None:
        stmt = stmt.where(Snapshot.captured_at >= since)
    if until is not None:
        stmt = stmt.where(Snapshot.captured_at <= until)
    stmt = stmt.order_by(Snapshot.captured_at.desc()).limit(limit).offset(offset)
    return list((await session.execute(stmt)).scalars().all())


@router.get("/{product_id}/crawl-log", response_model=list[CrawlLogOut])
async def list_crawl_log(
    product_id: int,
    tenant: TenantDep,
    session: SessionDep,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    await _get_owned(session, tenant.id, product_id)
    stmt = (
        select(CrawlLog)
        .where(CrawlLog.product_id == product_id)
        .order_by(CrawlLog.started_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return list((await session.execute(stmt)).scalars().all())


@router.get("/{product_id}/price-history", response_model=list[PricePoint])
async def price_history(
    product_id: int,
    tenant: TenantDep,
    session: SessionDep,
    since: datetime | None = None,
    until: datetime | None = None,
    limit: int = Query(1000, ge=1, le=5000),
):
    await _get_owned(session, tenant.id, product_id)
    stmt = select(
        Snapshot.captured_at,
        Snapshot.price,
        Snapshot.old_price,
        Snapshot.discount_pct,
        Snapshot.in_stock,
    ).where(Snapshot.product_id == product_id)
    if since is not None:
        stmt = stmt.where(Snapshot.captured_at >= since)
    if until is not None:
        stmt = stmt.where(Snapshot.captured_at <= until)
    stmt = stmt.order_by(Snapshot.captured_at.asc()).limit(limit)
    rows = (await session.execute(stmt)).all()
    return [
        PricePoint(
            captured_at=r.captured_at,
            price=r.price,
            old_price=r.old_price,
            discount_pct=r.discount_pct,
            in_stock=r.in_stock,
        )
        for r in rows
    ]
