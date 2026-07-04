from decimal import Decimal
from pathlib import Path

import pytest

from app.parse.extractor import clean_price, extract

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("12 990 ₽", Decimal("12990")),
        ("12 990", Decimal("12990")),
        ("3 248,50 ₽", Decimal("3248.50")),
        ("", None),
        ("нет", None),
        ("0 ₽", None),
    ],
)
def test_clean_price(raw, expected):
    assert clean_price(raw) == expected


def test_extract_in_stock_with_discount():
    result = extract(_load("product_in_stock_discount.html"))
    assert result.is_usable()
    assert result.price == Decimal("12990")
    assert result.old_price == Decimal("14990")
    assert result.in_stock is True
    assert result.discount_pct is not None and result.discount_pct > 0
    assert any("Распродажа" in p for p in result.promo_labels)
    assert result.raw_hash


def test_extract_live_data_qa_fields():
    # Mirrors the live vseinstrumenti.ru DOM (data-qa selectors + coupon button).
    result = extract(_load("product_live_data_qa.html"))
    assert result.is_usable()
    assert result.price == Decimal("13990")
    assert result.old_price == Decimal("15545")
    assert result.discount_pct == Decimal("10.00")
    assert result.in_stock is True
    joined = " | ".join(result.promo_labels)
    assert "Распродажа остатков!" in result.promo_labels
    assert "Промокод: B2B258K1" in result.promo_labels
    assert "для бизнеса" in joined


def test_extract_out_of_stock():
    result = extract(_load("product_out_of_stock.html"))
    assert result.is_usable()
    assert result.price == Decimal("5490")
    assert result.in_stock is False
    assert result.discount_pct is None


def test_extract_empty_html():
    result = extract("")
    assert not result.success
    assert result.error == "empty_html"


def test_extract_garbage_html():
    result = extract("<html><body><p>hello</p></body></html>")
    assert not result.is_usable()
