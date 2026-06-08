/* ===========================================================================
 * MyHeritage – Request-Capture (fängt die ECHTEN App-Anfragen ab)
 *
 * Zweck: /web-family-graphql gibt uns 403. Die App selbst lädt die Matches
 * aber erfolgreich. Dieses Script hängt sich in fetch + XHR und protokolliert
 * die EXAKTE Anfrage (URL, Methode, Header, Body) + Antwort-Anfang, sobald
 * die App match-bezogene Daten lädt.
 *
 * ANLEITUNG:
 *   1. Match-Liste offen: myheritage.de/dna/matches/OYYV65GLYXMJ2JPTF5BJPM3IIQRB5LQ
 *   2. F12 → Console → diesen Text einfügen → Enter
 *   3. Dann in der Seite LANGSAM nach unten scrollen, bis neue Matches nachladen
 *      (oder einen Match anklicken). Das triggert die echten Calls.
 *   4. Sobald [CAP] Zeilen erscheinen → ALLE hier einfügen.
 *   5. window._caps  enthält die gesammelten Anfragen (zum Nachschauen).
 * =========================================================================== */
(() => {
  "use strict";
  if (window.__mhCapInstalled) {
    console.log("[CAP] Bereits aktiv. window._caps =", window._caps?.length || 0, "Treffer");
    return;
  }
  window.__mhCapInstalled = true;
  window._caps = [];

  const INTERESTING = /match|graphql|dna_|shared|pedigree/i;
  const DATA_HINTS  = ["dna_match", "total_shared", "shared_segments",
                       "shared_dna", "dna_matches", "other_dna_kit", "display_name"];

  function looksLikeData(body) {
    if (!body || body.length < 30) return false;
    return DATA_HINTS.some(h => body.includes(h));
  }

  function record(kind, url, method, headers, reqBody, respBody) {
    const entry = { kind, url, method, headers, reqBody,
                    respSnippet: (respBody || "").slice(0, 400) };
    window._caps.push(entry);
    console.log(`%c[CAP] ${kind} ${method} → ${url}`, "color:#0a0;font-weight:bold");
    console.log("[CAP]   Header:", JSON.stringify(headers));
    if (reqBody) console.log("[CAP]   Body:", String(reqBody).slice(0, 400));
    console.log("[CAP]   Antwort:", (respBody || "").slice(0, 300));
    console.log("[CAP]   ── (vollständig in window._caps[" + (window._caps.length-1) + "])");
  }

  // ── fetch ──────────────────────────────────────────────────────────────
  const origFetch = window.fetch;
  window.fetch = function(...args) {
    const req    = args[0];
    const opts   = args[1] || {};
    const url    = typeof req === "string" ? req : (req && req.url) || "";
    const method = (opts.method || (req && req.method) || "GET").toUpperCase();
    const reqBody = opts.body || null;
    const headers = opts.headers
      ? (opts.headers instanceof Headers
          ? Object.fromEntries(opts.headers.entries())
          : opts.headers)
      : {};

    const p = origFetch.apply(this, args);
    if (url && INTERESTING.test(url)) {
      p.then(r => {
        r.clone().text().then(body => {
          if (looksLikeData(body)) record("fetch", url, method, headers, reqBody, body);
        }).catch(()=>{});
      }).catch(()=>{});
    }
    return p;
  };

  // ── XMLHttpRequest ───────────────────────────────────────────────────────
  const origOpen = XMLHttpRequest.prototype.open;
  const origSend = XMLHttpRequest.prototype.send;
  const origSetH = XMLHttpRequest.prototype.setRequestHeader;

  XMLHttpRequest.prototype.open = function(method, url, ...rest) {
    this.__cap = { method: (method||"GET").toUpperCase(), url: url || "", headers: {} };
    return origOpen.apply(this, [method, url, ...rest]);
  };
  XMLHttpRequest.prototype.setRequestHeader = function(name, value) {
    if (this.__cap) this.__cap.headers[name] = value;
    return origSetH.apply(this, [name, value]);
  };
  XMLHttpRequest.prototype.send = function(body) {
    const cap = this.__cap;
    if (cap && INTERESTING.test(cap.url)) {
      this.addEventListener("load", function() {
        let resp = "";
        try { resp = this.responseText || ""; } catch(e) {}
        if (looksLikeData(resp))
          record("xhr", cap.url, cap.method, cap.headers, body, resp);
      });
    }
    return origSend.apply(this, [body]);
  };

  console.log("%c[CAP] Interceptor aktiv (fetch + XHR).", "color:#0a0;font-weight:bold");
  console.log("[CAP] → Jetzt in der Match-Liste nach unten scrollen, bis neue Matches laden.");
  console.log("[CAP] → Danach erscheinen [CAP]-Zeilen. window._caps enthält alles.");
})();
