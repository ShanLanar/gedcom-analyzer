"""Regressionstest: Buchlisten-Pagination cappte früher bei 100 (2×50)."""
from ancestry.tools.fetch_matricula_books import _MAX_BOOK_PAGES, _with_page


def test_with_page_appends_param():
    url = "https://data.matricula-online.eu/de/deutschland/osnabrueck/x/"
    assert _with_page(url, 2) == url + "?page=2"


def test_with_page_replaces_existing():
    out = _with_page("https://ex.com/x/?page=1", 3)
    assert "page=3" in out
    assert out.count("page=") == 1          # ersetzt, nicht angehängt


def test_with_page_keeps_other_params():
    out = _with_page("https://ex.com/x/?foo=bar", 5)
    assert "foo=bar" in out
    assert "page=5" in out


def test_max_pages_high_enough():
    # 200 Seiten × 50 Bücher = 10 000 – weit über jeder realen Pfarrei.
    assert _MAX_BOOK_PAGES >= 100
