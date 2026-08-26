from __future__ import annotations

import html
import itertools
import json
import re
from collections import Counter
from pathlib import Path
from urllib.parse import quote, unquote, urlparse

import generate_wawa_center_pages as generator


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


def visible_text(source: str) -> str:
    source = re.sub(
        r"<(?:script|style|header|footer|nav)\b.*?</(?:script|style|header|footer|nav)>",
        " ",
        source,
        flags=re.I | re.S,
    )
    return clean(source)


def normalized_copy(value: str, profile: dict) -> str:
    facts = [
        profile["title"],
        profile["slug"],
        profile.get("address", ""),
        profile.get("location_note", ""),
        profile["region"],
        profile["city"],
        *profile["localities"],
        *profile["schools"],
        *profile["subjects"].keys(),
        *profile["subjects"].values(),
    ]
    for fact in sorted({item for item in facts if item}, key=len, reverse=True):
        value = value.replace(fact, " VAR ")
    return re.sub(r"\s+", " ", value).strip()


def shingles(value: str, size: int = 4) -> set[tuple[str, ...]]:
    words = re.findall(r"[가-힣A-Za-z0-9]+", value.lower())
    return {
        tuple(words[index : index + size])
        for index in range(max(0, len(words) - size + 1))
    }


def main() -> None:
    pages = sorted(path for path in TARGET.glob("*/index.html"))
    profiles = {profile["slug"]: profile for profile in generator.build_profiles()}
    errors: list[str] = []
    warnings: list[str] = []
    metas: list[str] = []
    titles: list[str] = []
    faq_signatures: list[str] = []
    representative_urls: list[str] = []
    review_notes: list[str] = []
    all_urls: set[str] = set()
    visible_lengths: list[int] = []
    normalized_shingles: list[set[tuple[str, ...]]] = []
    normalized_paragraphs: Counter[str] = Counter()

    for page in pages:
        source = page.read_text(encoding="utf-8")
        slug = page.parent.name
        profile = profiles.get(slug)
        label = str(page.relative_to(ROOT))
        if profile is None:
            errors.append(f"{label}: 원자료 프로필 없음")
            continue
        if source.count('<section class="center-profile-context">') != 1:
            errors.append(f"{label}: 센터별 상담 자료 섹션 수 오류")
        main_match = re.search(r"<main\b.*?</main>", source, re.I | re.S)
        main = main_match.group(0) if main_match else ""
        text = visible_text(main)
        visible_lengths.append(len(text))
        normalized_shingles.append(shingles(normalized_copy(text, profile)))
        for attrs, body in re.findall(r"<p\b([^>]*)>(.*?)</p>", main, re.I | re.S):
            if any(
                marker in attrs
                for marker in ("subject-kicker", "subject-review-label", "eyebrow")
            ):
                continue
            paragraph = normalized_copy(clean(body), profile)
            if len(paragraph) >= 30:
                normalized_paragraphs[paragraph] += 1
        source_facts = [
            profile.get("address", ""),
            *profile["localities"],
            *profile["subjects"].keys(),
            *profile["subjects"].values(),
            *profile["schools"][:14],
        ]
        missing_facts = [fact for fact in source_facts if fact and fact not in text]
        if missing_facts:
            errors.append(f"{label}: 화면 원자료 누락 {missing_facts[:4]}")
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

    similarities = [
        len(left & right) / len(left | right)
        for left, right in itertools.combinations(normalized_shingles, 2)
        if left or right
    ]
    sorted_similarities = sorted(similarities)
    similarity_average = sum(similarities) / len(similarities)
    similarity_p90 = sorted_similarities[int(len(sorted_similarities) * 0.9)]
    similarity_max = max(similarities)
    paragraph_max_df = max(normalized_paragraphs.values())
    if sum(visible_lengths) / len(visible_lengths) < 2900:
        errors.append("센터 본문 평균 글자수 2900자 미만")
    if similarity_average > 0.25 or similarity_p90 > 0.30 or similarity_max > 0.45:
        errors.append(
            "정규화 본문 유사도 초과 "
            f"avg={similarity_average:.4f} p90={similarity_p90:.4f} max={similarity_max:.4f}"
        )
    if paragraph_max_df > 30:
        errors.append(f"정규화 문단 최대 반복 {paragraph_max_df}/30")

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
        "visible_chars": {
            "min": min(visible_lengths),
            "max": max(visible_lengths),
            "average": round(sum(visible_lengths) / len(visible_lengths), 1),
        },
        "normalized_similarity": {
            "average": round(similarity_average, 4),
            "p90": round(similarity_p90, 4),
            "max": round(similarity_max, 4),
        },
        "normalized_paragraphs": {
            "instances": sum(normalized_paragraphs.values()),
            "unique": len(normalized_paragraphs),
            "max_document_frequency": paragraph_max_df,
            "families_used_20_plus": sum(
                count >= 20 for count in normalized_paragraphs.values()
            ),
        },
        "meta_length": {"min": min(map(len, metas)), "max": max(map(len, metas)), "average": round(sum(map(len, metas)) / len(metas), 1)},
        "error_samples": errors[:20],
        "warning_samples": warnings[:20],
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
