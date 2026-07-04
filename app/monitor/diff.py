from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from app.db.models import EventType, Snapshot
from app.parse.types import ExtractResult


@dataclass
class DetectedEvent:
    type: EventType
    old_value: str | None
    new_value: str | None
    payload: dict


def _s(value) -> str | None:
    return None if value is None else str(value)


def detect_changes(prev: Snapshot | None, new: ExtractResult) -> list[DetectedEvent]:
    """Compare the previous stored snapshot with a fresh extraction result."""
    events: list[DetectedEvent] = []

    # First observation: no baseline, so nothing to diff against.
    if prev is None:
        return events

    # Price
    if new.price is not None and prev.price is not None and Decimal(prev.price) != new.price:
        direction = "down" if new.price < Decimal(prev.price) else "up"
        events.append(
            DetectedEvent(
                EventType.price_changed,
                _s(prev.price),
                _s(new.price),
                {"direction": direction},
            )
        )

    # Stock transitions
    if prev.in_stock is not None and new.in_stock is not None and prev.in_stock != new.in_stock:
        if new.in_stock is False:
            events.append(
                DetectedEvent(EventType.went_out_of_stock, "true", "false", {})
            )
        else:
            events.append(DetectedEvent(EventType.back_in_stock, "false", "true", {}))

    # Discount lifecycle (presence of an old_price above current price)
    prev_disc = prev.discount_pct is not None and Decimal(prev.discount_pct) > 0
    new_disc = new.discount_pct is not None and new.discount_pct > 0
    if new_disc and not prev_disc:
        events.append(
            DetectedEvent(
                EventType.discount_started,
                None,
                _s(new.discount_pct),
                {"old_price": _s(new.old_price), "price": _s(new.price)},
            )
        )
    elif prev_disc and not new_disc:
        events.append(
            DetectedEvent(EventType.discount_ended, _s(prev.discount_pct), None, {})
        )

    # Promo labels
    prev_promos = set(prev.promo_labels or [])
    new_promos = set(new.promo_labels or [])
    if prev_promos != new_promos:
        events.append(
            DetectedEvent(
                EventType.promo_changed,
                ", ".join(sorted(prev_promos)) or None,
                ", ".join(sorted(new_promos)) or None,
                {
                    "added": sorted(new_promos - prev_promos),
                    "removed": sorted(prev_promos - new_promos),
                },
            )
        )

    return events
