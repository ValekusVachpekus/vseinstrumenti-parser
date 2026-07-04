from __future__ import annotations

from app.core.config import settings
from app.fetch.base import Fetcher
from app.fetch.httpx_fetcher import HttpxFetcher
from app.fetch.rate_limit import RateLimiter, make_redis


def build_fetcher() -> Fetcher:
    """
    Construct the configured fetcher backend.

    Extension point: add 'playwright' or 'service' backends here without changing
    the monitor pipeline. All backends implement the Fetcher interface.
    """
    backend = settings.fetcher_backend.lower()
    rate_limiter = RateLimiter(make_redis(), settings.global_rate_limit_rps)

    if backend == "httpx":
        return HttpxFetcher(rate_limiter=rate_limiter)

    if backend == "playwright":
        # Imported lazily so the (heavy) browser dependency is optional.
        from app.fetch.playwright_fetcher import PlaywrightFetcher

        return PlaywrightFetcher(rate_limiter=rate_limiter)

    raise ValueError(f"Unknown FETCHER_BACKEND: {settings.fetcher_backend}")
