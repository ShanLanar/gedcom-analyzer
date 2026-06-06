/* ===========================================================================
 * Ancestry DNA – Shared-Matches-Spion
 * ===========================================================================
 *
 * ZWECK
 *   Findet die EXAKTE Anfrage, mit der Ancestry die "Shared Matches /
 *   Gemeinsame Übereinstimmungen" eines bestimmten Matches lädt – inkl.
 *   des richtigen Filter-Parameters (unser 'matchSampleId' liefert fälschlich
 *   ALLE Matches). Speichert "ancestry_spy_shared.json".
 *
 * ANLEITUNG
 *   1. Match-Liste öffnen:
 *      https://www.ancestry.com/discoveryui-matches/list/BEC4AE66-352E-406F-B2DA-6BC5D4DED923
 *   2. Einen Match anklicken und dort "Shared Matches /
 *      Gemeinsame Übereinstimmungen" öffnen, bis die Liste erscheint.
 *      (1–2 Seiten weiterscrollen, damit auch die Folgeseite feuert.)
 *   3. F12 → "Console" → diesen GESAMTEN Text einfügen → Enter.
 *   4. Klick im Overlay erneut auf "Shared Matches", damit die LIVE-Anfrage
 *      erfasst wird. Nach ~20 Sek. lädt "ancestry_spy_shared.json" → hier rein.
 *
 * Liest nur – ändert nichts.
 * ========================================================================= */

(async () => {
  "use strict";

  // Verdächtig: alles, was nach shared/match-Liste aussieht.
  const HINT  = /shared|matchlist|matches|relation|incommon|common/i;
  const API   = /\/api\/|matchesservice|discoveryui|\/dna\//i;
  const IGNORE = [
    "ube-torrent","/events","newrelic","nr-data","/log","telemetry","google",
    "doubleclick","adobe","/akam/","qualtrics","hotjar","/metrics","/beacon",
    "fonts.",".css",".js",".png",".jpg",".svg",".woff","/ping","optimizely","/static/",
  ];
  const isApi = (u) => !!u && API.test(u) && !IGNORE.some(s => u.toLowerCase().includes(s));

  const captures = [];
  const seen = new Set();

  function summarize(text) {
    try {
      const j = JSON.parse(text);
      const arr = Array.isArray(j) ? j : (j.matchList || j.matches || j.sharedMatches);
      return {
        topKeys: Array.isArray(j) ? ["<array len=" + j.length + ">"] : Object.keys(j||{}),
        listLen: Array.isArray(arr) ? arr.length : null,
        firstItem: Array.isArray(arr) && arr.length ? JSON.stringify(arr[0]).slice(0,1200) : null,
        sample: JSON.stringify(j).slice(0, 1500),
      };
    } catch (e) { return { nonJson: true, sample: String(text).slice(0,200) }; }
  }
  function add(method, url, body, text, source) {
    captures.push({ method, url, source, hot: HINT.test(url),
      requestBody: body ? String(body).slice(0,800) : null, ...summarize(text) });
  }

  // ── Live-Hooks ──────────────────────────────────────────────────────────────
  const _fetch = window.fetch;
  window.fetch = async function (input, init) {
    const url = (typeof input === "string") ? input : (input && input.url);
    const method = (init && init.method) || "GET";
    const body = init && init.body;
    const resp = await _fetch.apply(this, arguments);
    if (isApi(url) && HINT.test(url) && !seen.has("L:"+url)) {
      seen.add("L:"+url);
      try { resp.clone().text().then(t => add(method, url, body, t, "live")); } catch (e) {}
    }
    return resp;
  };
  const _open = XMLHttpRequest.prototype.open;
  const _send = XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.open = function (m,u){ this.__m=m; this.__u=u; return _open.apply(this,arguments); };
  XMLHttpRequest.prototype.send = function (b){
    this.addEventListener("load", function(){
      if (isApi(this.__u) && HINT.test(this.__u) && !seen.has("L:"+this.__u)) {
        seen.add("L:"+this.__u);
        try { add(this.__m, this.__u, b, this.responseText, "live"); } catch (e) {}
      }
    });
    return _send.apply(this,arguments);
  };

  // ── Overlay ─────────────────────────────────────────────────────────────────
  const box = document.createElement("div");
  box.style.cssText = "position:fixed;right:16px;bottom:16px;z-index:2147483647;"+
    "background:#3a1b2b;color:#fff;font:14px/1.4 system-ui,sans-serif;padding:14px 18px;"+
    "border-radius:10px;box-shadow:0 4px 18px rgba(0,0,0,.4);max-width:380px;";
  document.body.appendChild(box);
  const setMsg = (h)=>{ box.innerHTML=h; };
  const sleep = (ms)=>new Promise(r=>setTimeout(r,ms));

  setMsg("<b>Shared-Spion aktiv.</b><br>Jetzt im Match die <b>Shared Matches</b> öffnen "+
         "bzw. erneut anklicken und scrollen …");

  // Bereits geladene shared-artige GETs nachholen
  for (let n=0; n<18; n++) {
    const urls = performance.getEntriesByType("resource").map(e=>e.name)
                  .filter(u=>isApi(u)&&HINT.test(u));
    for (const url of [...new Set(urls)]) {
      if (!seen.has("R:"+url)) {
        seen.add("R:"+url);
        try { const r=await _fetch(url,{credentials:"include",headers:{Accept:"application/json"}});
              add("GET", url, null, await r.text(), "replay"); } catch(e){}
      }
    }
    setMsg("<b>Shared-Spion</b><br>Warte auf deine Klicks … ("+(18-n)+"s)<br>Erfasst: "+captures.length);
    await sleep(1000);
  }

  // ── Download ────────────────────────────────────────────────────────────────
  window.fetch = _fetch;
  XMLHttpRequest.prototype.open = _open;
  XMLHttpRequest.prototype.send = _send;

  const blob = new Blob([JSON.stringify(captures, null, 2)], { type:"application/json" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob); a.download = "ancestry_spy_shared.json";
  document.body.appendChild(a); a.click(); a.remove();

  setMsg("✅ <b>Fertig.</b> "+captures.length+" Anfragen in <b>ancestry_spy_shared.json</b>.<br>"+
         "Datei im Chat einfügen.");
})();
