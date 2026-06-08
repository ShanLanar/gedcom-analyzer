/* ===========================================================================
 * MyHeritage DNA – Spy + Auto-Scroll (alle Matches erfassen)
 * ===========================================================================
 *
 * STRATEGIE: Nicht selbst API-Calls machen (Ze/Imperva blockiert Console-Calls),
 * sondern die React-App's eigene erfolgreiche Calls abfangen und die Matches
 * beim Scrollen einsammeln.
 *
 * ANLEITUNG:
 *   1. https://www.myheritage.com/dna/matches/OYYV65GLYXMJ2JPTF5BJPM3IIQRB5LQ öffnen
 *   2. Warten bis erste Matches sichtbar sind
 *   3. F12 → Console → diesen Text einfügen → Enter
 *   4. Script scrollt automatisch und erfasst alle Matches (~7-15 Min)
 *   5. Download startet automatisch, oder: window._download() aufrufen
 *
 * Zwischenstand: window._status() → aktuell erfasste Anzahl
 * Manueller Download: window._download()
 * =========================================================================== */

(async () => {
  "use strict";

  const TOTAL_EXPECTED = 11145;
  const SCROLL_DELAY   = 1500;  // ms zwischen Scroll-Schritten
  const MAX_STABLE_ROUNDS = 8;  // Runden ohne neue Matches → fertig

  // ── 1. Fetch-Spy installieren ────────────────────────────────────────────
  const captured  = new Map();   // match_id → match-Daten
  const _realFetch = window.fetch; // Ze's gepatchte Version

  window.fetch = async function(...args) {
    const response = await _realFetch.apply(this, args);
    const url = (typeof args[0] === "string" ? args[0] : args[0]?.url || "");

    // DNA-Match-Antworten abfangen (Ze leitet zu /web-family-graphql)
    if (url.includes("web-family-graphql") || url.includes("familygraphql")) {
      response.clone().json().then(json => {
        // dna_matches-Antwort
        const arr = json?.data?.dna_kit?.dna_matches?.data;
        if (Array.isArray(arr) && arr.length > 0) {
          let newCount = 0;
          arr.forEach(m => { if (m?.id && !captured.has(m.id)) { captured.set(m.id, m); newCount++; } });
          if (newCount > 0) {
            console.log(`[SPY] +${newCount} neue Matches (gesamt: ${captured.size}/${TOTAL_EXPECTED})`);
          }
        }
      }).catch(() => {});
    }
    return response;
  };

  console.log("[SPY] ✓ Fetch-Spy aktiv – starte Auto-Scroll …");

  // ── Hilfsfunktionen ──────────────────────────────────────────────────────
  function download(filename, obj) {
    const blob = new Blob([JSON.stringify(obj, null, 2)], { type: "application/json" });
    const a = Object.assign(document.createElement("a"), {
      href: URL.createObjectURL(blob), download: filename,
    });
    document.body.appendChild(a); a.click(); document.body.removeChild(a);
    console.log(`[SPY] ✓ Download: ${filename} (${captured.size} Matches)`);
  }

  window._status = () => {
    console.log(`[SPY] Erfasst: ${captured.size}/${TOTAL_EXPECTED}`);
    return captured.size;
  };

  window._download = () => {
    const arr = Array.from(captured.values());
    download(`mh_spy_${arr.length}.json`, {
      meta: {
        kit_id:           "dnakit-9F9E6C0C-5EF0-4A73-9F85-1F1C8219B3A2",
        site_id:          "OYYV65GLYXMJ2JPTF5BJPM3IIQRB5LQ",
        total_count:      TOTAL_EXPECTED,
        downloaded_count: arr.length,
        downloaded_at:    new Date().toISOString(),
        method:           "spy_scroll",
      },
      matches: arr,
    });
    return arr.length;
  };

  // ── 2. Scroll-Container finden ───────────────────────────────────────────
  function findScrollContainer() {
    // Mögliche Selektoren für die MH DNA-Matches-Liste
    const candidates = [
      ".dna-matches-list",
      "[class*='MatchesList']",
      "[class*='matches-list']",
      "[class*='matchesList']",
      "[class*='DNAMatches']",
      "[class*='dna-matches']",
      ".infinite-scroll-component",
      "[data-testid*='match']",
      // Fallback: größtes scrollbares Element
    ];
    for (const sel of candidates) {
      const el = document.querySelector(sel);
      if (el && el.scrollHeight > el.clientHeight) {
        console.log(`[SCROLL] Container gefunden: ${sel}`);
        return el;
      }
    }
    // Fallback: erstes Element mit Overflow-Auto oder -Scroll
    const all = document.querySelectorAll("*");
    for (const el of all) {
      const style = window.getComputedStyle(el);
      if ((style.overflow === "auto" || style.overflowY === "auto" ||
           style.overflow === "scroll" || style.overflowY === "scroll") &&
          el.scrollHeight > el.clientHeight + 100) {
        console.log(`[SCROLL] Container (Overflow-Fallback): ${el.tagName}.${el.className.split(" ")[0]}`);
        return el;
      }
    }
    console.log("[SCROLL] Kein spezifischer Container gefunden – scrolle document");
    return null;
  }

  function scrollStep(container) {
    if (container) {
      container.scrollTop += 3000;
    }
    // Immer auch window/document scrollen
    window.scrollTo({ top: document.documentElement.scrollHeight, behavior: "smooth" });
    document.documentElement.scrollTop += 5000;
    document.body.scrollTop += 5000;
  }

  // ── 3. Auto-Scroll-Schleife ──────────────────────────────────────────────
  const sleep = ms => new Promise(r => setTimeout(r, ms));

  // Kurz warten damit erste Matches geladen sind
  await sleep(1500);

  let container = findScrollContainer();
  let lastCount = captured.size;
  let stableRounds = 0;
  let totalScrolls = 0;

  while (stableRounds < MAX_STABLE_ROUNDS) {
    scrollStep(container);
    await sleep(SCROLL_DELAY);
    totalScrolls++;

    // Container neu suchen (falls DOM sich geändert hat)
    if (totalScrolls % 20 === 0) {
      container = findScrollContainer();
    }

    if (captured.size > lastCount) {
      lastCount = captured.size;
      stableRounds = 0;
    } else {
      stableRounds++;
    }

    // Fortschritt alle 50 Scrolls loggen
    if (totalScrolls % 50 === 0) {
      const pct = (captured.size / TOTAL_EXPECTED * 100).toFixed(1);
      console.log(`[SCROLL] ${totalScrolls} Scrolls, ${captured.size}/${TOTAL_EXPECTED} (${pct}%), stabil: ${stableRounds}/${MAX_STABLE_ROUNDS}`);
    }

    // Zwischendownload alle 500 neue Matches
    if (captured.size > 0 && captured.size % 500 < 10 && captured.size !== lastCount) {
      window._download();
    }

    // Abbruch wenn alle erfasst
    if (captured.size >= TOTAL_EXPECTED) {
      console.log(`[SCROLL] ✅ Alle ${TOTAL_EXPECTED} Matches erfasst!`);
      break;
    }
  }

  // ── 4. Ergebnis herunterladen ────────────────────────────────────────────
  if (captured.size === 0) {
    console.warn("[SPY] ⚠️  Keine Matches erfasst.");
    console.warn("[SPY] Tipp: Seite neu laden, Matches-Liste sichtbar machen, dann erneut ausführen.");
    console.warn("[SPY] Oder: manuell durch die Liste scrollen und dann window._download() aufrufen.");
  } else {
    console.log(`\n[SPY] ✅ Fertig! ${captured.size} Matches erfasst.`);
    window._download();
  }
})();
