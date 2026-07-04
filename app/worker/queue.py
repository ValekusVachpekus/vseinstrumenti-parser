from __future__ import annotations

from arq import create_pool
from arq.connections import ArqRedis, RedisSettings

from app.core.config import settings


async def get_arq_pool() -> ArqRedis:
    return await create_pool(RedisSettings.from_dsn(settings.redis_url))


async def enqueue_check(pool: ArqRedis, product_id: int) -> str | None:
    job = await pool.enqueue_job("check_product_task", product_id)
    return job.job_id if job else None
