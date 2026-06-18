"""GEDmatch-Export: DNA-Matches als One-to-Many-TSV ausgeben.

Spiegelt das von ancestry/tools/import_gedmatch_matches.py gelesene Format
(Tab-getrennt, GEDmatch „One-to-Many"):

  Kit_Number  Name  Email  Tags  Sex  Total_cM  Largest_Seg  Gen
  X-DNA_cM  X-DNA_Segs  Source  SNPs  Overlap  mtDNA  YDNA

Damit sind exportierte Matches wieder importierbar bzw. in GEDmatch-kompatiblen
Werkzeugen nutzbar. Reine Logik (kein DB/GUI), daher testbar.
"""
from __future__ import annotations

GEDMATCH_COLUMNS = [
    "Kit_Number", "Name", "Email", "Tags", "Sex", "Total_cM", "Largest_Seg",
    "Gen", "X-DNA_cM", "X-DNA_Segs", "Source", "SNPs", "Overlap", "mtDNA", "YDNA",
]

# kanonische Quelle → GEDmatch-Plattformkürzel
_SOURCE_MAP = {
    "ancestry": "Ancestry", "myheritage": "MyHeritage", "gedmatch": "GEDmatch",
    "ftdna": "FTDNA", "23andme": "23andMe",
}


def _get(m, key, default=None):
    """Liest ein Feld aus dict ODER Objekt (DnaMatch)."""
    if isinstance(m, dict):
        return m.get(key, default)
    return getattr(m, key, default)


def _row(m) -> list[str]:
    cm   = float(_get(m, "shared_cm", 0) or 0)
    seg  = float(_get(m, "longest_segment", 0) or 0)
    src  = str(_get(m, "source", "") or "").strip().lower()
    return [
        str(_get(m, "match_guid", "") or ""),        # Kit_Number
        str(_get(m, "display_name", "") or ""),      # Name
        "",                                          # Email (nicht vorhanden)
        "",                                          # Tags
        "",                                          # Sex (unbekannt)
        f"{cm:.1f}",                                 # Total_cM
        f"{seg:.1f}" if seg else "",                 # Largest_Seg
        "",                                          # Gen
        "", "",                                      # X-DNA_cM, X-DNA_Segs
        _SOURCE_MAP.get(src, src.title() if src else ""),  # Source
        "", "", "", "",                              # SNPs, Overlap, mtDNA, YDNA
    ]


def export_gedmatch_matches(matches, min_cm: float = 0.0) -> str:
    """Erzeugt den GEDmatch-One-to-Many-TSV-Text für die übergebenen Matches.

    matches: Iterable von DnaMatch-Objekten oder dicts.
    min_cm:  nur Matches ab dieser cM-Grenze exportieren.
    Sortiert absteigend nach Total_cM.
    """
    rows = [m for m in (matches or []) if float(_get(m, "shared_cm", 0) or 0) >= min_cm]
    rows.sort(key=lambda m: float(_get(m, "shared_cm", 0) or 0), reverse=True)
    lines = ["\t".join(GEDMATCH_COLUMNS)]
    lines.extend("\t".join(_row(m)) for m in rows)
    return "\n".join(lines) + "\n"
