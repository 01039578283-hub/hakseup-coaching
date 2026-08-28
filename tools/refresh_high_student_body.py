from __future__ import annotations

"""Differentiate repeated prose in 371 high-school-student locality pages.

The command is a validated dry run by default. ``--apply`` updates the visible
``subject-copy-flow`` content and WebPage/Article modification date. It gives
ambiguous or high-risk secondary keywords their own intent-specific copy and
FAQ answer. When old school copy conflicts with the verified source block, it
also synchronizes the third visible/schema FAQ and Article description. Apart
from verified school facts, geographic corrections, method-coherence updates,
targeted malformed or intent-mismatched H2 corrections, and a synchronized
existing center snippet, H1/title/canonical metadata, media, and internal-link
blocks stay unchanged.
"""

import argparse
import hashlib
import html
import itertools
import json
import re
import statistics
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urlsplit

try:
    from source_copy_utils import VERIFIED_SCHOOL_SOURCE_CORRECTIONS
except ModuleNotFoundError:  # package import
    from .source_copy_utils import VERIFIED_SCHOOL_SOURCE_CORRECTIONS


DEFAULT_ROOT = Path(__file__).resolve().parents[1]
CATEGORY = "고등학생학원"
RELEASE_DATE = "2026-08-28"
LEGACY_MARKER = "<!-- high-student-body-differentiation:2026-08-28 -->"
MARKER = "<!-- high-student-body-differentiation:2026-08-28-v2 -->"
KEYWORD_MARKER_RE = re.compile(
    r"<!--\s*high-student-secondary-keyword:([가-힣A-Za-z0-9·]+)\s*-->"
)
AREA_FACT_OVERRIDES = {
    "다정동": "세종특별자치시",
    "새롬동": "세종특별자치시",
}
AREA_DISPLAY_OVERRIDES = {
    "충청 청주시": "충청북도 청주시",
    "충청 천안시": "충청남도 천안시",
    "충청 충주시": "충청북도 충주시",
    "충청 당진시": "충청남도 당진시",
    "충청 아산시": "충청남도 아산시",
    "경상 경산시": "경상북도 경산시",
    "경상 창원시": "경상남도 창원시",
    "경상 거제시": "경상남도 거제시",
    "경상 포항시": "경상북도 포항시",
    "경상 구미시": "경상북도 구미시",
    "전라 전주시": "전북특별자치도 전주시",
    "전라 완주군": "전북특별자치도 완주군",
    "제주 제주시": "제주특별자치도 제주시",
}
POSTAL_ADDRESS_OVERRIDES = {
    "충청 청주시": ("충청북도", "청주시"),
    "충청 천안시": ("충청남도", "천안시"),
    "충청 충주시": ("충청북도", "충주시"),
    "충청 당진시": ("충청남도", "당진시"),
    "충청 아산시": ("충청남도", "아산시"),
    "경상 경산시": ("경상북도", "경산시"),
    "경상 창원시": ("경상남도", "창원시"),
    "경상 거제시": ("경상남도", "거제시"),
    "경상 포항시": ("경상북도", "포항시"),
    "경상 구미시": ("경상북도", "구미시"),
    "전라 전주시": ("전북특별자치도", "전주시"),
    "전라 완주군": ("전북특별자치도", "완주군"),
    "제주 제주시": ("제주특별자치도", "제주시"),
}
POSTAL_LOCALITY_OVERRIDES = {
    "다정동": ("세종특별자치시", "새롬동"),
    "위례": ("경기도", "성남시 수정구"),
    "위례신도시": ("경기도", "성남시 수정구"),
    "창곡동": ("경기도", "성남시 수정구"),
}
SCOPE_OVERRIDES = {
    "전주 장동": "전주 장동",
    "전주혁신도시": "전주 혁신도시",
}
SEMANTIC_HEADING_REPLACEMENTS = (
    ("복습 시작을 줄이는", "복습 시작 지연을 줄이는"),
    ("과제 점검을 줄이는", "과제 점검 누락을 줄이는"),
    ("시험 시간을 줄이는", "시험 시간 부족을 줄이는"),
    ("난도 적응을 줄이는", "난도 적응 부담을 줄이는"),
    ("시험 분석을 줄이는", "시험 분석 누락을 줄이는"),
    ("과목 우선순위를 줄이는", "과목 우선순위 혼선을 줄이는"),
    ("집중 지속을 줄이는", "집중 중단을 줄이는"),
    ("서술형 구성을 줄이는", "서술형 구성 오류를 줄이는"),
    ("자기 설명을 줄이는", "자기 설명 부족을 줄이는"),
    ("검토 절차를 줄이는", "검토 절차 누락을 줄이는"),
    ("오답 원인을 줄이는", "오답 반복을 줄이는"),
    ("복습 시작을 정확히 진단하는", "복습 시작이 늦어지는 원인을 진단하는"),
    ("과제 점검을 정확히 진단하는", "과제 점검 누락의 원인을 진단하는"),
    ("시험 시간을 정확히 진단하는", "시험 시간 부족의 원인을 진단하는"),
    ("난도 적응을 정확히 진단하는", "난도 적응 부담의 원인을 진단하는"),
    ("시험 분석을 정확히 진단하는", "시험 결과를 정확히 분석하는"),
    ("과목 우선순위를 정확히 진단하는", "과목 우선순위 혼선을 진단하는"),
    ("집중 지속을 정확히 진단하는", "집중이 중단되는 원인을 진단하는"),
    ("서술형 구성을 정확히 진단하는", "서술형 구성 오류를 진단하는"),
    ("자기 설명을 정확히 진단하는", "자기 설명이 부족한 원인을 진단하는"),
    ("검토 절차를 정확히 진단하는", "검토 절차 누락을 진단하는"),
)
FLOW_RE = re.compile(
    r'(<div\s+class="subject-copy-flow">)(.*?)(</div>\s*</article>)', re.I | re.S
)
JSONLD_RE = re.compile(
    r'(<script\b[^>]*type=["\']application/ld\+json["\'][^>]*>)(.*?)(</script>)',
    re.I | re.S,
)
SCHOOL_RE = re.compile(
    r"<!-- school-reference:start -->.*?<!-- school-reference:end -->", re.I | re.S
)
NETWORK_RE = re.compile(
    r"<!-- local-study-network:start -->.*?<!-- local-study-network:end -->",
    re.I | re.S,
)
FAQ_RE = re.compile(
    r'<section\b[^>]*class="subject-faq-section".*?</section>', re.I | re.S
)
FAQ_ITEM_RE = re.compile(
    r'<details\b[^>]*class="subject-faq-item".*?</details>', re.I | re.S
)
CENTER_BLOCK_RE = re.compile(
    r'<section\b[^>]*class=["\'][^"\']*\bwawa-center-snippet\b[^"\']*["\'][^>]*>'
    r'.*?(?=\s*<section\b[^>]*class=["\'][^"\']*\bsubject-related-section\b)',
    re.I | re.S,
)
ANSWER_RE = re.compile(
    r'<div\b[^>]*class="subject-answer-box".*?</div>', re.I | re.S
)
REVIEW_RE = re.compile(
    r'<section\b[^>]*class="subject-review-section".*?</section>', re.I | re.S
)
SCRIPT_STYLE_RE = re.compile(
    r"<(?:script|style|header|footer|nav|noscript|svg)\b.*?</(?:script|style|header|footer|nav|noscript|svg)>",
    re.I | re.S,
)
TAG_RE = re.compile(r"<[^>]+>")


@dataclass(frozen=True)
class Context:
    path: Path
    ordinal: int
    before: str
    title: str
    locality: str
    area: str
    grade: str
    persona: str
    keyword: str
    school_state: str
    schools: tuple[str, ...]
    school_fact: str


@dataclass(frozen=True)
class Plan:
    context: Context
    after: str
    replacements: int
    school_fixes: int
    particle_fixes: int
    keyword_reductions: int


def clean(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(TAG_RE.sub(" ", value or ""))).strip()


def first(pattern: str, source: str, flags: int = re.I | re.S) -> str:
    match = re.search(pattern, source, flags)
    return clean(match.group(1)) if match else ""


def stable_number(value: str, salt: str) -> int:
    digest = hashlib.sha256(f"{value}|{salt}".encode("utf-8")).hexdigest()
    return int(digest[:14], 16)


def choose(context: Context, salt: str, values: tuple[str, ...]) -> str:
    if not values:
        raise ValueError(f"empty choice pool: {salt}")
    return values[stable_number(context.title, salt) % len(values)]


def has_batchim(value: str) -> bool:
    last = next((char for char in reversed(value) if "가" <= char <= "힣"), "")
    return bool(last) and (ord(last) - ord("가")) % 28 != 0


def particle(value: str, batchim: str, no_batchim: str) -> str:
    return batchim if has_batchim(value) else no_batchim


def extract_context(path: Path, ordinal: int) -> Context:
    source = path.read_text(encoding="utf-8", errors="strict")
    title = first(r"<h1\b[^>]*>(.*?)</h1>", source)
    suffix = f" {CATEGORY}"
    locality = title[: -len(suffix)].strip() if title.endswith(suffix) else ""
    area = first(r"HIGH SCHOOL COACHING\s*·\s*([^<]+)</p>", source)
    flow_match = FLOW_RE.search(source)
    flow_html = flow_match.group(2) if flow_match else ""
    flow_text = clean(flow_html)
    grade_match = re.search(r"(?:예비고1|고[1-3])", flow_text)
    grade = grade_match.group(0) if grade_match else "고등학생"
    persona_match = re.search(
        r"((?:예비고1|고[1-3])\s+[^<.]{2,100}?\s+유형)에는 “두 시간 공부”",
        flow_html,
    )
    if not persona_match:
        persona_match = re.search(
            r"((?:예비고1|고[1-3])\s+[^<.!?]{1,60}?·[^<.!?]{1,60}?\s+유형)",
            flow_html,
        )
    persona = persona_match.group(1).strip() if persona_match else grade + " 학생"
    keyword_match = KEYWORD_MARKER_RE.search(flow_html)
    if not keyword_match:
        keyword_match = re.search(
            rf"{re.escape(locality)}에서\s+([가-힣A-Za-z0-9·]+)(?:을|를)\s+알아볼 때 핵심",
            flow_text,
        )
    if not keyword_match:
        keyword_match = re.search(
            r"광고 문구가 아닌\s+([가-힣A-Za-z0-9·]+)의 실제 확인법",
            flow_text,
        )
    keyword = keyword_match.group(1) if keyword_match else "학습관리"
    school_block = SCHOOL_RE.search(source)
    school_html = school_block.group(0) if school_block else ""
    state_match = re.search(r'data-source-state="(provided|missing|coverage)"', school_html)
    school_state = state_match.group(1) if state_match else ""
    schools = tuple(re.findall(r'data-source-school="([^"]+)"', school_html))
    school_fact = first(r"<span\s+data-school-source-fact>(.*?)</span>", school_html)
    missing = [
        name
        for name, value in (
            ("title", title),
            ("locality", locality),
            ("area", area),
            ("flow", flow_text),
            ("school_state", school_state),
            ("school_fact", school_fact),
        )
        if not value
    ]
    if missing:
        raise ValueError(f"{path}: context missing {missing}")
    if school_state == "provided" and not schools:
        raise ValueError(f"{path}: provided school state without schools")
    if school_state != "provided" and schools:
        raise ValueError(f"{path}: {school_state} state unexpectedly has schools")
    return Context(
        path, ordinal, source, title, locality, area, grade, persona, keyword,
        school_state, schools, school_fact,
    )


def replace_literal(value: str, before: str, after: str) -> tuple[str, int]:
    if before not in value:
        return value, 0
    return value.replace(before, after, 1), 1


def correct_semantic_heading_phrases(value: str) -> tuple[str, int]:
    total = 0
    for before, after in SEMANTIC_HEADING_REPLACEMENTS:
        count = value.count(before)
        if count:
            value = value.replace(before, after)
            total += count
    value, count = re.subn(
        r"(?P<issue>[가-힣· ]{2,30})(?:이|가) 반복되는 학생을 위한 선택 기준",
        lambda match: (
            f"{match.group('issue').strip()}"
            f"{'' if match.group('issue').strip().endswith('점검') else ' 점검'}"
            "이 필요한 학생을 위한 선택 기준"
        ),
        value,
    )
    total += count
    value, count = re.subn(
        r"(?P<prefix>고등학생학원에서 )(?P<object>[가-힣A-Za-z0-9·]+(?:을|를)) "
        r"판단하는 방법",
        lambda match: f"{match.group('prefix')}{match.group('object')} 확인하는 기준",
        value,
    )
    total += count
    return value, total


def geographic_scope(context: Context) -> str:
    """Join area/locality without repeating the same city token."""
    if context.locality in SCOPE_OVERRIDES:
        return SCOPE_OVERRIDES[context.locality]
    if context.locality in AREA_FACT_OVERRIDES:
        return f"{AREA_FACT_OVERRIDES[context.locality]} {context.locality}"
    area = AREA_DISPLAY_OVERRIDES.get(context.area, context.area)
    locality_parts = context.locality.split()
    if len(locality_parts) > 1 and locality_parts[0] in area:
        return f"{area} {' '.join(locality_parts[1:])}".strip()
    for token in reversed(area.split()):
        base = re.sub(r"(?:특별자치시|광역시|특별시|시|군|구)$", "", token)
        if (
            len(base) >= 2
            and context.locality.startswith(base)
            and context.locality[len(base) :] not in {"", "동", "읍", "면", "리"}
        ):
            return f"{area} {context.locality[len(base):]}".strip()
    return f"{area} {context.locality}".strip()


def correct_geographic_scope_phrases(
    value: str, context: Context
) -> tuple[str, int]:
    before = f"{context.area} {context.locality}".strip()
    after = geographic_scope(context)
    total = value.count(before) if before != after else 0
    if total:
        value = value.replace(before, after)
    override = AREA_FACT_OVERRIDES.get(context.locality) or AREA_DISPLAY_OVERRIDES.get(
        context.area
    )
    if override and context.area != override:
        count = value.count(context.area)
        if count:
            value = value.replace(context.area, override)
            total += count
    return value, total


def extract_balanced_section(source: str, class_name: str) -> str:
    opening = re.search(
        rf'<section\b(?=[^>]*class=["\'][^"\']*\b{re.escape(class_name)}\b)[^>]*>',
        source,
        re.I,
    )
    if not opening:
        return ""
    depth = 0
    for token in re.finditer(r'</?section\b[^>]*>', source[opening.start() :], re.I):
        value = token.group(0)
        if value.startswith("</"):
            depth -= 1
            if depth == 0:
                return source[opening.start() : opening.start() + token.end()]
        elif not value.rstrip().endswith("/>"):
            depth += 1
    return ""


def reference_center_snippet(context: Context, reference_root: Path) -> str:
    for href in re.findall(r'\bhref=["\']([^"\']+)["\']', context.before, re.I):
        decoded = unquote(urlsplit(html.unescape(href)).path)
        parts = [part for part in decoded.split("/") if part]
        if len(parts) != 4 or parts[0] != "전국학원":
            continue
        candidate = reference_root.joinpath(*parts, "index.html")
        if not candidate.is_file():
            continue
        snippet = extract_balanced_section(
            candidate.read_text(encoding="utf-8", errors="strict"),
            "wawa-center-snippet",
        )
        if not snippet:
            raise ValueError(f"{candidate}: balanced center snippet missing")
        return snippet
    raise ValueError(f"{context.path}: nationwide reference page missing")


def sync_center_snippet(source: str, snippet: str, context: Context) -> tuple[str, int]:
    match = CENTER_BLOCK_RE.search(source)
    if not match:
        raise ValueError(f"{context.path}: inherited center snippet boundary missing")
    updated = source[: match.start()] + snippet + source[match.end() :]
    if updated.count('<section class="wawa-center-snippet"') != 1:
        raise ValueError(f"{context.path}: center snippet count invalid")
    return updated, int(updated != source)


def school_display(context: Context) -> str:
    return "·".join(context.schools)


def split_school_names(value: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in re.split(r"[·,]", value) if item.strip())


def school_mismatch(flow: str, context: Context) -> bool:
    plain_flow = clean(flow)
    normalized_flow = re.sub(r"\s*[·,]\s*", "·", clean(flow))
    normalized_expected = re.sub(
        r"\s*[·,]\s*", "·", corrected_school_copy(context)
    )
    if normalized_expected in normalized_flow:
        return False
    if any(
        fused in plain_flow for fused in VERIFIED_SCHOOL_SOURCE_CORRECTIONS
    ):
        return True
    match = re.search(
        r"[^<>.!?]{0,80}?자료에 기재된 학교는 (?P<names>[^<>.!?]{1,160}?)(?=이며,)",
        flow,
    )
    names = split_school_names(match.group("names")) if match else ()
    says_missing = "자료에는 수업 학교명이 없어" in clean(flow)
    if bool(names) == says_missing:
        raise ValueError(f"{context.path}: ambiguous legacy school statement")
    tokens = {
        token
        for chip in context.schools
        for token in re.split(r"[\s·,/]+", chip)
        if token
    }
    listed_tokens = {
        token
        for name in names
        for token in re.split(r"[\s·,/]+", name)
        if token
    }
    invalid = listed_tokens - tokens
    missing = tokens - listed_tokens
    if context.school_state == "provided":
        return bool(invalid or missing)
    return context.school_state in {"missing", "coverage"} and bool(names)


def school_boundary(context: Context) -> str:
    if context.school_state == "provided":
        return "학교별 범위는 학생이 받은 범위표·학교 자료·최근 시험지로 다시 확인하세요."
    if context.school_state == "coverage":
        return "개별 학교의 현재 편성은 재학 학교·과목과 함께 별도로 확인하세요."
    return "특정 학교를 임의로 추가하지 말고 재학 학교·학년·범위표를 상담에서 확인하세요."


def corrected_school_copy(context: Context) -> str:
    if context.school_state == "coverage":
        return (
            f"{context.locality} 공통 타깃학교 원자료에는 ‘지역내 모든 고등학교 가능’이라는 범위 문구가 있으나, "
            "현재 연결된 센터 정보에는 개별 고등학교명이 기재되지 않았습니다. "
            "실제 수업 가능 여부는 재학 학교·학년·과목을 밝혀 최신 상담에서 확인하세요."
        )
    return f"{context.school_fact} {school_boundary(context)}"


def coverage_school_summary(context: Context) -> str:
    return (
        f"{context.locality} 공통 타깃학교 원자료에는 ‘지역내 모든 고등학교 가능’이라는 범위 문구가 있으나, "
        "현재 연결된 센터 정보에는 개별 고등학교명이 기재되지 않았습니다. "
        "실제 수업 가능 여부는 재학 학교·학년·과목을 밝혀 최신 상담에서 확인해야 합니다."
    )


def school_exam_reference(context: Context) -> str:
    """Build the body exam sentence only from verified high-school facts."""
    if context.school_state == "provided":
        selected = context.schools[:2]
        schools = selected[0] if len(selected) == 1 else f"{selected[0]} 또는 {selected[1]}"
        subject = f"{context.locality}의 {schools}"
    else:
        subject = f"{context.locality} 학생이 재학 중인 학교의"
        return f"{subject} 시험 준비에서는 범위 확인일과 1차 학습 완료일을 구분합니다."
    return f"{subject} 시험 준비에서는 범위 확인일과 1차 학습 완료일을 구분합니다."


def school_faq_question(context: Context) -> str:
    locality = context.locality
    if context.school_state == "provided":
        return f"{locality} 고등학생의 학교별 내신 범위는 어떤 자료로 확인해야 하나요?"
    if context.school_state == "coverage":
        return f"{locality}의 ‘지역내 모든 고등학교 가능’ 문구는 어떻게 확인해야 하나요?"
    return f"{locality} 고등학생의 재학 학교 정보가 원자료에 없을 때 무엇을 확인해야 하나요?"


def school_article_phrase(context: Context) -> str:
    locality = context.locality
    if context.school_state == "provided":
        return f"{locality} 자료의 고등학교 실제 수업 가능 학교는 {school_display(context)}이며 학원 주소는"
    if context.school_state == "coverage":
        return (
            f"{locality} 공통 타깃학교 원자료에는 ‘지역내 모든 고등학교 가능’이라는 범위 문구가 있으나 "
            "연결된 센터 정보에는 개별 고등학교명이 없으며 학원 주소는"
        )
    return f"{locality} 자료의 고등학교 타깃학교 칸은 미기재 상태이며 학원 주소는"


def corrected_heading_phrase(context: Context) -> tuple[str, str]:
    before = f"{context.keyword}와 학부모 소통"
    after = f"{context.keyword}{particle(context.keyword, '과', '와')} 학부모 소통"
    return before, after


OPERATOR_SYSTEM_KEYWORDS = {
    "학원결제시스템", "학원고객관리시스템", "학원관리솔루션",
    "학원관리앱", "학원관리프로그램",
}
OPERATOR_WORKFLOW_KEYWORDS = {
    "학원결제관리", "학원고객관리", "학원관리", "학원매출관리",
    "학원문서관리", "학원미납관리", "학원상담관리", "학원수강생관리",
    "학원수납관리", "학원운영", "학원행정", "학원회원관리",
}
OPERATOR_OTHER_KEYWORDS = {"학원창업", "학원운영자", "학원프로그램"}
OPERATOR_KEYWORDS = (
    OPERATOR_SYSTEM_KEYWORDS | OPERATOR_WORKFLOW_KEYWORDS | OPERATOR_OTHER_KEYWORDS
)


def special_keyword_heading(context: Context) -> str:
    locality = context.locality
    keyword = context.keyword
    if keyword in OPERATOR_SYSTEM_KEYWORDS:
        return (
            f"{locality}에서 {keyword}{particle(keyword, '을', '를')} "
            "도입하기 전에 확인할 기능과 데이터 기준"
        )
    if keyword == "학원창업":
        return f"{locality} 학원창업 준비에서 확인할 교육·운영 기준"
    if keyword == "학원개원":
        return f"{locality} 학원개원의 두 가지 검색 의도를 구분하는 기준"
    if keyword == "학원운영자":
        return f"{locality} 학원운영자의 역할과 책임을 확인하는 기준"
    if keyword == "학원프로그램":
        return f"{locality} 학원프로그램의 두 가지 의미를 구분하는 기준"
    if keyword == "학원관리":
        return f"{locality} 학원관리에서 학습과 운영 업무를 구분하는 기준"
    if keyword == "학원운영":
        return f"{locality} 학원운영에서 확인할 기록과 책임"
    if keyword == "학원행정":
        return f"{locality} 학원행정에서 확인할 기록과 절차"
    if keyword in OPERATOR_WORKFLOW_KEYWORDS:
        return f"{locality} {keyword} 운영에서 확인할 기록과 절차"
    if keyword == "내신성적":
        return f"{locality} 내신성적을 점수표보다 깊게 읽는 기준"
    if keyword == "내신분석":
        return f"{locality} 내신분석에서 답안과 학교 자료를 보는 순서"
    if keyword == "자기주도학습":
        return f"{locality} 자기주도학습에서 스스로 정하고 점검할 네 단계"
    if keyword == "일일학습점검":
        return f"{locality} 일일학습점검에서 다음 날 행동까지 연결하는 기준"
    if keyword == "주간학습점검":
        return f"{locality} 주간학습점검에서 누적 흐름을 조정하는 기준"
    if keyword == "월간학습점검":
        return f"{locality} 월간학습점검에서 변화 추세와 다음 목표를 읽는 기준"
    if keyword == "정기학습점검":
        return f"{locality} 정기학습점검의 간격·지표·후속 행동 기준"
    if keyword == "녹화수업":
        return f"{locality} 녹화수업에서 시청과 이해를 함께 확인하는 기준"
    if keyword in {
        "실시간수업", "온라인수업", "화상수업",
        "학원실시간수업", "학원온라인수업", "학원화상수업",
    }:
        return f"{locality} {keyword}의 접속·질문·대체 절차 확인 기준"
    if keyword in {"수준별수업", "학원수준별수업"}:
        return f"{locality} {keyword}의 배치와 반 변경 기준"
    if keyword in {
        "개별지도", "학원개별지도", "개인별수업",
        "맞춤수업", "학원맞춤수업",
    }:
        return f"{locality} {keyword}의 인원·진도·피드백 확인 기준"
    if keyword == "참여형수업":
        return f"{locality} 참여형수업에서 학생이 남겨야 할 학습 결과"
    if keyword == "토론형수업":
        return f"{locality} 토론형수업의 근거·발언·반론 확인 기준"
    if keyword == "클리닉수업":
        return f"{locality} 클리닉수업의 진단·보완·재확인 흐름"
    if keyword in {"특강수업", "학원특강", "입시특강"}:
        return f"{locality} {keyword}의 기간·주제·완료 범위 확인 기준"
    if keyword in {"보강수업", "학원보강"}:
        return f"{locality} {keyword}의 신청·진도·예외 처리 기준"
    if keyword in {"보충수업", "학원보충"}:
        return f"{locality} {keyword}의 대상·보완 범위·종료 기준"
    if keyword in {"일대일수업", "학원일대일"}:
        return f"{locality} {keyword}의 1:1 운영·진도 조정 기준"
    if keyword in {"소수정예수업", "학원소수정예"}:
        return f"{locality} {keyword}의 인원·질문·개별 조정 기준"
    if keyword == "학원집중반":
        return f"{locality} 학원집중반의 기간·분량·종료 기준"
    if keyword == "학습교재관리":
        return f"{locality} 학습교재관리의 선택·진도·교체 기준"
    if keyword == "학원환불":
        return f"{locality} 학원환불의 신청·처리·정산 조건을 확인하는 기준"
    if keyword == "학원프로모션":
        return f"{locality} 학원프로모션의 적용 범위와 정상 수강료 전환 시점을 확인하는 기준"
    if keyword == "학원매니저":
        return f"{locality} 학원매니저의 담당 업무와 문의 연결 범위를 확인하는 기준"
    if keyword == "입시상담예약":
        return f"{locality} 입시상담예약 전 준비 자료와 변경 절차를 확인하는 기준"
    if keyword == "학원셔틀":
        return f"{locality} 학원셔틀의 운행 조건과 실제 통학 동선을 확인하는 기준"
    if keyword == "입시실적":
        return f"{locality} 입시실적의 집계 조건과 현재 학생의 준비 과정을 구분하는 기준"
    if keyword == "학원강의실":
        return f"{locality} 학원강의실의 이용 조건과 학습 환경을 확인하는 기준"
    if keyword == "학원스터디룸":
        return f"{locality} 학원스터디룸의 이용 조건과 학습 환경을 확인하는 기준"
    if keyword == "학원교재실":
        return f"{locality} 학원교재실의 분류·대여·보관 기준"
    if keyword == "학원사물함":
        return f"{locality} 학원사물함의 배정·보관·반납 기준"
    if keyword == "학원상담실":
        return f"{locality} 학원상담실의 이용·기록·개인정보 기준"
    if keyword == "학원자료실":
        return f"{locality} 학원자료실의 접근·대여·버전 관리 기준"
    if keyword == "학원출결앱":
        return f"{locality} 학원출결앱의 확인·알림·수정 기준"
    if keyword == "학원휴게실":
        return f"{locality} 학원휴게실의 이용·청결·수업 복귀 기준"
    if keyword == "학원주차":
        return f"{locality} 학원주차의 위치·비용·승하차 기준"
    if keyword == "학원일정":
        return f"{locality} 학원일정의 수업일·휴강·변경 확인 기준"
    if keyword == "학원온라인등록":
        return f"{locality} 학원온라인등록의 신청·동의·확정 기준"
    if keyword == "학원재등록":
        return f"{locality} 학원재등록의 기존 기록·변경 조건·기한 확인 기준"
    if keyword in {"학원문자발송", "학원알림톡"}:
        return f"{locality} {keyword}의 수신 동의·발송·실패 처리 기준"
    if keyword == "시험시간관리":
        return f"{locality} 시험시간관리의 배분·전환·검토 기준"
    if keyword in {"학습성과관리", "학습성적관리"}:
        return f"{locality} {keyword}의 측정·비교·후속 행동 기준"
    if keyword == "학원출결":
        return f"{locality} 학원출결의 기록·통보·수정 기준"
    return ""


def special_keyword_faq_question(context: Context) -> str:
    locality = context.locality
    keyword = context.keyword
    if keyword in OPERATOR_SYSTEM_KEYWORDS:
        return (
            f"{locality}에서 {keyword}{particle(keyword, '을', '를')} "
            "도입하기 전에 무엇을 확인해야 하나요?"
        )
    if keyword == "학원창업":
        return f"{locality}에서 학원창업을 준비할 때 무엇을 확인해야 하나요?"
    if keyword == "학원개원":
        return f"{locality} 학원개원은 신규 학원 확인과 개원 준비를 어떻게 구분하나요?"
    if keyword == "학원운영자":
        return f"{locality}에서 학원운영자의 역할과 책임은 어떻게 확인하나요?"
    if keyword == "학원프로그램":
        return f"{locality}에서 학원프로그램의 두 가지 의미는 어떻게 구분하나요?"
    if keyword == "학원관리":
        return f"{locality}에서 학원관리의 학습 업무와 운영 업무는 어떻게 구분하나요?"
    if keyword == "학원운영":
        return f"{locality}에서 학원운영의 기록과 책임은 어떻게 확인하나요?"
    if keyword == "학원행정":
        return f"{locality}에서 학원행정 업무는 무엇을 확인해야 하나요?"
    if keyword in OPERATOR_WORKFLOW_KEYWORDS:
        return f"{locality}에서 {keyword} 운영은 무엇을 확인해야 하나요?"
    if keyword == "내신성적":
        return f"{locality} 내신성적은 어떤 기준으로 해석해야 하나요?"
    if keyword == "내신분석":
        return f"{locality} 내신분석에는 어떤 자료가 필요한가요?"
    if keyword == "자기주도학습":
        return f"{locality} 자기주도학습은 혼자 공부하는 것과 무엇이 다른가요?"
    if keyword == "일일학습점검":
        return f"{locality} 일일학습점검에서는 매일 무엇을 확인해야 하나요?"
    if keyword == "주간학습점검":
        return f"{locality} 주간학습점검에서는 한 주의 무엇을 조정해야 하나요?"
    if keyword == "월간학습점검":
        return f"{locality} 월간학습점검에서는 어떤 변화를 비교해야 하나요?"
    if keyword == "정기학습점검":
        return f"{locality} 정기학습점검의 간격과 기준은 어떻게 정하나요?"
    if keyword == "녹화수업":
        return f"{locality} 녹화수업을 선택할 때 무엇을 확인해야 하나요?"
    if keyword in {
        "실시간수업", "온라인수업", "화상수업",
        "학원실시간수업", "학원온라인수업", "학원화상수업",
    }:
        return f"{locality} {keyword}의 진행 방식과 접속 장애 대체 절차는 어떻게 확인하나요?"
    if keyword in {"수준별수업", "학원수준별수업"}:
        return f"{locality} {keyword}의 배치와 반 변경은 어떤 기준으로 정하나요?"
    if keyword in {
        "개별지도", "학원개별지도", "개인별수업",
        "맞춤수업", "학원맞춤수업",
    }:
        return (
            f"{locality} {keyword}{particle(keyword, '은', '는')} "
            "학생별 진도와 피드백을 어떻게 조정하나요?"
        )
    if keyword == "참여형수업":
        return f"{locality} 참여형수업에서는 학생의 참여를 무엇으로 확인하나요?"
    if keyword == "토론형수업":
        return f"{locality} 토론형수업에서는 어떤 기록을 확인해야 하나요?"
    if keyword == "클리닉수업":
        return f"{locality} 클리닉수업의 진행 순서는 무엇으로 확인하나요?"
    if keyword in {"특강수업", "학원특강", "입시특강"}:
        return f"{locality} {keyword}{particle(keyword, '을', '를')} 선택하기 전에 무엇을 확인해야 하나요?"
    if keyword in {"보강수업", "학원보강"}:
        return f"{locality} {keyword}의 신청과 진도·예외 조건은 무엇인가요?"
    if keyword in {"보충수업", "학원보충"}:
        return f"{locality} {keyword}은 어떤 학생과 보완 범위를 대상으로 하나요?"
    if keyword in {"일대일수업", "학원일대일"}:
        return f"{locality} {keyword}은 실제로 어떻게 1:1 진도를 조정하나요?"
    if keyword in {"소수정예수업", "학원소수정예"}:
        return f"{locality} {keyword}의 인원과 개별 피드백은 어떻게 확인하나요?"
    if keyword == "학원집중반":
        return f"{locality} 학원집중반의 기간과 완료 범위는 어떻게 확인하나요?"
    if keyword == "학습교재관리":
        return f"{locality} 학습교재관리는 어떤 기준으로 교재를 선택하고 바꾸나요?"
    if keyword == "학원교재실":
        return f"{locality} 학원교재실은 교재를 어떻게 분류하고 대여·반납하나요?"
    if keyword == "학원사물함":
        return f"{locality} 학원사물함의 배정과 보관·반납 조건은 무엇인가요?"
    if keyword == "학원상담실":
        return f"{locality} 학원상담실 이용과 상담 기록은 어떻게 확인하나요?"
    if keyword == "학원자료실":
        return f"{locality} 학원자료실은 어떤 자료를 어떻게 이용하고 관리하나요?"
    if keyword == "학원출결앱":
        return f"{locality} 학원출결앱의 확인과 알림·수정 기능은 어떻게 살펴보나요?"
    if keyword == "학원휴게실":
        return f"{locality} 학원휴게실은 어떤 이용 규칙과 수업 복귀 기준을 확인해야 하나요?"
    if keyword == "학원주차":
        return f"{locality} 학원주차는 위치·이용 시간·비용을 어떻게 확인하나요?"
    if keyword == "학원일정":
        return f"{locality} 학원일정은 수업일과 휴강·변경을 어떻게 확인하나요?"
    if keyword == "학원온라인등록":
        return f"{locality} 학원온라인등록은 접수와 최종 확정을 어떻게 구분하나요?"
    if keyword == "학원재등록":
        return f"{locality} 학원재등록 전에 기존 기록과 변경 조건을 어떻게 확인하나요?"
    if keyword in {"학원문자발송", "학원알림톡"}:
        return f"{locality} {keyword}의 수신 동의와 실패·재발송은 어떻게 관리하나요?"
    if keyword == "시험시간관리":
        return f"{locality} 시험시간관리는 문항별 배분과 검토 시간을 어떻게 정하나요?"
    if keyword in {"학습성과관리", "학습성적관리"}:
        return (
            f"{locality} {keyword}{particle(keyword, '은', '는')} "
            "어떤 자료와 기간을 기준으로 확인하나요?"
        )
    if keyword == "학원출결":
        return f"{locality} 학원출결은 등원·하원과 누락·수정을 어떻게 확인하나요?"
    return ""


def special_keyword_paragraphs(context: Context) -> tuple[str, str] | tuple[()]:
    if context.keyword in {"수준별수업", "학원수준별수업"}:
        return (
            (
                f"{context.locality}에서 {context.keyword}{particle(context.keyword, '을', '를')} 알아볼 때는 반 이름보다 첫 배치에 사용한 시험지·설명·과제 자료와 단원별 통과 기준을 확인해야 합니다. "
                "같은 학년이라도 개념 이해와 적용 속도가 다르므로 어느 범위부터 시작하고 어떤 도움을 제공하는지 구체적으로 물어보세요."
            ),
            (
                f"{context.locality} 학생의 반 이동은 한 번의 점수보다 일정 기간의 완료 범위, 독립 풀이, 질문과 재풀이 결과로 판단하는 편이 좋습니다. "
                "상향·유지·보완 배치의 조건과 확인 주기, 변경 뒤 진도 공백을 보완하는 절차가 안내되는지 살펴보세요."
            ),
        )
    if context.keyword in {
        "개별지도", "학원개별지도", "개인별수업",
        "맞춤수업", "학원맞춤수업",
    }:
        return (
            (
                f"{context.locality}에서 {context.keyword}{particle(context.keyword, '을', '를')} 확인할 때는 수업 인원과 학생이 질문·설명을 주고받을 수 있는 시간을 먼저 살펴봐야 합니다. "
                "최근 시험지·교재·오답을 바탕으로 학생별 설명과 연습 범위, 진도 시작점을 어떻게 정하는지 실제 자료에서 확인하세요."
            ),
            (
                f"{context.locality} 학생에게 맞춘 과제와 진도 조정은 막연한 개인별 대응이 아니라 완료 범위·질문·재풀이 결과에 근거해야 합니다. "
                "결석·미완료·이해 부족 때의 보완 절차와 다음 점검일, 학부모에게 전달할 피드백 항목도 구체적으로 물어보세요."
            ),
        )
    if context.keyword in {"일대일수업", "학원일대일"}:
        return (
            (
                f"{context.locality}에서 {context.keyword}{particle(context.keyword, '을', '를')} 확인할 때는 실제 한 명의 학생과 한 명의 담당자가 수업하는 범위와 질문·설명 시간을 먼저 물어봐야 합니다. "
                "최근 시험지·교재·오답을 바탕으로 시작 진도와 설명·연습 순서를 어떻게 정하는지 실제 계획에서 살펴보세요."
            ),
            (
                f"{context.locality} 학생의 과제와 진도는 완료 범위·질문·재풀이 결과에 따라 조정되는 편이 좋습니다. "
                "담당자 변경이나 결석 때 수업 기록을 어떻게 이어 가는지, 이해가 부족할 때의 보완과 다음 점검일도 함께 확인하세요."
            ),
        )
    if context.keyword in {"소수정예수업", "학원소수정예"}:
        return (
            (
                f"{context.locality}에서 {context.keyword}{particle(context.keyword, '을', '를')} 알아볼 때는 최대 인원뿐 아니라 현재 참여 인원과 학생별 질문·설명 시간을 확인해야 합니다. "
                "같은 그룹 안에서도 시작 진도와 과제, 오답 보완 범위를 어떤 자료로 다르게 정하는지 물어보세요."
            ),
            (
                f"{context.locality} 학생에게 맞는 소수 수업은 단순히 인원이 적은 수업이 아니라 개별 완료·질문·재풀이 기록이 다음 진도에 반영되는 수업입니다. "
                "그룹의 공통 속도가 맞지 않을 때 과제·설명·반 편성을 조정하는 기준과 학부모 피드백 시점도 살펴보세요."
            ),
        )
    if context.keyword == "참여형수업":
        return (
            (
                f"{context.locality}에서 참여형수업을 확인할 때는 손을 들거나 말한 횟수보다 학생이 설명·질문·풀이·요약으로 어떤 학습 결과를 남기는지 살펴봐야 합니다. "
                "수업 전 준비 자료와 활동 중 역할, 활동 뒤 확인할 결과물이 구체적으로 정해지는지 물어보세요."
            ),
            (
                f"{context.locality} 학생의 참여 기록에는 제시한 근거, 해결한 문제, 남은 질문과 피드백 뒤 수정한 내용이 이어지는 편이 좋습니다. "
                "말이 많은 학생만 유리하지 않도록 개별 작성물과 이해 확인, 다음 과제까지 같은 기준으로 평가하는지 확인하세요."
            ),
        )
    if context.keyword == "토론형수업":
        return (
            (
                f"{context.locality}에서 토론형수업을 살필 때는 주제에 대한 주장만이 아니라 교재·자료에서 찾은 근거, 발언 순서와 상대 의견에 대한 질문·반론을 확인해야 합니다. "
                "수업 전에 읽을 범위와 준비할 근거가 안내되고 발언하지 못한 학생도 기록으로 생각을 남길 수 있는지 물어보세요."
            ),
            (
                f"{context.locality} 학생의 토론 뒤에는 처음 주장과 수정한 생각, 새로 확인할 질문을 짧은 글이나 개념 설명으로 정리하는 편이 좋습니다. "
                "발언의 자신감만 평가하지 않고 근거의 정확성, 상대 의견 이해, 피드백 반영을 다음 학습에 연결하는지 살펴보세요."
            ),
        )
    if context.keyword == "클리닉수업":
        return (
            (
                f"{context.locality}에서 클리닉수업을 확인할 때는 먼저 어떤 시험지·과제·진단 문항으로 부족한 단원과 원인을 찾는지 살펴봐야 합니다. "
                "진단 결과가 개념 설명, 보완 문제, 학생의 재설명과 재풀이로 이어지는지 단계별로 물어보세요."
            ),
            (
                f"{context.locality} 학생의 보완이 끝났다는 기준은 수업 참여가 아니라 같은 개념을 도움 없이 설명하고 비슷한 문항을 다시 해결한 결과여야 합니다. "
                "재확인 날짜와 통과하지 못했을 때의 추가 보완, 정규 진도에 다시 연결하는 방법도 확인하세요."
            ),
        )
    if context.keyword in {"특강수업", "학원특강", "입시특강"}:
        return (
            (
                f"{context.locality}에서 {context.keyword}{particle(context.keyword, '을', '를')} 알아볼 때는 홍보 제목보다 시작·종료일, 대상 학년과 시작 수준, 다룰 주제와 단원, 총횟수를 먼저 확인해야 합니다. "
                "정규 수업과 겹치는 범위와 별도로 준비할 교재·과제, 결석 때의 보완 조건도 구분해 물어보세요."
            ),
            (
                f"{context.locality} 학생에게 맞는지는 기간 안에 끝낼 범위와 마지막에 확인할 결과물이 현재 일정에 들어가는지로 판단하는 편이 좋습니다. "
                "종료 뒤 개념 설명·재풀이·누적 복습 중 무엇으로 완료를 확인하고 다음 학습에 어떻게 이어지는지 살펴보세요."
            ),
        )
    if context.keyword == "학습교재관리":
        return (
            (
                f"{context.locality}에서 학습교재관리를 확인할 때는 교재 수보다 학교 진도·학생 수준·목표에 맞춰 각 교재를 선택한 이유와 사용할 순서를 물어봐야 합니다. "
                "단원별 계획 진도와 실제 완료, 이해·오답·질문 상태를 같은 기록에서 구분하는지도 살펴보세요."
            ),
            (
                f"{context.locality} 학생이 교재를 바꿀 때는 단순히 한 권을 끝냈는지가 아니라 핵심 개념 설명과 대표 유형 재풀이, 남은 공백을 기준으로 판단하는 편이 좋습니다. "
                "진도가 밀리거나 난도가 맞지 않을 때 유지·보완·교체를 결정하는 사람과 다음 확인일도 기록하세요."
            ),
        )
    if context.keyword == "자기주도학습":
        return (
            (
                f"{context.locality}에서 자기주도학습을 확인할 때는 학생이 목표와 완료 기준을 직접 말하고, 실행 순서를 정한 뒤 막힌 지점을 질문으로 남기는지 살펴봐야 합니다. "
                "처음부터 모든 결정을 맡기기보다 현재 기록을 함께 읽고 학생이 선택할 수 있는 범위를 단계적으로 넓히는 편이 현실적입니다."
            ),
            (
                f"{context.locality} 학생의 주간 기록에는 스스로 정한 목표, 실제 완료, 도움을 요청한 시점, 다시 바꿀 계획이 이어져야 합니다. "
                "담당자의 도움은 정답을 대신 주는 일이 아니라 점검 질문과 선택 기준을 제공하고, 학생이 혼자 점검할 수 있을수록 개입을 줄이는 방식인지 확인하세요."
            ),
        )
    if context.keyword == "일일학습점검":
        return (
            (
                f"{context.locality}에서 일일학습점검을 할 때는 그날 계획한 범위와 실제 완료, 남은 질문, 오답 수정 여부를 같은 기록에 남겨야 합니다. "
                "공부 시간만 합산하지 말고 멈춘 단계와 미완료 이유를 구분해야 다음 날 첫 행동을 구체적으로 정할 수 있습니다."
            ),
            (
                f"{context.locality} 학생은 하루가 끝날 때 가장 먼저 이어서 할 과제와 다시 풀 문제, 질문할 내용을 한 줄씩 정하는 편이 좋습니다. "
                "매일 같은 지표로 짧게 확인하되 하루의 결과만으로 성취를 단정하지 말고 주간 기록과 함께 해석하세요."
            ),
        )
    if context.keyword == "주간학습점검":
        return (
            (
                f"{context.locality}에서 주간학습점검을 진행할 때는 과목별 계획 대비 완료 범위, 반복된 오답, 질문 해결 상태와 이월 과제를 한 주 단위로 모아 봐야 합니다. "
                "하루의 성공·실패보다 여러 날에 걸쳐 같은 지점에서 멈췄는지를 확인하는 편이 중요합니다."
            ),
            (
                f"{context.locality} 학생의 다음 주 계획은 누적 완료량과 반복 오류를 바탕으로 유지할 과제, 줄일 분량, 먼저 보완할 단원을 구분해야 합니다. "
                "점검 결과가 단순 보고로 끝나지 않고 과목 우선순위와 복습 간격, 다음 확인일에 반영되는지 살펴보세요."
            ),
        )
    if context.keyword == "월간학습점검":
        return (
            (
                f"{context.locality}에서 월간학습점검을 할 때는 한 달의 총 공부 시간보다 주차별 완료 범위, 반복 오답, 질문과 재풀이 결과가 어떻게 변했는지 같은 기준으로 비교해야 합니다. "
                "월초에 세운 목표의 중간 지점과 실제 도달 범위를 구분해 일시적인 점수 변화에만 기대지 마세요."
            ),
            (
                f"{context.locality} 학생의 다음 달 목표는 이번 달에 안정된 행동과 계속 막힌 단원을 나눠 정하는 편이 좋습니다. "
                "유지할 습관, 보완할 과목, 확인할 평가와 날짜를 구체화하고 지난달과 같은 지표로 다시 비교할 수 있게 기록하세요."
            ),
        )
    if context.keyword == "정기학습점검":
        return (
            (
                f"{context.locality}에서 정기학습점검을 운영할 때는 매주·격주·시험 전후처럼 확인 간격과 추가 점검이 필요한 조건을 먼저 정해야 합니다. "
                "완료 범위, 오답 재풀이, 질문 해결, 계획 이월처럼 매번 같은 지표를 사용해야 시점별 변화를 비교할 수 있습니다."
            ),
            (
                f"{context.locality} 학생의 점검 주기는 학교 평가와 과제량, 계획 유지 상태에 따라 달라질 수 있습니다. "
                "정해진 날짜의 확인에 그치지 말고 반복 오류나 미완료가 기준을 넘으면 바로 조정하며, 결과를 다음 행동과 재확인일로 연결하세요."
            ),
        )
    if context.keyword == "녹화수업":
        return (
            (
                f"{context.locality}에서 녹화수업을 선택할 때는 영상 한 편의 길이와 전체 제공 기간, 배속·일시정지·이어보기 가능 여부를 먼저 확인해야 합니다. "
                "질문 제출 방법과 답변 시점, 시청 기한이 지난 뒤의 만료·재생 가능 조건도 실제 안내에서 구분해 살펴보세요."
            ),
            (
                f"{context.locality} 학생은 영상을 재생한 사실만으로 학습 완료로 처리하지 말고 핵심 내용을 설명하거나 확인 문제를 풀어 이해 여부를 남기는 편이 좋습니다. "
                "멈춘 구간과 질문, 재시청한 부분을 기록하고 그 결과가 과제와 다음 설명에 반영되는지 확인하세요."
            ),
        )
    if context.keyword == "내신성적":
        return (
            (
                f"{context.locality}에서 내신성적을 살필 때는 한 번의 등급이나 총점만 보지 말고 과목·단원·문항 유형별 결과와 이전 평가의 변화를 같은 기준으로 비교해야 합니다. "
                "원점수·등급·성취도처럼 실제 성적표에 제시된 항목과 시험 범위가 달라진 부분을 구분해 기록하세요."
            ),
            (
                f"{context.locality} 학생의 점수 변화는 시험 난도·범위·시간 배분·실수의 영향을 함께 받을 수 있습니다. "
                "오답이 생긴 원인과 맞혔지만 근거가 약한 문항을 나누고, 보완 단원·재풀이 날짜·다음 확인 기준으로 연결한 뒤 여러 평가의 기록을 보고 판단하는 편이 좋습니다."
            ),
        )
    if context.keyword == "내신분석":
        return (
            (
                f"{context.locality}에서 내신분석을 진행할 때는 실제 시험지와 학생 답안, 범위표, 교과서·학교 자료를 함께 펼쳐 문항별 출제 단원과 요구한 풀이를 대조해야 합니다. "
                "틀린 문항뿐 아니라 맞혔지만 추측했거나 풀이 근거가 불안한 문항도 따로 표시하세요."
            ),
            (
                f"{context.locality} 학생의 분석 기록에는 개념 부족·조건 해석·계산·표현·시간 배분을 구분하고 서술형 감점 기준과 재풀이 결과를 남기는 편이 좋습니다. "
                "일반적인 시험 일정 안내에 그치지 말고 실제 학교 자료에서 확인한 범위와 다음 보완 행동, 재확인 날짜가 연결되는지 살펴보세요."
            ),
        )
    if context.keyword == "개인별수업":
        return (
            (
                f"{context.locality}에서 개인별수업을 알아볼 때는 학생마다 목표·현재 수준·진도 속도를 어떤 자료로 구분하는지 확인해야 합니다. "
                "최근 시험지와 교재 진도, 질문 기록을 바탕으로 과목별 설명·과제·복습 범위가 달라지는지, 다음 점검일에 계획을 어떻게 조정하는지 살펴보세요."
            ),
            (
                f"{context.locality} 학부모는 명칭만 보고 일대일 수업이라고 단정하지 말고 실제 수업 인원과 학생별 설명 시간, 담당자, 피드백 방식을 확인하는 편이 좋습니다. "
                "같은 반에서도 학생별 목표와 완료 기록이 따로 남는지 상담 자료로 대조하세요."
            ),
        )
    if context.keyword == "시험오답":
        return (
            (
                f"{context.locality}에서 시험오답을 점검할 때는 틀린 번호만 모으지 말고 문제의 단원·유형과 개념 부족, 조건 해석, 계산·표현, 시간 배분 원인을 구분해야 합니다. "
                "학생이 정답 근거를 다시 설명하고 비슷한 문제를 재풀이할 날짜까지 정하는지 확인하세요."
            ),
            (
                f"{context.locality} 학생의 오답 기록은 시험 직후 정리에서 끝나지 않아야 합니다. "
                "교정 전후 답안과 반복된 원인을 다음 진도·과제에 반영하고, 재시험 결과를 기준으로 다시 볼 항목과 넘어갈 항목을 나누는 편이 좋습니다."
            ),
        )
    if context.keyword == "입시결과":
        return (
            (
                f"{context.locality}에서 입시결과를 확인할 때는 학교명이나 합격 문구만 보지 말고 자료의 작성 시점, 대상 인원, 전형과 학년, 집계 기준이 함께 제시되는지 살펴봐야 합니다. "
                "개별 사례인지 전체 통계인지와 확인 가능한 출처가 있는지도 구분하세요."
            ),
            (
                f"{context.locality} 학생에게 과거 결과를 그대로 대입해 합격 가능성을 단정해서는 안 됩니다. "
                "현재 성적·과목 선택·희망 전형과 당시 사례의 차이를 먼저 확인하고, 참고할 준비 과정과 지금 실행할 항목만 따로 기록하는 편이 안전합니다."
            ),
        )
    if context.keyword == "입시진단":
        return (
            (
                f"{context.locality}에서 입시진단을 알아볼 때는 어떤 자료를 입력하고 어떤 판단 근거와 실행 항목을 돌려받는지 확인해야 합니다. "
                "최근 내신·모의평가, 과목 선택, 희망 계열과 학교 활동을 함께 살피는지, 결과가 과목 우선순위와 준비 일정으로 연결되는지 질문하세요."
            ),
            (
                f"{context.locality} 학부모는 진단표의 등급이나 결론만 보지 말고 자료 기준일과 빠진 정보, 다시 확인할 시점을 기록하는 편이 좋습니다. "
                "진단은 현재 준비 방향을 정리하는 참고 자료이며 특정 대학이나 전형의 결과를 보장하지 않습니다."
            ),
        )
    if context.keyword in {"입시성공전략", "입시합격관리", "입시합격전략"}:
        return (
            (
                f"{context.locality}에서 {context.keyword}{particle(context.keyword, '을', '를')} 알아볼 때는 성공·합격이라는 표현보다 현재 학생 자료와 목표 전형을 연결한 실행 계획이 있는지 확인해야 합니다. "
                "최근 성적과 과목 선택, 희망 계열, 준비 시기를 기준으로 이번 달 과제와 다음 점검일이 구체적으로 제시되는지 살펴보세요."
            ),
            (
                f"{context.locality} 학생은 과거 합격 사례의 결론보다 당시 조건·작성 시점·실행 과정을 현재 상황과 구분해 봐야 합니다. "
                "새 성적이나 공식 일정이 나오면 우선순위와 준비 계획을 다시 조정하고, 어떤 전략도 특정 결과를 미리 보장하는 것으로 해석하지 마세요."
            ),
        )
    if context.keyword in {"시험분석", "시험성적", "시험성적관리"}:
        return (
            (
                f"{context.locality}에서 {context.keyword}{particle(context.keyword, '을', '를')} 확인할 때는 총점만 보지 말고 과목·단원·문항 유형별 결과와 오답 원인을 나누어야 합니다. "
                "최근 답안에서 맞힌 과정과 막힌 과정, 시간 부족과 실수를 구분하고 이전 시험과 같은 기준으로 비교하는지 살펴보세요."
            ),
            (
                f"{context.locality} 학생의 결과 기록은 점수 보관에서 끝나지 않고 다음 개념 복습·재풀이·시간 연습으로 이어져야 합니다. "
                "시험 범위와 난도가 달랐던 경우에는 단순 점수 차이를 향상이나 하락으로 단정하지 말고, 비교 조건과 다음 점검일을 함께 남기세요."
            ),
        )
    if context.keyword == "학습개선":
        return (
            (
                f"{context.locality}에서 학습개선을 확인하려면 시작 전 상태와 바꾼 행동, 이후 결과를 같은 기준으로 비교해야 합니다. "
                "과목별 완료 범위·오답 원인·질문 횟수처럼 확인 가능한 항목을 정하고, 어떤 설명·과제·복습 조정이 있었는지 기록하세요."
            ),
            (
                f"{context.locality} 학생은 한 번의 점수 변화만으로 개선 여부를 판단하기보다 여러 주의 실행 기록과 재풀이 결과를 함께 보는 편이 좋습니다. "
                "효과가 없었던 방법도 남겨 다음 계획에서 분량·순서·도움 요청 시점을 조정하세요."
            ),
        )
    if context.keyword == "학습결과":
        return (
            (
                f"{context.locality}에서 학습결과를 살필 때는 공부 시간뿐 아니라 끝낸 범위, 설명할 수 있는 개념, 재풀이 정답과 남은 질문을 함께 확인해야 합니다. "
                "계획 대비 완료량과 과목별 산출물이 같은 기간 기준으로 기록되는지 살펴보세요."
            ),
            (
                f"{context.locality} 학생의 결과는 시험 난도와 범위, 시작 수준에 따라 해석이 달라질 수 있습니다. "
                "단일 점수로 성장을 단정하지 말고 기록의 변화와 반복되는 어려움을 다음 과제·복습·상담 계획에 연결하세요."
            ),
        )
    if context.keyword in {"학습관리", "학습관리반", "학습관리수업"}:
        return (
            (
                f"{context.locality}에서 {context.keyword}{particle(context.keyword, '을', '를')} 알아볼 때는 진단·계획·실행 확인·오답 재학습·계획 수정이 한 흐름으로 이어지는지 살펴봐야 합니다. "
                "학생별 목표와 담당자, 확인 주기, 미완료 때의 조정 방법이 시간표와 기록에 구체적으로 제시되는지 질문하세요."
            ),
            (
                f"{context.locality} 학부모는 수업 시간과 별도로 계획 점검·질문·피드백에 쓰는 시간이 있는지 확인하는 편이 좋습니다. "
                "반 이름만으로 관리 범위를 판단하지 말고 실제 인원, 사용하는 자료, 학생과 보호자가 확인할 수 있는 기록을 대조하세요."
            ),
        )
    if context.keyword == "학습관리표":
        return (
            (
                f"{context.locality}에서 학습관리표를 확인할 때는 날짜와 공부 시간만 적는지, 목표 범위·실제 완료·오답·질문·조정 사유까지 남기는지 살펴봐야 합니다. "
                "과목별 계획과 결과가 같은 칸에서 비교되고 다음 수업의 행동으로 연결되는지 확인하세요."
            ),
            (
                f"{context.locality} 학생에게 맞는 표는 항목이 많은 표보다 매일 실제로 기록하고 주간 단위로 다시 볼 수 있는 표입니다. "
                "누가 언제 확인하는지와 미완료 항목을 옮기는 규칙, 보호자에게 공유되는 범위를 상담에서 구체적으로 물어보세요."
            ),
        )
    if context.keyword in {"과제관리반", "과제관리수업"}:
        return (
            (
                f"{context.locality}에서 {context.keyword}{particle(context.keyword, '을', '를')} 비교할 때는 과제량보다 배정·제출·확인·수정의 흐름을 살펴봐야 합니다. "
                "학생 수준에 맞춘 완료 기준, 미제출 사유, 틀린 문제의 재풀이와 다음 수업 반영 방법이 기록되는지 확인하세요."
            ),
            (
                f"{context.locality} 학부모는 과제를 대신 끝내게 하는 관리인지 학생이 스스로 계획하고 도움을 요청하게 하는 관리인지 구분하는 편이 좋습니다. "
                "실제 수업 인원과 점검 시간, 담당자, 과제 조정 기준을 상담 자료로 대조하세요."
            ),
        )
    if context.keyword in {"동기관리반", "습관관리반", "집중력관리반"}:
        return (
            (
                f"{context.locality}에서 {context.keyword}{particle(context.keyword, '을', '를')} 알아볼 때는 의지를 평가하기보다 시작을 돕는 신호와 반복 가능한 행동을 어떻게 설계하는지 확인해야 합니다. "
                "과제 시작 시각·완료 범위·집중 구간·도움 요청 시점을 기록하고 매주 한 가지 행동을 조정하는지 살펴보세요."
            ),
            (
                f"{context.locality} 학생에게는 벌점이나 막연한 격려보다 실패한 날 다시 시작할 수 있는 작은 규칙이 필요합니다. "
                "학생 상태에 따라 휴식·분량·환경을 조정하는 기준과 담당자의 확인 주기, 보호자에게 공유할 범위를 구분해 물어보세요."
            ),
        )
    if context.keyword == "반복수업":
        return (
            (
                f"{context.locality}에서 반복수업을 확인할 때는 같은 설명이나 문제를 되풀이하는지보다 일정 간격 뒤 학생이 스스로 개념을 떠올리고 적용하는지 살펴봐야 합니다. "
                "첫 학습·짧은 확인·유형 재풀이·누적 점검의 시점과 통과 기준이 있는지 질문하세요."
            ),
            (
                f"{context.locality} 학생의 반복 범위는 이미 아는 내용과 계속 막히는 내용을 구분해 조정하는 편이 좋습니다. "
                "정답 암기에 그치지 않도록 설명 과정과 변형 문제 결과를 기록하고, 통과한 항목은 간격을 늘려 다시 확인하세요."
            ),
        )
    if context.keyword in {"오답관리반", "오답관리수업"}:
        return (
            (
                f"{context.locality}에서 {context.keyword}{particle(context.keyword, '을', '를')} 확인할 때는 오답을 베끼는지보다 원인 분류·교정·재풀이·누적 확인이 이어지는지 살펴봐야 합니다. "
                "개념 부족, 조건 해석, 계산·표현, 시간 배분을 구분하고 다음 재시험 날짜와 통과 기준을 기록하는지 질문하세요."
            ),
            (
                f"{context.locality} 학부모는 실제 수업에서 오답 점검에 쓰는 시간과 담당자, 사용하는 시험지·교재·기록표를 확인하는 편이 좋습니다. "
                "학생이 정답 근거를 다시 설명하고 비슷한 문제에서 같은 원인이 줄었는지까지 대조하세요."
            ),
        )
    if context.keyword in {"진도관리반", "진도관리수업"}:
        return (
            (
                f"{context.locality}에서 {context.keyword}{particle(context.keyword, '을', '를')} 알아볼 때는 교재 쪽수보다 계획 진도와 실제 이해·완료 상태를 함께 확인해야 합니다. "
                "학교 범위와 선행 목표, 필수 복습을 구분하고 미완료나 오답이 쌓일 때 진도 속도를 어떻게 조정하는지 살펴보세요."
            ),
            (
                f"{context.locality} 학생의 진도 기록에는 학습 날짜, 완료 범위, 질문과 재학습 항목, 다음 확인일이 남아야 합니다. "
                "반 이름이나 목표 진도만 보지 말고 실제 수업 인원·담당자·점검 주기와 이해 확인 기준을 상담에서 대조하세요."
            ),
        )
    if context.keyword in {"플래너관리반", "플래너관리수업"}:
        return (
            (
                f"{context.locality}에서 {context.keyword}{particle(context.keyword, '을', '를')} 확인할 때는 계획표 작성보다 실행 결과와 수정 과정을 점검하는지 살펴봐야 합니다. "
                "학교 일정·과목 우선순위·완료 범위를 배치하고, 미완료 사유와 옮길 날짜를 기록하는지 질문하세요."
            ),
            (
                f"{context.locality} 학생에게는 매일 다시 쓸 수 있는 크기의 계획과 주간 검토 시간이 필요합니다. "
                "누가 플래너를 확인하는지, 학생이 스스로 설명하는지, 과도한 분량이나 반복 지연을 어떤 규칙으로 조정하는지 상담에서 확인하세요."
            ),
        )
    if context.keyword == "학습심화":
        return (
            (
                f"{context.locality}에서 학습심화를 진행할 때는 어려운 문제 수를 늘리기 전에 필수 개념과 기본 적용이 안정됐는지 확인해야 합니다. "
                "새 조건이 붙은 문제에서 개념을 선택한 이유와 풀이 과정을 설명하고, 막힌 지점을 보완한 뒤 다른 유형으로 옮기는지 살펴보세요."
            ),
            (
                f"{context.locality} 학생의 심화 범위는 현재 학교 진도와 과목별 목표, 남아 있는 기초 공백을 함께 고려해 조정하는 편이 좋습니다. "
                "정답률만 보지 말고 설명·비교·변형 적용이 가능한지와 다시 확인할 시점을 기록하세요."
            ),
        )
    if context.keyword == "학습예습":
        return (
            (
                f"{context.locality}에서 학습예습을 할 때는 앞으로 배울 단원의 핵심 용어와 기본 구조를 미리 익혀 학교 수업에서 질문할 지점을 만드는 데 초점을 두세요. "
                "선행 분량을 크게 잡기보다 개념 훑기·기본 예제·모르는 부분 표시까지 완료하는지 확인해야 합니다."
            ),
            (
                f"{context.locality} 학생의 예습은 이미 배운 내용을 다시 푸는 복습과 구분해 기록하는 편이 좋습니다. "
                "학교 진도와 달라질 수 있는 범위를 확인하고, 수업 뒤에는 예측이 맞았던 부분과 새로 이해한 내용을 짧게 정리하세요."
            ),
        )
    if context.keyword == "학습응용":
        return (
            (
                f"{context.locality}에서 학습응용을 확인할 때는 익힌 풀이를 그대로 반복하는지보다 조건이 달라진 문제에서 필요한 개념을 선택하고 연결하는지 살펴봐야 합니다. "
                "학생이 조건 변화와 풀이 근거를 말로 설명하고 두 가지 접근을 비교하는 과정이 있는지 질문하세요."
            ),
            (
                f"{context.locality} 학생은 기본 개념과 대표 유형을 통과한 뒤 변형 문제로 이동하는 편이 좋습니다. "
                "틀렸을 때는 답만 고치지 말고 어떤 조건을 놓쳤는지 기록하고, 유사하지만 다른 문제에서 스스로 적용되는지 다시 확인하세요."
            ),
        )
    if context.keyword == "학습시간관리":
        return (
            (
                f"{context.locality}에서 학습시간관리를 할 때는 공부 시간을 늘리기보다 학교·수업·이동처럼 고정된 일정과 과목별 우선순위를 먼저 배치해야 합니다. "
                "각 시간대에 끝낼 범위와 집중 구간, 휴식, 미완료 항목을 옮길 여유 시간이 계획에 있는지 확인하세요."
            ),
            (
                f"{context.locality} 학생은 예정 시간과 실제 사용 시간을 비교해 방해 요인과 과도한 계획을 찾는 편이 좋습니다. "
                "시험이나 학교 행사로 일정이 달라지면 우선순위·분량·다음 점검일을 함께 조정하세요."
            ),
        )
    if context.keyword == "학습오답관리":
        return (
            (
                f"{context.locality}에서 학습오답관리를 할 때는 틀린 문제의 정답을 옮기기보다 개념·조건 해석·계산·표현·시간 배분 원인을 구분해야 합니다. "
                "교정한 풀이와 학생의 설명, 비슷한 문제를 다시 풀 날짜와 통과 기준이 함께 남는지 확인하세요."
            ),
            (
                f"{context.locality} 학생은 같은 원인이 여러 교재와 시험에서 반복되는지 주간 단위로 대조하는 편이 좋습니다. "
                "통과한 항목과 다시 볼 항목을 나누고 결과를 다음 진도·과제·질문 계획에 반영하세요."
            ),
        )
    if context.keyword == "학습진도관리":
        return (
            (
                f"{context.locality}에서 학습진도관리를 할 때는 계획한 교재 범위와 실제 완료·이해·재학습 상태를 분리해 기록해야 합니다. "
                "학교 범위와 선행 목표, 필수 복습을 구분하고 오답이나 미완료가 쌓일 때 속도를 조정하는 기준이 있는지 확인하세요."
            ),
            (
                f"{context.locality} 학생의 진도표에는 날짜·단원·완료 기준·남은 질문·다음 확인일이 함께 있어야 합니다. "
                "쪽수를 빠르게 넘기는 것을 성과로 단정하지 말고 설명과 재풀이 결과를 기준으로 다음 범위를 정하세요."
            ),
        )
    if context.keyword == "학습진척도":
        return (
            (
                f"{context.locality}에서 학습진척도를 확인할 때는 계획량 대비 실제 완료 범위와 개념 설명, 오답 재풀이, 질문 해결 상태를 같은 기간 기준으로 비교해야 합니다. "
                "단원별 시작점과 현재 상태, 미완료 사유가 기록되는지 살펴보세요."
            ),
            (
                f"{context.locality} 학생의 진척은 공부 시간이나 교재 쪽수만으로 판단하기 어렵습니다. "
                "학교 일정과 난도 변화를 고려하고, 느려진 항목은 분량·순서·도움 요청 시점을 조정해 다음 점검일에 다시 대조하세요."
            ),
        )
    if context.keyword == "학습통계":
        return (
            (
                f"{context.locality}에서 학습통계를 볼 때는 공부 시간, 완료 문항, 정답률, 오답 원인, 질문처럼 각 수치의 정의와 집계 기간을 먼저 확인해야 합니다. "
                "같은 기준으로 기록된 값인지와 누락된 날·과목이 있는지 살펴보세요."
            ),
            (
                f"{context.locality} 학생의 수치는 순위를 매기기보다 반복되는 패턴을 찾아 다음 계획을 조정하는 데 쓰는 편이 좋습니다. "
                "표본이 적거나 시험 범위가 다른 경우에는 단순 증가·감소를 성과로 단정하지 말고 원자료와 함께 해석하세요."
            ),
        )
    if context.keyword == "학습훈련":
        return (
            (
                f"{context.locality}에서 학습훈련을 확인할 때는 문제량보다 학생이 스스로 시작하고 설명하고 검토하는 행동을 반복하는지 살펴봐야 합니다. "
                "짧은 목표·실행·즉시 확인·간격 재시도의 순서와 통과 기준이 실제 수업에 있는지 질문하세요."
            ),
            (
                f"{context.locality} 학생에게 필요한 훈련은 과목과 어려움에 따라 달라집니다. "
                "처음에는 도움을 제공하되 점차 질문과 검토를 학생이 맡도록 조정하고, 반복 횟수보다 독립적으로 완료한 결과를 기록하세요."
            ),
        )
    if context.keyword == "학원브랜드":
        return (
            (
                f"{context.locality}에서 학원브랜드를 비교할 때는 이름이나 이미지보다 교육 원칙이 실제 수업·교재·학생 관리에 일관되게 적용되는지 확인해야 합니다. "
                "지점별 담당자와 수업 방식, 기록·상담 절차가 어디까지 공통이고 무엇이 달라지는지 살펴보세요."
            ),
            (
                f"{context.locality} 학부모는 인지도나 홍보 문구만으로 수업 품질을 단정하지 말고 학생에게 적용될 반·강사·교재·점검 방법을 자료로 확인하는 편이 좋습니다. "
                "브랜드 안내와 실제 계약·상담 내용이 다르면 적용 조건을 다시 질문하세요."
            ),
        )
    if context.keyword == "학원교재":
        return (
            (
                f"{context.locality}에서 학원교재를 확인할 때는 책의 수보다 학교 진도와 학생 수준, 목표에 맞춰 어떤 기준으로 선택하는지 살펴봐야 합니다. "
                "교재명·단원·사용 시기와 기본·응용·오답 보완 자료의 역할이 실제 계획에 제시되는지 질문하세요."
            ),
            (
                f"{context.locality} 학생에게는 한 권을 끝내는 기준과 다음 자료로 넘어가는 조건이 필요합니다. "
                "학교별 자료나 별도 프린트가 있다면 출처와 사용 범위, 미완료·오답을 다시 보는 방법도 함께 확인하세요."
            ),
        )
    if context.keyword == "학원교재실":
        return (
            (
                f"{context.locality}에서 학원교재실을 확인할 때는 교재를 과목·학년·과정·사용 상태별로 어떻게 분류하고 찾는지부터 살펴봐야 합니다. "
                "학생에게 배부하거나 빌려주는 자료의 대여일·반납일·담당자와 분실·훼손 때의 확인 절차가 기록되는지 물어보세요."
            ),
            (
                f"{context.locality} 학부모는 학생이 사용할 교재의 이름과 범위, 개인 소유인지 대여 자료인지, 보관 장소와 반납 조건을 구분해 확인하는 편이 좋습니다. "
                "재고와 최신 판본을 점검하는 주기, 사용이 끝난 교재의 회수·폐기 방법도 실제 안내와 기록에서 대조하세요."
            ),
        )
    if context.keyword == "학원사물함":
        return (
            (
                f"{context.locality}에서 학원사물함을 확인할 때는 배정 대상과 사용 기간, 크기, 위치, 잠금 방식과 열쇠·비밀번호 관리 방법을 먼저 물어봐야 합니다. "
                "교재와 개인 물품 중 보관 가능한 항목, 분실·파손이나 잠금 오류가 생겼을 때의 신고·확인 절차도 살펴보세요."
            ),
            (
                f"{context.locality} 학생은 사물함 번호와 배정·반납일을 기록하고 귀중품처럼 보관이 제한되는 물품을 구분하는 편이 좋습니다. "
                "이용 기간이 끝나거나 반을 옮길 때 남은 물품을 확인하는 방법, 미반납 열쇠와 장기 보관 물품의 처리 안내도 등록 전에 확인하세요."
            ),
        )
    if context.keyword == "학원상담실":
        return (
            (
                f"{context.locality}에서 학원상담실을 확인할 때는 대화 내용이 불필요하게 노출되지 않는 공간인지와 예약 시간, 참석자, 상담 목적을 먼저 구분해야 합니다. "
                "학생이 함께 참여하는 구간과 보호자만 확인할 내용을 나누고, 상담 중 사용할 성적표·시험지·질문 목록을 미리 안내하는지 살펴보세요."
            ),
            (
                f"{context.locality} 학부모는 상담 뒤 남기는 기록의 항목과 열람 담당자, 보관·수정·문의 방법을 확인하는 편이 좋습니다. "
                "성적·연락처 등 개인정보는 상담 목적에 필요한 범위로 다루는지 묻고, 다음 실행 항목과 확인일은 학생에게 전달할 내용과 구분해 기록하세요."
            ),
        )
    if context.keyword == "학원자료실":
        return (
            (
                f"{context.locality}에서 학원자료실을 확인할 때는 종이 교재·프린트가 있는 물리 공간인지, 파일을 보는 온라인 공간인지부터 구분해야 합니다. "
                "이용 가능한 자료 종류와 대상 학년·과목, 접근 권한과 이용 시간, 검색·열람·다운로드 또는 대여·반납 방법을 실제 안내에서 살펴보세요."
            ),
            (
                f"{context.locality} 학생은 자료의 출처·적용 범위·판본 또는 수정일을 확인하고, 현재 수업과 연결된 자료만 사용하는 편이 좋습니다. "
                "개인별 답안처럼 개인정보가 포함된 자료의 접근 범위와 보관 방법, 오래된 파일·교재를 교체하는 기준도 함께 확인하세요."
            ),
        )
    if context.keyword == "학원출결앱":
        return (
            (
                f"{context.locality}에서 학원출결앱을 확인할 때는 등원·하원 시각을 누가 어떤 방식으로 입력하고 학생·보호자에게 언제 알리는지 살펴봐야 합니다. "
                "지각·조퇴·결석과 입력 누락을 구분하고, 잘못된 기록의 수정 요청·확인 담당자·변경 이력이 안내되는지 물어보세요."
            ),
            (
                f"{context.locality} 학부모는 실시간 알림의 수신 대상과 실패했을 때의 대체 연락 방법, 학생·보호자·담당자의 열람 권한을 확인하는 편이 좋습니다. "
                "출결 정보의 수집 목적과 보관·열람·수정 문의 방법도 확인하되, 앱 알림만으로 학생의 실제 위치나 안전을 단정하지 마세요."
            ),
        )
    if context.keyword == "학원휴게실":
        return (
            (
                f"{context.locality}에서 학원휴게실을 확인할 때는 수업 사이에 쉬는 공간이라는 목적에 맞게 이용 대상과 가능한 시간, 음식·음료 규칙을 먼저 살펴봐야 합니다. "
                "교실과 소음이 분리되는지, 혼잡 시간과 좌석 이용 방법, 청결 점검과 불편·안전 문제를 알리는 담당자가 안내되는지 물어보세요."
            ),
            (
                f"{context.locality} 학생은 휴식 시간을 지나치게 늘리거나 다음 수업을 놓치지 않도록 이용 종료 시각과 복귀 방법을 확인하는 편이 좋습니다. "
                "휴게실을 자습 공간으로 전제하지 말고 실제 운영 목적과 보관 제한 물품, 이용 뒤 정리 기준이 수업 일정과 맞는지 살펴보세요."
            ),
        )
    if context.keyword == "학원주차":
        return (
            (
                f"{context.locality}에서 학원주차를 확인할 때는 건물 주차장인지 인근 제휴·공영 주차장인지와 정확한 진입 위치부터 구분해야 합니다. "
                "이용 가능한 요일·시간과 혼잡 시간, 주차 가능 대수처럼 달라질 수 있는 조건을 등록 전 최신 안내에서 다시 물어보세요."
            ),
            (
                f"{context.locality} 학부모는 무료·유료 여부와 기본 시간·추가 요금, 차량 등록이나 할인 확인 방법을 실제 안내에서 살펴보는 편이 좋습니다. "
                "학생 승하차 구역과 보호자 단기 대기 가능 여부, 만차나 운영 변경 때 이용할 대체 위치와 연락 방법도 함께 확인하세요."
            ),
        )
    if context.keyword == "학원데이터관리":
        return (
            (
                f"{context.locality}에서 학원데이터관리를 확인할 때는 출결·진도·과제·오답·상담·결제 중 어떤 정보를 왜 기록하는지 먼저 구분해야 합니다. "
                "입력 담당자와 확인 주기, 학생 계획을 조정할 때 쓰는 항목, 오류를 고치는 절차가 안내되어 있는지 살펴보세요."
            ),
            (
                f"{context.locality} 학부모는 학생·보호자 정보의 접근 권한과 보관 기간, 열람·수정·삭제 요청 방법을 함께 확인하는 편이 좋습니다. "
                "통계나 자동화 기능보다 원자료의 정확성과 개인정보 안내, 담당 변경 때 기록이 이어지는지를 먼저 대조하세요."
            ),
        )
    if context.keyword in {"학원결제시스템", "학원미납관리", "학원수납관리"}:
        return (
            (
                f"{context.locality}에서 {context.keyword}{particle(context.keyword, '을', '를')} 운영 관점으로 확인할 때는 청구·결제·수납·미납·환불 상태가 같은 기준으로 연결되는지 살펴봐야 합니다. "
                "수강 항목과 금액, 처리일, 영수증, 수정 이력과 담당자가 자료에서 대조되는지 확인하세요."
            ),
            (
                f"{context.locality} 운영자는 보호자에게 보이는 안내와 내부 정산 기록을 구분하고, 결제 오류·부분 납부·환불처럼 예외 상황의 처리 절차를 확인하는 편이 좋습니다. "
                "학생별 결제 정보의 접근 권한과 보관 범위도 함께 정하되 교육 성과와 매출 정보를 혼동하지 마세요."
            ),
        )
    if context.keyword in {"학원고객관리", "학원고객관리시스템", "학원회원관리", "학원수강생관리"}:
        return (
            (
                f"{context.locality}에서 {context.keyword}{particle(context.keyword, '을', '를')} 운영 관점으로 검토할 때는 상담 문의·등록·출결·수업·연락 기록이 어떤 목적으로 연결되는지 확인해야 합니다. "
                "중복 정보와 변경 이력을 정리하고 담당자가 필요한 항목만 열람할 수 있는지 살펴보세요."
            ),
            (
                f"{context.locality} 운영자는 학생과 보호자 정보를 단순 명단으로 모으기보다 상담 후속 조치와 수업 지원에 필요한 범위를 구분하는 편이 좋습니다. "
                "수집 목적·동의·보관 기간·열람·수정 요청 절차와 담당 변경 때의 인계 기준을 함께 확인하세요."
            ),
        )
    if context.keyword in {"학원관리솔루션", "학원관리앱", "학원관리프로그램"}:
        return (
            (
                f"{context.locality}에서 {context.keyword}{particle(context.keyword, '을', '를')} 비교할 때는 기능 수보다 출결·수납·상담·학습 기록 중 실제 필요한 업무가 연결되는지 확인해야 합니다. "
                "사용자별 권한, 자료 입력·수정, 내보내기와 백업, 오류 문의 방법을 실제 화면과 안내에서 살펴보세요."
            ),
            (
                f"{context.locality} 운영자는 자동 알림이나 통계가 원자료와 맞는지, 기존 기록을 옮길 수 있는지, 서비스 변경 때 자료를 돌려받을 수 있는지 확인하는 편이 좋습니다. "
                "학생·보호자 정보의 보관 위치와 접근 범위도 계약 전에 구체적으로 질문하세요."
            ),
        )
    if context.keyword == "학원문서관리":
        return (
            (
                f"{context.locality}에서 학원문서관리를 점검할 때는 계약·동의·수업·상담·결제 문서를 종류와 보관 기간별로 구분해야 합니다. "
                "최신본과 수정 이력, 작성·열람 담당자, 필요한 때 검색하고 사본을 제공하는 절차가 있는지 확인하세요."
            ),
            (
                f"{context.locality} 운영자는 종이와 전자 문서가 중복되거나 서로 다른 내용을 담지 않도록 기준본을 정하는 편이 좋습니다. "
                "개인정보가 포함된 자료의 접근·폐기·오류 수정 방법과 담당 변경 때의 인계 기록도 함께 살펴보세요."
            ),
        )
    if context.keyword == "학원상담관리":
        return (
            (
                f"{context.locality}에서 학원상담관리를 확인할 때는 문의 접수·상담 준비·답변·후속 확인이 하나의 기록으로 이어지는지 살펴봐야 합니다. "
                "학생 목표와 현재 자료, 질문, 안내한 수업·비용·일정, 다음 연락일과 담당자가 구분되어 있는지 확인하세요."
            ),
            (
                f"{context.locality} 운영자는 상담 내용을 과도하게 수집하지 말고 수업 판단과 후속 안내에 필요한 범위를 정하는 편이 좋습니다. "
                "담당자가 바뀌어도 답변이 달라지지 않도록 근거 자료와 변경 이력을 남기고, 학생·보호자 정보의 접근 범위도 확인하세요."
            ),
        )
    if context.keyword in {"학원운영", "학원행정"}:
        return (
            (
                f"{context.locality}에서 {context.keyword}{particle(context.keyword, '을', '를')} 살필 때는 수업 외 업무를 등록·출결·시간표·수납·상담·안전·개인정보로 나누고 담당자와 확인 주기를 정해야 합니다. "
                "각 기록이 최신 안내와 일치하고 예외 상황의 처리 절차가 문서로 남는지 확인하세요."
            ),
            (
                f"{context.locality} 운영자는 업무 효율만이 아니라 학생 수업이 중단되지 않도록 담당 변경과 자료 인계, 보호자 연락 기준을 함께 설계하는 편이 좋습니다. "
                "법령·행정 요건처럼 달라질 수 있는 내용은 관할 기관의 최신 공식 안내에서 별도로 확인하세요."
            ),
        )
    if context.keyword in {
        "녹화수업", "실시간수업", "온라인수업", "화상수업",
        "학원실시간수업", "학원온라인수업", "학원화상수업",
    }:
        return (
            (
                f"{context.locality}에서 {context.keyword}{particle(context.keyword, '을', '를')} 알아볼 때는 접속 방식과 수업 시간, 질문·답변이 이루어지는 방법을 먼저 확인해야 합니다. "
                "영상 제공 기간, 출석·과제·피드백 기준, 접속 장애나 결석 때의 대체 절차가 실제 안내에 제시되는지 살펴보세요."
            ),
            (
                f"{context.locality} 학생은 기기·인터넷 환경과 혼자 학습 가능한 시간, 필요한 교재를 미리 점검하는 편이 좋습니다. "
                "시청이나 접속만으로 완료 처리되는지, 이해 확인과 질문 기록이 다음 수업에 어떻게 반영되는지도 구분해 물어보세요."
            ),
        )
    if context.keyword in {"단기집중반", "방학집중반", "방학특강", "주말집중반", "평일집중반", "장기관리반", "학원집중반"}:
        return (
            (
                f"{context.locality}에서 {context.keyword}{particle(context.keyword, '을', '를')} 확인할 때는 운영 기간과 대상 학년·과목, 시작 수준, 기간 안에 끝낼 범위를 구체적으로 살펴봐야 합니다. "
                "수업 요일·시간·총횟수와 과제·결석·보강 기준, 종료 뒤 이어질 복습 계획이 안내되는지 확인하세요."
            ),
            (
                f"{context.locality} 학생은 짧거나 긴 기간이라는 이름보다 학교 일정과 기존 학습량에 실제로 들어갈 수 있는지 계산하는 편이 좋습니다. "
                "수업 전 진단과 중간 점검, 종료 시 확인할 결과물을 정하고 과도한 진도나 성과를 미리 단정하지 마세요."
            ),
        )
    if context.keyword in {"보강수업", "학원보강"}:
        return (
            (
                f"{context.locality}에서 {context.keyword}{particle(context.keyword, '을', '를')} 확인할 때는 결석한 정규 수업을 언제·어떤 방식으로 보완하는지와 신청 조건을 살펴봐야 합니다. "
                "가능한 요일·시간, 담당자, 동일 진도 제공 여부, 과제와 출결 처리, 변경·취소 절차가 안내되는지 확인하세요."
            ),
            (
                f"{context.locality} 학부모는 보강 가능 여부를 모든 상황에 적용된다고 단정하지 말고 결석 사유와 신청 시점별 예외를 물어보는 편이 좋습니다. "
                "실제 보완한 범위와 남은 질문이 다음 정규 수업에 이어지는지도 기록으로 대조하세요."
            ),
        )
    if context.keyword in {"보충수업", "학원보충"}:
        return (
            (
                f"{context.locality}에서 {context.keyword}{particle(context.keyword, '을', '를')} 알아볼 때는 결석 보강과 구분해 개념·단원별 부족과 취약한 문제 유형 가운데 무엇을 추가로 다루는지 확인해야 합니다. "
                "대상 선정 기준과 수업 시간·인원·교재, 이해 확인과 종료 기준이 실제 안내에 제시되는지 살펴보세요."
            ),
            (
                f"{context.locality} 학생에게는 많이 남는 수업보다 부족한 지점과 끝낼 목표가 분명한 보충이 필요합니다. "
                "추가 수업 뒤 학생 설명과 재풀이 결과를 확인하고 정규 진도·과제량을 어떻게 조정할지도 함께 물어보세요."
            ),
        )
    if context.keyword in {"야간수업", "오전수업", "오후수업", "주말수업", "평일수업"}:
        return (
            (
                f"{context.locality}에서 {context.keyword}{particle(context.keyword, '을', '를')} 알아볼 때는 실제 운영 요일과 시작·종료 시각, 대상 학년·과목, 확정 가능한 반을 확인해야 합니다. "
                "학교·이동·식사·귀가와 복습 시간을 함께 계산하고 지각·결석·공휴일 때의 변경·보강 기준을 살펴보세요."
            ),
            (
                f"{context.locality} 학생에게 맞는 시간대는 신청 가능 여부뿐 아니라 집중 상태와 수면·학교 일정이 지속 가능한지를 함께 봐야 합니다. "
                "시간표는 달라질 수 있으므로 등록 전 확정 시각과 담당자, 변경 연락 방법을 최신 안내에서 다시 확인하세요."
            ),
        )
    if context.keyword == "예약제수업":
        return (
            (
                f"{context.locality}에서 예약제수업을 확인할 때는 예약 가능한 수업과 대상, 신청·확정 시점, 수업 시간과 장소를 구분해야 합니다. "
                "준비할 교재·자료, 담당자, 변경·취소·지각·결석 때의 처리 기준이 안내되는지 살펴보세요."
            ),
            (
                f"{context.locality} 학부모는 신청을 보낸 것과 수업이 확정된 것을 따로 확인하는 편이 좋습니다. "
                "학생의 학교 일정과 이동 시간을 대조하고, 예약 변경 뒤 새 시간과 준비 항목을 같은 연락 수단에서 다시 확인하세요."
            ),
        )
    if context.keyword in {"자기주도반", "자기주도수업"}:
        return (
            (
                f"{context.locality}에서 {context.keyword}{particle(context.keyword, '을', '를')} 알아볼 때는 학생에게 공부를 맡겨 두는지보다 목표 설정·실행·질문·검토를 스스로 하도록 어떤 지원을 제공하는지 확인해야 합니다. "
                "초기 진단과 주간 계획, 담당자의 개입 기준과 점차 도움을 줄이는 과정이 있는지 살펴보세요."
            ),
            (
                f"{context.locality} 학생에게 필요한 자율 범위는 현재 습관과 과목 난도에 따라 달라집니다. "
                "완료 기록과 오답·질문을 학생이 설명하게 하고, 계획이 무너졌을 때 다시 시작하는 규칙과 보호자 공유 범위를 구분해 확인하세요."
            ),
        )
    if context.keyword in {"학습성과", "학습성취도", "학습완성도", "학습향상", "학습효율", "학습성장력"}:
        return (
            (
                f"{context.locality}에서 {context.keyword}{particle(context.keyword, '을', '를')} 확인할 때는 단일 점수나 공부 시간보다 시작점과 목표, 완료 범위, 개념 설명, 오답 재풀이 같은 지표를 같은 기간 기준으로 비교해야 합니다. "
                "어떤 자료로 측정했고 누락되거나 조건이 달라진 부분이 있는지 살펴보세요."
            ),
            (
                f"{context.locality} 학생의 변화는 과목 난도와 시험 범위, 학교 일정에 따라 다르게 나타날 수 있습니다. "
                "수치만으로 향상이나 효율을 단정하지 말고 바뀐 학습 행동과 남은 어려움, 다음 조정 항목을 함께 기록하세요."
            ),
        )
    if context.keyword == "학습성과표":
        return (
            (
                f"{context.locality}에서 학습성과표를 확인할 때는 목표·시작점·실행 기록·완료 결과와 측정 기간이 한눈에 구분되는지 살펴봐야 합니다. "
                "과목별 진도와 오답 재풀이, 질문 해결, 계획 대비 완료 범위가 근거 자료와 연결되는지 확인하세요."
            ),
            (
                f"{context.locality} 학생의 표는 좋은 결과만 모으기보다 미완료와 반복된 어려움, 조정한 방법도 함께 보여 주는 편이 좋습니다. "
                "시험 범위와 난도가 다른 수치를 단순 비교하지 말고 다음 계획에 쓸 항목을 구체적으로 표시하세요."
            ),
        )
    if context.keyword == "학습포트폴리오":
        return (
            (
                f"{context.locality}에서 학습포트폴리오를 만들 때는 결과물만 모으지 말고 목표·과정·수정·최종 결과와 작성 날짜를 함께 남겨야 합니다. "
                "시험지·과제·오답 교정·발표나 글쓰기 자료가 학생의 설명과 다음 목표로 연결되는지 확인하세요."
            ),
            (
                f"{context.locality} 학생은 대표 자료를 고른 이유와 전후 차이를 직접 설명하는 편이 좋습니다. "
                "개인정보와 학교 자료의 공유 범위를 확인하고, 포트폴리오 자체가 성적이나 입시 결과를 보장하는 것으로 해석하지 마세요."
            ),
        )
    if context.keyword == "학습체크리스트":
        return (
            (
                f"{context.locality}에서 학습체크리스트를 사용할 때는 출석 여부보다 과목별 완료 범위·오답 재풀이·질문·복습과 다음 행동을 확인할 수 있어야 합니다. "
                "완료 기준과 점검 시점, 학생과 담당자의 확인 칸이 구분되어 있는지 살펴보세요."
            ),
            (
                f"{context.locality} 학생에게는 항목이 많은 목록보다 매일 실제로 확인할 수 있는 짧은 목록이 적합합니다. "
                "체크되지 않은 항목의 원인과 옮길 날짜를 기록하고, 주간 점검에서 불필요한 항목을 줄이거나 순서를 조정하세요."
            ),
        )
    if context.keyword in {"학원과제", "학원숙제"}:
        return (
            (
                f"{context.locality}에서 {context.keyword}{particle(context.keyword, '을', '를')} 확인할 때는 양보다 과목·단원·완료 기준과 제출 시점, 수업에서 배운 내용과의 연결을 살펴봐야 합니다. "
                "학생 수준에 따라 분량을 조정하고 미완료·오답을 누가 언제 확인하는지 질문하세요."
            ),
            (
                f"{context.locality} 학생은 답을 채우는 데서 끝내지 말고 어려웠던 문제와 도움받은 부분, 다시 풀 항목을 표시하는 편이 좋습니다. "
                "학교 일정과 다른 과목 부담을 고려해 과도한 분량을 조정하고 결과가 다음 수업에 반영되는지 확인하세요."
            ),
        )
    if context.keyword in {"학원설명회", "학원오리엔테이션"}:
        return (
            (
                f"{context.locality}에서 {context.keyword}{particle(context.keyword, '을', '를')} 알아볼 때는 대상 학년·참석자와 날짜·장소, 다루는 주제, 진행 순서를 먼저 확인해야 합니다. "
                "수업·교재·시간표·비용·학생 관리 중 무엇을 안내하고 개별 질문이나 후속 상담을 어떻게 받는지 살펴보세요."
            ),
            (
                f"{context.locality} 학부모는 공통 안내와 학생에게 실제 적용될 조건을 구분해 기록하는 편이 좋습니다. "
                "참석 전 질문과 준비 자료를 정하고, 종료 뒤 담당자·확정 일정·추가 확인 항목을 최신 안내에서 다시 대조하세요."
            ),
        )
    if context.keyword == "학원결제관리":
        return (
            (
                f"{context.locality}에서 학원결제관리를 확인할 때는 보호자 안내와 운영자 정산의 두 관점을 구분해야 합니다. "
                "수강 항목·금액·결제일·영수증·할인·환불·미납 상태와 수정 이력이 같은 자료에서 대조되는지 살펴보세요."
            ),
            (
                f"{context.locality} 학부모는 실제 청구 내용과 결제·환불 조건을 확인하고, 운영자는 예외 처리와 월별 정산 기준을 확인하는 편이 좋습니다. "
                "학생별 결제 정보의 접근·보관 범위와 문의 담당자도 함께 구분하세요."
            ),
        )
    if context.keyword == "학원관리":
        return (
            (
                f"{context.locality}에서 학원관리를 알아볼 때는 학생 학습관리와 운영 행정 가운데 무엇을 뜻하는지 먼저 구분해야 합니다. "
                "학습 측면은 진도·과제·오답·상담 기록을, 운영 측면은 출결·시간표·수납·안전·개인정보의 담당자와 절차를 확인하세요."
            ),
            (
                f"{context.locality} 학부모는 학생에게 적용될 수업·기록·연락 범위를 확인하고, 운영자는 자료 정확성과 인계·예외 처리 기준을 별도로 살펴보는 편이 좋습니다. "
                "명칭만으로 제공 기능이나 책임 범위를 단정하지 마세요."
            ),
        )
    if context.keyword in {"학원데스크", "학원매니저", "학원상담직원", "학원직원", "학원코디네이터"}:
        return (
            (
                f"{context.locality}에서 {context.keyword}{particle(context.keyword, '을', '를')} 검색할 때는 채용·직무 정보와 학부모가 확인하려는 담당자 역할을 구분해야 합니다. "
                "이 페이지에서는 상담·출결·시간표·비용 문의와 수업 담당자 연결이 누구의 책임인지, 답변·인계 절차가 있는지를 확인합니다."
            ),
            (
                f"{context.locality} 학부모는 직함만으로 권한을 판단하지 말고 문의 유형별 담당자와 연락 방법, 답변 시점을 기록하는 편이 좋습니다. "
                "구직자는 근무 조건이나 채용 여부를 이 페이지에서 추정하지 말고 해당 기관의 최신 공식 채용 공고를 별도로 확인해야 합니다."
            ),
        )
    if context.keyword == "학원프로그램":
        return (
            (
                f"{context.locality}에서 학원프로그램을 알아볼 때는 수업 과정과 운영 소프트웨어 가운데 어떤 의미인지 먼저 구분해야 합니다. "
                "수업 과정이라면 대상·과목·기간·교재·관리 흐름을, 소프트웨어라면 출결·수납·상담·학습 기록 기능과 권한·자료 보관을 확인하세요."
            ),
            (
                f"{context.locality} 학부모는 학생에게 실제 적용될 수업 내용과 시간표를 확인하고, 운영자는 필요한 업무와 자료 이동·백업·오류 지원 조건을 별도로 살펴보는 편이 좋습니다. "
                "명칭만으로 커리큘럼이나 시스템 기능을 단정하지 마세요."
            ),
        )
    if context.keyword == "학습피드백":
        return (
            (
                f"{context.locality}에서 학습피드백을 확인할 때는 칭찬이나 평가 문구보다 학생이 무엇을 끝냈고 "
                "어디에서 막혔는지, 다음에 무엇을 고칠지가 구체적으로 남는지 살펴봐야 합니다. "
                "① 완료·미완료 범위, ② 오답 원인과 다시 풀 항목, ③ 다음 수업 전 실행할 과제가 "
                "교재·시험지·학습 기록과 연결되는지 확인하세요."
            ),
            (
                f"{context.locality} 학부모는 누가 어떤 자료를 보고 의견을 남기는지와 전달 주기를 함께 확인하는 편이 좋습니다. "
                "학생이 실제로 수정한 내용과 다음 점검일을 기록하고, 같은 어려움이 반복될 때는 과제량·설명 방식·복습 순서를 "
                "어떻게 조정할지 상담에서 구체적으로 정하세요."
            ),
        )
    if context.keyword in {"입시일정관리", "입시일정"}:
        return (
            (
                f"{context.locality}에서 {context.keyword}{particle(context.keyword, '을', '를')} 확인할 때는 공식 안내를 기준으로 "
                "지원·전형·시험·결과 발표 일정을 구분해 정리하는지가 중요합니다. ① 일정의 확인 출처와 기준일, ② 학생이 준비할 서류와 과제, "
                "③ 변경 여부를 다시 확인할 시점이 실제 계획에 제시되는지 살펴보세요."
            ),
            (
                f"{context.locality} 학생은 마감일만 달력에 적기보다 준비 시작일과 중간 점검일을 함께 두는 편이 좋습니다. "
                "학교·대학·전형별 안내가 달라질 수 있으므로 확정되지 않은 날짜를 단정하지 말고, 최신 공지와 학생의 선택을 "
                "대조해 일정표를 갱신하세요."
            ),
        )
    if context.keyword == "학원시간표":
        return (
            (
                f"{context.locality}에서 학원시간표를 확인할 때는 수업 요일과 시작 시각뿐 아니라 수업 길이, 담당 과목, "
                "변경·보강 기준까지 함께 살펴봐야 합니다. ① 학교 수업과 이동 시간, ② 자습·과제에 필요한 시간, "
                "③ 결석이나 공휴일 때 적용되는 절차가 실제 안내에 제시되는지 확인하세요."
            ),
            (
                f"{context.locality} 학생에게 맞는 시간표는 빈 시간을 모두 채우기보다 학교 일정과 식사·휴식, 복습 시간을 "
                "유지할 수 있어야 합니다. 등록 전에는 가능한 반과 확정 시각을 다시 확인하고, 일정이 바뀌면 보강 가능 여부와 "
                "새로운 학습 흐름을 함께 조정하세요."
            ),
        )
    if context.keyword == "학습시간표":
        return (
            (
                f"{context.locality}에서 학습시간표를 세울 때는 학교·수업처럼 바꾸기 어려운 시간을 먼저 표시한 뒤 "
                "과목 우선순위와 완료 기준을 배치하는 편이 좋습니다. ① 당일 진도와 과제, ② 오답·암기 복습, "
                "③ 밀린 일을 옮길 여유 시간이 주간 계획에 포함되어 있는지 확인하세요."
            ),
            (
                f"{context.locality} 학생은 공부 시간을 길게 적는 것보다 각 시간대에 끝낼 자료와 범위를 구체적으로 정해야 합니다. "
                "실행 여부를 매일 표시하고 시험·학교 행사로 계획이 달라지면 과목 순서와 분량을 다시 배치해, 미완료 항목이 "
                "다음 주까지 이유 없이 누적되지 않도록 점검하세요."
            ),
        )
    if context.keyword == "시험일정관리":
        return (
            (
                f"{context.locality}에서 시험일정관리를 할 때는 학교가 안내한 시험일과 범위, 수행평가 일정을 먼저 확인해야 합니다. "
                "① 공식 안내를 확인한 날짜, ② 과목별 범위와 준비 상태, ③ 시험 전 개념·문제 풀이·오답 점검 시점을 "
                "역순으로 배치했는지 살펴보세요."
            ),
            (
                f"{context.locality} 학생은 시험 날짜만 기록하지 말고 범위가 확정되기 전후의 계획을 구분하는 편이 좋습니다. "
                "학교 공지가 바뀌면 일정표와 학습 분량을 함께 수정하고, 수행평가와 다른 과목 준비가 겹치는 주에는 "
                "여유 시간을 두어 미완료 항목을 재배치하세요."
            ),
        )
    if context.keyword == "학습일정관리":
        return (
            (
                f"{context.locality}에서 학습일정관리를 할 때는 주간 계획과 월간 목표를 학교 일정·시험·과제와 연결해야 합니다. "
                "① 반드시 끝낼 과목별 범위, ② 복습과 오답 점검 시점, ③ 예상보다 늦어졌을 때 옮길 수 있는 여유 시간이 "
                "계획표에 구분되어 있는지 확인하세요."
            ),
            (
                f"{context.locality} 학생은 계획한 시간보다 실제 완료한 범위를 기준으로 다음 일정을 조정하는 편이 좋습니다. "
                "매주 미완료 원인을 확인해 분량·순서·도움 요청 시점을 바꾸고, 학교 행사나 시험 일정이 달라지면 "
                "우선순위와 점검일도 함께 갱신하세요."
            ),
        )
    if context.keyword == "학원전자계약":
        return (
            (
                f"{context.locality}에서 학원전자계약을 확인할 때는 서명 방식보다 계약 내용과 동의 범위를 먼저 읽어야 합니다. "
                "① 수업 과목·기간·시간과 비용, ② 환불·결석·보강·변경 조건, ③ 개인정보 수집과 전자문서 사본 제공 방법이 "
                "화면과 안내문에 일치하는지 살펴보세요."
            ),
            (
                f"{context.locality} 학부모는 서명 전에 선택 동의와 필수 동의를 구분하고, 계약 완료 뒤 열람할 수 있는 사본을 보관하는 편이 좋습니다. "
                "수업이나 비용 조건이 달라질 때의 수정 절차와 해지·문의 창구도 확인하되, 구체적인 법적 효력은 해당 계약과 "
                "최신 공식 안내를 기준으로 판단하세요."
            ),
        )
    if context.keyword == "학원예약관리":
        return (
            (
                f"{context.locality}에서 학원예약관리를 확인할 때는 상담·진단·수업 가운데 무엇을 예약했는지와 확정 상태를 구분해야 합니다. "
                "① 날짜·시간·장소와 담당자, ② 준비할 성적표·시험지·질문 목록, ③ 변경·취소·재확인 방법이 "
                "문자나 예약 화면에 분명히 안내되는지 살펴보세요."
            ),
            (
                f"{context.locality} 학부모는 신청을 보낸 시점과 예약이 확정된 시점을 따로 기록하는 편이 좋습니다. "
                "방문 전날에는 대상 학생과 상담 목적, 준비 자료를 다시 대조하고, 일정이 달라지면 변경 결과와 새 확정 시간을 "
                "같은 연락 수단에서 확인하세요."
            ),
        )
    if context.keyword == "학원매출관리":
        return (
            (
                f"{context.locality}에서 학원매출관리를 점검할 때는 등록 인원만 보지 말고 청구·수납·할인·환불을 구분해 "
                "같은 기간 기준으로 대조해야 합니다. ① 수강 항목별 청구와 실제 입금, ② 미수·환불·보강에 따른 조정, "
                "③ 영수증과 정산 기록의 일치 여부를 확인하세요."
            ),
            (
                f"{context.locality} 운영자는 학생별 결제 정보에 필요한 접근 권한과 보관 범위를 정하고, 월별 집계와 개별 거래 기록이 "
                "서로 맞는지 정기적으로 살펴보는 편이 좋습니다. 매출 수치만으로 교육 성과를 해석하지 말고, 오류가 발견되면 "
                "근거 문서와 수정 이력을 함께 남기세요."
            ),
        )
    if context.keyword == "입시설계":
        return (
            (
                f"{context.locality}에서 입시설계를 알아볼 때 핵심은 희망 진로와 현재 성적, "
                "과목 선택, 준비 시기를 하나의 실행 계획으로 연결하는지입니다. "
                "상담에서는 ① 최근 내신·모의평가와 과목별 강약점, ② 희망 계열과 선택 과목, "
                "③ 학기·방학·지원 시기별 점검 항목이 실제 자료에 제시되는지 확인해야 합니다."
            ),
            (
                f"{context.locality} 학부모는 해당 계획의 결론만 듣기보다 판단에 사용한 자료와 "
                "다음 확인 시점을 함께 기록하세요. 학생의 희망이 바뀌거나 새 성적이 나온 경우에는 "
                "과목 우선순위와 준비 일정을 다시 조정하되 특정 결과를 미리 단정하지 않는 편이 안전합니다."
            ),
        )
    if context.keyword == "입시설명회":
        return (
            (
                f"{context.locality}에서 입시설명회를 알아볼 때 핵심은 발표 내용이 학생의 학년, "
                "현재 자료, 준비 일정과 어떻게 연결되는지입니다. "
                "설명회 전후에는 ① 대상 학년과 다루는 주제, ② 안내의 근거 자료와 변경 가능성, "
                "③ 이후 개별 확인과 실행 계획 방법이 실제 자료에 제시되는지 확인해야 합니다."
            ),
            (
                f"{context.locality} 학생은 설명회에서 들은 공통 정보를 자신의 성적표·과목 선택·학교 일정과 "
                "구분해 정리하는 편이 좋습니다. 설명회가 끝난 뒤에는 추가로 확인할 질문과 다음 주에 실행할 "
                "한 가지 행동을 남겨 정보가 듣는 데서 끝나지 않도록 하세요."
            ),
        )
    if context.keyword == "입시상담예약":
        return (
            (
                f"{context.locality}에서 입시상담예약을 알아볼 때 핵심은 상담 목적과 준비 자료, 가능한 일정, "
                "예약 확인 방법이 분명한지입니다. 예약 전에는 ① 학생 학년과 상담 주제, "
                "② 가져갈 성적표·시험지·과목 선택 자료, ③ 확정 일정과 변경·취소 절차를 실제 안내에서 확인하세요."
            ),
            (
                f"{context.locality} 학부모는 상담 예약을 마친 뒤 질문 목록과 준비 자료를 한곳에 모아 두는 편이 좋습니다. "
                "상담이 끝나면 답변을 학생의 현재 일정과 대조해 다음 확인일과 실행 항목을 기록하되, "
                "상담만으로 특정 입시 결과가 보장된다고 판단하지 마세요."
            ),
        )
    if context.keyword == "학원개원":
        return (
            (
                f"{context.locality}의 학원개원 검색에는 새로 문을 연 학원을 찾는 학부모 의도와 직접 개원을 준비하는 운영자 의도가 함께 섞일 수 있습니다. "
                "학부모라면 실제 수업 시작일, 가능한 학년·과목과 시간표, 담당자·교재·진단 자료, 결석·보강 절차를 현재 안내에서 확인하세요."
            ),
            (
                f"{context.locality}에서 운영자가 개원을 준비한다면 대상 학년·과목과 수업 계획, 강사·교재·학생 관리 흐름, "
                "수강료·환불·안전·개인정보 안내를 자료로 구체화해야 합니다. 등록·시설 등 행정 요건과 승인 여부는 관할 기관의 최신 공식 안내에서 별도로 확인하고, "
                "학부모는 개원 초기 홍보 문구보다 첫 수업 뒤 진도·질문·오답 관리가 안내대로 이어지는지를 다시 살펴보세요."
            ),
        )
    if context.keyword == "학원방역관리":
        return (
            (
                f"{context.locality}에서 학원방역관리를 알아볼 때는 막연히 안전하다는 표현보다 실제 안내와 대응 절차를 확인해야 합니다. "
                "상담에서는 ① 환기·공용 공간 관리 주기, ② 감염 의심 증상이 있을 때의 등원·연락 기준, "
                "③ 수업 변경이나 결석 처리 안내를 어떤 방식으로 제공하는지 물어보세요."
            ),
            (
                f"{context.locality} 학부모는 방역 안내의 제공 범위와 담당자, 확인 가능한 기록, 예외 상황을 구분해 적는 편이 좋습니다. "
                "학생의 학교 일정과 건강 상태가 달라질 수 있으므로 실제 적용 여부와 최신 안내는 등록 전과 변경 시점에 다시 확인하세요."
            ),
        )
    if context.keyword == "학원청결관리":
        return (
            (
                f"{context.locality}에서 학원청결관리를 확인할 때는 시설이 깔끔해 보이는지만 판단하지 말고 실제 관리 범위를 질문해야 합니다. "
                "① 교실·책상·공용 물품의 관리 주기, ② 환기와 화장실·휴게 공간 점검, "
                "③ 불편 사항을 전달하고 조치 결과를 확인하는 방법이 안내되어 있는지 살펴보세요."
            ),
            (
                f"{context.locality} 학부모는 청결 안내의 담당자와 점검 시점, 확인 가능한 자료를 기록해 두는 편이 좋습니다. "
                "학생이 오래 머무는 요일을 기준으로 실제 이용 공간과 관리 상태를 살피고, 달라질 수 있는 운영 조건은 상담에서 다시 확인하세요."
            ),
        )
    if context.keyword == "학원개인정보관리":
        return (
            (
                f"{context.locality}에서 학원개인정보관리를 확인할 때는 어떤 정보를 왜 수집하고 누가 접근하는지부터 물어보는 편이 좋습니다. "
                "① 학생·보호자 정보의 수집 목적과 항목, ② 보관 기간과 열람·수정 요청 방법, "
                "③ 문자·앱·사진 등 전달 수단별 동의와 철회 절차가 실제 안내에 제시되는지 확인하세요."
            ),
            (
                f"{context.locality} 학부모는 개인정보 안내를 등록 서류와 연락 수단별로 나누어 살펴보세요. "
                "필수 정보와 선택 정보를 구분하고, 제3자 제공이나 홍보 활용처럼 별도 확인이 필요한 항목은 동의 범위와 문의 창구를 기록해 두는 편이 안전합니다."
            ),
        )
    if context.keyword == "학원창업":
        return (
            (
                f"{context.locality}에서 학원창업 정보를 살필 때는 개원 문구보다 실제 교육·운영 준비 항목을 구체적으로 나누어야 합니다. "
                "① 대상 학년·과목과 수업 계획, ② 강사·교재·학생 관리 흐름, ③ 수강료·환불·안전·개인정보 안내를 "
                "어떤 자료로 준비했는지 확인하고, 행정 요건은 관할 기관의 최신 안내를 별도로 확인하세요."
            ),
            (
                f"{context.locality}의 창업 계획은 학생 모집보다 수업 품질과 운영 책임을 지속할 수 있는지 먼저 점검하는 편이 좋습니다. "
                "초기 시간표와 상담 기록, 결석·보강 절차를 실제 상황에 대입해 보고, 확인되지 않은 비용·성과·승인 여부는 단정하지 마세요."
            ),
        )
    if context.keyword == "학원운영자":
        return (
            (
                f"{context.locality}에서 학원운영자를 확인할 때는 직함보다 교육과 운영 책임이 어떻게 나뉘는지 질문해야 합니다. "
                "① 수업·교재·진도 결정 담당자, ② 출결·보강·비용 문의 담당자, "
                "③ 학습 기록과 보호자 상담을 최종 확인하는 사람이 실제 안내에 제시되는지 살펴보세요."
            ),
            (
                f"{context.locality} 학부모는 운영 책임자와 강사·상담 담당자의 역할을 구분하고, 문의 유형별 연락 방법과 답변 시점을 기록해 두는 편이 좋습니다. "
                "담당자가 바뀌는 경우에도 학생의 진도·질문·오답 기록이 이어지는지 첫 점검일에 다시 확인하세요."
            ),
        )
    if context.keyword == "학원일정":
        return (
            (
                f"{context.locality}에서 학원일정을 확인할 때는 정규 수업일과 휴강·공휴일, 시험 대비·특강 일정을 한 달력에서 구분해야 합니다. "
                "각 일정의 대상 학년·과목과 시작·종료 시각, 처음 안내한 날짜와 최종 확정 시점이 표시되는지 살펴보세요."
            ),
            (
                f"{context.locality} 학생의 학교 행사나 시험 일정과 겹칠 때는 변경·보강 여부와 새 확정 시간을 같은 연락 수단에서 다시 확인하는 편이 좋습니다. "
                "일정 변경을 누가 언제 알리는지와 학생 계획표·보호자 안내가 함께 갱신되는지도 기록하세요."
            ),
        )
    if context.keyword == "학원온라인등록":
        return (
            (
                f"{context.locality}에서 학원온라인등록을 할 때는 공식 신청 경로와 입력 항목, 제출할 학생 자료, 필수·선택 동의 범위를 먼저 확인해야 합니다. "
                "결제가 포함되는 경우에는 수강 항목·금액·영수증과 오류 문의 방법이 신청 화면의 안내와 일치하는지 살펴보세요."
            ),
            (
                f"{context.locality} 학부모는 신청서를 보낸 ‘접수’와 반·시간표까지 정해진 ‘등록 확정’을 구분하는 편이 좋습니다. "
                "누락·중복·결제 오류의 수정 창구와 확정 통보 방법, 제출한 개인정보의 열람·수정 문의 방법도 함께 확인하세요."
            ),
        )
    if context.keyword == "학원재등록":
        return (
            (
                f"{context.locality}에서 학원재등록을 검토할 때는 기존 진도·과제·오답·질문 기록과 다음 기간의 목표를 먼저 대조해야 합니다. "
                "계속할 과목·반과 바꿀 진도, 새 시간표·담당자·교재가 이전 조건과 어떻게 달라지는지 자료에서 확인하세요."
            ),
            (
                f"{context.locality} 학부모는 재등록 신청·확정 기한과 다음 기간의 비용, 환불·결석·보강 등 변경된 안내를 다시 읽는 편이 좋습니다. "
                "자동으로 같은 조건이 이어진다고 가정하지 말고 기존 기록을 근거로 유지·변경·종료를 판단한 뒤 확정 내용을 보관하세요."
            ),
        )
    if context.keyword in {"학원문자발송", "학원알림톡"}:
        return (
            (
                f"{context.locality}에서 {context.keyword}{particle(context.keyword, '을', '를')} 운영할 때는 안내 목적별 수신 대상과 동의·수신 거부 상태를 먼저 구분해야 합니다. "
                "발신 주체와 연락처, 즉시·예약 발송 시점, 같은 내용을 중복 전송하지 않는 확인 절차가 있는지 살펴보세요."
            ),
            (
                f"{context.locality} 운영자는 발송 실패·번호 오류·미수신을 확인하고 필요한 경우에만 재발송하거나 다른 연락 수단을 사용하는 편이 좋습니다. "
                "성적·상담처럼 민감할 수 있는 정보는 전달 목적에 필요한 범위로 줄이고 열람 대상과 문의·수정 방법을 안내하세요."
            ),
        )
    if context.keyword == "시험시간관리":
        return (
            (
                f"{context.locality}에서 시험시간관리를 점검할 때는 전체 시간만 재지 말고 문항·영역별 목표 시간과 막힌 문항에서 넘어갈 기준을 정해야 합니다. "
                "답안 마킹과 서술형 작성, 마지막 검토에 남길 시간을 실제 시험 순서에 맞춰 배분해 보세요."
            ),
            (
                f"{context.locality} 학생은 시간 부족이 개념·조건 해석·계산·문항 집착·검토 누락 중 어디에서 생겼는지 기록하는 편이 좋습니다. "
                "같은 범위와 난도의 연습에서 배분표를 다시 적용하고 완료 문항 수·정확도·검토 시간을 함께 재측정하세요."
            ),
        )
    if context.keyword in {"학습성과관리", "학습성적관리"}:
        return (
            (
                f"{context.locality}에서 {context.keyword}{particle(context.keyword, '을', '를')} 확인할 때는 시작 시점과 비교 기간을 정하고 과목·단원·문항 유형별 완료와 오답 원인을 같은 기준으로 기록해야 합니다. "
                "점수뿐 아니라 개념 설명, 독립 풀이, 재풀이 통과처럼 실제 학습 결과를 보여 주는 자료도 함께 살펴보세요."
            ),
            (
                f"{context.locality} 학생의 변화는 시험 범위·난도·평가 방식이 다른 결과를 그대로 비교하지 않는 편이 안전합니다. "
                "조건이 비슷한 자료에서 달라진 점과 아직 남은 공백을 구분하고 다음 복습 범위·재풀이 날짜·확인 기준으로 연결하세요."
            ),
        )
    if context.keyword == "학원출결":
        return (
            (
                f"{context.locality}에서 학원출결을 확인할 때는 등원·하원 시각의 입력 방법과 지각·조퇴·결석·기록 누락을 어떻게 구분하는지 살펴봐야 합니다. "
                "학생·보호자에게 통보하는 시점과 담당자, 연락이 닿지 않을 때의 확인 방법이 안내되는지 물어보세요."
            ),
            (
                f"{context.locality} 학부모는 잘못된 출결 기록의 수정 요청과 변경 이력, 결석 수업의 과제·보강 연결 방법을 확인하는 편이 좋습니다. "
                "출결 기록만으로 학생의 학습 상태를 단정하지 말고 실제 수업 참여와 보완한 범위를 함께 대조하세요."
            ),
        )
    return ()


def special_keyword_faq_answer(context: Context) -> str:
    if context.keyword == "자기주도학습":
        return (
            f"{context.locality}에서는 자기주도학습을 단순히 혼자 공부하는 방식으로 보지 마세요. "
            "학생이 목표와 완료 기준을 정하고 실행·질문·자기 점검 기록을 남기며, 담당자는 그 능력이 자리 잡을수록 도움을 단계적으로 줄이는지 확인하는 편이 좋습니다."
        )
    if context.keyword == "일일학습점검":
        return (
            f"{context.locality}에서는 일일학습점검에 그날의 계획·실제 완료·질문·오답 수정·미완료 이유를 남기세요. "
            "하루 결과를 다음 날 첫 과제와 재풀이, 질문 행동으로 연결하되 한 번의 기록만으로 성취를 단정하지 않는 편이 좋습니다."
        )
    if context.keyword == "주간학습점검":
        return (
            f"{context.locality}에서는 주간학습점검으로 과목별 누적 완료 범위, 반복 오답, 질문 해결과 이월 과제를 비교하세요. "
            "결과를 다음 주의 과목 우선순위·분량·복습 간격과 재확인일에 반영하는 편이 좋습니다."
        )
    if context.keyword == "월간학습점검":
        return (
            f"{context.locality}에서는 월간학습점검으로 주차별 완료 범위와 반복 오답, 질문·재풀이 결과의 추세를 비교하세요. "
            "이번 달의 안정된 행동과 남은 공백을 나눠 다음 달 목표·보완 과목·확인 날짜를 정하는 편이 좋습니다."
        )
    if context.keyword == "정기학습점검":
        return (
            f"{context.locality}에서는 정기학습점검의 기본 간격과 시험·반복 미완료처럼 추가 확인을 여는 조건을 함께 정하세요. "
            "매번 같은 완료·오답·질문·이월 지표를 사용하고 결과를 다음 행동과 재확인일로 연결하는 편이 좋습니다."
        )
    if context.keyword == "녹화수업":
        return (
            f"{context.locality}에서는 녹화수업의 영상 길이·제공 기간·배속·이어보기와 만료 뒤 재생 조건을 확인하세요. "
            "질문 제출·답변 시점과 이해 확인 문제, 재시청 기록이 과제와 다음 설명에 반영되는지도 함께 살펴보는 편이 좋습니다."
        )
    if context.keyword in {"수준별수업", "학원수준별수업"}:
        return (
            f"{context.locality}에서는 {context.keyword}의 첫 배치 자료와 단원별 통과 기준을 확인하세요. "
            "일정 기간의 완료 범위·독립 풀이·질문·재풀이 결과로 반을 유지하거나 바꾸는지, 변경 뒤 진도 공백을 어떻게 보완하는지도 살펴보는 편이 좋습니다."
        )
    if context.keyword in {
        "개별지도", "학원개별지도", "개인별수업",
        "맞춤수업", "학원맞춤수업",
    }:
        return (
            f"{context.locality}에서는 {context.keyword}의 수업 인원과 질문·설명 시간, 최근 시험지·교재·오답을 바탕으로 정한 학생별 시작 진도와 연습 범위를 확인하세요. "
            "완료·질문·재풀이 결과에 따라 과제와 진도를 조정하는지, 결석·미완료·이해 부족 때의 보완과 다음 점검일도 함께 살펴보는 편이 좋습니다."
        )
    if context.keyword in {"일대일수업", "학원일대일"}:
        return (
            f"{context.locality}에서는 {context.keyword}의 실제 수업 인원과 한 학생에게 배정되는 설명·질문·풀이 확인 시간을 먼저 확인하세요. "
            "담당자와 진도·과제·오답 기록이 학생별로 이어지는지, 결석이나 이해 부족 때의 보완 방식과 다음 확인일도 함께 살펴보는 편이 좋습니다."
        )
    if context.keyword in {"소수정예수업", "학원소수정예"}:
        return (
            f"{context.locality}에서는 {context.keyword}의 최대·평균 인원과 같은 시간에 학생별 진도와 질문을 어떻게 나누는지 확인하세요. "
            "개별 설명·풀이 점검 순서와 대기 시간, 진도 차이가 커질 때의 조정·보완 기준도 실제 운영 안내에서 살펴보는 편이 좋습니다."
        )
    if context.keyword == "참여형수업":
        return (
            f"{context.locality}에서는 참여형수업의 참여를 발언 횟수만으로 판단하지 마세요. "
            "학생이 남긴 설명·질문·풀이·요약과 피드백 뒤 수정 결과, 다음 과제가 같은 기준으로 확인되는지 살펴보는 편이 좋습니다."
        )
    if context.keyword == "토론형수업":
        return (
            f"{context.locality}에서는 토론형수업 전에 준비할 근거와 발언·질문·반론 기준을 확인하세요. "
            "수업 뒤 처음 주장과 수정한 생각, 남은 질문을 기록하고 근거의 정확성과 상대 의견 이해를 다음 학습에 반영하는지도 살펴보는 편이 좋습니다."
        )
    if context.keyword == "클리닉수업":
        return (
            f"{context.locality}에서는 클리닉수업이 시험지·과제·진단 문항으로 원인을 찾고 개념 보완, 학생 설명과 재풀이로 이어지는지 확인하세요. "
            "재확인 날짜와 통과 기준, 추가 보완 뒤 정규 진도에 연결하는 방법도 함께 살펴보는 편이 좋습니다."
        )
    if context.keyword in {"특강수업", "학원특강", "입시특강"}:
        return (
            f"{context.locality}에서는 {context.keyword}의 기간·대상·시작 수준·주제·단원·총횟수와 완료 범위를 확인하세요. "
            "정규 수업과 겹치는 내용, 결석 보완, 종료 뒤 설명·재풀이·누적 복습 결과가 다음 학습으로 이어지는지도 살펴보는 편이 좋습니다."
        )
    if context.keyword == "학습교재관리":
        return (
            f"{context.locality}에서는 학습교재관리에서 학교 진도·수준·목표에 맞춘 선택 이유와 교재별 순서를 확인하세요. "
            "계획 진도와 실제 이해·오답·질문을 기록하고 개념 설명·대표 유형 재풀이 결과로 유지·보완·교체를 결정하는지 살펴보는 편이 좋습니다."
        )
    if context.keyword == "내신성적":
        return (
            f"{context.locality}에서는 내신성적을 한 번의 총점으로 판단하지 말고 과목·단원·문항 유형과 시험 범위를 같은 기준으로 비교하세요. "
            "점수 변화의 원인을 오답·시간 배분·실수로 나누고 보완 단원, 재풀이 날짜, 다음 확인 기준으로 연결하는 편이 좋습니다."
        )
    if context.keyword == "내신분석":
        return (
            f"{context.locality}에서는 실제 시험지와 학생 답안, 범위표, 교과서·학교 자료를 함께 대조하세요. "
            "틀린 문항과 근거가 약한 정답을 구분하고 개념·조건 해석·계산·표현·시간 배분 원인, 서술형 감점과 재풀이 결과까지 기록하는 편이 좋습니다."
        )
    if context.keyword == "개인별수업":
        return (
            f"{context.locality}에서는 개인별수업이 학생의 목표·현재 수준·진도 속도에 따라 설명·과제·복습 범위를 달리하는지 확인하세요. "
            "실제 수업 인원과 학생별 설명 시간, 담당자, 기록·피드백 방식도 함께 대조하는 편이 좋습니다."
        )
    if context.keyword == "시험오답":
        return (
            f"{context.locality}에서는 시험오답을 단원·유형과 개념 부족·조건 해석·계산·표현·시간 배분 원인으로 나누세요. "
            "교정한 답안과 정답 근거 설명, 비슷한 문제의 재풀이 날짜와 결과가 다음 계획에 반영되는지도 확인하는 편이 좋습니다."
        )
    if context.keyword == "입시결과":
        return (
            f"{context.locality}에서는 입시결과 자료의 작성 시점·대상 인원·전형·학년·집계 기준과 출처를 먼저 확인하세요. "
            "과거 사례를 현재 학생에게 그대로 대입하거나 합격 가능성으로 단정하지 말고 참고할 준비 과정만 구분하는 편이 안전합니다."
        )
    if context.keyword == "입시진단":
        return (
            f"{context.locality}에서는 입시진단에 사용한 내신·모의평가·과목 선택·희망 계열 자료와 기준일을 확인하세요. "
            "진단 결과가 과목 우선순위와 준비 일정, 다음 점검일로 연결되는지 살피되 특정 결과의 보장으로 해석하지 않는 편이 좋습니다."
        )
    if context.keyword in {"입시성공전략", "입시합격관리", "입시합격전략"}:
        return (
            f"{context.locality}에서는 현재 성적·과목 선택·희망 전형과 준비 시기를 기준으로 {context.keyword}의 이번 달 실행 항목과 다음 점검일을 확인하세요. "
            "과거 사례의 조건을 현재 학생과 구분하고 어떤 전략도 특정 합격 결과를 보장하는 것으로 해석하지 마세요."
        )
    if context.keyword in {"시험분석", "시험성적", "시험성적관리"}:
        return (
            f"{context.locality}에서는 {context.keyword}{particle(context.keyword, '을', '를')} 총점이 아니라 과목·단원·문항 유형과 오답 원인, 시간 사용으로 나누어 확인하세요. "
            "이전 시험과 비교할 조건을 맞추고 결과가 다음 개념 복습·재풀이·시간 연습으로 이어지는지도 살펴보는 편이 좋습니다."
        )
    if context.keyword == "학습개선":
        return (
            f"{context.locality}에서는 학습개선 전후의 완료 범위·오답 원인·질문과 재풀이 결과를 같은 기준으로 비교하세요. "
            "어떤 설명·과제·복습 조정이 있었는지와 효과가 없었던 방법도 기록해 다음 계획에 반영하는 편이 좋습니다."
        )
    if context.keyword == "학습결과":
        return (
            f"{context.locality}에서는 학습결과를 공부 시간만으로 보지 말고 완료 범위·개념 설명·재풀이 정답·남은 질문으로 확인하세요. "
            "시험 난도와 시작 수준을 고려하고 단일 점수로 성장을 단정하지 않는 편이 좋습니다."
        )
    if context.keyword in {"학습관리", "학습관리반", "학습관리수업"}:
        return (
            f"{context.locality}에서는 {context.keyword}에서 진단·계획·실행 확인·오답 재학습·수정이 이어지는지 확인하세요. "
            "학생별 목표와 담당자, 점검 주기, 실제 인원, 사용하는 자료와 보호자가 확인할 수 있는 기록도 함께 살펴보는 편이 좋습니다."
        )
    if context.keyword == "학습관리표":
        return (
            f"{context.locality}에서는 학습관리표에 목표 범위·실제 완료·오답·질문·미완료 사유·다음 행동이 함께 남는지 확인하세요. "
            "누가 언제 점검하고 미완료 항목을 어떤 규칙으로 옮기는지도 살펴보는 편이 좋습니다."
        )
    if context.keyword in {"과제관리반", "과제관리수업"}:
        return (
            f"{context.locality}에서는 {context.keyword}의 과제 배정·제출·확인·수정 흐름과 학생별 완료 기준을 확인하세요. "
            "미제출 사유와 오답 재풀이가 다음 수업에 반영되는지, 실제 인원·점검 시간·담당자가 안내되는지도 살펴보는 편이 좋습니다."
        )
    if context.keyword in {"동기관리반", "습관관리반", "집중력관리반"}:
        return (
            f"{context.locality}에서는 {context.keyword}이 의지를 평가하기보다 시작 신호·완료 범위·집중 구간·도움 요청 시점을 기록하고 작은 행동을 조정하는지 확인하세요. "
            "실패한 날 다시 시작하는 규칙과 담당자의 점검 주기도 함께 살펴보는 편이 좋습니다."
        )
    if context.keyword == "반복수업":
        return (
            f"{context.locality}에서는 반복수업이 같은 설명을 되풀이하는 데 그치지 않고 일정 간격 뒤 개념 회상·유형 재풀이·누적 점검으로 이어지는지 확인하세요. "
            "학생 설명과 변형 문제 결과를 기준으로 통과 여부와 다음 확인 시점을 정하는 편이 좋습니다."
        )
    if context.keyword in {"오답관리반", "오답관리수업"}:
        return (
            f"{context.locality}에서는 {context.keyword}에서 오답 원인 분류·교정·재풀이·누적 확인이 이어지는지 확인하세요. "
            "실제 점검 시간과 담당자, 사용하는 시험지·교재·기록표, 재시험 날짜와 통과 기준도 함께 살펴보는 편이 좋습니다."
        )
    if context.keyword in {"진도관리반", "진도관리수업"}:
        return (
            f"{context.locality}에서는 {context.keyword}의 계획 진도와 실제 완료·이해·재학습 상태를 구분하세요. "
            "학교 범위와 선행·복습 목표, 미완료 때의 속도 조정 기준, 실제 인원·담당자·확인 기록도 함께 살펴보는 편이 좋습니다."
        )
    if context.keyword in {"플래너관리반", "플래너관리수업"}:
        return (
            f"{context.locality}에서는 {context.keyword}이 계획표 작성에 그치지 않고 실제 완료·미완료 사유·옮길 날짜를 점검하는지 확인하세요. "
            "누가 언제 플래너를 보고 과도한 분량이나 반복 지연을 어떻게 조정하는지도 살펴보는 편이 좋습니다."
        )
    if context.keyword == "학습심화":
        return (
            f"{context.locality}에서는 학습심화 전에 필수 개념과 기본 적용이 안정됐는지 확인하세요. "
            "조건이 달라진 문제에서 개념 선택 이유와 풀이 과정을 설명하고, 기초 공백과 학교 진도를 고려해 범위를 조정하는 편이 좋습니다."
        )
    if context.keyword == "학습예습":
        return (
            f"{context.locality}에서는 학습예습을 앞으로 배울 단원의 핵심 용어·구조·기본 예제를 미리 살피고 모르는 부분을 표시하는 과정으로 확인하세요. "
            "이미 배운 내용을 다시 푸는 복습과 구분하고 학교 진도에 맞춰 범위를 조정하는 편이 좋습니다."
        )
    if context.keyword == "학습응용":
        return (
            f"{context.locality}에서는 학습응용이 익힌 풀이 반복이 아니라 조건이 달라진 문제에서 필요한 개념을 선택하고 근거를 설명하는 과정인지 확인하세요. "
            "기본 유형을 통과한 뒤 변형 문제로 이동하고 놓친 조건을 다음 재풀이에서 점검하는 편이 좋습니다."
        )
    if context.keyword == "학습시간관리":
        return (
            f"{context.locality}에서는 학습시간관리에 고정 일정·과목 우선순위·완료 범위·집중과 휴식 구간·여유 시간이 함께 배치되는지 확인하세요. "
            "예정 시간과 실제 사용 시간을 비교하고 일정이 달라지면 분량과 다음 점검일도 조정하는 편이 좋습니다."
        )
    if context.keyword == "학습오답관리":
        return (
            f"{context.locality}에서는 학습오답관리에서 개념·조건 해석·계산·표현·시간 배분 원인을 구분하고 교정 답안과 재풀이 날짜를 남기는지 확인하세요. "
            "반복 원인을 다음 진도·과제·질문 계획에 반영하는지도 함께 살펴보는 편이 좋습니다."
        )
    if context.keyword == "학습진도관리":
        return (
            f"{context.locality}에서는 학습진도관리에서 계획 범위와 실제 완료·이해·재학습 상태를 구분하세요. "
            "날짜·단원·완료 기준·남은 질문·다음 확인일을 기록하고 쪽수보다 설명과 재풀이 결과로 다음 범위를 정하는 편이 좋습니다."
        )
    if context.keyword == "학습진척도":
        return (
            f"{context.locality}에서는 학습진척도를 계획 대비 완료 범위·개념 설명·오답 재풀이·질문 해결 상태로 확인하세요. "
            "공부 시간이나 쪽수만으로 판단하지 말고 시작점·난도·미완료 사유와 다음 조정 항목을 함께 기록하는 편이 좋습니다."
        )
    if context.keyword == "학습통계":
        return (
            f"{context.locality}에서는 학습통계의 각 수치 정의와 집계 기간, 누락 여부를 먼저 확인하세요. "
            "공부 시간·완료 문항·정답률·오답 원인을 같은 기준으로 비교하고 표본이 적거나 범위가 다르면 단순 증감을 성과로 단정하지 마세요."
        )
    if context.keyword == "학습훈련":
        return (
            f"{context.locality}에서는 학습훈련이 짧은 목표·실행·즉시 확인·간격 재시도의 순서로 학생의 시작·설명·검토 행동을 반복하는지 확인하세요. "
            "반복 횟수보다 도움 없이 완료한 결과와 다음 통과 기준을 기록하는 편이 좋습니다."
        )
    if context.keyword == "학원브랜드":
        return (
            f"{context.locality}에서는 학원브랜드의 홍보 문구보다 교육 원칙이 수업·교재·학생 관리에 실제로 적용되는지 확인하세요. "
            "지점별 공통점과 차이, 학생에게 적용될 반·강사·기록·상담 절차를 자료로 대조하는 편이 좋습니다."
        )
    if context.keyword == "학원교재":
        return (
            f"{context.locality}에서는 학원교재가 학교 진도·학생 수준·목표에 맞춰 선택되는지 확인하세요. "
            "교재명·단원·사용 시기와 완료 기준, 기본·응용·오답 보완 자료의 역할, 미완료를 다시 보는 방법도 함께 살펴보는 편이 좋습니다."
        )
    if context.keyword == "학원데이터관리":
        return (
            f"{context.locality}에서는 학원데이터관리의 기록 항목·목적·입력 담당자·확인 주기와 오류 수정 방법을 확인하세요. "
            "학생 계획에 실제로 쓰이는 자료인지와 개인정보 접근·보관·열람·삭제 절차, 담당 변경 때의 인계 기준도 함께 살펴보는 편이 좋습니다."
        )
    if context.keyword in {"학원결제시스템", "학원미납관리", "학원수납관리"}:
        return (
            f"{context.locality}에서는 {context.keyword} 자료에서 수강 항목별 청구·결제·수납·미납·환불과 영수증·수정 이력을 같은 기간으로 대조하세요. "
            "예외 처리 절차와 담당자, 학생별 결제 정보의 접근·보관 범위도 함께 확인하는 편이 좋습니다."
        )
    if context.keyword in {"학원고객관리", "학원고객관리시스템", "학원회원관리", "학원수강생관리"}:
        return (
            f"{context.locality}에서는 {context.keyword}에서 상담·등록·출결·수업·연락 기록의 목적과 연결 범위를 확인하세요. "
            "중복·변경 이력과 사용자별 접근 권한, 수집 동의·보관 기간·열람·수정 요청 절차도 함께 살펴보는 편이 좋습니다."
        )
    if context.keyword in {"학원관리솔루션", "학원관리앱", "학원관리프로그램"}:
        return (
            f"{context.locality}에서는 {context.keyword}이 실제 필요한 출결·수납·상담·학습 기록을 연결하는지 확인하세요. "
            "사용자 권한과 자료 수정·내보내기·백업·오류 문의, 서비스 변경 때의 자료 반환과 개인정보 보관 범위도 함께 살펴보는 편이 좋습니다."
        )
    if context.keyword == "학원문서관리":
        return (
            f"{context.locality}에서는 학원문서관리에서 계약·동의·수업·상담·결제 자료의 기준본과 보관 기간, 최신본·수정 이력, 작성·열람 담당자를 확인하세요. "
            "개인정보가 포함된 문서의 사본 제공·오류 수정·폐기·인계 절차도 함께 살펴보는 편이 좋습니다."
        )
    if context.keyword == "학원상담관리":
        return (
            f"{context.locality}에서는 학원상담관리 기록에 학생 목표·현재 자료·질문·안내한 수업·비용·일정·다음 연락일과 담당자가 구분되는지 확인하세요. "
            "근거와 변경 이력, 개인정보 접근 범위를 함께 남겨 담당자가 바뀌어도 후속 안내가 이어지도록 하는 편이 좋습니다."
        )
    if context.keyword in {"학원운영", "학원행정"}:
        return (
            f"{context.locality}에서는 {context.keyword} 업무를 등록·출결·시간표·수납·상담·안전·개인정보로 나누고 담당자·확인 주기·예외 절차를 확인하세요. "
            "담당 변경과 자료 인계 기준을 두고 달라질 수 있는 행정 요건은 관할 기관의 최신 공식 안내에서 별도로 확인하는 편이 좋습니다."
        )
    if context.keyword in {
        "실시간수업", "온라인수업", "화상수업",
        "학원실시간수업", "학원온라인수업", "학원화상수업",
    }:
        return (
            f"{context.locality}에서는 {context.keyword}의 접속 방식·수업 시간·영상 제공 기간과 질문·출석·과제·피드백 기준을 확인하세요. "
            "접속 장애나 결석 때의 대체 절차와 학생의 이해 확인 결과가 다음 수업에 반영되는지도 살펴보는 편이 좋습니다."
        )
    if context.keyword in {"단기집중반", "방학집중반", "방학특강", "주말집중반", "평일집중반", "장기관리반", "학원집중반"}:
        return (
            f"{context.locality}에서는 {context.keyword}의 운영 기간·대상·과목·시작 수준과 수업 요일·시간·총횟수·완료 범위를 확인하세요. "
            "과제·결석·보강 기준과 중간 점검, 종료 뒤 복습 계획도 함께 살피고 성과를 미리 단정하지 않는 편이 좋습니다."
        )
    if context.keyword in {"보강수업", "학원보강"}:
        return (
            f"{context.locality}에서는 {context.keyword}의 신청 조건과 가능한 요일·시간, 담당자, 동일 진도 제공 여부, 출결·과제 처리와 변경·취소 절차를 확인하세요. "
            "결석 사유와 신청 시점별 예외, 보완한 범위가 다음 정규 수업에 이어지는지도 함께 살펴보는 편이 좋습니다."
        )
    if context.keyword in {"보충수업", "학원보충"}:
        return (
            f"{context.locality}에서는 {context.keyword}{particle(context.keyword, '이', '가')} 개념·단원별 부족과 취약 문제 유형 중 무엇을 다루는지, 대상 선정 기준은 무엇인지 확인하세요. "
            "수업 시간·인원·교재·종료 기준과 추가 수업 뒤 학생 설명·재풀이 결과가 정규 계획에 반영되는지도 살펴보는 편이 좋습니다."
        )
    if context.keyword in {"야간수업", "오전수업", "오후수업", "주말수업", "평일수업"}:
        return (
            f"{context.locality}에서는 {context.keyword}의 실제 운영 요일·시작·종료 시각과 대상 학년·과목·확정 가능한 반을 확인하세요. "
            "학교·이동·식사·귀가·복습 시간을 함께 계산하고 지각·결석·공휴일 때의 변경·보강 기준도 살펴보는 편이 좋습니다."
        )
    if context.keyword == "예약제수업":
        return (
            f"{context.locality}에서는 예약제수업의 대상과 신청·확정 시점, 날짜·시간·장소·담당자·준비 자료를 확인하세요. "
            "신청과 확정을 구분하고 변경·취소·지각·결석 때의 처리 기준과 새 확정 내용을 다시 확인하는 편이 좋습니다."
        )
    if context.keyword in {"자기주도반", "자기주도수업"}:
        return (
            f"{context.locality}에서는 {context.keyword}이 학생에게 맡겨 두는 방식이 아니라 목표 설정·실행·질문·검토를 스스로 하도록 지원하는지 확인하세요. "
            "초기 진단과 주간 기록, 담당자의 개입·축소 기준, 계획이 무너졌을 때 다시 시작하는 규칙도 함께 살펴보는 편이 좋습니다."
        )
    if context.keyword in {"학습성과", "학습성취도", "학습완성도", "학습향상", "학습효율", "학습성장력"}:
        return (
            f"{context.locality}에서는 {context.keyword}{particle(context.keyword, '을', '를')} 시작점·목표·완료 범위·개념 설명·오답 재풀이 같은 지표로 확인하세요. "
            "측정 자료와 기간, 누락과 난도 차이를 살피고 단일 점수나 공부 시간만으로 변화를 단정하지 않는 편이 좋습니다."
        )
    if context.keyword == "학습성과표":
        return (
            f"{context.locality}에서는 학습성과표에 목표·시작점·실행 기록·완료 결과·측정 기간과 근거 자료가 연결되는지 확인하세요. "
            "좋은 결과뿐 아니라 미완료·반복 어려움·조정 방법을 함께 남기고 조건이 다른 수치를 단순 비교하지 않는 편이 좋습니다."
        )
    if context.keyword == "학습포트폴리오":
        return (
            f"{context.locality}에서는 학습포트폴리오에 결과물뿐 아니라 목표·과정·수정·최종 결과·작성 날짜와 학생 설명이 함께 남는지 확인하세요. "
            "개인정보와 공유 범위를 살피고 포트폴리오 자체를 성적이나 입시 결과의 보장으로 해석하지 마세요."
        )
    if context.keyword == "학습체크리스트":
        return (
            f"{context.locality}에서는 학습체크리스트에 과목별 완료 범위·오답 재풀이·질문·복습·다음 행동과 완료 기준이 표시되는지 확인하세요. "
            "미완료 원인과 옮길 날짜를 기록하고 주간 점검에서 항목과 순서를 조정하는 편이 좋습니다."
        )
    if context.keyword in {"학원과제", "학원숙제"}:
        return (
            f"{context.locality}에서는 {context.keyword}의 과목·단원·완료 기준·제출 시점과 수업 내용의 연결을 확인하세요. "
            "학생별 분량 조정과 미완료·오답 점검 담당자, 다시 풀 항목이 다음 수업에 반영되는지도 함께 살펴보는 편이 좋습니다."
        )
    if context.keyword in {"학원설명회", "학원오리엔테이션"}:
        return (
            f"{context.locality}에서는 {context.keyword}의 대상·날짜·장소·주제·진행 순서와 수업·교재·시간표·비용·관리 중 안내 범위를 확인하세요. "
            "공통 안내와 학생에게 적용될 조건을 구분하고 개별 질문·후속 상담 방법도 함께 살펴보는 편이 좋습니다."
        )
    if context.keyword == "학원결제관리":
        return (
            f"{context.locality}에서는 학원결제관리에서 수강 항목·금액·결제일·영수증·할인·환불·미납·수정 이력을 같은 자료로 대조하세요. "
            "보호자 안내와 운영자 정산을 구분하고 예외 처리·문의 담당자·결제 정보의 접근·보관 범위도 함께 확인하는 편이 좋습니다."
        )
    if context.keyword == "학원관리":
        return (
            f"{context.locality}에서는 학원관리가 학생 진도·과제·오답·상담을 뜻하는지, 출결·시간표·수납·안전·개인정보 운영을 뜻하는지 구분하세요. "
            "학부모와 운영자에게 필요한 기록·담당자·예외 절차를 각각 확인하고 명칭만으로 범위를 단정하지 않는 편이 좋습니다."
        )
    if context.keyword in {"학원데스크", "학원매니저", "학원상담직원", "학원직원", "학원코디네이터"}:
        return (
            f"{context.locality}에서는 {context.keyword}의 직함보다 상담·출결·시간표·비용 문의와 수업 담당자 연결의 책임 범위를 확인하세요. "
            "채용·근무 조건을 찾는 경우에는 이 페이지에서 추정하지 말고 해당 기관의 최신 공식 채용 공고를 별도로 확인해야 합니다."
        )
    if context.keyword == "학원프로그램":
        return (
            f"{context.locality}에서는 학원프로그램이 수업 과정인지 운영 소프트웨어인지 먼저 구분하세요. "
            "수업이면 대상·과목·기간·교재·관리 흐름을, 소프트웨어면 출결·수납·상담·기록 기능과 권한·보관·백업 조건을 확인하는 편이 좋습니다."
        )
    if context.keyword == "학습피드백":
        return (
            f"{context.locality}에서는 학습피드백에 완료·미완료 범위, 오답 원인, 다시 풀 항목과 다음 행동이 "
            "구체적으로 남는지 확인하세요. 누가 어떤 자료를 보고 언제 의견을 전달하는지, 학생이 수정한 내용과 "
            "다음 점검일이 기록되는지도 함께 살펴보는 편이 좋습니다."
        )
    if context.keyword in {"입시일정관리", "입시일정"}:
        return (
            f"{context.locality}에서는 공식 안내를 기준으로 지원·전형·시험·결과 발표 일정을 구분하고, "
            f"학생이 준비할 서류와 과제, 변경 여부를 다시 확인할 시점을 {context.keyword}에 함께 기록하세요. "
            "확정되지 않은 날짜를 단정하지 말고 최신 공지에 맞춰 갱신하는 편이 안전합니다."
        )
    if context.keyword == "학원시간표":
        return (
            f"{context.locality}에서는 학원시간표의 수업 요일·시각·길이와 담당 과목, 변경·보강 기준을 확인하세요. "
            "학교 수업과 이동·자습·복습 시간을 함께 놓고 실제 가능한 반과 확정 시간을 대조한 뒤, 일정이 바뀔 때의 절차도 살펴보는 편이 좋습니다."
        )
    if context.keyword == "학습시간표":
        return (
            f"{context.locality}에서는 학교·수업처럼 고정된 시간을 먼저 표시하고 과목별 완료 범위, 오답·암기 복습, "
            "밀린 일을 옮길 여유 시간을 학습시간표에 배치하세요. 매일 실제 완료 범위를 표시하고 시험·학교 행사에 맞춰 순서와 분량을 조정하는 편이 좋습니다."
        )
    if context.keyword == "시험일정관리":
        return (
            f"{context.locality}에서는 학교가 안내한 시험일·범위·수행평가 일정을 기준으로 시험일정관리를 시작하세요. "
            "과목별 개념·문제 풀이·오답 점검 시점을 역순으로 배치하고, 공지가 바뀌면 일정과 분량을 함께 수정하는 편이 좋습니다."
        )
    if context.keyword == "학습일정관리":
        return (
            f"{context.locality}에서는 학교 일정·시험·과제와 과목별 완료 범위, 복습 시점, 여유 시간을 학습일정관리에 함께 반영하세요. "
            "매주 실제 완료 범위와 미완료 원인을 확인하고 일정이 달라지면 우선순위와 다음 점검일을 갱신하는 편이 좋습니다."
        )
    if context.keyword == "학원전자계약":
        return (
            f"{context.locality}에서는 학원전자계약에 적힌 수업 과목·기간·시간과 비용, 환불·결석·보강·변경 조건, "
            "개인정보 동의 범위를 서명 전에 확인하세요. 완료 뒤 열람할 수 있는 사본과 수정·해지·문의 절차도 함께 살펴보는 편이 좋습니다."
        )
    if context.keyword == "학원예약관리":
        return (
            f"{context.locality}에서는 학원예약관리에 상담·진단·수업 중 예약 대상과 확정된 날짜·시간·장소, 담당자, "
            "준비 자료가 분명히 표시되는지 확인하세요. 신청과 확정을 구분하고 변경·취소·재확인 방법도 함께 살펴보는 편이 좋습니다."
        )
    if context.keyword == "학원매출관리":
        return (
            f"{context.locality}에서는 학원매출관리 자료에서 같은 기간의 청구·수납·할인·미수·환불을 구분하고 "
            "영수증과 정산 기록이 일치하는지 확인하세요. 학생별 결제 정보의 접근·보관 범위와 오류 수정 이력도 함께 관리하는 편이 좋습니다."
        )
    if context.keyword == "입시설계":
        return (
            f"{context.locality}에서는 희망 진로만 먼저 정하기보다 최근 내신·모의평가, "
            "과목별 강약점, 선택 과목과 준비 시기를 함께 놓고 입시설계의 실행 순서를 확인하세요. "
            "결과를 미리 단정하지 말고 학기·방학·지원 시기마다 무엇을 다시 점검할지도 기록하는 편이 안전합니다."
        )
    if context.keyword == "입시설명회":
        return (
            f"{context.locality}에서는 입시설명회의 대상 학년과 주제, 안내에 사용한 근거 자료, "
            "변경될 수 있는 조건을 먼저 확인하세요. 발표 내용을 학생의 현재 성적·과목 선택·준비 일정과 "
            "대조하고, 설명회 뒤 개별 상담에서 확인할 질문과 다음 행동을 남기는 편이 좋습니다."
        )
    if context.keyword == "입시상담예약":
        return (
            f"{context.locality}에서는 입시상담예약 전에 학생 학년과 상담 목적을 정하고, "
            "성적표·시험지·과목 선택 자료 가운데 필요한 항목을 확인하세요. 예약 확정 일정과 변경·취소 방법을 "
            "안내에서 대조하고, 상담 뒤에는 다음 확인일과 실행 항목을 기록하는 편이 좋습니다."
        )
    if context.keyword == "학원개원":
        return (
            f"{context.locality}에서 신규 학원을 확인하는 학부모라면 실제 수업 시작일, 가능한 학년·과목과 시간표, "
            "담당자·교재·진단 자료의 준비 범위를 살펴보세요. 직접 개원을 준비하는 운영자라면 수업 계획과 학생 관리, "
            "수강료·환불·안전·개인정보 안내를 문서화하고 등록·시설 등 행정 요건은 관할 기관의 최신 공식 안내에서 별도로 확인해야 합니다."
        )
    if context.keyword == "학원교재실":
        return (
            f"{context.locality}에서는 교재를 과목·학년·과정·사용 상태별로 분류하는지와 대여일·반납일·담당자 기록을 확인하세요. "
            "학생이 사용할 자료의 소유·보관·반납 조건과 분실·훼손 처리, 재고·판본 점검 방법까지 실제 안내에서 대조하는 편이 좋습니다."
        )
    if context.keyword == "학원사물함":
        return (
            f"{context.locality}에서는 사물함의 배정 대상·사용 기간·크기·잠금 방식과 열쇠 또는 비밀번호 관리 방법을 확인하세요. "
            "보관 제한 물품, 분실·파손 신고, 이용 종료 때 물품 확인과 열쇠 반납 절차도 함께 살펴보는 편이 좋습니다."
        )
    if context.keyword == "학원상담실":
        return (
            f"{context.locality}에서는 상담실의 대화가 불필요하게 노출되지 않는지와 예약 시간·참석자·준비 자료를 확인하세요. "
            "상담 기록의 항목·열람 담당자·보관·수정·문의 방법과 개인정보를 상담 목적에 필요한 범위로 다루는지도 실제 안내에서 살펴보는 편이 좋습니다."
        )
    if context.keyword == "학원자료실":
        return (
            f"{context.locality}에서는 종이 자료를 두는 물리 공간인지 온라인 파일 공간인지 먼저 구분하고 자료 종류·대상·접근 권한·이용 시간을 확인하세요. "
            "열람·다운로드 또는 대여·반납 방법과 출처·판본·수정일, 오래된 자료의 교체·보관 기준도 실제 안내에서 대조하는 편이 좋습니다."
        )
    if context.keyword == "학원출결앱":
        return (
            f"{context.locality}에서는 등원·하원 시각의 입력 방식과 알림 시점, 지각·조퇴·결석·누락 구분, 잘못된 기록의 수정 절차를 확인하세요. "
            "학생·보호자·담당자의 열람 권한과 알림 실패 때의 대체 연락, 출결 정보의 보관·열람·수정 문의 방법도 함께 살펴보는 편이 좋습니다."
        )
    if context.keyword == "학원휴게실":
        return (
            f"{context.locality}에서는 휴게실의 이용 대상·가능 시간과 음식·음료 규칙, 교실과의 소음 분리, 혼잡·청결·안전 문제의 문의 담당자를 확인하세요. "
            "학생이 정해진 휴식 뒤 다음 수업에 복귀하는 방법과 이용 종료 때의 정리 기준도 실제 안내에서 살펴보는 편이 좋습니다."
        )
    if context.keyword == "학원주차":
        return (
            f"{context.locality}에서는 건물 또는 인근 주차장의 위치와 진입 방법, 이용 요일·시간·혼잡 조건을 먼저 확인하세요. "
            "무료·유료 여부와 차량 등록·할인, 승하차·단기 대기 가능 범위, 만차나 운영 변경 때의 대체 위치도 최신 안내에서 다시 살펴보는 편이 좋습니다."
        )
    if context.keyword == "학원방역관리":
        return (
            f"{context.locality}에서는 환기·공용 공간 관리 주기, 감염 의심 증상이 있을 때의 등원·연락 기준, "
            "수업 변경이나 결석 처리 안내 방법을 구분해 확인하세요. 실제 적용 범위와 최신 학원방역관리 안내는 "
            "등록 전과 운영 조건이 달라질 때 다시 묻는 편이 좋습니다."
        )
    if context.keyword == "학원청결관리":
        return (
            f"{context.locality}에서는 교실·책상·공용 물품의 관리 주기와 환기, 화장실·휴게 공간 점검 범위를 확인하세요. "
            "학원청결관리의 담당자와 불편 사항 전달 방법, 조치 결과를 확인할 수 있는 안내까지 함께 살펴보는 편이 좋습니다."
        )
    if context.keyword == "학원개인정보관리":
        return (
            f"{context.locality}에서는 학생·보호자 정보의 수집 목적과 항목, 보관 기간, 열람·수정 요청 방법을 먼저 확인하세요. "
            "문자·앱·사진 등 전달 수단별 동의 범위와 철회 절차, 문의 창구를 구분해 학원개인정보관리 안내에 적혀 있는지 살펴보는 편이 안전합니다."
        )
    if context.keyword == "학원창업":
        return (
            f"{context.locality}에서 학원창업을 준비한다면 대상 학년·과목과 수업 계획, 강사·교재·학생 관리 흐름, "
            "수강료·환불·안전·개인정보 안내를 자료로 구체화하세요. 필요한 행정 요건과 승인 여부는 관할 기관의 최신 안내에서 별도로 확인해야 합니다."
        )
    if context.keyword == "학원운영자":
        return (
            f"{context.locality}에서는 학원운영자의 직함보다 수업·교재·진도, 출결·보강·비용 문의, "
            "학습 기록·보호자 상담의 책임자가 각각 누구인지 확인하세요. 담당 변경 시에도 학생 기록이 이어지는지와 문의 유형별 연락 방법을 함께 살펴보는 편이 좋습니다."
        )
    if context.keyword == "학원일정":
        return (
            f"{context.locality}에서는 정규 수업일·휴강·공휴일·시험 대비 일정을 대상 학년과 과목별로 구분해 확인하세요. "
            "처음 안내와 최종 확정 시점을 구분하고, 변경 통보 방법과 학생 계획표·보호자 안내가 함께 갱신되는지도 살펴보는 편이 좋습니다."
        )
    if context.keyword == "학원온라인등록":
        return (
            f"{context.locality}에서는 공식 학원온라인등록 경로와 입력·제출 항목, 필수·선택 동의와 결제 조건을 먼저 확인하세요. "
            "신청 완료와 반·시간표 확정을 구분하고 접수 확인 방법, 입력 오류·취소·환불 문의 절차도 함께 살펴보는 편이 좋습니다."
        )
    if context.keyword == "학원재등록":
        return (
            f"{context.locality}에서는 기존 수업·출결·과제·오답 기록과 다음 기간의 과목·반·시간·교재·비용 변경 사항을 함께 확인하세요. "
            "신청 기한과 확정 시점, 변경·취소 절차를 구분하고 미완료 보완 계획이 다음 수업으로 이어지는지도 살펴보는 편이 좋습니다."
        )
    if context.keyword in {"학원문자발송", "학원알림톡"}:
        return (
            f"{context.locality}에서는 {context.keyword}의 발송 목적·수신 대상·동의 범위와 발신자·문의처가 안내에 표시되는지 확인하세요. "
            "출결·일정 변경처럼 중요한 알림의 발송·도달 기록과 실패·재발송·연락처 수정 절차도 함께 살펴보는 편이 좋습니다."
        )
    if context.keyword == "시험시간관리":
        return (
            f"{context.locality}에서는 시험 총시간에서 읽기·풀이·마킹·검토 시간을 나누고 문항 유형별 전환 기준을 정하세요. "
            "실전과 같은 조건에서 완료 문항 수·정확도·검토 시간을 함께 기록하고 반복 결과에 따라 배분표를 조정하는 편이 좋습니다."
        )
    if context.keyword in {"학습성과관리", "학습성적관리"}:
        measure = "학습성과" if context.keyword == "학습성과관리" else "학습성적"
        return (
            f"{context.locality}에서는 {measure}의 시작 시점과 비교 기간을 정하고 같은 범위·난도의 자료를 기준으로 비교하세요. "
            "총점만 보지 말고 과목·단원·오답 원인·완료·재풀이 결과를 함께 기록해 다음 설명·과제·복습과 재확인일로 연결하는 편이 좋습니다."
        )
    if context.keyword == "학원출결":
        return (
            f"{context.locality}에서는 학원출결의 등원·하원 시각과 지각·조퇴·결석 구분, 기록 담당자와 보호자 통보 시점을 확인하세요. "
            "누락·오류 수정 이력과 결석 뒤 보강·과제·진도 연결 방법, 알림 실패 때의 대체 연락도 함께 살펴보는 편이 좋습니다."
        )
    return ""


def privacy_supplemental_heading(context: Context) -> str:
    return f"{context.locality} 개인정보 안내에서 확인할 권리와 처리 절차"


def replace_second_keyword_heading(
    values: list[str], context: Context
) -> tuple[list[str], int]:
    if context.keyword != "학원개인정보관리":
        return values, 0
    if privacy_supplemental_heading(context) in values:
        return values, 0
    matches = [
        index
        for index, value in enumerate(values)
        if isinstance(value, str) and context.keyword in value
    ]
    if len(matches) != 2:
        raise ValueError(
            f"{context.path}: privacy keyword heading count={len(matches)}/2"
        )
    updated = list(values)
    updated[matches[1]] = privacy_supplemental_heading(context)
    return updated, 1


def update_special_keyword_flow(flow: str, context: Context) -> tuple[str, int]:
    paragraphs = special_keyword_paragraphs(context)
    section_re = re.compile(
        r'(<section\s+class="subject-copy-section"><h2>[^<]*'
        + re.escape(context.keyword)
        + r'[^<]*</h2>)(?P<body>.*?)(</section>)',
        re.S,
    )
    match = section_re.search(flow)
    heading = special_keyword_heading(context)
    if not paragraphs:
        if not heading:
            return flow, 0
        if not match:
            raise ValueError(f"{context.path}: special heading section missing")
        section, count = re.subn(
            r"(<h2>).*?(</h2>)",
            lambda heading_match: (
                heading_match.group(1) + html.escape(heading) + heading_match.group(2)
            ),
            match.group(0),
            count=1,
            flags=re.S,
        )
        if count != 1:
            raise ValueError(f"{context.path}: special heading update failed")
        return flow[: match.start()] + section + flow[match.end() :], 1
    if not match:
        raise ValueError(f"{context.path}: special keyword section missing")
    old_paragraphs = re.findall(r"<p>.*?</p>", match.group("body"), re.S)
    if len(old_paragraphs) != 2:
        raise ValueError(
            f"{context.path}: special keyword paragraph count={len(old_paragraphs)}"
        )
    body = "".join(f"<p>{paragraph}</p>" for paragraph in paragraphs)
    heading_prefix = match.group(1)
    if heading:
        heading_prefix, heading_count = re.subn(
            r"(<h2>).*?(</h2>)",
            lambda heading_match: (
                heading_match.group(1) + html.escape(heading) + heading_match.group(2)
            ),
            heading_prefix,
            count=1,
            flags=re.S,
        )
        if heading_count != 1:
            raise ValueError(f"{context.path}: special keyword heading update failed")
    replacement = heading_prefix + body + match.group(3)
    updated = flow[: match.start()] + replacement + flow[match.end() :]
    changes = int(updated != flow)
    if context.keyword == "학원개인정보관리":
        if privacy_supplemental_heading(context) in updated:
            return updated, changes
        section_matches = [
            item
            for item in re.finditer(
                r'<section\s+class="subject-copy-section"><h2>(?P<heading>.*?)</h2>'
                r'(?P<body>.*?)</section>',
                updated,
                re.S,
            )
            if context.keyword in clean(item.group("heading") + item.group("body"))
        ]
        if len(section_matches) != 2:
            raise ValueError(
                f"{context.path}: privacy dedicated sections={len(section_matches)}/2"
            )
        target = section_matches[1]
        old_paragraphs = re.findall(r"<p>.*?</p>", target.group("body"), re.S)
        if len(old_paragraphs) != 2:
            raise ValueError(
                f"{context.path}: privacy supplemental paragraph count={len(old_paragraphs)}"
            )
        supplemental = (
            (
                f"{context.locality} 개인정보 안내에서는 수집 목적과 필수·선택 항목, 자료를 볼 수 있는 담당자, 보관 기간과 삭제 시점을 구분해 확인해야 합니다. "
                "학생·보호자가 자신의 정보를 열람하거나 잘못된 내용을 고쳐 달라고 요청할 방법도 현재 서면 안내에 적혀 있는지 살펴보세요."
            ),
            (
                f"{context.locality} 학부모는 제3자 제공과 사진·메시지 등 홍보 활용이 별도 동의로 나뉘는지 확인하는 편이 좋습니다. "
                "동의 철회와 이용 중지, 사고 발생 시 문의할 창구와 처리 순서를 기록하고 실제 적용되는 최신 안내를 등록 전에 다시 확인하세요."
            ),
        )
        section = target.group(0)
        section, heading_count = re.subn(
            r"(<h2>).*?(</h2>)",
            lambda heading_match: (
                heading_match.group(1)
                + html.escape(privacy_supplemental_heading(context))
                + heading_match.group(2)
            ),
            section,
            count=1,
            flags=re.S,
        )
        heading_delta = len(section) - len(target.group(0))
        body_start = target.start("body") - target.start() + heading_delta
        body_end = target.end("body") - target.start() + heading_delta
        section = (
            section[:body_start]
            + "".join(f"<p>{paragraph}</p>" for paragraph in supplemental)
            + section[body_end:]
        )
        if heading_count != 1:
            raise ValueError(f"{context.path}: privacy supplemental update failed")
        updated = updated[: target.start()] + section + updated[target.end() :]
        changes += 1
    return updated, changes


def replace_keyword_reference(value: str, keyword: str) -> tuple[str, int]:
    replacements = (
        (f"다음 {keyword} 행동", "다음 학습 행동"),
        (f"{keyword}이라는", "해당 명칭이라는"),
        (f"{keyword}라는", "해당 명칭이라는"),
        (f"{keyword}은 적용되는", "해당 안내가 적용되는"),
        (f"{keyword}는 적용되는", "해당 안내가 적용되는"),
        (f"{keyword} 적용 요일", "해당 안내가 적용되는 요일"),
        (f"{keyword} 비교도", "해당 조건을 비교할 때도"),
        (f"{keyword} 비교표", "해당 비교표"),
        (f"{keyword} 피드백", "해당 피드백"),
        (f"{keyword} 안내", "해당 안내"),
        (f"{keyword} 상담", "해당 상담"),
        (f"{keyword} 계획", "해당 계획"),
        (f"{keyword} 조건", "해당 조건"),
        (f"{keyword} 일정", "해당 일정"),
        (f"{keyword} 기록", "해당 기록"),
        (f"{keyword} 행동", "해당 학습 행동"),
        (f"{keyword}은", "해당 안내는"),
        (f"{keyword}는", "해당 안내는"),
        (f"{keyword}을", "해당 안내를"),
        (f"{keyword}를", "해당 안내를"),
        (f"{keyword}의", "해당 안내의"),
        (f"{keyword}과", "해당 안내와"),
        (f"{keyword}와", "해당 안내와"),
    )
    for before, after in replacements:
        if before in value:
            return value.replace(before, after, 1), 1
    if keyword in value:
        return value.replace(keyword, "해당 안내", 1), 1
    return value, 0


def replace_keyword_reference_preserving_anchor(
    value: str, context: Context
) -> tuple[str, int]:
    """Reduce a secondary keyword mention without losing context extraction."""
    sentinel = "__HIGH_STUDENT_PRIMARY_KEYWORD__"
    anchor = re.compile(
        rf"({re.escape(context.locality)}에서\s+)"
        rf"{re.escape(context.keyword)}"
        rf"((?:을|를)\s+알아볼 때 핵심)"
    )
    protected, protected_count = anchor.subn(
        lambda match: match.group(1) + sentinel + match.group(2),
        value,
        count=1,
    )
    updated, count = replace_keyword_reference(protected, context.keyword)
    if protected_count:
        updated = updated.replace(sentinel, context.keyword, 1)
    return updated, count


def reduce_keyword_density(
    flow: str, context: Context, maximum: int = 6
) -> tuple[str, int]:
    keyword = context.keyword
    reductions = 0
    section_re = re.compile(
        r'<section\s+class="subject-copy-section"><h2>(?P<heading>.*?)</h2>(?P<body>.*?)</section>',
        re.S,
    )
    paragraph_re = re.compile(r"<p>.*?</p>", re.S)
    while clean(flow).count(keyword) > maximum:
        changed = False
        sections = list(section_re.finditer(flow))
        for allow_keyword_heading in (False, True):
            for section in reversed(sections):
                heading = clean(section.group("heading"))
                if not allow_keyword_heading and keyword in heading:
                    continue
                paragraphs = list(paragraph_re.finditer(section.group("body")))
                for paragraph in reversed(paragraphs):
                    absolute_start = section.start("body") + paragraph.start()
                    absolute_end = section.start("body") + paragraph.end()
                    updated, count = replace_keyword_reference(
                        flow[absolute_start:absolute_end], keyword
                    )
                    if count:
                        flow = flow[:absolute_start] + updated + flow[absolute_end:]
                        reductions += count
                        changed = True
                        break
                if changed:
                    break
            if changed:
                break
        if not changed:
            raise ValueError(
                f"{context.path}: cannot reduce keyword density from {clean(flow).count(keyword)}"
            )
    return flow, reductions


def polish_source_phrasing(flow: str) -> tuple[str, int]:
    replacements = (
        ("기본 유형은 안정적으로 처리하지만", "기본 문제는 안정적으로 풀지만"),
        ("오답 원인의 원인", "오답이 생긴 원인"),
        ("오답 원인·오답 원인 구분 유형", "오답 기록·오답 원인 구분 유형"),
        ("선택 판단을", "답을 선택한 근거를"),
        ("선택 판단", "답을 선택한 근거"),
        (
            "일주일 뒤 완료율과 같은 오류의 반복 여부로 분량을 조정합니다.",
            "일주일 뒤 완료율과 동일한 오류의 반복 여부를 함께 확인해 분량을 조정합니다.",
        ),
        (
            "계획 대비 완료율과 같은 오류의 반복 횟수",
            "계획 대비 완료율과 동일 오류의 반복 횟수",
        ),
    )
    count = 0
    for before, after in replacements:
        changed = flow.count(before)
        flow = flow.replace(before, after)
        count += changed
    return flow, count


def section_role(heading: str) -> str:
    roles = (
        (("통학", "동선", "주소", "거리", "학교 일정", "귀가"), "통학 조건"),
        (("진단", "현재 상태", "최근 점수", "시험지", "준비하면"), "학습 진단"),
        (("피드백", "기록", "보고", "소통"), "학습 기록"),
        (("주간", "계획", "시간표", "선행", "과목별"), "학습 계획"),
        (("시험", "내신", "범위", "오답"), "시험 준비"),
        (("판단", "선택", "결정", "상담", "최종", "체크"), "상담 기준"),
    )
    for needles, role in roles:
        if any(needle in heading for needle in needles):
            return role
    return "학습관리 항목"


def neutralize_keyword_reference(
    value: str, context: Context, role: str
) -> tuple[str, int, int]:
    keyword = context.keyword
    if keyword in role:
        role = "현재 상태"
    keyword_subject = particle(keyword, "은", "는")
    keyword_object = particle(keyword, "을", "를")
    changes = 0
    keyword_reductions = 0
    diagnostic_prefix = choose(
        context,
        f"v2-diagnostic-prefix-{role}",
        (
            f"{context.locality} 학생의 최근 답안을 살필 때",
            "최근 시험지와 과제를 함께 검토할 때",
            f"{context.locality} {context.grade} 학생의 답안을 살필 때",
            "첫 진단 자료에서 풀이 과정을 확인할 때",
            "점수보다 학생이 남긴 풀이를 먼저 볼 때",
            f"{context.locality} 상담에서 답안을 원인별로 나눌 때",
            "학생이 처음 막힌 단계를 찾기 위해",
            "오답 기록을 원인별로 정리할 때",
        ),
    )

    replacements = (
        (f"다음 {keyword} 행동", "다음 학습 행동"),
        (f"{keyword} 다음 행동", "다음 학습 행동"),
        (f"{keyword} 검토를 위해", diagnostic_prefix),
        (f"{keyword} 진단은", "진단 결과에는"),
        (f"{keyword} 진행 전후", "학습 계획의 실행 전후"),
        (f"{keyword} 변화를", "학습 변화를"),
        (f"{keyword} 변화", "학습 변화"),
        (f"{keyword} 안내를 들은 뒤", "학습 계획을 세운 뒤"),
        (f"{keyword} 안내를 비교할 때", "학습관리 안내를 비교할 때"),
        (f"{keyword} 안내에서는", "학습관리 안내에서는"),
        (f"{keyword} 안내는", "학습관리 안내는"),
        (f"{keyword} 피드백", "학습 피드백"),
        (f"{keyword} 기록", "학습 기록"),
        (f"{keyword} 계획의 실행 여부", "다음 학습 계획의 실행 여부"),
        (f"{keyword} 계획과 대조", "다음 학습 계획과 대조"),
        (f"{keyword} 계획에서는", "학습 계획에서는"),
        (f"{keyword} 계획은", "학습 계획은"),
        (f"{keyword} 계획", "학습 계획"),
        (f"{keyword} 적용 요일", "학습 계획을 적용할 요일"),
        (f"{keyword} 일정과 단계", "학습 일정과 단계"),
        (f"{keyword} 일정도 같은 표", "통학 일정도 같은 표"),
        (f"{keyword} 일정", "학습 일정"),
        (f"{keyword} 비교표", "통학 비교표"),
        (f"{keyword} 비교도", "통학 가능성 판단도"),
        (f"{keyword} 조건이 그 일정", "수업 조건이 그 일정"),
        (f"{keyword} 조건", "상담 조건"),
        (f"{keyword} 상담에서 학교명", "통학 상담에서 학교명"),
        (f"{keyword} 상담 뒤에는", "진단 상담 뒤에는"),
        (f"{keyword} 상담", "상담 과정"),
        (f"{keyword} 선택에서는", "통학 계획에서는"),
        (f"{keyword}{keyword_object} 실제 학습 기록", "그 내용을 실제 학습 기록"),
        (f"{keyword}{keyword_object} 학습 변화로 확인하려면", "학습 변화를 확인하려면"),
        (f"{keyword}{keyword_object} 실제 관리와 연결하려면", "학습 계획을 실제 관리와 연결하려면"),
        (f"{keyword}{keyword_object} 배치해 보고", "학습 활동을 배치해 보고"),
        (f"{keyword}{keyword_object} 비교하세요", "통학 조건을 비교하세요"),
        (f"{keyword}{keyword_object} 살필 때", f"{role}{particle(role, '을', '를')} 살필 때"),
        (f"{keyword}{keyword_object} 확인할 때는", "학습 상태를 확인할 때는"),
        (f"{keyword}{keyword_subject} 적용되는", f"{role}{particle(role, '이', '가')} 적용되는"),
    )
    for before, after in replacements:
        count = value.count(before)
        if count:
            value = value.replace(before, after)
            changes += count
            keyword_reductions += count

    suffix_replacements = (
        ("은", particle(role, "은", "는")),
        ("는", particle(role, "은", "는")),
        ("이", particle(role, "이", "가")),
        ("가", particle(role, "이", "가")),
        ("을", particle(role, "을", "를")),
        ("를", particle(role, "을", "를")),
        ("과", particle(role, "과", "와")),
        ("와", particle(role, "과", "와")),
        ("의", "의"),
    )
    for old_suffix, new_suffix in suffix_replacements:
        before = keyword + old_suffix
        count = value.count(before)
        if count:
            value = value.replace(before, role + new_suffix)
            changes += count
            keyword_reductions += count
    remaining = value.count(keyword)
    if remaining:
        value = value.replace(keyword, role)
        changes += remaining
        keyword_reductions += remaining

    generic_replacements = (
        ("해당 안내 검토를 위해", diagnostic_prefix),
        ("해당 안내를 들은 뒤", "학습 계획을 세운 뒤"),
        ("해당 안내가 적용되는 요일", "학습 계획을 적용할 요일"),
        ("해당 안내 적용 요일", "학습 계획을 적용할 요일"),
        ("해당 안내를 배치해 보고", "학습 활동을 배치해 보고"),
        ("해당 안내를 활용할 시점", "학습 계획을 실행할 시점"),
        ("해당 안내 선택에서는", "통학 계획에서는"),
        ("해당 안내는 설명에 머물지 않고", "학습 계획은 설명에 머물지 않고"),
        ("해당 안내를 실제 관리와 연결하려면", "학습 계획을 실제 관리와 연결하려면"),
        ("해당 안내를 비교할 때는 전달 문구", "학습관리 안내를 비교할 때는 전달 문구"),
        ("해당 비교표", "통학 비교표"),
        ("해당 조건을 비교할 때도 주소", "통학 가능성을 판단할 때도 주소"),
        ("해당 안내를 비교하세요", "통학 조건을 비교하세요"),
        ("해당 안내를 확인할 때는 진도 속도보다", "학습 상태를 확인할 때는 진도 속도보다"),
        ("해당 안내를 살필 때", f"{role}{particle(role, '을', '를')} 살필 때"),
        ("해당 상담에서 학교명", "통학 상담에서 학교명"),
        ("해당 상담 뒤에는", "진단 상담 뒤에는"),
        ("해당 계획은", "주간 계획은"),
        ("해당 안내를 학습 변화로 확인하려면", "학습 변화를 확인하려면"),
    )
    for before, after in generic_replacements:
        count = value.count(before)
        if count:
            value = value.replace(before, after)
            changes += count

    return value, changes, keyword_reductions


TOPIC_REASON = {
    "난도 적응": "난도가 달라질 때 풀이가 끊기는 이유",
    "과목 우선순위": "과목별 우선순위를 정하지 못하는 이유",
    "시험 시간": "시험 시간 배분이 흔들리는 이유",
    "응용 출발점": "응용 문제의 첫 단계를 시작하지 못하는 이유",
    "자기 설명": "풀이 근거를 자신의 말로 설명하지 못하는 이유",
    "시험 분석": "시험 결과를 다음 학습으로 연결하지 못하는 이유",
    "과목 편차": "과목별 이해 차이가 커진 이유",
    "서술형 구성": "서술형 답안의 순서가 흐트러지는 이유",
    "선행 공백": "이전 과정의 학습 공백이 생긴 이유",
    "과제 점검": "과제 확인과 수정이 늦어지는 이유",
    "누적 복습": "이전 단원 복습이 이어지지 않는 이유",
    "계획 과부하": "계획량이 실제 수행량을 넘어선 이유",
    "집중 지속": "집중이 학습 중간에 끊기는 이유",
    "복습 시작": "복습을 제때 시작하지 못하는 이유",
    "검토 절차": "정해 둔 검토 순서를 지키지 못하는 이유",
    "조건 해석": "문제의 조건을 잘못 해석하는 이유",
    "질문 습관": "막힌 지점을 질문으로 남기지 못하는 이유",
    "오답 원인": "같은 오답이 반복되는 이유",
}


TOPIC_ITEM = {
    "난도 적응": "난도가 바뀌면 풀이가 끊기는",
    "과목 우선순위": "과목별 우선순위를 정하지 못한",
    "시험 시간": "시간 배분이 무너진",
    "응용 출발점": "응용 문제의 첫 단계를 시작하지 못한",
    "자기 설명": "풀이 근거를 자신의 말로 설명하지 못한",
    "시험 분석": "시험 결과를 원인별로 나누지 못한",
    "과목 편차": "과목별 이해 차이가 드러난",
    "서술형 구성": "서술형 답안의 순서가 흐트러진",
    "선행 공백": "이전 개념의 공백이 드러난",
    "과제 점검": "과제 확인과 수정이 늦어진",
    "누적 복습": "이전 단원과의 연결이 끊긴",
    "계획 과부하": "계획량이 실제 수행량을 넘어선",
    "집중 지속": "집중이 학습 중간에 끊긴",
    "복습 시작": "복습 시작이 늦어진",
    "검토 절차": "정해 둔 검토 순서를 지키지 못한",
    "조건 해석": "문제의 조건을 잘못 해석한",
    "질문 습관": "막힌 지점을 질문으로 남기지 못한",
    "오답 원인": "오답 원인을 설명하지 못한",
}


def topic_reason(topic: str) -> str:
    return TOPIC_REASON.get(topic, f"{topic} 문제가 반복되는 이유")


def topic_item(topic: str) -> str:
    return TOPIC_ITEM.get(topic, f"{topic} 어려움이 드러난")


def primary_challenge(context: Context) -> str:
    match = re.match(r"(?:예비고1|고[1-3]) (?P<topic>[^·]+)·", context.persona)
    if not match:
        raise ValueError(f"{context.path}: primary challenge missing")
    return match.group("topic").strip()


def secondary_challenge(context: Context) -> str:
    match = re.match(
        r"(?:예비고1|고[1-3]) [^·]+·(?P<topic>.+?) 유형$",
        context.persona,
    )
    if not match:
        raise ValueError(f"{context.path}: secondary challenge missing")
    return match.group("topic").strip()


def method_for_secondary_challenge(context: Context) -> str:
    topic = secondary_challenge(context)
    methods = {
        "교재 완주": "한 권의 교재를 끝낸 뒤 다음 자료로 넘어가는 방식",
        "도움 요청 시점": "막힌 문제를 표시하고 도움을 요청할 시점을 미리 정하는 방식",
        "수면 리듬": "취침·기상 시각과 집중 가능한 학습 구간을 함께 고정하는 방식",
        "시험 범위 확인": "학교에서 받은 시험 범위표를 먼저 확인하고 준비 순서를 정하는 방식",
        "시험 후 복기": "시험 직후 오답 원인을 분류하고 재풀이 날짜를 정하는 방식",
        "어려운 과목 미루기": "과목별 우선순위를 매일 다시 정렬하는 방식",
        "오답 원인 구분": "오답을 원인별로 분류하고 재시험 날짜를 정하는 방식",
        "오답 재풀이일": "오답마다 다시 풀 날짜와 통과 기준을 정하는 방식",
        "완료 기준": "공부 시간보다 완료할 단원·문항·결과물을 먼저 적는 방식",
        "주간 계획 유지": "주간 목표를 하루 세 과제 안쪽으로 쪼개는 방식",
        "주말 누적복습": "하루·주간·월간 복습 간격을 구분하는 방식",
        "질문 표시": "질문 목록을 수업 전에 한 줄씩 준비하는 방식",
        "채점 시차": "과제 완료 뒤 바로 채점하고 수정 날짜를 정하는 방식",
        "학습 기록": "완료 범위·오답·질문·다음 행동을 매일 기록하는 방식",
    }
    method = methods.get(topic)
    if not method:
        raise ValueError(f"{context.path}: method missing for {topic}")
    return method


def legacy_method_from_flow(flow: str, context: Context) -> str:
    if MARKER in flow:
        return method_for_secondary_challenge(context)
    for method_pattern in (
        r"특히 [^<.!?]{4,180}?에는 (?P<method>[^<.!?]{8,180}? 방식)이 필요한 유형입니다\.",
        r"유형에게 필요한 (?P<method>[^<.!?]{8,220}? 방식)이 실제 시간표에 반영되는지",
    ):
        match = re.search(method_pattern, flow)
        if match:
            return match.group("method").strip()
    raise ValueError(f"{context.path}: legacy learning method missing")


def feedback_metric_sentence(context: Context) -> str:
    topic = primary_challenge(context)
    metrics = {
        "시험 시간": "시간을 초과한 문항·끝내지 못한 문항·검토에 남긴 시간을 같은 형식으로 기록해 시간 배분의 변화를 확인하세요.",
        "과목 우선순위": "과목별 계획 시간과 실제 사용 시간, 미완료 과제를 나눠 적어 우선순위 조정이 실행됐는지 확인하세요.",
        "복습 시작": "복습 예정일과 실제 시작일, 미룬 이유를 기록해 시작 지연이 줄었는지 확인하세요.",
        "서술형 구성": "서술형 답안의 근거·풀이 순서·표현 수정 전후를 남겨 구성 오류가 줄었는지 확인하세요.",
        "검토 절차": "검토 체크 항목과 실제 확인한 문항, 놓친 오류를 기록해 절차 누락이 줄었는지 확인하세요.",
        "누적 복습": "단원별 복습일·간격·재확인 결과를 기록해 이전 단원과의 연결이 유지되는지 확인하세요.",
        "과제 점검": "과제 제출·채점·수정·재확인 완료 여부를 나눠 적어 점검 누락이 줄었는지 확인하세요.",
        "시험 분석": "문항별 원인 분류와 보완 행동, 재풀이 결과를 함께 남겨 분석이 다음 계획으로 이어지는지 확인하세요.",
        "질문 습관": "막힌 지점·질문한 시점·설명 뒤 해결 여부를 나눠 적어 질문을 미루는 일이 줄었는지 확인하세요.",
        "과목 편차": "과목별 완료 범위·정답 근거·막힌 단원을 같은 기준으로 기록해 과목 간 격차가 줄었는지 확인하세요.",
        "집중 지속": "집중 구간·중단 시점·중단 이유·복귀 시간을 기록해 유지 가능한 집중 시간이 늘었는지 확인하세요.",
        "계획 과부하": "계획량·실제 완료량·이월 항목·조정 사유를 기록해 과도한 계획이 줄었는지 확인하세요.",
        "응용 출발점": "응용 문항의 첫 접근과 도움을 받은 단계, 혼자 다시 푼 결과를 나눠 적어 시작 단계의 막힘이 줄었는지 확인하세요.",
        "자기 설명": "개념·풀이를 혼자 설명한 부분과 도움 뒤 설명한 부분을 나눠 적어 스스로 설명할 수 있는 범위가 넓어졌는지 확인하세요.",
        "선행 공백": "선행 단원별 독립 해결·도움 필요·복습 필요 항목을 나눠 적어 기초 공백이 줄었는지 확인하세요.",
        "조건 해석": "문제 조건을 혼자 해석한 경우와 도움 뒤 수정한 경우를 나눠 적어 해석 오류가 줄었는지 확인하세요.",
        "난도 적응": "기본·변형·고난도 문항별 독립 해결과 도움 필요 단계를 나눠 적어 난도 변화에 적응하는지 확인하세요.",
        "오답 원인": "오답 원인을 스스로 분류한 경우와 도움 뒤 수정한 경우를 나눠 적어 같은 오류의 반복이 줄었는지 확인하세요.",
        "오답 기록": "오답마다 원인·교정 내용·재풀이 날짜와 결과가 모두 남았는지 기록해 오답 정리가 다음 학습으로 이어지는지 확인하세요.",
    }
    metric = metrics.get(topic)
    if not metric:
        raise ValueError(f"{context.path}: feedback metric missing for {topic}")
    return f"{context.locality} {context.grade} 학생은 학습 기록에 {metric}"


def diagnostic_evidence_sentence(context: Context, topic: str) -> str:
    student = f"{context.locality} {context.grade} 학생"
    evidence = {
        "시험 시간": "시험지에 문항별 소요 시간·미완료 문항·검토 여부를 표시해 시간 배분이 무너진 구간부터 다시 연습하세요.",
        "과목 우선순위": "최근 주간표에서 과목별 계획 시간·실제 사용 시간·미완료 과제를 대조해 우선순위가 뒤바뀐 원인을 찾으세요.",
        "복습 시작": "복습 예정일과 실제 시작일, 미룬 이유를 나란히 기록해 시작이 늦어진 구간부터 조정하세요.",
        "서술형 구성": "최근 서술형 답안에서 근거·풀이 순서·표현을 구분하고 수정이 필요한 부분을 다시 구성하세요.",
        "검토 절차": "답안에 검토 체크 항목과 실제 확인한 문항, 놓친 오류를 표시해 검토 절차가 빠진 지점을 찾으세요.",
        "누적 복습": "단원별 마지막 복습일과 재확인 결과를 대조해 이전 단원과의 연결이 끊긴 구간부터 다시 배치하세요.",
        "과제 점검": "과제의 제출·채점·수정·재확인 상태를 나눠 표시해 점검이 멈춘 단계부터 바로잡으세요.",
        "시험 분석": "시험지와 답안에서 문항별 단원·오답 원인·시간 사용을 구분하고 각 원인에 맞는 후속 행동을 정하세요.",
        "질문 습관": "막힌 지점과 질문한 시점, 설명 뒤 해결 여부를 기록해 질문을 미루거나 놓친 대목부터 점검하세요.",
        "과목 편차": "과목별 완료 범위·정답 근거·막힌 단원을 같은 기준으로 비교해 이해 차이가 큰 과목부터 보완하세요.",
        "집중 지속": "집중 시작·중단·복귀 시각과 중단 이유를 기록해 반복해서 흐름이 끊기는 구간을 조정하세요.",
        "계획 과부하": "계획량·실제 완료량·이월 항목을 대조해 수행 가능량을 넘어선 과제를 줄이거나 재배치하세요.",
        "응용 출발점": "응용 문항의 첫 접근과 도움을 받은 단계를 표시한 뒤 비슷한 문항을 혼자 시작할 수 있는지 확인하세요.",
        "자기 설명": "최근 문항의 개념과 풀이 근거를 책 없이 설명하게 하고 막히는 단계만 다시 학습하세요.",
        "선행 공백": "선행 단원별 독립 해결·도움 필요·복습 필요 항목을 나눠 기초 개념이 비어 있는 구간을 먼저 보완하세요.",
        "조건 해석": "문제의 조건·단위·예외 문구를 표시하고 풀이에 사용한 근거를 설명한 뒤 유사 문항으로 다시 확인하세요.",
        "난도 적응": "기본·변형·고난도 문항을 차례로 풀고 어느 단계부터 도움이 필요했는지 표시해 다음 연습 난도를 정하세요.",
        "오답 원인": "오답을 개념·조건 해석·계산·표현·시간 배분으로 나누고 같은 원인이 반복되는 문항을 다시 확인하세요.",
        "오답 기록": "각 오답에 원인·교정 내용·재풀이 날짜와 결과가 모두 남았는지 확인하고 빠진 단계를 보완하세요.",
    }
    action = evidence.get(topic)
    if not action:
        raise ValueError(f"{context.path}: diagnostic evidence missing for {topic}")
    return f"{student}은 {action}"


def metric_clause(value: str) -> str:
    value = value.strip()
    rewrites = {
        "상담 전 자료와 상담 후 행동 계획이 어떻게 달라졌는지 비교하는 것":
            "상담 전 자료와 상담 후 행동 계획의 차이를 비교했는지",
        "기록 후 계획이 어떻게 조정됐는지 추적하는 것":
            "기록 후 계획의 조정 이력을 추적하는지",
    }
    if value in rewrites:
        return rewrites[value]
    if value.endswith("것"):
        return value[:-1].rstrip() + "지 여부"
    return value + "인지 여부"


def rewrite_page_check_copy(flow: str, context: Context) -> tuple[str, int]:
    locality = re.escape(context.locality)
    patterns = (
        rf"{locality} 상담 기록의 마지막에는 (?P<metric>[^<.!?]{{8,180}}?것)을 점검 항목으로 남겨 보세요\.",
        rf"최종 점검표에는 {locality} 학생의 (?P<metric>[^<.!?]{{8,180}}?것)을 확인하도록 적습니다\.",
        rf"(?P<metric>[^<.!?]{{8,180}}?것)이 {locality} 페이지에서 이어서 확인할 핵심 기록입니다\.",
        rf"{locality} 학부모는 다음 상담 때 (?P<metric>[^<.!?]{{8,180}}?것)을 같은 기준으로 다시 확인하세요\.",
        rf"마지막에는 {locality} 학생의 (?P<metric>[^<.!?]{{8,180}}?것)을 핵심 확인 항목으로 정하는 편이 좋습니다\.",
        rf"{locality}에서 남겨 둘 기록은 (?P<metric>[^<.!?]{{8,180}}?것)을 다음 점검일에 대조할 수 있는 형태여야 합니다\.",
        rf"다음 계획을 정하기 전 {locality} 학생의 (?P<metric>[^<.!?]{{8,180}}?것)을 기록으로 확인합니다\.",
        rf"(?P<metric>[^<.!?]{{8,180}}?것)을 {locality} 상담의 공통 점검 항목으로 사용해 보세요\.",
    )
    total = 0
    for index, pattern_value in enumerate(patterns):
        def replace(match: re.Match[str], variant: int = index) -> str:
            clause = metric_clause(match.group("metric"))
            return choose(
                context,
                f"v2-page-check-{variant}",
                (
                    f"{context.locality} 상담 기록에는 {clause}를 다음 점검 항목으로 적어 두세요.",
                    f"다음 상담에서는 {context.locality} 학생의 기록을 보며 {clause}를 같은 기준으로 살펴보세요.",
                    f"{context.locality} 점검표는 {clause}를 한눈에 볼 수 있어야 합니다.",
                    f"{context.locality} 학생의 후속 계획을 정하기 전에 {clause}를 살펴보세요.",
                    f"{clause}가 {context.locality} 상담의 다음 판단 기준입니다.",
                    f"{context.locality}에서는 다음 점검에서도 {clause}를 살펴보고, 확인 결과를 앞선 기록과 같은 기준으로 대조하세요.",
                    f"다음 점검일에는 {clause}를 다시 살펴보고, 확인 결과를 앞선 계획·실제 기록과 대조하세요.",
                    f"{context.locality} 상담의 마지막 확인 항목은 {clause}입니다.",
                ),
            )

        flow, count = re.subn(pattern_value, replace, flow, count=1)
        total += count
    return flow, total


def polish_v2_copy(flow: str, context: Context) -> tuple[str, int]:
    total = 0

    # The inherited v1 template attached particles to a full ``...하는 것``
    # clause. Rewrite the complete sentence instead of trying to repair josa.
    flow, count = rewrite_page_check_copy(flow, context)
    total += count

    phrase_replacements = (
        (
            "방식이 실제 시간표에 반영되는지 확인하고",
            "방식이 실제 수업과 학습 계획에 반영되는지 확인하고",
        ),
        ("해당 안내 진단은", "진단 결과에는"),
        ("해당 안내이", "해당 안내가"),
        ("해당 안내가 적용되는 요일과 학습 단계", "학습 계획을 적용할 요일과 단계"),
        ("해당 안내 변화를 확인하려면", "학습 변화를 확인하려면"),
        ("해당 피드백", "학습 피드백"),
        ("오답 원인·오답 원인 구분", "오답 기록·오답 원인 구분"),
        ("오답 원인의 원인", "오답이 생긴 원인"),
        (
            "진단 결과를 단원명·재풀이 날짜·질문 수로 받아 진단 결과를 실제 학습 기록과",
            "진단 결과를 단원명·재풀이 날짜·질문 수로 받아 실제 학습 기록과",
        ),
        (
            "실제 적용 조건은 무엇을 포함하는지, 누가 확인하는지, 어떤 자료를 쓰는지와 예외로 구체화하세요.",
            "실제 적용 조건은 포함 범위, 담당자, 확인 자료, 예외 처리의 네 항목으로 구체화하세요.",
        ),
        (
            "통학 조건이 적용되는 요일과 학습 단계",
            "학습 활동을 실행할 요일과 단계",
        ),
        (
            "학습관리 항목이 적용되는 요일과 학습 단계",
            "학습 활동을 실행할 요일과 단계",
        ),
        (
            "통학 조건을 활용할 시점과 학습 단계",
            "학습 활동을 배치할 시점과 단계",
        ),
        (
            "학습관리 항목을 활용할 시점과 학습 단계",
            "학습 활동을 배치할 시점과 단계",
        ),
        (
            "통학 조건은 사례 비교가 아니라",
            "현재 계획은 다른 사례를 따르기보다",
        ),
        (
            "학습관리 항목은 사례 비교가 아니라",
            "현재 계획은 다른 사례를 따르기보다",
        ),
        (
            "학습관리 항목은 설명에 머물지 않고",
            "학습 계획은 설명에 머물지 않고",
        ),
        (
            "통학 조건은 설명에 머물지 않고",
            "학습 계획은 설명에 머물지 않고",
        ),
        (
            "학습관리 항목은 설명만이 아니라",
            "학습관리 안내는 설명만이 아니라",
        ),
        (
            "통학 조건을 살필 때",
            "통학 계획을 살필 때",
        ),
        (
            "학습관리 항목을 살필 때",
            "통학 계획을 살필 때",
        ),
        (
            "해당 일정과 단계를 학교·과제 시간 옆에 배치",
            "학습 활동의 요일과 단계를 학교·과제 시간 옆에 배치",
        ),
        ("해당 일정도 같은 표에서", "남은 복습 시간도 같은 표에서"),
        ("해당 조건이 그 일정과 맞는지", "수업 조건이 그 일정과 맞는지"),
        ("해당 기록에는", "학습 기록에는"),
        ("해당 안내는 설명만이 아니라", "학습관리 안내는 설명만이 아니라"),
        ("해당 안내 설명", "관련 설명"),
        (
            "학부모에게 완료·미완료·조정 사유를 구분해 공유하는 방식",
            "완료·미완료·조정 사유를 구분해 학부모에게 공유하는 방식",
        ),
        ("답안을 다섯 원인으로 분류해", "답안을 다섯 가지 원인으로 분류해"),
    )
    for before, after in phrase_replacements:
        count = flow.count(before)
        if count:
            flow = flow.replace(before, after)
            total += count

    flow, count = re.subn(
        r"(?P<persona>(?:예비고1|고[1-3]) [^<.!?]{2,100}? 유형)에게 필요한 "
        r"(?P<method>[^<.!?]{8,220}? 방식)이 실제 수업과 학습 계획에 반영되는지 확인하고",
        lambda match: (
            f"{match.group('persona')}에는 {match.group('method')}이 "
            "실제 수업과 학습 계획에 반영되는지 확인하고"
        ),
        flow,
    )
    total += count

    flow, count = re.subn(r"([.!?])(?=[가-힣“‘])", r"\1 ", flow)
    total += count

    flow, count = re.subn(
        r"(?P<prefix>[^<.!?]{2,80}? 상담에서) 답안을 원인별로 나눌 때 "
        r"오답 원인을 다섯 범주로 나눈 뒤",
        lambda match: f"{match.group('prefix')}는 오답을 다섯 범주로 나눈 뒤",
        flow,
    )
    total += count
    flow, count = re.subn(
        r"오답 기록을 원인별로 정리할 때 오답 기록을 원인별로 정리하고",
        "오답 기록을 원인별로 정리하고",
        flow,
    )
    total += count
    flow, count = re.subn(
        r"오답 원인을 설명하지 못한 대목부터 다시 설명하게",
        "오답의 원인을 말하지 못한 대목부터 풀이 근거를 다시 설명하게",
        flow,
    )
    total += count
    flow, count = re.subn(
        r"(?P<prefix>(?:최근 )?답안을 살필 때|답안을 원인별로 나눌 때) "
        r"(?:최근 )?답안을",
        lambda match: f"{match.group('prefix')} 이를",
        flow,
    )
    total += count
    flow, count = re.subn(
        r"막힌 지점을 질문으로 남기지 못한 (?P<noun>지점|부분|과정|대목|문항)",
        lambda match: f"질문으로 정리하지 못한 {match.group('noun')}",
        flow,
    )
    total += count

    feedback_pattern = (
        r"(?:예비고1|고[1-3]) [^<.!?]{2,100}? 유형의 기록에는 "
        r"혼자 해결한 문제와 도움 뒤 해결한 문제를 나눠 적어 "
        r"[^<.!?]{2,80}?의 변화를 확인하는 편이 좋습니다\."
    )
    flow, count = re.subn(
        feedback_pattern,
        feedback_metric_sentence(context),
        flow,
        count=1,
    )
    total += count

    school_exam_pattern = (
        rf"{re.escape(context.locality)}의 [^<.!?]{{2,120}}? 시험 준비에서는 "
        r"범위 확인일과 1차 학습 완료일을 구분합니다\."
    )
    flow, count = re.subn(
        school_exam_pattern,
        school_exam_reference(context),
        flow,
        count=1,
    )
    total += count

    flow, count = correct_geographic_scope_phrases(flow, context)
    total += count

    repeated_metric = "범위별 이해도, 오답 수, 재풀이 통과 여부를 주차별로 확인하는지 여부"
    flow, count = re.subn(
        re.escape(repeated_metric) + r"(?P<ending>입니다|를|가)",
        lambda match: {
            "입니다": "범위별 이해도·오답 수·재풀이 통과 결과를 주차별로 기록하는 일입니다",
            "를": "범위별 이해도·오답 수·재풀이 통과 결과가 주차별로 기록되는지를",
            "가": "범위별 이해도·오답 수·재풀이 통과 결과가 주차별로 기록되는지가",
        }[match.group("ending")],
        flow,
    )
    total += count

    registration_metric = "등록일, 시작 진도, 첫 점검일, 반 변경 기준을 한 번에 적어 두는지 여부"
    flow, count = re.subn(
        re.escape(registration_metric) + r"(?P<ending>입니다|를|가)",
        lambda match: {
            "입니다": "등록일·시작 진도·첫 점검일·반 변경 기준을 한 기록에 정리하는 일입니다",
            "를": "등록일·시작 진도·첫 점검일·반 변경 기준이 한 기록에 정리되는지를",
            "가": "등록일·시작 진도·첫 점검일·반 변경 기준이 한 기록에 정리되는지가",
        }[match.group("ending")],
        flow,
    )
    total += count

    # Repair every event-review variant that made a time phrase possess the
    # record instead of saying when the student left it.
    event_pattern = (
        rf"{re.escape(context.locality)} 학생의 "
        r"(?P<moment>[^<.!?]{4,140}?(?:때|시기|직후|기간|학기|시점|첫 주|주간|달)) "
        r"(?P<kind>실행 )?기록"
    )
    flow, count = re.subn(
        event_pattern,
        lambda match: (
            f"{context.locality} 학생이 {match.group('moment')}에 남긴 "
            f"{match.group('kind') or ''}기록"
        ),
        flow,
    )
    total += count

    # A method can itself begin with ``학부모에게``; avoid two consecutive
    # recipients when the surrounding template already starts with persona.
    double_recipient = re.compile(
        r"(?P<persona>(?:예비고1|고[1-3]) [^<.!?]{2,100}? 유형)에게 필요한 "
        r"학부모에게 완료·미완료·조정 사유를 구분해 공유하는 방식"
    )
    flow, count = double_recipient.subn(
        lambda match: (
            f"{match.group('persona')}의 완료·미완료·조정 사유를 "
            "구분해 학부모에게 공유하는 방식"
        ),
        flow,
    )
    total += count

    # Rewrite the inherited ``{topic} 문제가 드러난 문항`` construction.
    problem_pattern = re.compile(
        r"(?P<persona>(?:예비고1|고[1-3]) [^<.!?]{2,100}? 유형)에는 "
        r"문제 수를 늘리기보다 (?P<topic>[^<.!?]{2,40}?) 문제가 드러난 "
        r"문항을 설명하고 비슷한 문제를 다시 풀게 하는 과정이 필요합니다\."
    )

    def replace_problem(match: re.Match[str]) -> str:
        return diagnostic_evidence_sentence(
            context, match.group("topic").strip()
        )

    flow, count = problem_pattern.subn(replace_problem, flow)
    total += count
    return flow, total


def refine_keyword_scope(flow: str, context: Context) -> tuple[str, int, int]:
    section_re = re.compile(
        r'<section\s+class="subject-copy-section"><h2>(?P<heading>.*?)</h2>(?P<body>.*?)</section>',
        re.S,
    )
    paragraph_re = re.compile(r"<p>.*?</p>", re.S)
    expected_dedicated_sections = sum(
        context.keyword in clean(match.group("heading"))
        for match in section_re.finditer(flow)
    )
    dedicated_limit = 3 if expected_dedicated_sections == 1 else 2
    dedicated_sections = 0
    total_changes = 0
    keyword_reductions = 0

    def replace_section(match: re.Match[str]) -> str:
        nonlocal dedicated_sections, total_changes, keyword_reductions
        heading = clean(match.group("heading"))
        section = match.group(0)
        if context.keyword not in heading:
            role = section_role(heading)
            section, changes, reductions = neutralize_keyword_reference(
                section, context, role
            )
            total_changes += changes
            keyword_reductions += reductions
            if context.keyword in clean(section):
                raise ValueError(f"{context.path}: keyword remains outside dedicated section")
            return section

        dedicated_sections += 1
        body = match.group("body")
        while clean(match.group("heading") + body).count(context.keyword) > dedicated_limit:
            changed = False
            for paragraph in reversed(list(paragraph_re.finditer(body))):
                paragraph_source = body[paragraph.start() : paragraph.end()]
                updated, count = replace_keyword_reference_preserving_anchor(
                    paragraph_source, context
                )
                if count:
                    body = body[: paragraph.start()] + updated + body[paragraph.end() :]
                    total_changes += count
                    keyword_reductions += count
                    changed = True
                    break
            if not changed:
                raise ValueError(f"{context.path}: cannot reduce dedicated keyword density")
        body_start = match.start("body") - match.start()
        body_end = match.end("body") - match.start()
        return section[:body_start] + body + section[body_end:]

    flow = section_re.sub(replace_section, flow)
    if dedicated_sections not in {1, 2}:
        raise ValueError(f"{context.path}: dedicated keyword sections={dedicated_sections}")

    phrase_replacements = (
        ("때은", "때에는"),
        ("시기은", "시기에는"),
        ("직후은", "직후에는"),
        ("니다 따라서", "니다. 따라서"),
        ("니다 그러므로", "니다. 그러므로"),
        ("니다 실제 적용", "니다. 실제 적용"),
    )
    for before, after in phrase_replacements:
        count = flow.count(before)
        if count:
            flow = flow.replace(before, after)
            total_changes += count

    def rewrite_moment(match: re.Match[str]) -> str:
        moment = match.group("moment").strip()
        method = match.group("method").strip()
        return (
            f"{context.locality} {context.grade} 학생은 {moment}에 {method}을 적용하고, "
            "남은 과제는 중요도에 따라 핵심과 보류 항목으로 다시 나누는 편이 좋습니다."
        )

    flow, count = re.subn(
        r"(?P<persona>(?:예비고1|고[1-3]) [^<.!?]{2,100}? 유형)에게 "
        r"(?P<moment>[^<.!?]{4,100}?(?:때|시기|직후))에는 "
        r"(?P<method>[^<.!?]{8,220}? 방식)을 실행할 시점입니다\. "
        r"남은 과제는 중요도에 따라 핵심과 보류 항목으로 다시 나누세요\.",
        rewrite_moment,
        flow,
    )
    total_changes += count

    def rewrite_reason(match: re.Match[str]) -> str:
        topic = match.group("topic").strip()
        return (
            f"진도 속도보다 {topic_reason(topic)}를 "
            "찾고 수정하는 절차"
        )

    flow, count = re.subn(
        r"진도 속도보다 (?P<topic>[^<.!?]{2,40}?)의 원인을 발견하고 수정하는 절차",
        rewrite_reason,
        flow,
    )
    total_changes += count
    def rewrite_error_classification(match: re.Match[str]) -> str:
        topic = match.group("topic").strip()
        descriptor = topic_item(topic)
        return choose(
            context,
            "v2-error-classification",
            (
                f"오답을 개념, 조건 해석, 적용, 계산·표현, 시간 배분으로 나누면 {descriptor} 지점을 구체적으로 찾기 쉽습니다.",
                f"답안을 다섯 원인으로 분류해 {descriptor} 부분을 첫 보완 항목으로 정하세요.",
                f"개념·조건 해석·적용·계산·시간 배분으로 오답을 구분하면 {descriptor} 과정이 반복되는지 확인할 수 있습니다.",
                f"오답 원인을 다섯 범주로 나눈 뒤 {descriptor} 대목부터 다시 설명하게 하는 편이 좋습니다.",
                f"최근 답안을 원인별로 표시하면 {descriptor} 부분과 단순 실수를 구분하기 쉬워집니다.",
                f"개념부터 시간 배분까지 오답을 나누어 {descriptor} 지점을 다음 복습 범위로 정해 보세요.",
                f"오답 기록을 원인별로 정리하고 {descriptor} 부분이 재풀이에서도 나타나는지 확인하세요.",
                f"다섯 가지 오답 원인을 대조하면 {descriptor} 지점에 필요한 다음 행동을 구체적으로 정할 수 있습니다.",
            ),
        )

    flow, count = re.subn(
        r"오답을 개념, 조건 해석, 적용, 계산·표현, 시간 배분으로 나누면 "
        r"(?P<topic>[^<.!?]{2,40}?) 문제가 생기는 지점을 설명할 수 있습니다\.",
        rewrite_error_classification,
        flow,
    )
    total_changes += count
    flow, count = polish_v2_copy(flow, context)
    total_changes += count
    return flow, total_changes, keyword_reductions


def rewrite_flow(flow: str, context: Context) -> tuple[str, int, int, int]:
    if MARKER in flow:
        return flow, 0, 0, 0
    if LEGACY_MARKER in flow:
        flow = flow.replace(LEGACY_MARKER, "", 1).lstrip()
        school_fixes = 0
        if school_mismatch(flow, context):
            school_pattern = (
                rf"{re.escape(context.locality)} 자료에 기재된 학교는 "
                rf"[^<>.!?]{{1,160}}?이며, [^<>.!?]{{4,180}}?\."
            )
            match = re.search(school_pattern, flow)
            if not match:
                raise ValueError(f"{context.path}: mismatched school sentence missing")
            flow = (
                flow[: match.start()]
                + corrected_school_copy(context)
                + flow[match.end() :]
            )
            school_fixes = 1
        flow, refinements, keyword_reductions = refine_keyword_scope(flow, context)
        keyword_marker = f"<!-- high-student-secondary-keyword:{context.keyword} -->"
        return MARKER + "\n" + keyword_marker + "\n" + flow, refinements, school_fixes, keyword_reductions

    locality = context.locality
    area = context.area
    grade = context.grade
    persona = context.persona
    student = f"{locality} {grade} 학생"
    keyword = context.keyword
    keyword_subject = particle(keyword, "은", "는")
    keyword_object = particle(keyword, "을", "를")
    replacements = 0
    school_fixes = 0

    legacy_method = legacy_method_from_flow(flow, context)
    intended_method = method_for_secondary_challenge(context)
    if legacy_method != intended_method:
        method_count = flow.count(legacy_method)
        flow = flow.replace(legacy_method, intended_method)
        replacements += method_count

    def literal(before: str, after: str) -> None:
        nonlocal flow, replacements
        flow, count = replace_literal(flow, before, after)
        replacements += count

    def pattern(pattern_value: str, salt: str, build) -> None:
        nonlocal flow, replacements
        match = re.search(pattern_value, flow, re.S)
        if not match:
            return
        replacement = build(match, salt)
        flow = flow[: match.start()] + replacement + flow[match.end() :]
        replacements += 1

    if school_mismatch(flow, context):
        school_pattern = (
            rf"{re.escape(locality)} 자료에 기재된 학교는 "
            rf"[^<>.!?]{{1,160}}?이며, [^<>.!?]{{4,180}}?\."
        )
        match = re.search(school_pattern, flow)
        if not match:
            raise ValueError(f"{context.path}: mismatched school sentence missing")
        flow = flow[: match.start()] + corrected_school_copy(context) + flow[match.end() :]
        school_fixes = 1

    literal(
        f"{locality} {grade} 학생의 주간 계획은 학교 일정과 고정 수업을 먼저 적고 남은 시간에 과목별 완료 기준을 배치하는 순서가 좋습니다.",
        choose(
            context,
            "weekly-plan",
            (
                f"{locality} {grade} 주간표에는 학교 일정과 고정 수업을 먼저 표시하고, 남는 시간마다 끝낼 단원과 문항 기준을 적어 두는 편이 좋습니다.",
                f"학교 일정이 정해진 뒤 {locality} {grade} 학생이 활용할 수 있는 시간을 계산하고 과목별 완료 기준을 작은 단위로 배치하세요.",
                f"{locality} {grade} 학생의 계획은 하교·수업 같은 고정 시간을 제외한 뒤, 남은 구간에 과목별 결과물을 넣어야 실행하기 쉽습니다.",
                f"주간 학습량을 정할 때는 {locality} {grade} 학생의 학교 일정부터 잠그고 남은 시간에 단원·문항·오답 완료 기준을 나누어 넣으세요.",
                f"{locality} {grade} 주간 계획에서는 시간을 채우는 것보다 학교 일정 뒤 실제로 끝낼 수 있는 과제를 과목별로 정하는 일이 먼저입니다.",
                f"고정 수업과 학교 행사를 먼저 적은 다음 {locality} {grade} 학생의 빈 시간에 과목별 학습 결과를 배치하면 미완료 원인을 찾기 쉽습니다.",
                f"{locality} {grade} 학생은 학교 일정·이동 시간을 먼저 반영하고, 남은 구간마다 완료할 단원과 재풀이 항목을 구체적으로 적는 편이 좋습니다.",
                f"한 주 계획을 세울 때 {locality} {grade} 학생의 고정 일정을 먼저 빼고, 실제 학습 가능 시간에 과목별 완료 기준을 맞춰 보세요.",
                f"{locality} {grade} 주간표는 학교와 수업 시간을 바탕으로 만들고, 각 빈 구간에는 공부 시간보다 끝낼 문제와 확인 항목을 적어야 합니다.",
                f"학교 일정에 변수가 많은 {locality} {grade} 학생은 고정 시간을 먼저 정리한 뒤 남은 구간을 과목별 작은 과제로 나누는 것이 현실적입니다.",
                f"{locality} {grade} 학생의 주간표에는 반드시 해야 하는 일정과 조정 가능한 공부를 구분하고, 후자에 단원별 완료 기준을 붙이세요.",
                f"과목별 공부를 배치하기 전 {locality} {grade} 학생의 학교·이동·고정 수업 시간을 먼저 계산해야 실제 가능한 계획이 됩니다.",
            ),
        ),
    )
    literal(
        f"{area} {locality}에서 고등학생학원을 고를 때는 지도상의 거리보다 평일 하교, 이동, 식사, 귀가까지 이어지는 실제 시간을 계산하는 편이 현실적입니다.",
        choose(
            context,
            "commute-plan",
            (
                f"{area} {locality}에서 고등학생학원을 비교할 때는 거리 숫자만 보지 말고 하교부터 식사·등원·귀가까지 걸리는 시간을 실제 요일별로 계산하세요.",
                f"{locality} 통학 가능성은 지도상의 거리보다 평일 학교 종료 뒤 이동과 식사, 수업 후 귀가가 한 일정 안에 들어오는지로 판단하는 편이 정확합니다.",
                f"{area} {locality} 학생은 하교 시각과 이동 수단, 식사 시간, 늦은 귀가 방법을 이어서 적어 봐야 꾸준한 등원 가능성을 알 수 있습니다.",
                f"고등학생의 동선은 단순 거리가 아니라 실제 하교 시간대의 이동·식사·수업·귀가 순서로 확인해야 합니다. {locality}에서도 같은 기준을 적용하세요.",
                f"{locality}에서 학원을 알아볼 때에는 학교 또는 집에서 출발하는 시각부터 수업 종료 후 귀가까지 한 번에 계산해 보는 것이 좋습니다.",
                f"{area} {locality}의 통학 계획에는 하교 지연과 식사, 이동, 귀가 연락 방법까지 포함해야 반복 가능한 일정인지 판단할 수 있습니다.",
                f"지도에 표시된 분 수보다 {locality} 학생이 자주 다닐 요일의 하교·이동·식사·귀가 시간을 직접 대조하는 편이 현실적입니다.",
                f"{locality} 고등학생학원 방문 전에는 실제 평일 동선을 기준으로 학교 종료부터 귀가까지 걸리는 시간을 순서대로 적어 보세요.",
                f"{area} {locality}에서 등원 부담을 보려면 거리뿐 아니라 학교 일정 뒤 남는 시간과 수업 종료 후 귀가 방법을 함께 확인해야 합니다.",
                f"{locality} 학생의 이동 가능 시간은 학교 종료 시각마다 달라집니다. 식사와 등원, 귀가까지 포함한 요일별 일정을 먼저 만들어 보세요.",
                f"통학 거리가 짧아도 하교·식사·귀가가 맞지 않으면 계획을 유지하기 어렵습니다. {locality}의 실제 생활 시간표로 확인하세요.",
                f"{area} {locality} 학원 선택에서는 지도 거리와 실제 소요 시간을 구분하고, 늦은 수업 뒤 귀가 방식까지 미리 점검하는 편이 좋습니다.",
            ),
        ),
    )
    literal(
        f"{persona}에는 “두 시간 공부”보다 단원, 문항 수, 질문, 오답 재풀이 날짜를 적은 작은 과제가 더 분명합니다.",
        choose(
            context,
            "measurable-task",
            (
                f"{student}의 과제는 ‘두 시간 공부’처럼 시간만 적기보다 단원·문항·질문과 오답 재풀이 날짜까지 남겨야 완료 여부를 판단할 수 있습니다.",
                f"공부 시간을 길게 잡는 것보다 {student}에게 오늘 끝낼 단원과 문항, 질문 목록, 다시 풀 날짜를 정해 주는 편이 구체적입니다.",
                f"{student}은 시간 목표만 세우기보다 단원 범위와 문항 수, 질문할 내용, 오답을 다시 볼 날짜를 각각 적는 것이 좋습니다.",
                f"{student}의 주간표에는 ‘몇 시간’ 대신 끝낼 단원·문항과 질문, 재풀이 시점을 기록해 실행 결과가 보이게 하세요.",
                f"완료 기준이 필요한 {student}에게는 공부 시간보다 단원명, 풀 문제 수, 질문 항목과 오답 확인일이 더 유용합니다.",
                f"{student}의 작은 과제는 시작 시각이 아니라 끝낼 범위·문항·질문과 다음 오답 점검일로 표현하는 편이 분명합니다.",
                f"두 시간이라는 목표를 세우기 전에 {student}이 마칠 단원과 문제, 남길 질문, 다시 볼 오답 날짜를 먼저 정하세요.",
                f"{student}에게는 학습 시간을 채우는 목표보다 단원·문항·질문·재풀이 날짜가 들어간 완료 목록이 실행하기 쉽습니다.",
            ),
        ),
    )
    pattern(
        rf"{re.escape(persona)}에게는 ([^<.!?]{{4,100}}?)에 ([^<.!?]{{8,240}}? 방식)을 쓰되, 미완료가 생기면 핵심 과제와 보류 과제를 나눠야 합니다\.",
        "weekly-method",
        lambda match, salt: choose(
            context,
            salt,
            (
                f"{student}은 {match.group(1)}에 {match.group(2)}을 적용하고, 끝내지 못한 경우에는 필수 과제와 다음 순서로 넘길 과제를 구분해야 합니다.",
                f"{match.group(1)}에는 {student}에게 {match.group(2)}을 사용하되, 미완료 항목은 원인을 확인해 핵심 과제와 보류 과제로 나누세요.",
                f"{student}의 계획에는 {match.group(1)}에 실행할 {match.group(2)}과 미완료 시 줄이거나 미룰 기준이 함께 있어야 합니다.",
                f"{match.group(1)}에 {match.group(2)}을 적용한 뒤 {student}이 끝내지 못한 과제는 우선 완료할 것과 재배치할 것으로 구분합니다.",
                f"{student}은 {match.group(1)}에 {match.group(2)}을 실행하고, 남은 과제는 중요도에 따라 핵심과 보류 항목으로 다시 나누는 편이 좋습니다.",
                f"{match.group(1)}에 사용할 {match.group(2)}을 정하고, {student}에게 미완료가 생기면 분량을 필수 과제와 이후 과제로 조정합니다.",
                f"{student}은 {match.group(1)}에 {match.group(2)}을 시도한 기록을 남기고, 미완료 내용은 다음 계획에서 핵심·보류로 분리하는 편이 좋습니다.",
                f"{match.group(1)}에 맞춘 {match.group(2)}이 실제로 실행되는지 본 뒤 {student}에게 남은 과제를 유지·조정 항목으로 나누세요.",
            ),
        ),
    )
    literal(
        f"{persona}에는 적용 기준이 필요합니다.",
        choose(
            context,
            "application-rule",
            (
                f"{student}에게 적용할 조건은 현재 답안과 주간 기록으로 구체화해야 합니다.",
                f"이 안내가 {student}에게 맞는지는 실행 자료와 점검 시점으로 확인해야 합니다.",
                f"{student}의 적용 기준은 수업 전 기록과 첫 점검 결과를 함께 보고 정하는 편이 좋습니다.",
                f"같은 안내라도 {student}의 현재 약점과 일정에 맞는 적용 범위를 따로 확인해야 합니다.",
                f"{student}에게 필요한 조건은 최근 시험지와 계획 실행 기록을 근거로 구분하세요.",
                f"실제 적용 여부는 {student}의 현재 자료와 첫 주 실행 결과를 대조해 판단합니다.",
                f"{student}에게는 설명보다 적용 조건, 확인 자료, 조정 시점이 분명해야 합니다.",
                f"이 조건은 {student}의 학습 기록과 생활 일정 안에서 실행 가능한지 확인해야 합니다.",
            ),
        ),
    )
    literal(
        f"{locality} 고등학생학원 상담 전에는 진단 방식, 수업 인원, 과제·오답 확인, 결석·보강 처리, 비용 항목, 보호자 피드백을 한 표에서 비교해야 합니다.",
        choose(
            context,
            "comparison-table",
            (
                f"{locality} 고등학생학원 비교표에는 진단, 수업 인원, 과제·오답, 결석·보강, 비용, 보호자 피드백의 여섯 항목을 같은 순서로 적어 보세요.",
                f"상담 답변을 비교하려면 {locality}에서 진단 방법부터 인원·과제·오답·보강·비용·보호자 전달 방식까지 한 표에 모으는 편이 좋습니다.",
                f"{locality} 고등학생학원을 알아볼 때는 각 상담의 진단 자료, 수업 인원, 과제 확인, 보강 조건, 비용 항목과 피드백 시점을 나란히 정리하세요.",
                f"같은 기준으로 비교할 수 있도록 {locality} 상담 전에 진단·인원·과제와 오답·결석 처리·비용·보호자 피드백 칸을 만들어 두세요.",
                f"{locality} 학부모는 수업 설명을 들을 때 진단 방식, 질문 가능 인원, 과제·오답 확인, 보강, 비용과 피드백 범위를 표로 남기는 편이 정확합니다.",
                f"고등학생학원 선택표는 {locality} 상담별로 진단 자료와 수업 규모, 과제·오답, 결석 대응, 비용, 가정 전달 방식을 구분해 적어야 합니다.",
                f"{locality} 상담 내용을 기억에만 의존하지 말고 진단·인원·과제·오답·보강·비용·피드백을 동일한 여섯 칸으로 비교해 보세요.",
                f"수업 조건을 대조할 때 {locality}에서는 진단부터 보호자 피드백까지 같은 질문을 사용하고, 답변은 비용과 예외 처리까지 함께 기록하세요.",
            ),
        ),
    )
    literal(
        f"{area} {locality}에서 수업을 시작한 뒤에는 첫 점검일을 정해 진도, 질문, 오답, 통학 부담이 예상과 달랐는지 살피고 특정 결과를 미리 단정하지 않아야 합니다.",
        choose(
            context,
            "first-review",
            (
                f"{area} {locality}에서 수업을 시작하면 첫 점검일을 미리 정하고 진도·질문·오답·통학 기록을 처음 예상과 대조해 계획을 조정하세요.",
                f"등록 뒤에는 {locality} 학생의 첫 점검 날짜를 잡아 실제 진도와 질문, 반복 오답, 이동 부담이 상담 내용과 맞는지 확인해야 합니다.",
                f"{locality} 수업의 초기 판단은 결과를 예측하기보다 정해 둔 날에 진도·질문·오답·통학 부담을 다시 확인하는 방식이 안전합니다.",
                f"첫 수업 전에 재점검 시점을 정하고 {area} {locality} 학생의 진도, 질문 기록, 오답 재발과 이동 부담을 그날 함께 살펴보세요.",
                f"{locality}에서 시작한 계획은 첫 확인일에 진도와 질문의 변화, 오답, 통학 피로를 점검한 뒤 유지하거나 수정해야 합니다.",
                f"수업 시작 직후 결과를 단정하지 말고 {locality} 학생의 첫 점검일에 실제 진도·질문·오답·동선 기록을 모아 판단하세요.",
                f"{area} {locality} 학부모는 등록 당시 예상과 첫 점검일까지의 진도, 질문, 오답, 통학 부담을 나란히 놓고 차이를 확인하는 편이 좋습니다.",
                f"{locality} 수업의 적합성은 첫 인상보다 정해 둔 점검일의 진도·질문·오답·이동 기록을 근거로 조정하는 것이 좋습니다.",
            ),
        ),
    )
    pattern(
        rf"{re.escape(area)} {re.escape(locality)} 생활 일정에 맞춘 계획 안에서 {re.escape(keyword)}(?:은|는) 어느 요일과 단계에 적용되는지 보여야 실제 도움을 체감할 수 있습니다\.",
        "keyword-schedule",
        lambda _match, salt: choose(
            context,
            salt,
            (
                f"{area} {locality}의 생활표에는 {keyword}{particle(keyword, '이', '가')} 적용되는 요일과 학습 단계를 표시해 실제 실행 가능성을 확인하세요.",
                f"{keyword} 계획은 {locality} 학생의 어느 요일, 어떤 학습 단계에서 실행되는지 주간표 안에 구체적으로 보여야 합니다.",
                f"{area} {locality} 일정에 {keyword}{keyword_object} 배치해 보고 학교 과제와 복습 사이에서 실제로 유지할 수 있는지 살펴보세요.",
                f"{locality} 학생의 생활 일정과 연결하려면 {keyword} 적용 요일, 시작 조건, 완료 기준을 계획표에 나누어 적는 편이 좋습니다.",
                f"{keyword}{keyword_subject} 설명에 머물지 않고 {area} {locality} 학생의 주간 일정 속 어느 구간에서 실행되는지 확인해야 합니다.",
                f"{locality} 계획에서는 {keyword} 일정과 단계를 학교·과제 시간 옆에 배치해 실제 학습 흐름과 맞는지 대조하세요.",
                f"{area} {locality} 학생이 {keyword}{keyword_object} 활용할 시점과 학습 단계를 정하고, 주간표에서 겹치는 일정이 없는지 확인합니다.",
                f"{keyword} 안내를 들은 뒤 {locality} 생활표에 요일과 실행 단계를 직접 넣어 보아야 지속 가능한 계획인지 판단할 수 있습니다.",
            ),
        ),
    )
    literal(
        f"{keyword} 관련 안내에서는",
        choose(
            context,
            "keyword-detail-prefix",
            (
                "이 안내의 실제 범위를 확인할 때는",
                f"{locality} 상담에서 운영 내용을 살펴볼 때는",
                "말로 들은 설명을 자료와 대조할 때는",
                "상담 조건을 구체적으로 비교할 때는",
                f"{keyword} 설명이 실제 과정과 맞는지 볼 때는",
                "학생에게 적용될 범위를 확인할 때는",
                f"{locality}에서 같은 질문으로 비교할 때는",
                "실제 제공되는 절차를 확인할 때는",
            ),
        ),
    )
    literal(
        f"{keyword}{keyword_object} 포함 범위·담당자·확인 자료·예외 처리로 구체화하세요.",
        choose(
            context,
            "keyword-final-scope",
            (
                "해당 안내의 포함 범위와 담당자, 확인 자료, 예외 처리까지 구체적으로 적어 두세요.",
                "이 조건은 제공 범위·담당자·근거 자료·예외 상황의 네 항목으로 나누어 확인하세요.",
                f"{locality} 상담표에는 적용 범위와 담당자, 확인 자료, 달라질 수 있는 조건을 구분해 적으세요.",
                "안내된 내용을 포함 범위·담당자·확인 방법·예외 처리로 나누면 비교가 쉬워집니다.",
                "실제 적용 조건은 무엇을 포함하는지, 누가 확인하는지, 어떤 자료를 쓰는지와 예외로 구체화하세요.",
                f"{keyword} 조건을 제공 범위와 담당자, 확인 자료, 예외 처리로 나누어 기록하세요.",
                "상담 답변은 적용 범위·담당 주체·근거 자료·예외 상황이 보이도록 정리하는 편이 좋습니다.",
                "이 안내가 달라지는 경우까지 확인해 범위, 담당자, 자료와 예외를 한 표에 남기세요.",
            ),
        ),
    )
    literal(
        f"{locality} 상담에서 {persona}{particle(persona, '을', '를')} 진단할 때는 점수 한 줄보다 최근 시험지, 학교 과제, 사용 교재, 오답 흔적, 주간 시간표를 함께 봐야 합니다.",
        choose(
            context,
            "diagnostic-evidence",
            (
                f"{locality} 상담에서 {student}의 현재 상태를 보려면 점수만 말하기보다 최근 시험지·학교 과제·교재·오답·주간표를 함께 펼쳐야 합니다.",
                f"{student}의 진단에는 한 번의 성적보다 최근 시험지와 과제, 사용 교재, 오답 흔적, 실제 시간표가 필요합니다.",
                f"점수 한 줄로 {student}의 학습 원인을 정하지 말고 {locality} 상담에 최근 답안·과제·교재·오답 기록·주간 일정을 가져가세요.",
                f"{locality}에서 {grade} 학생의 현재 상태를 살필 때는 성적표와 함께 최근 시험지, 학교 과제, 현재 교재, 오답과 주간 시간표를 대조하는 편이 좋습니다.",
                f"{student}의 학습 원인은 점수보다 최근 자료의 흐름에서 잘 보입니다. {locality} 상담에서는 시험지·과제·교재·오답·주간표를 같이 확인하세요.",
                f"{locality} 상담 자료는 성적 한 줄에 그치지 않고 {student}의 최근 시험 답안, 과제, 교재 진도, 오답 흔적과 실제 일정까지 포함해야 합니다.",
                f"최근 시험지와 학교 과제, 교재, 오답, 주간표를 한자리에서 보면 {student}이 막히는 지점을 점수보다 구체적으로 구분할 수 있습니다.",
                f"{locality} 학부모는 {student}의 학습 상태를 진단하기 전에 최근 성적뿐 아니라 답안과 과제, 교재 사용 흔적, 오답 기록, 한 주 일정을 준비하는 편이 좋습니다.",
            ),
        ),
    )
    pattern(
        rf"{re.escape(persona)}에는 통학 뒤 남는 복습 시간까지 넣은 주간표가 필요하므로, {re.escape(keyword)}(?:을|를) 비교할 때 주소와 학교명만으로 판단하지 않는 것이 좋습니다\.",
        "commute-study-balance",
        lambda _match, salt: choose(
            context,
            salt,
            (
                f"{student}은 통학 후 확보되는 복습 시간을 주간표에 넣어야 하므로, {keyword} 비교도 주소와 학교명만으로 끝내지 마세요.",
                f"주소와 학교 정보는 출발점일 뿐입니다. {student}이 통학한 뒤 실제 복습 시간이 남는지 확인하며 {keyword}{keyword_object} 비교하세요.",
                f"{student}에게는 등원 후 남는 자습·복습 시간이 중요하므로 {keyword} 상담에서 학교명과 위치 외에 주간 학습 가능 시간을 물어야 합니다.",
                f"{keyword}{keyword_object} 살필 때 {student}의 학교 일정과 통학 뒤 복습 시간을 함께 계산해야 주소 정보가 실제 계획으로 이어집니다.",
                f"{student}의 주간표에 이동과 귀가, 남은 복습 시간을 넣은 뒤 {keyword} 조건이 그 일정과 맞는지 확인하는 편이 좋습니다.",
                f"통학이 가능해 보여도 {student}의 복습 시간이 사라질 수 있습니다. {keyword} 비교표에는 주소·학교와 함께 남는 학습 시간을 적으세요.",
                f"{student}의 등원 계획은 학교명보다 통학 후 확보되는 복습 시간으로 판단하고, {keyword} 일정도 같은 표에서 대조하세요.",
                f"{keyword} 선택에서는 {student}이 통학한 뒤 복습 구간이 실제로 남는지를 먼저 계산해 위치와 학교 정보의 적합성을 확인합니다.",
            ),
        ),
    )
    literal(
        f"{locality} 학부모가 받을 피드백은 “잘함”이나 “부족함”보다 완료 단원, 미완료 과제, 반복 오답, 다음 조정을 구분한 내용이어야 합니다.",
        choose(
            context,
            "parent-feedback",
            (
                f"{locality} 학부모 피드백에는 막연한 평가보다 완료 단원, 남은 과제, 반복 오답과 다음 조정을 항목별로 구분해 적는 편이 좋습니다.",
                f"‘잘함·부족함’만 전달받기보다 {locality} 가정에서는 완료 범위와 미완료 이유, 반복 오류, 다음 변경 내용을 나누어 확인하세요.",
                f"{locality} 학생의 피드백은 평가 표현보다 끝낸 단원, 미완료 과제, 반복된 오답, 다음 주 조정이 보이도록 구성되어야 합니다.",
                f"학부모가 계획을 이해하려면 {locality} 수업 기록에 완료·미완료·반복 오답·다음 행동이 각각 표시되어야 합니다.",
                f"{locality} 가정에 전달되는 내용은 ‘잘했다’는 말보다 어떤 단원을 마쳤고 무엇이 남았으며 다음에 무엇을 바꿀지가 구체적이어야 합니다.",
                f"완료 단원과 남은 과제, 다시 나온 오답, 다음 조정을 구분한 기록이 {locality} 학부모에게 더 실용적인 피드백이 됩니다.",
                f"{locality} 학부모는 수업 평가를 받을 때 완료 범위·미완료 항목·반복 오류·조정 계획의 네 부분이 분리되어 있는지 확인하세요.",
                f"감상형 피드백보다 {locality} 학생이 끝낸 내용과 남긴 오답, 미완료 이유, 다음 수정 계획이 기록으로 전달되는 편이 좋습니다.",
            ),
        ),
    )
    literal(
        f"{keyword} 안내는 담당자, 전달 시점, 확인 자료가 분명해야 하며 계획·실행·원인·다음 행동이 일관되게 전달되는지가 중요합니다.",
        choose(
            context,
            "keyword-feedback",
            (
                f"{keyword} 안내에서는 누가 언제 어떤 자료로 확인하는지와 계획·실행·원인·다음 행동이 한 기록 안에서 이어지는지를 살펴보세요.",
                f"담당자와 전달 시점, 확인 자료가 정해져 있어야 {keyword} 계획이 실행 결과와 원인, 다음 조정으로 연결될 수 있습니다.",
                f"{keyword}{keyword_subject} 설명만이 아니라 담당자·확인 시점·근거 자료와 다음 행동까지 같은 흐름으로 전달되어야 합니다.",
                f"{keyword} 기록에는 계획한 일, 실제 실행, 미완료 원인, 다음 변경과 이를 확인할 담당자·시점이 함께 보여야 합니다.",
                f"담당자와 점검 주기, 사용하는 자료를 먼저 확인하고 {keyword} 피드백이 계획에서 다음 행동까지 연결되는지 살펴보세요.",
                f"{keyword} 안내를 비교할 때는 전달 문구보다 담당자, 시점, 근거 자료, 실행 원인과 다음 조정이 일관적인지를 보는 편이 좋습니다.",
                "누가 어떤 자료를 언제 확인하는지가 분명해야 학습 기록에서 계획·실행 결과·원인·다음 행동을 연속해서 볼 수 있습니다.",
                f"{keyword}{keyword_object} 실제 관리와 연결하려면 담당자, 전달일, 확인 자료와 계획 수정 과정이 기록으로 남아야 합니다.",
            ),
        ),
    )
    literal(
        f"{area} {locality} 가정에서는 주 1회 이 기록을 보고 학생이 다음 목표를 설명하게 하면 감정적인 재촉을 줄이고 자기 점검을 늘릴 수 있습니다.",
        choose(
            context,
            "weekly-family-review",
            (
                f"{area} {locality} 가정은 일주일에 한 번 이 기록을 함께 보고 학생이 다음 목표를 직접 말하게 해 자기 점검의 근거로 사용할 수 있습니다.",
                f"주 1회 {locality} 학생이 기록을 설명하고 다음 행동을 정하게 하면 학부모의 재촉보다 구체적인 점검 대화가 가능합니다.",
                f"{locality} 가정에서는 이 기록을 매주 같은 날 확인하고 학생이 다음 주 목표와 조정 이유를 자신의 말로 정리하게 해 보세요.",
                f"감정적인 확인을 줄이려면 {area} {locality} 학부모가 주 1회 기록을 보고 학생에게 다음 목표를 설명하도록 요청하는 편이 좋습니다.",
                f"{locality} 학생과 일주일에 한 번 완료·미완료 기록을 검토한 뒤 다음 목표를 직접 고르게 하면 자기 점검 흐름을 만들 수 있습니다.",
                f"이 기록은 {area} {locality} 가정에서 매주 짧게 확인하고 학생이 다음 행동을 설명하는 자료로 활용하는 것이 좋습니다.",
                f"{locality} 학부모는 주간 기록을 근거로 질문하고 학생은 다음 목표를 말하게 하여 막연한 재촉을 구체적인 점검으로 바꿀 수 있습니다.",
                f"매주 한 번 {locality} 학생이 기록을 보며 다음 계획을 설명하도록 하면 가정에서도 결과보다 과정 중심으로 대화하기 쉽습니다.",
            ),
        ),
    )
    literal(
        f"{locality} {grade} 학생의 시험 준비는 범위 확인, 1차 개념 학습, 학교 자료 적용, 오답 재풀이, 시간 제한 점검으로 나누는 것이 좋습니다.",
        choose(
            context,
            "exam-sequence",
            (
                f"{locality} {grade} 시험 준비는 범위를 먼저 확인한 뒤 개념 학습, 학교 자료 적용, 오답 재풀이, 시간 제한 점검의 순서로 나누어 보세요.",
                f"{locality} {grade} 학생은 시험 범위 확인일과 개념 완료일, 학교 자료 적용일, 오답 재풀이일, 시간 점검일을 각각 정하는 편이 좋습니다.",
                f"시험 대비를 한 덩어리로 보지 말고 {locality} {grade} 학생의 범위·개념·학교 자료·오답·시간 점검을 단계별로 구분하세요.",
                f"{locality} {grade} 계획표에는 시험 범위 확인부터 개념, 학교 자료, 재풀이, 제한 시간 연습까지 다섯 단계를 순서대로 배치하는 것이 좋습니다.",
                f"{locality} {grade} 학생의 시험 준비는 범위를 확정하고 개념을 점검한 뒤 학교 자료와 오답, 시간 관리로 이어져야 합니다.",
                f"먼저 시험 범위를 정리하고 개념과 학교 자료를 학습한 다음 오답 재풀이와 시간 제한 연습을 하는 흐름이 {locality} {grade} 학생에게 필요합니다.",
                f"{locality} {grade} 시험 계획은 범위 확인, 개념 보완, 학교 자료 적용, 오답 확인, 시간 점검의 완료 날짜를 따로 두는 편이 명확합니다.",
                f"시험일까지 남은 기간을 {locality} {grade} 학생의 범위 확인·개념·학교 자료·오답·시간 연습 단계로 나누어 진행하세요.",
            ),
        ),
    )
    pattern(
        rf"{re.escape(area)} {re.escape(locality)}의 {re.escape(keyword)} 안내도 과거 사례를 그대로 대입하지 말고 내신·모의평가의 단원, 시간, 실수 원인을 다음 주 행동으로 바꾸는 데 활용해야 합니다\.",
        "past-case-guidance",
        lambda _match, salt: choose(
            context,
            salt,
            (
                f"{area} {locality}의 {keyword} 계획은 과거 사례를 복제하기보다 현재 내신·모의평가의 단원, 시간 사용, 실수 원인을 다음 주 행동으로 바꾸는 데 활용해야 합니다.",
                f"이전 사례를 그대로 적용하지 말고 {locality} 학생의 내신·모의평가 기록에서 단원·시간·실수 원인을 찾아 {keyword} 다음 행동으로 옮기세요.",
                f"{keyword} 안내는 과거 결과보다 {area} {locality} 학생의 현재 단원과 시간 배분, 실수 원인을 분석해 다음 주 계획을 정하는 데 쓰는 편이 좋습니다.",
                f"{locality} 학생의 {keyword} 계획에서는 다른 사례보다 최근 내신·모의평가의 단원, 풀이 시간, 실수 원인을 다음 행동과 연결해야 합니다.",
                f"과거 학생의 방식을 대입하기보다 {area} {locality}의 현재 답안에서 단원·시간·오류 원인을 확인하고 {keyword} 계획을 다음 주 행동으로 구체화하세요.",
                f"{keyword}{keyword_subject} 사례 비교가 아니라 {locality} 학생의 내신·모의평가 기록을 분석해 다음 주에 바꿀 학습 행동을 찾는 과정이어야 합니다.",
                f"{area} {locality} 학생에게 필요한 {keyword} 안내는 최근 평가의 단원, 시간 사용, 실수 원인을 근거로 다음 주 실행 항목을 정하는 것입니다.",
                f"{locality}에서는 과거 결과를 기준으로 삼지 않고 현재 내신·모의평가의 단원과 시간, 오류를 다음 {keyword} 행동으로 전환하는지 확인하세요.",
            ),
        ),
    )
    pattern(
        rf"{re.escape(area)} {re.escape(locality)} 학부모는 진단 결과를 단원명, 재풀이 날짜, 질문 수로 받아야 {re.escape(keyword)}(?:을|를) 실제 학습 변화와 연결해 볼 수 있습니다\.",
        "diagnostic-report",
        lambda _match, salt: choose(
            context,
            salt,
            (
                f"{area} {locality} 학부모는 진단 결과를 단원명·재풀이 날짜·질문 수로 받아 {keyword}{keyword_object} 실제 학습 기록과 연결해 볼 수 있습니다.",
                f"{keyword} 진단은 {locality} 학생의 보완 단원, 다시 풀 날짜, 질문 개수가 기록되어야 이후 변화를 대조하기 쉽습니다.",
                f"{locality} 상담 결과를 단원과 재풀이일, 질문 수로 구체화하면 {area} 학부모가 {keyword} 진행 전후를 비교할 수 있습니다.",
                f"{keyword}{keyword_object} 학습 변화로 확인하려면 {locality} 진단 기록에 단원명, 다음 재풀이 날짜, 질문 수가 남아 있어야 합니다.",
                f"{area} {locality} 가정은 진단 설명을 보완 단원·재확인일·질문 수의 세 항목으로 받아 {keyword} 계획과 대조하세요.",
                f"{locality} 학부모가 {keyword} 변화를 확인하려면 진단 때 정한 단원과 재풀이 시점, 질문 수를 같은 형식으로 기록하는 편이 좋습니다.",
                f"진단 결과는 {area} {locality} 학생의 단원, 재풀이 날짜, 질문 수로 정리되어야 {keyword} 계획의 실행 여부를 확인할 수 있습니다.",
                f"{keyword} 상담 뒤에는 {locality} 학생이 먼저 볼 단원과 재풀이일, 질문 목표를 받아 다음 점검 자료로 사용하세요.",
            ),
        ),
    )

    grade_defaults = {
        "예비고1": f"{locality}의 예비고1 학습에서는 중학교식 단기 암기에서 벗어나 누적 복습과 긴 시험 범위에 적응하는 연습이 필요합니다.",
        "고1": f"{locality}의 고1 학습에서는 첫 내신과 수행평가, 과목별 과제량에 적응하는 과정을 세밀하게 봐야 합니다.",
        "고2": f"{locality}의 고2 학습에서는 과목별 난도와 진로 선택을 함께 고려해 학습 시간의 배분 기준을 세워야 합니다.",
        "고3": f"{locality}의 고3 학습에서는 학교 평가, 모의평가, 지원 준비가 겹치므로 과제의 우선순위를 자주 조정해야 합니다.",
    }
    if grade in grade_defaults:
        grade_pools = {
            "예비고1": (
                f"{locality} 예비고1 시기에는 짧은 암기 위주의 중학교 학습에서 벗어나 긴 시험 범위와 누적 복습에 적응하는 연습이 필요합니다.",
                f"고교 진입을 앞둔 {locality} 예비고1 학생은 단기 시험 대비뿐 아니라 여러 주의 내용을 이어 복습하는 방식을 익혀야 합니다.",
                f"{locality} 예비고1 학습은 중학교 때의 짧은 범위 공부를 고등학교식 누적 복습과 장기 계획으로 전환하는 데 초점을 둡니다.",
                f"시험 범위가 길어지는 시기를 대비해 {locality} 예비고1 학생은 이전 단원을 일정 간격으로 다시 보는 습관부터 만들어야 합니다.",
            ),
            "고1": (
                f"{locality} 고1 학생은 첫 내신과 수행평가, 과목별 과제량이 겹치는 시기에 일정과 완료 기준을 세밀하게 조정해야 합니다.",
                f"고등학교 첫 평가에 적응하는 {locality} 고1 시기에는 내신·수행평가·과목별 과제를 한 주 안에서 나누어 관리하는 연습이 필요합니다.",
                f"{locality} 고1 학습은 첫 내신 범위와 수행평가, 늘어난 과제량을 함께 확인하며 무리 없는 주간 흐름을 만드는 일이 중요합니다.",
                f"첫 내신을 준비하는 {locality} 고1 학생은 수행평가와 과목별 과제 시간을 따로 계산해 초기 학습 리듬을 점검해야 합니다.",
            ),
            "고2": (
                f"{locality} 고2 시기에는 과목별 체감 난도와 진로 선택을 함께 살펴 제한된 학습 시간을 어디에 배분할지 정해야 합니다.",
                f"과목 간 성취 차이가 커질 수 있는 {locality} 고2 학생은 진로 방향과 현재 난도를 기준으로 주간 학습 비중을 조정하는 편이 좋습니다.",
                f"{locality} 고2 학습은 과목별 난도만이 아니라 진로에 필요한 과목과 보완 시급성을 함께 고려해 시간표를 구성해야 합니다.",
                f"진로 선택을 구체화하는 {locality} 고2 학생은 모든 과목에 같은 시간을 쓰기보다 난도와 우선순위에 따라 배분 기준을 세워야 합니다.",
            ),
            "고3": (
                f"{locality} 고3 학생은 학교 평가와 모의평가, 지원 준비가 겹치므로 시기마다 과제 우선순위와 학습량을 다시 정해야 합니다.",
                f"내신·모의평가·지원 일정이 이어지는 {locality} 고3 시기에는 고정 계획보다 현재 일정에 따른 우선순위 조정이 중요합니다.",
                f"{locality} 고3 학습은 학교 평가와 모의평가 결과, 지원 준비 일정을 함께 보고 다음 과제를 자주 재배치해야 합니다.",
                f"여러 평가와 지원 일정이 겹치는 {locality} 고3 학생은 가장 가까운 마감과 현재 약점을 기준으로 과제 순서를 조정하는 편이 좋습니다.",
            ),
        }
        literal(
            grade_defaults[grade],
            choose(context, "grade-context", grade_pools[grade]),
        )

    pattern(
        rf"그 뒤에는 {re.escape(locality)} 학생이 ([^<.!?]{{4,100}}?)에 남긴 실행 기록을 살펴 계획이 실제로 실행됐는지 확인합니다\.",
        "event-review",
        lambda match, salt: choose(
            context,
            salt,
            (
                f"이후 점검에서는 {locality} 학생이 {match.group(1)}에 남긴 완료 항목과 미완료 이유를 대조해 계획의 실행 여부를 확인합니다.",
                f"{locality} 학생이 {match.group(1)}에 작성한 기록을 다시 보고 계획대로 한 일과 조정할 일을 구분하세요.",
                f"다음 상담에서는 {locality} 학생이 {match.group(1)}에 남긴 기록에서 실제 실행된 항목과 미완료 원인을 확인하는 편이 좋습니다.",
                f"{locality} 학생이 {match.group(1)}에 남긴 실행 기록을 기준으로 계획이 현실적이었는지 다시 판단합니다.",
                f"{locality} 학생이 {match.group(1)}에 무엇을 끝냈고 어디에서 멈췄는지 기록으로 확인해 다음 계획에 반영하세요.",
                f"계획 점검일에는 {locality} 학생의 {match.group(1)} 실행 기록을 살펴 유지할 항목과 바꿀 항목을 나누어야 합니다.",
                f"{locality} 학생이 {match.group(1)}에 작성한 기록은 계획과 실제 행동의 차이를 확인하는 다음 상담 자료로 활용합니다.",
                f"{locality} 학생의 {match.group(1)} 기록을 바탕으로 실행률과 미완료 원인을 확인하고 다음 주 분량을 조정하세요.",
            ),
        ),
    )
    pattern(
        rf"{re.escape(locality)} 페이지에서 남길 점검 항목은 ([^<.!?]{{8,150}}?)입니다\.",
        "page-check",
        lambda match, salt: choose(
            context,
            salt,
            (
                f"{locality} 상담 기록의 마지막에는 {match.group(1)}{particle(match.group(1), '을', '를')} 점검 항목으로 남겨 보세요.",
                f"최종 점검표에는 {locality} 학생의 {match.group(1)}{particle(match.group(1), '을', '를')} 확인하도록 적습니다.",
                f"{match.group(1)}{particle(match.group(1), '이', '가')} {locality} 페이지에서 이어서 확인할 핵심 기록입니다.",
                f"{locality} 학부모는 다음 상담 때 {match.group(1)}{particle(match.group(1), '을', '를')} 같은 기준으로 다시 확인하세요.",
                f"마지막에는 {locality} 학생의 {match.group(1)}{particle(match.group(1), '을', '를')} 핵심 확인 항목으로 정하는 편이 좋습니다.",
                f"{locality}에서 남겨 둘 기록은 {match.group(1)}{particle(match.group(1), '을', '를')} 다음 점검일에 대조할 수 있는 형태여야 합니다.",
                f"다음 계획을 정하기 전 {locality} 학생의 {match.group(1)}{particle(match.group(1), '을', '를')} 기록으로 확인합니다.",
                f"{match.group(1)}{particle(match.group(1), '을', '를')} {locality} 상담의 공통 점검 항목으로 사용해 보세요.",
            ),
        ),
    )
    pattern(
        rf"{re.escape(area)} {re.escape(locality)} 학부모는 “([^”]{{8,180}})”라는 점을 고려해 명칭보다 실제 적용 조건과 예외 상황을 질문하는 편이 좋습니다\.",
        "marketing-claim",
        lambda match, salt: choose(
            context,
            salt,
            (
                f"{area} {locality} 상담에서는 ‘{match.group(1)}’라는 기준을 염두에 두고 명칭보다 적용 조건과 예외 처리를 구체적으로 질문하세요.",
                f"{locality} 학부모는 ‘{match.group(1)}’라는 점을 고려해 이름만 비교하지 말고 실제 적용 범위와 달라지는 조건을 기록하는 편이 좋습니다.",
                f"‘{match.group(1)}’라는 설명을 기준으로 {area} {locality}에서는 운영 조건과 예외 상황을 나누어 확인하세요.",
                f"{area} {locality} 학부모가 확인할 부분은 명칭 자체보다 ‘{match.group(1)}’라는 기준이 실제 조건과 예외에 어떻게 반영되는지입니다.",
                f"{locality} 상담 답변에는 ‘{match.group(1)}’라는 판단 기준과 함께 적용 범위·예외 처리도 적어 두는 편이 좋습니다.",
                f"명칭만으로 결정하기 전에 {area} {locality} 학부모는 ‘{match.group(1)}’라는 점을 고려해 실제 적용 조건과 달라질 수 있는 경우를 함께 물어보세요.",
                f"{locality}에서는 ‘{match.group(1)}’라는 점을 상담 기준으로 삼아 구체적인 운영 범위와 예외를 대조합니다.",
                f"{area} {locality} 상담에서는 ‘{match.group(1)}’라는 점을 고려해 이름보다 학생에게 적용될 조건과 예외를 먼저 확인하세요.",
            ),
        ),
    )

    if replacements < 11:
        raise ValueError(
            f"{context.path}: expected at least 11 repeated-copy replacements, got {replacements}"
        )
    flow, keyword_reductions = reduce_keyword_density(flow, context)
    replacements += keyword_reductions
    flow, phrasing_fixes = polish_source_phrasing(flow)
    replacements += phrasing_fixes
    flow, refinements, scope_keyword_reductions = refine_keyword_scope(flow, context)
    replacements += refinements
    keyword_reductions += scope_keyword_reductions
    keyword_marker = f"<!-- high-student-secondary-keyword:{context.keyword} -->"
    return MARKER + "\n" + keyword_marker + "\n" + flow, replacements, school_fixes, keyword_reductions


def corrected_school_faq(context: Context) -> tuple[str, str]:
    return school_faq_question(context), corrected_school_copy(context)


def update_coverage_school_block(
    source: str, context: Context
) -> tuple[str, int]:
    if context.school_state != "coverage":
        return source, 0
    school_match = SCHOOL_RE.search(source)
    if not school_match:
        raise ValueError(f"{context.path}: coverage school block missing")
    block = school_match.group(0)
    old_heading = "<h3>고등학교 실제 수업 가능 학교</h3>"
    new_heading = "<h3>고등학교 수업 가능 범위</h3>"
    heading_count = block.count(old_heading)
    if heading_count == 1:
        block = block.replace(old_heading, new_heading, 1)
    elif new_heading not in block:
        raise ValueError(f"{context.path}: coverage school heading missing")
    fact = (
        f"{context.locality} 공통 타깃학교 원자료에는 ‘지역내 모든 고등학교 가능’이 고등학교 수업 가능 범위로 기재되어 있으나, "
        "현재 연결된 센터 정보에는 개별 고등학교명이 기재되지 않았습니다."
    )
    authored = (
        "고등 학습 단계 상담에서는 재학 학교·학년·과목을 밝혀 실제 수업 가능 여부를 다시 확인하고 "
        "반 배정 상태는 담당자에게 직접 물어보세요."
    )
    block, copy_count = re.subn(
        r"(<span\s+data-school-source-fact>).*?(</span>\s*<span\s+data-school-authored-copy>).*?(</span>)",
        lambda match: (
            match.group(1) + html.escape(fact) + match.group(2)
            + html.escape(authored) + match.group(3)
        ),
        block,
        count=1,
        flags=re.S,
    )
    if heading_count not in {0, 1} or copy_count != 1:
        raise ValueError(
            f"{context.path}: coverage school heading/copy={heading_count}/{copy_count}"
        )
    updated = source[: school_match.start()] + block + source[school_match.end() :]
    return updated, int(updated != source)


def update_visible_school_faq(
    source: str, context: Context, needs_school_fix: bool
) -> tuple[str, int]:
    if not needs_school_fix:
        return source, 0
    faq_match = FAQ_RE.search(source)
    if not faq_match:
        raise ValueError(f"{context.path}: FAQ section missing")
    block = faq_match.group(0)
    items = list(FAQ_ITEM_RE.finditer(block))
    if len(items) != 5:
        raise ValueError(f"{context.path}: FAQ items={len(items)}")
    target = items[2]
    item = target.group(0)
    question, answer = corrected_school_faq(context)
    item, question_count = re.subn(
        r'(<summary><span>Q</span>)(.*?)(</summary>)',
        lambda match: match.group(1) + html.escape(question) + match.group(3),
        item,
        count=1,
        flags=re.S,
    )
    if question_count != 1:
        raise ValueError(f"{context.path}: FAQ school question update={question_count}")
    item, answer_count = re.subn(
        r'(<div\s+class="subject-faq-answer"><span>A</span><p>)(.*?)(</p>)',
        lambda match: match.group(1) + html.escape(answer) + match.group(3),
        item,
        count=1,
        flags=re.S,
    )
    if answer_count != 1:
        raise ValueError(f"{context.path}: FAQ school answer update={answer_count}")
    updated_block = block[: target.start()] + item + block[target.end() :]
    return source[: faq_match.start()] + updated_block + source[faq_match.end() :], 2


def update_visible_special_keyword_faq(
    source: str, context: Context
) -> tuple[str, int]:
    answer = special_keyword_faq_answer(context)
    if not answer:
        return source, 0
    faq_match = FAQ_RE.search(source)
    if not faq_match:
        raise ValueError(f"{context.path}: FAQ section missing")
    block = faq_match.group(0)
    items = list(FAQ_ITEM_RE.finditer(block))
    if len(items) != 5:
        raise ValueError(f"{context.path}: FAQ items={len(items)}")
    target = items[1]
    item = target.group(0)
    question = special_keyword_faq_question(context)
    if question:
        item, question_count = re.subn(
            r'(<summary><span>Q</span>)(.*?)(</summary>)',
            lambda match: match.group(1) + html.escape(question) + match.group(3),
            item,
            count=1,
            flags=re.S,
        )
        if question_count != 1:
            raise ValueError(
                f"{context.path}: special FAQ question update={question_count}"
            )
    item, answer_count = re.subn(
        r'(<div\s+class="subject-faq-answer"><span>A</span><p>)(.*?)(</p>)',
        lambda match: match.group(1) + html.escape(answer) + match.group(3),
        item,
        count=1,
        flags=re.S,
    )
    if answer_count != 1:
        raise ValueError(f"{context.path}: special FAQ answer update={answer_count}")
    updated_block = block[: target.start()] + item + block[target.end() :]
    updated = source[: faq_match.start()] + updated_block + source[faq_match.end() :]
    return updated, int(updated != source)


def replace_nested_text(value, before: str, after: str) -> tuple[object, int]:
    if isinstance(value, str):
        return value.replace(before, after), value.count(before)
    if isinstance(value, list):
        result = []
        count = 0
        for item in value:
            updated, item_count = replace_nested_text(item, before, after)
            result.append(updated)
            count += item_count
        return result, count
    if isinstance(value, dict):
        result = {}
        count = 0
        for key, item in value.items():
            updated, item_count = replace_nested_text(item, before, after)
            result[key] = updated
            count += item_count
        return result, count
    return value, 0


def correct_nested_geographic(value, context: Context) -> tuple[object, int]:
    if isinstance(value, str):
        return correct_geographic_scope_phrases(value, context)
    if isinstance(value, list):
        result = []
        total = 0
        for item in value:
            updated, count = correct_nested_geographic(item, context)
            result.append(updated)
            total += count
        return result, total
    if isinstance(value, dict):
        result = {}
        total = 0
        for key, item in value.items():
            updated, count = correct_nested_geographic(item, context)
            result[key] = updated
            total += count
        return result, total
    return value, 0


def apply_jsonld_changes(
    payload: dict, context: Context, needs_school_fix: bool, update_dates: bool
) -> tuple[dict, int, int]:
    graph = payload.get("@graph", []) if isinstance(payload, dict) else []
    page_nodes = article_nodes = faq_nodes = 0
    school_fixes = particle_fixes = 0
    wrong_heading, correct_heading = corrected_heading_phrase(context)
    question, _ = corrected_school_faq(context)
    special_heading = special_keyword_heading(context)
    special_question = special_keyword_faq_question(context)
    original_flow = FLOW_RE.search(context.before)
    if not original_flow:
        raise ValueError(f"{context.path}: original flow missing for JSON-LD")
    legacy_method = legacy_method_from_flow(original_flow.group(2), context)
    intended_method = method_for_secondary_challenge(context)
    for index, node in enumerate(graph):
        if not isinstance(node, dict):
            continue
        node_type = node.get("@type", [])
        types = set(node_type if isinstance(node_type, list) else [node_type])
        if legacy_method != intended_method:
            node, _ = replace_nested_text(node, legacy_method, intended_method)
            graph[index] = node
        if {"EducationalOrganization", "LocalBusiness"} & types:
            # The synchronized canonical center card exposes the current fee
            # notice/link rather than a full price table, so do not publish a
            # hidden 18-offer catalog in structured data.
            node.pop("hasOfferCatalog", None)
            postal = node.get("address")
            if isinstance(postal, dict):
                address_override = POSTAL_ADDRESS_OVERRIDES.get(context.area)
                if context.locality in AREA_FACT_OVERRIDES:
                    address_override = (
                        AREA_FACT_OVERRIDES[context.locality],
                        context.locality,
                    )
                if context.locality in POSTAL_LOCALITY_OVERRIDES:
                    address_override = POSTAL_LOCALITY_OVERRIDES[context.locality]
                if address_override:
                    postal["addressRegion"], postal["addressLocality"] = address_override
                    node["address"] = postal
        if special_heading and ({"WebPage", "Article"} & types):
            for part in node.get("hasPart", []):
                if (
                    isinstance(part, dict)
                    and isinstance(part.get("name"), str)
                    and context.keyword in part["name"]
                ):
                    part["name"] = special_heading
                    break
            if "Article" in types:
                sections = node.get("articleSection", [])
                if isinstance(sections, list):
                    updated_sections = list(sections)
                    for section_index, value in enumerate(updated_sections):
                        if isinstance(value, str) and context.keyword in value:
                            updated_sections[section_index] = special_heading
                            break
                    node["articleSection"] = updated_sections
        if {"WebPage", "Article"} & types:
            raw_scope = f"{context.area} {context.locality}".strip()
            display_scope = geographic_scope(context)
            if raw_scope != display_scope:
                for part in node.get("hasPart", []):
                    if isinstance(part, dict) and isinstance(part.get("name"), str):
                        part["name"] = part["name"].replace(raw_scope, display_scope)
                if "Article" in types:
                    sections = node.get("articleSection", [])
                    if isinstance(sections, list):
                        node["articleSection"] = [
                            value.replace(raw_scope, display_scope)
                            if isinstance(value, str)
                            else value
                            for value in sections
                        ]
        if {"WebPage", "Article", "Service", "FAQPage"} & types:
            node, _ = correct_nested_geographic(node, context)
            graph[index] = node
        if (
            "WebPageElement" in types
            and context.school_state == "coverage"
            and str(node.get("@id", "")).endswith("#school-reference")
        ):
            node["description"] = coverage_school_summary(context)
        if "WebPage" in types:
            page_nodes += 1
            if update_dates:
                node["dateModified"] = RELEASE_DATE
        if "Article" in types:
            article_nodes += 1
            if update_dates:
                node["dateModified"] = RELEASE_DATE
            if needs_school_fix:
                description = node.get("description", "")
                description, count = re.subn(
                    rf"{re.escape(context.locality)} 자료에서 수업 학교 정보는 .*?이며 학원 주소는",
                    school_article_phrase(context),
                    description,
                    count=1,
                )
                if count != 1:
                    raise ValueError(f"{context.path}: Article school description update={count}")
                node["description"] = description
                school_fixes += 1
        if "FAQPage" in types:
            faq_nodes += 1
            if needs_school_fix:
                entities = node.get("mainEntity", [])
                if not isinstance(entities, list) or len(entities) != 5:
                    raise ValueError(f"{context.path}: schema FAQ entities invalid")
                entities[2]["name"] = question
                accepted = entities[2].get("acceptedAnswer", {})
                accepted["text"] = corrected_school_copy(context)
                entities[2]["acceptedAnswer"] = accepted
                school_fixes += 2
            special_answer = special_keyword_faq_answer(context)
            if special_answer:
                entities = node.get("mainEntity", [])
                if not isinstance(entities, list) or len(entities) != 5:
                    raise ValueError(f"{context.path}: schema FAQ entities invalid")
                if special_question:
                    entities[1]["name"] = special_question
                accepted = entities[1].get("acceptedAnswer", {})
                accepted["text"] = special_answer
                entities[1]["acceptedAnswer"] = accepted
        if context.keyword == "학원개인정보관리" and ({"WebPage", "Article"} & types):
            parts = node.get("hasPart", [])
            supplemental_heading = privacy_supplemental_heading(context)
            if any(
                isinstance(part, dict) and part.get("name") == supplemental_heading
                for part in parts
            ):
                continue
            matching_parts = [
                part
                for part in parts
                if isinstance(part, dict)
                and isinstance(part.get("name"), str)
                and context.keyword in part["name"]
            ]
            if len(matching_parts) != 2:
                raise ValueError(
                    f"{context.path}: schema privacy hasPart count={len(matching_parts)}/2"
                )
            matching_parts[1]["name"] = supplemental_heading
            if "Article" in types:
                sections = node.get("articleSection", [])
                if not isinstance(sections, list):
                    raise ValueError(f"{context.path}: privacy articleSection invalid")
                sections, _ = replace_second_keyword_heading(sections, context)
                node["articleSection"] = sections
        if wrong_heading != correct_heading and ({"WebPage", "Article"} & types):
            updated, count = replace_nested_text(node, wrong_heading, correct_heading)
            graph[index] = updated
            particle_fixes += count
    if page_nodes != 1 or article_nodes != 1 or faq_nodes != 1:
        raise ValueError(
            f"{context.path}: WebPage/Article/FAQPage={page_nodes}/{article_nodes}/{faq_nodes}"
        )
    payload["@graph"] = graph
    return payload, school_fixes, particle_fixes


def update_jsonld(
    source: str, context: Context, needs_school_fix: bool
) -> tuple[str, int, int]:
    updated = False
    school_fixes = particle_fixes = 0

    def replace(match: re.Match[str]) -> str:
        nonlocal updated, school_fixes, particle_fixes
        if updated:
            return match.group(0)
        payload = json.loads(match.group(2))
        payload, school_fixes, particle_fixes = apply_jsonld_changes(
            payload, context, needs_school_fix, update_dates=True
        )
        updated = True
        packed = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        return match.group(1) + packed + match.group(3)

    result = JSONLD_RE.sub(replace, source, count=1)
    if not updated:
        raise ValueError(f"{context.path}: JSON-LD not updated")
    return result, school_fixes, particle_fixes


def transform(context: Context, center_snippet: str) -> Plan:
    match = FLOW_RE.search(context.before)
    if not match:
        raise ValueError(f"{context.path}: subject-copy-flow missing")
    needs_school_fix = school_mismatch(match.group(2), context)
    legacy_method = legacy_method_from_flow(match.group(2), context)
    intended_method = method_for_secondary_challenge(context)
    rewritten, replacements, school_flow_fixes, keyword_reductions = rewrite_flow(
        match.group(2), context
    )
    rewritten, special_flow_fixes = update_special_keyword_flow(rewritten, context)
    replacements += special_flow_fixes
    wrong_heading, correct_heading = corrected_heading_phrase(context)
    visible_particle_fixes = 0
    if wrong_heading != correct_heading:
        visible_particle_fixes = rewritten.count(wrong_heading)
        rewritten = rewritten.replace(wrong_heading, correct_heading)
    after = context.before[: match.start(2)] + rewritten + context.before[match.end(2) :]
    after, faq_school_fixes = update_visible_school_faq(
        after, context, needs_school_fix
    )
    after, coverage_school_fixes = update_coverage_school_block(after, context)
    replacements += coverage_school_fixes
    after, special_faq_fixes = update_visible_special_keyword_faq(after, context)
    replacements += special_faq_fixes
    if legacy_method != intended_method:
        method_fixes = after.count(legacy_method)
        after = after.replace(legacy_method, intended_method)
        replacements += method_fixes
    after, center_fixes = sync_center_snippet(after, center_snippet, context)
    replacements += center_fixes
    after, geographic_fixes = correct_geographic_scope_phrases(after, context)
    replacements += geographic_fixes
    after, json_school_fixes, json_particle_fixes = update_jsonld(
        after, context, needs_school_fix
    )
    after, semantic_heading_fixes = correct_semantic_heading_phrases(after)
    replacements += semantic_heading_fixes
    school_fixes = school_flow_fixes + faq_school_fixes + json_school_fixes
    particle_fixes = visible_particle_fixes + json_particle_fixes
    if needs_school_fix and school_fixes != 6:
        raise ValueError(f"{context.path}: school fixes={school_fixes}/6")
    if not needs_school_fix and school_fixes:
        raise ValueError(f"{context.path}: unexpected school fixes={school_fixes}")
    if particle_fixes < visible_particle_fixes:
        raise ValueError(
            f"{context.path}: particle fixes={particle_fixes}/{visible_particle_fixes}"
        )
    return Plan(
        context, after, replacements, school_fixes, particle_fixes,
        keyword_reductions,
    )


def unchanged(pattern: re.Pattern[str], before: str, after: str) -> bool:
    left = pattern.search(before)
    right = pattern.search(after)
    return bool(left and right and left.group(0) == right.group(0))


def jsonld_without_dates(source: str) -> object:
    match = JSONLD_RE.search(source)
    if not match:
        return None
    payload = json.loads(match.group(2))
    graph = payload.get("@graph", []) if isinstance(payload, dict) else []
    for node in graph:
        if not isinstance(node, dict):
            continue
        node_type = node.get("@type", [])
        types = set(node_type if isinstance(node_type, list) else [node_type])
        if {"WebPage", "Article"} & types:
            node.pop("dateModified", None)
    return payload


def intended_jsonld_without_dates(
    source: str, context: Context, needs_school_fix: bool
) -> object:
    match = JSONLD_RE.search(source)
    if not match:
        return None
    payload = json.loads(match.group(2))
    payload, _, _ = apply_jsonld_changes(
        payload, context, needs_school_fix, update_dates=False
    )
    packed = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    packed, _ = correct_semantic_heading_phrases(packed)
    synthetic = match.group(1) + packed + match.group(3)
    return jsonld_without_dates(synthetic)


def validate(plans: list[Plan], root: Path) -> list[str]:
    errors: list[str] = []
    if len(plans) != 371:
        errors.append(f"pages={len(plans)}/371")
    for plan in plans:
        before = plan.context.before
        after = plan.after
        relative = plan.context.path.relative_to(root).as_posix()
        old_flow = FLOW_RE.search(before)
        new_flow = FLOW_RE.search(after)
        needs_school_fix = bool(
            old_flow and school_mismatch(old_flow.group(2), plan.context)
        )
        for label, regex in (
            ("school", SCHOOL_RE),
            ("answer", ANSWER_RE),
            ("review", REVIEW_RE),
            ("network", NETWORK_RE),
        ):
            left = regex.search(before)
            right = regex.search(after)
            expected = (
                correct_geographic_scope_phrases(left.group(0), plan.context)[0]
                if left
                else ""
            )
            if label == "school" and plan.context.school_state == "coverage":
                expected, _ = update_coverage_school_block(
                    expected, plan.context
                )
            source_flow = FLOW_RE.search(before)
            if source_flow:
                legacy_method = legacy_method_from_flow(
                    source_flow.group(2), plan.context
                )
                expected = expected.replace(
                    legacy_method, method_for_secondary_challenge(plan.context)
                )
            if not left or not right or expected != right.group(0):
                errors.append(f"{relative}: {label} changed")
        try:
            expected_faq_source, _ = update_visible_school_faq(
                before, plan.context, needs_school_fix
            )
            expected_faq_source, _ = update_visible_special_keyword_faq(
                expected_faq_source, plan.context
            )
            expected_faq_source, _ = correct_geographic_scope_phrases(
                expected_faq_source, plan.context
            )
            source_flow = FLOW_RE.search(before)
            if source_flow:
                expected_faq_source = expected_faq_source.replace(
                    legacy_method_from_flow(source_flow.group(2), plan.context),
                    method_for_secondary_challenge(plan.context),
                )
            expected_faq = FAQ_RE.search(expected_faq_source)
            actual_faq = FAQ_RE.search(after)
            if not expected_faq or not actual_faq or expected_faq.group(0) != actual_faq.group(0):
                errors.append(
                    f"{relative}: FAQ changed beyond intended school/special correction"
                )
        except Exception as exc:
            errors.append(f"{relative}: FAQ validation {type(exc).__name__}: {exc}")
        for pattern_value, label in (
            (r"<title>(.*?)</title>", "title"),
            (r"<h1\b[^>]*>(.*?)</h1>", "H1"),
            (r'<link\b(?=[^>]*\brel="canonical")[^>]*\bhref="([^"]+)"', "canonical"),
            (r'<meta\s+name="description"\s+content="([^"]+)"', "description"),
        ):
            left = re.search(pattern_value, before, re.I | re.S)
            right = re.search(pattern_value, after, re.I | re.S)
            expected = (
                correct_geographic_scope_phrases(left.group(0), plan.context)[0]
                if left and label == "description"
                else left.group(0) if left else ""
            )
            if not left or not right or expected != right.group(0):
                errors.append(f"{relative}: {label} changed")
        old_headings = re.findall(
            r'<section\s+class="subject-copy-section"><h2>(.*?)</h2>',
            old_flow.group(2) if old_flow else "",
            re.I | re.S,
        )
        new_headings = re.findall(
            r'<section\s+class="subject-copy-section"><h2>(.*?)</h2>',
            new_flow.group(2) if new_flow else "",
            re.I | re.S,
        )
        wrong_heading, correct_heading = corrected_heading_phrase(plan.context)
        old_headings = [heading.replace(wrong_heading, correct_heading) for heading in old_headings]
        old_headings = [
            correct_semantic_heading_phrases(heading)[0]
            for heading in old_headings
        ]
        old_headings = [
            correct_geographic_scope_phrases(heading, plan.context)[0]
            for heading in old_headings
        ]
        special_heading = special_keyword_heading(plan.context)
        if special_heading:
            for heading_index, heading in enumerate(old_headings):
                if plan.context.keyword in clean(heading):
                    old_headings[heading_index] = special_heading
                    break
        if plan.context.keyword == "학원개인정보관리":
            old_headings, _ = replace_second_keyword_heading(
                old_headings, plan.context
            )
        if old_headings != new_headings or len(new_headings) != 6:
            errors.append(f"{relative}: headings changed/count={len(new_headings)}")
        old_paragraphs = re.findall(r"<p\b[^>]*>.*?</p>", old_flow.group(2) if old_flow else "", re.I | re.S)
        new_paragraphs = re.findall(r"<p\b[^>]*>.*?</p>", new_flow.group(2) if new_flow else "", re.I | re.S)
        if len(old_paragraphs) != 12 or len(new_paragraphs) != 12:
            errors.append(f"{relative}: paragraph count={len(old_paragraphs)}/{len(new_paragraphs)}")
        old_assets = re.findall(r'\b(?:href|src|srcset)="([^"]+)"', before, re.I)
        new_assets = re.findall(r'\b(?:href|src|srcset)="([^"]+)"', after, re.I)
        old_center = CENTER_BLOCK_RE.search(before)
        new_center = CENTER_BLOCK_RE.search(after)
        if old_center and new_center:
            old_assets = re.findall(
                r'\b(?:href|src|srcset)="([^"]+)"',
                before[: old_center.start()] + before[old_center.end() :],
                re.I,
            )
            new_assets = re.findall(
                r'\b(?:href|src|srcset)="([^"]+)"',
                after[: new_center.start()] + after[new_center.end() :],
                re.I,
            )
        if old_assets != new_assets:
            errors.append(f"{relative}: href/src changed")
        if after.count("<section") != after.count("</section>"):
            errors.append(f"{relative}: section tags unbalanced")
        if after.count("<details") != after.count("</details>"):
            errors.append(f"{relative}: details tags unbalanced")
        center_match = CENTER_BLOCK_RE.search(after)
        if not center_match or not extract_balanced_section(
            center_match.group(0), "wawa-center-snippet"
        ):
            errors.append(f"{relative}: center snippet unbalanced")
        if "wawa-fee-accordion" in (center_match.group(0) if center_match else ""):
            errors.append(f"{relative}: stale fee accordion remains")
        if MARKER not in (new_flow.group(2) if new_flow else ""):
            errors.append(f"{relative}: marker missing")
        keyword_count = clean(new_flow.group(2) if new_flow else "").count(
            plan.context.keyword
        )
        if not 2 <= keyword_count <= 4:
            errors.append(
                f"{relative}: keyword {plan.context.keyword} count={keyword_count}"
            )
        try:
            expected_jsonld = intended_jsonld_without_dates(
                before, plan.context, needs_school_fix
            )
            if expected_jsonld != jsonld_without_dates(after):
                errors.append(
                    f"{relative}: JSON-LD changed beyond intended school/heading/date updates"
                )
        except Exception as exc:
            errors.append(f"{relative}: JSON-LD intent {type(exc).__name__}: {exc}")
        if wrong_heading != correct_heading and wrong_heading in after:
            errors.append(f"{relative}: wrong heading particle remains")
        try:
            payload_match = JSONLD_RE.search(after)
            payload = json.loads(payload_match.group(2)) if payload_match else {}
            dates = set()
            for node in payload.get("@graph", []):
                node_type = node.get("@type", []) if isinstance(node, dict) else []
                types = set(node_type if isinstance(node_type, list) else [node_type])
                if {"WebPage", "Article"} & types:
                    dates.add(node.get("dateModified"))
            if dates != {RELEASE_DATE}:
                errors.append(f"{relative}: dates={sorted(map(str, dates))}")
        except Exception as exc:
            errors.append(f"{relative}: JSON-LD {type(exc).__name__}: {exc}")
    return errors


def visible_text(source: str) -> str:
    match = re.search(r"<main\b.*?</main>", source, re.I | re.S)
    return clean(SCRIPT_STYLE_RE.sub(" ", match.group(0) if match else source))


def article_text(source: str) -> str:
    match = FLOW_RE.search(source)
    return clean(match.group(2)) if match else ""


def shingles(value: str, size: int = 4) -> set[tuple[str, ...]]:
    words = re.findall(r"[가-힣A-Za-z0-9]+", value.lower())
    return {
        tuple(words[index : index + size])
        for index in range(max(0, len(words) - size + 1))
    }


def similarity(values: list[str], sample_size: int = 90) -> dict[str, float]:
    if len(values) > sample_size:
        indices = [
            round(index * (len(values) - 1) / (sample_size - 1))
            for index in range(sample_size)
        ]
        values = [values[index] for index in indices]
    sets = [shingles(value) for value in values]
    scores = [
        len(left & right) / len(left | right)
        for left, right in itertools.combinations(sets, 2)
        if left or right
    ]
    ordered = sorted(scores)
    return {
        "average": round(statistics.mean(scores), 4),
        "p90": round(ordered[int(len(ordered) * 0.9)], 4),
        "max": round(max(scores), 4),
    }


def atomic_write(path: Path, value: str) -> None:
    temporary = path.with_name(path.name + ".high-student-diff.tmp")
    temporary.write_text(value, encoding="utf-8", newline="\n")
    temporary.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument(
        "--reference-root",
        type=Path,
        help="repository root containing canonical 전국학원 center cards",
    )
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    root = args.root.resolve()
    reference_root = (args.reference_root or root).resolve()
    target = root / "과목별학원" / CATEGORY
    paths = sorted(target.glob("*/index.html"))
    contexts = [extract_context(path, index) for index, path in enumerate(paths)]
    plans = [
        transform(context, reference_center_snippet(context, reference_root))
        for context in contexts
    ]
    errors = validate(plans, root)
    before_articles = [article_text(plan.context.before) for plan in plans]
    after_articles = [article_text(plan.after) for plan in plans]
    before_full = [visible_text(plan.context.before) for plan in plans]
    after_full = [visible_text(plan.after) for plan in plans]
    before_keyword_counts = [
        article_text(plan.context.before).count(plan.context.keyword) for plan in plans
    ]
    after_keyword_counts = [
        article_text(plan.after).count(plan.context.keyword) for plan in plans
    ]
    report = {
        "mode": "APPLY" if args.apply else "DRY-RUN",
        "pages": len(plans),
        "changed": sum(plan.context.before != plan.after for plan in plans),
        "replacements": {
            "total": sum(plan.replacements for plan in plans),
            "min": min((plan.replacements for plan in plans), default=0),
            "average": round(statistics.mean(plan.replacements for plan in plans), 2),
            "max": max((plan.replacements for plan in plans), default=0),
        },
        "school_fact_fixes": {
            "pages": sum(plan.school_fixes > 0 for plan in plans),
            "total": sum(plan.school_fixes for plan in plans),
        },
        "heading_particle_fixes": {
            "pages": sum(plan.particle_fixes > 0 for plan in plans),
            "total": sum(plan.particle_fixes for plan in plans),
        },
        "keyword_density_reductions": {
            "pages": sum(plan.keyword_reductions > 0 for plan in plans),
            "total": sum(plan.keyword_reductions for plan in plans),
        },
        "keyword_occurrences_in_flow": {
            "before_average": round(statistics.mean(before_keyword_counts), 2),
            "before_min": min(before_keyword_counts),
            "before_max": max(before_keyword_counts),
            "after_average": round(statistics.mean(after_keyword_counts), 2),
            "after_min": min(after_keyword_counts),
            "after_max": max(after_keyword_counts),
            "after_over_4_pages": sum(value > 4 for value in after_keyword_counts),
        },
        "visible_chars_average": {
            "before": round(statistics.mean(map(len, before_full)), 1),
            "after": round(statistics.mean(map(len, after_full)), 1),
        },
        "article_similarity": {
            "before": similarity(before_articles),
            "after": similarity(after_articles),
        },
        "full_page_similarity": {
            "before": similarity(before_full),
            "after": similarity(after_full),
        },
        "unique_articles": len(set(after_articles)),
        "errors": len(errors),
        "samples": errors[:30],
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if errors:
        return 1
    if args.apply:
        for plan in plans:
            if plan.context.before != plan.after:
                atomic_write(plan.context.path, plan.after)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
