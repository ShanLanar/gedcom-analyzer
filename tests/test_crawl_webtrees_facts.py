"""Tests für die reichhaltige Fakten-Extraktion des webtrees-Crawlers.

Eicht parse_facts/parse_individual und den GEDCOM-Export an einem an die echte
Anverwandte-/webtrees-2.2.6-Markup angelehnten Fragment: Taufe mit Matricula-
Quelle + Religion + Patin, zwei Heiraten (mit Partner-/Familien-Verweis),
Beruf, Tod mit Bemerkung. Stellt sicher, dass die Ereignisse als GEDCOM mit
Datum/Ort/Quelle/Notiz und MARR im FAM-Record landen.
"""
import json
from pathlib import Path

from ancestry.tools.crawl_webtrees import (
    parse_facts, parse_individual, _db, _save_person, export_gedcom,
)

# Verdichtetes, aber strukturtreues Fakten-Tabellen-Fragment (Theme xenea).
FACTS_HTML = """
<div class="wt-tab-facts">
  <table class="table wt-facts-table">
    <tr class="">
      <th scope="row"><div class="wt-fact-label ut">Taufe</div></th>
      <td>
        <span class="wt-fact-date-age">
          <span class="date"><a href="x">28. Januar 1804</a></span>
          <span class="age">(9 Tage alt)</span></span>
        <div class="wt-fact-place"><a class="ut" href="y">St. Remigius, Oesede, Niedersachsen, DEU</a></div>
        <div class="wt-fact-other-attributes mt-2">
          <div><span class="label">Religion</span>: <span class="value"><span class="ut">röm.-kath.</span></span></div>
        </div>
        <div class="wt-fact-notes mt-2">
          <div><span class="label">Notiz</span>: <span class="ut"><a href="https://data.matricula-online.eu/de/deutschland/osnabrueck/oesede-st-peter-und-paul/0053/?pg=40">Quelle: Matricula</a> Seite F 200; Patin: Maria Gertrud Broxtermann</span></div>
        </div>
      </td>
    </tr>
    <tr class="">
      <th scope="row"><div class="wt-fact-label ut">Beruf</div></th>
      <td>
        <div class="wt-fact-main-attributes">
          <div class="wt-fact-value"><span class="ut">Heuerling</span></div>
          <div class="wt-fact-place"><a class="ut" href="p">Oesede-Dröper, Niedersachsen, DEU</a></div>
        </div>
        <div class="wt-fact-other-attributes mt-2">
          <div><span class="label">Arbeitgeber</span>: <span class="value"><span class="ut">Musenberg</span></span></div>
        </div>
      </td>
    </tr>
    <tr class="">
      <th scope="row"><div class="wt-fact-label ut">Besitz</div></th>
      <td>
        <div class="wt-fact-notes mt-2">
          <div><span class="label">Notiz</span>: <span class="ut">Markkotten Patke; Knecht des Pastors</span></div>
        </div>
      </td>
    </tr>
    <tr class="">
      <th scope="row"><div class="wt-fact-label ut">Kirchliche Trauung</div></th>
      <td>
        <div class="wt-fact-record">
          <a href="https://x/tree/anverwandte/individual/X44331/August"><span class="NAME">August <span class="SURN">Reichert</span></span></a> —
          <a href="https://x/tree/anverwandte/family/X44332/August-Maria">Diese Familie ansehen</a>
        </div>
        <span class="date"><a href="z">24. Mai 1829</a></span>
        <div class="wt-fact-place"><a class="ut" href="w">St. Johann, Osnabrück, Niedersachsen, DEU</a></div>
        <div class="wt-fact-notes mt-2">
          <div><span class="label">Notiz</span>: <span class="ut"><a href="https://data.matricula-online.eu/de/deutschland/osnabrueck/osnabruck-st-johann/0059/?pg=1">Quelle: Matricula</a> S. 64, Nr. 11; Zeuge: Johann Brinker</span></div>
        </div>
      </td>
    </tr>
    <tr class="">
      <th scope="row"><div class="wt-fact-label ut">Tod</div></th>
      <td>
        <span class="date"><a href="z">22. Februar 1852</a></span>
        <div class="wt-fact-place"><a class="ut" href="w">Osnabrück, Niedersachsen, DEU</a></div>
        <div class="wt-fact-notes mt-2">
          <div><span class="label">Notiz</span>: <span class="ut">Witwer heiratet erneut.</span></div>
        </div>
      </td>
    </tr>
    <tr class="">
      <th scope="row"><div class="wt-fact-label ut">Letzte Änderung</div></th>
      <td><span class="date"><a href="z">6. April 2023</a></span></td>
    </tr>
  </table>
</div>
"""


def test_parse_facts_extracts_events():
    facts = parse_facts(FACTS_HTML)
    tags = [f["tag"] for f in facts]
    # Letzte Änderung wird ausgelassen
    assert tags == ["BAPM", "OCCU", "PROP", "MARR", "DEAT"]

    bapm = facts[0]
    assert bapm["date"] == "28. Januar 1804"
    assert bapm["place"].startswith("St. Remigius, Oesede")
    assert bapm["religion"] == "röm.-kath."
    assert "Patin: Maria Gertrud Broxtermann" in bapm["note"]
    assert "matricula-online.eu" in bapm["matricula_url"]

    occu = facts[1]
    assert occu["value"] == "Heuerling"
    assert occu["employer"] == "Musenberg"
    assert occu["place"].startswith("Oesede-Dröper")

    prop = facts[2]
    assert prop["tag"] == "PROP"
    assert "Markkotten Patke" in prop["note"]

    marr = facts[3]
    assert marr["tag"] == "MARR"
    assert marr["spouse_id"] == "X44331"
    assert marr["family_id"] == "X44332"
    assert marr["date"] == "24. Mai 1829"
    assert "Zeuge: Johann Brinker" in marr["note"]


def test_parse_individual_convenience_fields():
    url = "https://x/tree/anverwandte/individual/I11925/Maria"
    p = parse_individual(FACTS_HTML, url)
    assert p["occupation"] == "Heuerling"
    assert p["religion"] == "röm.-kath."
    assert any("Patin" in n for n in p["notes"])
    # Geburts-/Todesdaten aus Fakten ergänzt (kein h2-Titel im Fragment)
    assert p["death_date"] == "22. Februar 1852"


def test_export_gedcom_emits_rich_events(tmp_path: Path):
    url_a = "https://x/tree/anverwandte/individual/I11925/Maria"
    pa = parse_individual(FACTS_HTML, url_a)
    pa["id"] = "I11925"
    pa["sex"] = "F"
    pa["spouses_ids"] = ["X44331"]

    dbp = tmp_path / "t.db"
    c = _db(dbp)
    _save_person(c, pa, "I11925", url_a, tree_source="anverwandte")
    spouse = {**{k: "" for k in pa}, "id": "X44331", "given_name": "August",
              "surname": "Reichert", "sex": "M", "name": "August Reichert",
              "spouse_names": [], "child_names": [], "matricula": [],
              "facts": [], "occupation": "", "religion": "", "notes": [],
              "parents": [], "children": [], "spouses_ids": ["I11925"],
              "siblings": [], "related": [], "families": [],
              "url": "https://x/tree/anverwandte/individual/X44331/August"}
    _save_person(c, spouse, "X44331", spouse["url"], tree_source="anverwandte")
    import sqlite3  # noqa: F401
    c.execute("UPDATE wt_persons SET spouses_json=? WHERE id=?",
              (json.dumps(["X44331"]), "I11925"))
    c.commit(); c.close()

    out = tmp_path / "t.ged"
    export_gedcom(dbp, str(out), tree_source="anverwandte")
    ged = out.read_text(encoding="utf-8")

    assert "1 BAPM" in ged
    # Ort kann durch die Ortskonkordanz übersetzt werden – Präfix bleibt stabil.
    assert "2 PLAC St. Remigius, Oesede" in ged
    assert "1 OCCU Heuerling" in ged
    assert "2 SOUR @S2@" in ged          # Matricula als Ereignis-Quelle
    assert "Patin: Maria Gertrud Broxtermann" in ged
    # Heirat im FAM-Record mit Datum
    assert "1 MARR" in ged
    assert "2 DATE 24. Mai 1829" in ged
    # Keine MARR im INDI-Record
    indi_block = ged.split("0 @F", 1)[0]
    assert "1 MARR" not in indi_block


def test_training_run_saves_html_json_and_zip(tmp_path, monkeypatch):
    import zipfile
    import ancestry.tools.crawl_webtrees as cw

    graph = {"I1": ["I2", "I3"], "I2": ["I1", "I4"], "I3": ["I1"],
             "I4": ["I2", "I5"], "I5": ["I4"]}

    def fake_init(self, base, **kw):
        self.base = base; self.delay = 0; self._last = 0
        self._extra_headers = {}; self._perm_fail = set(); self.robots = None
        import http.cookiejar
        import urllib.request as rq
        self._cookie_jar = http.cookiejar.CookieJar()
        self._opener = rq.build_opener()

    def fake_get(self, url, *a, **k):
        import re
        pid = re.search(r"/individual/(I\d+)", url).group(1)
        links = "".join(
            f'<a href="/tree/anverwandte/individual/{r}/x">x</a>'
            for r in graph.get(pid, []))
        return f"<html><div class='wt-fact-label ut'>Geburt</div>{links}</html>"

    monkeypatch.setattr(cw.Fetcher, "__init__", fake_init)
    monkeypatch.setattr(cw.Fetcher, "get", fake_get)

    out = tmp_path / "training_pages"
    res = cw.training_run(
        "https://x/tree/anverwandte/individual/I1/Seed",
        n_pages=4, out_dir=out, delay=0)
    assert res == out
    # Roh-HTML + Parser-JSON je Seite + Manifest
    assert sorted(p.name for p in out.glob("*.html")) == \
        ["I1.html", "I2.html", "I3.html", "I4.html"]
    assert (out / "I1.json").exists()
    assert (out / "_manifest.json").exists()
    # ZIP-Beigabe enthält HTML, JSON und Manifest
    zp = out.with_suffix(".zip")
    assert zp.exists()
    names = zipfile.ZipFile(zp).namelist()
    assert "_manifest.json" in names and "I1.html" in names and "I1.json" in names
