/* ===========================================================================
 * Ancestry DNA – Namen-Export direkt im Browser
 * ===========================================================================
 *
 * WAS MACHT DAS?
 *   Lädt für ALLE DNA-Matches die echten Namen und speichert sie als Datei
 *   "ancestry_names_<GUID>.json". Diese Datei dann im Tool über
 *   "Namen importieren" einlesen – fertig.
 *
 * WARUM IM BROWSER?
 *   Der Namen-Endpunkt (profileData) lehnt Anfragen von außerhalb des
 *   Browsers ab (HTTP 303). Im Browser selbst funktioniert er einwandfrei,
 *   weil hier alle Sicherheits-Header automatisch mitgeschickt werden.
 *
 * ANLEITUNG (3 Schritte):
 *   1. Im Browser einloggen und die DNA-Match-Liste öffnen:
 *        https://www.ancestry.com/discoveryui-matches/list/<DEINE-KIT-GUID>
 *   2. F12 drücken → Reiter "Console" → diesen GESAMTEN Text einfügen → Enter
 *   3. Warten. Unten rechts läuft ein Fortschrittsbalken. Am Ende lädt sich
 *      automatisch eine JSON-Datei herunter. Diese im Tool importieren.
 *
 * Es wird NICHTS verändert – nur gelesen. Komplett ungefährlich.
 * ========================================================================= */

(async () => {
  "use strict";

  // ── Konfiguration ─────────────────────────────────────────────────────────
  const LIST_BASE    = "/discoveryui-matches/parents/list/api/matchList";
  const PROFILE_BASE = "/discoveryui-matches/cluster/api/profileData";
  const PAGE_SIZE    = 100;   // Matches pro matchList-Seite
  const NAME_BATCH   = 20;    // sampleIds pro profileData-Request
  const DELAY_MS     = 120;   // Pause zwischen Requests (schont den Server)

  // ── test_guid aus der URL holen ───────────────────────────────────────────
  const guidMatch = location.pathname.match(/[0-9A-Fa-f-]{36}/);
  const TEST_GUID = guidMatch ? guidMatch[0]
                              : prompt("Test-GUID (aus der Match-Listen-URL):");
  if (!TEST_GUID) { alert("Keine Test-GUID gefunden – abgebrochen."); return; }

  // ── CSRF-Token roh aus dem Cookie lesen ──────────────────────────────────
  function getCookie(name) {
    const m = document.cookie.match(new RegExp("(?:^|; )" +
      name.replace(/([.$?*|{}()\[\]\\\/\+^])/g, "\\$1") + "=([^;]*)"));
    return m ? m[1] : "";           // bewusst NICHT dekodieren (%7C bleibt %7C)
  }
  const CSRF = getCookie("_dnamatches-matchlistui-x-csrf-token")
            || getCookie("_csrf");

  // ── kleines Fortschritts-Overlay (kein Konsolen-Lesen nötig) ──────────────
  const box = document.createElement("div");
  box.style.cssText =
    "position:fixed;right:16px;bottom:16px;z-index:2147483647;" +
    "background:#1b3a2b;color:#fff;font:14px/1.4 system-ui,sans-serif;" +
    "padding:14px 18px;border-radius:10px;box-shadow:0 4px 18px rgba(0,0,0,.4);" +
    "max-width:340px;";
  box.innerHTML = "<b>Ancestry Namen-Export</b><br><span id='ax-msg'>Starte …</span>";
  document.body.appendChild(box);
  const setMsg = (html) => {
    const el = document.getElementById("ax-msg");
    if (el) el.innerHTML = html;
  };
  const sleep = (ms) => new Promise(r => setTimeout(r, ms));

  // ── Helfer: JSON-fetch mit den richtigen Headern ──────────────────────────
  async function getJSON(url) {
    const r = await fetch(url, {
      credentials: "include",
      headers: { "Accept": "application/json", "X-Requested-With": "XMLHttpRequest" },
    });
    if (!r.ok) throw new Error("GET " + url + " → HTTP " + r.status);
    return r.json();
  }

  async function postNames(sampleIds) {
    const headers = {
      "Accept": "application/json",
      "Content-Type": "application/json",
      "X-Requested-With": "XMLHttpRequest",
    };
    if (CSRF) headers["X-CSRF-Token"] = CSRF;   // roh, wie der Browser es tut
    const r = await fetch(PROFILE_BASE + "/" + TEST_GUID, {
      method: "POST",
      credentials: "include",
      headers,
      body: JSON.stringify({ matchSampleIds: sampleIds }),
    });
    if (!r.ok) throw new Error("profileData → HTTP " + r.status);
    return r.json();
  }

  try {
    // ── 1) Alle sampleIds über matchList einsammeln ─────────────────────────
    setMsg("Lese Match-Liste …");
    const ids = [];
    let page = 1, totalPages = 1;
    do {
      const url = LIST_BASE + "/" + TEST_GUID +
                  "?currentPage=" + page + "&itemsPerPage=" + PAGE_SIZE;
      const d = await getJSON(url);
      totalPages = d.totalPages || (d.paging && d.paging.totalPages) || totalPages;
      let rows = d.matchList || d.matchGroups || d.matches || d.data || [];
      if (rows.length && rows[0] && rows[0].matches) {
        rows = rows.flatMap(g => g.matches || []);
      }
      for (const m of rows) {
        const sid = m.sampleId || m.testGuid || m.guid;
        if (sid) ids.push(sid);
      }
      setMsg("Match-Liste: Seite " + page + "/" + totalPages +
             " – " + ids.length + " Matches");
      page++;
      await sleep(DELAY_MS);
    } while (page <= totalPages);

    if (!ids.length) { setMsg("⚠️ Keine Matches gefunden."); return; }

    // ── 2) Namen in 20er-Batches über profileData laden ─────────────────────
    const out = [];            // [{sampleId, name}]
    let done = 0, fails = 0;
    for (let i = 0; i < ids.length; i += NAME_BATCH) {
      const batch = ids.slice(i, i + NAME_BATCH);
      try {
        const data = await postNames(batch);
        for (const sid of Object.keys(data || {})) {
          const info = data[sid] || {};
          const name = (info.matchName || info.managedName || "").trim();
          if (name) out.push({ sampleId: sid, name });
        }
      } catch (e) {
        fails++;
        if (fails <= 3) console.warn(e.message);
        if (fails === 1 && String(e.message).includes("303")) {
          setMsg("⚠️ profileData lehnt ab (303). Seite neu laden und Skript " +
                 "ERNEUT als Erstes einfügen.");
        }
      }
      done = Math.min(i + NAME_BATCH, ids.length);
      setMsg("Namen: " + done + "/" + ids.length +
             " – gefunden: " + out.length +
             (fails ? " – Fehler: " + fails : ""));
      await sleep(DELAY_MS);
    }

    if (!out.length) {
      setMsg("⚠️ Keine Namen geladen (alle Anfragen abgelehnt). " +
             "Seite neu laden und Skript sofort erneut einfügen.");
      return;
    }

    // ── 3) Als Datei herunterladen ──────────────────────────────────────────
    const blob = new Blob([JSON.stringify(out, null, 2)],
                          { type: "application/json" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "ancestry_names_" + TEST_GUID + ".json";
    document.body.appendChild(a);
    a.click();
    a.remove();

    setMsg("✅ Fertig: " + out.length + " Namen gespeichert.<br>" +
           "Datei <b>" + a.download + "</b> jetzt im Tool über " +
           "<b>Namen importieren</b> einlesen.");
  } catch (e) {
    setMsg("❌ Fehler: " + (e && e.message ? e.message : e));
    console.error(e);
  }
})();
