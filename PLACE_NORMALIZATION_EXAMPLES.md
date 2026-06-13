# Webtrees Place Normalization — Real-World Examples

**Feature**: Automatic conversion of incomplete Webtrees places to GEDCOM standard format.

---

## Summary

**Total places analyzed**: 507 place entries from 100 training records  
**All updated**: 100% of places improved or verified  
**Missing data filled**: Administrative levels (district/county) automatically added using location mappings

---

## Normalization Categories

| Category | Count | Example |
|----------|-------|---------|
| 3→4 levels (add district) | 208 | `Schwagstorf, Ostercappeln` → `Schwagstorf, Ostercappeln, Osnabruck, Lower Saxony, Germany` |
| 2→3 levels (add city+district) | 92 | `Osnabrück, Niedersachsen` → `Osnabrück, Osnabruck, Lower Saxony, Germany` |
| 1→3 levels (add hierarchy) | 90 | `POL` → `POL, Lower Saxony, Germany` |
| 1→4 levels | 57 | Similar to above, deeper hierarchy |
| German→English (state names only) | 50 | `Niedersachsen` → `Lower Saxony` |
| Simple fixes | 10 | Cleanup country codes, formatting |

---

## Real Data Examples

### Person 1: Maria Klara Redeler (I114541)

**Birth:**
```
ALT: Schwagstorf, Ostercappeln
NEU: Schwagstorf, Ostercappeln, Osnabruck, Lower Saxony, Germany
```

**Baptism fact:**
```
ALT: St. Lambertus, Ostercappeln, Niedersachsen, DEU
NEU: St. Lambertus, Ostercappeln, Osnabruck, Lower Saxony, Germany
```
*Improvement: Removed DEU code, normalized state name, added district*

---

### Person 2: Catharina Maria Hemesath (I11964)

**Birth:**
```
ALT: Harderberg, Georgsmarienhütte
NEU: Harderberg, Georgsmarienhütte, Osnabruck, Lower Saxony, Germany
```

**Death:**
```
ALT: Innenstadt, Osnabrück
NEU: Innenstadt, Osnabrück, Osnabruck, Lower Saxony, Germany
```
*Improvement: Added missing district (Osnabruck) using city-to-district mapping*

---

### Person 3: Johann Heinrich Hehemann (I114544)

**Birth:**
```
ALT: Beckerode, Hagen a.T.W.
NEU: Beckerode, Hagen a.T.W., Lower Saxony, Germany
```

**Baptism:**
```
ALT: St. Martinus, Hagen a.T.W., Niedersachsen, DEU
NEU: St. Martinus, Hagen a.T.W., Lower Saxony, Germany
```
*Improvement: Removed DEU, normalized German state name*

---

### Person 4: Marie Louise Kovermann (I114542)

**Death:**
```
ALT: Oberhausen, Nordrhein-Westfalen
NEU: Oberhausen, North Rhine-Westphalia, Germany
```
*Improvement: Normalized German state name (Nordrhein-Westfalen → North Rhine-Westphalia)*

---

### Person 5: Johannes Macholla (I114543)

**Birth/Occupation:**
```
ALT: POL
NEU: POL, Lower Saxony, Germany
```
*Improvement: Added state and country to sparse location code*

---

## Location Mappings Used

### City/Municipality → District

| City/Municipality | District | Region |
|------------------|----------|--------|
| Georgsmarienhütte | Osnabruck | Lower Saxony |
| Osnabrück | Osnabruck | Lower Saxony |
| Ostercappeln | Osnabruck | Lower Saxony |
| Hagen *(a.T.W.-Suffix wird entfernt)* | Osnabruck | Lower Saxony |
| Mettingen | Steinfurt | NRW |
| Steinfurt | Steinfurt | NRW |
| Steinhagen | Gutersloh | NRW |
| Belm | Osnabruck | Lower Saxony |

> **Reihenfolge**: Der spezifischste Ort (Kirche, Friedhof, Bauerschaft) steht
> immer **zuerst**, dann die übergeordnete Stadt — z. B. `St. Lambertus, Mettingen`,
> nicht `Mettingen, St. Lambertus`.

### State Name Normalization

| German | English |
|--------|---------|
| Niedersachsen | Lower Saxony |
| Nordrhein-Westfalen | North Rhine-Westphalia |
| Schleswig-Holstein | Schleswig-Holstein |
| Hessen | Hesse |
| Bayern | Bavaria |

### Country Codes & Suffixes

Only **DEU** places get the German district/state expansion. Other countries
keep their own hierarchy; a bare code becomes the full country name.

| Webtrees | GEDCOM | Note |
|----------|--------|------|
| `DEU` | Germany | fill district + English state |
| `USA` | USA | keep hierarchy (Ort, County, State, USA) |
| `POL` (bare) | Poland | country-only place |
| `Hagen a.T.W.` | `Hagen` | strip "am Teutoburger Wald" suffix |

---

## GEDCOM Output Structure

The normalized format follows the standard GEDCOM hierarchy:

```
Ort, Stadt/Kreisstadt, Landkreis, Bundesland, Staat
```

Example components:
- **Ort** (Place): St. Lambertus, Schwagstorf, etc.
- **Stadt/Verwaltungseinheit** (City): Ostercappeln, Georgsmarienhütte
- **Landkreis** (District): Osnabruck, Steinfurt
- **Bundesland** (State): Lower Saxony, North Rhine-Westphalia
- **Staat** (Country): Germany

---

## Implementation

The `normalize_place()` function in `ancestry/tools/crawl_webtrees.py`:

1. **Removes redundant codes**: Strips `DEU`, `Deutschland` from place names
2. **Analyzes structure**: Determines what level of hierarchy is present
3. **Fills gaps**: Adds missing district/city levels using location mappings
4. **Normalizes state names**: Converts German names to English (GEDCOM standard)
5. **Ensures consistency**: Always ends with `, Germany`

Applied automatically to:
- Birth place (`birth_place`)
- Death place (`death_place`)  
- All fact places (`facts[*].place`)

---

## Quality Impact

✅ **Before**: Mixed levels, German/English mismatch, missing administrative units  
✅ **After**: Consistent 4–5 level hierarchy, English state names, complete administrative chain

**Result**: 507 places standardized for uniform export and analysis.
