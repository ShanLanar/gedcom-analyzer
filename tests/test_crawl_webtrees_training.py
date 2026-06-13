"""Tests für den webtrees-Trainingslauf (training_run).

Stellt sicher, dass die Stichprobe ohne Netz funktioniert: Roh-HTML + Parser-
JSON je besuchter Person werden geschrieben, ein _manifest.json fasst zusammen,
die Breitensuche folgt den Verwandtschafts-Links und das Seiten-Limit wird
eingehalten. Der Fetcher wird gemockt — es geht kein echter Request raus.
"""
import json

import ancestry.tools.crawl_webtrees as cw


def _page(ind_id: str, links: list[str]) -> str:
    """Minimales, parser-taugliches webtrees-Seitenfragment mit Nachbar-Links."""
    tree = "anverwandte"
    rels = "".join(
        f'<a href="/tree/{tree}/individual/{lid}/x">Nachbar {lid}</a>'
        for lid in links
    )
    return (
        f'<title>{ind_id} 1800–1860</title>'
        f'<bdi>Max* /Muster{ind_id}/</bdi>'
        f'{rels}'
    )


class _FakeFetcher:
    """Ersetzt Fetcher: liefert HTML aus einer ID→Seiten-Map, kein Netzverkehr."""

    def __init__(self, pages: dict[str, str]):
        self._pages = pages
        self.requested: list[str] = []

    def get(self, url: str, *a, **k) -> str | None:
        ind_id = (cw._IND_RE.search(url) or [None, ""])[1]
        self.requested.append(ind_id)
        return self._pages.get(ind_id)


def test_training_run_saves_html_json_and_manifest(tmp_path, monkeypatch):
    # Kleiner Baum: I1 → I2, I3 ; I2 → I4
    pages = {
        "I1": _page("I1", ["I2", "I3"]),
        "I2": _page("I2", ["I4"]),
        "I3": _page("I3", []),
        "I4": _page("I4", []),
    }
    fake = _FakeFetcher(pages)
    monkeypatch.setattr(cw, "Fetcher", lambda *a, **k: fake)

    seed = "https://example.org/tree/anverwandte/individual/I1/Max"
    out = cw.training_run(seed, n_pages=100, delay=0, out_dir=tmp_path)

    assert out == tmp_path
    # Alle vier Personen besucht und als HTML + JSON gesichert
    for pid in ("I1", "I2", "I3", "I4"):
        assert (tmp_path / f"{pid}.html").exists()
        data = json.loads((tmp_path / f"{pid}.json").read_text(encoding="utf-8"))
        assert data["id"] == pid
        assert "_parse_error" not in data        # sauber geparst

    manifest = json.loads((tmp_path / "_manifest.json").read_text(encoding="utf-8"))
    assert manifest["saved"] == 4
    assert manifest["parse_errors"] == 0
    assert {m["id"] for m in manifest["pages"]} == {"I1", "I2", "I3", "I4"}


def test_training_run_respects_page_limit(tmp_path, monkeypatch):
    # Kette I1→I2→I3→… ; Limit 2 muss nach zwei Seiten stoppen
    pages = {f"I{i}": _page(f"I{i}", [f"I{i + 1}"]) for i in range(1, 6)}
    fake = _FakeFetcher(pages)
    monkeypatch.setattr(cw, "Fetcher", lambda *a, **k: fake)

    seed = "https://example.org/tree/anverwandte/individual/I1/Max"
    cw.training_run(seed, n_pages=2, delay=0, out_dir=tmp_path)

    manifest = json.loads((tmp_path / "_manifest.json").read_text(encoding="utf-8"))
    assert manifest["saved"] == 2
    assert len(fake.requested) == 2          # nicht mehr geholt als nötig


def test_training_run_records_unreachable_pages(tmp_path, monkeypatch):
    # I1 verlinkt I2 (privat → kein HTML). I2 wird übersprungen, nicht gesichert.
    pages = {"I1": _page("I1", ["I2"])}       # I2 fehlt → get() liefert None
    fake = _FakeFetcher(pages)
    monkeypatch.setattr(cw, "Fetcher", lambda *a, **k: fake)

    seed = "https://example.org/tree/anverwandte/individual/I1/Max"
    cw.training_run(seed, n_pages=100, delay=0, out_dir=tmp_path)

    assert (tmp_path / "I1.html").exists()
    assert not (tmp_path / "I2.html").exists()
    manifest = json.loads((tmp_path / "_manifest.json").read_text(encoding="utf-8"))
    assert manifest["saved"] == 1
    assert manifest["skipped"] == 1
