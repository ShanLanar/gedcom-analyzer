"""bundle_matricula_pdf.py – Kirchenbuch-Bilder pro Buch zu einer PDF zusammenfassen.

Durchläuft <archive_dir>/<parish>/<book>/ und erzeugt je eine PDF-Datei
neben dem Buchordner: <archive_dir>/<parish>/<book>.pdf

Verwendung:
    python -m ancestry.tools.bundle_matricula_pdf [--archive-dir PATH] [--parish SLUG ...]
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

DEFAULT_ARCHIVE = Path(os.environ.get(
    "MATRICULA_ARCHIVE",
    os.path.expanduser("~/matricula_images"),
))

_IMG_EXT = {".jpg", ".jpeg", ".png", ".tif", ".tiff"}


def _sorted_images(book_dir: Path) -> list[Path]:
    imgs = [p for p in book_dir.iterdir() if p.suffix.lower() in _IMG_EXT]
    imgs.sort(key=lambda p: p.stem)
    return imgs


def bundle_book(book_dir: Path, pdf_path: Path) -> int:
    """Wandelt alle Bilder in book_dir in eine PDF um. Gibt Seitenanzahl zurück."""
    try:
        from PIL import Image
    except ImportError:
        print("⚠ Pillow nicht installiert – bitte: pip install pillow", flush=True)
        sys.exit(1)

    imgs = _sorted_images(book_dir)
    if not imgs:
        return 0

    pages: list[Image.Image] = []
    for p in imgs:
        try:
            img = Image.open(p)
            if img.mode not in ("RGB", "L"):
                img = img.convert("RGB")
            pages.append(img)
        except Exception as exc:
            print(f"  ⚠ {p.name}: {exc}", flush=True)

    if not pages:
        return 0

    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    first, rest = pages[0], pages[1:]
    first.save(pdf_path, format="PDF", save_all=True, append_images=rest,
               resolution=150)
    return len(pages)


def bundle_parish(parish_dir: Path) -> None:
    book_dirs = sorted(d for d in parish_dir.iterdir() if d.is_dir())
    if not book_dirs:
        print(f"  (keine Buchordner in {parish_dir.name})", flush=True)
        return
    total_books = len(book_dirs)
    for i, book_dir in enumerate(book_dirs, 1):
        pdf_path = parish_dir / f"{book_dir.name}.pdf"
        print(f"  [{i}/{total_books}] {book_dir.name} → {pdf_path.name} …",
              end=" ", flush=True)
        n = bundle_book(book_dir, pdf_path)
        if n:
            size_kb = pdf_path.stat().st_size // 1024
            print(f"{n} Seiten, {size_kb} KB", flush=True)
        else:
            print("keine Bilder", flush=True)


def main(archive_dir: Path, parishes: list[str] | None) -> None:
    if not archive_dir.exists():
        print(f"⚠ Archivordner nicht gefunden: {archive_dir}", flush=True)
        sys.exit(1)

    parish_dirs = sorted(archive_dir.iterdir()) if archive_dir.is_dir() else []
    parish_dirs = [d for d in parish_dirs if d.is_dir()]

    if parishes:
        parish_dirs = [d for d in parish_dirs if d.name in parishes]

    if not parish_dirs:
        print("Keine Pfarrei-Ordner gefunden.", flush=True)
        return

    for parish_dir in parish_dirs:
        print(f"\n⛪ {parish_dir.name}", flush=True)
        bundle_parish(parish_dir)

    print("\n✓ Fertig.", flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Kirchenbuch-Bilder → PDF")
    ap.add_argument("--archive-dir", default=str(DEFAULT_ARCHIVE),
                    help="Archiv-Wurzelverzeichnis")
    ap.add_argument("--parish", nargs="+", metavar="SLUG",
                    help="Nur diese Pfarrei(en) bündeln")
    args = ap.parse_args()
    main(Path(args.archive_dir), args.parish)
