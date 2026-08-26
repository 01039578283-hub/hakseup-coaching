from __future__ import annotations

"""Reduce the site-wide '연구소' signal without changing URL identity.

The public brand used in metadata is aligned with academy-search intent, while
compact labels are used in the visible header/footer and brand wording is
removed from image alternative text.  The default mode is a validated dry run.
"""

import argparse
import html
import json
import re
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OLD_BRAND = "학습코칭 연구소"
META_BRAND = "학습코칭 학원 안내"
HEADER_BRAND = "학습코칭"
FOOTER_BRAND = "학습코칭.kr"
HOME_TITLE = "영어·수학 학습코칭 학원 안내 | 학습코칭.kr"
MODIFIED_DATE = "2026-08-27"
EXCLUDED_PARTS = {".git", ".vercel", "__pycache__", "tmp"}

IMG_RE = re.compile(r"<img\b[^>]*>", re.I | re.S)
META_RE = re.compile(r"<meta\b[^>]*>", re.I | re.S)
ATTR_RE = re.compile(r'(\b(?:alt|content)\s*=\s*)(["\'])(.*?)\2', re.I | re.S)
TITLE_RE = re.compile(r"(<title>).*?(</title>)", re.I | re.S)
DATE_MODIFIED_RE = re.compile(r'("dateModified"\s*:\s*")[0-9]{4}-[0-9]{2}-[0-9]{2}(")')


@dataclass(frozen=True)
class Plan:
    path: Path
    before: str
    after: str


def _clean_brand_from_value(value: str) -> str:
    value = value.replace(OLD_BRAND, " ").replace(META_BRAND, " ")
    return re.sub(r"\s+", " ", value).strip(" ·|-")


def _clean_img_tag(match: re.Match[str]) -> str:
    tag = match.group(0)

    def replace_attr(attr: re.Match[str]) -> str:
        if not attr.group(1).lower().strip().startswith("alt"):
            return attr.group(0)
        cleaned = _clean_brand_from_value(html.unescape(attr.group(3)))
        return attr.group(1) + attr.group(2) + html.escape(cleaned, quote=True) + attr.group(2)

    return ATTR_RE.sub(replace_attr, tag)


def _clean_og_image_alt(match: re.Match[str]) -> str:
    tag = match.group(0)
    if not re.search(r'property\s*=\s*["\']og:image:alt["\']', tag, re.I):
        return tag

    def replace_attr(attr: re.Match[str]) -> str:
        if not attr.group(1).lower().strip().startswith("content"):
            return attr.group(0)
        cleaned = _clean_brand_from_value(html.unescape(attr.group(3)))
        return attr.group(1) + attr.group(2) + html.escape(cleaned, quote=True) + attr.group(2)

    return ATTR_RE.sub(replace_attr, tag)


def _replace_meta(source: str, key: str, value: str) -> str:
    escaped = html.escape(value, quote=True)
    pattern = re.compile(
        rf'(<meta\b(?=[^>]*(?:property|name)=["\']{re.escape(key)}["\'])'
        rf'[^>]*\bcontent=["\'])(.*?)(["\'][^>]*>)',
        re.I | re.S,
    )
    return pattern.sub(lambda match: match.group(1) + escaped + match.group(3), source, count=1)


def transform(path: Path, source: str) -> str:
    source = IMG_RE.sub(_clean_img_tag, source)
    source = META_RE.sub(_clean_og_image_alt, source)
    source = source.replace(f"<span>{OLD_BRAND}</span>", f"<span>{HEADER_BRAND}</span>")
    source = source.replace(f"<strong>{OLD_BRAND}</strong>", f"<strong>{FOOTER_BRAND}</strong>")
    source = source.replace(f"{OLD_BRAND}는", f"{FOOTER_BRAND}은")
    source = source.replace(f"편집: {OLD_BRAND}", f"편집: {FOOTER_BRAND}")
    source = source.replace(OLD_BRAND, META_BRAND)
    source = DATE_MODIFIED_RE.sub(rf"\g<1>{MODIFIED_DATE}\g<2>", source)

    if path == ROOT / "index.html":
        source = TITLE_RE.sub(rf"\g<1>{HOME_TITLE}\g<2>", source, count=1)
        source = _replace_meta(source, "og:title", HOME_TITLE)
        source = _replace_meta(source, "twitter:title", HOME_TITLE)
    return source


def public_pages() -> list[Path]:
    return [
        path
        for path in sorted(ROOT.rglob("index.html"))
        if not any(part in EXCLUDED_PARTS for part in path.relative_to(ROOT).parts)
    ]


def validate(plans: list[Plan]) -> list[str]:
    errors: list[str] = []
    titles: dict[str, Path] = {}
    for plan in plans:
        relative = plan.path.relative_to(ROOT).as_posix()
        if OLD_BRAND in plan.after:
            errors.append(f"{relative}: 이전 연구소 브랜드 잔존")
        if plan.after.count("<h1") != plan.before.count("<h1"):
            errors.append(f"{relative}: H1 수 변경")
        for tag in IMG_RE.findall(plan.after):
            if META_BRAND in html.unescape(tag) or OLD_BRAND in html.unescape(tag):
                errors.append(f"{relative}: 이미지 alt 브랜드 반복 잔존")
                break
        match = TITLE_RE.search(plan.after)
        if not match:
            errors.append(f"{relative}: title 없음")
            continue
        title = html.unescape(re.sub(r"<[^>]+>", "", match.group(0))).strip()
        if title in titles:
            errors.append(
                f"{relative}: title 중복({titles[title].relative_to(ROOT).as_posix()})"
            )
        titles[title] = plan.path
        if not 10 <= len(title) <= 60:
            errors.append(f"{relative}: title 길이 {len(title)}")
    if len(plans) != 4744:
        errors.append(f"collection: source pages {len(plans)}/4744")
    return errors


def atomic_write(path: Path, value: str) -> None:
    temporary = path.with_name(path.name + ".brand.tmp")
    temporary.write_text(value, encoding="utf-8", newline="\n")
    temporary.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    plans = [
        Plan(path, source, transform(path, source))
        for path in public_pages()
        for source in [path.read_text(encoding="utf-8", errors="strict")]
    ]
    errors = validate(plans)
    changed = sum(plan.before != plan.after for plan in plans)
    old_before = sum(plan.before.count(OLD_BRAND) for plan in plans)
    old_after = sum(plan.after.count(OLD_BRAND) for plan in plans)
    print(
        json.dumps(
            {
                "mode": "APPLY" if args.apply else "DRY-RUN",
                "pages": len(plans),
                "changed": changed,
                "old_brand_before": old_before,
                "old_brand_after": old_after,
                "errors": len(errors),
                "samples": errors[:20],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    if errors:
        return 1
    if args.apply:
        for plan in plans:
            if plan.before != plan.after:
                atomic_write(plan.path, plan.after)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
