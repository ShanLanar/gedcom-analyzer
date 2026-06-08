/* ===========================================================================
 * MyHeritage DNA – Alle Matches herunterladen (via Ze-gepatchtes fetch)
 * ===========================================================================
 *
 * ANLEITUNG:
 *   1. https://www.myheritage.com/dna/matches/OYYV65GLYXMJ2JPTF5BJPM3IIQRB5LQ öffnen
 *   2. Warten bis Matches sichtbar sind
 *   3. F12 → Console → diesen gesamten Text einfügen → Enter
 *   4. Warten (~3-4 Min) – Fortschritt erscheint in Console
 *   5. Datei "mh_all_matches.json" wird automatisch heruntergeladen
 *
 * WICHTIG: Script läuft im Browser-Kontext – Ze patcht window.fetch
 *   automatisch und fügt Auth-Header hinzu. Kein Token nötig.
 * =========================================================================== */

(async () => {
  "use strict";

  // Kit-ID aus IndexedDB / HTML (internes Format)
  const KIT_ID = "dnakit-9F9E6C0C-5EF0-4A73-9F85-1F1C8219B3A2";
  const SITE_ID = "OYYV65GLYXMJ2JPTF5BJPM3IIQRB5LQ";

  // Ze fängt Aufrufe an familygraphql.myheritage.com ab und
  // leitet sie zu /web-family-graphql mit Auth-Headern weiter
  const ENDPOINT = "https://familygraphql.myheritage.com/graphql";

  const LIMIT = 50;     // Matches pro Request (max. 50)
  const DELAY = 600;    // ms zwischen Requests (Rate Limiting)
  const SORT  = "total_shared_segments_length_in_cm"; // Stärkste zuerst

  const sleep = ms => new Promise(r => setTimeout(r, ms));

  function download(filename, obj) {
    const blob = new Blob([JSON.stringify(obj, null, 2)], { type: "application/json" });
    const a = Object.assign(document.createElement("a"), {
      href: URL.createObjectURL(blob), download: filename,
    });
    document.body.appendChild(a); a.click(); document.body.removeChild(a);
    console.log(`[MH] Heruntergeladen: ${filename}`);
  }

  // GraphQL-Query für eine Seite Matches
  function makeQuery(offset) {
    return `{
  dna_kit (id: "${KIT_ID}", lang: "EN") {
    dna_matches (
      offset: ${offset},
      limit: ${LIMIT},
      sort_query: "${SORT}",
      query: "",
      filter: "0",
      filter_by_relationship: "0",
      filter_by_label: "",
      filter_by_ancestral_place: "",
      filter_by_review_status: "",
      filter_by_ethnicity: "0"
    ) {
      count
      data {
        id
        link
        is_new
        total_shared_segments_length_in_cm
        largest_shared_segment_length_in_cm
        percentage_of_shared_segments
        total_shared_segments
        confidence_level
        is_recently_recalculated
        complete_dna_relationships {
          relationship_type
          relationship_degree
        }
        refined_dna_relationships {
          relationship_type
          relationship_degree
        }
        exact_dna_relationship {
          relationship_type
          relationship_degree
        }
        genealogical_relationship {
          description
        }
        other_dna_kit {
          submitter {
            id
            name
            first_name
            last_name
            country
            country_code
            link
            is_public
          }
          member {
            id
            first_name
            name
            gender
            age_group
            age_group_in_years
            country_code
            country
            is_public
            link
          }
          associated_individual {
            id
            first_name
            name
            gender
            birth_place
            tree {
              id
              name
              link
              individual_count
            }
            link_in_tree
          }
        }
      }
    }
  }
}`;
  }

  async function gqlFetch(query) {
    const resp = await fetch(ENDPOINT, {
      method: "POST",
      credentials: "same-origin",
      headers: {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "X-Requested-With": "XMLHttpRequest",
      },
      body: JSON.stringify({ query }),
    });
    if (!resp.ok) {
      const body = await resp.text().catch(() => "");
      throw new Error(`HTTP ${resp.status}: ${body.slice(0, 200)}`);
    }
    return resp.json();
  }

  // ── Schritt 1: Gesamt-Anzahl ermitteln ───────────────────────────────────
  console.log("[MH] Ermittle Gesamtanzahl …");
  let totalCount;
  try {
    const r = await gqlFetch(`{ dna_kit (id: "${KIT_ID}") { dna_matches (offset: 0, limit: 1, sort_query: "${SORT}") { count } } }`);
    totalCount = r?.data?.dna_kit?.dna_matches?.count;
    if (!totalCount) {
      // Fallback: aus bekanntem Wert
      totalCount = 11145;
      console.warn("[MH] count nicht ermittelt, nutze Fallback:", totalCount);
    } else {
      console.log(`[MH] Gesamt: ${totalCount} Matches`);
    }
  } catch(e) {
    console.error("[MH] Fehler bei Count-Query:", e.message);
    console.log("[MH] Versuche trotzdem zu laden …");
    totalCount = 11145;
  }

  // ── Schritt 2: Alle Seiten laden ─────────────────────────────────────────
  const allMatches = [];
  const totalPages = Math.ceil(totalCount / LIMIT);
  let errors = 0;

  for (let page = 0; page < totalPages; page++) {
    const offset = page * LIMIT;
    const pct = ((page / totalPages) * 100).toFixed(1);

    if (page % 10 === 0) {
      console.log(`[MH] Seite ${page + 1}/${totalPages} (${pct}%) – ${allMatches.length} Matches geladen`);
    }

    try {
      const r = await gqlFetch(makeQuery(offset));
      const data = r?.data?.dna_kit?.dna_matches?.data;
      if (data && data.length > 0) {
        allMatches.push(...data);
        // Zwischenspeichern alle 500 Matches
        if (allMatches.length % 500 === 0) {
          console.log(`[MH] Zwischenstand: ${allMatches.length} Matches – speichere …`);
          download(`mh_matches_partial_${allMatches.length}.json`, allMatches);
        }
      } else if (r?.errors) {
        console.warn(`[MH] Seite ${page + 1} – GraphQL-Fehler:`, JSON.stringify(r.errors).slice(0, 300));
        errors++;
        if (errors > 5) { console.error("[MH] Zu viele Fehler, Abbruch."); break; }
      } else {
        // Leer – wahrscheinlich Ende erreicht
        console.log(`[MH] Seite ${page + 1} leer – Abbruch bei ${allMatches.length} Matches`);
        break;
      }
    } catch(e) {
      console.error(`[MH] Fehler auf Seite ${page + 1}:`, e.message);
      errors++;
      if (errors > 5) { console.error("[MH] Zu viele Fehler, Abbruch."); break; }
      await sleep(2000); // Länger warten bei Fehler
    }

    await sleep(DELAY);
  }

  // ── Schritt 3: Ergebnis herunterladen ────────────────────────────────────
  console.log(`\n[MH] ✅ Fertig! ${allMatches.length} von ${totalCount} Matches geladen.`);

  const result = {
    meta: {
      kit_id: KIT_ID,
      site_id: SITE_ID,
      total_count: totalCount,
      downloaded_count: allMatches.length,
      downloaded_at: new Date().toISOString(),
      sort: SORT,
    },
    matches: allMatches,
  };

  download("mh_all_matches.json", result);
  console.log(`[MH] Datei mh_all_matches.json mit ${allMatches.length} Matches heruntergeladen.`);
  return result;
})();
