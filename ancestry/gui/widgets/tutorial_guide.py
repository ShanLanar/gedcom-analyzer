"""ancestry/gui/widgets/tutorial_guide.py — Schritt-für-Schritt-Tutorial.

Öffnet ein nicht-modales Fenster mit 12 geführten Schritten
durch das Tool. Positioniert sich rechts neben dem Hauptfenster.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

STEPS: list[dict] = [
    {
        "title_de": "Willkommen beim Ancestry-DNA-Analyse-Tool",
        "title_en": "Welcome to the Ancestry DNA Analysis Tool",
        "text_de": (
            "Dieses Tool hilft dir, DNA-Matches mit deinem Stammbaum zu verknüpfen, "
            "Cluster zu bilden und Vorfahren zu identifizieren.\n\n"
            "Das Tutorial führt dich in 12 Schritten durch alle wichtigen Funktionen.\n\n"
            "Empfohlener Ablauf:\n"
            "  Start → Login → Herunterladen → Matches → Cluster → Statistiken\n"
            "       → Personen → Werkzeuge → Matricula"
        ),
        "text_en": (
            "This tool helps you link DNA matches to your family tree, "
            "build clusters, and identify ancestors.\n\n"
            "The tutorial guides you through all key features in 12 steps.\n\n"
            "Recommended workflow:\n"
            "  Start → Login → Download → Matches → Cluster → Statistics\n"
            "       → Persons → Tools → Matricula"
        ),
    },
    {
        "title_de": "1 · Start-Tab: GEDCOM / Stammbaum laden",
        "title_en": "1 · Start tab: Load GEDCOM / family tree",
        "text_de": (
            "Im Start-Tab lädst du deine GEDCOM-Datei (Stammbaum-Export aus FTM, "
            "Gramps, MacFamilyTree usw.) und wählst deine Wurzelperson.\n\n"
            "Wo bekommst du eine GEDCOM-Datei?\n"
            "  • Family Tree Maker: Datei → Exportieren → GEDCOM\n"
            "  • Gramps: Familie → Exportieren → GEDCOM\n"
            "  • Ancestry-Stammbaum: Stammbaum → Herunterladen → GEDCOM\n\n"
            "Hinweis FTM 2024 (MacKiev): Die .ftm-Datei ist verschlüsselt —\n"
            "bitte als GEDCOM exportieren und hier laden.\n\n"
            "Das GEDCOM wird für den Abgleich im Matches-Tab benötigt."
        ),
        "text_en": (
            "In the Start tab, you load your GEDCOM file (family tree export from FTM, "
            "Gramps, MacFamilyTree, etc.) and choose your root person.\n\n"
            "Where to get a GEDCOM file?\n"
            "  • Family Tree Maker: File → Export → GEDCOM\n"
            "  • Gramps: Family → Export → GEDCOM\n"
            "  • Ancestry tree: Tree → Download → GEDCOM\n\n"
            "Note for FTM 2024 (MacKiev): the .ftm file is encrypted —\n"
            "please export as GEDCOM and load it here.\n\n"
            "The GEDCOM is needed for matching in the Matches tab."
        ),
    },
    {
        "title_de": "2 · Login-Tab: Ancestry-Cookie laden",
        "title_en": "2 · Login tab: Load Ancestry cookie",
        "text_de": (
            "Ancestry blockiert automatisierte Logins — deshalb exportierst du "
            "deine Browser-Cookies nach dem manuellen Login.\n\n"
            "Schritt für Schritt:\n"
            "  1. Browser-Erweiterung »Cookie-Editor« installieren\n"
            "     (Chrome: Chrome Web Store | Firefox: Add-ons)\n"
            "  2. Auf ancestry.com einloggen\n"
            "  3. Cookie-Editor → Export → JSON → Datei speichern\n"
            "  4. Im Login-Tab: »Datei wählen …« → exportierte JSON-Datei öffnen\n"
            "  5. »Mit Cookies einloggen« klicken → Kit-GUID erscheint\n\n"
            "Der Login-Status bleibt gespeichert, bis Ancestry die Sitzung beendet.\n"
            "Bei HTTP 401/403-Fehlern: Schritt 1–5 wiederholen."
        ),
        "text_en": (
            "Ancestry blocks automated logins — so you export your browser cookies "
            "after logging in manually.\n\n"
            "Step by step:\n"
            "  1. Install the browser extension »Cookie-Editor«\n"
            "     (Chrome: Chrome Web Store | Firefox: Add-ons)\n"
            "  2. Log in on ancestry.com\n"
            "  3. Cookie-Editor → Export → JSON → save file\n"
            "  4. In the Login tab: click »Choose file …« → open the exported JSON\n"
            "  5. Click »Log in with cookies« → kit GUID appears\n\n"
            "The login state is saved until Ancestry ends the session.\n"
            "On HTTP 401/403 errors: repeat steps 1–5."
        ),
    },
    {
        "title_de": "3 · Herunterladen: Matches laden",
        "title_en": "3 · Download: Load matches",
        "text_de": (
            "Im Herunterladen-Tab rufst du Daten in dieser Reihenfolge ab:\n\n"
            "  A)  Matches herunterladen (alle oder gefiltert nach cM)\n"
            "  A2) Namen & Stammbaum nachladen\n"
            "      → Vorfahren & Orte laden (liefert Geburtsorte für Karte)\n"
            "      → Ahnentafeln laden (bis zu N Generationen)\n"
            "  B)  Shared Matches herunterladen (für Cluster-Bildung)\n\n"
            "Tipp: »A+A2+Vorfahren+B starten« führt alles nacheinander durch —\n"
            "kann über Nacht laufen (je nach Anzahl Matches mehrere Stunden).\n\n"
            "Höherer Min.-cM-Wert bei Shared Matches = deutlich schneller."
        ),
        "text_en": (
            "In the Download tab, fetch data in this order:\n\n"
            "  A)  Download matches (all or filtered by cM)\n"
            "  A2) Reload names & tree\n"
            "      → Load ancestors & places (provides birthplaces for map)\n"
            "      → Load pedigrees (up to N generations)\n"
            "  B)  Download shared matches (for cluster building)\n\n"
            "Tip: »Start A+A2+Ancestors+B« runs everything in sequence —\n"
            "can run overnight (several hours depending on number of matches).\n\n"
            "Higher min. cM for shared matches = much faster."
        ),
    },
    {
        "title_de": "4 · Matches-Tab: GEDCOM abgleichen",
        "title_en": "4 · Matches tab: GEDCOM matching",
        "text_de": (
            "Im Matches-Tab siehst du alle heruntergeladenen DNA-Matches.\n\n"
            "Wichtigste Aktion:\n"
            "  Auswertung → »Eigenen Baum (GEDCOM) abgleichen«\n"
            "  → verknüpft jeden Match mit Personen aus deinem Stammbaum.\n\n"
            "Filtere Matches nach:\n"
            "  • cM-Wert (Nähe der Verwandtschaft)\n"
            "  • Beziehungstyp (Cousin 2°, Halbgeschwister …)\n"
            "  • Seite (väterlich / mütterlich)\n"
            "  • Sternchen (manuell markierte Matches)\n\n"
            "Klicke einen Match an → Detailansicht mit Ahnentafel, Shared Matches,\n"
            "gemeinsamen Vorfahren und Kirchenbuch-Treffern."
        ),
        "text_en": (
            "The Matches tab shows all downloaded DNA matches.\n\n"
            "Most important action:\n"
            "  Analysis → »Match own tree (GEDCOM)«\n"
            "  → links every match to persons in your family tree.\n\n"
            "Filter matches by:\n"
            "  • cM value (closeness of the relationship)\n"
            "  • relationship type (2nd cousin, half-sibling …)\n"
            "  • side (paternal / maternal)\n"
            "  • star (manually starred matches)\n\n"
            "Click a match → detail view with pedigree, shared matches,\n"
            "common ancestors and church record hits."
        ),
    },
    {
        "title_de": "5 · Cluster-Tab: Leeds-Methode",
        "title_en": "5 · Cluster tab: Leeds method",
        "text_de": (
            "Der Cluster-Tab gruppiert DNA-Matches automatisch nach gemeinsamen "
            "Shared Matches (Leeds-Methode).\n\n"
            "Empfohlene Starteinstellungen:\n"
            "  • Primäre cM von: 20 – bis: 400\n"
            "  • Min. cM Shared: 15\n"
            "  → »🔄 Cluster berechnen«\n\n"
            "Jeder Cluster repräsentiert i. d. R. eine Verwandtschaftslinie.\n\n"
            "Klicke auf einen Cluster → »🌳 Stammbaum-Analyse«:\n"
            "  Zeigt gemeinsame Vorfahren aller Cluster-Mitglieder und\n"
            "  hilft, den gemeinsamen Vorfahren (MRCA) zu identifizieren.\n\n"
            "Ordne Cluster mit ⚡ Seite zuweisen den Großelternlinien zu."
        ),
        "text_en": (
            "The Cluster tab automatically groups DNA matches by shared "
            "matches (Leeds method).\n\n"
            "Recommended starting settings:\n"
            "  • Primary cM from: 20 – to: 400\n"
            "  • Min. cM shared: 15\n"
            "  → »🔄 Calculate clusters«\n\n"
            "Each cluster typically represents one family line.\n\n"
            "Click on a cluster → »🌳 Tree analysis«:\n"
            "  Shows common ancestors of all cluster members and\n"
            "  helps identify the most recent common ancestor (MRCA).\n\n"
            "Assign clusters to grandparent lines with ⚡ Assign side."
        ),
    },
    {
        "title_de": "6 · Statistiken-Tab",
        "title_en": "6 · Statistics tab",
        "text_de": (
            "Der Statistiken-Tab bietet:\n\n"
            "  • Kennzahlen: Gesamtzahl, cM-Verteilung, Sternchen, Bäume …\n"
            "  • Beziehungsverteilung (Tortendiagramm)\n"
            "  • Ahnentafel-Vollständigkeit pro Generation\n"
            "  • Ethnizitäts-Auswertung (nach »▶ Herkunft & Traits laden«)\n"
            "  • Kits & Matches (Übersicht aller importierten Quellen)\n\n"
            "Auswertungs-Menü (Menüleiste) bietet zusätzlich:\n"
            "  • Cluster-Netzwerkgraph\n"
            "  • Migrations-Analyse\n"
            "  • MRCA-Wahrscheinlichkeit\n"
            "  • Forschungs-Dashboard\n\n"
            "Tipp: »↻ Aktualisieren« nach jedem neuen Download."
        ),
        "text_en": (
            "The Statistics tab offers:\n\n"
            "  • Key figures: total count, cM distribution, stars, trees …\n"
            "  • Relationship distribution (pie chart)\n"
            "  • Pedigree completeness by generation\n"
            "  • Ethnicity analysis (after »▶ Load origin & traits«)\n"
            "  • Kits & matches (overview of all imported sources)\n\n"
            "The Analysis menu (menu bar) also offers:\n"
            "  • Cluster network graph\n"
            "  • Migration analysis\n"
            "  • MRCA probability\n"
            "  • Research dashboard\n\n"
            "Tip: »↻ Refresh« after each new download."
        ),
    },
    {
        "title_de": "7 · Personen-Tab: Stammbaum-Browser",
        "title_en": "7 · Persons tab: family tree browser",
        "text_de": (
            "Der Personen-Tab zeigt alle Personen aus importierten Quellen:\n\n"
            "  • GEDCOM   — deine eigene Forschung\n"
            "  • Webtrees — öffentlicher Stammbaum der Anverwandten\n"
            "  • WikiTree — importierte WikiTree-Profile (via API)\n\n"
            "Filtere nach Name, Datenquelle und Konfession.\n\n"
            "Klicke auf eine Person → Ahnentafel-Canvas mit\n"
            "verstellbarer Generationstiefe (1–5 Generationen).\n\n"
            "Die Konfessions-Anzeige wird aus dem Geburtsort und\n"
            "dem Matricula-Pfarrei-Katalog abgeleitet (kath./ev./unbek.)."
        ),
        "text_en": (
            "The Persons tab shows all persons from imported sources:\n\n"
            "  • GEDCOM   — your own research\n"
            "  • Webtrees — public family tree of relatives\n"
            "  • WikiTree — imported WikiTree profiles (via API)\n\n"
            "Filter by name, data source and religion.\n\n"
            "Click a person → pedigree canvas with\n"
            "adjustable generation depth (1–5 generations).\n\n"
            "The religion display is derived from the birthplace and\n"
            "the Matricula parish catalogue (cath./prot./unknown)."
        ),
    },
    {
        "title_de": "8 · Werkzeuge-Tab: Datenquellen-Pipeline",
        "title_en": "8 · Tools tab: data source pipeline",
        "text_de": (
            "Der Werkzeuge-Tab bündelt alle Import-Tools in einer Pipeline:\n\n"
            "  🗂 GEDCOM/FTM  — eigenen Baum laden / FTM-Direktbrücke\n"
            "  🧬 Ancestry    — Login erfolgt im Login-Tab\n"
            "  🌳 Webtrees    — öffentlichen Stammbaum crawlen\n"
            "  💙 MyHeritage  — DNA-Matches downloaden und importieren\n"
            "  🔗 GEDmatch    — One-to-Many TSV importieren\n"
            "  🔬 FTDNA       — Family Finder Matches-CSV importieren\n"
            "  🌐 WikiTree    — Vorfahren-Import via öffentliche API\n\n"
            "Klicke auf eine Quellen-Box → aufklappbares Detail-Panel mit\n"
            "DE+EN-Anleitung, Datei-Auswahl und Start-/Stop-Schaltflächen."
        ),
        "text_en": (
            "The Tools tab bundles all import tools in a pipeline:\n\n"
            "  🗂 GEDCOM/FTM  — load own tree / FTM direct bridge\n"
            "  🧬 Ancestry    — login happens in the Login tab\n"
            "  🌳 Webtrees    — crawl public family tree\n"
            "  💙 MyHeritage  — download and import DNA matches\n"
            "  🔗 GEDmatch    — import One-to-Many TSV\n"
            "  🔬 FTDNA       — import Family Finder matches CSV\n"
            "  🌐 WikiTree    — ancestor import via public API\n\n"
            "Click a source box → expandable detail panel with\n"
            "DE+EN instructions, file picker and start/stop buttons."
        ),
    },
    {
        "title_de": "9 · Matricula-Tab: Kirchenbücher transkribieren",
        "title_en": "9 · Matricula tab: transcribe parish registers",
        "text_de": (
            "Der Matricula-Tab transkribiert historische Kirchenbücher\n"
            "mit KI-gestützter Bildanalyse (Claude Vision, Tesseract, Kraken).\n\n"
            "Schritt für Schritt:\n"
            "  0) »0 · Pfarrei-Katalog« einmalig ausführen\n"
            "  1) Pfarrei aus der Liste auswählen (Strg+Klick = Mehrfach)\n"
            "     → »1 · Bücherverzeichnis holen«\n"
            "  2) »2 · Seiten scannen (Claude Vision)« starten\n"
            "     → lädt Bilder, schickt sie an die OCR-Engine,\n"
            "       speichert Transkriptionen in der Datenbank\n\n"
            "Transkribierte Einträge erscheinen im Matches-Tab\n"
            "(Detailansicht → ⛪ Kirchenbücher) und im Personen-Tab.\n\n"
            "Voraussetzung für Claude Vision: ANTHROPIC_API_KEY setzen."
        ),
        "text_en": (
            "The Matricula tab transcribes historical parish registers\n"
            "with AI-assisted image analysis (Claude Vision, Tesseract, Kraken).\n\n"
            "Step by step:\n"
            "  0) Run »0 · Parish catalogue« once\n"
            "  1) Select a parish from the list (Ctrl+Click = multiple)\n"
            "     → »1 · Fetch book directory«\n"
            "  2) Start »2 · Scan pages (Claude Vision)«\n"
            "     → loads images, sends them to the OCR engine,\n"
            "       saves transcriptions to the database\n\n"
            "Transcribed entries appear in the Matches tab\n"
            "(detail view → ⛪ Church records) and in the Persons tab.\n\n"
            "Prerequisite for Claude Vision: set ANTHROPIC_API_KEY."
        ),
    },
    {
        "title_de": "10 · Weitere DNA-Plattformen einbinden",
        "title_en": "10 · Adding more DNA platforms",
        "text_de": (
            "Neben Ancestry kannst du weitere DNA-Plattformen einbinden:\n\n"
            "  MyHeritage:\n"
            "    myheritage.com → DNA → Matches → Herunterladen → CSV\n"
            "    → Werkzeuge → 💙 MyHeritage → Match-CSV importieren\n\n"
            "  GEDmatch:\n"
            "    gedmatch.com → One-to-Many → Download → TSV\n"
            "    → Werkzeuge → 🔗 GEDmatch → TSV importieren\n\n"
            "  FTDNA:\n"
            "    ftdna.com → Family Finder → Matches → Herunterladen → CSV\n"
            "    → Werkzeuge → 🔬 FTDNA → CSV importieren\n\n"
            "  WikiTree:\n"
            "    wikitree.com/wiki/Name-123 (ID aus URL ablesen)\n"
            "    → Werkzeuge → 🌐 WikiTree → ID eingeben → importieren"
        ),
        "text_en": (
            "Besides Ancestry, you can integrate other DNA platforms:\n\n"
            "  MyHeritage:\n"
            "    myheritage.com → DNA → Matches → Download → CSV\n"
            "    → Tools → 💙 MyHeritage → import match CSV\n\n"
            "  GEDmatch:\n"
            "    gedmatch.com → One-to-Many → Download → TSV\n"
            "    → Tools → 🔗 GEDmatch → import TSV\n\n"
            "  FTDNA:\n"
            "    ftdna.com → Family Finder → Matches → Download → CSV\n"
            "    → Tools → 🔬 FTDNA → import CSV\n\n"
            "  WikiTree:\n"
            "    wikitree.com/wiki/Name-123 (read ID from URL)\n"
            "    → Tools → 🌐 WikiTree → enter ID → import"
        ),
    },
    {
        "title_de": "11 · Häufige Fragen & Tipps",
        "title_en": "11 · FAQ & tips",
        "text_de": (
            "Häufige Fragen:\n\n"
            "❓ Ancestry-Session abgelaufen (HTTP 401/403)?\n"
            "   → Cookies neu exportieren und im Login-Tab laden.\n\n"
            "❓ GEDCOM-Abgleich liefert keine Treffer?\n"
            "   → Wurzelperson im Start-Tab überprüfen.\n\n"
            "❓ Cluster leer?\n"
            "   → Erst Shared Matches (Schritt B) herunterladen.\n\n"
            "❓ FTM 2024: .ftm-Datei nicht lesbar?\n"
            "   → In FTM: Datei → Exportieren → GEDCOM → .ged-Datei laden.\n\n"
            "❓ Matricula-Scan bricht ab?\n"
            "   → ANTHROPIC_API_KEY setzen oder --dry-run verwenden.\n\n"
            "Vollständige Anleitung: »📖 Anleitung öffnen« im Werkzeuge-Tab."
        ),
        "text_en": (
            "Frequently asked questions:\n\n"
            "❓ Ancestry session expired (HTTP 401/403)?\n"
            "   → Re-export cookies and load them in the Login tab.\n\n"
            "❓ GEDCOM matching finds no hits?\n"
            "   → Check root person in the Start tab.\n\n"
            "❓ Cluster empty?\n"
            "   → Download shared matches first (step B).\n\n"
            "❓ FTM 2024: .ftm file not readable?\n"
            "   → In FTM: File → Export → GEDCOM → load .ged file.\n\n"
            "❓ Matricula scan aborts?\n"
            "   → Set ANTHROPIC_API_KEY or use --dry-run.\n\n"
            "Full guide: »📖 Open guide« in the Tools tab."
        ),
    },
    {
        "title_de": "12 · Das war's – viel Erfolg!",
        "title_en": "12 · That's it – good luck!",
        "text_de": (
            "Du hast das Tutorial abgeschlossen!\n\n"
            "Empfohlener Ablauf noch einmal im Überblick:\n\n"
            "  ① Start-Tab:      GEDCOM + Wurzelperson wählen\n"
            "  ② Login-Tab:      Ancestry-Cookie laden\n"
            "  ③ Herunterladen: Matches + Ahnentafeln laden\n"
            "  ④ Matches-Tab:   GEDCOM abgleichen\n"
            "  ⑤ Cluster-Tab:   Cluster bilden + Seite zuweisen\n"
            "  ⑥ Werkzeuge-Tab: weitere Quellen ergänzen\n\n"
            "Für weitere Hilfe:\n"
            "  • »📖 Anleitung öffnen« im Werkzeuge-Tab (WIKI.md)\n"
            "  • Dieses Tutorial jederzeit über »❓ Tutorial« neu starten\n\n"
            "Viel Erfolg bei der Ahnenforschung! 🌳"
        ),
        "text_en": (
            "You have completed the tutorial!\n\n"
            "Recommended workflow at a glance:\n\n"
            "  ① Start tab:    choose GEDCOM + root person\n"
            "  ② Login tab:    load Ancestry cookie\n"
            "  ③ Download:     load matches + pedigrees\n"
            "  ④ Matches tab:  GEDCOM matching\n"
            "  ⑤ Cluster tab:  build clusters + assign side\n"
            "  ⑥ Tools tab:    add more data sources\n\n"
            "For more help:\n"
            "  • »📖 Open guide« in the Tools tab (WIKI.md)\n"
            "  • Restart this tutorial any time via »❓ Tutorial«\n\n"
            "Good luck with your genealogy research! 🌳"
        ),
    },
]


class TutorialGuide:
    """Schritt-für-Schritt-Tutorial als nicht-modales Toplevel-Fenster.

    Verwendung:
        guide = TutorialGuide(root_widget, state)
        guide.start()
    """

    def __init__(self, parent: tk.Widget, state):
        self._parent = parent
        self._state  = state
        self._win:   tk.Toplevel | None = None
        self._step = 0

    # ── Public API ────────────────────────────────────────────────────────────

    def start(self, step: int = 0):
        self._step = step
        if self._win and self._win.winfo_exists():
            self._win.lift()
            self._show_step()
            return
        self._build_window()
        self._show_step()

    # ── Window ────────────────────────────────────────────────────────────────

    def _build_window(self):
        self._win = tk.Toplevel(self._parent)
        lang = self._lang()
        self._win.title("Tutorial" if lang == "en" else "Tutorial – Schritt für Schritt")
        self._win.resizable(True, True)
        self._win.minsize(440, 380)

        c  = self._state.colors()
        bg = c.get("bg", "#F0F4F8")
        self._win.configure(bg=bg)

        # Header
        hdr = tk.Frame(self._win, bg="#1F4E79")
        hdr.pack(fill="x")
        self._lbl_title = tk.Label(
            hdr, text="",
            bg="#1F4E79", fg="#ffffff",
            font=("Segoe UI", 11, "bold"),
            wraplength=390, justify="left",
            padx=14, pady=10,
        )
        self._lbl_title.pack(side="left", fill="x", expand=True)
        tk.Button(
            hdr, text="✕",
            bg="#1F4E79", fg="#ffffff",
            activebackground="#2E6FA3", activeforeground="#ffffff",
            relief="flat", bd=0,
            font=("Segoe UI", 11, "bold"),
            cursor="hand2",
            command=self._close,
        ).pack(side="right", padx=8, pady=6)

        # Progress
        pg = tk.Frame(self._win, bg=bg)
        pg.pack(fill="x", padx=12, pady=(8, 2))
        self._progress = ttk.Progressbar(pg, mode="determinate", maximum=len(STEPS))
        self._progress.pack(fill="x")
        self._lbl_prog = tk.Label(
            pg, text="",
            bg=bg, fg=c.get("text_dim", "#888888"),
            font=("Segoe UI", 8),
        )
        self._lbl_prog.pack(anchor="e")

        # Text
        txt_f = tk.Frame(self._win, bg=bg)
        txt_f.pack(fill="both", expand=True, padx=12, pady=4)
        self._text = tk.Text(
            txt_f,
            wrap="word",
            font=("Segoe UI", 10),
            bg=bg, fg=c.get("text", "#1A1A2E"),
            relief="flat", bd=0,
            state="disabled",
            height=14,
            padx=6, pady=4,
        )
        vsb = ttk.Scrollbar(txt_f, orient="vertical", command=self._text.yview)
        self._text.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        self._text.pack(fill="both", expand=True)

        # Navigation
        nav = tk.Frame(self._win, bg=bg)
        nav.pack(fill="x", padx=12, pady=(4, 10))
        self._btn_prev = ttk.Button(nav, text="◀ Zurück", command=self._prev)
        self._btn_prev.pack(side="left")
        ttk.Button(nav, text="⟳ Neustart", command=lambda: self.start(0)).pack(
            side="right", padx=(0, 8),
        )
        self._btn_next = ttk.Button(nav, text="Weiter ▶", command=self._next)
        self._btn_next.pack(side="right")

        self._reposition()
        self._win.protocol("WM_DELETE_WINDOW", self._close)

    # ── Step rendering ────────────────────────────────────────────────────────

    def _show_step(self):
        if self._win is None:
            return
        lang = self._lang()
        s = STEPS[self._step]
        title = s.get(f"title_{lang}", s.get("title_de", ""))
        text  = s.get(f"text_{lang}",  s.get("text_de",  ""))

        self._lbl_title.configure(text=title)
        self._progress.configure(value=self._step + 1)
        self._lbl_prog.configure(text=f"Schritt {self._step + 1} / {len(STEPS)}")

        self._text.configure(state="normal")
        self._text.delete("1.0", "end")
        self._text.insert("1.0", text)
        self._text.configure(state="disabled")

        self._btn_prev.configure(state="normal" if self._step > 0 else "disabled")
        last = self._step == len(STEPS) - 1
        self._btn_next.configure(
            text="Fertig ✓" if last else "Weiter ▶",
            command=self._close if last else self._next,
        )

    def _next(self):
        if self._step < len(STEPS) - 1:
            self._step += 1
            self._show_step()

    def _prev(self):
        if self._step > 0:
            self._step -= 1
            self._show_step()

    def _close(self):
        if self._win and self._win.winfo_exists():
            self._win.destroy()
        self._win = None

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _lang(self) -> str:
        try:
            return self._state.lang()
        except Exception:
            return "de"

    def _reposition(self):
        if self._win is None:
            return
        try:
            root = self._parent.winfo_toplevel()
            x = root.winfo_x() + root.winfo_width() + 10
            y = root.winfo_y() + 60
            self._win.geometry(f"460x560+{x}+{y}")
        except Exception:
            self._win.geometry("460x560+100+100")
