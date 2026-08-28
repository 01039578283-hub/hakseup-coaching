from __future__ import annotations

import html
import re
from typing import Iterable


# The source CSV keeps these directions as multiline notes.  Flattening the
# line breaks without restoring sentence boundaries produced strings such as
# ``...건물입니다 주차...`` throughout every page family.  These corrections
# are deliberately exact: they improve punctuation and cautious wording while
# preserving the source address, building and access facts.
LOCATION_NOTE_CORRECTIONS = {
    "경기도 하남시 덕풍동로119 하남프라자501호 스타벅스 맞은편 건물입니다 주차 1시간 가능합니다": (
        "경기도 하남시 덕풍동로 119 하남프라자 501호, 스타벅스 맞은편 건물입니다. "
        "주차 1시간 가능 여부는 방문 전에 확인해 주세요."
    ),
    "북일프라자 1차가 아닌 MUZE건물 2층 북일프라자 2층입니다 북일프라자 2층, 뮤즈카페 건물위 2층입니다": (
        "북일프라자 1차가 아닌 MUZE 건물 2층, 북일프라자 2층입니다. "
        "뮤즈카페가 있는 건물 2층입니다."
    ),
    "광주광역시 광산구 월계로191 첨단메디컬빌딩 4층 404호 1층에 김가네와 쿼드커피 사이에 입구가 있습니다 엘리베이터에서 내리셔서 바로 오른쪽에 센터가 위치합니다": (
        "광주광역시 광산구 월계로 191 첨단메디컬빌딩 4층 404호입니다. "
        "1층 김가네와 쿼드커피 사이에 입구가 있습니다. "
        "엘리베이터에서 내리면 바로 오른쪽에 센터가 있습니다."
    ),
    "경기 김포시 운양동 1296-7 헤리움'리버테라스' 205호입니다 엘레베이터 열리고 바로 왼쪽으로 오시면 됩니다~": (
        "경기 김포시 운양동 1296-7 헤리움리버테라스 205호입니다. "
        "엘리베이터에서 내리면 바로 왼쪽에 있습니다."
    ),
    "경기도 광명시 도덕공원로27 삼우빌딩 2층 (주차장이 없습니다 인근 철산성당이나 인근 아파트에 주차가능합니다)": (
        "경기도 광명시 도덕공원로 27 삼우빌딩 2층입니다. "
        "건물 주차장은 없으며, 인근 주차 가능 장소는 방문 전에 확인해 주세요."
    ),
    "경기 남양주시 늘을3로 65-6 (호평동 617-3) 테마프라자2층 205호 건물 지하 무료주차 가능합니다": (
        "경기 남양주시 늘을3로 65-6(호평동 617-3) 테마프라자 2층 205호입니다. "
        "건물 지하 무료 주차 가능 여부는 방문 전에 확인해 주세요."
    ),
}

# These six high-school source literals occur in twelve locality rows.  They
# are verified lists whose delimiters were lost in the source spreadsheet.
# Keep the rule exact; whitespace is not a safe general school-name separator.
VERIFIED_SCHOOL_SOURCE_CORRECTIONS = {
    "성사고 화수고": ("성사고", "화수고"),
    "진접고 오남고": ("진접고", "오남고"),
    "상동고 상일고 상원고 중흥고 중원고": (
        "상동고", "상일고", "상원고", "중흥고", "중원고"
    ),
    "비전고 한광고 한광여고 평택여고": (
        "비전고", "한광고", "한광여고", "평택여고"
    ),
    "충북고 운호고 충북여고 산남고": (
        "충북고", "운호고", "충북여고", "산남고"
    ),
    "장성고 포고 포여고 유성여고": (
        "장성고", "포고", "포여고", "유성여고"
    ),
}


UNSAFE_PUBLIC_COPY = re.compile(
    r"LOCAL ACADEMY GUIDE|핵심\s*키워드|(?<![가-힣])원고(?![가-힣])|\bSEO\b|"
    r"보조\s*키워드|세부\s*키워드|검색\s*의도|작성자|제작자|필자|"
    r"이\s*글(?:에서는|은)|이\s*페이지(?:에서는|는)|본문\s*이미지|"
    r"메타\s*디스크립션|검색엔진|\bAEO\b|\bGEO\b|"
    r"수업\s*진행방식|실시간\s*수업|온라인\s*수업|입시\s*합격|합격\s*전략|합격률|"
    r"후기\s*기반|실제\s*후기|성적(?:이|을|은|의)?\s*(?:향상|올랐|올리)|"
    r"점수(?:가|를)?\s*올랐|따라가며도|바뀌도|학습예습|영수국|"
    r"풀이을|적용와|적용를|표현와|표현를|기록를|기준를|기준는|"
    r"과정를|습관를|내용를|계획를|학생 학생|상담 상담|확인 확인",
    re.I,
)
UNSUPPORTED_OPERATION_COPY = re.compile(
    r"(?:저희|본원|우리\s*학원|(?:학원|센터|강사진?|교사진?|선생님)(?:은|는|이|가|에서)?)"
    r"[^.!?\n]{0,55}"
    r"(?:운영|진행|지도|관리|제공|보장)(?:하고\s*있습니다|합니다|해\s*드립니다|드립니다)",
)


def normalize_location_note(value: object) -> str:
    """Restore safe sentence boundaries in known multiline source notes."""

    compacted = re.sub(r"\s+", " ", str(value or "").replace("\x08", " ")).strip()
    return LOCATION_NOTE_CORRECTIONS.get(compacted, compacted)


def _plain(fragment: str) -> str:
    text = re.sub(r"<[^>]+>", " ", fragment)
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def source_theme(source_html: str, locality: str, category_label: str, fallback: str) -> str:
    """Read the short editorial angle from the source workbook H1."""

    match = re.search(r"<h1\b[^>]*>(.*?)</h1>", source_html, re.I | re.S)
    if not match:
        return fallback
    heading = _plain(match.group(1))
    if "," in heading:
        theme = heading.split(",", 1)[1].strip()
    else:
        theme = heading.removeprefix(f"{locality} {category_label}").strip(" ,·:-")
    if not 4 <= len(theme) <= 52:
        return fallback
    if "학원검색" in theme or "국어" in theme or UNSAFE_PUBLIC_COPY.search(theme):
        return fallback
    return theme


def source_paragraphs(
    source_html: str,
    *,
    useful_terms: Iterable[str],
    blocked_terms: Iterable[str] = (),
    excluded_school_names: Iterable[str] = (),
    limit: int = 8,
) -> list[str]:
    """Recover useful authored paragraphs without workbook labels or unsafe claims."""

    useful = tuple(useful_terms)
    blocked = tuple(blocked_terms)
    excluded_schools = tuple(excluded_school_names)
    result: list[str] = []
    seen: set[str] = set()
    for fragment in re.findall(r"<p\b[^>]*>(.*?)</p>", source_html, re.I | re.S):
        paragraph = _plain(fragment).strip(" ·")
        if not 55 <= len(paragraph) <= 360:
            continue
        if UNSAFE_PUBLIC_COPY.search(paragraph) or UNSUPPORTED_OPERATION_COPY.search(paragraph):
            continue
        if blocked and any(term in paragraph for term in blocked):
            continue
        if excluded_schools and any(school in paragraph for school in excluded_schools):
            continue
        if useful and not any(term in paragraph for term in useful):
            continue
        paragraph = re.sub(r"^(?:핵심\s*포인트|수업\s*진행방식|선생님\s*특징)\s*", "", paragraph)
        normalized = re.sub(r"\W+", "", paragraph)
        if normalized in seen:
            continue
        seen.add(normalized)
        if paragraph[-1] not in ".!?다요죠":
            paragraph += "."
        result.append(paragraph)
        if len(result) >= limit:
            break
    return result


def distribute_source_paragraphs(
    sections: list[dict[str, object]],
    paragraphs: Iterable[str],
) -> None:
    """Spread source copy across sections instead of creating a bolted-on text block."""

    usable_sections = sections[:5] if len(sections) > 5 else sections
    for index, paragraph in enumerate(paragraphs):
        target = usable_sections[index % len(usable_sections)]
        target_paragraphs = target.setdefault("paragraphs", [])
        if not isinstance(target_paragraphs, list):
            raise TypeError("section paragraphs must be a list")
        target_paragraphs.append(paragraph)
