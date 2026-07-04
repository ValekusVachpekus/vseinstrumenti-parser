from __future__ import annotations

import asyncio
import time

from app.core.config import settings
from app.core.logging import get_logger
from app.fetch.base import Fetcher, FetchResponse
from app.fetch.rate_limit import RateLimiter

log = get_logger(__name__)

# Minimal fingerprint hardening so a headless browser is less obviously automated.
STEALTH = """
Object.defineProperty(navigator,'webdriver',{get:()=>undefined});
Object.defineProperty(navigator,'languages',{get:()=>['ru-RU','ru','en-US']});
Object.defineProperty(navigator,'plugins',{get:()=>[1,2,3,4,5]});
window.chrome = window.chrome || { runtime: {} };
"""

UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)

# Hard ServicePipe ban page marker (as opposed to a solvable JS challenge).
HARD_BLOCK_MARKERS = ("please copy the report", "REQUEST-IP")
# Signal that the real product page rendered.
READY_MARKERS = ('application/ld+json', 'itemprop="price"', "data-qa=\"product-price")


class PlaywrightFetcher(Fetcher):
    """
    Renders pages in a real Chromium via a persistent context. ServicePipe cookies
    live in the context, so its JS challenge is solved once and reused for later
    navigations. Requires a clean (residential/mobile) IP to pass ServicePipe.
    """

    def __init__(self, rate_limiter: RateLimiter | None = None):
        self._rate_limiter = rate_limiter
        self._sem = asyncio.Semaphore(max(settings.playwright_max_concurrency, 1))
        self._pw = None
        self._browser = None
        self._context = None

    async def astart(self) -> None:
        from playwright.async_api import async_playwright

        self._pw = await async_playwright().start()
        launch_args = ["--no-sandbox", "--disable-blink-features=AutomationControlled",
                       "--disable-dev-shm-usage"]
        self._browser = await self._pw.chromium.launch(
            headless=settings.playwright_headless, args=launch_args,
            proxy={"server": settings.proxy_url} if settings.proxy_url else None,
        )
        self._context = await self._browser.new_context(
            locale="ru-RU", timezone_id="Europe/Moscow",
            viewport={"width": 1366, "height": 768}, user_agent=UA,
        )
        await self._context.add_init_script(STEALTH)
        if settings.target_city_id:
            await self._context.add_cookies(
                [{"name": "city_id", "value": settings.target_city_id,
                  "domain": ".vseinstrumenti.ru", "path": "/"}]
            )
        log.info("playwright fetcher started (headless=%s)", settings.playwright_headless)

    async def fetch(self, url: str) -> FetchResponse:
        if self._context is None:
            return FetchResponse(url=url, ok=False, error="playwright_not_started")
        if self._rate_limiter is not None:
            await self._rate_limiter.acquire()

        async with self._sem:
            started = time.monotonic()
            page = await self._context.new_page()
            try:
                resp = await page.goto(
                    url, wait_until="domcontentloaded",
                    timeout=settings.playwright_nav_timeout_ms,
                )
                status = resp.status if resp else None
                html = await self._settle(page)
                elapsed = int((time.monotonic() - started) * 1000)
                low = html.lower()

                if any(m.lower() in low for m in HARD_BLOCK_MARKERS):
                    return FetchResponse(url=url, ok=False, status_code=status or 403,
                                         error="servicepipe_hard_block", elapsed_ms=elapsed)
                if any(m.lower() in low for m in READY_MARKERS):
                    return FetchResponse(url=url, ok=True, status_code=status or 200,
                                         text=html, elapsed_ms=elapsed)
                return FetchResponse(url=url, ok=False, status_code=status,
                                     error="challenge_unresolved", elapsed_ms=elapsed)
            except Exception as exc:  # noqa: BLE001
                return FetchResponse(url=url, ok=False,
                                     error=f"{type(exc).__name__}: {exc}")
            finally:
                await page.close()

    async def _settle(self, page) -> str:
        """Wait for the product markup; tolerate a one-shot challenge redirect."""
        try:
            await page.wait_for_selector(
                "script[type='application/ld+json'], [itemprop='price']",
                timeout=settings.playwright_nav_timeout_ms // 2,
            )
        except Exception:  # noqa: BLE001 - challenge may still be running
            await page.wait_for_timeout(settings.playwright_wait_ms)
        await page.wait_for_timeout(settings.playwright_wait_ms)
        return await page.content()

    async def aclose(self) -> None:
        if self._context is not None:
            await self._context.close()
        if self._browser is not None:
            await self._browser.close()
        if self._pw is not None:
            await self._pw.stop()
