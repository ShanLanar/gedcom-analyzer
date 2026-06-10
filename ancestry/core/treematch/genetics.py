"""
Genetische Inferenz: Endogamie-Erkennung, Generationsschätzung,
Verwandtschaftsbezeichnungen, cM-basierte Vorfahren-Einschätzung.

Enthält: endogamy_flag, longest_to_generation, pair_relationship,
cm_to_mrca, cluster_confidence.
"""


def endogamy_flag(total_cm: float, num_segments: int, longest: float) -> tuple[str, float]:
    """Schätzt aus Segmentdaten, ob Endogamie/mehrere Linien vorliegen.
    Viele kleine Segmente bei moderater Gesamt-cM = mehrere geteilte Ahnenlinien.
    Ein großes längstes Segment = jüngerer gemeinsamer Vorfahr (eine klare Linie).
    Liefert (label, score 0..1) – score hoch = Endogamie wahrscheinlich."""
    total_cm = total_cm or 0
    num = num_segments or 0
    longest = longest or 0
    if num <= 0:
        return "unbekannt", 0.0
    avg = total_cm / num
    score = 0.0
    # viele Segmente, aber im Schnitt klein → typische Endogamie-Signatur
    if num >= 4 and avg < 12:
        score += 0.5
    if num >= 7 and longest < 15:
        score += 0.3
    if total_cm < 90 and num >= 5:
        score += 0.2
    # großes längstes Segment spricht GEGEN Endogamie (jüngere, klare Linie)
    if longest >= 30:
        score -= 0.4
    score = max(0.0, min(score, 1.0))
    label = ("Endogamie wahrscheinlich" if score >= 0.6 else
             "Endogamie möglich" if score >= 0.3 else
             "eher eine klare Linie")
    return label, round(score, 2)


def longest_to_generation(longest: float) -> int:
    """Grobe Generation des gemeinsamen Vorfahren aus dem längsten Segment
    (endogamie-robuster als Gesamt-cM). Wurzel=Gen 1."""
    l = longest or 0
    for thr, gen in [(90, 3), (50, 4), (30, 5), (18, 6), (12, 7), (0, 8)]:
        if l >= thr:
            return gen
    return 8


def cluster_confidence(size: int, density: float, median_cm: float = 0.0,
                       conv_frac: float = None, endogamy_score: float = 0.0,
                       n_confirmed: int = 0) -> dict:
    """Bewertet einen Cluster. Liefert dict mit:
      realness  – P(Cluster ist echt, kein Zufall) 0..1 (Größe × Dichte)
      cohesion  – Dichte (eine Linie vs. mehrere verschmolzen)
      conv      – Anteil Mitglieder, die auf denselben Vorfahren konvergieren
      label, note.
    Mitglieder sind NICHT unabhängig – darum dominiert die gegenseitige
    Vernetzung (Dichte), nicht die bloße Anzahl.

    Kombination per Noisy-OR: realness = 1 − ∏(1 − pᵢ) über die UNABHÄNGIGEN
    Evidenzquellen (1) Struktur=Größe×Dichte und (2) cM-Höhe. Innerhalb des
    Clusters wird NICHT pro Mitglied multipliziert (keine Unabhängigkeit) –
    die Größe geht dichte-gewichtet als 'effektive Bestätigungen' ein."""
    size = max(size, 1)
    d = max(0.0, min(density or 0.0, 1.0))
    # (1) Strukturelle Evidenz: effektive Bestätigungen ~ Größe × Dichte
    eff = 1 + (size - 1) * max(d, 0.25)
    p_struct = 1 - 0.5 ** eff
    # (2) cM-Evidenz: hohe cM ⇒ Mitglied praktisch sicher echt (kein IBC-Zufall)
    cm = median_cm or 0
    p_cm = 1 - 0.5 ** (cm / 18.0)          # 18cM→0.5, 36→0.75, 54→0.875, 90→0.97
    # (3) Bestätigungs-Evidenz: ≥1 Mitglied mit ThruLine/Baum-Link ⇒ die
    # Verbindung des Clusters zu DIR ist unabhängig belegt (auch niedrige cM echt).
    p_conf = 1 - 0.15 ** n_confirmed if n_confirmed else 0.0
    # Noisy-OR der unabhängigen Quellen (Gegenwahrscheinlichkeiten multiplizieren)
    realness = 1 - (1 - p_struct) * (1 - p_cm) * (1 - p_conf)
    if realness >= 0.97:
        label = "sehr hoch"
    elif realness >= 0.85:
        label = "hoch"
    elif realness >= 0.6:
        label = "mittel"
    else:
        label = "niedrig"
    note = ""
    if n_confirmed:
        note = (f"durch {n_confirmed} Mitglied(er) mit ThruLine/Baum-Link "
                "bestätigt – auch niedrige cM hier echt")
    elif cm and cm < 15:
        note = "niedrige cM → je Mitglied erhöhtes False-Positive-Risiko (IBC)"
    elif endogamy_score and endogamy_score >= 0.6:
        note = "viele kleine Segmente → Endogamie wahrscheinlich (mehrere Linien)"
    elif d < 0.3 and size >= 6:
        note = "lose vernetzt → evtl. mehrere Linien verschmolzen (Endogamie?)"
    elif conv_frac is not None and conv_frac < 0.4 and size >= 4:
        note = "geringe Pedigree-Konvergenz → Vorhersage unsicher"
    return {"realness": realness, "cohesion": d, "conv": conv_frac,
            "label": label, "note": note, "endogamy": endogamy_score}


def pair_relationship(cm: float) -> str:
    """Grobe Verwandtschaft ZWEIER Personen aus geteilten cM (Shared-cM-Project).
    Für die interne Cluster-Struktur (z.B. Eltern/Kind, Geschwister, Cousin)."""
    c = cm or 0
    for thr, label in [
        (2400, "Eltern/Kind o. Vollgeschwister"),
        (1450, "Geschwister/Großeltern/Onkel/Tante"),
        (850,  "Onkel/Tante o. Halbgeschwister"),
        (550,  "1. Cousin o. Großonkel"),
        (300,  "1C / 1C1R"),
        (150,  "1C1R / 2. Cousin"),
        (75,   "2. Cousin / 2C1R"),
        (40,   "2C1R / 3. Cousin"),
        (20,   "3. / 4. Cousin"),
        (0,    "entfernt (4C+)"),
    ]:
        if c >= thr:
            return label
    return "entfernt"


# Endogamie-Korrekturfaktoren nach Population/Region.
# Werte > 1.0: geteilte cM liegen ÜBER dem Erwartungswert für Nicht-Endogamie,
# d.h. die echte Verwandtschaft ist entfernter als die Tabelle zeigt.
# Quellen: Behar et al. 2013 (Ashkenazi), Ancestry cM-Auswertungen 2020.
ENDOGAMY_FACTORS: dict[str, float] = {
    "ashkenazi":    1.7,  # AJ-Gemeinschaft sehr endogam
    "jewish":       1.5,
    "mennonite":    1.6,
    "amish":        1.8,
    "icelandic":    1.3,
    "finn":         1.2,
    "finnish":      1.2,
    "sardinian":    1.4,
    "german":       1.05, # geringe Endogamie im deutschen Raum
    "osnabrück":    1.10, # niedersächsische Kleinbauern-Bevölkerung
    "ostwestfalen": 1.10,
}


def cm_to_mrca(cm: float, endogamy_factor: float = 1.0,
               population: str = "") -> tuple[str, int]:
    """Schätzt aus geteilten cM die Beziehung und die Pedigree-Generation des
    gemeinsamen Vorfahren (Wurzel=Gen 1). Basiert auf Shared-cM-Project-Mittelwerten.

    Parameters
    ----------
    cm:
        Geteilte cM.
    endogamy_factor:
        Korrekturfaktor > 1.0 für endogame Populationen. Teilt die cM vor dem
        Tabellen-Lookup (Endogamie erhöht cM, echte Verwandtschaft ist entfernter).
    population:
        Optionaler Populations-/Regions-Name für automatischen Faktor-Lookup
        (``ENDOGAMY_FACTORS``). Wird ignoriert, wenn endogamy_factor != 1.0.

    Returns
    -------
    (label, gen) — gen = erwartete Generation des gemeinsamen Vorfahren.
    """
    if endogamy_factor == 1.0 and population:
        key = population.lower().strip()
        for k, v in ENDOGAMY_FACTORS.items():
            if k in key or key in k:
                endogamy_factor = v
                break

    c = (cm or 0) / max(endogamy_factor, 0.5)
    table = [
        (1300, "Großeltern-/Onkel-/Tante-Ebene", 2),
        (575,  "1. Cousin (gem. Großeltern)",     3),
        (300,  "1C1R / 2. Cousin",                 4),
        (140,  "2. Cousin (gem. Urgroßeltern)",    4),
        (75,   "2C1R / 3. Cousin",                 5),
        (45,   "3. Cousin (gem. Ur-Urgroßeltern)", 5),
        (28,   "4. Cousin (gem. 3×-Urgroßeltern)", 6),
        (18,   "4.–5. Cousin",                     7),
        (10,   "5.–6. Cousin",                     8),
        (0,    "entfernt (≥6. Cousin)",            9),
    ]
    for thr, label, gen in table:
        if c >= thr:
            return label, gen
    return "unbekannt", 9
