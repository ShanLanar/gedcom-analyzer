/* ===========================================================================
 * MyHeritage DNA – XHR-Spy + sanfter Auto-Scroll v4
 * ===========================================================================
 * VORAUSSETZUNG: Session muss gültig sein.
 * Das Script prüft zuerst ob Calls klappen – bei 403 stoppt es sofort.
 *
 * ANLEITUNG:
 *   1. Seite frisch laden (F5) + warten bis Matches-Liste erscheint
 *   2. F12 → Console → Text einfügen → Enter
 *   3. Script prüft Session, dann sanftes Auto-Scroll (~18 Min für 11.145)
 *   4. Download startet automatisch; manuell: window._download()
 *
 * Befehle:
 *   window._status()    → Anzahl erfasster Matches
 *   window._download()  → sofort herunterladen
 *   window._stop()      → stoppen
 * =========================================================================== */

(async () => {
  "use strict";

  const TOTAL  = 11145;
  const DELAY  = () => 3800 + Math.random() * 2400;  // 3.8 – 6.2 Sek (zufällig)
  const STABLE = 15;   // Runden ohne neue Matches → fertig

  let _running  = true;
  let _xhr403s  = 0;   // 403-Zähler aus React's eigenen Calls

  // ── 1. XHR-Spy: React's axios-Calls abfangen ────────────────────────────
  const captured = new Map();
  const _XHROpen = XMLHttpRequest.prototype.open;
  const _XHRSend = XMLHttpRequest.prototype.send;

  XMLHttpRequest.prototype.open = function(method, url, ...rest) {
    this._mhUrl = String(url || "");
    return _XHROpen.apply(this, [method, url, ...rest]);
  };

  XMLHttpRequest.prototype.send = function(body) {
    const xhr = this;
    const url = xhr._mhUrl;

    if (url.includes("web-family-graphql") || url.includes("familygraphql")) {
      xhr.addEventListener("readystatechange", function() {
        if (xhr.readyState !== 4) return;

        if (xhr.status === 403) {
          _xhr403s++;
          if (_xhr403s >= 3) {
            console.error(`[SPY] ⛔ ${_xhr403s} × 403 – Session abgelaufen! Bitte Seite neu laden.`);
            _running = false;
          }
          return;
        }
        _xhr403s = 0; // Reset bei Erfolg

        if (xhr.status !== 200) return;
        try {
          const json = JSON.parse(xhr.responseText);
          const arr  = json?.data?.dna_kit?.dna_matches?.data;
          if (Array.isArray(arr) && arr.length > 0) {
            let added = 0;
            arr.forEach(m => { if (m?.id && !captured.has(m.id)) { captured.set(m.id, m); added++; } });
            if (added > 0)
              console.log(`[SPY] +${added} Matches → gesamt: ${captured.size}/${TOTAL}`);
          }
        } catch(_) {}
      });
    }
    return _XHRSend.apply(this, arguments);
  };

  // fetch-Spy als Fallback
  const _zeFetch = window.fetch;
  window.fetch = async function(...args) {
    const resp = await _zeFetch.apply(this, args);
    const url  = typeof args[0] === "string" ? args[0] : (args[0]?.url ?? "");
    if (url.includes("web-family-graphql") || url.includes("familygraphql")) {
      resp.clone().json().then(j => {
        const arr = j?.data?.dna_kit?.dna_matches?.data;
        if (Array.isArray(arr) && arr.length > 0) {
          let added = 0;
          arr.forEach(m => { if (m?.id && !captured.has(m.id)) { captured.set(m.id, m); added++; } });
          if (added > 0) console.log(`[SPY-fetch] +${added} → ${captured.size}/${TOTAL}`);
        }
      }).catch(() => {});
    }
    return resp;
  };

  console.log("[SPY] ✓ XHR + fetch Spy aktiv – warte auf erste Matches …");

  // ── Hilfsfunktionen ──────────────────────────────────────────────────────
  function doDownload(label = "") {
    const arr = Array.from(captured.values());
    if (!arr.length) { console.log("[SPY] Nichts zu downloaden"); return 0; }
    const obj = {
      meta: { kit_id: "dnakit-9F9E6C0C-5EF0-4A73-9F85-1F1C8219B3A2",
              site_id: "OYYV65GLYXMJ2JPTF5BJPM3IIQRB5LQ",
              total_count: TOTAL, downloaded_count: arr.length,
              downloaded_at: new Date().toISOString(), method: "xhr_spy_v4" },
      matches: arr,
    };
    const blob = new Blob([JSON.stringify(obj, null, 2)], { type: "application/json" });
    const name = `mh_spy_${arr.length}${label}.json`;
    const a = Object.assign(document.createElement("a"), { href: URL.createObjectURL(blob), download: name });
    document.body.appendChild(a); a.click(); document.body.removeChild(a);
    console.log(`[SPY] ✓ Download: ${name}`);
    return arr.length;
  }

  window._status   = () => { console.log(`[SPY] ${captured.size}/${TOTAL}`); return captured.size; };
  window._download = () => doDownload();
  window._stop     = () => { _running = false; console.log("[SPY] Gestoppt"); };

  // ── 2. Warten bis erste Matches erscheinen ───────────────────────────────
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  const t0 = Date.now();
  while (captured.size === 0 && Date.now() - t0 < 15000) {
    await sleep(500);
  }

  if (_xhr403s >= 3 || !_running) {
    console.error("[SPY] ❌ Session ungültig. Bitte Seite neu laden und erneut anmelden.");
    return;
  }
  if (captured.size === 0) {
    console.warn("[SPY] ⚠️ Keine Matches in 15 Sek. Seite ggf. neu laden.");
  } else {
    console.log(`[SPY] ✓ Session gültig – ${captured.size} Matches bereits geladen`);
  }

  // ── 3. Scroll-Container ──────────────────────────────────────────────────
  const SKIP = ["nav","menu","dropdown","header","footer","toolbar","popup","modal","sidebar","tabs"];

  function findContainer() {
    if (document.documentElement.scrollHeight > window.innerHeight + 300) return "window";
    let best = null, bestH = 0;
    document.querySelectorAll("div,section,main,article").forEach(el => {
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
    // Kleiner zufälliger Betrag (simuliert Mausrad)
    const amount = 900 + Math.floor(Math.random() * 600);
    if (container === "window") {
      window.scrollBy({ top: amount, behavior: "smooth" });
      document.documentElement.scrollTop += amount;
      document.body.scrollTop += amount;
    } else {
      container.scrollTop = Math.min(container.scrollTop + amount, container.scrollHeight);
    }
    // Scroll-Events (für infinite-scroll-Listener)
    [window, document, document.documentElement, document.body].forEach(t => {
      try { t.dispatchEvent(new Event("scroll", { bubbles: true })); } catch(_) {}
    });
  }

  // ── 4. Sanfter Auto-Scroll ───────────────────────────────────────────────
  let container = findContainer();
  let lastCount = captured.size;
  let stable    = 0;
  let scrolls   = 0;

  console.log(`[SCROLL] Start – Container: ${container === "window" ? "window" : container.tagName}`);

  while (_running && stable < STABLE && captured.size < TOTAL) {
    scrollStep(container);

    // Zufällige Pause – menschenähnlich
    const wait = DELAY();
    await sleep(wait);
    scrolls++;

    // Gelegentlich längere Pause (liest angeblich)
    if (scrolls % 15 === 0) {
      const longPause = 4000 + Math.random() * 3000;
      console.log(`[SCROLL] kurze Pause ${(longPause/1000).toFixed(1)}s …`);
      await sleep(longPause);
    }

    if (scrolls % 20 === 0) container = findContainer();

    if (captured.size > lastCount) {
      lastCount = captured.size;
      stable = 0;
    } else {
      stable++;
    }

    // Status alle 10 Scrolls
    if (scrolls % 10 === 0) {
      const pct = (captured.size / TOTAL * 100).toFixed(1);
      const eta = stable >= STABLE - 3
        ? "fast fertig?"
        : `~${Math.round((TOTAL - captured.size) / Math.max(1, captured.size / scrolls) * (wait/1000) / 60)} Min`;
      console.log(`[SCROLL] ${scrolls} Scrolls | ${captured.size}/${TOTAL} (${pct}%) | ${eta}`);
    }

    // Backup alle 1000 Matches
    if (captured.size > 0 && captured.size % 1000 < 3 && captured.size !== lastCount) {
      doDownload(`_backup`);
    }

    if (!_running) { console.log("[SPY] Manuell gestoppt"); break; }
  }

  // ── 5. Abschluss ────────────────────────────────────────────────────────
  if (captured.size > 0) {
    console.log(`[SPY] ✅ Fertig: ${captured.size}/${TOTAL} Matches`);
    doDownload("_final");
  } else {
    console.error("[SPY] ❌ Nichts erfasst → Session war ungültig");
  }
})();
