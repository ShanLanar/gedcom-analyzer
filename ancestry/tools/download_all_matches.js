/* ===========================================================================
 * MyHeritage DNA – Alle Matches herunterladen (v2 – korrekte Query)
 * ===========================================================================
 *
 * ANLEITUNG:
 *   1. https://www.myheritage.com/dna/matches/OYYV65GLYXMJ2JPTF5BJPM3IIQRB5LQ öffnen
 *   2. Warten bis Matches sichtbar sind
 *   3. F12 → Console → gesamten Text einfügen → Enter
 *   4. Warten (~3-4 Min) – Fortschritt erscheint in Console
 *   5. Datei mh_all_matches.json wird automatisch heruntergeladen
 *   6. Alle 500 Matches gibt es eine Zwischendatei als Backup
 *
 * Endpunkt: familygraphql.myheritage.com → Ze fängt ab → /web-family-graphql
 * Kit-ID:   internes dnakit-UUID Format (nicht die URL-ID)
 * =========================================================================== */

(async () => {
  "use strict";

  const KIT_ID  = "dnakit-9F9E6C0C-5EF0-4A73-9F85-1F1C8219B3A2";
  const SITE_ID = "OYYV65GLYXMJ2JPTF5BJPM3IIQRB5LQ";
  // Ze interceptiert Aufrufe an familygraphql.myheritage.com
  const ENDPOINT = "https://familygraphql.myheritage.com/graphql";
  const LIMIT    = 50;
  const DELAY    = 700;   // ms zwischen Requests
  const SORT     = "total_shared_segments_length_in_cm"; // Stärkste zuerst

  const sleep = ms => new Promise(r => setTimeout(r, ms));

  function download(filename, obj) {
    const blob = new Blob([JSON.stringify(obj, null, 2)], { type: "application/json" });
    const a = Object.assign(document.createElement("a"), {
      href: URL.createObjectURL(blob), download: filename,
    });
    document.body.appendChild(a); a.click(); document.body.removeChild(a);
    console.log(`[MH] ✓ Download: ${filename}`);
  }

  // Exakt dieselbe Query wie die React-App (aus IndexedDB-Cache extrahiert).
  // WICHTIG: exact_dna_relationship und genealogical_relationship sind Skalare
  // (kein { } Sub-Selektion), filter_by_labels/filter_by_country korrekt.
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
      filter_by_country: "0",
      filter_by_labels: ""
    ) {
      count
      data {
        id
        link
        is_new
        complete_dna_relationships { relationship_type relationship_degree }
        refined_dna_relationships  { relationship_type relationship_degree }
        dna_cm_explainer {
          relationships { ...dna_match_relationship }
          most_probable_relationships { ...dna_match_relationship }
          calculation_strategy
        }
        exact_dna_relationship
        genealogical_relationship
        total_shared_segments_length_in_cm
        largest_shared_segment_length_in_cm
        percentage_of_shared_segments
        total_shared_segments
        is_recently_recalculated
        confidence_level
        other_dna_kit {
          submitter {
            id name name_transliterated first_name first_name_transliterated
            link is_public
          }
          member {
            id first_name first_name_transliterated name name_transliterated
            gender age_group age_group_in_years
            personal_photo { ...PERSONAL_PHOTO_INFO }
            country_code country is_public link
          }
          associated_individual {
            id first_name first_name_transliterated name name_transliterated
            gender age_group age_group_in_years
            personal_photo { ...PERSONAL_PHOTO_INFO }
            birth_place
            tree { ...tree_info }
            relationship { ...RELATIONSHIP_INFO }
            link_in_pedigree_tree link_in_tree
          }
        }
      }
    }
  }
}

fragment dna_match_relationship on DnaMatchRelationship {
  relationship_type relationship_class path_type probability
  most_recent_common_ancestor_relationship_type
  most_recent_common_ancestor_relationship_class
}
fragment tree_info on Tree {
  id name link individual_count
  site {
    is_request_membership_allowed
    creator { id name name_transliterated country country_code link is_public }
  }
}
fragment PERSONAL_PHOTO_INFO on Photo {
  thumbnails (thumbnail_size: "96x96") { url }
}
fragment RELATIONSHIP_INFO on Relationship {
  relationship_description
}`;
  }

  async function gqlFetch(query) {
    const resp = await fetch(ENDPOINT, {
      method: "POST",
      credentials: "same-origin",
      headers: {
        "Content-Type":    "application/json",
        "Accept":          "application/json",
        "X-Requested-With":"XMLHttpRequest",
      },
      body: JSON.stringify({ query }),
    });
    if (!resp.ok) {
      const body = await resp.text().catch(() => "");
      throw new Error(`HTTP ${resp.status}: ${body.slice(0, 300)}`);
    }
    const json = await resp.json();
    if (json?.errors?.length) {
      // GQL-Fehler loggen aber trotzdem weitermachen (partial data möglich)
      console.warn("[MH] GQL-Fehler:", JSON.stringify(json.errors).slice(0, 400));
    }
    return json;
  }

  // ── Schritt 1: Gesamtanzahl ermitteln ────────────────────────────────────
  console.log("[MH] Ermittle Gesamtanzahl …");
  let totalCount = 0;
  try {
    const r = await gqlFetch(
      `{ dna_kit (id: "${KIT_ID}") { dna_matches (offset: 0, limit: 1, sort_query: "${SORT}") { count } } }`
    );
    totalCount = r?.data?.dna_kit?.dna_matches?.count ?? 0;
    console.log(`[MH] Gesamt: ${totalCount} Matches`);
  } catch(e) {
    console.error("[MH] Count-Query Fehler:", e.message);
    totalCount = 11145; // Bekannter Wert als Fallback
    console.warn(`[MH] Nutze Fallback: ${totalCount}`);
  }

  if (!totalCount) {
    console.error("[MH] Keine Matches gefunden. Seite neu laden und erneut versuchen.");
    return;
  }

  // ── Schritt 2: Alle Seiten laden ─────────────────────────────────────────
  const allMatches = [];
  const totalPages = Math.ceil(totalCount / LIMIT);
  let errors = 0;

  for (let page = 0; page < totalPages; page++) {
    const offset = page * LIMIT;

    if (page % 5 === 0) {
      const pct = ((page / totalPages) * 100).toFixed(1);
      console.log(`[MH] Seite ${page+1}/${totalPages} (${pct}%) – ${allMatches.length} geladen`);
    }

    try {
      const r = await gqlFetch(makeQuery(offset));
      const data = r?.data?.dna_kit?.dna_matches?.data;

      if (Array.isArray(data) && data.length > 0) {
        allMatches.push(...data);
        errors = 0; // Reset bei Erfolg

        // Zwischenspeichern alle 500 Matches
        if (allMatches.length % 500 < LIMIT) {
          download(`mh_matches_partial_${allMatches.length}.json`, allMatches);
        }
      } else if (Array.isArray(data) && data.length === 0) {
        console.log(`[MH] Seite ${page+1} leer – fertig bei ${allMatches.length} Matches`);
        break;
      } else {
        console.warn(`[MH] Seite ${page+1}: data=null – GQL-Fehler?`);
        errors++;
        if (errors > 5) { console.error("[MH] Zu viele Fehler, Abbruch."); break; }
        await sleep(2000);
      }
    } catch(e) {
      console.error(`[MH] Fehler Seite ${page+1}:`, e.message);
      errors++;
      if (errors > 5) { console.error("[MH] Zu viele Fehler, Abbruch."); break; }
      await sleep(3000);
    }

    await sleep(DELAY);
  }

  // ── Schritt 3: Download ──────────────────────────────────────────────────
  console.log(`\n[MH] ✅ ${allMatches.length} von ${totalCount} Matches geladen`);

  const result = {
    meta: {
      kit_id:           KIT_ID,
      site_id:          SITE_ID,
      total_count:      totalCount,
      downloaded_count: allMatches.length,
      downloaded_at:    new Date().toISOString(),
      sort:             SORT,
    },
    matches: allMatches,
  };

  download("mh_all_matches.json", result);
  console.log(`[MH] Fertig! ${allMatches.length} Matches in mh_all_matches.json`);
  return result;
})();
