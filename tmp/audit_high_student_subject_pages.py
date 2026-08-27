from __future__ import annotations

import json
import html
import re
import sys
from collections import Counter
from pathlib import Path
from urllib.parse import quote


ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parents[1]
SITEMAP_PATH = Path(sys.argv[2]).resolve() if len(sys.argv) > 2 else ROOT / "sitemap.xml"
SITE_ROOT = Path(sys.argv[3]).resolve() if len(sys.argv) > 3 else ROOT
CATEGORY = "고등학생학원"
BASE_URL = "https://xn--ru4bi8s1tac0p.kr"
TARGET = ROOT / "과목별학원" / CATEGORY
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(ROOT / "tools"))
import refresh_high_student_body as high_refresh

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
    differentiated_pages = 0
    special_pages = 0
    keyword_counts: list[int] = []
    flow_sentences: Counter[str] = Counter()

    if len(pages) != 371:
        errors.append(f"local page count={len(pages)}")

    for ordinal, path in enumerate(pages):
        page = path.read_text(encoding="utf-8")
        slug = path.parent.name
        try:
            context = high_refresh.extract_context(path, ordinal)
        except Exception as exc:
            errors.append(f"{slug}: context {type(exc).__name__}: {exc}")
            continue
        flow_match = high_refresh.FLOW_RE.search(page)
        flow = flow_match.group(2) if flow_match else ""
        if high_refresh.MARKER in flow:
            differentiated_pages += 1
        else:
            errors.append(f"{slug}: differentiation marker missing")
        keyword_marker = high_refresh.KEYWORD_MARKER_RE.search(flow)
        if not keyword_marker or keyword_marker.group(1) != context.keyword:
            errors.append(f"{slug}: secondary keyword marker mismatch")
        flow_h2_count = len(re.findall(r'<section\s+class="subject-copy-section"><h2>', flow))
        flow_paragraph_count = len(re.findall(r"<p\b[^>]*>.*?</p>", flow, re.S | re.I))
        if flow_h2_count != 6 or flow_paragraph_count != 12:
            errors.append(
                f"{slug}: flow h2/paragraphs={flow_h2_count}/{flow_paragraph_count}"
            )
        keyword_count = high_refresh.clean(flow).count(context.keyword)
        keyword_counts.append(keyword_count)
        if not 2 <= keyword_count <= 4:
            errors.append(f"{slug}: keyword {context.keyword} count={keyword_count}")
        sections = re.findall(
            r'<section\s+class="subject-copy-section"><h2>(.*?)</h2>(.*?)</section>',
            flow,
            re.S,
        )
        dedicated_sections = sum(
            context.keyword in high_refresh.clean(heading)
            for heading, _body in sections
        )
        outside_keyword = sum(
            high_refresh.clean(heading + body).count(context.keyword)
            for heading, body in sections
            if context.keyword not in high_refresh.clean(heading)
        )
        if dedicated_sections not in {1, 2} or outside_keyword:
            errors.append(
                f"{slug}: keyword scope dedicated/outside={dedicated_sections}/{outside_keyword}"
            )
        for bad_phrase in (
            "때은", "시기은", "직후은", "니다 따라서", "니다 그러므로",
            "니다 실제 적용", "원인의 원인", "항목 항목", "계획 계획",
            "확인하는지 확인", "대조하는지 대조", "기록하는지 기록",
            "남기는지 남겨", "남기는지 여부를 같은 형식으로 남겨",
            "기록하는지 여부를 같은 형식으로 남겨",
            "확인하는지 여부를 같은 형식으로 남겨", "기록에서 기록에서",
            "입시일정를", "해당 안내이", "실제 시간표에 반영되는지",
            "학습 피드백의 계획·실행", "학생 자료를 보며 주간 안내에서",
            "학생의 기록을 보며 주간 안내에서", "남은 원인",
            "답안을 살필 때 답안을",
            "답안을 원인별로 나눌 때 답안을",
            "답안을 원인별로 나눌 때 최근 답안을",
            "최근 답안을 살필 때 최근 답안을",
            "답안을 다섯 원인으로 분류해",
            "답을 선택한 근거을",
            "기본 유형은 안정적으로 처리하지만",
            "과제 점검 점검이 필요한 학생을 위한 선택 기준",
            "하는지 여부를 다음 점검에서 같은 기준으로 비교하세요",
            "하는지 여부를 기준으로 앞선 계획과 실제 기록을 비교하세요",
            "범위별 이해도, 오답 수, 재풀이 통과 여부를 주차별로 확인하는지 여부",
            "등록일, 시작 진도, 첫 점검일, 반 변경 기준을 한 번에 적어 두는지 여부",
            "혼자 해결한 문제와 도움 뒤 해결한 문제를 나눠 적어",
            "유형의 통학 뒤", "유형의 학교 일정과 통학 뒤",
            "유형의 등원 계획은",
            "유형의 미완료", "유형이 끝내지 못한 과제", "유형의 남은 과제",
            "유형의 원인", "유형의 학습 원인", "유형의 최근 시험 답안",
            "유형의 막힘", "유형의 현재 상태", "유형이 처음부터 풀이",
            "유형이 같은 원리", "유형의 학습 기록과 생활 일정",
            "선택 판단",
            "완료율과 같은 오류",
            "상담 후 행동 계획이 어떻게 달라졌는지 비교하는지 여부",
            "기록 후 계획이 어떻게 조정됐는지 추적하는지 여부",
            "학생이 받은 범위표를 먼저 확인하고 준비 순서를 정하는 방식",
            "운영 관점에서 확인할 때",
            "운영 관점에서 검토할 때",
        ):
            if bad_phrase in high_refresh.clean(flow):
                errors.append(f"{slug}: bad phrase {bad_phrase}")
        flow_text = high_refresh.clean(flow)
        if context.school_state == "coverage":
            if "<h3>고등학교 실제 수업 가능 학교</h3>" in page:
                errors.append(f"{slug}: coverage school heading overstates named schools")
            if "<h3>고등학교 수업 가능 범위</h3>" not in page:
                errors.append(f"{slug}: coverage school range heading missing")
            if high_refresh.corrected_school_copy(context) not in page:
                errors.append(f"{slug}: coverage source boundary missing")
            if "실제 수업 가능 학교 범위를 뜻합니다" in page:
                errors.append(f"{slug}: coverage claim conflicts with center data")
        wrong_object = context.keyword + high_refresh.particle(
            context.keyword, "를", "을"
        )
        wrong_topic = context.keyword + high_refresh.particle(
            context.keyword, "는", "은"
        )
        if wrong_object in flow_text:
            errors.append(f"{slug}: wrong object particle {wrong_object}")
        if wrong_topic in flow_text:
            errors.append(f"{slug}: wrong topic particle {wrong_topic}")
        if re.search(
            r"(?:습니다|합니다|됩니다|입니다|없습니다|있습니다) (?=[가-힣‘“])",
            flow_text,
        ):
            errors.append(f"{slug}: missing sentence boundary")
        for pattern_name, pattern in (
            (
                "duplicated student material scope",
                r"학생 자료(?:에서|를 보며) [^.?!]{0,80}에서",
            ),
            (
                "awkward temporal student record",
                r"학생의 [^.?!]{0,100}(?:때|시기|직후|기간|학기|시점|첫 주|달) (?:실행 )?기록",
            ),
            (
                "ambiguous remaining execution record",
                r"[^.?!]{2,60}에 남은 [^.?!]{2,30} 학생의 실행 흔적",
            ),
            (
                "awkward event record order",
                r"[^.?!]{2,60}에 작성한 [^.?!]{2,30} 기록은",
            ),
            (
                "duplicated error-cause predicate",
                r"유형의 오답 원인을 구분할 때 [^.?!]{0,100}오답 원인을",
            ),
            (
                "old malformed semantic heading",
                r"(?:복습 시작|과제 점검|시험 시간|난도 적응|시험 분석|과목 우선순위|집중 지속|서술형 구성|자기 설명|검토 절차|오답 원인)을 줄이는",
            ),
            (
                "meaning-reversed repeated-student heading",
                r"[가-힣· ]{2,30}(?:이|가) 반복되는 학생을 위한 선택 기준",
            ),
            (
                "duplicated parent recipient method",
                r"(?:유형에게|에 사용할|에 맞춘) 학부모에게 완료·미완료·조정 사유",
            ),
            (
                "duplicated error-classification lead",
                r"(?:답안을 원인별로 나눌 때 오답 원인을|오답 기록을 원인별로 정리할 때 오답 기록을 원인별로 정리하고)",
            ),
            (
                "duplicated question-habit point",
                r"막힌 지점을 질문으로 남기지 못한 (?:지점|부분|과정|대목|문항)",
            ),
            (
                "malformed keyword judgment heading",
                r"고등학생학원에서 [가-힣A-Za-z0-9·]+(?:을|를) 판단하는 방법",
            ),
        ):
            if re.search(pattern, flow_text):
                errors.append(f"{slug}: {pattern_name}")
        for sentence in re.split(r"(?<=[.!?])\s+", flow_text):
            sentence = sentence.strip()
            if sentence and sentence != high_refresh.school_boundary(context):
                flow_sentences[sentence] += 1
        special_paragraphs = high_refresh.special_keyword_paragraphs(context)
        special_answer = high_refresh.special_keyword_faq_answer(context)
        if bool(special_paragraphs) != bool(special_answer):
            errors.append(f"{slug}: special flow/FAQ coverage mismatch")
        if special_paragraphs:
            special_pages += 1
            if not all(paragraph in page for paragraph in special_paragraphs):
                errors.append(f"{slug}: special keyword paragraphs missing")
            if special_answer not in page:
                errors.append(f"{slug}: special keyword FAQ answer missing")
        special_heading = high_refresh.special_keyword_heading(context)
        if special_heading and special_heading not in page:
            errors.append(f"{slug}: special keyword heading missing")
        if context.keyword == "학원개인정보관리":
            supplemental = high_refresh.privacy_supplemental_heading(context)
            if supplemental not in page or page.count("학원개인정보관리") < 2:
                errors.append(f"{slug}: privacy supplemental section missing")
        intended_method = high_refresh.method_for_secondary_challenge(context)
        faq_block = high_refresh.FAQ_RE.search(page)
        faq_items = (
            list(high_refresh.FAQ_ITEM_RE.finditer(faq_block.group(0)))
            if faq_block
            else []
        )
        if flow.count(intended_method) < 2:
            errors.append(f"{slug}: intended secondary method missing in flow")
        if not faq_items or intended_method not in faq_items[0].group(0):
            errors.append(f"{slug}: intended secondary method missing in FAQ1")
        try:
            if high_refresh.school_mismatch(flow, context):
                errors.append(f"{slug}: school fact mismatch")
        except Exception as exc:
            errors.append(f"{slug}: school fact {type(exc).__name__}: {exc}")
        school_exam_matches = re.findall(
            rf"{re.escape(context.locality)}(?:의| 학생의) [^<.!?]{{2,120}}? 시험 준비에서는 "
            r"범위 확인일과 1차 학습 완료일을 구분합니다\.",
            flow,
        )
        if school_exam_matches and school_exam_matches != [
            high_refresh.school_exam_reference(context)
        ]:
            errors.append(f"{slug}: unverified school exam reference")
        wrong_heading, correct_heading = high_refresh.corrected_heading_phrase(context)
        if wrong_heading != correct_heading and wrong_heading in page:
            errors.append(f"{slug}: wrong heading particle remains")
        expected_url = BASE_URL + quote(f"/과목별학원/{CATEGORY}/{slug}/", safe="/")
        title = extract(r"<title>(.*?)</title>", page)
        meta = extract(r'<meta name="description" content="([^"]*)"', page)
        canonical = extract(r'<link rel="canonical" href="([^"]+)"', page)
        og_url = extract(r'<meta property="og:url" content="([^"]+)"', page)
        h1s = re.findall(r"<h1(?:\s[^>]*)?>(.*?)</h1>", page, re.S | re.I)
        visible_faq = re.findall(r'<details class="subject-faq-item">', page)
        answer = extract(r'<div class="subject-answer-box">.*?<p>(.*?)</p>', page)
        review = extract(r'<section class="subject-review-section">.*?<blockquote>(.*?)</blockquote>', page)
        if intended_method not in review:
            errors.append(f"{slug}: intended secondary method missing in review")
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
        if not schema_faq or intended_method not in json.dumps(
            schema_faq[0], ensure_ascii=False
        ):
            errors.append(f"{slug}: intended secondary method missing in schema FAQ1")
        visible_faq_total += len(visible_faq)
        schema_faq_total += len(schema_faq)

        if len(faq_items) == len(schema_faq) == 5:
            for faq_index, (visible_item, schema_item) in enumerate(
                zip(faq_items, schema_faq), start=1
            ):
                visible_question = extract(
                    r"<summary><span>Q</span>(.*?)</summary>",
                    visible_item.group(0),
                )
                visible_answer = extract(
                    r'<div\s+class="subject-faq-answer"><span>A</span><p>(.*?)</p>',
                    visible_item.group(0),
                )
                schema_answer = schema_item.get("acceptedAnswer", {}).get("text", "")
                visible_question = html.unescape(visible_question)
                visible_answer = html.unescape(visible_answer)
                if visible_question != schema_item.get("name", ""):
                    errors.append(f"{slug}: FAQ{faq_index} visible/schema question mismatch")
                if visible_answer != schema_answer:
                    errors.append(f"{slug}: FAQ{faq_index} visible/schema answer mismatch")

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
        if page.count("<section") != page.count("</section>"):
            errors.append(f"{slug}: section tags unbalanced")
        if page.count("<details") != page.count("</details>"):
            errors.append(f"{slug}: details tags unbalanced")
        center_match = high_refresh.CENTER_BLOCK_RE.search(page)
        if not center_match or not high_refresh.extract_balanced_section(
            center_match.group(0), "wawa-center-snippet"
        ):
            errors.append(f"{slug}: center snippet unbalanced")
        elif "wawa-fee-accordion" in center_match.group(0):
            errors.append(f"{slug}: stale fee accordion remains")
        if any(
            isinstance(node, dict) and "hasOfferCatalog" in node
            for node in graph
        ):
            errors.append(f"{slug}: hidden offer catalog remains")
        raw_scope = f"{context.area} {context.locality}".strip()
        display_scope = high_refresh.geographic_scope(context)
        if raw_scope != display_scope and raw_scope in page:
            errors.append(f"{slug}: malformed geographic scope remains")
        if (
            context.area in high_refresh.AREA_DISPLAY_OVERRIDES
            or context.locality in high_refresh.AREA_FACT_OVERRIDES
        ):
            expanded_page = page
            for expanded in (
                *high_refresh.AREA_DISPLAY_OVERRIDES.values(),
                *high_refresh.AREA_FACT_OVERRIDES.values(),
            ):
                expanded_page = expanded_page.replace(expanded, "")
            if context.area in expanded_page:
                errors.append(f"{slug}: abbreviated geographic area remains")
        postal_override = high_refresh.POSTAL_ADDRESS_OVERRIDES.get(context.area)
        if context.locality in high_refresh.AREA_FACT_OVERRIDES:
            postal_override = (
                high_refresh.AREA_FACT_OVERRIDES[context.locality],
                context.locality,
            )
        if context.locality in high_refresh.POSTAL_LOCALITY_OVERRIDES:
            postal_override = high_refresh.POSTAL_LOCALITY_OVERRIDES[context.locality]
        if postal_override:
            organization = next(
                (
                    node
                    for node in graph
                    if isinstance(node, dict)
                    and "EducationalOrganization" in (
                        node.get("@type")
                        if isinstance(node.get("@type"), list)
                        else [node.get("@type")]
                    )
                ),
                {},
            )
            address = organization.get("address", {})
            if (
                address.get("addressRegion"),
                address.get("addressLocality"),
            ) != postal_override:
                errors.append(f"{slug}: postal address override mismatch")
        if 'class="subject-hidden-representative"' not in page or 'style="display:none;"' not in page:
            errors.append(f"{slug}: hidden representative missing")
        if f'assets/centers/common/{"seoul" if "서울" in extract(r"<p class=\"subject-kicker\">(.*?)</p>", page) else "local"}.webp' not in page:
            errors.append(f"{slug}: body image mismatch")
        map_src = extract(r'<img src="([^"\']*assets/maps/[^"\']+)"', page)
        site_page_path = SITE_ROOT / path.relative_to(ROOT)
        if not map_src or not (site_page_path.parent / map_src).resolve().exists():
            errors.append(f"{slug}: map image missing")
        if 'class="subject-related-grid"' not in page:
            errors.append(f"{slug}: related links missing")

        titles.append(title)
        metas.append(meta)
        answer_texts.append(re.sub(r"<[^>]+>", "", answer))
        review_texts.append(re.sub(r"<[^>]+>", "", review))

    sitemap = SITEMAP_PATH.read_text(encoding="utf-8")
    sitemap_count = sitemap.count("<url>")
    missing_sitemap = sum(
        1 for path in pages
        if BASE_URL + quote(f"/과목별학원/{CATEGORY}/{path.parent.name}/", safe="/") not in sitemap
    )
    hub_checks = {}
    for path in [
        SITE_ROOT / "과목별학원" / "index.html",
        SITE_ROOT / "과목별학원" / CATEGORY / "index.html",
    ]:
        page = path.read_text(encoding="utf-8")
        hub_checks[str(path.relative_to(SITE_ROOT))] = {
            "h1": len(re.findall(r"<h1(?:\s[^>]*)?>", page, re.I)),
            "indexed": 'content="index, follow"' in page,
            "jsonld_valid": all(json.loads(item) is not None for item in re.findall(r'<script type="application/ld\+json">(.*?)</script>', page, re.S)),
        }

    repeated_sentence, repeated_count = (
        flow_sentences.most_common(1)[0] if flow_sentences else ("", 0)
    )
    if repeated_count > 60:
        errors.append(
            f"exact sentence repeated {repeated_count} times: {repeated_sentence}"
        )

    report = {
        "local_pages": len(pages),
        "unique_titles": len(set(titles)),
        "unique_meta_descriptions": len(set(metas)),
        "unique_answer_blocks": len(set(answer_texts)),
        "unique_review_blocks": len(set(review_texts)),
        "duplicate_title_count": sum(count - 1 for count in Counter(titles).values() if count > 1),
        "visible_faq_total": visible_faq_total,
        "schema_faq_total": schema_faq_total,
        "differentiated_pages": differentiated_pages,
        "special_keyword_pages": special_pages,
        "keyword_occurrences": {
            "min": min(keyword_counts) if keyword_counts else 0,
            "max": max(keyword_counts) if keyword_counts else 0,
        },
        "sitemap_urls": sitemap_count,
        "missing_sitemap_urls": missing_sitemap,
        "hub_checks": hub_checks,
        "most_repeated_nonfact_sentence": {
            "count": repeated_count,
            "text": repeated_sentence,
        },
        "errors": errors[:100],
        "error_count": len(errors),
    }
    print(json.dumps(report, ensure_ascii=True, indent=2))
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
