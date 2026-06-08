/* ===========================================================================
 * MyHeritage DNA – API-Endpunkt-Spion v2
 * ===========================================================================
 *
 * ANLEITUNG:
 *   1. MyHeritage Match-Liste öffnen:
 *        https://www.myheritage.com/dna/matches/OYYV65GLYXMJ2JPTF5BJPM3IIQRB5LQ
 *   2. F12 → "Console" → diesen GESAMTEN Text einfügen → Enter
 *   3. Seite neu laden (F5) — der Spion fängt alle API-Calls ab
 *   4. Einen Match anklicken → "Review DNA Match" (damit Segment-Calls auftauchen)
 *   5. Nach ~25 Sekunden erscheint in der Console:
 *         ===== MH SPY RESULT =====
 *         {"ts": ..., "calls": [...]}
 *         =========================
 *   6. Diesen JSON-Text KOMPLETT kopieren (Rechtsklick → "Copy object" oder
 *      manuell alles zwischen den ====-Linien markieren) und hier einfügen.
 *
 * Alternativ: Network-Tab → Filter "Fetch/XHR" → Seite neu laden →
 * ersten Request mit JSON-Antwort anklicken → URL + Response hier schicken.
 * =========================================================================== */

(() => {
  "use strict";

  const CAPTURE_MS = 25000;
  const IGNORE = [
    "telemetry","analytics","google","doubleclick","facebook","newrelic",
    "fonts",".css",".js",".png",".jpg",".svg",".woff","/ping","/beacon",
    "hotjar","/log?","metrics","gtm","clarity","mouseflow",
  ];

  const captured = [];
  const seen = new Set();

  const skip = url => IGNORE.some(p => url.includes(p));

  function record(entry) {
    const key = entry.method + "|" + entry.url;
    if (seen.has(key)) return;
    seen.add(key);
    captured.push(entry);
  }

  // ── XHR ──────────────────────────────────────────────────────────────────
  const OrigXHR = window.XMLHttpRequest;
  function PatchedXHR() {
    const xhr  = new OrigXHR();
    const meta = { url: "", method: "", body: null, headers: {} };

    xhr.open = new Proxy(xhr.open, { apply(t,_,[m,u,...r]) {
      meta.method = m; meta.url = u; return t.call(xhr,m,u,...r);
    }});
    xhr.setRequestHeader = new Proxy(xhr.setRequestHeader, {
      apply(t,_,[k,v]) { meta.headers[k]=v; return t.call(xhr,k,v); }
    });
    xhr.send = new Proxy(xhr.send, { apply(t,_,[b]) {
      if (b) { try { meta.body = JSON.parse(b); } catch { meta.body = String(b).slice(0,300); } }
      xhr.addEventListener("load", () => {
        if (skip(meta.url)) return;
        let resp = null;
        try { resp = JSON.parse(xhr.responseText); } catch { resp = xhr.responseText?.slice(0,500); }
        record({ type:"xhr", method:meta.method, url:meta.url, status:xhr.status,
          reqHeaders:meta.headers, reqBody:meta.body,
          respKeys: resp && typeof resp==="object" ? Object.keys(resp).slice(0,30) : null,
          resp: typeof resp==="object" ? JSON.stringify(resp).slice(0,1200) : String(resp||"").slice(0,500),
        });
      });
      return t.call(xhr, b);
    }});
    return xhr;
  }
  PatchedXHR.prototype = OrigXHR.prototype;
  window.XMLHttpRequest = PatchedXHR;

  // ── fetch ─────────────────────────────────────────────────────────────────
  const origFetch = window.fetch;
  window.fetch = async function(input, init={}) {
    const url    = typeof input==="string" ? input : input?.url || "";
    const method = (init?.method || "GET").toUpperCase();
    let body = null;
    if (init?.body) { try { body=JSON.parse(init.body); } catch { body=String(init.body).slice(0,300); } }

    const resp = await origFetch(input, init);
    if (!skip(url)) {
      resp.clone().text().then(txt => {
        let parsed = null;
        try { parsed = JSON.parse(txt); } catch {}
        record({ type:"fetch", method, url, status:resp.status,
          reqHeaders: Object.fromEntries(Object.entries(init?.headers||{}).slice(0,10)),
          reqBody: body,
          respKeys: parsed && typeof parsed==="object" ? Object.keys(parsed).slice(0,30) : null,
          resp: parsed ? JSON.stringify(parsed).slice(0,1200) : txt.slice(0,500),
        });
      }).catch(()=>{});
    }
    return resp;
  };

  // ── Overlay ───────────────────────────────────────────────────────────────
  const div = document.createElement("div");
  Object.assign(div.style, {
    position:"fixed", top:"10px", right:"10px", zIndex:"999999",
    background:"#1a5276", color:"#fff", padding:"12px 16px",
    borderRadius:"8px", font:"13px/1.5 sans-serif",
    boxShadow:"0 4px 12px rgba(0,0,0,.5)", maxWidth:"300px",
  });
  const timer = document.createElement("span");
  div.innerHTML = `<b>🔍 MH Spion v2 aktiv</b><br>
    1. Seite neu laden (F5)<br>
    2. Einen Match anklicken<br>
    Fertig in <span id="_mh_t">${CAPTURE_MS/1000}</span>s`;
  document.body.appendChild(div);
  const tspan = div.querySelector("#_mh_t");
  let remaining = CAPTURE_MS / 1000;
  const ti = setInterval(() => {
    remaining--;
    if (tspan) tspan.textContent = remaining;
    if (remaining <= 0) clearInterval(ti);
  }, 1000);

  // ── Ausgabe nach Timer ────────────────────────────────────────────────────
  setTimeout(() => {
    clearInterval(ti);
    div.innerHTML = `<b>✅ ${captured.length} Calls gefangen</b><br>Ergebnis in Console (F12)`;
    setTimeout(() => div.remove(), 4000);

    const out = { ts: new Date().toISOString(), kitGuid: KIT_GUID(), calls: captured };
    const outStr = JSON.stringify(out, null, 2);

    console.log("\n===== MH SPY RESULT =====");
    console.log(outStr);
    console.log("=========================\n");

    // Versuch 1: Download via Blob
    try {
      const a = Object.assign(document.createElement("a"), {
        href: URL.createObjectURL(new Blob([outStr], {type:"application/json"})),
        download: "mh_spy.json",
      });
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
    } catch(e) { console.warn("Download fehlgeschlagen:", e); }

    // Versuch 2: In Clipboard
    try {
      navigator.clipboard.writeText(outStr).then(
        () => console.log("📋 Auch in Zwischenablage kopiert"),
        () => {}
      );
    } catch {}

    // Kurz-Übersicht für schnelle Orientierung
    console.log(`\n📊 Gefangene Calls (${captured.length}):`);
    captured.forEach((c,i) => console.log(
      `  [${i+1}] ${c.method} ${c.url.slice(0,100)}`
      + (c.respKeys ? `  →  {${c.respKeys.join(", ")}}` : "")
    ));
  }, CAPTURE_MS);

  function KIT_GUID() {
    const m = location.pathname.match(/\/([A-Z0-9]{20,})/);
    return m ? m[1] : "unbekannt";
  }

  console.log("[MH Spion v2] Gestartet – lade jetzt die Seite neu (F5)");
})();
