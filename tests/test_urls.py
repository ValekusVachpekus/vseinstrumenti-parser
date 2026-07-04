import pytest

from app.parse.urls import InvalidProductUrl, canonical_url, parse_product_ref


def test_parse_full_url():
    vi_id, slug = parse_product_ref(
        "https://www.vseinstrumenti.ru/product/perforator-makita-hr2470x15-814840/"
    )
    assert vi_id == "814840"
    assert slug == "perforator-makita-hr2470x15"


def test_parse_url_without_scheme():
    vi_id, slug = parse_product_ref(
        "www.vseinstrumenti.ru/product/perforator-sturm-rh2520m-221673"
    )
    assert vi_id == "221673"
    assert slug == "perforator-sturm-rh2520m"


def test_parse_bare_id():
    vi_id, slug = parse_product_ref("814840")
    assert vi_id == "814840"
    assert slug is None


def test_parse_invalid():
    with pytest.raises(InvalidProductUrl):
        parse_product_ref("https://www.vseinstrumenti.ru/category/perforatory-32/")


def test_canonical_url():
    assert (
        canonical_url("814840", "perforator-makita-hr2470x15")
        == "https://www.vseinstrumenti.ru/product/perforator-makita-hr2470x15-814840/"
    )
    assert canonical_url("814840") == "https://www.vseinstrumenti.ru/product/814840/"
