from __future__ import annotations

import html
import re
from typing import Iterable


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
