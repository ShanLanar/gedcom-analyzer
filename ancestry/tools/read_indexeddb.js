/* ===========================================================================
 * MyHeritage DNA – IndexedDB-Extraktor
 * ===========================================================================
 * Die React-App cached DNA-Matches in IndexedDB (Store "dna").
 * Dieses Script liest sie direkt aus dem Browser-Cache.
 *
 * ANLEITUNG:
 *   1. https://www.myheritage.com/dna/matches/OYYV65GLYXMJ2JPTF5BJPM3IIQRB5LQ öffnen
 *   2. F12 → Console → diesen Text komplett einfügen → Enter
 *   3. Ergebnis erscheint in ~3 Sek in Console + wird als JSON heruntergeladen
 * =========================================================================== */

(async () => {
  "use strict";

  // ── Schritt 1: Alle IndexedDB-Datenbanken auflisten ──────────────────────
  let allDbs = [];
  try {
    allDbs = await indexedDB.databases();
    console.log("[IDB] Gefundene Datenbanken:", allDbs.map(d => `${d.name} (v${d.version})`));
  } catch(e) {
    console.warn("[IDB] indexedDB.databases() nicht verfügbar, versuche bekannte Namen …");
  }

  function download(filename, obj) {
    const blob = new Blob([JSON.stringify(obj, null, 2)], { type: "application/json" });
    const a = Object.assign(document.createElement("a"), {
      href: URL.createObjectURL(blob), download: filename,
    });
    document.body.appendChild(a); a.click(); document.body.removeChild(a);
    console.log(`[IDB] Heruntergeladen: ${filename}`);
  }

  async function readAllFromStore(db, storeName) {
    return new Promise((resolve, reject) => {
      try {
        const tx   = db.transaction(storeName, "readonly");
        const store= tx.objectStore(storeName);
        const req  = store.getAll();
        req.onsuccess = () => resolve(req.result);
        req.onerror   = () => reject(req.error);
      } catch(e) { reject(e); }
    });
  }

  async function openDb(name, version) {
    return new Promise((resolve, reject) => {
      const req = indexedDB.open(name, version);
      req.onsuccess = () => resolve(req.result);
      req.onerror   = () => reject(req.error);
      req.onblocked = () => reject(new Error("Blocked"));
    });
  }

  // ── Schritt 2: Bekannte MyHeritage DB-Namen durchprobieren ───────────────
  const candidateNames = [
    "mhClientCache", "mh-client-cache", "mhCache", "dna-cache",
    "myheritage", "mh_dna", "clientCache", "mhDB",
    ...allDbs.map(d => d.name).filter(Boolean),
  ];
  const uniqueNames = [...new Set(candidateNames)];

  const allResults = {};
  let foundAny = false;

  for (const dbName of uniqueNames) {
    try {
      const dbInfo = allDbs.find(d => d.name === dbName);
      const db = await openDb(dbName, dbInfo?.version || undefined);
      const storeNames = [...db.objectStoreNames];
      console.log(`[IDB] DB "${dbName}" – Stores: ${storeNames.join(", ")}`);

      for (const storeName of storeNames) {
        try {
          const records = await readAllFromStore(db, storeName);
          if (records && records.length > 0) {
            console.log(`  Store "${storeName}": ${records.length} Einträge`);
            // Nach DNA-relevanten Daten suchen
            const txt = JSON.stringify(records);
            const hasDna = ["dna_match","sharedDna","shared_dna","dnaMatch","matchId",
                            "display_name","shared_cm","chromosome"].some(k => txt.includes(k));
            if (hasDna) {
              console.log(`  *** DNA-DATEN GEFUNDEN in "${dbName}"."${storeName}"!`);
              allResults[`${dbName}.${storeName}`] = records;
              foundAny = true;
              // Vorschau
              const first = records[0];
              console.log("  Erster Eintrag:", JSON.stringify(first).slice(0, 500));
            } else {
              allResults[`${dbName}.${storeName}`] = `${records.length} Einträge (kein DNA-Inhalt)`;
            }
          } else {
            console.log(`  Store "${storeName}": leer`);
          }
        } catch(e) {
          console.log(`  Store "${storeName}": Fehler: ${e.message}`);
        }
      }
      db.close();
    } catch(e) {
      // DB nicht gefunden oder kein Zugriff – überspringen
    }
  }

  // ── Schritt 3: Ergebnisse ausgeben ───────────────────────────────────────
  if (foundAny) {
    console.log("\n[IDB] ✅ DNA-Daten gefunden! Download startet …");
    download("mh_indexeddb_dna.json", allResults);
  } else {
    console.log("\n[IDB] ⚠️  Keine DNA-Daten in IndexedDB gefunden.");
    console.log("[IDB] Alle gefundenen Datenbanken & Stores:");
    console.log(JSON.stringify(allResults, null, 2));
    download("mh_indexeddb_all.json", allResults);
    console.log("\n[IDB] Tipp: Lade die Seite neu (F5), warte bis Matches sichtbar sind,");
    console.log("      dann dieses Script erneut ausführen.");
  }
})();
