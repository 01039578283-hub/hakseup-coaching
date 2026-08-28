from __future__ import annotations

"""Strict release audit for the 371 local ``영수학원`` pages.

The generator and this auditor intentionally do not share implementation code.
That separation makes the audit useful: page slugs and factual assertions are
read again from the common source CSV, while URLs and structured data are
derived from the public contract rather than from generator output.

The default is release-strict: any failed invariant exits with status 1.
Use ``--soft`` only while developing pages when a machine-readable report is
more useful than a failing process.
"""

import argparse
import csv
import html
import json
import re
import sys
from collections import Counter
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Iterable, Iterator, Sequence
from urllib.parse import quote, unquote, urlsplit
from xml.etree import ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "과목별학원" / "영수학원"
DEFAULT_COMMON = ROOT.parent / "참고자료" / "공통자료"
FACT_CSV_NAME = "센터정보 정리.csv"
BASE_URL = "https://xn--ru4bi8s1tac0p.kr"
BASE_HOST = (urlsplit(BASE_URL).hostname or "").lower()
DETAIL_COUNT = 371
SIMILARITY_LIMIT = 0.75

# These source cells lost explicit delimiters.  Keep this allowlist exact:
# whitespace is not a generally safe school-name delimiter, and the final
# entry repairs one elementary name fused to the first middle-school name.
SCHOOL_SOURCE_CORRECTIONS: dict[str, tuple[str, ...]] = {
    "성라초 성사초": ("성라초", "성사초"),
    "화수중 성사중 원당중": ("화수중", "성사중", "원당중"),
    "성사고 화수고": ("성사고", "화수고"),
    "해밀초 화봉초": ("해밀초", "화봉초"),
    "풍양중 주곡중": ("풍양중", "주곡중"),
    "진접고 오남고": ("진접고", "오남고"),
    "석천초 상인초": ("석천초", "상인초"),
    "석천중 상동중 상일중 부인중": ("석천중", "상동중", "상일중", "부인중"),
    "상동고 상일고 상원고 중흥고 중원고": (
        "상동고", "상일고", "상원고", "중흥고", "중원고"
    ),
    "이화초 가내초 자란초": ("이화초", "가내초", "자란초"),
    "비전중 한광중 한광여중 평택여중 소사벌중": (
        "비전중", "한광중", "한광여중", "평택여중", "소사벌중"
    ),
    "비전고 한광고 한광여고 평택여고": (
        "비전고", "한광고", "한광여고", "평택여고"
    ),
    "수곡중 산남중": ("수곡중", "산남중"),
    "충북고 운호고 충북여고 산남고": (
        "충북고", "운호고", "충북여고", "산남고"
    ),
    "학남중 강북중": ("학남중", "강북중"),
    "양덕초 양서초 장흥초": ("양덕초", "양서초", "장흥초"),
    "양덕중 장흥중 대도중 환호여중": (
        "양덕중", "장흥중", "대도중", "환호여중"
    ),
    "장성고 포고 포여고 유성여고": (
        "장성고", "포고", "포여고", "유성여고"
    ),
    "오현초호매실중, 능실중, 영신중, 고색중": (
        "오현초", "호매실중", "능실중", "영신중", "고색중"
    ),
}

REQUIRED_DETAIL_TYPES = {
    "EducationalOrganization",
    "LocalBusiness",
    "WebPage",
    "ImageObject",
    "Article",
    "Service",
    "FAQPage",
    "BreadcrumbList",
    "ItemList",
}

FORBIDDEN_AUTHORING_PHRASES = (
    "핵심 키워드",
    "보조 키워드",
    "세부 키워드",
    "키워드:",
    "검색 의도",
    "작성자",
    "제작자",
    "필자",
    "원고",
    "이 글에서는",
    "이 글은",
    "이 페이지에서는",
    "이 페이지는",
    "본문 이미지",
    "메타 디스크립션",
    "검색엔진",
    "SEO",
    "AEO",
    "GEO",
    "LOCAL ACADEMY GUIDE",
    "ANSWER READY",
    "PARENT REVIEW",
)

FORBIDDEN_SOURCE_ERRORS = (
    "따라가며도",
    "영수(영어·수학·국어)",
    "영수(영어, 수학, 국어)",
    "영수(영어·수학· 국어)",
    "OO학생",
    "정보 준비중",
    "�",
)

# A first-person or institution-as-speaker claim is not supported merely by a
# manuscript.  Verified names, addresses, registration facts and grade/school
# lists are checked separately below.
UNSUPPORTED_OPERATION_RE = re.compile(
    r"(?:저희|본원|우리\s*학원|(?:학원|센터|강사진?|교사진?|선생님)(?:은|는|이|가|에서)?)"
    r"[^.!?\n]{0,55}"
    r"(?:운영|진행|지도|관리|제공|보장)(?:하고\s*있습니다|합니다|해\s*드립니다|드립니다)",
)
UNSUPPORTED_REVIEW_RE = re.compile(
    r"(?:실제\s*(?:학부모|학생)\s*후기|"
    r"성적(?:이|을)[^.!?\n]{0,12}(?:올랐습니다|향상되었습니다|올려\s*드립니다)|"
    r"점수(?:가|를)[^.!?\n]{0,12}(?:올랐습니다|올려\s*드립니다)|"
    r"합격(?:을)?\s*보장(?:합니다|해\s*드립니다))"
)

TAG_ATTR_RE = re.compile(
    r"([^\s=/>]+)(?:\s*=\s*(?:\"([^\"]*)\"|'([^']*)'|([^\s>]+)))?",
    re.S,
)
GRADE_RE = re.compile(r"(?<![가-힣A-Za-z0-9])(초[1-6]|중[1-3]|고[1-3])(?![가-힣A-Za-z0-9])")


@dataclass(frozen=True)
class CenterFact:
    slug: str
    locality: str
    city: str
    district: str
    center_name: str
    legal_name: str
    registration: str
    address: str
    english_grades: tuple[str, ...]
    math_grades: tuple[str, ...]
    common_grades: tuple[str, ...]
    schools: tuple[str, ...]


@dataclass(frozen=True)
class PageRecord:
    path: Path
    fact: CenterFact
    title: str
    meta: str
    canonical: str
    h1: str
    visible_text: str
    h2s: tuple[str, ...]
    faqs: tuple[tuple[str, str], ...]
    representative: str
    map_image: str


class Audit:
    def __init__(self) -> None:
        self.errors: list[dict[str, str]] = []
        self.warnings: list[dict[str, str]] = []

    def error(self, code: str, location: str | Path, message: str) -> None:
        self.errors.append(
            {"code": code, "location": display_path(location), "message": message}
        )

    def warn(self, code: str, location: str | Path, message: str) -> None:
        self.warnings.append(
            {"code": code, "location": display_path(location), "message": message}
        )


class VisibleTextParser(HTMLParser):
    """Collect user-visible main content while excluding sitewide chrome."""

    SKIP_TAGS = {"script", "style", "template", "noscript", "svg", "header", "footer", "nav"}
    VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}

    def __init__(self, require_main: bool) -> None:
        super().__init__(convert_charrefs=True)
        self.require_main = require_main
        self.main_depth = 0
        self.skip_depth = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        attr = {key.lower(): (value or "") for key, value in attrs}
        if tag == "main":
            self.main_depth += 1
        if self.skip_depth:
            if tag not in self.VOID_TAGS:
                self.skip_depth += 1
            return
        if tag in self.SKIP_TAGS:
            self.skip_depth = 1
            return
        hidden = (
            "hidden" in attr
            or attr.get("aria-hidden", "").lower() == "true"
            or re.search(r"(?:^|;)\s*display\s*:\s*none\b", attr.get("style", ""), re.I)
        )
        if hidden and tag not in self.VOID_TAGS:
            self.skip_depth += 1

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        # Visible text never comes from a void element's attributes.
        return

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if self.skip_depth:
            self.skip_depth -= 1
            return
        if tag == "main" and self.main_depth:
            self.main_depth -= 1

    def handle_data(self, data: str) -> None:
        if not self.skip_depth and (not self.require_main or self.main_depth):
            value = normalize(data)
            if value:
                self.parts.append(value)


def display_path(value: str | Path) -> str:
    if isinstance(value, Path):
        try:
            return value.relative_to(ROOT).as_posix()
        except ValueError:
            return str(value)
    return value


def normalize(value: Any) -> str:
    return re.sub(r"\s+", " ", html.unescape(str(value or ""))).strip()


def clean_fragment(value: str) -> str:
    value = re.sub(r"<(?:script|style|template)\b[^>]*>.*?</(?:script|style|template)>", " ", value, flags=re.I | re.S)
    return normalize(re.sub(r"<[^>]+>", " ", value))


def parse_attrs(raw: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for match in TAG_ATTR_RE.finditer(raw):
        key = match.group(1).lower()
        value = next((part for part in match.groups()[1:] if part is not None), "")
        result[key] = html.unescape(value)
    return result


def tags(source: str, tag: str) -> Iterator[dict[str, str]]:
    for match in re.finditer(rf"<{re.escape(tag)}\b([^>]*)>", source, re.I | re.S):
        yield parse_attrs(match.group(1))


def attr_values(source: str, tag: str, key: str, expected: str) -> list[str]:
    values: list[str] = []
    for attr in tags(source, tag):
        if attr.get(key, "").lower() == expected.lower():
            values.append(normalize(attr.get("content", "")))
    return values


def canonical_values(source: str) -> list[str]:
    result: list[str] = []
    for attr in tags(source, "link"):
        if "canonical" in attr.get("rel", "").lower().split():
            result.append(attr.get("href", ""))
    return result


def element_texts(source: str, tag: str) -> list[str]:
    return [
        clean_fragment(match.group(1))
        for match in re.finditer(
            rf"<{re.escape(tag)}\b[^>]*>(.*?)</{re.escape(tag)}\s*>",
            source,
            re.I | re.S,
        )
    ]


def visible_text(source: str) -> str:
    parser = VisibleTextParser(require_main=bool(re.search(r"<main\b", source, re.I)))
    parser.feed(source)
    parser.close()
    return normalize(" ".join(parser.parts))


def split_csv_list(value: str) -> tuple[str, ...]:
    return tuple(
        part.strip()
        for part in re.split(r"[,，./|·;\r\n]+", value or "")
        if part.strip()
    )


def normalize_slug(value: str) -> str:
    return re.sub(r"[\s-]+", "", normalize(value))


def school_values(*values: str) -> tuple[str, ...]:
    result: list[str] = []
    for raw in values:
        text = normalize(raw)
        if not text:
            continue
        if "모든 고등학교" in text or "상담 확인 필요" in text:
            continue
        corrected = SCHOOL_SOURCE_CORRECTIONS.get(text)
        tokens = corrected if corrected is not None else split_csv_list(text)
        for token in tokens:
            token = normalize(token)
            if not token or "모든 고등학교" in token or "상담 확인 필요" in token:
                continue
            result.append(token)
    return tuple(dict.fromkeys(result))


def load_facts(common: Path, audit: Audit) -> dict[str, CenterFact]:
    path = common / FACT_CSV_NAME
    if not path.is_file():
        audit.error("fact_csv_missing", path, "공통 사실 CSV가 없습니다")
        return {}
    try:
        with path.open(encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
    except (OSError, UnicodeError, csv.Error) as exc:
        audit.error("fact_csv_read", path, str(exc))
        return {}

    required = {
        "근처 수업가능 동네",
        "지역",
        "시or구",
        "센터명",
        "교육지원청명칭",
        "교육지원청 등록번호",
        "센터 주소",
        "타깃학교\n(초)",
        "타깃학교\n(중)",
        "타깃학교\n(고)",
        "가능학년\n(영어)",
        "가능학년\n(수학)",
    }
    columns = set(rows[0]) if rows else set()
    if missing := required - columns:
        audit.error("fact_csv_columns", path, f"필수 열 누락: {sorted(missing)}")
        return {}

    result: dict[str, CenterFact] = {}
    duplicates: list[str] = []
    for row_number, row in enumerate(rows, start=2):
        locality = normalize(row["근처 수업가능 동네"])
        slug = normalize_slug(locality)
        if not slug:
            audit.error("fact_slug_empty", path, f"{row_number}행 동네가 비어 있습니다")
            continue
        if slug in result:
            duplicates.append(slug)
            continue
        english = split_csv_list(row["가능학년\n(영어)"])
        math = split_csv_list(row["가능학년\n(수학)"])
        math_set = set(math)
        common_grades = tuple(grade for grade in english if grade in math_set)
        schools = school_values(
            row["타깃학교\n(초)"],
            row["타깃학교\n(중)"],
            row["타깃학교\n(고)"],
        )
        result[slug] = CenterFact(
            slug=slug,
            locality=locality,
            city=normalize(row["지역"]),
            district=normalize(row["시or구"]),
            center_name=normalize(row["센터명"]),
            legal_name=normalize(row["교육지원청명칭"]),
            registration=normalize(row["교육지원청 등록번호"]),
            address=normalize(row["센터 주소"]),
            english_grades=english,
            math_grades=math,
            common_grades=common_grades,
            schools=schools,
        )
    if duplicates:
        audit.error("fact_slug_duplicate", path, f"중복 동네: {sorted(set(duplicates))}")
    if len(result) != DETAIL_COUNT:
        audit.error("fact_count", path, f"CSV 고유 동네={len(result)}, 예상={DETAIL_COUNT}")
    for fact in result.values():
        missing_values = [
            name
            for name, value in (
                ("센터명", fact.center_name),
                ("법적명", fact.legal_name),
                ("등록번호", fact.registration),
                ("주소", fact.address),
            )
            if not value
        ]
        if missing_values:
            audit.error("fact_required_empty", fact.slug, f"사실값 누락: {missing_values}")
    return result


def expected_url(slug: str | None = None) -> str:
    route = "/과목별학원/영수학원/"
    if slug is not None:
        route += f"{slug}/"
    return BASE_URL + quote(route, safe="/")


def graph_nodes(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, dict) and isinstance(value.get("@graph"), list):
        return [node for node in value["@graph"] if isinstance(node, dict)]
    if isinstance(value, dict):
        return [value]
    if isinstance(value, list):
        return [node for node in value if isinstance(node, dict)]
    return []


def parse_jsonld(source: str, path: Path, audit: Audit) -> list[dict[str, Any]]:
    blocks = re.findall(
        r"<script\b[^>]*type\s*=\s*['\"]application/ld\+json['\"][^>]*>(.*?)</script\s*>",
        source,
        re.I | re.S,
    )
    if not blocks:
        audit.error("jsonld_missing", path, "JSON-LD 블록이 없습니다")
        return []
    nodes: list[dict[str, Any]] = []
    for number, block in enumerate(blocks, start=1):
        try:
            nodes.extend(graph_nodes(json.loads(html.unescape(block))))
        except (json.JSONDecodeError, TypeError) as exc:
            audit.error("jsonld_parse", path, f"{number}번 블록: {exc}")
    return nodes


def node_types(node: dict[str, Any]) -> set[str]:
    value = node.get("@type", [])
    if isinstance(value, str):
        return {value}
    if isinstance(value, list):
        return {item for item in value if isinstance(item, str)}
    return set()


def nodes_of_type(nodes: Sequence[dict[str, Any]], kind: str) -> list[dict[str, Any]]:
    return [node for node in nodes if kind in node_types(node)]


def nested_strings(value: Any) -> Iterator[str]:
    if isinstance(value, str):
        yield normalize(value)
    elif isinstance(value, dict):
        for item in value.values():
            yield from nested_strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from nested_strings(item)


def nested_typed_names(value: Any, kind: str) -> Iterator[str]:
    if isinstance(value, dict):
        if kind in node_types(value) and normalize(value.get("name", "")):
            yield normalize(value["name"])
        for item in value.values():
            yield from nested_typed_names(item, kind)
    elif isinstance(value, list):
        for item in value:
            yield from nested_typed_names(item, kind)


def breadcrumb_schema(nodes: Sequence[dict[str, Any]]) -> tuple[list[str], list[int], list[str]]:
    found = nodes_of_type(nodes, "BreadcrumbList")
    if len(found) != 1:
        return [], [], []
    names: list[str] = []
    positions: list[int] = []
    items: list[str] = []
    for entry in found[0].get("itemListElement", []):
        if not isinstance(entry, dict):
            continue
        names.append(normalize(entry.get("name", "")))
        try:
            positions.append(int(entry.get("position")))
        except (TypeError, ValueError):
            positions.append(-1)
        item = entry.get("item", "")
        if isinstance(item, dict):
            item = item.get("@id") or item.get("url") or ""
        items.append(str(item))
    return names, positions, items


def breadcrumb_visible(source: str) -> list[str]:
    block = ""
    for match in re.finditer(r"<(nav|ol|div)\b([^>]*)>", source, re.I | re.S):
        if "breadcrumb" in parse_attrs(match.group(2)).get("class", "").lower():
            closing = re.search(rf"</{match.group(1)}\s*>", source[match.end() :], re.I)
            if closing:
                block = source[match.end() : match.end() + closing.start()]
            break
    if not block:
        return []
    anchors = element_texts(block, "a")
    current_matches: list[str] = []
    for match in re.finditer(r"<(strong|span|li)\b([^>]*)>(.*?)</\1\s*>", block, re.I | re.S):
        attr = parse_attrs(match.group(2))
        text = clean_fragment(match.group(3))
        if (
            match.group(1).lower() == "strong"
            or attr.get("aria-current", "").lower() in {"page", "location", "true"}
        ) and text:
            current_matches.append(text)
    if anchors and current_matches:
        return anchors + [current_matches[-1]]
    plain = clean_fragment(block)
    return [normalize(part) for part in re.split(r"\s*(?:›|>|/)\s*", plain) if normalize(part)]


def faq_visible(source: str) -> tuple[tuple[str, str], ...]:
    result: list[tuple[str, str]] = []
    for match in re.finditer(r"<details\b([^>]*)>(.*?)</details\s*>", source, re.I | re.S):
        attr = parse_attrs(match.group(1))
        if "faq" not in attr.get("class", "").lower():
            continue
        body = match.group(2)
        summary = re.search(r"<summary\b[^>]*>(.*?)</summary\s*>", body, re.I | re.S)
        if not summary:
            continue
        question = clean_fragment(summary.group(1))
        question = re.sub(r"^(?:Q|질문)\s*[:.\-)]?\s*", "", question, flags=re.I)
        answer_html = body[summary.end() :]
        answer_match = re.search(
            r"<(?:div|p)\b[^>]*class\s*=\s*['\"][^'\"]*answer[^'\"]*['\"][^>]*>(.*?)</(?:div|p)\s*>",
            answer_html,
            re.I | re.S,
        )
        answer = clean_fragment(answer_match.group(1) if answer_match else answer_html)
        answer = re.sub(r"^(?:A|답변)\s*[:.\-)]?\s*", "", answer, flags=re.I)
        result.append((normalize(question), normalize(answer)))
    return tuple(result)


def faq_schema(nodes: Sequence[dict[str, Any]]) -> tuple[tuple[str, str], ...]:
    found = nodes_of_type(nodes, "FAQPage")
    if len(found) != 1:
        return ()
    result: list[tuple[str, str]] = []
    for question in found[0].get("mainEntity", []):
        if not isinstance(question, dict):
            continue
        answer = question.get("acceptedAnswer", {})
        text = answer.get("text", "") if isinstance(answer, dict) else ""
        result.append((normalize(question.get("name", "")), clean_fragment(str(text))))
    return tuple(result)


def heading_blocks(source: str) -> list[tuple[int, str, int, int]]:
    result: list[tuple[int, str, int, int]] = []
    for match in re.finditer(r"<h([2-4])\b[^>]*>(.*?)</h\1\s*>", source, re.I | re.S):
        result.append((int(match.group(1)), clean_fragment(match.group(2)), match.start(), match.end()))
    return result


def common_grade_section(source: str) -> tuple[str, ...] | None:
    for match in re.finditer(
        r"<dt\b[^>]*>(.*?)</dt\s*>\s*<dd\b[^>]*>(.*?)</dd\s*>",
        source,
        re.I | re.S,
    ):
        title = clean_fragment(match.group(1))
        if all(term in title for term in ("영어", "수학", "공통", "학년")):
            return tuple(dict.fromkeys(GRADE_RE.findall(clean_fragment(match.group(2)))))
    headings = heading_blocks(source)
    for index, (level, title, _start, end) in enumerate(headings):
        if all(term in title for term in ("영어", "수학", "공통", "학년")):
            stop = len(source)
            for next_level, _title, next_start, _end in headings[index + 1 :]:
                if next_level <= level:
                    stop = next_start
                    break
            return tuple(dict.fromkeys(GRADE_RE.findall(clean_fragment(source[end:stop]))))
    return None


def find_img(source: str, class_name: str) -> tuple[dict[str, str], str] | None:
    for match in re.finditer(r"<img\b([^>]*)>", source, re.I | re.S):
        attr = parse_attrs(match.group(1))
        if class_name in attr.get("class", "").split():
            return attr, match.group(0)
    return None


def class_block(source: str, class_name: str) -> str:
    for match in re.finditer(r"<(figure|section|div)\b([^>]*)>", source, re.I | re.S):
        if class_name in parse_attrs(match.group(2)).get("class", "").split():
            closing = re.search(rf"</{match.group(1)}\s*>", source[match.end() :], re.I)
            if closing:
                return source[match.end() : match.end() + closing.start()]
    return ""


def first_img(source: str) -> dict[str, str] | None:
    match = re.search(r"<img\b([^>]*)>", source, re.I | re.S)
    return parse_attrs(match.group(1)) if match else None


def resource_paths(attr: dict[str, str]) -> list[str]:
    result = [attr["src"]] if attr.get("src") else []
    if attr.get("srcset"):
        result.extend(part.strip().split()[0] for part in attr["srcset"].split(",") if part.strip())
    return result


def resolve_resource(page: Path, value: str) -> Path | None:
    raw_value = html.unescape(value).strip()
    if raw_value.startswith("data:"):
        return None
    split = urlsplit(raw_value)
    raw = unquote(split.path)
    if not raw:
        return None
    if split.scheme or split.netloc:
        if split.scheme.lower() != "https" or split.netloc.lower() != BASE_HOST:
            return None
        candidate = ROOT / raw.lstrip("/")
    else:
        candidate = ROOT / raw.lstrip("/") if raw.startswith("/") else page.parent / raw
    try:
        return candidate.resolve()
    except OSError:
        return candidate


def public_asset_url(asset: Path) -> str | None:
    try:
        relative = asset.resolve().relative_to(ROOT.resolve()).as_posix()
    except (OSError, ValueError):
        return None
    return BASE_URL + quote("/" + relative, safe="/")


def check_image(
    page: Path,
    role: str,
    attr: dict[str, str] | None,
    audit: Audit,
) -> tuple[str, Path | None]:
    if attr is None:
        audit.error(f"image_{role}_missing", page, f"{role} 이미지가 없습니다")
        return "", None
    if not normalize(attr.get("alt", "")):
        audit.error(f"image_{role}_alt", page, f"{role} 이미지 ALT가 비어 있습니다")
    src = attr.get("src", "")
    if not src:
        audit.error(f"image_{role}_src", page, f"{role} 이미지 src가 없습니다")
        return "", None
    resolved: Path | None = None
    for value in resource_paths(attr):
        path = resolve_resource(page, value)
        if path is None:
            if (
                role == "representative"
                and re.fullmatch(
                    r"https://wawa-center\.com/wp-content/uploads/[0-9]{4}/[0-9]{2}/I[0-9]+\.jpg",
                    value,
                    re.I,
                )
            ):
                continue
            audit.error(f"image_{role}_remote", page, f"{role} 이미지는 로컬 실파일이어야 합니다: {value}")
            continue
        try:
            path.resolve().relative_to(ROOT.resolve())
        except (OSError, ValueError):
            audit.error(f"image_{role}_outside", page, f"사이트 루트 밖 이미지: {value}")
            continue
        if not path.is_file() or path.stat().st_size <= 0:
            audit.error(f"image_{role}_file", page, f"이미지 실파일 없음/빈 파일: {value}")
        if value == src:
            resolved = path
    return src, resolved


def item_url(entry: dict[str, Any]) -> str:
    value: Any = entry.get("item", entry.get("url", ""))
    if isinstance(value, dict):
        value = value.get("@id") or value.get("url") or ""
    return str(value)


def check_detail_schema(
    page: Path,
    source: str,
    nodes: list[dict[str, Any]],
    fact: CenterFact,
    canonical: str,
    h1: str,
    visible: str,
    representative_url: str | None,
    audit: Audit,
) -> tuple[tuple[str, str], ...]:
    present: set[str] = set()
    for node in nodes:
        present.update(node_types(node))
    if missing := REQUIRED_DETAIL_TYPES - present:
        audit.error("schema_types", page, f"필수 @type 누락: {sorted(missing)}")

    for kind in REQUIRED_DETAIL_TYPES - {"EducationalOrganization", "LocalBusiness", "ItemList"}:
        count = len(nodes_of_type(nodes, kind))
        if count != 1:
            audit.error("schema_type_count", page, f"{kind} 노드={count}, 예상=1")

    educational = nodes_of_type(nodes, "EducationalOrganization")
    local = nodes_of_type(nodes, "LocalBusiness")
    combined = [node for node in nodes if {"EducationalOrganization", "LocalBusiness"} <= node_types(node)]
    if len(educational) != 1 or len(local) != 1 or len(combined) != 1:
        audit.error(
            "schema_org_combined",
            page,
            f"EducationalOrganization={len(educational)}, LocalBusiness={len(local)}, 결합노드={len(combined)}",
        )

    article = nodes_of_type(nodes, "Article")
    webpage = nodes_of_type(nodes, "WebPage")
    service = nodes_of_type(nodes, "Service")
    organization = combined
    contracts = (
        (article[0] if len(article) == 1 else {}, ("about", "mentions", "articleSection"), "Article"),
        (webpage[0] if len(webpage) == 1 else {}, ("about", "mentions", "hasPart"), "WebPage"),
        (service[0] if len(service) == 1 else {}, ("about", "mentions", "makesOffer"), "Service"),
        (organization[0] if len(organization) == 1 else {}, ("makesOffer",), "Organization"),
    )
    for node, fields, label in contracts:
        absent = [field for field in fields if not node.get(field)]
        if absent:
            audit.error("schema_properties", page, f"{label} 필수 속성 누락/빈 값: {absent}")

    if organization:
        org = organization[0]
        if normalize(org.get("name", "")) != fact.center_name:
            audit.error("schema_center_name", page, f"organization name은 CSV 센터명과 정확히 같아야 합니다: {fact.center_name}")
        if normalize(org.get("legalName", "")) != fact.legal_name:
            audit.error("schema_legal_name", page, f"legalName 불일치: {fact.legal_name}")
        blob = normalize(" ".join(nested_strings(org)))
        for label, value in (("주소", fact.address), ("등록번호", fact.registration)):
            if value not in blob:
                audit.error("schema_fact", page, f"Organization에 CSV {label}가 없습니다: {value}")

    names, positions, items = breadcrumb_schema(nodes)
    expected_names = ["홈", "과목별학원", "영수학원", h1]
    expected_items = [
        BASE_URL + "/",
        BASE_URL + quote("/과목별학원/", safe="/"),
        expected_url(),
        canonical,
    ]
    if names != expected_names or positions != [1, 2, 3, 4] or items != expected_items:
        audit.error(
            "schema_breadcrumb",
            page,
            f"BreadcrumbList 불일치 names={names}, positions={positions}, items={items}",
        )

    schema_faq = faq_schema(nodes)
    shown_faq = faq_visible(source)
    if shown_faq != schema_faq:
        audit.error("faq_visible_schema", page, f"화면 FAQ와 스키마 FAQ 불일치: {len(shown_faq)}/{len(schema_faq)}")
    if not 4 <= len(shown_faq) <= 6:
        audit.error("faq_count", page, f"FAQ={len(shown_faq)}, 예상 범위=4~6")
    if any(not question or not answer for question, answer in shown_faq):
        audit.error("faq_empty", page, "질문 또는 답변이 빈 FAQ가 있습니다")
    if len(set(shown_faq)) != len(shown_faq):
        audit.error("faq_duplicate_within", page, "한 페이지 안에 같은 FAQ가 반복됩니다")

    if any("Review" in node_types(node) or "AggregateRating" in node_types(node) for node in nodes):
        audit.error("unsupported_review_schema", page, "근거 없는 Review/AggregateRating 구조화 데이터가 있습니다")
    serialized = json.dumps(nodes, ensure_ascii=False)
    if '"review"' in serialized or '"aggregateRating"' in serialized:
        audit.error("unsupported_review_schema", page, "근거 없는 review/aggregateRating 속성이 있습니다")

    image_objects = nodes_of_type(nodes, "ImageObject")
    if len(image_objects) == 1 and representative_url:
        urls = {
            normalize(value)
            for key in ("contentUrl", "url")
            for value in ([image_objects[0].get(key)] if not isinstance(image_objects[0].get(key), list) else image_objects[0].get(key))
            if isinstance(value, str)
        }
        if representative_url not in urls:
            audit.error("schema_image", page, f"ImageObject가 숨김 대표이미지와 연결되지 않았습니다: {representative_url}")

    # All whitelisted schools must be visible and represented as mentions.  A
    # school from another row is caught separately in the collection audit.
    mentions: list[Any] = []
    for node in nodes:
        value = node.get("mentions", [])
        mentions.extend(value if isinstance(value, list) else [value] if value else [])
    mentioned_schools = set(nested_typed_names(mentions, "EducationalOrganization"))
    expected_schools = set(fact.schools)
    if mentioned_schools != expected_schools:
        audit.error(
            "school_mentions_mismatch",
            page,
            f"missing={sorted(expected_schools-mentioned_schools)}, extra={sorted(mentioned_schools-expected_schools)}",
        )
    for school in fact.schools:
        if school not in visible:
            audit.error("school_missing_visible", page, f"CSV 타깃학교가 화면에 없습니다: {school}")

    detail_lists = nodes_of_type(nodes, "ItemList")
    url_lists = [
        item_list
        for item_list in detail_lists
        if any(
            isinstance(entry, dict) and item_url(entry)
            for entry in item_list.get("itemListElement", [])
            if isinstance(item_list.get("itemListElement", []), list)
        )
    ]
    expected_url_list_ids = {canonical + "#related", canonical + "#local-study-network"}
    actual_url_list_ids = [normalize(item_list.get("@id", "")) for item_list in url_lists]
    if len(actual_url_list_ids) != 2 or set(actual_url_list_ids) != expected_url_list_ids:
        audit.error(
            "detail_itemlist_url_ids",
            page,
            f"actual={actual_url_list_ids}, expected={sorted(expected_url_list_ids)}",
        )
    for item_list in url_lists:
        entries = item_list.get("itemListElement", [])
        if not isinstance(entries, list) or not entries:
            audit.error(
                "detail_itemlist_empty",
                page,
                f"ItemList가 비어 있습니다: {normalize(item_list.get('@id', ''))}",
            )
        else:
            if item_list.get("numberOfItems") != len(entries):
                audit.error(
                    "detail_itemlist_count",
                    page,
                    f"numberOfItems={item_list.get('numberOfItems')!r}, actual={len(entries)}: "
                    f"{normalize(item_list.get('@id', ''))}",
                )
            for entry in entries:
                if not isinstance(entry, dict) or not item_url(entry):
                    audit.error(
                        "detail_itemlist_entry",
                        page,
                        f"ItemList 항목 URL이 없습니다: {normalize(item_list.get('@id', ''))}",
                    )
                    break
    return shown_faq


def check_facts(
    page: Path,
    source: str,
    visible: str,
    fact: CenterFact,
    school_universe: set[str],
    audit: Audit,
) -> None:
    for label, value in (
        ("센터명", fact.center_name),
        ("주소", fact.address),
        ("법적명", fact.legal_name),
        ("등록번호", fact.registration),
    ):
        if value and value not in visible:
            audit.error("fact_missing_visible", page, f"CSV {label}가 화면에 없습니다: {value}")

    grades = common_grade_section(source)
    if grades is None:
        audit.error("common_grades_section", page, "영어·수학 공통 가능 학년 제목/구간이 없습니다")
    elif set(grades) != set(fact.common_grades):
        audit.error(
            "common_grades_mismatch",
            page,
            f"공통 학년 화면={list(grades)}, CSV 교집합={list(fact.common_grades)}",
        )

    unexpected = []
    for school in school_universe - set(fact.schools):
        if re.search(rf"(?<![가-힣A-Za-z0-9]){re.escape(school)}(?![가-힣A-Za-z0-9])", visible):
            unexpected.append(school)
    if unexpected:
        audit.error("school_not_whitelisted", page, f"다른 지역 CSV 학교명 노출: {sorted(unexpected)[:12]}")

    # Compare only the two owned school-chip surfaces.  Scanning every class
    # containing ``school`` also captures authored prose such as ``확인하고``.
    source_school_values = [
        normalize(attr.get("data-source-school", ""))
        for attr in tags(source, "span")
        if "data-source-school" in attr
    ]
    center_profile_values = [
        value
        for value in element_texts(
            class_block(source, "center-profile-school-list"), "span"
        )
        if re.search(r"(?:초등학교|중학교|고등학교|초|중|고)$", value)
    ]
    expected_schools = set(fact.schools)
    for code, values in (
        ("school_source_chip_mismatch", source_school_values),
        ("school_profile_chip_mismatch", center_profile_values),
    ):
        actual_schools = set(values)
        duplicates = sorted(name for name, count in Counter(values).items() if count > 1)
        if actual_schools != expected_schools or duplicates:
            audit.error(
                code,
                page,
                f"missing={sorted(expected_schools-actual_schools)}, extra={sorted(actual_schools-expected_schools)}, duplicates={duplicates}",
            )

    for phrase in FORBIDDEN_AUTHORING_PHRASES + FORBIDDEN_SOURCE_ERRORS:
        found = (
            re.search(r"(?<![가-힣])원고(?![가-힣])", source)
            if phrase == "원고"
            else phrase in source
        )
        if found:
            audit.error("forbidden_phrase", page, f"금지된 제작/원고 표현: {phrase}")
    if "???" in source:
        audit.error("encoding_damage", page, "물음표 3개 연속(인코딩 손상 가능성)")
    if UNSUPPORTED_OPERATION_RE.search(visible):
        audit.error("unsupported_operation_claim", page, f"근거 없는 기관 화자형 운영 주장: {UNSUPPORTED_OPERATION_RE.search(visible).group(0)}")
    if UNSUPPORTED_REVIEW_RE.search(visible):
        audit.error("unsupported_result_claim", page, f"근거 없는 후기/결과 주장: {UNSUPPORTED_REVIEW_RE.search(visible).group(0)}")


def internal_target(page: Path, href: str) -> tuple[Path | None, str]:
    value = html.unescape(href).strip()
    if not value or value.startswith(("mailto:", "tel:", "javascript:", "data:")):
        return None, ""
    split = urlsplit(value)
    if split.scheme and split.scheme.lower() not in {"http", "https"}:
        return None, ""
    if split.netloc:
        host = (split.hostname or "").lower()
        if host not in {"xn--ru4bi8s1tac0p.kr", "학습코칭.kr", "www.xn--ru4bi8s1tac0p.kr", "www.학습코칭.kr"}:
            return None, ""
    path_text = unquote(split.path)
    if not path_text:
        candidate = page
    elif path_text.startswith("/"):
        candidate = ROOT / path_text.lstrip("/")
    else:
        candidate = page.parent / path_text
    try:
        candidate = candidate.resolve()
    except OSError:
        pass
    if candidate.is_dir() or path_text.endswith("/") or (not candidate.suffix and not candidate.exists()):
        candidate /= "index.html"
    return candidate, unquote(split.fragment)


def element_ids(source: str) -> set[str]:
    result: set[str] = set()
    for match in re.finditer(r"<[A-Za-z][^>]*>", source, re.S):
        value = parse_attrs(match.group(0)[1:-1]).get("id")
        if value:
            result.add(value)
    return result


def check_internal_links(page: Path, source: str, audit: Audit, require_detail_links: bool) -> set[Path]:
    targets: set[Path] = set()
    ids_cache: dict[Path, set[str]] = {page.resolve(): element_ids(source)}
    for attr in tags(source, "a"):
        href = attr.get("href", "")
        target, fragment = internal_target(page, href)
        if target is None:
            continue
        try:
            target.resolve().relative_to(ROOT.resolve())
        except (OSError, ValueError):
            audit.error("internal_link_outside", page, f"사이트 밖 내부 링크: {href}")
            continue
        targets.add(target)
        if not target.is_file():
            audit.error("internal_link_missing", page, f"내부 링크 대상 없음: {href}")
            continue
        if fragment:
            key = target.resolve()
            if key not in ids_cache:
                try:
                    ids_cache[key] = element_ids(target.read_text(encoding="utf-8"))
                except (OSError, UnicodeError):
                    ids_cache[key] = set()
            if fragment not in ids_cache[key]:
                audit.error("internal_fragment_missing", page, f"링크 앵커 없음: {href}")
    if require_detail_links:
        hub = (TARGET / "index.html").resolve()
        subject_hub = (ROOT / "과목별학원" / "index.html").resolve()
        if hub not in {path.resolve() for path in targets}:
            audit.error("internal_hub_link", page, "영수학원 허브 내부 링크가 없습니다")
        if subject_hub not in {path.resolve() for path in targets}:
            audit.error("internal_parent_link", page, "과목별학원 상위 허브 내부 링크가 없습니다")
        html_targets = {path for path in targets if path.name == "index.html"}
        if len(html_targets) < 3:
            audit.error("internal_link_count", page, f"고유 내부 페이지 링크={len(html_targets)}, 최소=3")
    return targets


def audit_detail(
    page: Path,
    fact: CenterFact,
    school_universe: set[str],
    audit: Audit,
) -> PageRecord | None:
    try:
        source = page.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        audit.error("html_read", page, str(exc))
        return None

    body_tags = list(tags(source, "body"))
    expected_body_classes = {"subject-academy-page", "yeongsu-subject-page"}
    actual_body_classes = set(body_tags[0].get("class", "").split()) if len(body_tags) == 1 else set()
    if len(body_tags) != 1 or not expected_body_classes <= actual_body_classes:
        audit.error("body_contract", page, f"body class에 {sorted(expected_body_classes)}가 모두 필요합니다")

    expected_h1 = f"{fact.locality} 영수학원"
    expected_title = f"{fact.locality} 영수학원 | 학습코칭 학원 안내"
    canonical = expected_url(fact.slug)
    titles = element_texts(source, "title")
    h1s = element_texts(source, "h1")
    descriptions = attr_values(source, "meta", "name", "description")
    og_titles = attr_values(source, "meta", "property", "og:title")
    og_descriptions = attr_values(source, "meta", "property", "og:description")
    canonicals = canonical_values(source)
    og_urls = attr_values(source, "meta", "property", "og:url")
    checks = (
        (titles, [expected_title], "title_exact"),
        (og_titles, [expected_title], "og_title_exact"),
        (h1s, [expected_h1], "h1_exact"),
        (canonicals, [canonical], "canonical_exact"),
        (og_urls, [canonical], "og_url_exact"),
    )
    for actual, expected, code in checks:
        if actual != expected:
            audit.error(code, page, f"실제={actual}, 예상={expected}")
    if len(descriptions) != 1:
        audit.error("meta_description_count", page, f"description={len(descriptions)}, 예상=1")
        meta = descriptions[0] if descriptions else ""
    else:
        meta = descriptions[0]
        if not 70 <= len(meta) <= 105:
            audit.error("meta_description_length", page, f"길이={len(meta)}, 예상=70~105자")
    if og_descriptions != [meta]:
        audit.error("og_description_exact", page, "og:description이 meta description과 정확히 같지 않습니다")

    visible = visible_text(source)
    breadcrumb = breadcrumb_visible(source)
    expected_breadcrumb = ["홈", "과목별학원", "영수학원", expected_h1]
    if breadcrumb != expected_breadcrumb:
        audit.error("visible_breadcrumb", page, f"화면 breadcrumb={breadcrumb}, 예상={expected_breadcrumb}")

    nodes = parse_jsonld(source, page, audit)

    representative_found = find_img(source, "subject-hidden-representative")
    representative_attr = representative_found[0] if representative_found else None
    if representative_attr is not None:
        if representative_attr.get("data-role") != "representative-image":
            audit.error("image_representative_role", page, '대표이미지 data-role="representative-image" 누락')
        style = representative_attr.get("style", "")
        hidden = (
            "hidden" in representative_attr
            or representative_attr.get("aria-hidden", "").lower() == "true"
            or re.search(r"display\s*:\s*none", style, re.I)
        )
        if not hidden:
            audit.error("image_representative_hidden", page, "대표이미지가 숨김 처리되지 않았습니다")
    rep_src, rep_file = check_image(page, "representative", representative_attr, audit)
    body_attr = first_img(class_block(source, "subject-body-card"))
    _body_src, _body_file = check_image(page, "body", body_attr, audit)
    map_attr = first_img(class_block(source, "subject-map-card"))
    map_src, _map_file = check_image(page, "map", map_attr, audit)
    rep_public = public_asset_url(rep_file) if rep_file else None
    og_images = attr_values(source, "meta", "property", "og:image")
    if rep_public and og_images != [rep_public]:
        audit.error("og_image_exact", page, f"og:image={og_images}, 대표이미지={rep_public}")

    shown_faq = check_detail_schema(
        page, source, nodes, fact, canonical, expected_h1, visible, rep_public, audit
    )
    check_facts(page, source, visible, fact, school_universe, audit)
    check_internal_links(page, source, audit, require_detail_links=True)

    h2s = tuple(element_texts(source, "h2"))
    if len(h2s) != len(set(h2s)):
        duplicates = [name for name, count in Counter(h2s).items() if count > 1]
        audit.error("h2_duplicate_within", page, f"페이지 안 H2 중복: {duplicates}")

    return PageRecord(
        path=page,
        fact=fact,
        title=titles[0] if len(titles) == 1 else "",
        meta=meta,
        canonical=canonicals[0] if len(canonicals) == 1 else "",
        h1=h1s[0] if len(h1s) == 1 else "",
        visible_text=visible,
        h2s=h2s,
        faqs=shown_faq,
        representative=rep_src,
        map_image=map_src,
    )


def list_item_urls(node: dict[str, Any]) -> tuple[list[str], list[int]]:
    urls: list[str] = []
    positions: list[int] = []
    for entry in node.get("itemListElement", []):
        if not isinstance(entry, dict):
            continue
        urls.append(item_url(entry))
        try:
            positions.append(int(entry.get("position")))
        except (TypeError, ValueError):
            positions.append(-1)
    return urls, positions


def check_hub(hub: Path, facts: dict[str, CenterFact], audit: Audit) -> None:
    if not hub.is_file():
        audit.error("hub_missing", hub, "영수학원 허브가 없습니다")
        return
    try:
        source = hub.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        audit.error("hub_read", hub, str(exc))
        return
    canonical = expected_url()
    if canonical_values(source) != [canonical]:
        audit.error("hub_canonical", hub, f"허브 canonical은 {canonical}이어야 합니다")
    if attr_values(source, "meta", "property", "og:url") != [canonical]:
        audit.error("hub_og_url", hub, f"허브 og:url은 {canonical}이어야 합니다")
    descriptions = attr_values(source, "meta", "name", "description")
    if len(descriptions) != 1 or attr_values(source, "meta", "property", "og:description") != descriptions:
        audit.error("hub_description", hub, "허브 meta/og description 단일·동일 조건 실패")
    titles = element_texts(source, "title")
    if len(titles) != 1 or attr_values(source, "meta", "property", "og:title") != titles:
        audit.error("hub_title", hub, "허브 title/og:title 단일·동일 조건 실패")
    if len(element_texts(source, "h1")) != 1:
        audit.error("hub_h1", hub, "허브 H1은 정확히 1개여야 합니다")

    nodes = parse_jsonld(source, hub, audit)
    item_lists = nodes_of_type(nodes, "ItemList")
    if len(item_lists) != 1:
        audit.error("hub_itemlist_count", hub, f"ItemList={len(item_lists)}, 예상=1")
    else:
        item_list = item_lists[0]
        urls, positions = list_item_urls(item_list)
        expected_urls = {expected_url(slug) for slug in facts}
        try:
            number = int(item_list.get("numberOfItems"))
        except (TypeError, ValueError):
            number = -1
        if number != DETAIL_COUNT or len(urls) != DETAIL_COUNT:
            audit.error("hub_itemlist_size", hub, f"numberOfItems={number}, entries={len(urls)}, 예상={DETAIL_COUNT}")
        if set(urls) != expected_urls or len(set(urls)) != DETAIL_COUNT:
            missing = sorted(expected_urls - set(urls))[:10]
            extra = sorted(set(urls) - expected_urls)[:10]
            audit.error("hub_itemlist_urls", hub, f"ItemList URL 집합 불일치 missing={missing}, extra={extra}")
        if positions != list(range(1, DETAIL_COUNT + 1)):
            audit.error("hub_itemlist_positions", hub, "ItemList position이 1~371 연속 순서가 아닙니다")

    detail_files = {(TARGET / slug / "index.html").resolve() for slug in facts}
    targets = check_internal_links(hub, source, audit, require_detail_links=False)
    linked_details = {path.resolve() for path in targets if path.resolve() in detail_files}
    if linked_details != detail_files:
        audit.error(
            "hub_detail_links",
            hub,
            f"고유 상세 링크={len(linked_details)}, 예상={DETAIL_COUNT}; 누락={len(detail_files-linked_details)}",
        )

    search_inputs = [attr for attr in tags(source, "input") if attr.get("type", "").lower() == "search"]
    if len(search_inputs) != 1:
        audit.error("hub_search_input", hub, f'type="search" 입력={len(search_inputs)}, 예상=1')
    else:
        search_id = search_inputs[0].get("id", "")
        if not search_id:
            audit.error("hub_search_id", hub, "검색 입력 id가 없습니다")
        if not (search_inputs[0].get("aria-label") or search_inputs[0].get("placeholder")):
            audit.error("hub_search_accessible", hub, "검색 입력 aria-label/placeholder가 없습니다")
        scripts = " ".join(re.findall(r"<script\b[^>]*>(.*?)</script\s*>", source, re.I | re.S))
        for attr in tags(source, "script"):
            src = attr.get("src")
            if not src:
                continue
            path = resolve_resource(hub, src)
            if path and path.is_file():
                try:
                    scripts += " " + path.read_text(encoding="utf-8")
                except (OSError, UnicodeError):
                    pass
        inline_handler = search_inputs[0].get("oninput", "") or search_inputs[0].get("onkeyup", "")
        has_event = bool(
            inline_handler
            or re.search(r"addEventListener\s*\(\s*['\"](?:input|keyup)['\"]", scripts)
        )
        has_filter = bool(re.search(r"(?:\.filter\s*\(|\.includes\s*\(|\.hidden\b|style\.display|classList\.)", scripts))
        if not search_id or search_id not in scripts or not has_event or not has_filter:
            audit.error("hub_search_function", hub, "검색 입력과 실제 필터링 코드의 연결을 확인할 수 없습니다")


def shingles(text: str, size: int = 5) -> frozenset[tuple[str, ...]]:
    words = re.findall(r"[가-힣]+|[a-z]+|\d+(?:[.,]\d+)*", text.lower())
    return frozenset(tuple(words[index : index + size]) for index in range(max(0, len(words) - size + 1)))


def masked_text(record: PageRecord) -> str:
    fact = record.fact
    value = record.visible_text
    # Replace longest values first so an address is not partially consumed by
    # its city/district, and use a single token for every school.
    mapping: list[tuple[str, str]] = [
        (f"{fact.locality} 영수학원", " 지역영수학원 "),
        (fact.center_name, " 센터명 "),
        (fact.legal_name, " 법적명 "),
        (fact.registration, " 등록번호 "),
        (fact.address, " 센터주소 "),
        *[(school, " 학교명 ") for school in fact.schools],
        (fact.district, " 시군구 "),
        (fact.city, " 지역 "),
        (fact.locality, " 동네 "),
    ]
    for old, new in sorted(((old, new) for old, new in mapping if old), key=lambda pair: len(pair[0]), reverse=True):
        value = value.replace(old, new)
    value = GRADE_RE.sub(" 학년 ", value)
    value = re.sub(r"\b\d+(?:[.,-]\d+)*\b", " 숫자 ", value)
    return normalize(value)


def max_pair_similarity(
    records: Sequence[PageRecord],
    masked: bool,
    audit: Audit,
) -> tuple[float, tuple[str, str]]:
    sets: list[frozenset[tuple[str, ...]]] = []
    for record in records:
        value = masked_text(record) if masked else record.visible_text
        current = shingles(value)
        if len(current) < 20:
            audit.error("shingle_content_short", record.path, f"5-shingle 수={len(current)}, 최소=20")
        sets.append(current)
    best_score = 0.0
    best_pair = ("", "")
    for left in range(len(records)):
        a = sets[left]
        for right in range(left + 1, len(records)):
            b = sets[right]
            if not a and not b:
                score = 1.0
            elif not a or not b:
                score = 0.0
            else:
                # Jaccard 5-shingle similarity is symmetric and does not let a
                # very short page hide as a subset of a long page.
                intersection = len(a & b)
                score = intersection / (len(a) + len(b) - intersection)
            if score > best_score:
                best_score = score
                best_pair = (records[left].fact.slug, records[right].fact.slug)
    return best_score, best_pair


def duplicate_collection_checks(records: Sequence[PageRecord], audit: Audit, threshold: float) -> dict[str, Any]:
    fields = {
        "title": [record.title for record in records],
        "meta": [record.meta for record in records],
        "canonical": [record.canonical for record in records],
        "H1": [record.h1 for record in records],
        "representative": [record.representative for record in records],
        "map_image": [record.map_image for record in records],
    }
    uniqueness: dict[str, int] = {}
    for label, values in fields.items():
        uniqueness[label] = len(set(values))
        duplicate_count = len(values) - len(set(values))
        if duplicate_count:
            samples = [value for value, count in Counter(values).items() if count > 1][:5]
            audit.error(f"duplicate_{label.lower()}", "collection", f"중복={duplicate_count}, 예={samples}")

    h2_occurrences: dict[str, list[str]] = {}
    faq_questions: dict[str, list[str]] = {}
    faq_answers: dict[str, list[str]] = {}
    for record in records:
        for heading in record.h2s:
            h2_occurrences.setdefault(normalize(heading), []).append(record.fact.slug)
        for question, answer in record.faqs:
            faq_questions.setdefault(normalize(question), []).append(record.fact.slug)
            faq_answers.setdefault(normalize(answer), []).append(record.fact.slug)
    for label, mapping in (
        ("h2", h2_occurrences),
        ("faq_question", faq_questions),
        ("faq_answer", faq_answers),
    ):
        duplicates = {text: pages for text, pages in mapping.items() if text and len(pages) > 1}
        if duplicates:
            samples = [f"{text[:80]} -> {pages[:5]}" for text, pages in list(duplicates.items())[:8]]
            audit.error(f"duplicate_{label}", "collection", f"중복 문구={len(duplicates)}; 예={samples}")

    exact_score, exact_pair = max_pair_similarity(records, masked=False, audit=audit)
    masked_score, masked_pair = max_pair_similarity(records, masked=True, audit=audit)
    if exact_score >= threshold:
        audit.error("similarity_exact", "collection", f"exact 5-shingle max={exact_score:.6f}, pair={exact_pair}, 기준 < {threshold}")
    if masked_score >= threshold:
        audit.error("similarity_masked", "collection", f"masked 5-shingle max={masked_score:.6f}, pair={masked_pair}, 기준 < {threshold}")
    return {
        "uniqueness": uniqueness,
        "h2_unique": len(h2_occurrences),
        "faq_questions_unique": len(faq_questions),
        "faq_answers_unique": len(faq_answers),
        "exact_5_shingle_max": round(exact_score, 6),
        "exact_5_shingle_pair": exact_pair,
        "masked_5_shingle_max": round(masked_score, 6),
        "masked_5_shingle_pair": masked_pair,
        "similarity_limit_exclusive": threshold,
    }


def canonical_for_html(path: Path, audit: Audit) -> str | None:
    try:
        source = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        audit.error("site_html_read", path, str(exc))
        return None
    robots = attr_values(source, "meta", "name", "robots")
    if any("noindex" in value.lower() for value in robots):
        return None
    values = canonical_values(source)
    if len(values) != 1:
        audit.error("site_canonical_count", path, f"공개 HTML canonical={len(values)}, 예상=1")
        return None
    return values[0]


def check_sitemap_html_set(audit: Audit) -> dict[str, int]:
    ignored_parts = {".git", ".vercel", "tmp", "node_modules", "__pycache__"}
    public: list[tuple[Path, str]] = []
    for path in ROOT.rglob("index.html"):
        relative = path.relative_to(ROOT)
        if any(part in ignored_parts for part in relative.parts):
            continue
        canonical = canonical_for_html(path, audit)
        if canonical:
            public.append((path, canonical))
    counter = Counter(value for _path, value in public)
    duplicates = [value for value, count in counter.items() if count > 1]
    if duplicates:
        audit.error("site_canonical_duplicate", "site", f"HTML canonical 중복={len(duplicates)}, 예={duplicates[:10]}")

    sitemap_path = ROOT / "sitemap.xml"
    try:
        tree = ET.parse(sitemap_path)
        namespace = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
        locs = [normalize(node.text) for node in tree.findall(".//sm:loc", namespace)]
    except (OSError, ET.ParseError) as exc:
        audit.error("sitemap_read", sitemap_path, str(exc))
        return {"public_html": len(public), "sitemap_urls": 0}
    if len(locs) != len(set(locs)):
        audit.error("sitemap_duplicates", sitemap_path, f"중복 loc={len(locs)-len(set(locs))}")
    html_set = set(counter)
    sitemap_set = set(locs)
    if html_set != sitemap_set:
        audit.error(
            "sitemap_html_set",
            sitemap_path,
            f"HTML에만={len(html_set-sitemap_set)} {sorted(html_set-sitemap_set)[:8]}, sitemap에만={len(sitemap_set-html_set)} {sorted(sitemap_set-html_set)[:8]}",
        )
    return {"public_html": len(public), "sitemap_urls": len(locs)}


def run(common: Path, threshold: float, error_sample_limit: int) -> tuple[dict[str, Any], int]:
    audit = Audit()
    facts = load_facts(common, audit)
    hub = TARGET / "index.html"
    all_indexes = sorted(TARGET.rglob("index.html")) if TARGET.exists() else []
    detail_paths = sorted(path for path in all_indexes if path != hub)
    direct_details = sorted(path for path in detail_paths if path.parent.parent == TARGET)
    if len(all_indexes) != DETAIL_COUNT + 1:
        audit.error("target_page_count", TARGET, f"허브+상세={len(all_indexes)}, 예상={DETAIL_COUNT+1}")
    if len(direct_details) != DETAIL_COUNT or len(detail_paths) != len(direct_details):
        audit.error("detail_page_layout", TARGET, f"직접 하위 상세={len(direct_details)}, 전체 상세 index={len(detail_paths)}, 예상={DETAIL_COUNT}")

    csv_slugs = set(facts)
    file_slugs = {path.parent.name for path in direct_details}
    if file_slugs != csv_slugs:
        audit.error(
            "slug_csv_match",
            TARGET,
            f"CSV에만={sorted(csv_slugs-file_slugs)[:20]}, 파일에만={sorted(file_slugs-csv_slugs)[:20]}",
        )

    school_universe = {school for fact in facts.values() for school in fact.schools}
    records: list[PageRecord] = []
    for page in direct_details:
        fact = facts.get(page.parent.name)
        if fact is None:
            continue
        record = audit_detail(page, fact, school_universe, audit)
        if record:
            records.append(record)

    check_hub(hub, facts, audit)
    collection: dict[str, Any] = {}
    if len(records) == DETAIL_COUNT:
        collection = duplicate_collection_checks(records, audit, threshold)
    else:
        audit.error("collection_incomplete", "collection", f"분석 가능한 상세={len(records)}, 예상={DETAIL_COUNT}")
    sitemap = check_sitemap_html_set(audit)

    by_code = Counter(item["code"] for item in audit.errors)
    warning_by_code = Counter(item["code"] for item in audit.warnings)
    report: dict[str, Any] = {
        "audit": "영수학원 subject pages strict release audit",
        "strict_pass": not audit.errors,
        "common_csv": str(common / FACT_CSV_NAME),
        "expected_detail_pages": DETAIL_COUNT,
        "csv_rows": len(facts),
        "hub_pages": int(hub.is_file()),
        "detail_pages": len(direct_details),
        "audited_detail_pages": len(records),
        "collection": collection,
        "sitemap": sitemap,
        "errors": len(audit.errors),
        "warnings": len(audit.warnings),
        "errors_by_code": dict(sorted(by_code.items())),
        "warnings_by_code": dict(sorted(warning_by_code.items())),
        "error_samples": audit.errors[:error_sample_limit],
        "warning_samples": audit.warnings[:error_sample_limit],
    }
    return report, 1 if audit.errors else 0


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--common",
        type=Path,
        default=DEFAULT_COMMON,
        help=f"공통자료 폴더 (기본: {DEFAULT_COMMON})",
    )
    parser.add_argument(
        "--similarity-limit",
        type=float,
        default=SIMILARITY_LIMIT,
        help="exact/masked 5-shingle Jaccard 배타 상한 (기본 0.75)",
    )
    parser.add_argument("--error-samples", type=int, default=80, help="보고서 오류 예시 최대 수")
    parser.add_argument("--soft", action="store_true", help="오류가 있어도 종료 상태 0 (개발 중에만 사용)")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv if argv is not None else sys.argv[1:])
    if not 0.0 < args.similarity_limit < 1.0:
        print("--similarity-limit은 0과 1 사이여야 합니다", file=sys.stderr)
        return 2
    report, status = run(args.common.resolve(), args.similarity_limit, max(1, args.error_samples))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if args.soft else status


if __name__ == "__main__":
    raise SystemExit(main())
