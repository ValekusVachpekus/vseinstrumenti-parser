from __future__ import annotations

import hashlib
import json
import re
from decimal import Decimal, InvalidOperation

from selectolax.parser import HTMLParser

from app.parse.types import ExtractResult

# Promo/discount keywords seen on vseinstrumenti.ru cards. Extend as observed.
PROMO_KEYWORDS = (
    "распродажа",
    "скидка",
    "акция",
    "промокод",
    "выгода",
    "спеццена",
    "уценка",
    "для бизнеса",
)

_OUT_OF_STOCK_MARKERS = ("нет в наличии", "нет на складе", "снят с производства", "под заказ")
_IN_STOCK_MARKERS = ("в наличии", "самовывоз", "курьером", "доставка завтра", "доставка сегодня")

_PRICE_CLEAN_RE = re.compile(r"[^\d,\.]")


def clean_price(text: str | None) -> Decimal | None:
    """Parse '12 990 ₽' / '12\\u00a0990' / '3 248,50' into a Decimal."""
    if not text:
        return None
    normalized = text.replace(" ", " ").replace(",", ".")
    normalized = _PRICE_CLEAN_RE.sub("", normalized)
    if not normalized:
        return None
    # Keep only the first dotted group if multiple dots slipped in.
    parts = normalized.split(".")
    if len(parts) > 2:
        normalized = "".join(parts[:-1]) + "." + parts[-1]
    try:
        value = Decimal(normalized)
    except InvalidOperation:
        return None
    return value if value > 0 else None


def _availability_to_bool(text: str | None) -> bool | None:
    if not text:
        return None
    low = text.lower()
    if "outofstock" in low.replace(" ", "") or any(m in low for m in _OUT_OF_STOCK_MARKERS):
        return False
    if "instock" in low.replace(" ", "") or any(m in low for m in _IN_STOCK_MARKERS):
        return True
    return None


def _compute_discount(price: Decimal | None, old_price: Decimal | None) -> Decimal | None:
    if price is None or old_price is None or old_price <= 0 or old_price <= price:
        return None
    pct = (old_price - price) / old_price * Decimal(100)
    return pct.quantize(Decimal("0.01"))


def _state_hash(result: ExtractResult) -> str:
    parts = [
        str(result.price),
        str(result.old_price),
        str(result.in_stock),
        "|".join(sorted(result.promo_labels)),
    ]
    return hashlib.sha256("::".join(parts).encode("utf-8")).hexdigest()


# --- Strategy 1: JSON-LD (schema.org Product/Offer) ---------------------------


def _iter_ld_objects(tree: HTMLParser):
    for node in tree.css('script[type="application/ld+json"]'):
        raw = node.text(deep=True, strip=True)
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            continue
        stack = [data]
        while stack:
            item = stack.pop()
            if isinstance(item, list):
                stack.extend(item)
            elif isinstance(item, dict):
                if "@graph" in item and isinstance(item["@graph"], list):
                    stack.extend(item["@graph"])
                yield item


def extract_jsonld(tree: HTMLParser) -> ExtractResult | None:
    for obj in _iter_ld_objects(tree):
        obj_type = obj.get("@type")
        if obj_type != "Product" and not (isinstance(obj_type, list) and "Product" in obj_type):
            continue

        offers = obj.get("offers")
        if isinstance(offers, list):
            offers = offers[0] if offers else None
        if not isinstance(offers, dict):
            offers = {}

        price = clean_price(str(offers.get("price"))) if offers.get("price") else None
        availability = offers.get("availability")
        result = ExtractResult(
            success=True,
            source="jsonld",
            title=obj.get("name"),
            price=price,
            in_stock=_availability_to_bool(availability),
            availability_raw=availability,
        )
        if result.is_usable():
            return result
    return None


# --- Strategy 2: microdata / HTML selectors -----------------------------------


def _first_attr(tree: HTMLParser, selector: str, attr: str) -> str | None:
    node = tree.css_first(selector)
    if node is None:
        return None
    return node.attributes.get(attr)


def _first_text(tree: HTMLParser, selector: str) -> str | None:
    node = tree.css_first(selector)
    if node is None:
        return None
    text = node.text(deep=True, strip=True)
    return text or None


def extract_html(tree: HTMLParser) -> ExtractResult | None:
    # Current price: live `data-qa` first, then microdata fallbacks.
    price = clean_price(_first_text(tree, '[data-qa="price-now"]'))
    if price is None:
        price = clean_price(_first_attr(tree, 'meta[itemprop="price"]', "content"))
    if price is None:
        price = clean_price(_first_text(tree, '[data-qa="product-price-current"]'))
    if price is None:
        price = clean_price(_first_text(tree, '[itemprop="price"]'))

    old_price = clean_price(_first_text(tree, '[data-qa="price-old"]'))
    if old_price is None:
        old_price = clean_price(_first_text(tree, '[data-qa="product-price-old"]'))

    availability_text = (
        _first_text(tree, '[data-qa="availability-info"]')
        or _first_text(tree, '[data-qa="product-availability"]')
        or _first_text(tree, '[data-qa="availability"]')
    )
    avail_href = _first_attr(tree, 'meta[itemprop="availability"]', "href") or _first_attr(
        tree, 'link[itemprop="availability"]', "href"
    )
    availability_raw = availability_text or avail_href

    title = _first_text(tree, "h1") or _first_attr(
        tree, 'meta[property="og:title"]', "content"
    )

    promo_labels = _collect_promos(tree)

    result = ExtractResult(
        success=True,
        source="html",
        title=title,
        price=price,
        old_price=old_price,
        in_stock=_availability_to_bool(availability_raw),
        availability_raw=availability_raw,
        promo_labels=promo_labels,
    )
    return result if result.is_usable() else None


# A promo code: short uppercase latin/digit token (e.g. B2B258K1).
_PROMO_CODE_RE = re.compile(r"^[A-Z0-9]{5,15}$")


def _add(found: list[str], text: str | None) -> None:
    text = (text or "").strip()
    if text and text not in found:
        found.append(text)


def _collect_promos(tree: HTMLParser) -> list[str]:
    found: list[str] = []

    # Promo badges ("Распродажа остатков!", etc.) and the savings nameplate.
    for node in tree.css('[data-qa="nameplate"]'):
        _add(found, node.text(deep=True, strip=True))
    _add(found, _first_text(tree, '[data-qa="price-discount"]'))

    # Promo codes rendered inside copy buttons (e.g. "-25% для бизнеса" → B2B258K1).
    for btn in tree.css("button"):
        text = btn.text(deep=True, strip=True)
        if text and _PROMO_CODE_RE.match(text):
            _add(found, f"Промокод: {text}")

    # Keyword fallback for any other short promo lines.
    body = tree.body or tree.root
    if body is not None:
        for node in body.css("span, div, a, li, p"):
            text = node.text(deep=False, strip=True)
            if not text or len(text) > 60:
                continue
            if any(kw in text.lower() for kw in PROMO_KEYWORDS):
                _add(found, text)

    return found[:12]


# --- Public entry point -------------------------------------------------------


def extract(html: str) -> ExtractResult:
    """Run the strategy chain over raw HTML and return a normalized result."""
    if not html or not html.strip():
        return ExtractResult(success=False, error="empty_html")

    tree = HTMLParser(html)

    result = extract_jsonld(tree)
    html_result = extract_html(tree)

    if result is None:
        result = html_result
    elif html_result is not None:
        # Enrich JSON-LD result with fields it usually lacks.
        result.old_price = result.old_price or html_result.old_price
        result.promo_labels = result.promo_labels or html_result.promo_labels
        result.title = result.title or html_result.title
        if result.in_stock is None:
            result.in_stock = html_result.in_stock
            result.availability_raw = result.availability_raw or html_result.availability_raw

    if result is None or not result.is_usable():
        return ExtractResult(success=False, error="no_usable_fields")

    result.discount_pct = _compute_discount(result.price, result.old_price)
    result.raw_hash = _state_hash(result)
    return result
