from __future__ import annotations

import html
import json
import re
from collections import Counter
from pathlib import Path
from urllib.parse import quote, unquote, urlparse


ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "과목별학원" / "와와학습코칭센터"
BASE_URL = "https://xn--ru4bi8s1tac0p.kr"
REQUIRED_TYPES = {"EducationalOrganization", "LocalBusiness", "Article", "Service", "FAQPage", "BreadcrumbList", "ItemList"}


def clean(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", value))).strip()


def types(graph: list[dict]) -> set[str]:
    result: set[str] = set()
    for node in graph:
        value = node.get("@type")
        result.update(value if isinstance(value, list) else [value] if value else [])
    return result


def local_target(href: str) -> Path | None:
    if not href.startswith("/") or href.startswith("//"):
        return None
    route = unquote(urlparse(href).path).strip("/")
    return ROOT / route / "index.html" if route else ROOT / "index.html"


def main() -> None:
    pages = sorted(path for path in TARGET.glob("*/index.html"))
    errors: list[str] = []
    warnings: list[str] = []
    metas: list[str] = []
    titles: list[str] = []
    faq_signatures: list[str] = []
    representative_urls: list[str] = []
    review_notes: list[str] = []
    all_urls: set[str] = set()

    for page in pages:
        source = page.read_text(encoding="utf-8")
        slug = page.parent.name
        label = str(page.relative_to(ROOT))
        expected = BASE_URL + quote(f"/과목별학원/와와학습코칭센터/{slug}/", safe="/")
        h1 = re.findall(r"<h1\b[^>]*>(.*?)</h1>", source, re.I | re.S)
        if len(h1) != 1:
            errors.append(f"{label}: H1 {len(h1)}개")
        titles.extend(clean(value) for value in h1)
        canonical = re.findall(r'<link\s+rel="canonical"\s+href="([^"]+)"', source, re.I)
        og_url = re.findall(r'<meta\s+property="og:url"\s+content="([^"]+)"', source, re.I)
        if canonical != [expected]:
            errors.append(f"{label}: canonical 불일치")
        if og_url != [expected]:
            errors.append(f"{label}: og:url 불일치")
        all_urls.add(expected)
        meta_match = re.search(r'<meta\s+name="description"\s+content="([^"]*)"', source, re.I)
        meta = clean(meta_match.group(1)) if meta_match else ""
        metas.append(meta)
        if not 65 <= len(meta) <= 160:
            warnings.append(f"{label}: meta 길이 {len(meta)}")

        schema_match = re.search(r'<script\s+type="application/ld\+json">(.*?)</script>', source, re.I | re.S)
        if not schema_match:
            errors.append(f"{label}: JSON-LD 없음")
            continue
        try:
            data = json.loads(schema_match.group(1))
        except json.JSONDecodeError as exc:
            errors.append(f"{label}: JSON-LD 오류 {exc}")
            continue
        graph = data.get("@graph", [])
        missing = REQUIRED_TYPES - types(graph)
        if missing:
            errors.append(f"{label}: schema 누락 {sorted(missing)}")
        article = next((node for node in graph if node.get("@type") == "Article"), {})
        webpage = next((node for node in graph if node.get("@type") == "WebPage"), {})
        service = next((node for node in graph if node.get("@type") == "Service"), {})
        org = next((node for node in graph if isinstance(node.get("@type"), list) and "EducationalOrganization" in node["@type"]), {})
        for node, fields, name in [(article, ("about", "mentions", "articleSection"), "Article"), (webpage, ("about", "mentions", "hasPart"), "WebPage"), (service, ("about", "mentions", "makesOffer"), "Service"), (org, ("makesOffer",), "Organization")]:
            absent = [field for field in fields if not node.get(field)]
            if absent:
                errors.append(f"{label}: {name} {absent} 누락")

        faq_node = next((node for node in graph if node.get("@type") == "FAQPage"), {})
        schema_faq = [(clean(item.get("name", "")), clean(item.get("acceptedAnswer", {}).get("text", ""))) for item in faq_node.get("mainEntity", [])]
        visible_faq = [(clean(q), clean(a)) for q, a in re.findall(r'<details class="subject-faq-item">\s*<summary><span>Q</span>(.*?)</summary>\s*<div class="subject-faq-answer"><span>A</span><p>(.*?)</p>', source, re.I | re.S)]
        if visible_faq != schema_faq or len(visible_faq) != 5:
            errors.append(f"{label}: 화면/JSON FAQ 불일치 ({len(visible_faq)}/{len(schema_faq)})")
        faq_signatures.append(json.dumps(schema_faq, ensure_ascii=False))

        media_match = re.search(r'<section class="subject-media-section.*?</section>', source, re.I | re.S)
        media = media_match.group(0) if media_match else ""
        representative = re.search(r'<img[^>]+class="subject-hidden-representative"[^>]+src="([^"]+)"[^>]+style="display:none;"', media, re.I)
        if not representative:
            errors.append(f"{label}: 숨김 대표이미지 위치 오류")
        else:
            representative_urls.append(representative.group(1))
        review_match = re.search(r'<section class="subject-review-section">.*?<blockquote>(.*?)</blockquote>', source, re.I | re.S)
        review_notes.append(clean(review_match.group(1)) if review_match else "")
        for src in re.findall(r'(?:src|srcset)="([^"]+)"', source, re.I):
            if src.startswith(("http://", "https://", "data:")):
                continue
            asset = (page.parent / src).resolve()
            if not asset.exists():
                errors.append(f"{label}: 이미지 없음 {src}")
        for href in re.findall(r'href="([^"]+)"', source, re.I):
            target = local_target(href)
            if target is not None and not target.exists():
                errors.append(f"{label}: 내부링크 없음 {href}")

    hub = (TARGET / "index.html").read_text(encoding="utf-8")
    hub_schema = json.loads(re.search(r'<script\s+type="application/ld\+json">(.*?)</script>', hub, re.I | re.S).group(1))
    hub_list = next(node for node in hub_schema["@graph"] if node.get("@type") == "ItemList")
    if hub_list.get("numberOfItems") != len(pages) or len(hub_list.get("itemListElement", [])) != len(pages):
        errors.append("허브 ItemList 수량 불일치")
    sitemap = (ROOT / "sitemap.xml").read_text(encoding="utf-8")
    missing_sitemap = sum(1 for url in all_urls | {BASE_URL + quote('/과목별학원/와와학습코칭센터/', safe='/')} if url not in sitemap)
    if missing_sitemap:
        errors.append(f"sitemap 누락 {missing_sitemap}개")
    if len(set(representative_urls)) != len(pages):
        errors.append(f"대표이미지 중복 {len(pages) - len(set(representative_urls))}개")

    report = {
        "hub_pages": 1,
        "detail_pages": len(pages),
        "errors": len(errors),
        "warnings": len(warnings),
        "unique_h1": len(set(titles)),
        "unique_meta": len(set(metas)),
        "unique_faq_sets": len(set(faq_signatures)),
        "unique_representative_images": len(set(representative_urls)),
        "unique_consultation_scenarios": len(set(review_notes)),
        "meta_length": {"min": min(map(len, metas)), "max": max(map(len, metas)), "average": round(sum(map(len, metas)) / len(metas), 1)},
        "error_samples": errors[:20],
        "warning_samples": warnings[:20],
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
