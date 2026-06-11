"""Zentrales Farb-Schema für die Ancestry-GUI.

Importiert von app.py und den Tab-Mixins, um zirkuläre Abhängigkeiten zu vermeiden.
COLORS und _COLORS_DARK bleiben immer separate Objekte — _active_colors() wählt
zur Laufzeit das richtige Dict, sodass Theme-Wechsel korrekt funktioniert.
"""

COLORS: dict = {
    "primary" : "#1F4E79",
    "accent"  : "#2E75B6",
    "light"   : "#D6E4F0",
    "bg"      : "#F0F4F8",
    "text"    : "#1A1A2E",
    "success" : "#217A3C",
    "warning" : "#C85000",
    "white"   : "#FFFFFF",
    "cluster" : ["#FFD6D6","#D6F5E3","#D6E4FF","#FFF3CD","#F0D6FF","#D6F0FF"],
}

_COLORS_DARK: dict = {
    "primary" : "#7c7cf8",
    "accent"  : "#a5a5ff",
    "light"   : "#2a2a3e",
    "bg"      : "#1e1e2e",
    "text"    : "#cdd6f4",
    "success" : "#50fa7b",
    "warning" : "#ffb86c",
    "white"   : "#ffffff",
    "cluster" : ["#3a2020","#1a3a2a","#1e1e3a","#2e2a10","#2a1a3a","#0a2230"],
}

def _is_dark_theme() -> bool:
    try:
        import config as _cfg
        return getattr(_cfg, "THEME", "light") == "dark"
    except Exception:
        return False
