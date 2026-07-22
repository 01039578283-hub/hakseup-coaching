from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageOps


ROOT = Path(__file__).resolve().parents[1]
COMMON = ROOT / "assets" / "centers" / "common"
ACADEMY = ROOT / "전국학원"
QUALITY = 92


def convert(source: Path, destination: Path) -> None:
    with Image.open(source) as opened:
        image = ImageOps.exif_transpose(opened).convert("RGB")
        image.save(destination, "WEBP", quality=QUALITY, method=6)


def replace_page_references() -> tuple[int, int]:
    changed_pages = 0
    replaced_references = 0
    replacements = {
        "assets/centers/common/local.jpg": "assets/centers/common/local.webp",
        "assets/centers/common/seoul.jpg": "assets/centers/common/seoul.webp",
    }
    for page in ACADEMY.rglob("index.html"):
        html = page.read_text(encoding="utf-8")
        updated = html
        for old, new in replacements.items():
            count = updated.count(old)
            replaced_references += count
            updated = updated.replace(old, new)
        if updated != html:
            page.write_text(updated, encoding="utf-8", newline="\n")
            changed_pages += 1
    return changed_pages, replaced_references


if __name__ == "__main__":
    for name in ("local", "seoul"):
        convert(COMMON / f"{name}.jpg", COMMON / f"{name}.webp")
    pages, references = replace_page_references()
    print(f"changed_pages={pages}")
    print(f"replaced_references={references}")
