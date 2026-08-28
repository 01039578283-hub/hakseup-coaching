#!/usr/bin/env python3
"""Add page-specific anchor navigation to subject academy detail pages.

The script targets only ``과목별학원/<category>/<detail>/index.html``. It
builds links from the headings already visible on each page, preserves hubs,
and is safe to rerun after a page generator updates the manuscripts.
"""

from __future__ import annotations

import argparse
import html
import re
import sys
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SUBJECT_ROOT = ROOT / "과목별학원"
TOC_START = "<!-- subject-page-anchor-toc:start -->"
TOC_END = "<!-- subject-page-anchor-toc:end -->"

TOC_BLOCK_RE = re.compile(
    rf"{re.escape(TOC_START)}.*?{re.escape(TOC_END)}",
    re.IGNORECASE | re.DOTALL,
)
TOC_REMOVE_RE = re.compile(
    rf"\n[ \t]*{re.escape(TOC_START)}.*?{re.escape(TOC_END)}",
    re.IGNORECASE | re.DOTALL,
)
TARGET_ANCHOR_RE = re.compile(
    r'<span class="subject-page-anchor" id="(?P<id>section-\d+(?:-\d+)?)" '
    r'aria-hidden="true"></span>',
    re.IGNORECASE,
)
LEGACY_SECTION_ID_RE = re.compile(
    r'(<section)\s+id=(["\'])section-\d+(?:-\d+)?\2(?=\s|>)',
    re.IGNORECASE,
)
SECTION_OPEN_RE = re.compile(r"<section(?P<attrs>[^>]*)>", re.IGNORECASE)
SECTION_TAG_RE = re.compile(r"</?section\b[^>]*>", re.IGNORECASE)
H2_RE = re.compile(r"<h2\b[^>]*>(?P<body>.*?)</h2>", re.IGNORECASE | re.DOTALL)
CLASS_RE = re.compile(
    r"\bclass\s*=\s*([\"'])(?P<class_names>[^\"']+)\1", re.IGNORECASE
)
ANY_ID_RE = re.compile(r"\bid\s*=\s*([\"'])(?P<id>[^\"']+)\1", re.IGNORECASE)

CENTER_TARGET_CLASSES = {
    "center-profile-overview",
    "center-profile-context",
    "center-profile-grade",
    "center-profile-flow",
    "center-profile-school",
    "subject-review-section",
    "subject-faq-section",
    "subject-related-section",
    "consult-strip",
}


@dataclass(frozen=True)
class TocTarget:
    closing_end: int
    heading_end: int
    text: str


def visible_text(fragment: str) -> str:
    text = re.sub(r"<[^>]+>", " ", fragment)
    return " ".join(html.unescape(text).split())


def class_names(attrs: str) -> set[str]:
    match = CLASS_RE.search(attrs)
    return set(match.group("class_names").split()) if match else set()


def detail_pages() -> list[Path]:
    if not SUBJECT_ROOT.exists():
        return []
    return sorted(
        SUBJECT_ROOT.glob("*/*/index.html"), key=lambda path: path.as_posix()
    )


def section_end(source: str, opening: re.Match[str] | None) -> int | None:
    if not opening:
        return None
    depth = 0
    for match in SECTION_TAG_RE.finditer(source, opening.start()):
        if match.group(0).lower().startswith("</section"):
            depth -= 1
            if depth == 0:
                return match.end()
        else:
            depth += 1
    return None


def classed_section_end(source: str, class_name: str) -> int | None:
    opening = re.search(
        rf"<section\b[^>]*class\s*=\s*([\"'])[^\"']*\b{re.escape(class_name)}\b[^\"']*\1[^>]*>",
        source,
        re.IGNORECASE,
    )
    return section_end(source, opening)


def select_targets(source: str, is_center: bool) -> list[TocTarget]:
    selected: list[TocTarget] = []
    for opening in SECTION_OPEN_RE.finditer(source):
        attrs = opening.group("attrs")
        classes = class_names(attrs)
        if is_center:
            if not classes.intersection(CENTER_TARGET_CLASSES):
                continue
        elif "subject-copy-section" not in classes:
            continue

        closing_end = section_end(source, opening)
        if closing_end is None:
            continue
        heading = H2_RE.search(source, opening.end(), closing_end)
        if not heading:
            continue
        text = visible_text(heading.group("body"))
        if not text:
            continue
        selected.append(
            TocTarget(
                closing_end=closing_end,
                heading_end=heading.end(),
                text=text,
            )
        )
    return selected


def add_target_anchors(
    source: str, targets: list[TocTarget]
) -> tuple[str, list[tuple[str, str]]]:
    used_ids = {match.group("id") for match in ANY_ID_RE.finditer(source)}
    replacements: list[tuple[int, int, str]] = []
    links: list[tuple[str, str]] = []

    for number, target in enumerate(targets, start=1):
        base_id = f"section-{number:02d}"
        target_id = base_id
        suffix = 2
        while target_id in used_ids:
            target_id = f"{base_id}-{suffix}"
            suffix += 1
        used_ids.add(target_id)
        replacements.append(
            (
                target.heading_end,
                target.heading_end,
                f'<span class="subject-page-anchor" id="{target_id}" '
                'aria-hidden="true"></span>',
            )
        )
        links.append((target_id, target.text))

    for start, end, replacement in reversed(replacements):
        source = source[:start] + replacement + source[end:]
    return source, links


def toc_markup(links: list[tuple[str, str]], is_center: bool) -> str:
    title = "이 센터 페이지에서 확인할 내용" if is_center else "이 페이지에서 확인할 내용"
    items = []
    for index, (target_id, text) in enumerate(links, start=1):
        items.append(
            "        <li>"
            f'<a href="#{html.escape(target_id, quote=True)}">'
            f'<span class="subject-page-toc-number" aria-hidden="true">{index:02d}</span>'
            f'<span>{html.escape(text)}</span>'
            "</a></li>"
        )
    return (
        "\n"
        + TOC_START
        + "\n"
        + '<nav class="subject-page-toc" aria-labelledby="subject-page-toc-title">\n'
        + '  <div class="subject-page-toc-shell">\n'
        + '    <div class="subject-page-toc-heading">\n'
        + '      <p>PAGE CONTENTS</p>\n'
        + f'      <strong id="subject-page-toc-title">{title}</strong>\n'
        + "    </div>\n"
        + '    <ol class="subject-page-toc-list">\n'
        + "\n".join(items)
        + "\n    </ol>\n"
        + "  </div>\n"
        + "</nav>\n"
        + TOC_END
    )


def render_page(original: str) -> tuple[str, int, str]:
    source = TOC_REMOVE_RE.sub("", original, count=1)
    source = TARGET_ANCHOR_RE.sub("", source)
    source = LEGACY_SECTION_ID_RE.sub(r"\1", source)
    is_center = "center-profile-page" in source
    targets = select_targets(source, is_center)
    minimum = 3 if is_center else 2
    if len(targets) < minimum:
        raise ValueError(f"Only {len(targets)} usable content headings found")

    source, links = add_target_anchors(source, targets)
    insertion_point = classed_section_end(source, "subject-quick-answer")
    if insertion_point is None:
        insertion_point = classed_section_end(source, "subject-local-hero")
    if insertion_point is None:
        raise ValueError("TOC insertion section end not found")

    source = source[:insertion_point] + toc_markup(links, is_center) + source[insertion_point:]
    return source, len(links), "center" if is_center else "subject"


def validate_page(source: str) -> list[str]:
    errors: list[str] = []
    if source.count(TOC_START) != 1 or source.count(TOC_END) != 1:
        errors.append("TOC marker count is not exactly one")

    toc_match = TOC_BLOCK_RE.search(source)
    if not toc_match:
        errors.append("TOC block missing")
        return errors

    is_center = "center-profile-page" in source
    hrefs = re.findall(r'href=["\']#([^"\']+)["\']', toc_match.group(0))
    targets = select_targets(source, is_center)
    target_ids: list[str | None] = []
    for target in targets:
        anchor = TARGET_ANCHOR_RE.match(source, target.heading_end)
        target_ids.append(anchor.group("id") if anchor else None)
    if hrefs != target_ids:
        errors.append("TOC link order does not match content sections")

    labels = [visible_text(item) for item in re.findall(
        r'<li>\s*<a\b[^>]*>.*?<span>(.*?)</span>\s*</a>\s*</li>',
        toc_match.group(0),
        re.IGNORECASE | re.DOTALL,
    )]
    target_labels = [target.text for target in targets]
    if labels != target_labels:
        errors.append("TOC labels do not match visible H2 text")

    all_ids = [match.group("id") for match in ANY_ID_RE.finditer(source)]
    if len(all_ids) != len(set(all_ids)):
        errors.append("Duplicate id found")
    for target_id in hrefs:
        if all_ids.count(target_id) != 1:
            errors.append(
                f"Anchor target count for {target_id!r} is {all_ids.count(target_id)}"
            )

    hero_end = classed_section_end(source, "subject-local-hero")
    quick_end = classed_section_end(source, "subject-quick-answer")
    media_start = source.find("subject-media-section")
    required_start = quick_end if quick_end is not None else hero_end
    if required_start is None or toc_match.start() < required_start:
        errors.append("TOC appears before the hero or quick answer")
    if media_start < 0 or toc_match.end() > media_start:
        errors.append("TOC is not before the media section")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--write", action="store_true", help="Write generated TOCs to disk"
    )
    parser.add_argument(
        "--check", action="store_true", help="Fail if any detail page is not current"
    )
    args = parser.parse_args()

    pages = detail_pages()
    changed = 0
    subject_counts: list[int] = []
    center_counts: list[int] = []
    failures: list[str] = []

    for path in pages:
        original = path.read_bytes().decode("utf-8")
        if "\r" in original:
            failures.append(f"{path.relative_to(ROOT)}: non-LF line ending found")
            continue
        try:
            rendered, link_count, page_kind = render_page(original)
        except Exception as exc:
            failures.append(f"{path.relative_to(ROOT)}: {exc}")
            continue

        validation_errors = validate_page(rendered)
        if validation_errors:
            failures.append(
                f"{path.relative_to(ROOT)}: " + "; ".join(validation_errors)
            )
            continue

        if page_kind == "center":
            center_counts.append(link_count)
        else:
            subject_counts.append(link_count)
        if rendered != original:
            changed += 1
            if args.write:
                path.write_bytes(rendered.encode("utf-8"))

    print(
        f"pages={len(pages)} subject={len(subject_counts)} center={len(center_counts)}"
    )
    if subject_counts:
        print(
            "subject_toc_links="
            f"min:{min(subject_counts)} max:{max(subject_counts)} "
            f"total:{sum(subject_counts)}"
        )
    if center_counts:
        print(
            "center_toc_links="
            f"min:{min(center_counts)} max:{max(center_counts)} "
            f"total:{sum(center_counts)}"
        )
    print(f"changed={changed} mode={'write' if args.write else 'dry-run'}")

    if failures:
        print(f"failures={len(failures)}", file=sys.stderr)
        for failure in failures[:50]:
            print(failure, file=sys.stderr)
        return 1
    if args.check and changed:
        print("Target pages are not up to date. Run with --write.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
