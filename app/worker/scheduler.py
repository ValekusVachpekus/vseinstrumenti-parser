from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from sqlalchemy import or_, select

from app.core.config import settings
from app.core.logging import get_logger
from app.db.models import Product
from app.db.session import async_session_factory
from app.monitor.schedule import compute_next_check_at
from app.worker.queue import enqueue_check, get_arq_pool

log = get_logger(__name__)

BATCH_SIZE = 500


async def enqueue_due_products() -> int:
    now = datetime.now(timezone.utc)
    pool = await get_arq_pool()
    enqueued = 0
    try:
        async with async_session_factory() as session:
            stmt = (
                select(Product)
                .where(
                    Product.is_active.is_(True),
                    or_(Product.next_check_at.is_(None), Product.next_check_at <= now),
                )
                .order_by(Product.next_check_at.asc().nulls_first())
                .limit(BATCH_SIZE)
                .with_for_update(skip_locked=True)
            )
            products = (await session.execute(stmt)).scalars().all()
            for product in products:
                await enqueue_check(pool, product.id)
                # Bump immediately so the next tick doesn't re-enqueue the same product.
                product.next_check_at = compute_next_check_at(product, now)
                enqueued += 1
            await session.commit()
    finally:
        await pool.aclose()
    return enqueued


async def run() -> None:
    log.info("scheduler started, tick=%ss", settings.scheduler_tick_seconds)
    while True:
        try:
            count = await enqueue_due_products()
            if count:
                log.info("enqueued %s due products", count)
        except Exception:  # noqa: BLE001 - keep the loop alive
            log.exception("scheduler tick failed")
        await asyncio.sleep(settings.scheduler_tick_seconds)


if __name__ == "__main__":
    asyncio.run(run())
