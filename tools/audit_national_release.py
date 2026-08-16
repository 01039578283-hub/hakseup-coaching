from __future__ import annotations

import html
import json
import re
from collections import Counter
from pathlib import Path
from urllib.parse import unquote, urlsplit
from xml.etree import ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
NATIONAL_ROOT = ROOT / "전국학원"
DETAIL_DEPTHS = {3, 4}
REQUIRED_DETAIL_TYPES = {
    "EducationalOrganization",
    "LocalBusiness",
    "WebPage",
    "Article",
    "Service",
    "FAQPage",
    "BreadcrumbList",
    "ItemList",
}
FORBIDDEN_LABELS = (
    "LOCAL ACADEMY GUIDE",
    "local academy guide",
    "COACHING CHECK",
    "PARENT FAQ",
    "PARENT REVIEW",
    "LEARNING COACHING DIFFERENCE",
    "SEARCH INTENT ANSWER",
    "SEO · AEO · GEO SUMMARY",
    "ANSWER READY",
    "CONSULTING CHECKLIST",
    "정보 준비중",
)


def node_types(node: dict) -> set[str]:
    value = node.get("@type", [])
    if isinstance(value, str):
        return {value}
    return {item for item in value if isinstance(item, str)}


def graph_nodes(data: object) -> list[dict]:
    if isinstance(data, dict) and isinstance(data.get("@graph"), list):
        return [node for node in data["@graph"] if isinstance(node, dict)]
    if isinstance(data, dict):
        return [data]
    if isinstance(data, list):
        return [node for node in data if isinstance(node, dict)]
    return []


def visible_breadcrumb(source: str) -> list[str]:
    match = re.search(r'<div class="breadcrumb">(.*?)</div>', source, re.S)
    if not match:
        return []
    plain = re.sub(r"<[^>]+>", "", match.group(1))
    return [part.strip() for part in html.unescape(plain).split("›") if part.strip()]


def schema_breadcrumb(nodes: list[dict]) -> list[str]:
    node = next((item for item in nodes if "BreadcrumbList" in node_types(item)), {})
    entries = node.get("itemListElement", [])
    return [
        str(item.get("name", "")).strip()
        for item in entries
        if isinstance(item, dict) and str(item.get("name", "")).strip()
    ]


def visible_faq(source: str) -> list[tuple[str, str]]:
    pairs = re.findall(
        r'<span class="parent-faq-q">Q</span>([^<]*)</summary>\s*<p\b[^>]*>(.*?)</p>',
        source,
        re.S,
    )
    return [
        (
            html.unescape(re.sub(r"<[^>]+>", "", question)).strip(),
            html.unescape(re.sub(r"<[^>]+>", "", answer)).strip(),
        )
        for question, answer in pairs
    ]


def schema_faq(nodes: list[dict]) -> list[tuple[str, str]]:
    node = next((item for item in nodes if "FAQPage" in node_types(item)), {})
    result: list[tuple[str, str]] = []
    for question in node.get("mainEntity", []):
        if not isinstance(question, dict):
            continue
        answer = question.get("acceptedAnswer", {})
        result.append(
            (
                str(question.get("name", "")).strip(),
                str(answer.get("text", "")).strip() if isinstance(answer, dict) else "",
            )
        )
    return result


def resolve_internal_link(page: Path, href: str) -> Path | None:
    split = urlsplit(html.unescape(href))
    if split.scheme or split.netloc or href.startswith(("mailto:", "tel:", "#", "javascript:")):
        return None
    raw_path = unquote(split.path)
    if not raw_path:
        return None
    if raw_path.startswith("/"):
        candidate = ROOT / raw_path.lstrip("/")
    else:
        candidate = page.parent / raw_path
    candidate = candidate.resolve()
    if not str(candidate).lower().startswith(str(ROOT.resolve()).lower()):
        return candidate
    if raw_path.endswith("/") or candidate.is_dir():
        candidate = candidate / "index.html"
    return candidate


def main() -> int:
    pages = sorted(NATIONAL_ROOT.rglob("index.html"))
    details = [
        path
        for path in pages
        if len(path.parent.relative_to(NATIONAL_ROOT).parts) in DETAIL_DEPTHS
    ]
    hubs = [path for path in pages if path not in set(details)]
    errors: list[tuple[str, str]] = []
    descriptions: list[str] = []
    detail_h1: list[str] = []
    broken_links: Counter[str] = Counter()

    for path in pages:
        relative = path.relative_to(ROOT).as_posix()
        source = path.read_text(encoding="utf-8")
        title = re.findall(r"<title>(.*?)</title>", source, re.S | re.I)
        h1 = re.findall(r"<h1\b[^>]*>(.*?)</h1>", source, re.S | re.I)
        canonical = re.findall(r'<link\b[^>]*rel=["\']canonical["\'][^>]*href=["\']([^"\']+)', source, re.I)
        og_url = re.findall(r'<meta\b[^>]*property=["\']og:url["\'][^>]*content=["\']([^"\']+)', source, re.I)
        description = re.findall(
            r'<meta\b[^>]*name=["\']description["\'][^>]*content=["\']([^"\']*)',
            source,
            re.I,
        )
        if len(title) != 1:
            errors.append((relative, f"title count={len(title)}"))
        if len(h1) != 1:
            errors.append((relative, f"H1 count={len(h1)}"))
        if len(canonical) != 1 or len(og_url) != 1 or (canonical and og_url and canonical[0] != og_url[0]):
            errors.append((relative, "canonical/og:url mismatch"))
        if len(description) != 1 or not description[0].strip():
            errors.append((relative, "meta description missing"))

        json_blocks = re.findall(
            r'<script\b[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
            source,
            re.S | re.I,
        )
        nodes: list[dict] = []
        try:
            for block in json_blocks:
                nodes.extend(graph_nodes(json.loads(block)))
        except json.JSONDecodeError as exc:
            errors.append((relative, f"JSON-LD parse: {exc}"))
            continue

        if visible_breadcrumb(source) != schema_breadcrumb(nodes):
            errors.append((relative, "visible/schema breadcrumb mismatch"))

        if path in details:
            present_types: set[str] = set()
            for node in nodes:
                present_types.update(node_types(node))
            missing = REQUIRED_DETAIL_TYPES - present_types
            if missing:
                errors.append((relative, f"missing JSON-LD: {sorted(missing)}"))
            if visible_faq(source) != schema_faq(nodes):
                errors.append((relative, "visible/schema FAQ mismatch"))
            if any("review" in node or "aggregateRating" in node for node in nodes):
                errors.append((relative, "unsupported review/rating schema"))
            if 'aria-label="5점 후기"' in source or 'aria-label="4점 후기"' in source:
                errors.append((relative, "visible star rating remains"))
            if '<picture class="bulk-responsive-picture">' not in source:
                errors.append((relative, "responsive body picture missing"))
            body_image = re.search(
                r'<picture class="bulk-responsive-picture">.*?<img\b([^>]*)>',
                source,
                re.S,
            )
            if not body_image or not all(name in body_image.group(1) for name in ("width=", "height=", "decoding=")):
                errors.append((relative, "body image dimensions/decoding missing"))
            # og:image may also point at the same map asset. Inspect the
            # rendered <img>, not the first arbitrary assets/maps reference.
            map_image = re.search(
                r'<img\b[^>]*src=["\'][^"\']*assets/maps/[^"\']+["\'][^>]*>',
                source,
                re.I,
            )
            if not map_image or not all(name in map_image.group(0) for name in ("width=", "height=", "decoding=")):
                errors.append((relative, "map image dimensions/decoding missing"))
            descriptions.extend(description)
            if h1:
                detail_h1.append(html.unescape(re.sub(r"<[^>]+>", "", h1[0])).strip())
        else:
            if not re.search(r'<meta\b[^>]*property=["\']og:image["\']', source, re.I):
                errors.append((relative, "hub og:image missing"))

        for label in FORBIDDEN_LABELS:
            if label in source:
                errors.append((relative, f"forbidden label: {label}"))

        for href in re.findall(r'<a\b[^>]*href=["\']([^"\']+)', source, re.I):
            candidate = resolve_internal_link(path, href)
            if candidate is not None and not candidate.exists():
                broken_links[str(candidate)] += 1

    if len(pages) != 1574:
        errors.append(("collection", f"national pages={len(pages)}, expected=1574"))
    if len(details) != 1484:
        errors.append(("collection", f"detail pages={len(details)}, expected=1484"))
    if len(set(descriptions)) != len(descriptions):
        errors.append(("collection", f"duplicate detail descriptions={len(descriptions)-len(set(descriptions))}"))
    duplicate_h1 = sum(count - 1 for count in Counter(detail_h1).values() if count > 1)
    if duplicate_h1:
        errors.append(("collection", f"duplicate detail H1={duplicate_h1}"))
    for missing, count in broken_links.items():
        errors.append(("links", f"{count}x missing {missing}"))

    tree = ET.parse(ROOT / "sitemap.xml")
    ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    urls = [node.text or "" for node in tree.findall(".//sm:loc", ns)]
    lastmods = [node.text or "" for node in tree.findall(".//sm:lastmod", ns)]
    if len(urls) != len(set(urls)):
        errors.append(("sitemap", f"duplicate URLs={len(urls)-len(set(urls))}"))
    public_indexes = []
    for path in ROOT.rglob("index.html"):
        relative = path.relative_to(ROOT)
        if any(part in {".git", ".vercel", "__pycache__", "tmp"} for part in relative.parts):
            continue
        source = path.read_text(encoding="utf-8", errors="ignore")
        if re.search(
            r'<meta\s+name=["\']robots["\']\s+content=["\'][^"\']*noindex',
            source,
            re.I,
        ):
            continue
        public_indexes.append(path)
    if len(urls) != len(public_indexes):
        errors.append(("sitemap", f"URL count={len(urls)} differs from index.html count"))
    if not lastmods or any(not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value) for value in lastmods):
        errors.append(("sitemap", "invalid lastmod"))

    print(f"national_pages={len(pages)}")
    print(f"hub_pages={len(hubs)}")
    print(f"detail_pages={len(details)}")
    print(f"unique_detail_descriptions={len(set(descriptions))}")
    print(f"unique_detail_h1={len(set(detail_h1))}")
    print(f"broken_internal_links={sum(broken_links.values())}")
    print(f"sitemap_urls={len(urls)}")
    print(f"sitemap_lastmod_dates={len(set(lastmods))}")
    print(f"errors={len(errors)}")
    for location, issue in errors[:50]:
        print(f"ERROR {location}: {issue}")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
