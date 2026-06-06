/* ===========================================================================
 * Ancestry DNA – Endpunkt-Spion (findet die Baum-/Vorfahren-Daten)
 * ===========================================================================
 *
 * ZWECK
 *   Findet heraus, welche Netzwerk-Anfrage die Daten der "rechten Spalte"
 *   liefert (Baum-Status, Personenzahl, gemeinsamer Vorfahre). Speichert eine
 *   Datei "ancestry_spy.json", die du mir schickst – daraus baue ich den Abruf.
 *
 * ANLEITUNG (4 Schritte)
 *   1. Im Browser die DNA-Match-Liste öffnen:
 *        https://www.ancestry.com/discoveryui-matches/list/<DEINE-KIT-GUID>
 *   2. F12 → Reiter "Console" → diesen GESAMTEN Text einfügen → Enter
 *   3. Wenn das Overlay "Scrolle jetzt …" zeigt: die Match-Liste langsam
 *      ein Stück nach unten scrollen (10–15 Sekunden), damit Karten nachladen.
 *   4. Nach ~25 Sekunden lädt sich automatisch "ancestry_spy.json" herunter.
 *      Diese Datei hier in den Chat ziehen / einfügen.
 *
 * Es wird NICHTS verändert – nur mitgelesen.
 * ========================================================================= */

(() => {
  "use strict";

  const CAPTURE_MS = 25000;   // wie lange mitgehört wird
  const IGNORE = [            // Telemetrie/Tracking ausblenden
    "ube-torrent", "/events", "newrelic", "nr-data", "/log", "telemetry",
    "google", "doubleclick", "adobe", "/akam/", "qualtrics", "hotjar",
    "/metrics", "/beacon", "fonts", ".css", ".js", ".png", ".jpg", ".svg",
    ".woff", "/ping",
  ];
  const captures = [];

  function interesting(url) {
    if (!url) return false;
    if (!url.includes("/api/") && !url.includes("matchesservice")
        && !url.includes("/discoveryui")) return false;
    const low = url.toLowerCase();
    return !IGNORE.some(s => low.includes(s));
  }

  function summarize(text) {
    // Liefert {keys, sample} für eine (hoffentlich) JSON-Antwort
    try {
      const j = JSON.parse(text);
      let keys, first = j;
      if (Array.isArray(j)) {
        keys = ["<array len=" + j.length + ">"];
        first = j[0];
      } else if (j && typeof j === "object") {
        keys = Object.keys(j);
        // bei {sid:{...}} das erste Unterobjekt zeigen
        if (keys.length && typeof j[keys[0]] === "object") first = j[keys[0]];
      }
      return {
        topKeys: Array.isArray(j) ? keys : Object.keys(j || {}),
        firstChildKeys: (first && typeof first === "object")
                        ? Object.keys(first) : null,
        sample: JSON.stringify(j).slice(0, 1200),
      };
    } catch (e) {
      return { nonJson: true, sample: String(text).slice(0, 200) };
    }
  }

  function record(method, url, reqBody, respText) {
    if (!interesting(url)) return;
    const info = summarize(respText);
    captures.push({
      method, url,
      requestBody: reqBody ? String(reqBody).slice(0, 500) : null,
      ...info,
    });
  }

  // ── fetch abfangen ─────────────────────────────────────────────────────────
  const _fetch = window.fetch;
  window.fetch = async function (input, init) {
    const url = (typeof input === "string") ? input : (input && input.url);
    const method = (init && init.method) || "GET";
    const reqBody = init && init.body;
    const resp = await _fetch.apply(this, arguments);
    if (interesting(url)) {
      try { resp.clone().text().then(t => record(method, url, reqBody, t)); }
      catch (e) {}
    }
    return resp;
  };

  // ── XMLHttpRequest abfangen ─────────────────────────────────────────────────
  const _open = XMLHttpRequest.prototype.open;
  const _send = XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.open = function (m, u) {
    this.__m = m; this.__u = u; return _open.apply(this, arguments);
  };
  XMLHttpRequest.prototype.send = function (body) {
    this.addEventListener("load", function () {
      if (interesting(this.__u)) {
        try { record(this.__m, this.__u, body, this.responseText); } catch (e) {}
      }
    });
    return _send.apply(this, arguments);
  };

  // ── Overlay + Auto-Download ─────────────────────────────────────────────────
  const box = document.createElement("div");
  box.style.cssText =
    "position:fixed;right:16px;bottom:16px;z-index:2147483647;background:#3a2b1b;" +
    "color:#fff;font:14px/1.4 system-ui,sans-serif;padding:14px 18px;" +
    "border-radius:10px;box-shadow:0 4px 18px rgba(0,0,0,.4);max-width:360px;";
  document.body.appendChild(box);
  const t0 = Date.now();
  const tick = setInterval(() => {
    const left = Math.max(0, Math.ceil((CAPTURE_MS - (Date.now() - t0)) / 1000));
    box.innerHTML = "<b>Endpunkt-Spion läuft</b><br>" +
      "⬇️ <b>Jetzt die Liste langsam scrollen!</b><br>" +
      "Aufgezeichnet: " + captures.length + " Anfragen<br>" +
      "Fertig in " + left + " s …";
  }, 400);

  setTimeout(() => {
    clearInterval(tick);
    window.fetch = _fetch;
    XMLHttpRequest.prototype.open = _open;
    XMLHttpRequest.prototype.send = _send;

    const blob = new Blob([JSON.stringify(captures, null, 2)],
                          { type: "application/json" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "ancestry_spy.json";
    document.body.appendChild(a); a.click(); a.remove();

    box.innerHTML = "✅ <b>Fertig.</b> " + captures.length +
      " Anfragen in <b>ancestry_spy.json</b> gespeichert.<br>" +
      "Datei im Chat einfügen.";
  }, CAPTURE_MS);
})();
