from decimal import Decimal
from types import SimpleNamespace

from app.db.models import EventType
from app.monitor.diff import detect_changes
from app.parse.types import ExtractResult


def _snap(price=None, old_price=None, discount_pct=None, in_stock=None, promo_labels=None):
    return SimpleNamespace(
        price=price,
        old_price=old_price,
        discount_pct=discount_pct,
        in_stock=in_stock,
        promo_labels=promo_labels or [],
    )


def test_no_baseline_no_events():
    new = ExtractResult(success=True, price=Decimal("100"), in_stock=True)
    assert detect_changes(None, new) == []


def test_price_drop():
    prev = _snap(price=Decimal("150"), in_stock=True)
    new = ExtractResult(success=True, price=Decimal("100"), in_stock=True)
    events = detect_changes(prev, new)
    types = {e.type for e in events}
    assert EventType.price_changed in types
    ev = next(e for e in events if e.type == EventType.price_changed)
    assert ev.payload["direction"] == "down"


def test_went_out_of_stock():
    prev = _snap(price=Decimal("100"), in_stock=True)
    new = ExtractResult(success=True, price=Decimal("100"), in_stock=False)
    events = detect_changes(prev, new)
    assert any(e.type == EventType.went_out_of_stock for e in events)


def test_back_in_stock():
    prev = _snap(price=Decimal("100"), in_stock=False)
    new = ExtractResult(success=True, price=Decimal("100"), in_stock=True)
    events = detect_changes(prev, new)
    assert any(e.type == EventType.back_in_stock for e in events)


def test_discount_started():
    prev = _snap(price=Decimal("100"), discount_pct=None, in_stock=True)
    new = ExtractResult(
        success=True,
        price=Decimal("90"),
        old_price=Decimal("100"),
        discount_pct=Decimal("10.00"),
        in_stock=True,
    )
    events = detect_changes(prev, new)
    assert any(e.type == EventType.discount_started for e in events)


def test_promo_changed():
    prev = _snap(price=Decimal("100"), in_stock=True, promo_labels=["Акция"])
    new = ExtractResult(
        success=True, price=Decimal("100"), in_stock=True, promo_labels=["Распродажа"]
    )
    events = detect_changes(prev, new)
    assert any(e.type == EventType.promo_changed for e in events)


def test_stable_no_events():
    prev = _snap(price=Decimal("100"), in_stock=True, promo_labels=["Акция"])
    new = ExtractResult(
        success=True, price=Decimal("100"), in_stock=True, promo_labels=["Акция"]
    )
    assert detect_changes(prev, new) == []
