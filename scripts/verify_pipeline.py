"""Deterministic end-to-end check of the monitoring pipeline against a real
PostgreSQL, using a stub fetcher that returns local HTML fixtures. No network to
the target site is required.

Run inside the compose network:
    docker compose run --rm -v "$PWD/scripts:/code/scripts" -v "$PWD/tests:/code/tests" \
        api python scripts/verify_pipeline.py
"""
from __future__ import annotations

import asyncio
from pathlib import Path

from sqlalchemy import delete, select

from app.bootstrap import ensure_bootstrap_tenant
from app.db.models import Event, Product, Snapshot, Tenant
from app.db.session import async_session_factory
from app.fetch.base import Fetcher, FetchResponse
from app.monitor.pipeline import check_product

FIXTURES = Path("tests/fixtures")


class StubFetcher(Fetcher):
    def __init__(self, html: str):
        self.html = html

    async def fetch(self, url: str) -> FetchResponse:
        return FetchResponse(url=url, ok=True, status_code=200, text=self.html)


async def main() -> None:
    await ensure_bootstrap_tenant()

    async with async_session_factory() as session:
        tenant = (await session.execute(select(Tenant))).scalars().first()

        # Clean any previous run of the same test product.
        await session.execute(
            delete(Product).where(
                Product.tenant_id == tenant.id, Product.vi_product_id == "999999"
            )
        )
        await session.commit()

        product = Product(
            tenant_id=tenant.id,
            vi_product_id="999999",
            url="http://stub/product/999999/",
            city="Москва",
        )
        session.add(product)
        await session.commit()
        await session.refresh(product)
        pid = product.id

    # First check: in stock, with discount.
    html1 = (FIXTURES / "product_in_stock_discount.html").read_text(encoding="utf-8")
    async with async_session_factory() as session:
        product = await session.get(Product, pid)
        r1 = await check_product(session, product, StubFetcher(html1))
    print("check #1:", r1)

    # Second check: out of stock -> should emit went_out_of_stock + discount_ended.
    html2 = (FIXTURES / "product_out_of_stock.html").read_text(encoding="utf-8")
    async with async_session_factory() as session:
        product = await session.get(Product, pid)
        r2 = await check_product(session, product, StubFetcher(html2))
    print("check #2:", r2)

    async with async_session_factory() as session:
        snaps = (
            await session.execute(
                select(Snapshot).where(Snapshot.product_id == pid).order_by(Snapshot.id)
            )
        ).scalars().all()
        events = (
            await session.execute(
                select(Event).where(Event.product_id == pid).order_by(Event.id)
            )
        ).scalars().all()

    print(f"\nsnapshots={len(snaps)}")
    for s in snaps:
        print(
            f"  price={s.price} old={s.old_price} disc={s.discount_pct} "
            f"in_stock={s.in_stock} promos={s.promo_labels}"
        )
    print(f"events={len(events)}")
    for e in events:
        print(f"  {e.type}: {e.old_value} -> {e.new_value} {e.payload}")

    event_types = {e.type for e in events}
    assert len(snaps) == 2, "expected two snapshots"
    assert "went_out_of_stock" in event_types, "missing went_out_of_stock"
    assert "discount_ended" in event_types, "missing discount_ended"
    print("\nVERIFY OK")


if __name__ == "__main__":
    asyncio.run(main())
