/* ===========================================================================
 * MyHeritage DNA – XHR-Spy + Auto-Scroll v3
 * ===========================================================================
 * WICHTIG: React nutzt axios (XMLHttpRequest), NICHT window.fetch.
 * Dieser Spy patcht XMLHttpRequest.prototype um alle API-Calls abzufangen.
 *
 * ANLEITUNG:
 *   1. Seite neu laden (F5) – warten bis Matches sichtbar sind
 *   2. F12 → Console → Text einfügen → Enter
 *   3. Script scrollt automatisch (~7-15 Min für alle 11.145)
 *   4. Download startet automatisch; manuell: window._download()
 *
 * Befehle:
 *   window._status()    → aktuell erfasste Anzahl
 *   window._download()  → sofort herunterladen
 *   window._stop()      → Scroll stoppen
 * =========================================================================== */

(async () => {
  "use strict";

  const TOTAL_EXPECTED = 11145;
  const SCROLL_DELAY   = 2000;
  const MAX_STABLE     = 12;

  // ── 1. XHR-Spy installieren ──────────────────────────────────────────────
  const captured  = new Map();
  let   _running  = true;

  const _XHROpen  = XMLHttpRequest.prototype.open;
  const _XHRSend  = XMLHttpRequest.prototype.send;

  XMLHttpRequest.prototype.open = function(method, url, ...rest) {
    this._mhUrl = url;
    return _XHROpen.apply(this, [method, url, ...rest]);
  };

  XMLHttpRequest.prototype.send = function(body) {
    const xhr = this;
    const url = xhr._mhUrl || "";

    // DNA-Match-Endpunkte abfangen
    if (url.includes("web-family-graphql") || url.includes("familygraphql")) {
      xhr.addEventListener("readystatechange", function() {
        if (xhr.readyState !== 4 || xhr.status !== 200) return;
        try {
          const json = JSON.parse(xhr.responseText);
          // /fetch_dna_matches_for_kit/ → dna_kit.dna_matches.data
          const arr = json?.data?.dna_kit?.dna_matches?.data;
          if (Array.isArray(arr) && arr.length > 0) {
            let added = 0;
            arr.forEach(m => { if (m?.id && !captured.has(m.id)) { captured.set(m.id, m); added++; } });
            if (added > 0)
              console.log(`[SPY] +${added} Matches (gesamt: ${captured.size}/${TOTAL_EXPECTED})`);
          }
        } catch(_) {}
      });
    }
    return _XHRSend.apply(this, arguments);
  };

  // Auch fetch abfangen (Fallback, falls React teilweise fetch nutzt)
  const _realFetch = window.fetch;
  window.fetch = async function(...args) {
    const response = await _realFetch.apply(this, args);
    const url = (typeof args[0] === "string") ? args[0] : (args[0]?.url ?? "");
    if (url.includes("web-family-graphql") || url.includes("familygraphql")) {
      response.clone().json().then(json => {
        const arr = json?.data?.dna_kit?.dna_matches?.data;
        if (Array.isArray(arr) && arr.length > 0) {
          let added = 0;
          arr.forEach(m => { if (m?.id && !captured.has(m.id)) { captured.set(m.id, m); added++; } });
          if (added > 0)
            console.log(`[SPY-fetch] +${added} (gesamt: ${captured.size})`);
        }
      }).catch(() => {});
    }
    return response;
  };

  console.log("[SPY] ✓ XHR-Spy + fetch-Spy aktiv");
  console.log("[SPY] Warte auf erste Matches …");

  // ── Hilfsfunktionen ──────────────────────────────────────────────────────
  function doDownload(label = "") {
    const arr = Array.from(captured.values());
    if (!arr.length) { console.log("[SPY] Noch keine Matches erfasst"); return 0; }
    const obj = {
      meta: {
        kit_id:           "dnakit-9F9E6C0C-5EF0-4A73-9F85-1F1C8219B3A2",
        site_id:          "OYYV65GLYXMJ2JPTF5BJPM3IIQRB5LQ",
        total_count:      TOTAL_EXPECTED,
        downloaded_count: arr.length,
        downloaded_at:    new Date().toISOString(),
        method:           "xhr_spy_v3",
      },
      matches: arr,
    };
    const blob = new Blob([JSON.stringify(obj, null, 2)], { type: "application/json" });
    const name = `mh_spy_${arr.length}${label}.json`;
    const a = Object.assign(document.createElement("a"), { href: URL.createObjectURL(blob), download: name });
    document.body.appendChild(a); a.click(); document.body.removeChild(a);
    console.log(`[SPY] ✓ Download: ${name}`);
    return arr.length;
  }

  window._status   = () => { console.log(`[SPY] ${captured.size}/${TOTAL_EXPECTED}`); return captured.size; };
  window._download = () => doDownload();
  window._stop     = () => { _running = false; console.log("[SPY] Gestoppt"); };

  // ── 2. Kurz warten damit erste Matches laden ─────────────────────────────
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  await sleep(3000);

  if (captured.size === 0) {
    console.log("[SPY] Noch keine Matches – warte weitere 5 Sek …");
    await sleep(5000);
  }
  console.log(`[SPY] Start: ${captured.size} Matches bereits erfasst`);

  // ── 3. Auto-Scroll ───────────────────────────────────────────────────────
  const SKIP = ["nav", "menu", "dropdown", "header", "footer", "toolbar",
                "popup", "modal", "toast", "tooltip", "sidebar", "tabs"];

  function findContainer() {
    // Seite selbst scrollbar?
    if (document.documentElement.scrollHeight > window.innerHeight + 300) {
      return "window";
    }
    // Größtes scrollbares div ohne Nav-Kontext
    let best = null, bestH = 0;
    document.querySelectorAll("div,ul,section,main").forEach(el => {
      const cls = (el.className + el.id).toLowerCase();
      if (SKIP.some(k => cls.includes(k))) return;
      const s = window.getComputedStyle(el);
      if (!["auto","scroll"].includes(s.overflowY) && !["auto","scroll"].includes(s.overflow)) return;
      const extra = el.scrollHeight - el.clientHeight;
      if (extra > 300 && extra > bestH) { bestH = extra; best = el; }
    });
    return best || "window";
  }

  function scrollStep(container) {
    const amount = 2500;
    if (container === "window") {
      const t = document.documentElement.scrollTop + amount;
      document.documentElement.scrollTop = t;
      document.body.scrollTop = t;
      window.scrollBy(0, amount);
    } else {
      container.scrollTop = Math.min(container.scrollTop + amount, container.scrollHeight);
    }
    // Scroll-Events feuern um infinite-scroll-Listener zu triggern
    [window, document, document.documentElement, document.body].forEach(t => {
      try { t.dispatchEvent(new Event("scroll", { bubbles: true })); } catch(_) {}
    });
  }

  let container = findContainer();
  console.log(`[SCROLL] Container: ${container === "window" ? "window" : container.tagName + "." + (container.className||"").split(" ")[0]}`);

  let lastCount = captured.size;
  let stable    = 0;
  let scrolls   = 0;

  while (_running && stable < MAX_STABLE) {
    scrollStep(container);
    await sleep(SCROLL_DELAY);
    scrolls++;

    if (scrolls % 25 === 0) container = findContainer();

    if (captured.size > lastCount) {
      lastCount = captured.size;
      stable = 0;
    } else {
      stable++;
    }

    if (scrolls % 15 === 0) {
      const pct = (captured.size / TOTAL_EXPECTED * 100).toFixed(1);
      console.log(`[SCROLL] ${scrolls} Scrolls | ${captured.size}/${TOTAL_EXPECTED} (${pct}%) | stabil: ${stable}/${MAX_STABLE}`);
    }

    if (captured.size > 0 && captured.size % 500 < 3 && captured.size !== lastCount) {
      doDownload(`_backup_${captured.size}`);
    }

    if (captured.size >= TOTAL_EXPECTED) { console.log("[SPY] ✅ Alle erfasst!"); break; }
  }

  // ── 4. Abschluss ────────────────────────────────────────────────────────
  if (captured.size === 0) {
    console.warn("[SPY] ⚠️ 0 Matches. Mögliche Ursachen:");
    console.warn("  1. Session abgelaufen → Seite KOMPLETT NEU LADEN (F5), dann erneut starten");
    console.warn("  2. Matches noch nicht geladen → nach dem F5 kurz warten bis Liste erscheint");
    console.warn("  Dann: Script direkt nach dem Erscheinen der Liste einfügen");
  } else {
    console.log(`[SPY] ✅ Fertig: ${captured.size} Matches`);
    doDownload("_final");
  }
})();
