/* ===========================================================================
 * MyHeritage – Diagnose-Script (in Browser-Console einfügen)
 *
 * ANLEITUNG:
 *   1. https://www.myheritage.com/dna/matches/OYYV65GLYXMJ2JPTF5BJPM3IIQRB5LQ öffnen
 *   2. Warten bis Matches sichtbar
 *   3. F12 → Console → diesen Text einfügen → Enter
 *   4. Ausgabe hier einfügen (alle [DIAG] Zeilen)
 * =========================================================================== */
(async () => {
  "use strict";
  const KIT_ID = "dnakit-9F9E6C0C-5EF0-4A73-9F85-1F1C8219B3A2";
  const GQLEP  = "/web-family-graphql";
  const XSRF   = globalThis.mhXsrfToken || "";

  // ── 1. Token holen ──────────────────────────────────────────────────────
  let token = "";
  try {
    const Svc = (globalThis.api || {}).FamilyGraphTokenService;
    if (Svc) token = await new Svc().getToken(true);
  } catch(e) {}
  if (!token) {
    try {
      const r = await fetch(`/FP/API/FamilyGraph/get-familygraph-token.php?_=${Date.now()}&csrf_token=${encodeURIComponent(XSRF)}`,
        { credentials: "same-origin", headers: { Accept: "application/json" } });
      token = (await r.json())?.data?.token || "";
    } catch(e) {}
  }
  console.log("[DIAG] Token:", token ? token.slice(0,40)+"…" : "❌ KEINER");
  console.log("[DIAG] XSRF:", XSRF ? XSRF.slice(0,20)+"…" : "❌ leer");
  if (!token) { console.error("[DIAG] Abbruch: kein Token"); return; }

  const url = `${GQLEP}?access_token=${encodeURIComponent(token)}`;
  const hdrs = {
    "Content-Type": "application/json",
    "Accept": "application/json",
    "x-xsrf-token": XSRF,
    "X-Requested-With": "XMLHttpRequest",
  };

  async function q(label, query) {
    try {
      const r = await fetch(url, { method:"POST", credentials:"same-origin",
        headers: hdrs, body: JSON.stringify({ query }) });
      const body = await r.text();
      let parsed;
      try { parsed = JSON.parse(body); } catch(e) { parsed = null; }
      const ok = r.status === 200;
      const tag = ok ? "✅" : "❌";
      console.log(`[DIAG] ${tag} [${r.status}] ${label}`);
      if (parsed?.errors?.length) {
        console.warn("[DIAG]    GQL-Fehler:", JSON.stringify(parsed.errors).slice(0,400));
      }
      if (parsed?.data) {
        const d = JSON.stringify(parsed.data).slice(0,300);
        console.log("[DIAG]    data:", d);
      } else if (body.length < 500) {
        console.log("[DIAG]    body:", body);
      } else {
        console.log("[DIAG]    body(Anfang):", body.slice(0,300));
      }
      return parsed;
    } catch(e) {
      console.error(`[DIAG] ❌ ${label}:`, e.message);
      return null;
    }
  }

  // ── 2. Introspection (hat früher funktioniert) ──────────────────────────
  console.log("\n[DIAG] === Test 1: Introspection ===");
  await q("Introspection DnaKit",
    `{ __type(name:"DnaKit") { fields { name type { name } } } }`);

  // ── 3. Count-only – minimal ─────────────────────────────────────────────
  console.log("\n[DIAG] === Test 2: Count-only (beide Feldnamen) ===");
  const r2a = await q("count (Feld: count)",
    `{ dna_kit(id:"${KIT_ID}", lang:"EN") { dna_matches(offset:0,limit:1) { count } } }`);
  const r2b = await q("count (Feld: total_count)",
    `{ dna_kit(id:"${KIT_ID}", lang:"EN") { dna_matches(offset:0,limit:1) { total_count } } }`);

  // ── 4. 1 Match – nur ID + cM ────────────────────────────────────────────
  console.log("\n[DIAG] === Test 3: 1 Match minimal (id + cM) ===");
  const r3 = await q("1 Match minimal",
    `{ dna_kit(id:"${KIT_ID}", lang:"EN") {
       dna_matches(offset:0, limit:1) {
         data { id total_shared_segments_length_in_cm }
       }
     } }`);

  // ── 5. 1 Match + filter_by_labels Argument ──────────────────────────────
  console.log("\n[DIAG] === Test 4: 1 Match mit filter_by_labels ===");
  await q("1 Match mit Filtern",
    `{ dna_kit(id:"${KIT_ID}", lang:"EN") {
       dna_matches(offset:0, limit:1, sort_query:"total_shared_segments_length_in_cm",
                   query:"", filter:"0", filter_by_relationship:"0",
                   filter_by_country:"0", filter_by_labels:"") {
         data { id total_shared_segments_length_in_cm }
       }
     } }`);

  // ── 6. Fragment-Test ────────────────────────────────────────────────────
  console.log("\n[DIAG] === Test 5: Fragment-Syntax ===");
  await q("Fragment-Test",
    `{ dna_kit(id:"${KIT_ID}", lang:"EN") {
       dna_matches(offset:0, limit:1) {
         data { id ...relInfo }
       }
     } }
     fragment relInfo on DnaMatch {
       complete_dna_relationships { relationship_type relationship_degree }
     }`);

  // ── 7. Zusammenfassung ──────────────────────────────────────────────────
  const countField = r2a?.data?.dna_kit?.dna_matches?.count != null ? "count"
                   : r2b?.data?.dna_kit?.dna_matches?.total_count != null ? "total_count"
                   : "❓ keins";
  const got1 = r3?.data?.dna_kit?.dna_matches?.data?.length > 0;
  const id1  = r3?.data?.dna_kit?.dna_matches?.data?.[0]?.id || "—";
  console.log("\n[DIAG] === ZUSAMMENFASSUNG ===");
  console.log("[DIAG] Token-Methode: OK");
  console.log("[DIAG] Korrektes count-Feld:", countField);
  console.log("[DIAG] 1 Match ladbar:", got1 ? `✅ (${id1})` : "❌");
  console.log("[DIAG] Bitte ALLE obigen Zeilen kopieren.");
})();
