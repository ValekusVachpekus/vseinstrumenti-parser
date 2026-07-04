from __future__ import annotations

import re

BASE = "https://www.vseinstrumenti.ru"

# /product/<slug>-<id>/  ->  id is the trailing digit group of the last path segment.
_PRODUCT_PATH_RE = re.compile(r"/product/(?P<slug>[a-z0-9\-]+?)-(?P<id>\d+)/?$", re.IGNORECASE)
_ID_RE = re.compile(r"^\d+$")


class InvalidProductUrl(ValueError):
    pass


def parse_product_ref(ref: str) -> tuple[str, str | None]:
    """
    Accept a full product URL or a bare numeric product id.
    Return (vi_product_id, slug|None).
    """
    ref = ref.strip()
    if _ID_RE.match(ref):
        return ref, None

    # Tolerate protocol-less or www-less input.
    candidate = ref
    if candidate.startswith("//"):
        candidate = "https:" + candidate
    if not candidate.startswith("http"):
        candidate = "https://" + candidate.lstrip("/")

    match = _PRODUCT_PATH_RE.search(candidate)
    if not match:
        raise InvalidProductUrl(f"Cannot extract product id from: {ref}")
    return match.group("id"), match.group("slug")


def canonical_url(vi_product_id: str, slug: str | None = None) -> str:
    if slug:
        return f"{BASE}/product/{slug}-{vi_product_id}/"
    # Without a slug the site still resolves the numeric id form.
    return f"{BASE}/product/{vi_product_id}/"
