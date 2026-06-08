/* ===========================================================================
 * MyHeritage DNA – Spy + Auto-Scroll v2 (korrekter Container)
 * ===========================================================================
 *
 * ANLEITUNG:
 *   1. https://www.myheritage.com/dna/matches/OYYV65GLYXMJ2JPTF5BJPM3IIQRB5LQ öffnen
 *   2. Warten bis erste Matches sichtbar sind (Liste erscheint)
 *   3. F12 → Console → Text einfügen → Enter
 *   4. Script scrollt automatisch (~7-15 Min für alle 11.145)
 *   5. Download startet automatisch; manuell: window._download()
 *
 * Befehle:
 *   window._status()    → aktuell erfasste Anzahl
 *   window._download()  → sofort herunterladen
 *   window._stop()      → Scroll stoppen
 * =========================================================================== */

(async () => {
  "use strict";

  const TOTAL_EXPECTED  = 11145;
  const SCROLL_DELAY    = 1800;  // ms zwischen Scroll-Schritten
  const MAX_STABLE      = 10;    // Runden ohne neue Matches → fertig

  // ── 1. Fetch-Spy installieren ────────────────────────────────────────────
  // Ze hat window.fetch bereits gepatcht. Wir wrappen Ze's Version, damit
  // wir Reacts eigene erfolgreiche Calls abfangen.
  const captured   = new Map();
  const _zeFetch   = window.fetch;
  let   _running   = true;

  window.fetch = async function(...args) {
    const response = await _zeFetch.apply(this, args);
    const url = (typeof args[0] === "string") ? args[0]
              : (args[0]?.url ?? "");
    // DNA-Match-Calls abfangen (Ze leitet familygraphql → web-family-graphql)
    if (url.includes("familygraphql") || url.includes("web-family-graphql")) {
      response.clone().json().then(json => {
        const arr = json?.data?.dna_kit?.dna_matches?.data;
        if (Array.isArray(arr) && arr.length > 0) {
          let added = 0;
          arr.forEach(m => { if (m?.id && !captured.has(m.id)) { captured.set(m.id, m); added++; } });
          if (added > 0)
            console.log(`[SPY] +${added} Matches (gesamt: ${captured.size}/${TOTAL_EXPECTED})`);
        }
      }).catch(() => {});
    }
    return response;
  };

  console.log("[SPY] ✓ Fetch-Spy aktiv");

  // ── Hilfsfunktionen ──────────────────────────────────────────────────────
  function makeResult() {
    const arr = Array.from(captured.values());
    return {
      meta: {
        kit_id:           "dnakit-9F9E6C0C-5EF0-4A73-9F85-1F1C8219B3A2",
        site_id:          "OYYV65GLYXMJ2JPTF5BJPM3IIQRB5LQ",
        total_count:      TOTAL_EXPECTED,
        downloaded_count: arr.length,
        downloaded_at:    new Date().toISOString(),
        method:           "spy_scroll_v2",
      },
      matches: arr,
    };
  }

  function doDownload(label = "") {
    const arr = Array.from(captured.values());
    if (!arr.length) { console.log("[SPY] Nichts zu downloaden"); return 0; }
    const blob = new Blob([JSON.stringify(makeResult(), null, 2)], { type: "application/json" });
    const name = `mh_spy_${arr.length}${label}.json`;
    const a = Object.assign(document.createElement("a"), { href: URL.createObjectURL(blob), download: name });
    document.body.appendChild(a); a.click(); document.body.removeChild(a);
    console.log(`[SPY] ✓ Download: ${name}`);
    return arr.length;
  }

  window._status   = () => { console.log(`[SPY] ${captured.size}/${TOTAL_EXPECTED}`); return captured.size; };
  window._download = () => doDownload();
  window._stop     = () => { _running = false; console.log("[SPY] Scroll gestoppt"); };

  // ── 2. Matches-Container finden ──────────────────────────────────────────
  const SKIP_KEYWORDS = ["nav", "menu", "dropdown", "header", "footer", "toolbar",
                         "popup", "modal", "toast", "tooltip", "sidebar"];

  function isNav(el) {
    const cls = (el.className || "").toLowerCase();
    const id  = (el.id || "").toLowerCase();
    return SKIP_KEYWORDS.some(k => cls.includes(k) || id.includes(k)) ||
           ["HEADER", "FOOTER", "NAV", "ASIDE"].includes(el.tagName);
  }

  function findMatchesContainer() {
    // 1. Seite scrollt als Ganzes (viele SPAs)
    const bodyH = document.documentElement.scrollHeight;
    if (bodyH > window.innerHeight + 200) {
      console.log(`[SCROLL] Seite scrollbar (body: ${bodyH}px) – nutze window-Scroll`);
      return "window";
    }

    // 2. Suche größtes scrollbares Div/Ul ohne Nav-Kontext
    let best = null, bestSize = 0;
    document.querySelectorAll("div,ul,ol,section,main,article").forEach(el => {
      if (isNav(el)) return;
      const s = window.getComputedStyle(el);
      const scrollable = s.overflow === "auto" || s.overflowY === "auto" ||
                         s.overflow === "scroll" || s.overflowY === "scroll";
      if (!scrollable) return;
      const extra = el.scrollHeight - el.clientHeight;
      if (extra > 200 && extra > bestSize) { bestSize = extra; best = el; }
    });

    if (best) {
      console.log(`[SCROLL] Container: ${best.tagName}.${(best.className||"").split(" ")[0]} (scrollbar: ${bestSize}px)`);
      return best;
    }

    console.log("[SCROLL] Kein Container → window-Scroll");
    return "window";
  }

  // Simuliert menschliches Scrollen + feuert Scroll-Events
  function scrollStep(container) {
    const big = 3000;
    if (container === "window" || !container) {
      // Sofort ans Ende scrollen
      const target = Math.min(document.documentElement.scrollTop + big,
                              document.documentElement.scrollHeight);
      document.documentElement.scrollTop = target;
      document.body.scrollTop = target;
      window.scrollTo(0, target);
    } else {
      container.scrollTop = Math.min(container.scrollTop + big, container.scrollHeight);
    }
    // Scroll-Events feuern (triggert infinite-scroll-Listener)
    const targets = container === "window"
      ? [window, document, document.documentElement, document.body]
      : [container, window, document];
    targets.forEach(t => {
      try { t.dispatchEvent(new Event("scroll", { bubbles: true })); } catch(_) {}
    });
  }

  // ── 3. Auto-Scroll-Schleife ──────────────────────────────────────────────
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  await sleep(2000);

  let container  = findMatchesContainer();
  let lastCount  = captured.size;
  let stable     = 0;
  let scrolls    = 0;

  while (_running && stable < MAX_STABLE) {
    scrollStep(container);
    await sleep(SCROLL_DELAY);
    scrolls++;

    // Container alle 30 Scrolls neu prüfen (DOM ändert sich)
    if (scrolls % 30 === 0) container = findMatchesContainer();

    if (captured.size > lastCount) {
      lastCount = captured.size;
      stable = 0;
    } else {
      stable++;
    }

    // Log alle 20 Scrolls
    if (scrolls % 20 === 0) {
      const pct = (captured.size / TOTAL_EXPECTED * 100).toFixed(1);
      console.log(`[SCROLL] ${scrolls} Scrolls | ${captured.size}/${TOTAL_EXPECTED} (${pct}%) | stabil: ${stable}/${MAX_STABLE}`);
    }

    // Zwischendownload alle ~500 Matches
    if (captured.size > 0 && captured.size % 500 < 5 && captured.size !== lastCount) {
      doDownload(`_zwischenstand`);
    }

    if (captured.size >= TOTAL_EXPECTED) {
      console.log("[SPY] ✅ Alle Matches erfasst!");
      break;
    }
  }

  // ── 4. Abschluss ────────────────────────────────────────────────────────
  if (captured.size === 0) {
    console.warn("[SPY] ⚠️ Keine Matches erfasst. Mögliche Ursachen:");
    console.warn("  • Scroll hat nicht die richtige Liste getroffen");
    console.warn("  • React macht keine neuen API-Calls beim Scrollen");
    console.warn("");
    console.warn("[SPY] Bitte manuell scrollen und window._download() aufrufen.");
    console.warn("[SPY] Oder: Seite neu laden → Script erneut ausführen →");
    console.warn("       sofort nach dem Einfügen schnell nach unten scrollen.");
  } else {
    console.log(`[SPY] Fertig: ${captured.size} Matches | Download startet …`);
    doDownload("_final");
  }
})();
