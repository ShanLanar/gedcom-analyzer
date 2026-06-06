/* ===========================================================================
 * Ancestry DNA – Pedigree-Spion (volle Ahnentafel eines Matches)
 * ===========================================================================
 *
 * ZWECK
 *   Findet den Endpunkt, der die VOLLE Ahnentafel (Pedigree, 4+ Gen.) des
 *   Matches auf der Compare-Seite liefert – inkl. aller Vorfahren, nicht nur
 *   der gemeinsamen. Speichert die KOMPLETTEN Antworten (nicht gekürzt) der
 *   baum-relevanten Endpunkte in "ancestry_spy_pedigree.json".
 *
 * ANLEITUNG
 *   1. Compare-Seite öffnen und VOLLSTÄNDIG laden lassen, z.B.:
 *      https://www.ancestry.com/dna/matches/BEC4AE66-352E-406F-B2DA-6BC5D4DED923/compare/49924FD7-...
 *      (warten, bis der Ahnen-Baum/Pedigree sichtbar ist; falls es einen
 *       "Baum ansehen"/"View tree"-Tab gibt, draufklicken und laden lassen)
 *   2. F12 → "Console" → diesen GESAMTEN Text einfügen → Enter
 *   3. Overlay zählt hoch und holt baum-relevante Antworten vollständig nach.
 *   4. Nach ~20 Sek. lädt "ancestry_spy_pedigree.json" herunter → hier einfügen.
 *
 * Liest nur – ändert nichts.
 * ========================================================================= */

(async () => {
  "use strict";

  // Nur Endpunkte, die nach Baum/Ahnen/Pedigree aussehen → volle Antwort.
  const TREE_HINT = /tree|pedigree|ancestor|ancestry-tree|family|person|node|generation|kinship|lineage/i;
  const API_HINT  = /\/api\/|matchesservice|discoveryui|\/dna\/|trees|family-tree/i;
  const IGNORE = [
    "ube-torrent", "/events", "newrelic", "nr-data", "/log", "telemetry",
    "google", "doubleclick", "adobe", "/akam/", "qualtrics", "hotjar",
    "/metrics", "/beacon", "fonts.", ".css", ".js", ".png", ".jpg", ".jpeg",
    ".svg", ".woff", ".gif", "/ping", "optimizely", "/static/",
  ];
  const isApi  = (u) => !!u && API_HINT.test(u) &&
                        !IGNORE.some(s => u.toLowerCase().includes(s));
  const isTree = (u) => isApi(u) && TREE_HINT.test(u);

  const captures = [];   // baum-relevant → volle Antwort
  const others   = [];   // sonstige API-Calls → nur URL + Kopf (zur Übersicht)
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
      requestBody: reqBody ? String(reqBody).slice(0, 800) : null,
      topKeys: keysOf(respText),
    };
    if (isTree(url)) {
      rec.responseFull = String(respText).slice(0, 200000); // volle (große) Antwort
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
  setMsg("<b>Pedigree-Spion</b><br>Lese bereits geladene Anfragen …");
  const urls = performance.getEntriesByType("resource").map(e => e.name).filter(isApi);
  const uniqueGets = [...new Set(urls)].slice(0, 80);

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
    setMsg("<b>Pedigree-Spion</b><br>Hole Antworten nach: " + i + "/" +
           uniqueGets.length + "<br>Baum-Treffer: " + captures.length);
    await sleep(120);
  }

  await sleep(2500);  // letzte Live-Anfragen abwarten

  // ── Download ────────────────────────────────────────────────────────────────
  window.fetch = _fetch;
  XMLHttpRequest.prototype.open = _open;
  XMLHttpRequest.prototype.send = _send;

  const payload = { treeEndpoints: captures, otherApiCalls: others };
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = "ancestry_spy_pedigree.json";
  document.body.appendChild(a); a.click(); a.remove();

  setMsg("✅ <b>Fertig.</b> " + captures.length + " Baum-Endpunkte (voll), " +
         others.length + " weitere.<br>Datei <b>ancestry_spy_pedigree.json</b> im Chat einfügen.");
})();
