# -*- coding: utf-8 -*-
"""
config.py – Zentrale Konfiguration des Ahnen-Analyse-Frameworks
Alle Pfade, IDs und Konstanten hier anpassen.
Laufzeit-Overrides über config_user.json (von config_editor erzeugt, .gitignore).
"""

import os

# ── Verzeichnisse ──────────────────────────────────────────────────────────────
BASE_DIR = r"C:\ahnen"

DIRS = {
    "data":   r"C:\ahnen\data",
    "output": r"C:\ahnen\output",
    "logs":   r"C:\ahnen\logs",
}

# ── Eingabedateien ─────────────────────────────────────────────────────────────
FILES = {
    "gedfile":          r"C:\ahnen\data\family.ged",
    "location_data":    r"C:\ahnen\data\location_data.json",
    "output_xlsx":      r"C:\ahnen\output\genealogy_analysis_complete.xlsx",
    "output_json":      r"C:\ahnen\output\genealogy_results.json",
    "log_file":         r"C:\ahnen\logs\genealogy_analysis.log",
    "interactive_html": r"C:\ahnen\output\family_tree.html",
    "osnabrueck_xlsx":  r"C:\ahnen\output\osnabrueck_region_analysis.xlsx",
    "osnabrueck_html":  r"C:\ahnen\output\osnabrueck_region_report.html",
    "osnabrueck_json":  r"C:\ahnen\output\osnabrueck_region_analysis.json",
}

# ── Analyse-IDs ────────────────────────────────────────────────────────────────
ROOT_ID    = "@I251@"
EXCLUDE_ID = "@I2475@"

# ── Analyse-Optionen ───────────────────────────────────────────────────────────
CACHE_ENABLED    = True
MAX_CACHE_SIZE   = 1000
MAX_TREE_DEPTH   = 4
ENABLE_KI        = True     # scikit-learn (optional)
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
    "enable_ki_predictions": ENABLE_KI,
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
}
_GLOBAL_KEY_MAP = {
    "root_id":               "ROOT_ID",
    "exclude_id":            "EXCLUDE_ID",
    "cache_enabled":         "CACHE_ENABLED",
    "max_cache_size":        "MAX_CACHE_SIZE",
    "max_tree_depth":        "MAX_TREE_DEPTH",
    "enable_ki_predictions": "ENABLE_KI",
    "progress_display":      "PROGRESS_DISPLAY",
    "military_symbols":      "MILITARY_SYMBOLS",
}


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
    path = json_path or os.path.join(BASE_DIR, "config_user.json")
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
