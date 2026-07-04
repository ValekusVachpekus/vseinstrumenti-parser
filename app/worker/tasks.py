from __future__ import annotations

from arq.connections import RedisSettings

from app.core.config import settings
from app.core.logging import get_logger
from app.db.models import Product
from app.db.session import async_session_factory
from app.fetch.factory import build_fetcher

log = get_logger(__name__)


async def check_product_task(ctx: dict, product_id: int) -> dict:
    fetcher = ctx["fetcher"]
    async with async_session_factory() as session:
        product = await session.get(Product, product_id)
        if product is None:
            return {"status": "not_found", "product_id": product_id}
        if not product.is_active:
            return {"status": "inactive", "product_id": product_id}
        # Imported lazily to keep task module import-light.
        from app.monitor.pipeline import check_product

        result = await check_product(session, product, fetcher)
        log.info("checked product %s: %s", product_id, result.get("status"))
        return result


async def on_startup(ctx: dict) -> None:
    fetcher = build_fetcher()
    await fetcher.astart()
    ctx["fetcher"] = fetcher
    log.info("worker started, fetcher=%s", settings.fetcher_backend)


async def on_shutdown(ctx: dict) -> None:
    fetcher = ctx.get("fetcher")
    if fetcher is not None:
        await fetcher.aclose()


class WorkerSettings:
    functions = [check_product_task]
    on_startup = on_startup
    on_shutdown = on_shutdown
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    max_jobs = 20
    job_timeout = 120
