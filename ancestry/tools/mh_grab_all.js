/* ===========================================================================
 * MyHeritage DNA – ALLE Matches herunterladen  (v3 – konsolidiert)
 * ===========================================================================
 *
 * Warum dieses Script und nicht die alten?
 *   • download_all_matches.js rief https://familygraphql.myheritage.com/graphql
 *     DIREKT auf und verließ sich auf den fetch-Patch der App → fragil, schlug
 *     fehl wenn der Patch nicht aktiv war (CORS / falsche Auth).
 *   • query_mh.js hatte den RICHTIGEN Auth-Weg (same-origin /web-family-graphql
 *     mit access_token + x-xsrf-token, bewährt durch erfolgreiche Introspection),
 *     aber lud nur 10 Matches zum Testen.
 *
 *   → Dieses Script kombiniert beide: bewährte Auth + vollständige Pagination.
 *   → Die Query-Form stammt 1:1 aus dem IndexedDB-Cache der App (verifiziert).
 *
 * ANLEITUNG:
 *   1. https://www.myheritage.com/dna/matches/OYYV65GLYXMJ2JPTF5BJPM3IIQRB5LQ öffnen
 *   2. Warten bis die ersten Matches sichtbar sind (App muss initialisiert sein)
 *   3. F12 → Console → diesen GESAMTEN Text einfügen → Enter
 *   4. Laufen lassen (~3–4 Min für 11.145 Matches). Fortschritt in der Console.
 *   5. Am Ende lädt sich mh_all_matches.json automatisch herunter.
 *      Alle 500 Matches gibt es eine Backup-Zwischendatei.
 *   6. Datei nach ancestry/tools/ legen, dann:
 *        python import_mh_matches.py mh_all_matches.json
 * =========================================================================== */

(async () => {
  "use strict";

  // ── Konfiguration ─────────────────────────────────────────────────────────
  const KIT_ID  = "dnakit-9F9E6C0C-5EF0-4A73-9F85-1F1C8219B3A2";
  const SITE_ID = location.pathname.match(/\/([A-Z0-9]{20,})/)?.[1]
                  || "OYYV65GLYXMJ2JPTF5BJPM3IIQRB5LQ";
  const GQLEP   = "/web-family-graphql";   // same-origin Proxy (kein CORS, Cookies inkl.)
  const LIMIT   = 50;                        // wie die App – nicht erhöhen (Server kappt evtl.)
  const DELAY   = 650;                       // ms zwischen Seiten
  const SORT    = "total_shared_segments_length_in_cm";  // stärkste zuerst
  const REFRESH_EVERY = 40;                  // Token alle N Seiten erneuern (Ablauf vermeiden)

  const sleep = ms => new Promise(r => setTimeout(r, ms));

  function download(filename, obj) {
    const blob = new Blob([JSON.stringify(obj, null, 2)], { type: "application/json" });
    const a = Object.assign(document.createElement("a"), {
      href: URL.createObjectURL(blob), download: filename,
    });
    document.body.appendChild(a); a.click(); document.body.removeChild(a);
    console.log(`[MH] ✓ Download: ${filename}`);
  }

  // ── Token holen (App-Service bevorzugt, PHP-Endpoint als Fallback) ────────
  async function getToken() {
    try {
      const Svc = (globalThis.api || {}).FamilyGraphTokenService;
      if (Svc) {
        const t = await new Svc().getToken(true);   // true = frischer Token
        if (t) return t;
      }
    } catch (e) { /* still fall through */ }
    try {
      const ts   = Date.now();
      const xsrf = globalThis.mhXsrfToken || "";
      const resp = await fetch(
        `/FP/API/FamilyGraph/get-familygraph-token.php?_=${ts}&csrf_token=${encodeURIComponent(xsrf)}`,
        { credentials: "same-origin", headers: { Accept: "application/json" } }
      );
      const d = await resp.json();
      return d?.data?.token || "";
    } catch (e) {
      console.error("[MH] Token-Fehler:", e.message);
      return "";
    }
  }

  let TOKEN = await getToken();
  const XSRF = globalThis.mhXsrfToken || "";
  if (!TOKEN) {
    console.error("[MH] ❌ Kein Token erhalten. Seite neu laden, warten bis Matches "
                + "sichtbar sind, dann erneut ausführen.");
    return;
  }
  console.log("[MH] Token OK:", TOKEN.slice(0, 32) + "…");

  // ── GraphQL-Aufruf ────────────────────────────────────────────────────────
  async function gql(query) {
    const resp = await fetch(`${GQLEP}?access_token=${encodeURIComponent(TOKEN)}`, {
      method: "POST",
      credentials: "same-origin",
      headers: {
        "Content-Type":     "application/json",
        "Accept":           "application/json",
        "x-xsrf-token":     XSRF,
        "X-Requested-With": "XMLHttpRequest",
      },
      body: JSON.stringify({ query }),
    });
    if (resp.status === 401 || resp.status === 403) {
      // Token abgelaufen → einmal erneuern und Aufrufer signalisieren
      console.warn("[MH] Auth abgelaufen – erneuere Token …");
      TOKEN = await getToken();
      throw new Error("AUTH_REFRESH");
    }
    if (!resp.ok) {
      const body = await resp.text().catch(() => "");
      throw new Error(`HTTP ${resp.status}: ${body.slice(0, 200)}`);
    }
    return resp.json();
  }

  // ── Query-Form (Stufen: 0 = voll+Filter, 1 = voll, 2 = minimal) ───────────
  // Stufe 0/1 = 1:1 aus IndexedDB-Cache der App. Stufe 2 = nur Felder die der
  // Python-Importer (import_mh_matches.py) wirklich liest → kleinste Fehlerfläche.
  function dataQuery(offset, level) {
    const args = (level === 0)
      ? `offset: ${offset}, limit: ${LIMIT}, sort_query: "${SORT}", query: "", `
        + `filter: "0", filter_by_relationship: "0", filter_by_country: "0", filter_by_labels: ""`
      : `offset: ${offset}, limit: ${LIMIT}, sort_query: "${SORT}"`;

    if (level >= 2) {
      // Minimal: genau das, was der Importer braucht.
      return `{
        dna_kit (id: "${KIT_ID}", lang: "EN") {
          dna_matches (${args}) {
            count
            data {
              id link is_new
              complete_dna_relationships { relationship_type relationship_degree }
              refined_dna_relationships  { relationship_type relationship_degree }
              total_shared_segments_length_in_cm
              largest_shared_segment_length_in_cm
              total_shared_segments
              percentage_of_shared_segments
              confidence_level
              other_dna_kit {
                submitter { id name }
                member { id name gender country_code country link }
                associated_individual { id name birth_place tree { id name individual_count link } }
              }
            }
          }
        }
      }`;
    }

    return `{
      dna_kit (id: "${KIT_ID}", lang: "EN") {
        dna_matches (${args}) {
          count
          data {
            id link is_new
            complete_dna_relationships { relationship_type relationship_degree }
            refined_dna_relationships  { relationship_type relationship_degree }
            dna_cm_explainer {
              relationships { ...rel }
              most_probable_relationships { ...rel }
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
              submitter { id name name_transliterated first_name link is_public }
              member {
                id first_name name name_transliterated gender
                age_group age_group_in_years country_code country is_public link
              }
              associated_individual {
                id first_name name name_transliterated gender birth_place
                tree { ...tree_info }
                link_in_pedigree_tree link_in_tree
              }
            }
          }
        }
      }
    }
    fragment rel on DnaMatchRelationship {
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
    }`;
  }

  // ── Eine Seite laden – Auth-Retry + automatische Query-Eskalation ──────────
  // queryLevel bleibt erhalten, sobald eine niedrigere Stufe nötig war.
  let queryLevel = 0;
  async function fetchPage(offset) {
    for (let attempt = 0; attempt < 4; attempt++) {
      try {
        const r = await gql(dataQuery(offset, queryLevel));
        const dm  = r?.data?.dna_kit?.dna_matches ?? null;
        const errs = r?.errors?.length ? JSON.stringify(r.errors).slice(0, 300) : "";

        // Daten fehlen ODER Schema-/Argument-Fehler → eine Stufe simpler
        if ((!dm || dm.data == null) && queryLevel < 2) {
          queryLevel++;
          console.warn(`[MH] Query-Eskalation → Stufe ${queryLevel}`
                     + (errs ? ` (${errs})` : ""));
          continue;
        }
        if (errs) console.warn("[MH] GQL-Hinweis (fahre fort):", errs);
        return dm;
      } catch (e) {
        if (e.message === "AUTH_REFRESH") { await sleep(500); continue; }
        throw e;
      }
    }
    return null;
  }

  // ── Schritt 1: Gesamtanzahl ───────────────────────────────────────────────
  let totalCount = 0;
  try {
    const head = await fetchPage(0);
    totalCount = head?.count ?? 0;
    if (head?.data?.length) {
      console.log(`[MH] Erster Match: `
        + `${head.data[0]?.other_dna_kit?.member?.name || "?"} · `
        + `${head.data[0]?.total_shared_segments_length_in_cm} cM`);
    }
  } catch (e) {
    console.error("[MH] Count/Head-Query Fehler:", e.message);
  }
  if (!totalCount) { totalCount = 11145; console.warn(`[MH] Fallback Gesamt: ${totalCount}`); }
  console.log(`[MH] Gesamt: ${totalCount} Matches → starte Download …`);

  // ── Schritt 2: Alle Seiten via robustem Offset (advance by data.length) ───
  const seen = new Set();
  const allMatches = [];
  let offset = 0, errors = 0, pageNo = 0;

  while (offset < totalCount) {
    pageNo++;
    if (pageNo % REFRESH_EVERY === 0) {
      TOKEN = await getToken();   // proaktiver Refresh
    }

    let block;
    try {
      block = await fetchPage(offset);
    } catch (e) {
      console.error(`[MH] Fehler @offset ${offset}:`, e.message);
      if (++errors > 6) { console.error("[MH] Zu viele Fehler – Abbruch."); break; }
      await sleep(2500);
      continue;
    }

    const data = block?.data;
    if (!Array.isArray(data) || data.length === 0) {
      console.log(`[MH] Leere Seite @offset ${offset} – fertig bei ${allMatches.length}.`);
      break;
    }
    errors = 0;
    if (block.count) totalCount = block.count;   // aktuellsten Gesamtwert übernehmen

    let added = 0;
    for (const m of data) {
      if (m?.id && !seen.has(m.id)) { seen.add(m.id); allMatches.push(m); added++; }
    }
    offset += data.length;   // robust gegen serverseitige Seitengrößen-Kappung

    if (pageNo % 5 === 0 || allMatches.length >= totalCount) {
      const pct = ((allMatches.length / totalCount) * 100).toFixed(1);
      console.log(`[MH] ${allMatches.length}/${totalCount} (${pct}%) – offset ${offset}`);
    }

    // Backup alle 500
    if (Math.floor(allMatches.length / 500) > Math.floor((allMatches.length - added) / 500)) {
      download(`mh_matches_partial_${allMatches.length}.json`,
               { meta: { kit_id: KIT_ID, site_id: SITE_ID, total_count: totalCount,
                         downloaded_count: allMatches.length, partial: true, sort: SORT },
                 matches: allMatches });
    }

    await sleep(DELAY);
  }

  // ── Schritt 3: Finaler Download ───────────────────────────────────────────
  const result = {
    meta: {
      kit_id:           KIT_ID,
      site_id:          SITE_ID,
      total_count:      totalCount,
      downloaded_count: allMatches.length,
      downloaded_at:    new Date().toISOString(),
      sort:             SORT,
      source:           "web-family-graphql",
    },
    matches: allMatches,
  };
  download("mh_all_matches.json", result);
  console.log(`[MH] ✅ FERTIG: ${allMatches.length}/${totalCount} Matches → mh_all_matches.json`);
  console.log(`[MH] Nächster Schritt: python import_mh_matches.py mh_all_matches.json`);
  globalThis._mhResult = result;   // auch als globale Variable verfügbar
  return result;
})();
