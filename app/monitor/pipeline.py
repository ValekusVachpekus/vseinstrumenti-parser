from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.db.models import CrawlLog, CrawlStatus, Event, EventType, Product, Snapshot
from app.fetch.base import Fetcher
from app.monitor.diff import detect_changes
from app.monitor.schedule import compute_next_check_at
from app.parse.extractor import extract

log = get_logger(__name__)


async def _latest_snapshot(session: AsyncSession, product_id: int) -> Snapshot | None:
    stmt = (
        select(Snapshot)
        .where(Snapshot.product_id == product_id)
        .order_by(Snapshot.captured_at.desc())
        .limit(1)
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def _last_event_type(session: AsyncSession, product_id: int) -> EventType | None:
    stmt = (
        select(Event.type)
        .where(Event.product_id == product_id)
        .order_by(Event.created_at.desc())
        .limit(1)
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def check_product(session: AsyncSession, product: Product, fetcher: Fetcher) -> dict:
    """
    Run one monitoring cycle for a product. Persists a snapshot, emits change
    events, records a crawl log, and reschedules the product. Commits before return.
    """
    started = datetime.now(timezone.utc)
    resp = await fetcher.fetch(product.url)

    def _finish(status: CrawlStatus, http_status: int | None, error: str | None):
        session.add(
            CrawlLog(
                product_id=product.id,
                status=status,
                http_status=http_status,
                started_at=started,
                finished_at=datetime.now(timezone.utc),
                error=error,
            )
        )
        product.last_checked_at = datetime.now(timezone.utc)
        product.next_check_at = compute_next_check_at(product)

    if not resp.ok:
        _finish(CrawlStatus.fetch_error, resp.status_code, resp.error)
        await session.commit()
        return {"status": "fetch_error", "error": resp.error, "events": []}

    result = extract(resp.text)

    if not result.is_usable():
        # Emit parse_failed only when the previous event wasn't already one, to
        # avoid flooding on persistent layout changes.
        if await _last_event_type(session, product.id) != EventType.parse_failed:
            session.add(
                Event(
                    product_id=product.id,
                    type=EventType.parse_failed,
                    new_value=result.error,
                    payload={"http_status": resp.status_code},
                )
            )
        _finish(CrawlStatus.parse_error, resp.status_code, result.error)
        await session.commit()
        return {"status": "parse_error", "error": result.error, "events": ["parse_failed"]}

    prev = await _latest_snapshot(session, product.id)

    snapshot = Snapshot(
        product_id=product.id,
        price=result.price,
        old_price=result.old_price,
        discount_pct=result.discount_pct,
        in_stock=result.in_stock,
        availability_raw=result.availability_raw,
        promo_labels=result.promo_labels or None,
        raw_hash=result.raw_hash,
    )
    session.add(snapshot)

    detected = detect_changes(prev, result)
    for ev in detected:
        session.add(
            Event(
                product_id=product.id,
                type=ev.type,
                old_value=ev.old_value,
                new_value=ev.new_value,
                payload=ev.payload,
            )
        )

    if result.title and not product.title:
        product.title = result.title

    _finish(CrawlStatus.ok, resp.status_code, None)
    await session.commit()

    return {
        "status": "ok",
        "price": str(result.price) if result.price is not None else None,
        "in_stock": result.in_stock,
        "events": [e.type.value for e in detected],
    }
