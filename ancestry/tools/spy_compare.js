/* ===========================================================================
 * Ancestry DNA – Compare-Seiten-Spion (Baum / Nachnamen / Geburtsorte)
 * ===========================================================================
 *
 * ZWECK
 *   Findet die Endpunkte, die die Vergleichs-Seite (compare) nutzt:
 *   Ahnen-Baum des Matches, gemeinsame Nachnamen, Geburtsorte.
 *   Speichert "ancestry_spy_compare.json", die du mir schickst.
 *
 * ANLEITUNG
 *   1. Im Browser eine Compare-Seite öffnen und VOLLSTÄNDIG laden lassen, z.B.:
 *      https://www.ancestry.com/dna/matches/BEC4AE66-352E-406F-B2DA-6BC5D4DED923/compare/141ED3AC-75B0-47D0-9585-C6755CE7C718
 *      (kurz warten, bis Baum & Nachnamen sichtbar sind)
 *   2. F12 → Reiter "Console" → diesen GESAMTEN Text einfügen → Enter
 *   3. Das Overlay zählt hoch und holt die interessanten Antworten nach.
 *   4. Nach ~20 Sek. lädt sich "ancestry_spy_compare.json" herunter → hier einfügen.
 *
 * Liest nur – ändert nichts.
 * ========================================================================= */

(async () => {
  "use strict";

  const IGNORE = [
    "ube-torrent", "/events", "newrelic", "nr-data", "/log", "telemetry",
    "google", "doubleclick", "adobe", "/akam/", "qualtrics", "hotjar",
    "/metrics", "/beacon", "fonts.", ".css", ".js", ".png", ".jpg", ".jpeg",
    ".svg", ".woff", ".gif", "/ping", "optimizely", "/static/",
  ];
  const interesting = (u) => {
    if (!u) return false;
    if (!/\/api\/|matchesservice|discoveryui|\/dna\//.test(u)) return false;
    const low = u.toLowerCase();
    return !IGNORE.some(s => low.includes(s));
  };

  const captures = [];
  const seen = new Set();

  function summarize(text) {
    try {
      const j = JSON.parse(text);
      let first = j;
      if (Array.isArray(j)) first = j[0];
      else if (j && typeof j === "object") {
        const k = Object.keys(j);
        if (k.length && typeof j[k[0]] === "object") first = j[k[0]];
      }
      return {
        topKeys: Array.isArray(j) ? ["<array len=" + j.length + ">"]
                                  : Object.keys(j || {}),
        firstChildKeys: (first && typeof first === "object")
                        ? Object.keys(first) : null,
        sample: JSON.stringify(j).slice(0, 2000),
      };
    } catch (e) {
      return { nonJson: true, sample: String(text).slice(0, 200) };
    }
  }
  function add(method, url, reqBody, respText, source) {
    captures.push({
      method, url, source,
      requestBody: reqBody ? String(reqBody).slice(0, 600) : null,
      ...summarize(respText),
    });
  }

  // ── 1) Live-Hooks (falls noch Anfragen kommen) ──────────────────────────────
  const _fetch = window.fetch;
  window.fetch = async function (input, init) {
    const url = (typeof input === "string") ? input : (input && input.url);
    const method = (init && init.method) || "GET";
    const body = init && init.body;
    const resp = await _fetch.apply(this, arguments);
    if (interesting(url) && !seen.has("L:" + url)) {
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
      if (interesting(this.__u) && !seen.has("L:" + this.__u)) {
        seen.add("L:" + this.__u);
        try { add(this.__m, this.__u, b, this.responseText, "live"); } catch (e) {}
      }
    });
    return _send.apply(this, arguments);
  };

  // ── Overlay ─────────────────────────────────────────────────────────────────
  const box = document.createElement("div");
  box.style.cssText =
    "position:fixed;right:16px;bottom:16px;z-index:2147483647;background:#1b2b3a;" +
    "color:#fff;font:14px/1.4 system-ui,sans-serif;padding:14px 18px;border-radius:10px;" +
    "box-shadow:0 4px 18px rgba(0,0,0,.4);max-width:380px;";
  document.body.appendChild(box);
  const setMsg = (h) => { box.innerHTML = h; };
  const sleep = (ms) => new Promise(r => setTimeout(r, ms));

  // ── 2) Bereits geladene Anfragen aus performance lesen + GETs nachholen ─────
  setMsg("<b>Compare-Spion</b><br>Lese bereits geladene Anfragen …");
  const urls = performance.getEntriesByType("resource")
    .map(e => e.name)
    .filter(interesting);
  const uniqueGets = [...new Set(urls)].slice(0, 60);

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
    setMsg("<b>Compare-Spion</b><br>Hole Antworten nach: " + i + "/" +
           uniqueGets.length + "<br>Erfasst: " + captures.length);
    await sleep(120);
  }

  await sleep(2000);  // letzte Live-Anfragen abwarten

  // ── 3) Download ─────────────────────────────────────────────────────────────
  window.fetch = _fetch;
  XMLHttpRequest.prototype.open = _open;
  XMLHttpRequest.prototype.send = _send;

  const blob = new Blob([JSON.stringify(captures, null, 2)], { type: "application/json" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = "ancestry_spy_compare.json";
  document.body.appendChild(a); a.click(); a.remove();

  setMsg("✅ <b>Fertig.</b> " + captures.length +
         " Anfragen in <b>ancestry_spy_compare.json</b>.<br>Datei im Chat einfügen.");
})();
