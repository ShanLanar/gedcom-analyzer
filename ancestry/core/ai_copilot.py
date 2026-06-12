"""
ai_copilot.py — Claude-Copilot für genetische Genealogie.

Erklärt DNA-Cluster und empfiehlt Forschungsschritte.
Benötigt:  pip install anthropic   +   ANTHROPIC_API_KEY in der Umgebung.
Ohne beides: alle Funktionen degradieren gracefully (leerer String / False).
"""
from __future__ import annotations

import hashlib
import logging
import os
import threading
from collections import Counter
from typing import Callable

log = logging.getLogger(__name__)

_MODEL      = "claude-sonnet-4-6"
_MAX_TOKENS = 450
_CACHE: dict[str, str] = {}  # SHA-256[:20] → vollständiger Response


# ── Verfügbarkeitsprüfung ─────────────────────────────────────────────────────

def is_available() -> bool:
    """True wenn anthropic-Paket installiert UND API-Key gesetzt."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return False
    try:
        import anthropic  # noqa: F401
        return True
    except ImportError:
        return False


def availability_hint() -> str:
    """Menschenlesbare Erklärung, warum der Copilot nicht verfügbar ist."""
    try:
        import anthropic  # noqa: F401
    except ImportError:
        return ("anthropic-Paket nicht installiert.\n"
                "Bitte ausführen:  pip install anthropic")
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return ("ANTHROPIC_API_KEY nicht gesetzt.\n"
                "Umgebungsvariable setzen und Tool neu starten.")
    return ""


def _cache_key(prompt: str) -> str:
    return hashlib.sha256(prompt.encode()).hexdigest()[:20]


# ── Asynchroner Aufruf (für Tkinter-GUIs) ────────────────────────────────────

def explain_async(
    prompt: str,
    on_chunk: Callable[[str], None] | None = None,
    on_done: Callable[[str], None] | None = None,
    max_tokens: int = _MAX_TOKENS,
) -> None:
    """Startet asynchronen Claude-Aufruf im Background-Thread.

    on_chunk wird für jeden Text-Chunk gerufen (aus dem BG-Thread!).
    GUI-Code muss widget.after(0, ...) verwenden, um thread-safe zu bleiben.
    on_done wird einmal mit dem vollständigen Ergebnis gerufen.
    Gleiche Prompts werden gecached — kein zweiter API-Call.
    """
    k = _cache_key(prompt)
    if k in _CACHE:
        full = _CACHE[k]
        if on_chunk:
            on_chunk(full)
        if on_done:
            on_done(full)
        return

    def _run():
        try:
            import anthropic
            client = anthropic.Anthropic()
            buf: list[str] = []
            with client.messages.stream(
                model=_MODEL,
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}],
            ) as stream:
                for chunk in stream.text_stream:
                    buf.append(chunk)
                    if on_chunk:
                        on_chunk(chunk)
            result = "".join(buf)
            _CACHE[k] = result
            if on_done:
                on_done(result)
        except Exception as e:
            log.warning("ai_copilot explain_async: %s", e)
            err = f"\n[Fehler: {e}]"
            if on_chunk:
                on_chunk(err)
            if on_done:
                on_done(err)

    threading.Thread(target=_run, daemon=True).start()


# ── Prompt-Builder ────────────────────────────────────────────────────────────

def cluster_prompt(cluster_id: int, members: list[dict]) -> str:
    """Baut den Analyse-Prompt für einen Cluster."""
    if not members:
        return ""

    cms = [float(m.get("cm") or 0) for m in members if m.get("cm")]
    lo  = min(cms) if cms else 0
    hi  = max(cms) if cms else 0
    avg = sum(cms) / len(cms) if cms else 0

    surnames: Counter[str] = Counter()
    for m in members:
        name = (m.get("name") or "").strip()
        if name:
            surnames[name.split()[-1]] += 1
    top_sn = surnames.most_common(6)

    origins: Counter[str] = Counter()
    for m in members:
        org = m.get("probable_origin") or m.get("origin") or ""
        if org:
            origins[org.split(",")[0].strip()] += 1
    top_org = origins.most_common(3)

    lines = [
        "Du bist ein erfahrener genetischer Genealoge. "
        "Analysiere diesen DNA-Cluster und antworte auf Deutsch (max. 200 Wörter):",
        "",
        f"**Cluster #{cluster_id}** — {len(members)} Mitglieder",
        f"cM-Bereich: {lo:.0f}–{hi:.0f} cM  |  Ø {avg:.0f} cM",
    ]
    if top_sn:
        lines.append("Häufige Nachnamen: "
                     + ", ".join(f"{sn} ({n}×)" for sn, n in top_sn))
    if top_org:
        lines.append("Hauptherkunft: "
                     + ", ".join(f"{o} ({n}×)" for o, n in top_org))
    lines += [
        "",
        "Beantworte:",
        "1. Wer ist wahrscheinlich der MRCA (gemeinsamer Vorfahre)?",
        "2. Welche 2 konkreten nächsten Forschungsschritte empfiehlst du?",
    ]
    return "\n".join(lines)


def gaps_prompt(stats: dict) -> str:
    """Baut den Forschungsempfehlungs-Prompt aus Dashboard-Statistiken."""
    total = max(1, stats.get("total", 0))

    def pct(k: str) -> str:
        return f"{stats.get(k, 0) / total * 100:.0f}%"

    return "\n".join([
        "Du bist ein genetischer Genealoge. "
        "Gib 3 priorisierte Forschungsempfehlungen (max. 200 Wörter, Deutsch):",
        "",
        "Mein aktueller Forschungsstand:",
        f"- DNA-Matches gesamt: {stats.get('total', 0)}",
        f"- Geclustert: {pct('clustered')}  |  "
        f"Mit Ahnentafel: {pct('with_pedigree')}  |  "
        f"Mit Herkunft: {pct('with_origin')}",
        f"- GEDCOM-Personen im eigenen Stammbaum: {stats.get('gedcom_persons', 0)}",
        f"- Direkte Vorfahren (Sosa 1–31, Gen. 1–5): {stats.get('sosa_filled', 0)}/31",
        f"- ML-Modell trainiert: {'ja' if stats.get('ml_model_exists') else 'nein'}",
        f"- Kirchenbuch-Einträge (Matricula): {stats.get('matricula', 0)}",
        "",
        "Format: nummerierte Liste, jeder Punkt max. 2 Sätze.",
    ])
