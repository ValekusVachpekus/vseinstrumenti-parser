from __future__ import annotations

import asyncio
import contextlib
import time
from pathlib import Path

from app.core.config import settings
from app.core.logging import get_logger
from app.fetch.base import Fetcher, FetchResponse
from app.fetch.rate_limit import RateLimiter

log = get_logger(__name__)

# Spoof the WebGL vendor/renderer. Under xvfb the GPU is software (SwiftShader),
# which ServicePipe fingerprints as a bot; reporting a common GPU passes the check.
WEBGL_SPOOF = """
const _gp = WebGLRenderingContext.prototype.getParameter;
WebGLRenderingContext.prototype.getParameter = function (p) {
  if (p === 37445) return 'Intel Inc.';
  if (p === 37446) return 'Intel(R) Iris(R) Xe Graphics';
  return _gp.call(this, p);
};
const _gp2 = WebGL2RenderingContext.prototype.getParameter;
WebGL2RenderingContext.prototype.getParameter = function (p) {
  if (p === 37445) return 'Intel Inc.';
  if (p === 37446) return 'Intel(R) Iris(R) Xe Graphics';
  return _gp2.call(this, p);
};
"""

# ServicePipe hard-ban page (vs a solvable challenge or the real product page).
HARD_BLOCK_MARKERS = ("please copy the report", "request-ip")
CAPTCHA_MARKERS = ("sp_rotated_captcha", "captchaintgen")
# The product markup is present once the challenge has been solved.
READY_SELECTOR = "script[type='application/ld+json'], [itemprop='price']"


class PlaywrightFetcher(Fetcher):
    """
    Renders pages in a HEADED patchright Chromium with a persistent profile.
    This is the only transport observed to pass vseinstrumenti.ru's ServicePipe
    WAF: patchright hides automation, the headed real browser + persistent profile
    solves the JS challenge silently (headless gets an interactive captcha).

    Requirements on the host:
      - a clean/residential IP (ServicePipe weighs IP reputation),
      - a display: a real X display, or xvfb on a headless server
        (e.g. `xvfb-run -a arq app.worker.tasks.WorkerSettings`).
    """

    def __init__(self, rate_limiter: RateLimiter | None = None):
        self._rate_limiter = rate_limiter
        self._sem = asyncio.Semaphore(max(settings.playwright_max_concurrency, 1))
        self._pw = None
        self._context = None

    async def astart(self) -> None:
        from patchright.async_api import async_playwright

        # Clear stale Chromium singleton locks left by a crashed previous run
        # (the persistent profile lives on a volume, so a lock can survive restarts).
        profile = Path(settings.playwright_user_data_dir)
        for lock in ("SingletonLock", "SingletonSocket", "SingletonCookie"):
            with contextlib.suppress(OSError):
                (profile / lock).unlink()

        self._pw = await async_playwright().start()
        proxy = {"server": settings.proxy_url} if settings.proxy_url else None
        self._context = await self._pw.chromium.launch_persistent_context(
            user_data_dir=settings.playwright_user_data_dir,
            headless=settings.playwright_headless,
            channel=settings.playwright_channel,
            proxy=proxy,
            locale="ru-RU",
            timezone_id="Europe/Moscow",
            viewport={"width": 1366, "height": 768},
            # Required when running as root in a container.
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        await self._context.add_init_script(WEBGL_SPOOF)
        if settings.target_city_id:
            await self._context.add_cookies(
                [{"name": "city_id", "value": settings.target_city_id,
                  "domain": ".vseinstrumenti.ru", "path": "/"}]
            )
        log.info(
            "patchright fetcher started (headless=%s, channel=%s, profile=%s)",
            settings.playwright_headless, settings.playwright_channel,
            settings.playwright_user_data_dir,
        )

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
                    url, wait_until="commit", timeout=settings.playwright_nav_timeout_ms
                )
                status = resp.status if resp else None
                html, outcome = await self._settle(page)
                elapsed = int((time.monotonic() - started) * 1000)
                if outcome == "ready":
                    return FetchResponse(url=url, ok=True, status_code=200,
                                         text=html, elapsed_ms=elapsed)
                if outcome == "hard_block":
                    return FetchResponse(url=url, ok=False, status_code=status or 403,
                                         error="servicepipe_hard_block", elapsed_ms=elapsed)
                if outcome == "captcha":
                    return FetchResponse(url=url, ok=False, status_code=status or 403,
                                         error="servicepipe_captcha", elapsed_ms=elapsed)
                return FetchResponse(url=url, ok=False, status_code=status,
                                     error="challenge_unresolved", elapsed_ms=elapsed)
            except Exception as exc:  # noqa: BLE001
                return FetchResponse(url=url, ok=False, error=f"{type(exc).__name__}: {exc}")
            finally:
                await page.close()

    async def _settle(self, page) -> tuple[str, str]:
        """Wait out the ServicePipe challenge (which auto-reloads to the real page)."""
        html = ""
        for _ in range(max(settings.playwright_settle_tries, 1)):
            await page.wait_for_timeout(settings.playwright_settle_ms)
            try:
                html = await page.content()
            except Exception:  # noqa: BLE001 - page mid-navigation (challenge reload)
                continue
            low = html.lower()
            if any(m in low for m in HARD_BLOCK_MARKERS):
                return html, "hard_block"
            if any(m in low for m in CAPTCHA_MARKERS):
                return html, "captcha"
            if "application/ld+json" in low or 'itemprop="price"' in low:
                return html, "ready"
        return html, "timeout"

    async def aclose(self) -> None:
        if self._context is not None:
            await self._context.close()
        if self._pw is not None:
            await self._pw.stop()
