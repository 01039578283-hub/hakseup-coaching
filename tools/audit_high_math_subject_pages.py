from __future__ import annotations

import argparse
import html
import json
import re
import sys
from collections import Counter
from pathlib import Path
from urllib.parse import quote, unquote, urlsplit
from xml.etree import ElementTree as ET

import generate_high_math_subject_pages as generator


ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "과목별학원" / generator.CATEGORY
BASE_URL = generator.base.BASE_URL
DETAIL_COUNT = 371
REQUIRED_TYPES = {
    "EducationalOrganization", "LocalBusiness", "WebPage", "ImageObject",
    "Article", "Service", "FAQPage", "BreadcrumbList", "ItemList",
}
FORBIDDEN = re.compile(
    r"LOCAL ACADEMY GUIDE|핵심 키워드|보조 키워드|세부 키워드|검색 의도|"
    r"(?<![가-힣])원고(?![가-힣])|이 페이지는|이 안내는|수업 진행방식|ANSWER READY|"
    r"공통자료|공통 센터자료|학교명을 임의로|"
    r"실제 후기|Review|AggregateRating|따라가며도|영수국|정보 준비중|OO학생|"
    r"풀이을|재풀이은|재풀이과|고이 있습니다|합니다입니다|"
    r"적용와|적용를|기록를|기준를|기준는|과정를|계획를|"
    r"학생 학생|상담 상담|확인 확인|성적이 향상|점수가 올랐|합격을 보장",
    re.I,
)


def one(pattern: str, source: str, flags: int = re.I | re.S) -> str:
    matches = re.findall(pattern, source, flags)
    if len(matches) != 1:
        raise ValueError(f"single match expected: {pattern[:45]} count={len(matches)}")
    value = matches[0]
    if isinstance(value, tuple):
        value = value[0]
    return html.unescape(re.sub(r"<[^>]+>", " ", value)).strip()


def visible_text(source: str) -> str:
    match = re.search(r"<main\b[^>]*>(.*?)</main>", source, re.I | re.S)
    if not match:
        return ""
    main = match.group(1)
    main = re.sub(r"<(?:script|style|nav)\b.*?</(?:script|style|nav)>", " ", main, flags=re.I | re.S)
    main = re.sub(r"</(?:p|h[1-6]|li|dt|dd|summary|section|article|div)\s*>", "\n", main, flags=re.I)
    main = re.sub(r"<[^>]+>", " ", main)
    lines = [re.sub(r"[ \t\r\f\v]+", " ", html.unescape(line)).strip() for line in main.split("\n")]
    return "\n".join(line for line in lines if line)


def json_graph(source: str) -> list[dict]:
    raw = one(r'<script\b[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', source)
    data = json.loads(html.unescape(raw))
    return data.get("@graph", [])


def schema_types(graph: list[dict]) -> set[str]:
    result: set[str] = set()
    for node in graph:
        value = node.get("@type", [])
        result.update(value if isinstance(value, list) else [value])
    return result


def node_of(graph: list[dict], schema_type: str) -> dict:
    for node in graph:
        value = node.get("@type", [])
        if schema_type in (value if isinstance(value, list) else [value]):
            return node
    return {}


def visible_faqs(source: str) -> list[tuple[str, str]]:
    result: list[tuple[str, str]] = []
    for block in re.findall(r'<details\b[^>]*class="[^"]*subject-faq-item[^"]*"[^>]*>(.*?)</details>', source, re.I | re.S):
        q = one(r"<summary\b[^>]*>(.*?)</summary>", block)
        q = re.sub(r"^Q\s*", "", q).strip()
        a = one(r'<div\b[^>]*class="[^"]*subject-faq-answer[^"]*"[^>]*>(.*?)</div>', block)
        a = re.sub(r"^A\s*", "", a).strip()
        result.append((q, a))
    return result


def url_to_path(url: str) -> Path | None:
    parsed = urlsplit(url)
    if parsed.netloc and parsed.netloc not in {"xn--ru4bi8s1tac0p.kr", "학습코칭.kr"}:
        return None
    route = unquote(parsed.path)
    if not route.startswith("/"):
        return None
    path = ROOT / route.strip("/")
    return (path / "index.html") if route.endswith("/") else path


def shingles(text: str, size: int = 5) -> set[tuple[str, ...]]:
    tokens = re.findall(r"[가-힣A-Za-z0-9]+", text.lower())
    return {tuple(tokens[i:i + size]) for i in range(max(0, len(tokens) - size + 1))}


def similarity(a: set[tuple[str, ...]], b: set[tuple[str, ...]]) -> float:
    return len(a & b) / max(1, len(a | b))


def main() -> int:
    parser = argparse.ArgumentParser(description="고등 수학학원 371개 지역 페이지 엄격 감사")
    parser.add_argument("--workbook", type=Path, default=generator.DEFAULT_WORKBOOK)
    args = parser.parse_args()
    records = generator.make_records(args.workbook)
    errors: list[str] = []
    detail_paths = sorted(path for path in TARGET.glob("*/index.html") if path.parent != TARGET)
    if not (TARGET / "index.html").is_file():
        errors.append("hub missing")
    if len(detail_paths) != DETAIL_COUNT:
        errors.append(f"detail count={len(detail_paths)} expected={DETAIL_COUNT}")

    titles: list[str] = []
    metas: list[str] = []
    canonicals: list[str] = []
    h1s: list[str] = []
    representatives: list[str] = []
    maps: list[str] = []
    texts: list[tuple[generator.base.Record, str]] = []
    faq_questions: list[str] = []
    faq_answers: list[str] = []
    record_by_slug = {record.slug: record for record in records}

    for path in detail_paths:
        slug = path.parent.name
        record = record_by_slug.get(slug)
        if not record:
            errors.append(f"unexpected slug: {slug}")
            continue
        source = path.read_text(encoding="utf-8")
        expected_h1 = generator.title(record)
        expected_title = f"{expected_h1} | {generator.base.SITE_NAME}"
        expected_url = generator.page_url(record)
        try:
            title = one(r"<title>(.*?)</title>", source)
            meta = one(r'<meta\s+name="description"\s+content="([^"]+)"', source)
            canonical = one(r'<link\s+rel="canonical"\s+href="([^"]+)"', source)
            og_url = one(r'<meta\s+property="og:url"\s+content="([^"]+)"', source)
            og_title = one(r'<meta\s+property="og:title"\s+content="([^"]+)"', source)
            h1 = one(r"<h1\b[^>]*>(.*?)</h1>", source)
            main_text = visible_text(source)
            graph = json_graph(source)
        except Exception as exc:
            errors.append(f"{slug}: parse {exc}")
            continue
        for label, actual, expected in (
            ("title", title, expected_title), ("h1", h1, expected_h1),
            ("canonical", canonical, expected_url), ("og:url", og_url, expected_url),
            ("og:title", og_title, expected_title),
        ):
            if actual != expected:
                errors.append(f"{slug}: {label} mismatch {actual!r}")
        if not 65 <= len(meta) <= 105:
            errors.append(f"{slug}: meta length={len(meta)}")
        if source.count("<h1") != 1 or source.count("<main") != 1:
            errors.append(f"{slug}: H1/main count")
        breadcrumb = re.search(r'<nav\b[^>]*class="[^"]*subject-breadcrumb[^"]*"[^>]*>(.*?)</nav>', source, re.I | re.S)
        crumbs = re.findall(r"<(?:a|strong)\b[^>]*>(.*?)</(?:a|strong)>", breadcrumb.group(1), re.I | re.S) if breadcrumb else []
        crumbs = [html.unescape(re.sub(r"<[^>]+>", "", value)).strip() for value in crumbs]
        if crumbs != ["홈", "과목별학원", generator.CATEGORY_LABEL, expected_h1]:
            errors.append(f"{slug}: breadcrumb={crumbs}")

        types = schema_types(graph)
        if not REQUIRED_TYPES.issubset(types):
            errors.append(f"{slug}: schema missing={sorted(REQUIRED_TYPES-types)}")
        if {"Review", "AggregateRating"} & types:
            errors.append(f"{slug}: unsupported review/rating schema")
        webpage = node_of(graph, "WebPage")
        article = node_of(graph, "Article")
        service = node_of(graph, "Service")
        org = node_of(graph, "EducationalOrganization")
        breadcrumb_node = node_of(graph, "BreadcrumbList")
        if not all(key in webpage for key in ("about", "mentions", "hasPart", "primaryImageOfPage")):
            errors.append(f"{slug}: WebPage enrichment missing")
        if not all(key in article for key in ("about", "mentions", "hasPart", "articleSection")):
            errors.append(f"{slug}: Article enrichment missing")
        if "makesOffer" not in service or "makesOffer" not in org:
            errors.append(f"{slug}: makesOffer missing")
        schema_crumbs = [item.get("name") for item in breadcrumb_node.get("itemListElement", [])]
        if schema_crumbs != crumbs:
            errors.append(f"{slug}: visible/schema breadcrumb mismatch")

        faqs = visible_faqs(source)
        schema_faq = node_of(graph, "FAQPage").get("mainEntity", [])
        schema_pairs = [(item.get("name", ""), item.get("acceptedAnswer", {}).get("text", "")) for item in schema_faq]
        if len(faqs) != 5 or faqs != schema_pairs:
            errors.append(f"{slug}: FAQ visible/schema mismatch count={len(faqs)}")
        faq_questions.extend(q for q, _ in faqs)
        faq_answers.extend(a for _, a in faqs)

        rep = re.findall(r'<img\b[^>]*data-role="representative-image"[^>]*src="([^"]+)"', source, re.I)
        map_image = re.findall(r'<img\b[^>]*src="(\.\./\.\./\.\./assets/maps/[^"]+)"', source, re.I)
        if len(rep) != 1 or len(map_image) != 1:
            errors.append(f"{slug}: representative/map image count")
        else:
            representatives.append(rep[0])
            maps.append(map_image[0])
            if not (path.parent / map_image[0]).resolve().is_file():
                errors.append(f"{slug}: map asset missing")
        if len(re.findall(r"<img\b", source, re.I)) != 3:
            errors.append(f"{slug}: img count")

        grade_stage = generator.CATEGORY_LABEL.split()[0]
        grade_match = re.search(rf"<dt>수학 가능 {re.escape(grade_stage)} 학년</dt><dd>(.*?)</dd>", source, re.I | re.S)
        displayed_grade = html.unescape(re.sub(r"<[^>]+>", "", grade_match.group(1))).strip() if grade_match else ""
        expected_grades = "·".join(generator.high_grades(record)) if generator.high_grades(record) else "상담 확인 필요"
        if displayed_grade != expected_grades:
            errors.append(f"{slug}: grade fact mismatch {displayed_grade!r}")
        match = FORBIDDEN.search(main_text)
        if match:
            errors.append(f"{slug}: forbidden phrase={match.group(0)!r}")
        h2s = [re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", item))).strip() for item in re.findall(r"<h2\b[^>]*>(.*?)</h2>", source, re.I | re.S)]
        if len(h2s) < 10 or len(h2s) != len(set(h2s)):
            errors.append(f"{slug}: H2 count/duplicate={len(h2s)}/{len(set(h2s))}")
        for href in re.findall(r'<a\b[^>]*href="([^"]+)"', source, re.I):
            target = url_to_path(href)
            if target is not None and not target.exists():
                errors.append(f"{slug}: broken internal link {href}")
        titles.append(title); metas.append(meta); canonicals.append(canonical); h1s.append(h1)
        texts.append((record, main_text))

    for name, values, expected in (
        ("title", titles, DETAIL_COUNT), ("meta", metas, DETAIL_COUNT),
        ("canonical", canonicals, DETAIL_COUNT), ("H1", h1s, DETAIL_COUNT),
        ("representative", representatives, DETAIL_COUNT), ("map", maps, DETAIL_COUNT),
        ("FAQ questions", faq_questions, DETAIL_COUNT * 5), ("FAQ answers", faq_answers, DETAIL_COUNT * 5),
    ):
        if len(values) != expected or len(set(values)) != expected:
            errors.append(f"collection: {name} total/unique={len(values)}/{len(set(values))} expected={expected}")

    hub = TARGET / "index.html"
    if hub.is_file():
        source = hub.read_text(encoding="utf-8")
        links = re.findall(rf'href="/과목별학원/{generator.CATEGORY}/([^/]+)/"', source)
        if len(links) != DETAIL_COUNT or len(set(links)) != DETAIL_COUNT:
            errors.append(f"hub: detail links={len(links)}/{len(set(links))}")
        try:
            graph = json_graph(source)
            item_list = node_of(graph, "ItemList")
            if item_list.get("numberOfItems") != DETAIL_COUNT or len(item_list.get("itemListElement", [])) != DETAIL_COUNT:
                errors.append("hub: ItemList count")
        except Exception as exc:
            errors.append(f"hub: schema parse {exc}")

    masked_sets: list[set[tuple[str, ...]]] = []
    for record, text in texts:
        masked = text
        for value in [record.locality, record.center_name, record.address, *record.schools, *generator.HIGH_GRADES]:
            if value:
                masked = masked.replace(value, " 사실값 ")
        masked_sets.append(shingles(masked))
    max_score = 0.0
    max_pair = ("", "")
    for i in range(len(masked_sets)):
        for j in range(i + 1, len(masked_sets)):
            score = similarity(masked_sets[i], masked_sets[j])
            if score > max_score:
                max_score = score
                max_pair = (texts[i][0].slug, texts[j][0].slug)
    if max_score >= 0.75:
        errors.append(f"collection: masked similarity={max_score:.6f} pair={max_pair}")

    sitemap = ROOT / "sitemap.xml"
    sitemap_urls: set[str] = set()
    if sitemap.is_file():
        root = ET.parse(sitemap).getroot()
        sitemap_urls = {node.text or "" for node in root.findall("{http://www.sitemaps.org/schemas/sitemap/0.9}url/{http://www.sitemaps.org/schemas/sitemap/0.9}loc")}
        expected_urls = {generator.page_url(record) for record in records} | {generator.base.absolute_url("과목별학원", generator.CATEGORY)}
        missing = expected_urls - sitemap_urls
        if missing:
            errors.append(f"sitemap: missing={len(missing)}")
    else:
        errors.append("sitemap missing")

    report = {
        "audit": "high math subject pages release audit",
        "hub": int(hub.is_file()), "details": len(detail_paths),
        "unique_titles": len(set(titles)), "unique_meta": len(set(metas)),
        "unique_canonicals": len(set(canonicals)), "unique_faq_questions": len(set(faq_questions)),
        "unique_faq_answers": len(set(faq_answers)), "masked_5_shingle_max": round(max_score, 6),
        "masked_pair": max_pair, "sitemap_urls": len(sitemap_urls),
        "errors": len(errors), "error_samples": errors[:30],
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
