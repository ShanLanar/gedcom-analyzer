/* ===========================================================================
 * MyHeritage DNA – API-Endpunkt-Spion
 * ===========================================================================
 *
 * ANLEITUNG (3 Schritte):
 *   1. Im Browser die MyHeritage Match-Liste öffnen:
 *        https://www.myheritage.com/dna/matches/OYYV65GLYXMJ2JPTF5BJPM3IIQRB5LQ
 *   2. F12 → Reiter "Console" → diesen GESAMTEN Text einfügen → Enter
 *   3. Die Seite EINMAL neu laden (F5) — der Spion fängt alle API-Aufrufe ab
 *      Danach: Auf einen Match klicken (→ Detail-Seite), damit Segment-
 *      und ICW-Calls auftauchen
 *   4. Nach ~30 Sekunden lädt sich "mh_spy.json" herunter
 *
 * Es wird NICHTS verändert oder gesendet – nur mitgelesen.
 * =========================================================================== */

(() => {
  "use strict";

  const CAPTURE_MS = 30000;
  const IGNORE = [
    "telemetry", "analytics", "google", "doubleclick", "facebook",
    "newrelic", "fonts", ".css", ".js", ".png", ".jpg", ".svg", ".woff",
    "/ping", "/beacon", "hotjar", "/log?", "metrics",
  ];

  const captured = [];

  const shouldIgnore = url =>
    IGNORE.some(pat => url.includes(pat));

  // ── XHR abfangen ────────────────────────────────────────────────────────
  const OrigXHR = window.XMLHttpRequest;
  function PatchedXHR() {
    const xhr = new OrigXHR();
    const meta = { url: "", method: "", requestBody: null, reqHeaders: {} };

    const origOpen = xhr.open.bind(xhr);
    xhr.open = function(method, url, ...rest) {
      meta.method = method;
      meta.url = url;
      return origOpen(method, url, ...rest);
    };

    const origSetHeader = xhr.setRequestHeader.bind(xhr);
    xhr.setRequestHeader = function(k, v) {
      meta.reqHeaders[k] = v;
      return origSetHeader(k, v);
    };

    const origSend = xhr.send.bind(xhr);
    xhr.send = function(body) {
      if (body) {
        try { meta.requestBody = JSON.parse(body); }
        catch { meta.requestBody = String(body).slice(0, 500); }
      }
      xhr.addEventListener("load", () => {
        if (shouldIgnore(meta.url)) return;
        let respBody = null;
        try { respBody = JSON.parse(xhr.responseText); }
        catch { respBody = xhr.responseText?.slice(0, 300); }
        captured.push({
          type: "xhr",
          method: meta.method,
          url: meta.url,
          status: xhr.status,
          requestHeaders: meta.reqHeaders,
          requestBody: meta.requestBody,
          responseKeys: respBody && typeof respBody === "object"
            ? Object.keys(respBody).slice(0, 20) : null,
          responseSample: respBody && typeof respBody === "object"
            ? JSON.stringify(respBody).slice(0, 800) : String(respBody).slice(0, 400),
        });
      });
      return origSend(body);
    };
    return xhr;
  }
  PatchedXHR.prototype = OrigXHR.prototype;
  window.XMLHttpRequest = PatchedXHR;

  // ── fetch abfangen ───────────────────────────────────────────────────────
  const origFetch = window.fetch;
  window.fetch = async function(input, init = {}) {
    const url = typeof input === "string" ? input : input.url;
    const method = (init.method || "GET").toUpperCase();
    let reqBody = null;
    if (init.body) {
      try { reqBody = JSON.parse(init.body); }
      catch { reqBody = String(init.body).slice(0, 500); }
    }
    const resp = await origFetch(input, init);
    if (!shouldIgnore(url)) {
      const clone = resp.clone();
      clone.text().then(txt => {
        let parsed = null;
        try { parsed = JSON.parse(txt); } catch { parsed = null; }
        captured.push({
          type: "fetch",
          method,
          url,
          status: resp.status,
          requestHeaders: Object.fromEntries(
            Object.entries(init.headers || {}).slice(0, 15)
          ),
          requestBody: reqBody,
          responseKeys: parsed && typeof parsed === "object"
            ? Object.keys(parsed).slice(0, 20) : null,
          responseSample: parsed
            ? JSON.stringify(parsed).slice(0, 800)
            : txt.slice(0, 400),
        });
      }).catch(() => {});
    }
    return resp;
  };

  // ── Overlay ──────────────────────────────────────────────────────────────
  const div = document.createElement("div");
  div.style.cssText = [
    "position:fixed", "top:12px", "right:12px", "z-index:999999",
    "background:#1a5276", "color:#fff", "padding:12px 18px",
    "border-radius:8px", "font:14px/1.5 sans-serif",
    "box-shadow:0 4px 12px rgba(0,0,0,.4)", "max-width:320px",
  ].join(";");
  div.innerHTML = `<b>🔍 MH Spion aktiv</b><br>
    Lade jetzt die Seite neu (F5) und klicke danach auf<br>
    einen Match → "Review DNA Match".<br>
    Download startet automatisch nach ${CAPTURE_MS/1000}s.`;
  document.body.appendChild(div);

  // ── Download ─────────────────────────────────────────────────────────────
  setTimeout(() => {
    div.innerHTML = `<b>✅ Fertig – ${captured.length} Calls gefangen</b><br>Download startet …`;
    const blob = new Blob([JSON.stringify({
      ts: new Date().toISOString(),
      kitGuid: location.pathname.split("/").pop(),
      calls: captured,
    }, null, 2)], { type: "application/json" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "mh_spy.json";
    a.click();
    setTimeout(() => div.remove(), 3000);
  }, CAPTURE_MS);

  console.log("[MH Spion] Gestartet – warte auf API-Calls …");
})();
