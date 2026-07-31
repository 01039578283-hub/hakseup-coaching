from __future__ import annotations

import argparse
import re
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
NATIONAL_ROOT = ROOT / "전국학원"

IMG_RE = re.compile(r"<img\b[^>]*>", re.I | re.S)
SRC_RE = re.compile(r'\bsrc=(["\'])(.*?)\1', re.I | re.S)


def is_detail_page(path: Path) -> bool:
    return len(path.parent.relative_to(NATIONAL_ROOT).parts) in {3, 4}


def ensure_attribute(tag: str, name: str, value: str) -> str:
    if re.search(rf"\b{re.escape(name)}\s*=", tag, re.I):
        return tag
    return tag[:-1].rstrip() + f' {name}="{value}">'


def resolve_asset(page: Path, src: str) -> Path | None:
    if src.startswith(("http://", "https://", "//", "data:")):
        return None
    candidate = (page.parent / src).resolve()
    try:
        candidate.relative_to(ROOT.resolve())
    except ValueError:
        return None
    return candidate if candidate.is_file() else None


def dimensions(path: Path) -> tuple[int, int]:
    with Image.open(path) as image:
        return image.size


def transform(source: str, page: Path) -> tuple[str, int, int]:
    responsive_count = 0
    dimension_count = 0
    region = page.parent.relative_to(NATIONAL_ROOT).parts[0]
    expected_body = "seoul" if region == "서울" else "local"
    # 페이지 경로의 광역지역을 기준으로 서울/지방 안내 이미지를 일관되게 맞춘다.
    source = re.sub(
        r"(assets/centers/common/)(?:local|seoul)(-mobile)?\.webp",
        lambda match: f"{match.group(1)}{expected_body}{match.group(2) or ''}.webp",
        source,
        flags=re.I,
    )

    def replace(match: re.Match[str]) -> str:
        nonlocal responsive_count, dimension_count
        tag = match.group(0)
        src_match = SRC_RE.search(tag)
        if not src_match:
            return tag
        src = src_match.group(2)

        is_body = bool(
            re.search(
                r"assets/centers/common/(?:local|seoul)\.webp(?:[?#].*)?$",
                src,
                re.I,
            )
        )
        is_map = "assets/maps/" in src.replace("\\", "/")
        if not (is_body or is_map):
            return tag

        asset = resolve_asset(page, src.split("?", 1)[0].split("#", 1)[0])
        revised = tag
        if asset:
            width, height = dimensions(asset)
            before = revised
            revised = ensure_attribute(revised, "width", str(width))
            revised = ensure_attribute(revised, "height", str(height))
            revised = ensure_attribute(revised, "decoding", "async")
            if revised != before:
                dimension_count += 1

        if not is_body:
            return revised

        # 이미 picture 안에 있는 태그는 두 번째 실행에서 다시 감싸지 않는다.
        prefix = source[max(0, match.start() - 160) : match.start()]
        if re.search(r'<picture\b[^>]*class=["\'][^"\']*bulk-responsive-picture', prefix, re.I):
            return revised

        mobile_src = re.sub(r"\.webp(?=([?#].*)?$)", "-mobile.webp", src, flags=re.I)
        responsive_count += 1
        return (
            '<picture class="bulk-responsive-picture">'
            f'<source media="(max-width: 720px)" srcset="{mobile_src}">'
            f"{revised}"
            "</picture>"
        )

    return IMG_RE.sub(replace, source), responsive_count, dimension_count


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()

    pages = [
        path
        for path in sorted(NATIONAL_ROOT.rglob("index.html"))
        if is_detail_page(path)
    ]
    changed = 0
    responsive = 0
    dimensions_added = 0
    for page in pages:
        source = page.read_text(encoding="utf-8")
        updated, page_responsive, page_dimensions = transform(source, page)
        responsive += page_responsive
        dimensions_added += page_dimensions
        if updated != source:
            changed += 1
            if args.write:
                page.write_text(updated, encoding="utf-8", newline="\n")

    print("mode=" + ("WRITE" if args.write else "DRY-RUN"))
    print(f"pages={len(pages)}")
    print(f"changed_pages={changed}")
    print(f"responsive_body_images={responsive}")
    print(f"images_with_dimensions_added={dimensions_added}")


if __name__ == "__main__":
    main()
