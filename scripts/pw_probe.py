"""Standalone probe: does a real Chromium fetch + parse a vseinstrumenti.ru card
from THIS machine's IP? Run it on your own (residential) IP to confirm the
Playwright route works before wiring it into the worker.

Setup (repo root):
    python -m venv .venv && source .venv/bin/activate   # (Windows: .venv\\Scripts\\activate)
    pip install playwright selectolax
    playwright install chromium

Run:
    python scripts/pw_probe.py
    python scripts/pw_probe.py https://www.vseinstrumenti.ru/product/<slug>-<id>/
    HEADLESS=0 python scripts/pw_probe.py    # headed, if headless is flagged
"""
from __future__ import annotations

import asyncio
import os
import sys

from app.parse.extractor import extract

DEFAULT_URL = "https://www.vseinstrumenti.ru/product/perforator-makita-hr2470x15-814840/"
HEADLESS = os.environ.get("HEADLESS", "1") != "0"
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
STEALTH = """
Object.defineProperty(navigator,'webdriver',{get:()=>undefined});
Object.defineProperty(navigator,'languages',{get:()=>['ru-RU','ru','en-US']});
Object.defineProperty(navigator,'plugins',{get:()=>[1,2,3,4,5]});
window.chrome = window.chrome || { runtime: {} };
"""


async def main(url: str) -> int:
    from playwright.async_api import async_playwright

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=HEADLESS,
            args=["--no-sandbox", "--disable-blink-features=AutomationControlled"],
        )
        ctx = await browser.new_context(
            locale="ru-RU", timezone_id="Europe/Moscow",
            viewport={"width": 1366, "height": 768}, user_agent=UA,
        )
        await ctx.add_init_script(STEALTH)
        page = await ctx.new_page()
        resp = await page.goto(url, wait_until="domcontentloaded", timeout=45000)
        print(f"nav status: {resp.status if resp else None}  headless={HEADLESS}")
        try:
            await page.wait_for_selector(
                "script[type='application/ld+json'], [itemprop='price']", timeout=20000
            )
        except Exception:
            print("  (no product markup yet — waiting out challenge)")
        await page.wait_for_timeout(4000)
        html = await page.content()
        low = html.lower()
        if "please copy the report" in low:
            print("RESULT: HARD BLOCK (ServicePipe ban page) — this IP is flagged.")
            await browser.close()
            return 2

        result = extract(html)
        print(f"len(html)={len(html)}  parsed_ok={result.is_usable()}  source={result.source}")
        if result.is_usable():
            print(f"  title:  {result.title}")
            print(f"  price:  {result.price}  old:{result.old_price}  disc:{result.discount_pct}")
            print(f"  stock:  {result.in_stock}  ({result.availability_raw})")
            print(f"  promos: {result.promo_labels}")
            print("RESULT: OK — Playwright works from this IP.")
            code = 0
        else:
            print(f"RESULT: challenge unresolved / not parsed (error={result.error}).")
            print("  Try HEADLESS=0, or the IP/browser is being fingerprinted.")
            code = 1
        await browser.close()
        return code


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_URL
    sys.exit(asyncio.run(main(target)))
