/* ===========================================================================
 * MyHeritage DNA – GraphQL-Direkt-Query
 * ===========================================================================
 *
 * ANLEITUNG:
 *   1. https://www.myheritage.com/dna/matches/OYYV65GLYXMJ2JPTF5BJPM3IIQRB5LQ öffnen
 *   2. F12 → "Console" → diesen GESAMTEN Text einfügen → Enter
 *   3. Warten (~5 Sek) – Ergebnis erscheint in der Console
 *   4. Rechtsklick auf das Ergebnis → "Copy object" (oder "Store as global variable")
 *      ODER: Die Datei mh_schema.json / mh_matches.json wird automatisch heruntergeladen
 *
 * =========================================================================== */

(async () => {
  "use strict";

  const KIT  = location.pathname.match(/\/([A-Z0-9]{20,})/)?.[1] || "OYYV65GLYXMJ2JPTF5BJPM3IIQRB5LQ";
  // MyHeritage patcht window.fetch: familygraphql.myheritage.com → /web-family-graphql
  // Wir rufen den Proxy-Endpunkt direkt auf (same-origin, keine CORS-Probleme)
  const GQLEP = "/web-family-graphql";

  // ── Token holen ─────────────────────────────────────────────────────────────
  console.log("[MH-Query] Hole FamilyGraph-Token …");
  let token;
  try {
    const FGTokenSvc = (globalThis.api || {}).FamilyGraphTokenService;
    const svc = FGTokenSvc ? new FGTokenSvc() : null;
    if (svc) {
      token = await svc.getToken(true);  // true = fresh token
      console.log("[MH-Query] Token via FamilyGraphTokenService:", token?.slice(0, 40) + "…");
    } else {
      // Fallback: direkt holen
      const ts  = Date.now();
      const xsrf = globalThis.mhXsrfToken || "";
      const resp = await fetch(
        `/FP/API/FamilyGraph/get-familygraph-token.php?_=${ts}&csrf_token=${encodeURIComponent(xsrf)}`,
        { credentials: "same-origin", headers: { Accept: "application/json" } }
      );
      const d = await resp.json();
      token = d?.data?.token;
      console.log("[MH-Query] Token via PHP:", token?.slice(0, 40) + "…");
    }
  } catch(e) {
    console.error("[MH-Query] Token-Fehler:", e);
    return;
  }

  if (!token) { console.error("[MH-Query] Kein Token!"); return; }

  const xsrf = globalThis.mhXsrfToken || "";

  async function gql(query, label) {
    const resp = await fetch(`${GQLEP}?access_token=${encodeURIComponent(token)}`, {
      method: "POST",
      credentials: "same-origin",
      headers: {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "x-xsrf-token": xsrf,
        "X-Requested-With": "XMLHttpRequest",
      },
      body: JSON.stringify({ query }),
    });
    if (!resp.ok) { console.error(`[MH-Query] ${label}: HTTP ${resp.status}`); return null; }
    return resp.json();
  }

  function download(filename, obj) {
    const blob = new Blob([JSON.stringify(obj, null, 2)], { type: "application/json" });
    const a = Object.assign(document.createElement("a"), {
      href: URL.createObjectURL(blob), download: filename,
    });
    document.body.appendChild(a); a.click(); document.body.removeChild(a);
  }

  // ── Schritt 1: Schema-Introspection (Felder von DnaMatch / DnaMatches) ───────
  console.log("[MH-Query] Starte Schema-Introspection …");
  const introResult = await gql(`
    {
      __type(name: "DnaMatch") {
        name
        fields { name type { name kind ofType { name kind } } }
      }
    }
  `, "Introspection DnaMatch");

  if (introResult) {
    console.log("[MH-Query] DnaMatch-Felder:");
    const fields = introResult?.data?.__type?.fields || [];
    fields.forEach(f => console.log("  -", f.name, ":", f.type?.name || f.type?.ofType?.name));
    download("mh_schema.json", introResult);
  }

  // ── Schritt 2: dna_matches Query mit möglichst vielen Feldern ────────────────
  console.log("[MH-Query] Lade erste 10 Matches …");
  const matchResult = await gql(`
    {
      dna_kit (id: "${KIT}", lang: "EN") {
        dna_matches (limit: 10, offset: 0) {
          total_count
          data {
            id
            link
            display_name
            first_name
            last_name
            shared_dna
            shared_segments
            longest_segment
            relationship
            predicted_relationship
            image_url
            added_date
            kit_id
            country
            ethnicity_groups
          }
        }
      }
    }
  `, "dna_matches");

  if (matchResult) {
    console.log("[MH-Query] Ergebnis:");
    console.log(matchResult);
    download("mh_matches.json", matchResult);
    const count = matchResult?.data?.dna_kit?.dna_matches?.total_count;
    const first = matchResult?.data?.dna_kit?.dna_matches?.data?.[0];
    console.log(`[MH-Query] Total: ${count} Matches. Erster:`, first?.display_name, "–", first?.shared_dna, "cM");
  }

  // ── Schritt 3: Falls Felder fehlen, Fehler-Info ausgeben ─────────────────────
  if (matchResult?.errors) {
    console.warn("[MH-Query] GraphQL-Fehler (manche Felder fehlen vielleicht):");
    matchResult.errors.forEach(e => console.warn(" •", e.message, "→", JSON.stringify(e.path)));

    // Retry mit minimalen Feldern
    console.log("[MH-Query] Retry mit minimalen Feldern …");
    const minResult = await gql(`
      {
        dna_kit (id: "${KIT}", lang: "EN") {
          dna_matches (limit: 10) {
            total_count
            data { id display_name shared_dna relationship }
          }
        }
      }
    `, "minimal");
    if (minResult) { console.log("[MH-Query] Minimal-Ergebnis:", minResult); download("mh_matches_min.json", minResult); }
  }

  console.log("[MH-Query] Fertig!");
})();
