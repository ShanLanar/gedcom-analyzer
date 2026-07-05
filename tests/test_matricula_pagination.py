"""Regressionstest: Buchlisten-Pagination cappte früher bei 100 (2×50)."""
import sys
import types

# Playwright ist in CI/Container nicht installiert; _scrape_parish_books
# importiert nur die TimeoutError-Klasse daraus → Fake-Modul genügt.
if "playwright.sync_api" not in sys.modules:
    _pw = types.ModuleType("playwright")
    _pw_sync = types.ModuleType("playwright.sync_api")
    _pw_sync.TimeoutError = type("TimeoutError", (Exception,), {})
    _pw_sync.sync_playwright = lambda *a, **k: None
    _pw.sync_api = _pw_sync
    sys.modules["playwright"] = _pw
    sys.modules["playwright.sync_api"] = _pw_sync

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


# ── Pagination-Schleife mit Fake-Playwright-page (die 100er-Cap-Regression) ────

class _FakePage:
    """Minimaler Playwright-page-Stub: liefert je ?page=N vordefinierte Zeilen."""

    def __init__(self, pages):
        self._pages = pages
        self._cur = 1

    def goto(self, url, **kw):
        import urllib.parse
        q = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(url).query))
        self._cur = int(q.get("page", "1"))

    def evaluate(self, _script):
        idx = self._cur - 1
        return self._pages[idx] if 0 <= idx < len(self._pages) else []


def _row(sig):
    return {"signatur": sig, "href": f"/de/x/{sig}/",
            "typNorm": "Taufen", "typDisplay": "Taufen", "datum": "1700",
            "datumVon": "1700", "datumBis": "1750"}


def test_pagination_collects_more_than_100():
    """Regression: früher Cap bei 2×50=100. Drei Seiten (50/50/15) → 115 Bücher."""
    from ancestry.tools.fetch_matricula_books import _scrape_parish_books
    p1 = [_row(f"a{i}") for i in range(50)]
    p2 = [_row(f"b{i}") for i in range(50)]
    p3 = [_row(f"c{i}") for i in range(15)]
    fake = _FakePage([p1, p2, p3])
    rows = _scrape_parish_books(fake, "parish", "https://x/parish/", pause=0)
    assert len(rows) == 115


def test_pagination_stops_on_empty_page():
    from ancestry.tools.fetch_matricula_books import _scrape_parish_books
    fake = _FakePage([[_row("a"), _row("b")], []])   # zweite Seite leer
    rows = _scrape_parish_books(fake, "parish", "https://x/parish/", pause=0)
    assert len(rows) == 2


def test_pagination_dedupes_signatures_across_pages():
    from ancestry.tools.fetch_matricula_books import _scrape_parish_books
    # Matricula spiegelt out-of-range ?page auf die letzte Seite → gleiche sigs
    same = [_row("a"), _row("b")]
    fake = _FakePage([same, same, same])
    rows = _scrape_parish_books(fake, "parish", "https://x/parish/", pause=0)
    assert len(rows) == 2                           # keine Duplikate
