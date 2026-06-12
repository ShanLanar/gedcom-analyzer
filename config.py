# -*- coding: utf-8 -*-
"""
config.py – Zentrale Konfiguration des Ahnen-Analyse-Frameworks
Alle Pfade, IDs und Konstanten hier anpassen.
Laufzeit-Overrides über config_user.json (von config_editor erzeugt, .gitignore).
"""

import os

# ── Verzeichnisse ──────────────────────────────────────────────────────────────
# Pfade relativ zum Repo-Ordner (wo config.py liegt) – kein hartcodierter Pfad.
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

DIRS = {
    "data":   os.path.join(BASE_DIR, "data"),
    "output": os.path.join(BASE_DIR, "output"),
    "logs":   os.path.join(BASE_DIR, "logs"),
}

# ── Eingabedateien ─────────────────────────────────────────────────────────────
FILES = {
    "gedfile":          os.path.join(BASE_DIR, "data", "family.ged"),
    "location_data":    os.path.join(BASE_DIR, "data", "location_data.json"),
    "output_xlsx":      os.path.join(BASE_DIR, "output", "genealogy_analysis_complete.xlsx"),
    "output_json":      os.path.join(BASE_DIR, "output", "genealogy_results.json"),
    "log_file":         os.path.join(BASE_DIR, "logs", "genealogy_analysis.log"),
    "interactive_html": os.path.join(BASE_DIR, "output", "family_tree.html"),
    "timeline_html":    os.path.join(BASE_DIR, "output", "timeline.html"),
    "output_graphml":   os.path.join(BASE_DIR, "output", "family_network.graphml"),
    "osnabrueck_xlsx":  os.path.join(BASE_DIR, "output", "osnabrueck_region_analysis.xlsx"),
    "osnabrueck_html":  os.path.join(BASE_DIR, "output", "osnabrueck_region_report.html"),
    "osnabrueck_json":  os.path.join(BASE_DIR, "output", "osnabrueck_region_analysis.json"),
}

# ── Analyse-IDs ────────────────────────────────────────────────────────────────
ROOT_ID    = "@I251@"
EXCLUDE_ID = "@I2475@"

# ── Analyse-Optionen ───────────────────────────────────────────────────────────
CACHE_ENABLED    = True
MAX_CACHE_SIZE   = 1000
MAX_TREE_DEPTH   = 4
PROGRESS_DISPLAY = True

# ── Symbole ────────────────────────────────────────────────────────────────────
MILITARY_SYMBOLS = {
    "german":   "✠",
    "other":    "★",
    "fallen":   "⚔",
    "line_end": "‡",
    "migrated": "mig.",
}

# ── GUI-Farbschema (Dark Theme) ────────────────────────────────────────────────
BG        = "#1e1e2e"
BG2       = "#2a2a3e"
BG3       = "#232336"
ACCENT    = "#7c7cf8"
GREEN     = "#50fa7b"
RED       = "#ff5555"
YELLOW    = "#f1fa8c"
ORANGE    = "#ffb86c"
FG        = "#cdd6f4"
FG_DIM    = "#6c7086"

FONT_MAIN = ("Segoe UI", 10)
FONT_MONO = ("Consolas", 9)
FONT_HEAD = ("Segoe UI Semibold", 11)

# ── Kompakt-Mapping für Abwärtskompatibilität ──────────────────────────────────
DEFAULT_CONFIG = {
    "gedfile":            FILES["gedfile"],
    "root_id":            ROOT_ID,
    "exclude_id":         EXCLUDE_ID,
    "output_xlsx":        FILES["output_xlsx"],
    "output_json":        FILES["output_json"],
    "location_data_json": FILES["location_data"],
    "log_file":           FILES["log_file"],
    "cache_enabled":      CACHE_ENABLED,
    "max_cache_size":     MAX_CACHE_SIZE,
    "progress_display":   PROGRESS_DISPLAY,
    "interactive_html":   FILES["interactive_html"],
    "max_tree_depth":     MAX_TREE_DEPTH,
    "military_symbols":   MILITARY_SYMBOLS,
}


# Mapping flacher DEFAULT_CONFIG-Keys auf ihre kanonische Quelle in FILES/etc.
# Wird von apply_overrides() benutzt, damit Overrides auch bei Modulen ankommen,
# die direkt auf cfg.FILES / cfg.ROOT_ID etc. zugreifen.
_FILE_KEY_MAP = {
    "gedfile":            "gedfile",
    "output_xlsx":        "output_xlsx",
    "output_json":        "output_json",
    "location_data_json": "location_data",
    "log_file":           "log_file",
    "interactive_html":   "interactive_html",
    "timeline_html":      "timeline_html",
    "output_graphml":     "output_graphml",
}
_GLOBAL_KEY_MAP = {
    "root_id":               "ROOT_ID",
    "exclude_id":            "EXCLUDE_ID",
    "cache_enabled":         "CACHE_ENABLED",
    "max_cache_size":        "MAX_CACHE_SIZE",
    "max_tree_depth":        "MAX_TREE_DEPTH",
    "progress_display":      "PROGRESS_DISPLAY",
    "military_symbols":      "MILITARY_SYMBOLS",
}


def _overrides_path(json_path=None) -> str:
    """Pfad zur config_user.json: explizit, sonst BASE_DIR/config_user.json
    falls beschreibbar, sonst neben config.py."""
    if json_path:
        return json_path
    candidates = [
        os.path.join(BASE_DIR, "config_user.json"),
        os.path.join(os.path.dirname(os.path.abspath(__file__)),
                     "config_user.json"),
    ]
    # Bevorzuge bestehende Datei
    for p in candidates:
        if os.path.exists(p):
            return p
    # Sonst: ersten beschreibbaren Pfad
    for p in candidates:
        d = os.path.dirname(p)
        if d and os.path.isdir(d) and os.access(d, os.W_OK):
            return p
    return candidates[-1]


def save_overrides(updates: dict, json_path: str | None = None) -> bool:
    """Mischt `updates` in eine bestehende config_user.json (oder erzeugt sie)
    und schreibt das Ergebnis atomar zurück. Gibt True bei Erfolg.
    Wenn `updates` einen 'gedfile'-Key enthält, wird die Datei automatisch
    in die Recent-Files-Liste aufgenommen (max. 5 Einträge)."""
    import json as _json
    path = _overrides_path(json_path)
    existing: dict = {}
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                existing = _json.load(f)
        except (OSError, _json.JSONDecodeError):
            existing = {}
    existing.update(updates)
    # Recent-Files-Rotation: neue gedfile an Anfang, max. 5 Einträge
    if "gedfile" in updates and updates["gedfile"]:
        recent = [p for p in existing.get("recent_files", [])
                  if p != updates["gedfile"]]
        existing["recent_files"] = [updates["gedfile"]] + recent[:4]
    try:
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            _json.dump(existing, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
        return True
    except OSError as e:
        print(f"[config] Warnung: config_user.json konnte nicht "
              f"geschrieben werden: {e}")
        return False


def get_recent_files(json_path: str | None = None) -> list[str]:
    """Gibt die zuletzt geöffneten Dateien aus config_user.json zurück."""
    import json as _json
    path = _overrides_path(json_path)
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = _json.load(f)
        return [p for p in data.get("recent_files", []) if os.path.exists(p)]
    except (OSError, _json.JSONDecodeError):
        return []


def apply_overrides(json_path=None):
    """
    Liest config_user.json und überschreibt Werte in DEFAULT_CONFIG sowie
    in den kanonischen Konstanten (FILES, DIRS, ROOT_ID, …), damit Module,
    die direkt auf diese zugreifen, ebenfalls die Overrides sehen.
    Muss vor dem ersten Modulzugriff auf cfg.FILES / cfg.ROOT_ID erfolgen.

    Akzeptiert sowohl flache Keys ("gedfile", "root_id", …) als auch
    Top-Level-Dicts ("FILES", "DIRS").
    """
    import json as _json
    path = json_path or os.path.join(os.path.dirname(os.path.abspath(__file__)), "config_user.json")
    if not os.path.exists(path):
        return
    try:
        with open(path, "r", encoding="utf-8") as f:
            overrides = _json.load(f)
    except (OSError, _json.JSONDecodeError) as e:
        print(f"[config] Warnung: config_user.json konnte nicht geladen werden: {e}")
        return

    g = globals()
    for key, val in overrides.items():
        if key in _FILE_KEY_MAP:
            FILES[_FILE_KEY_MAP[key]] = val
            DEFAULT_CONFIG[key] = val
        elif key in _GLOBAL_KEY_MAP:
            g[_GLOBAL_KEY_MAP[key]] = val
            DEFAULT_CONFIG[key] = val
        elif key in ("FILES", "DIRS") and isinstance(val, dict):
            g[key].update(val)
            # Spiegelung der bekannten FILES-Keys nach DEFAULT_CONFIG
            if key == "FILES":
                for flat_k, files_k in _FILE_KEY_MAP.items():
                    if files_k in val:
                        DEFAULT_CONFIG[flat_k] = val[files_k]
        else:
            DEFAULT_CONFIG[key] = val
