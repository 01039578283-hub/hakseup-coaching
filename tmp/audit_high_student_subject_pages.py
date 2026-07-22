from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from urllib.parse import quote


ROOT = Path(__file__).resolve().parents[1]
CATEGORY = "고등학생학원"
BASE_URL = "https://xn--ru4bi8s1tac0p.kr"
TARGET = ROOT / "과목별학원" / CATEGORY
REQUIRED_TYPES = {
    "EducationalOrganization", "LocalBusiness", "WebPage", "Article",
    "Service", "FAQPage", "BreadcrumbList", "ItemList",
}


def schema_types(graph: list[dict]) -> set[str]:
    result: set[str] = set()
    for node in graph:
        value = node.get("@type")
        if isinstance(value, str):
            result.add(value)
        elif isinstance(value, list):
            result.update(item for item in value if isinstance(item, str))
    return result


def extract(pattern: str, page: str) -> str:
    match = re.search(pattern, page, re.S | re.I)
    return match.group(1).strip() if match else ""


def main() -> None:
    pages = sorted(path for path in TARGET.glob("*/index.html") if path.parent.name)
    errors: list[str] = []
    titles: list[str] = []
    metas: list[str] = []
    answer_texts: list[str] = []
    review_texts: list[str] = []
    visible_faq_total = 0
    schema_faq_total = 0

    if len(pages) != 371:
        errors.append(f"local page count={len(pages)}")

    for path in pages:
        page = path.read_text(encoding="utf-8")
        slug = path.parent.name
        expected_url = BASE_URL + quote(f"/과목별학원/{CATEGORY}/{slug}/", safe="/")
        title = extract(r"<title>(.*?)</title>", page)
        meta = extract(r'<meta name="description" content="([^"]*)"', page)
        canonical = extract(r'<link rel="canonical" href="([^"]+)"', page)
        og_url = extract(r'<meta property="og:url" content="([^"]+)"', page)
        h1s = re.findall(r"<h1(?:\s[^>]*)?>(.*?)</h1>", page, re.S | re.I)
        visible_faq = re.findall(r'<details class="subject-faq-item">', page)
        answer = extract(r'<div class="subject-answer-box">.*?<p>(.*?)</p>', page)
        review = extract(r'<section class="subject-review-section">.*?<blockquote>(.*?)</blockquote>', page)
        scripts = re.findall(r'<script type="application/ld\+json">(.*?)</script>', page, re.S)
        if len(scripts) != 1:
            errors.append(f"{slug}: jsonld scripts={len(scripts)}")
            continue
        try:
            data = json.loads(scripts[0])
        except json.JSONDecodeError as exc:
            errors.append(f"{slug}: invalid jsonld {exc}")
            continue
        graph = data.get("@graph", [])
        missing_types = REQUIRED_TYPES - schema_types(graph)
        faq_node = next((node for node in graph if node.get("@type") == "FAQPage"), {})
        schema_faq = faq_node.get("mainEntity", [])
        visible_faq_total += len(visible_faq)
        schema_faq_total += len(schema_faq)

        if not title or not meta:
            errors.append(f"{slug}: missing title/meta")
        if canonical != expected_url or og_url != expected_url:
            errors.append(f"{slug}: canonical/og mismatch")
        if len(h1s) != 1:
            errors.append(f"{slug}: h1={len(h1s)}")
        if len(visible_faq) != 5 or len(schema_faq) != 5:
            errors.append(f"{slug}: faq visible/schema={len(visible_faq)}/{len(schema_faq)}")
        if missing_types:
            errors.append(f"{slug}: missing schema={sorted(missing_types)}")
        if 'class="subject-hidden-representative"' not in page or 'style="display:none;"' not in page:
            errors.append(f"{slug}: hidden representative missing")
        if f'assets/centers/common/{"seoul" if "서울" in extract(r"<p class=\"subject-kicker\">(.*?)</p>", page) else "local"}.webp' not in page:
            errors.append(f"{slug}: body image mismatch")
        map_src = extract(r'<img src="([^"\']*assets/maps/[^"\']+)"', page)
        if not map_src or not (path.parent / map_src).resolve().exists():
            errors.append(f"{slug}: map image missing")
        if 'class="subject-related-grid"' not in page:
            errors.append(f"{slug}: related links missing")

        titles.append(title)
        metas.append(meta)
        answer_texts.append(re.sub(r"<[^>]+>", "", answer))
        review_texts.append(re.sub(r"<[^>]+>", "", review))

    sitemap = (ROOT / "sitemap.xml").read_text(encoding="utf-8")
    sitemap_count = sitemap.count("<url>")
    missing_sitemap = sum(
        1 for path in pages
        if BASE_URL + quote(f"/과목별학원/{CATEGORY}/{path.parent.name}/", safe="/") not in sitemap
    )
    hub_checks = {}
    for path in [ROOT / "과목별학원" / "index.html", TARGET / "index.html"]:
        page = path.read_text(encoding="utf-8")
        hub_checks[str(path.relative_to(ROOT))] = {
            "h1": len(re.findall(r"<h1(?:\s[^>]*)?>", page, re.I)),
            "indexed": 'content="index, follow"' in page,
            "jsonld_valid": all(json.loads(item) is not None for item in re.findall(r'<script type="application/ld\+json">(.*?)</script>', page, re.S)),
        }

    report = {
        "local_pages": len(pages),
        "unique_titles": len(set(titles)),
        "unique_meta_descriptions": len(set(metas)),
        "unique_answer_blocks": len(set(answer_texts)),
        "unique_review_blocks": len(set(review_texts)),
        "duplicate_title_count": sum(count - 1 for count in Counter(titles).values() if count > 1),
        "visible_faq_total": visible_faq_total,
        "schema_faq_total": schema_faq_total,
        "sitemap_urls": sitemap_count,
        "missing_sitemap_urls": missing_sitemap,
        "hub_checks": hub_checks,
        "errors": errors[:100],
        "error_count": len(errors),
    }
    print(json.dumps(report, ensure_ascii=True, indent=2))
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
