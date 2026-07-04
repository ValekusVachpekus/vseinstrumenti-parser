from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal


@dataclass
class ExtractResult:
    """Normalized product state extracted from a card page."""

    success: bool = False
    error: str | None = None
    source: str | None = None  # which strategy produced the result

    title: str | None = None
    price: Decimal | None = None
    old_price: Decimal | None = None
    discount_pct: Decimal | None = None
    in_stock: bool | None = None
    availability_raw: str | None = None
    promo_labels: list[str] = field(default_factory=list)
    raw_hash: str | None = None

    def is_usable(self) -> bool:
        """A result is usable if we got at least a price or a stock status."""
        return self.success and (self.price is not None or self.in_stock is not None)
