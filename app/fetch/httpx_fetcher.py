from __future__ import annotations

import asyncio
import random
import time
from pathlib import Path

import httpx

from app.core.config import settings
from app.core.logging import get_logger
from app.fetch.base import Fetcher, FetchResponse
from app.fetch.rate_limit import RateLimiter

log = get_logger(__name__)

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
]

BASE_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}


class HttpxFetcher(Fetcher):
    def __init__(self, rate_limiter: RateLimiter | None = None):
        self._rate_limiter = rate_limiter
        # Cookie-harvest: a fixed UA must match the browser the cookie came from.
        self._fixed_ua = settings.harvest_user_agent or None
        self._cookie_file = settings.cookie_file or None
        self._static_cookie = settings.session_cookie or None
        cookies = {}
        if settings.target_city_id:
            cookies["city_id"] = settings.target_city_id
        proxy = settings.proxy_url or None
        self._client = httpx.AsyncClient(
            timeout=settings.fetch_timeout_seconds,
            follow_redirects=True,
            headers=BASE_HEADERS,
            cookies=cookies,
            proxy=proxy,
            http2=True,
        )

    def _current_cookie(self) -> str | None:
        """Harvested Cookie header. File (re-read each call, hot-swappable) wins."""
        if self._cookie_file:
            try:
                text = Path(self._cookie_file).read_text(encoding="utf-8").strip()
                if text:
                    return text
            except OSError:
                pass
        return self._static_cookie

    def _request_headers(self) -> dict:
        headers = {"User-Agent": self._fixed_ua or random.choice(USER_AGENTS)}
        cookie = self._current_cookie()
        if cookie:
            headers["Cookie"] = cookie
        return headers

    async def fetch(self, url: str) -> FetchResponse:
        last_error: str | None = None
        last_status: int | None = None
        for attempt in range(1, settings.fetch_max_retries + 1):
            if self._rate_limiter is not None:
                await self._rate_limiter.acquire()
            await asyncio.sleep(
                random.uniform(settings.fetch_min_delay_seconds, settings.fetch_max_delay_seconds)
            )
            started = time.monotonic()
            try:
                resp = await self._client.get(url, headers=self._request_headers())
                elapsed = int((time.monotonic() - started) * 1000)
                if resp.status_code == 200:
                    return FetchResponse(
                        url=url,
                        ok=True,
                        status_code=resp.status_code,
                        text=resp.text,
                        elapsed_ms=elapsed,
                    )
                if resp.status_code in (403, 429) or resp.status_code >= 500:
                    last_error = f"http_{resp.status_code}"
                    last_status = resp.status_code
                    await self._backoff(attempt)
                    continue
                return FetchResponse(
                    url=url,
                    ok=False,
                    status_code=resp.status_code,
                    error=f"http_{resp.status_code}",
                    elapsed_ms=elapsed,
                )
            except httpx.HTTPError as exc:
                last_error = f"{type(exc).__name__}: {exc}"
                log.warning("fetch attempt %s failed for %s: %s", attempt, url, last_error)
                await self._backoff(attempt)

        return FetchResponse(
            url=url, ok=False, status_code=last_status, error=last_error or "unknown_error"
        )

    async def _backoff(self, attempt: int) -> None:
        await asyncio.sleep(min(2 ** attempt + random.random(), 30.0))

    async def aclose(self) -> None:
        await self._client.aclose()
