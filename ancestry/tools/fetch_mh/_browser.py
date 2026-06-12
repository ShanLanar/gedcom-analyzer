"""Browser authentication helpers for the MyHeritage shared-matches scraper."""
from __future__ import annotations

import os


def _load_cookie_editor_json(path: str) -> list[dict]:
    """Liest Cookie-Editor-JSON und gibt Playwright-kompatible Cookie-Dicts zurück.

    Dupliziert Session-Cookies für .com UND .de, da MH je nach Browser-Sprache
    auf verschiedenen TLDs landet, aber die gleichen Session-Tokens nutzt.
    """
    import json
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)

    def _make(c: dict, domain_override: str | None = None) -> dict:
        domain = (domain_override or c.get("domain", "")).lstrip(".")
        if "myheritage" in domain and not domain.startswith("."):
            domain = "." + domain
        ss = str(c.get("sameSite", "Lax")).capitalize()
        cookie: dict = {
            "name":     c.get("name", ""),
            "value":    c.get("value", ""),
            "domain":   domain,
            "path":     c.get("path", "/"),
            "sameSite": ss if ss in ("Strict", "Lax", "None") else "Lax",
        }
        if "secure" in c:
            cookie["secure"] = bool(c["secure"])
        if "httpOnly" in c:
            cookie["httpOnly"] = bool(c["httpOnly"])
        if "expirationDate" in c:
            cookie["expires"] = int(c["expirationDate"])
        return cookie

    result = []
    for c in raw:
        orig = _make(c)
        result.append(orig)
        # Für MH-Cookies: auch für die jeweils andere TLD eintragen
        # (.com ↔ .de) damit DNA-Seiten egal welche TLD den Login akzeptieren
        d = orig["domain"]  # z.B. ".myheritage.com" oder ".myheritage.de"
        if "myheritage.com" in d:
            alt = d.replace("myheritage.com", "myheritage.de")
            result.append(_make(c, alt))
        elif "myheritage.de" in d:
            alt = d.replace("myheritage.de", "myheritage.com")
            result.append(_make(c, alt))
    return result


def _resolve_extension_dir(id_or_path: str) -> str | None:
    """Findet den entpackten Erweiterungs-Ordner.

    Akzeptiert entweder einen direkten Pfad (mit manifest.json) ODER eine
    Chrome-Extension-ID (z.B. 'knnjkkdihbjonnkmajijmnfblpbopapk') — dann wird
    in den Standard-Chrome/Edge-Profilen nach der neuesten Version gesucht.
    """
    if not id_or_path:
        return None
    p = os.path.abspath(os.path.expanduser(id_or_path))
    if os.path.isdir(p) and os.path.isfile(os.path.join(p, "manifest.json")):
        return p

    ext_id = id_or_path.strip()
    # Kandidaten-Basisverzeichnisse (Windows/macOS/Linux, Chrome + Edge)
    home = os.path.expanduser("~")
    bases = []
    local = os.environ.get("LOCALAPPDATA", os.path.join(home, "AppData", "Local"))
    for vendor in (
        os.path.join(local, "Google", "Chrome", "User Data"),
        os.path.join(local, "Microsoft", "Edge", "User Data"),
        os.path.join(local, "Google", "Chrome Beta", "User Data"),
        os.path.join(home, ".config", "google-chrome"),
        os.path.join(home, ".config", "chromium"),
        os.path.join(home, ".config", "microsoft-edge"),
        os.path.join(home, "Library", "Application Support", "Google", "Chrome"),
        os.path.join(home, "Library", "Application Support", "Microsoft Edge"),
    ):
        bases.append(vendor)

    candidates = []
    for base in bases:
        if not os.path.isdir(base):
            continue
        # alle Profile (Default, Profile 1, …) durchsuchen
        try:
            for prof in os.listdir(base):
                ext_dir = os.path.join(base, prof, "Extensions", ext_id)
                if os.path.isdir(ext_dir):
                    for ver in os.listdir(ext_dir):
                        vp = os.path.join(ext_dir, ver)
                        if os.path.isfile(os.path.join(vp, "manifest.json")):
                            candidates.append(vp)
        except Exception:
            continue
    if not candidates:
        return None
    # neueste Version (lexikografisch/mtime) wählen
    candidates.sort(key=lambda x: os.path.getmtime(x))
    return candidates[-1]
