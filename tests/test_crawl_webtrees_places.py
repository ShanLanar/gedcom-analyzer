"""Tests für die Ortsnamen-Normalisierung (normalize_place).

Webtrees liefert verkürzte/uneinheitliche Orte; für den GEDCOM-Export müssen sie
auf das Muster ``Ort[, Stadt][, Landkreis], Bundesland, Staat`` gebracht werden.
Geprüft werden: Landkreis-Auffüllung, Bundesland-Übersetzung (DE→EN), Entfernen
der Ländercodes, Ortssuffix ``a.T.W.`` sowie Nicht-DE-Länder (USA/Polen).
"""
import ancestry.tools.crawl_webtrees as cw


def test_fills_district_and_translates_state():
    assert cw.normalize_place("Osnabrück, Niedersachsen") == \
        "Osnabrück, Osnabruck, Lower Saxony, Germany"


def test_strips_country_code_deu():
    assert cw.normalize_place("Schwagstorf, Ostercappeln, Niedersachsen, DEU") == \
        "Schwagstorf, Ostercappeln, Osnabruck, Lower Saxony, Germany"


def test_strips_atw_suffix_and_adds_district():
    # "Hagen a.T.W." (am Teutoburger Wald) → nur "Hagen", Landkreis Osnabruck
    assert cw.normalize_place("Beckerode, Hagen a.T.W.") == \
        "Beckerode, Hagen, Osnabruck, Lower Saxony, Germany"
    assert cw.normalize_place("St. Martinus, Hagen a.T.W., Niedersachsen, DEU") == \
        "St. Martinus, Hagen, Osnabruck, Lower Saxony, Germany"


def test_atw_suffix_in_four_part_place():
    # Tiefe Kette ohne Landkreis: der wird vor dem Bundesland eingefügt
    assert cw.normalize_place("Friedhof, Gellenbeck, Hagen a.T.W., Niedersachsen, DEU") == \
        "Friedhof, Gellenbeck, Hagen, Osnabruck, Lower Saxony, Germany"


def test_bare_country_code_pol_is_poland():
    assert cw.normalize_place("POL") == "Poland"


def test_usa_places_keep_their_hierarchy():
    # Nicht-deutsche Länder behalten ihre eigene Struktur, Code → voller Name
    assert cw.normalize_place("Baltimore, Maryland, USA") == "Baltimore, Maryland, USA"
    assert cw.normalize_place("Ottawa, Putnam, Ohio, USA") == "Ottawa, Putnam, Ohio, USA"


def test_nrw_state_translation():
    assert cw.normalize_place("Oberhausen, Nordrhein-Westfalen, DEU") == \
        "Oberhausen, North Rhine-Westphalia, Germany"


def test_steinhagen_maps_to_guetersloh():
    # lt. GEDCOM-Referenz: Steinhagen liegt im Landkreis Gütersloh (nicht Warendorf)
    assert cw.normalize_place("Steinhagen, Nordrhein-Westfalen") == \
        "Steinhagen, Gutersloh, North Rhine-Westphalia, Germany"


def test_subplace_to_city_to_district():
    # Ortsteil → übergeordnete Stadt → Landkreis
    assert cw.normalize_place("Harderberg, Georgsmarienhütte") == \
        "Harderberg, Georgsmarienhütte, Osnabruck, Lower Saxony, Germany"


def test_empty_place():
    assert cw.normalize_place("") == ""
    assert cw.normalize_place("   ") == ""
