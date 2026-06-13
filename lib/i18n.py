"""Sprachumschaltung (DE↔EN) für die rohen tk-Reiter (Start, Stammbaum).

Diese Reiter haben kein Key-basiertes Übersetzungssystem; daher wird – analog
zum Theme-Rethemer – per Text-Substitution über den Widgetbaum übersetzt: der
sichtbare deutsche Text eines Widgets wird gegen die englische Version getauscht
(und zurück). Dynamische Texte (Statuszeilen, Dateipfade) bleiben unangetastet.

Die DNA-Matches-App übersetzt sich selbst über ihr eigenes TRANSLATIONS-System
(set_language); deren Strings stehen NICHT in dieser Map.
"""
from __future__ import annotations

# Deutsch → Englisch (nur statische Beschriftungen der Start-/Stammbaum-Reiter)
DE_EN: dict[str, str] = {
    # Start: Abschnitts-Titel
    "📄  GEDCOM — Stammbaumdatei  (wird von BEIDEN Werkzeugen benötigt)":
        "📄  GEDCOM — family tree file  (required by BOTH tools)",
    "🔑  Ancestry-Login  (Cookie-Datei oder Kit-GUID)":
        "🔑  Ancestry login  (cookie file or kit GUID)",
    "📊  Datenbank-Status": "📊  Database status",
    "🔧  Tools & Schnellzugriff": "🔧  Tools & quick access",
    "📁  Verzeichnisse": "📁  Directories",
    "🏠  Genealogie-Suite — Einstellungen & Start":
        "🏠  Genealogy Suite — Settings & Start",
    # Start: Feld-Labels
    "Stammbaumdatei:": "Tree file:",
    "Zuletzt:": "Recent:",
    "Root-ID:": "Root ID:",
    "Exclude-ID:": "Exclude ID:",
    # Start: Buttons
    "▶ GEDCOM laden & analysieren": "▶ Load & analyze GEDCOM",
    "↺ Pfad merken  (kein Reload)": "↺ Remember path  (no reload)",
    "↺ Aktualisieren": "↺ Refresh",
    "🏘 Matricula laden": "🏘 Load Matricula",
    "① Erste Schritte": "① First steps",
    "? Hilfe": "? Help",
    "Protokoll": "Log",
    "Schließen": "Close",
    "Login wird beim Start eingehängt …": "Login is mounted at startup …",
    "… läuft": "… running",
    "⚠ fehlt": "⚠ missing",
    # Start: Datenbank-Status-Labels
    "DNA-Kits:": "DNA kits:",
    "Shared Matches:": "Shared matches:",
    "GEDCOM-Personen:": "GEDCOM persons:",
    "Matricula-Orte:": "Matricula places:",
    # Start: Verzeichnis-Labels
    "Ausgabe:": "Output:",
    "Protokolle:": "Logs:",
    "DNA-Datenbank:": "DNA database:",
    "Matricula-JSON:": "Matricula JSON:",
    # Reiter-Titel (Notebook) – via nb.tab(text=…), separat behandelt
    "  🏠 Start  ": "  🏠 Start  ",
    "  🌳 Stammbaum-Auswertung  ": "  🌳 Tree analysis  ",
    "  🧬 DNA-Matches  ": "  🧬 DNA matches  ",
}


def _map(to_en: bool) -> dict:
    return DE_EN if to_en else {v: k for k, v in DE_EN.items()}


def retranslate_tree(widget, to_en: bool) -> None:
    """Übersetzt den sichtbaren Text aller Widgets unter `widget` (DE↔EN)."""
    cmap = _map(to_en)
    stack = [widget]
    while stack:
        w = stack.pop()
        try:
            t = str(w.cget("text"))
            if t in cmap:
                w.configure(text=cmap[t])
        except Exception:
            pass
        try:
            stack.extend(w.winfo_children())
        except Exception:
            pass


def translate_notebook(nb, to_en: bool) -> None:
    """Übersetzt die Reiter-Beschriftungen eines ttk.Notebook."""
    cmap = _map(to_en)
    try:
        for tab_id in nb.tabs():
            cur = str(nb.tab(tab_id, "text"))
            if cur in cmap:
                nb.tab(tab_id, text=cmap[cur])
    except Exception:
        pass
