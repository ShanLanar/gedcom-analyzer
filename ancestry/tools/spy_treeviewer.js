/* ===========================================================================
 * Ancestry – Tree-Viewer-Spion (echte Ahnentafel / Pedigree, 4+ Gen.)
 * ===========================================================================
 *
 * ZWECK
 *   Findet den Endpunkt, der die ECHTE Ahnentafel eines Baums liefert
 *   (alle Vorfahren einer Person, nicht nur die gemeinsamen). Speichert die
 *   KOMPLETTEN Antworten der baum-/ahnen-relevanten Aufrufe in
 *   "ancestry_spy_treeviewer.json".
 *
 * ANLEITUNG
 *   1. Öffne den Baum-Viewer eines Match-Baums in der PEDIGREE-/Stammbaum-Ansicht.
 *      Aus dem Compare-Befund kennen wir z.B. den Baum eines Matches:
 *        treeId = 202129372 , personId = 282645439793   (Match "Rustmeier")
 *      URL-Vorlagen (eine probieren, bis der Fächer-Baum erscheint):
 *        https://www.ancestry.com/family-tree/tree/202129372/family?cfpid=282645439793
 *        https://www.ancestry.com/family-tree/person/tree/202129372/person/282645439793/facts
 *      → Warten, bis der Stammbaum mit mehreren Generationen sichtbar ist.
 *      → Falls vorhanden: einmal auf "Pedigree"/"Ahnentafel"-Ansicht umschalten
 *        und 1–2 Generationen aufklappen, damit die Ahnen-Anfragen feuern.
 *   2. F12 → "Console" → diesen GESAMTEN Text einfügen → Enter.
 *   3. Das Overlay sammelt baum-/ahnen-relevante Antworten vollständig nach.
 *   4. Nach ~25 Sek. lädt "ancestry_spy_treeviewer.json" → hier einfügen.
 *
 * Liest nur – ändert nichts.
 * ========================================================================= */

(async () => {
  "use strict";

  // Baum/Ahnen-relevante Endpunkte → volle Antwort speichern.
  const TREE_HINT = /tree|pedigree|ancestor|family|person|node|generation|kinship|lineage|relative|forebear|fan/i;
  const API_HINT  = /\/api\/|treesui|trees\/|family-tree|discoveryui|mediasvc|person/i;
  const IGNORE = [
    "ube-torrent", "/events", "newrelic", "nr-data", "/log", "telemetry",
    "google", "doubleclick", "adobe", "/akam/", "qualtrics", "hotjar",
    "/metrics", "/beacon", "fonts.", ".css", ".js", ".png", ".jpg", ".jpeg",
    ".svg", ".woff", ".gif", "/ping", "optimizely", "/static/", "/media/",
    "image/namespaces",
  ];
  const isApi  = (u) => !!u && API_HINT.test(u) &&
                        !IGNORE.some(s => u.toLowerCase().includes(s));
  const isTree = (u) => isApi(u) && TREE_HINT.test(u);

  const captures = [];   // baum/ahnen-relevant → volle Antwort
  const others   = [];   // sonstige API-Calls → URL + Kopf
  const seen = new Set();

  function keysOf(text) {
    try {
      const j = JSON.parse(text);
      return Array.isArray(j) ? ["<array len=" + j.length + ">"]
                              : Object.keys(j || {});
    } catch (e) { return null; }
  }
  function add(method, url, reqBody, respText, source) {
    const rec = {
      method, url, source,
      requestBody: reqBody ? String(reqBody).slice(0, 1200) : null,
      topKeys: keysOf(respText),
    };
    if (isTree(url)) {
      rec.responseFull = String(respText).slice(0, 400000);
      captures.push(rec);
    } else {
      rec.sample = String(respText).slice(0, 300);
      others.push(rec);
    }
  }

  // ── Live-Hooks ──────────────────────────────────────────────────────────────
  const _fetch = window.fetch;
  window.fetch = async function (input, init) {
    const url = (typeof input === "string") ? input : (input && input.url);
    const method = (init && init.method) || "GET";
    const body = init && init.body;
    const resp = await _fetch.apply(this, arguments);
    if (isApi(url) && !seen.has("L:" + url)) {
      seen.add("L:" + url);
      try { resp.clone().text().then(t => add(method, url, body, t, "live")); } catch (e) {}
    }
    return resp;
  };
  const _open = XMLHttpRequest.prototype.open;
  const _send = XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.open = function (m, u) { this.__m=m; this.__u=u; return _open.apply(this, arguments); };
  XMLHttpRequest.prototype.send = function (b) {
    this.addEventListener("load", function () {
      if (isApi(this.__u) && !seen.has("L:" + this.__u)) {
        seen.add("L:" + this.__u);
        try { add(this.__m, this.__u, b, this.responseText, "live"); } catch (e) {}
      }
    });
    return _send.apply(this, arguments);
  };

  // ── Overlay ─────────────────────────────────────────────────────────────────
  const box = document.createElement("div");
  box.style.cssText =
    "position:fixed;right:16px;bottom:16px;z-index:2147483647;background:#15321f;" +
    "color:#fff;font:14px/1.4 system-ui,sans-serif;padding:14px 18px;border-radius:10px;" +
    "box-shadow:0 4px 18px rgba(0,0,0,.4);max-width:380px;";
  document.body.appendChild(box);
  const setMsg = (h) => { box.innerHTML = h; };
  const sleep = (ms) => new Promise(r => setTimeout(r, ms));

  // ── Bereits geladene GETs nachholen (volle Antwort) ─────────────────────────
  setMsg("<b>Tree-Viewer-Spion</b><br>Interagiere jetzt mit dem Baum (aufklappen)…");
  await sleep(3000);  // dem Nutzer Zeit zum Aufklappen geben

  const urls = performance.getEntriesByType("resource").map(e => e.name).filter(isApi);
  const uniqueGets = [...new Set(urls)].slice(0, 120);

  let i = 0;
  for (const url of uniqueGets) {
    i++;
    if (!seen.has("R:" + url)) {
      seen.add("R:" + url);
      try {
        const r = await _fetch(url, { credentials: "include",
          headers: { "Accept": "application/json" } });
        const t = await r.text();
        add("GET", url, null, t, "replay");
      } catch (e) {}
    }
    setMsg("<b>Tree-Viewer-Spion</b><br>Hole Antworten nach: " + i + "/" +
           uniqueGets.length + "<br>Baum-Treffer: " + captures.length);
    await sleep(110);
  }

  await sleep(3000);  // letzte Live-Anfragen abwarten

  // ── Download ────────────────────────────────────────────────────────────────
  window.fetch = _fetch;
  XMLHttpRequest.prototype.open = _open;
  XMLHttpRequest.prototype.send = _send;

  const payload = { pageUrl: location.href, treeEndpoints: captures, otherApiCalls: others };
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = "ancestry_spy_treeviewer.json";
  document.body.appendChild(a); a.click(); a.remove();

  setMsg("✅ <b>Fertig.</b> " + captures.length + " Baum-Endpunkte (voll), " +
         others.length + " weitere.<br>Datei <b>ancestry_spy_treeviewer.json</b> im Chat einfügen.");
})();
