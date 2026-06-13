"""bundle_matricula_pdf.py – Kirchenbuch-Bilder pro Kirchspiel zu PDFs bündeln.

Durchläuft <archive_dir>/<parish>/<book>/ und sammelt alle Bilder pro
Kirchspiel. Erzeugt ggf. mehrere PDFs (je bis zu 500 Seiten):
    <archive_dir>/<parish>/<parish>_1.pdf
    <archive_dir>/<parish>/<parish>_2.pdf
    etc.

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
_MAX_PAGES_PER_PDF = 500


def _sorted_images(book_dir: Path) -> list[Path]:
    imgs = [p for p in book_dir.iterdir() if p.suffix.lower() in _IMG_EXT]
    imgs.sort(key=lambda p: p.stem)
    return imgs


def _save_pdf(pages: list, pdf_path: Path, total: int) -> None:
    """Speichert pages als PDF."""
    if not pages:
        return
    try:
        from PIL import Image
    except ImportError:
        print("⚠ Pillow nicht installiert – bitte: pip install pillow", flush=True)
        sys.exit(1)

    first, rest = pages[0], pages[1:]
    first.save(pdf_path, format="PDF", save_all=True, append_images=rest,
               resolution=150)
    size_kb = pdf_path.stat().st_size // 1024
    print(f"    {pdf_path.name}: {total} Seiten, {size_kb} KB", flush=True)


def bundle_parish(parish_dir: Path) -> None:
    """Sammelt alle Bilder aus allen Buchordnern und bündelt sie in PDFs."""
    try:
        from PIL import Image
    except ImportError:
        print("⚠ Pillow nicht installiert – bitte: pip install pillow", flush=True)
        sys.exit(1)

    book_dirs = sorted(d for d in parish_dir.iterdir() if d.is_dir())
    if not book_dirs:
        print("  (keine Buchordner)", flush=True)
        return

    all_images: list[tuple[str, Image.Image]] = []

    print("  Bilder sammeln…", end=" ", flush=True)
    for book_dir in book_dirs:
        imgs = _sorted_images(book_dir)
        for p in imgs:
            try:
                img = Image.open(p)
                if img.mode not in ("RGB", "L"):
                    img = img.convert("RGB")
                all_images.append((p.name, img))
            except Exception as exc:
                print(f"\n    ⚠ {p.name}: {exc}", flush=True)

    total_images = len(all_images)
    print(f"{total_images} Bilder", flush=True)

    if not all_images:
        print("  (keine Bilder gefunden)", flush=True)
        return

    parish_slug = parish_dir.name
    pdf_num = 1
    current_batch: list[Image.Image] = []
    batch_names = []

    for name, img in all_images:
        current_batch.append(img)
        batch_names.append(name)

        if len(current_batch) >= _MAX_PAGES_PER_PDF:
            pdf_path = parish_dir / f"{parish_slug}_{pdf_num}.pdf"
            _save_pdf(current_batch, pdf_path, len(current_batch))
            pdf_num += 1
            current_batch = []
            batch_names = []

    if current_batch:
        pdf_path = parish_dir / f"{parish_slug}_{pdf_num}.pdf"
        _save_pdf(current_batch, pdf_path, len(current_batch))


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
