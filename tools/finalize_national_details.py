# -*- coding: utf-8 -*-
"""전국학원 상세 페이지의 사실성·지역·구조화데이터를 마지막으로 정리한다.

기본 실행은 모든 변경을 메모리에서만 만들고 엄격 검증한다. ``--apply``를
명시한 경우에도 1,484개 전체가 검증을 통과하기 전에는 파일을 쓰지 않는다.
URL, 폴더, canonical, og:url 및 sitemap은 이 스크립트의 수정 대상이 아니다.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import re
import sys
from collections import defaultdict
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.parse import quote, urljoin


ROOT = Path(__file__).resolve().parents[1]
NATIONAL_ROOT = ROOT / "전국학원"
CENTER_DIRECTORY_ROOT = ROOT / "과목별학원" / "와와학습코칭센터"
REFERENCE_CSV = ROOT.parent / "참고자료" / "공통자료" / "센터정보 정리.csv"
BASE_URL = "https://xn--ru4bi8s1tac0p.kr"
ROOT_ORGANIZATION_ID = f"{BASE_URL}/#organization"
EXPECTED_DETAIL_COUNT = 1_484
REVIEW_DATE = "2026-08-16"

JSON_LD_RE = re.compile(
    r'(<script\b[^>]*type=["\']application/ld\+json["\'][^>]*>)(.*?)(</script>)',
    re.I | re.S,
)
HIDDEN_IMAGE_RE = re.compile(
    r'\s*<img\b(?=[^>]*\bclass=["\'][^"\']*\bgenerated-hidden-image\b[^"\']*["\'])[^>]*>\s*',
    re.I | re.S,
)
FEE_ACCORDION_RE = re.compile(
    r'\s*<details\b(?=[^>]*\bclass=["\'][^"\']*\bwawa-fee-accordion\b[^"\']*["\'])[^>]*>.*?</details>\s*',
    re.I | re.S,
)
LEGACY_ARTICLE_RE = re.compile(
    r'\s*<section\b[^>]*class=["\'][^"\']*\barticle-main\b[^"\']*["\'][^>]*>.*?'
    r'(?=<section\b[^>]*class=["\'][^"\']*\bgenerated-support-section\b)',
    re.I | re.S,
)
OUTCOME_RE = re.compile(
    r"(?:성적\s*(?:상승|향상)|점수\s*(?:상승|향상)|"
    r"성적이\s*오르|점수가\s*오르|성적을\s*올리|점수를\s*올리|"
    r"끌어올|점수로\s*연결|실력\s*향상|점수를\s*안정|성과를\s*높)"
)
OLD_CTA_RE = re.compile(r"(?:초등|중등|고등)\s+영수\s+학습\s+상담")
GENERIC_SCHOOL = "지역내 모든 고등학교 가능"
EXTENDED_OUTCOME_RE = re.compile(
    r"(?:끌어올|점수로\s*연결|실력\s*향상|점수를\s*안정|성과를\s*높)"
)
AWKWARD_OUTCOME_RE = re.compile(
    r"(?:학습 과정 (?:개선|점검)|취약 단원 보완).{0,14}"
    r"(?:만듭니다|노립니다|극대화|속도를 높|빠르게|이끕니다)"
)

SAFE_PROCESS_SENTENCES = (
    "현재 교재와 최근 평가 자료에서 취약 단원·오답 원인·실행 여부를 점검합니다.",
    "정답 수보다 개념 이해, 풀이 근거와 반복 오답을 구분해 다음 학습 범위를 정합니다.",
    "시험 범위와 최근 오답을 대조해 먼저 보완할 단원과 복습 순서를 확인합니다.",
    "과목별 진도와 실제 완료 기록을 비교해 무리 없는 주간 학습 계획을 세웁니다.",
    "결과를 미리 단정하지 않고 현재 자료에서 확인되는 학습 과정을 기준으로 상담합니다.",
    "영어·수학의 최근 교재와 오답 기록을 바탕으로 학생별 점검 항목을 정리합니다.",
)

OFFICIAL_REGION_NAMES = {
    "서울": "서울특별시",
    "서울특별시": "서울특별시",
    "부산": "부산광역시",
    "부산광역시": "부산광역시",
    "대구": "대구광역시",
    "대구광역시": "대구광역시",
    "인천": "인천광역시",
    "인천광역시": "인천광역시",
    "광주": "광주광역시",
    "광주광역시": "광주광역시",
    "대전": "대전광역시",
    "대전광역시": "대전광역시",
    "울산": "울산광역시",
    "울산광역시": "울산광역시",
    "세종": "세종특별자치시",
    "세종특별자치시": "세종특별자치시",
    "경기": "경기도",
    "경기도": "경기도",
    "강원": "강원특별자치도",
    "강원도": "강원특별자치도",
    "강원특별자치도": "강원특별자치도",
    "충북": "충청북도",
    "충청북도": "충청북도",
    "충남": "충청남도",
    "충청남도": "충청남도",
    "전북": "전북특별자치도",
    "전라북도": "전북특별자치도",
    "전북특별자치도": "전북특별자치도",
    "전남": "전라남도",
    "전라남도": "전라남도",
    "경북": "경상북도",
    "경상북도": "경상북도",
    "경남": "경상남도",
    "경상남도": "경상남도",
    "제주": "제주특별자치도",
    "제주특별자치도": "제주특별자치도",
}

OUTCOME_REPLACEMENTS = (
    ("실전 점수를 올리", "실전 대응을 점검하"),
    ("내신 점수를 올리", "내신 취약 단원을 보완하"),
    ("성적이 오르는", "학습 과정이 안정되는"),
    ("성적이 오르도록", "학습 과정이 안정되도록"),
    ("성적이 오른", "학습 과정이 안정된"),
    ("점수가 오르는", "취약 단원 대응이 나아지는"),
    ("점수가 오르도록", "취약 단원 대응이 나아지도록"),
    ("점수가 오른", "취약 단원 대응이 나아진"),
    ("성적을 올리", "학습 과정을 개선하"),
    ("점수를 올리", "취약 단원을 보완하"),
    ("성적 상승", "학습 과정 개선"),
    ("성적 향상", "학습 과정 개선"),
    ("점수 상승", "취약 단원 보완"),
    ("점수 향상", "취약 단원 보완"),
    ("단기 성과를 만듭니다", "단기 학습 목표를 점검합니다"),
)


def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", value or ""))).strip()


def first_match(source: str, pattern: str) -> str:
    match = re.search(pattern, source, re.I | re.S)
    return clean_text(match.group(1)) if match else ""


def meta_content(source: str, kind: str, key: str) -> str:
    for match in re.finditer(r"<meta\b[^>]*>", source, re.I | re.S):
        tag = match.group(0)
        attrs = {
            name.lower(): html.unescape(value)
            for name, _, value in re.findall(r'([:\w-]+)\s*=\s*(["\'])(.*?)\2', tag, re.I | re.S)
        }
        if attrs.get(kind.lower(), "").lower() == key.lower():
            return attrs.get("content", "")
    return ""


def replace_meta(source: str, kind: str, key: str, value: str) -> tuple[str, bool]:
    escaped = html.escape(value, quote=True)
    pattern = re.compile(
        rf'(<meta\b(?=[^>]*\b{re.escape(kind)}=["\']{re.escape(key)}["\'])[^>]*\bcontent=["\'])(.*?)(["\'][^>]*>)',
        re.I | re.S,
    )
    updated, count = pattern.subn(lambda match: match.group(1) + escaped + match.group(3), source, count=1)
    return updated, bool(count)


def replace_html_text(source: str, old: str, new: str) -> str:
    """script/style와 태그 속성(URL 포함)을 보존하고 text node만 치환한다."""
    if not old or old == new:
        return source
    protected = re.compile(
        r"<(?:script|style)\b.*?</(?:script|style)>|<[^>]+>",
        re.I | re.S,
    )
    result: list[str] = []
    cursor = 0
    for match in protected.finditer(source):
        result.append(source[cursor : match.start()].replace(old, new))
        result.append(match.group(0))
        cursor = match.end()
    result.append(source[cursor:].replace(old, new))
    return "".join(result)


def replace_text_attributes(source: str, old: str, new: str) -> str:
    """사람이 읽는 alt/title/aria-label만 바꾸고 href/src 등은 건드리지 않는다."""
    if not old or old == new:
        return source
    pattern = re.compile(r'((?:alt|title|aria-label)=["\'])(.*?)(["\'])', re.I | re.S)
    return pattern.sub(
        lambda match: match.group(1) + match.group(2).replace(old, new) + match.group(3),
        source,
    )


def node_types(node: dict[str, Any]) -> set[str]:
    value = node.get("@type")
    if isinstance(value, list):
        return {str(item) for item in value}
    return {str(value)} if value else set()


def graph_nodes(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, dict) and isinstance(data.get("@graph"), list):
        return [node for node in data["@graph"] if isinstance(node, dict)]
    if isinstance(data, dict):
        return [data]
    if isinstance(data, list):
        return [node for node in data if isinstance(node, dict)]
    return []


def replace_exact(value: Any, old: str, new: str) -> Any:
    if isinstance(value, str):
        return new if value == old else value
    if isinstance(value, list):
        return [replace_exact(item, old, new) for item in value]
    if isinstance(value, dict):
        return {key: replace_exact(item, old, new) for key, item in value.items()}
    return value


def absolute_path_url(*parts: str) -> str:
    suffix = "/" + "/".join(part.strip("/") for part in parts if part) + "/"
    return BASE_URL + quote(suffix, safe="/")


def postal_geography(address: str) -> tuple[str, str]:
    tokens = address.split()
    if not tokens:
        return "", ""
    region = OFFICIAL_REGION_NAMES.get(tokens[0], tokens[0])
    if region == "세종특별자치시":
        return region, "새롬동"
    locality = tokens[1] if len(tokens) > 1 else ""
    return region, locality


def physical_center_key(center_name: str, registration_number: str, address: str) -> str:
    registration_key = re.sub(r"\s+", "", registration_number)
    fallback_key = "|".join(
        re.sub(r"\s+", " ", part).strip() for part in (center_name, address) if part.strip()
    )
    return registration_key or fallback_key


def normalize_neighborhood(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").replace("-", " ")).strip()


@lru_cache(maxsize=1)
def authoritative_center_records() -> dict[tuple[str, str, str], dict[str, str]]:
    """URL의 지역 경로를 권위 센터 CSV 한 행과 정확히 연결한다."""
    if not REFERENCE_CSV.is_file():
        raise FileNotFoundError(f"센터 기준 CSV 없음: {REFERENCE_CSV}")
    with REFERENCE_CSV.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    result: dict[tuple[str, str, str], dict[str, str]] = {}
    for row in rows:
        key = (
            row.get("지역", "").strip(),
            row.get("시or구", "").strip(),
            normalize_neighborhood(row.get("근처 수업가능 동네", "")),
        )
        if key in result:
            raise ValueError(f"센터 기준 CSV 지역 중복: {key}")
        result[key] = row
    if len(result) != 371:
        raise ValueError(f"센터 기준 CSV 행 수 {len(result):,} / 예상 371")
    return result


@lru_cache(maxsize=1)
def center_profile_urls() -> dict[str, str]:
    """등록번호가 정확히 일치하는 센터 프로필의 canonical을 반환한다."""
    candidates: dict[str, list[str]] = defaultdict(list)
    for page in sorted(CENTER_DIRECTORY_ROOT.glob("*/index.html")):
        source = page.read_text(encoding="utf-8", errors="strict")
        registration = first_match(
            source,
            r"<dt>\s*교육지원청 등록번호\s*</dt>\s*<dd>(.*?)</dd>",
        )
        canonical = first_match(
            source,
            r'<link\b[^>]*rel=["\']canonical["\'][^>]*href=["\']([^"\']+)',
        )
        if registration and canonical:
            candidates[re.sub(r"\s+", "", registration)].append(canonical.rstrip("/") + "/")
    return {
        key: urls[0]
        for key, urls in candidates.items()
        if len(set(urls)) == 1
    }


@lru_cache(maxsize=1)
def preferred_detail_urls() -> dict[str, str]:
    """프로필이 없는 센터는 같은 physical key의 정렬상 첫 locality URL을 쓴다."""
    candidates: dict[str, list[str]] = defaultdict(list)
    for page in sorted(NATIONAL_ROOT.rglob("index.html")):
        if len(page.parent.relative_to(NATIONAL_ROOT).parts) != 3:
            continue
        source = page.read_text(encoding="utf-8", errors="strict")
        center_name = first_match(
            source,
            r'<section\b[^>]*class=["\'][^"\']*\bwawa-center-snippet\b[^"\']*["\'][^>]*aria-label=["\'](.*?)\s+센터 안내["\']',
        )
        address = first_match(
            source,
            r'<span\b[^>]*class=["\'][^"\']*\bwawa-label\b[^"\']*["\'][^>]*>\s*주소\s*</span>'
            r'\s*<p\b[^>]*class=["\'][^"\']*\bwawa-text\b[^"\']*["\'][^>]*>(.*?)</p>',
        )
        registration = first_match(
            source,
            r'<p\b[^>]*class=["\'][^"\']*\bwawa-register-line\b[^"\']*["\'][^>]*>'
            r'\s*<strong>\s*(?:등록번호|교육청 등록번호)\s*</strong>\s*:\s*(.*?)</p>',
        )
        canonical = first_match(
            source,
            r'<link\b[^>]*rel=["\']canonical["\'][^>]*href=["\']([^"\']+)',
        )
        key = physical_center_key(center_name, registration, address)
        if key and canonical:
            candidates[key].append(canonical.rstrip("/") + "/")
    return {key: sorted(set(urls))[0] for key, urls in candidates.items()}


def center_directory_identity(
    center_name: str, registration_number: str, address: str
) -> tuple[str, str]:
    """프로필 또는 대표 상세 URL에 연결되는 188개 stable 지점 엔티티 ID."""
    registration_key = re.sub(r"\s+", "", registration_number)
    profile_url = center_profile_urls().get(registration_key)
    if profile_url:
        return profile_url + "#organization", profile_url
    key = physical_center_key(center_name, registration_number, address)
    preferred_url = preferred_detail_urls().get(key)
    if not preferred_url:
        raise KeyError(f"물리센터 대표 URL 없음: {key}")
    return preferred_url + "#organization", preferred_url


def school_groups(source: str) -> dict[str, tuple[str, ...]]:
    """학교 카드별 이름을 분리한다. blanket 문구는 학교 엔티티가 아니다."""
    result: dict[str, tuple[str, ...]] = {}
    for key in ("elementary", "middle", "high"):
        match = re.search(
            rf'<article\b[^>]*class=["\'][^"\']*\bwawa-school-card\b[^"\']*\bis-{key}\b[^"\']*["\'][^>]*>'
            r'(.*?)</article>',
            source,
            re.I | re.S,
        )
        if not match:
            result[key] = ()
            continue
        result[key] = tuple(
            name
            for name in (
                clean_text(value)
                for value in re.findall(
                    r'<span\b[^>]*class=["\'][^"\']*\bwawa-pill\b[^"\']*["\'][^>]*>(.*?)</span>',
                    match.group(1),
                    re.I | re.S,
                )
            )
            if name and name != GENERIC_SCHOOL
        )
    return result


def relevant_school_names(source: str, title: str, is_child: bool) -> tuple[str, ...]:
    groups = school_groups(source)
    if is_child:
        key = "elementary" if "초등" in title else "middle" if "중등" in title else "high"
        return groups.get(key, ())
    result: list[str] = []
    for key in ("elementary", "middle", "high"):
        for name in groups.get(key, ()):
            if name not in result:
                result.append(name)
    return tuple(result)


def available_grades(source: str) -> dict[str, tuple[str, ...]]:
    result: dict[str, tuple[str, ...]] = {}
    for block in re.findall(
        r'<div\b[^>]*class=["\'][^"\']*\bwawa-grade-row\b[^"\']*["\'][^>]*>(.*?)</div>\s*</div>',
        source,
        re.I | re.S,
    ):
        subject = first_match(block, r'<div\b[^>]*class=["\'][^"\']*\bwawa-grade-subject\b[^"\']*["\'][^>]*>(.*?)</div>')
        if not subject:
            continue
        values = tuple(
            clean_text(value)
            for value in re.findall(
                r'<span\b[^>]*class=["\'][^"\']*\bwawa-pill\b[^"\']*["\'][^>]*>(.*?)</span>',
                block,
                re.I | re.S,
            )
            if clean_text(value)
        )
        result[subject] = values
    return result


@dataclass(frozen=True)
class Facts:
    path: Path
    relative: str
    region: str
    district: str
    neighborhood: str
    display_neighborhood: str
    child: str
    title: str
    canonical: str
    og_url: str
    source_address: str
    address: str
    center_name: str
    registration_name: str
    registration_number: str
    tuition_url: str
    map_url: str
    display_region: str
    display_district: str
    address_region: str
    address_locality: str
    organization_id: str
    organization_url: str
    has_school_names: bool
    school_names: tuple[str, ...]
    available_grades: dict[str, tuple[str, ...]]

    @property
    def is_child(self) -> bool:
        return bool(self.child)

    @property
    def physical_key(self) -> str:
        return physical_center_key(
            self.center_name, self.registration_number, self.address
        )


@dataclass
class Plan:
    facts: Facts
    old_source: str
    new_source: str
    description: str
    issues: list[str]


def facts_for(path: Path) -> Facts:
    source = path.read_text(encoding="utf-8", errors="strict")
    parts = path.parent.relative_to(NATIONAL_ROOT).parts
    if len(parts) not in {3, 4}:
        raise ValueError(f"상세 깊이가 아닙니다: {path}")
    region, district, neighborhood = parts[:3]
    child = parts[3] if len(parts) == 4 else ""
    title = first_match(source, r"<h1\b[^>]*>(.*?)</h1>")
    canonical = first_match(source, r'<link\b[^>]*rel=["\']canonical["\'][^>]*href=["\']([^"\']+)')
    og_url = meta_content(source, "property", "og:url")
    source_address = first_match(
        source,
        r'<span\b[^>]*class=["\'][^"\']*\bwawa-label\b[^"\']*["\'][^>]*>\s*주소\s*</span>'
        r'\s*<p\b[^>]*class=["\'][^"\']*\bwawa-text\b[^"\']*["\'][^>]*>(.*?)</p>',
    )
    center_name = first_match(
        source,
        r'<section\b[^>]*class=["\'][^"\']*\bwawa-center-snippet\b[^"\']*["\'][^>]*aria-label=["\'](.*?)\s+센터 안내["\']',
    )
    registration_name = first_match(
        source,
        r'<p\b[^>]*class=["\'][^"\']*\bwawa-register-line\b[^"\']*["\'][^>]*>'
        r'\s*<strong>\s*(?:교육지원청|등록 학원명)\s*</strong>\s*:\s*(.*?)</p>',
    )
    registration_number = first_match(
        source,
        r'<p\b[^>]*class=["\'][^"\']*\bwawa-register-line\b[^"\']*["\'][^>]*>'
        r'\s*<strong>\s*(?:등록번호|교육청 등록번호)\s*</strong>\s*:\s*(.*?)</p>',
    )
    tuition_url = first_match(
        source,
        r'<a\b[^>]*class=["\'][^"\']*\bwawa-tuition-link\b[^"\']*["\'][^>]*href=["\']([^"\']+)',
    )
    map_src = first_match(source, r'<img\b[^>]*src=["\']([^"\']*assets/maps/[^"\']+)["\'][^>]*>')
    map_url = urljoin(canonical, map_src) if canonical and map_src else ""
    center_key = (region, district, normalize_neighborhood(neighborhood))
    center_record = authoritative_center_records().get(center_key)
    if center_record is None:
        raise KeyError(f"센터 기준 CSV 매칭 실패: {path.relative_to(ROOT)} -> {center_key}")
    address = center_record.get("센터 주소", "").strip()
    if not address:
        raise ValueError(f"센터 기준 CSV 주소 공란: {path.relative_to(ROOT)}")
    center_name = center_record.get("센터명", "").strip() or center_name
    registration_name = center_record.get("교육지원청명칭", "").strip() or registration_name
    registration_number = (
        center_record.get("교육지원청 등록번호", "").strip() or registration_number
    )
    tuition_url = center_record.get("센터 교습비", "").strip()
    is_sejong = address.startswith("세종특별자치시")
    # URL /충청/은 충청 지역과 공유하므로 breadcrumb 링크 의미는 충청·세종,
    # 그 아래 기존 /새롬중앙로/ 링크는 행정구역인 세종특별자치시로 표시한다.
    display_region = "충청·세종" if is_sejong else region
    display_district = "세종특별자치시" if is_sejong else district
    # 센터의 물리 주소 locality는 서비스 대상 동네(다정동 포함)와 구분한다.
    address_region, address_locality = postal_geography(address)
    organization_id, organization_url = center_directory_identity(
        center_name, registration_number, address
    )
    relevant_schools = relevant_school_names(source, title, bool(child))
    return Facts(
        path=path,
        relative=path.relative_to(ROOT).as_posix(),
        region=region,
        district=district,
        neighborhood=neighborhood,
        display_neighborhood=neighborhood.replace("-", " "),
        child=child,
        title=title,
        canonical=canonical,
        og_url=og_url,
        source_address=source_address,
        address=address,
        center_name=center_name,
        registration_name=registration_name,
        registration_number=registration_number,
        tuition_url=tuition_url,
        map_url=map_url,
        display_region=display_region,
        display_district=display_district,
        address_region=address_region,
        address_locality=address_locality,
        organization_id=organization_id,
        organization_url=organization_url,
        has_school_names=bool(relevant_schools),
        school_names=relevant_schools,
        available_grades=available_grades(source),
    )


def description_for(facts: Facts) -> str:
    value = (
        f"{facts.title} | {facts.display_region} {facts.display_district} {facts.display_neighborhood} "
        "학년·과목, 참고 학교, 센터 위치와 상담 기준 안내."
    )
    if len(value) > 80:
        value = (
            f"{facts.title} | {facts.display_region} {facts.display_district} "
            "학년·과목, 센터 위치와 상담 기준 안내."
        )
    if len(value) > 80:
        raise ValueError(f"80자 메타 설명을 만들 수 없습니다({len(value)}자): {facts.relative}")
    return value


def leaf_grade(facts: Facts) -> tuple[str, str]:
    for label, prefix in (("초등", "초"), ("중등", "중"), ("고등", "고")):
        if label in facts.title:
            return label, prefix
    return "", ""


def leaf_availability_summary(facts: Facts) -> str:
    grade, prefix = leaf_grade(facts)
    if not grade:
        return ""
    parts: list[str] = []
    for subject in ("영어", "수학"):
        values = [value for value in facts.available_grades.get(subject, ()) if value.startswith(prefix)]
        parts.append(f"{subject} {', '.join(values)}" if values else f"{subject} 상담 시 확인")
    return " · ".join(parts)


def leaf_availability_answer(facts: Facts) -> str:
    grade, _ = leaf_grade(facts)
    return (
        f"{facts.title} 센터 제공 자료의 {grade} 가능 범위는 "
        f"{leaf_availability_summary(facts)}입니다. 현재 개설 여부와 시간표는 상담 시 최종 확인해 주세요."
    )


def school_information_answer(facts: Facts) -> str:
    if facts.school_names:
        return (
            f"센터 제공 자료의 {leaf_grade(facts)[0] or '학년별'} 참고 학교 목록은 "
            f"{', '.join(facts.school_names)}입니다. 실제 학교별 수업·시험 대비 가능 여부는 "
            "상담 시 확인해 주세요."
        )
    return (
        "센터 제공 자료에서 학교 정보가 확인되지 않았습니다. "
        "실제 학교별 수업·시험 대비 가능 여부는 상담 시 확인해 주세요."
    )


def rewrite_leaf_availability(source: str, facts: Facts) -> str:
    grade, _ = leaf_grade(facts)
    if not grade:
        return source
    availability_answer = html.escape(leaf_availability_answer(facts))
    school_answer = html.escape(school_information_answer(facts))

    # FAQ 전체에서 cue를 찾으면 다른 </details>까지 횡단할 수 있다. 먼저 각
    # item을 분리한 뒤 그 item 내부의 summary와 단일 answer만 교체한다.
    details_pattern = re.compile(
        r'<details\b[^>]*class=["\'][^"\']*\bparent-faq-item\b[^"\']*["\'][^>]*>'
        r'.*?</details>',
        re.I | re.S,
    )

    def rewrite_faq_item(match: re.Match[str]) -> str:
        block = match.group(0)
        summary = first_match(block, r"<summary\b[^>]*>(.*?)</summary>")
        replacement = ""
        if "학년" in summary and ("수강" in summary or "가능" in summary):
            replacement = availability_answer
        elif any(
            cue in summary
            for cue in ("학교별", "학교 시험", "학교 진도", "학교 정보")
        ):
            replacement = school_answer
        if not replacement:
            return block
        return re.sub(
            r'(<p\b[^>]*class=["\'][^"\']*\bparent-faq-answer\b[^"\']*["\'][^>]*>)'
            r'.*?(</p>)',
            lambda answer_match: answer_match.group(1)
            + replacement
            + answer_match.group(2),
            block,
            count=1,
            flags=re.I | re.S,
        )

    source = details_pattern.sub(rewrite_faq_item, source)
    checklist = (
        f"{facts.title} 센터 제공 자료의 {grade} 가능 범위는 "
        f"{leaf_availability_summary(facts)}입니다. 현재 개설 여부는 상담 시 확인합니다."
    )
    source = re.sub(
        r'(<li>\s*<b>가능 학년</b>\s*<span>).*?(</span>\s*</li>)',
        lambda match: match.group(1) + html.escape(checklist) + match.group(2),
        source,
        count=1,
        flags=re.I | re.S,
    )
    source = re.sub(
        r'(<article\b[^>]*class=["\'][^"\']*\bparent-review-card\b[^"\']*["\'][^>]*>\s*'
        r'<strong>학교·진도 확인</strong>\s*<p>).*?(</p>)',
        lambda match: match.group(1) + school_answer + match.group(2),
        source,
        count=1,
        flags=re.I | re.S,
    )
    guidance = (
        f"{facts.title} 센터 제공 자료의 {grade} 가능 범위는 "
        f"{leaf_availability_summary(facts)}입니다. 현재 개설 여부와 시간은 상담 시 최종 확인합니다."
    )
    source = re.sub(
        r'(<article\b[^>]*class=["\'][^"\']*\bparent-review-card\b[^"\']*["\'][^>]*>\s*'
        r'<strong>과목별 수강 범위</strong>\s*<p>).*?(</p>)',
        lambda match: match.group(1) + html.escape(guidance) + match.group(2),
        source,
        count=1,
        flags=re.I | re.S,
    )
    school_sentence = (
        f"{grade} 참고 학교 목록은 {'·'.join(facts.school_names)}입니다. "
        if facts.school_names
        else "센터 제공 자료에서 학교 정보가 확인되지 않았습니다. "
    )
    combined = (
        school_sentence
        + f"센터 제공 자료의 {grade} 가능 범위는 {leaf_availability_summary(facts)}입니다. "
        "학교별 수업과 현재 개설 여부는 상담 시 확인해 주세요."
    )
    source = re.sub(
        r'(<article>\s*<b>학교·가능 학년</b>\s*<p>).*?(</p>\s*</article>)',
        lambda match: match.group(1) + html.escape(combined) + match.group(2),
        source,
        count=1,
        flags=re.I | re.S,
    )
    return source


def normalize_claims(value: str) -> str:
    value = re.sub(r"성적이\s*오르는", "학습 과정이 안정되는", value)
    value = re.sub(r"성적이\s*오르도록", "학습 과정이 안정되도록", value)
    value = re.sub(r"성적이\s*오르게", "학습 과정이 안정되게", value)
    value = re.sub(r"점수가\s*오르는", "취약 단원 대응이 나아지는", value)
    value = re.sub(r"점수가\s*오르도록", "취약 단원 대응이 나아지도록", value)
    value = re.sub(r"점수가\s*오르게", "취약 단원 대응이 나아지게", value)
    for old, new in OUTCOME_REPLACEMENTS:
        value = value.replace(old, new)
    value = value.replace("성적상승", "학습 과정 개선")
    value = value.replace("점수상승", "취약 단원 보완")
    value = value.replace("성적향상", "학습 과정 개선")
    value = value.replace("점수향상", "취약 단원 보완")
    # 결과 보장처럼 읽히는 추가 문형은 관찰·점검 가능한 과정 표현으로 바꾼다.
    value = value.replace("끌어올", "점검하")
    value = value.replace("점수로 연결되게", "풀이 과정이 남게")
    value = value.replace("점수로 연결되도록", "풀이 과정으로 확인되도록")
    value = value.replace("점수로 연결되는", "풀이 과정이 확인되는")
    value = value.replace("점수로 연결합니다", "풀이 과정을 확인합니다")
    value = value.replace("점수로 연결할지", "풀이 과정으로 확인할지")
    value = value.replace("점수로 연결", "풀이 과정 확인")
    value = value.replace("실력 향상", "학습 과정 점검")
    value = re.sub(
        r"(?:실전\s+|최종\s+)?점수를\s+안정화합니다",
        "오답과 풀이 과정을 점검합니다",
        value,
    )
    value = re.sub(
        r"점수를\s+안정적으로\s+(?:만듭니다|올립니다|점검합니다)",
        "오답과 풀이 과정을 점검합니다",
        value,
    )
    value = re.sub(
        r"(?:체감\s+|당일\s+|시험\s+당일\s+)?성과를\s+높입니다",
        "시험 전 확인 항목을 점검합니다",
        value,
    )
    value = value.replace("성과를 높", "학습 과정을 점검하")
    value = re.sub(r"(?:내신\s+)?학습 과정 개선", "학습 과정 점검", value)
    value = re.sub(
        r"(?:학습 과정 점검|취약 단원 보완)(?:을|에|의|으로)?\s*"
        r"(?:만듭니다|노립니다|극대화합니다|이끕니다)",
        "현재 자료에서 취약 단원·오답·실행 여부를 점검합니다",
        value,
    )
    return value


def rewrite_visible_outcome_elements(source: str, facts: Facts) -> str:
    """성과 단정이 든 authored element를 검증 가능한 과정 문장으로 바꾼다."""

    def replace_element(match: re.Match[str]) -> str:
        body = match.group("body")
        if not OUTCOME_RE.search(clean_text(body)):
            return match.group(0)
        tag = match.group("tag").lower()
        if tag in {"h2", "h3", "strong"}:
            grade, _ = leaf_grade(facts)
            replacement = f"{grade + ' ' if grade else ''}학습 과정과 오답 점검"
        else:
            digest = hashlib.sha256(
                f"{facts.relative}|{clean_text(body)}".encode("utf-8")
            ).hexdigest()
            replacement = SAFE_PROCESS_SENTENCES[int(digest[:12], 16) % len(SAFE_PROCESS_SENTENCES)]
        return match.group("open") + html.escape(replacement) + match.group("close")

    for tag in ("p", "li", "h2", "h3", "strong"):
        pattern = re.compile(
            rf'(?P<open><(?P<tag>{tag})\b[^>]*>)(?P<body>.*?)(?P<close></{tag}>)',
            re.I | re.S,
        )
        source = pattern.sub(replace_element, source)
    return source


def normalize_text(value: str, facts: Facts) -> str:
    value = normalize_claims(value)
    value = value.replace("기록와", "기록과")
    value = value.replace("평소 공부 기록를", "평소 공부 기록을")
    value = re.sub(
        r"(학년별|초등|중등|고등) 학교 참고 정보에(?:는)? "
        r"(.+?)(?: 등이|이|가) 포함되어 있습니다\.",
        r"\1 참고 학교 목록은 \2입니다.",
        value,
    )
    value = re.sub(r"(초등|중등|고등)\s+영수\s+학습\s+상담", r"\1 영어·수학 학습 상담", value)
    value = value.replace(
        GENERIC_SCHOOL,
        "센터 제공 자료에서 고등학교 정보가 확인되지 않았습니다",
    )
    value = value.replace(
        "교습비 안내 준비중",
        "센터 제공 교습비 자료가 확인되지 않아 실제 금액·횟수는 상담 시 확인해 주세요.",
    )
    if facts.address.startswith("세종특별자치시"):
        value = value.replace(
            f"충청 새롬중앙로 {facts.neighborhood}",
            f"충청·세종 세종특별자치시 {facts.neighborhood}",
        )
        value = value.replace("충청 새롬중앙로의", "충청·세종 세종특별자치시의")
        value = value.replace("충청 새롬중앙로 인근", "세종특별자치시 인근")
    if not facts.has_school_names:
        value = re.sub(
            rf"{re.escape(facts.title)} 상담에서는 재학 학교와 최근 학습 자료를 기준으로 "
            r"학교별 진도와 시험 범위를 확인합니다\.",
            "센터 제공 자료에서 학교 정보가 확인되지 않았습니다. 실제 학교별 수업·시험 대비 가능 여부는 상담 시 확인해 주세요.",
            value,
        )
    if not facts.tuition_url:
        value = re.sub(
            rf"{re.escape(facts.title)} 페이지의 교습비 안내 버튼에서 .*?의 제공 자료를 확인할 수 있습니다\. "
            r"실제 수강료와 횟수는 .*?상담 시 최종 확인이 필요합니다\.",
            "센터 제공 교습비 자료가 확인되지 않아 실제 금액·횟수와 개설 과목은 상담 시 확인해 주세요.",
            value,
        )
    return value


def breadcrumb_entries(facts: Facts) -> list[dict[str, str]]:
    entries = [
        {"name": "홈", "item": BASE_URL + "/"},
        {"name": "전국학원", "item": absolute_path_url("전국학원")},
        {
            "name": facts.display_region,
            "item": absolute_path_url("전국학원", facts.region),
        },
        {
            "name": facts.display_district,
            "item": absolute_path_url("전국학원", facts.region, facts.district),
        },
    ]
    if facts.is_child:
        entries.append(
            {
                "name": f"{facts.display_neighborhood} 학원",
                "item": absolute_path_url(
                    "전국학원", facts.region, facts.district, facts.neighborhood
                ),
            }
        )
    entries.append({"name": facts.title, "item": facts.canonical})
    return entries


def render_visible_breadcrumb(facts: Facts) -> str:
    entries = breadcrumb_entries(facts)
    linked = [
        f'<a href="{html.escape(entry["item"], quote=True)}">{html.escape(entry["name"])}</a>'
        for entry in entries[:-1]
    ]
    linked.append(html.escape(entries[-1]["name"]))
    return '<div class="breadcrumb">' + " › ".join(linked) + "</div>"


def normalize_json_strings(value: Any, facts: Facts) -> Any:
    if isinstance(value, str):
        # URL/@id/item은 기존 taxonomy path를 유지한다. 아래 치환은 오직
        # name·description·keywords 같은 사람이 읽는 semantic 문자열용이다.
        if value.startswith(("https://", "http://", "/", "../", "./")):
            return value
        if facts.address.startswith("세종특별자치시") and value == "충청":
            return "충청·세종"
        if facts.address.startswith("세종특별자치시") and value == "새롬중앙로":
            return "세종특별자치시"
        value = normalize_text(value, facts)
        if facts.address.startswith("세종특별자치시"):
            value = value.replace("새롬중앙로", "세종특별자치시")
        if facts.neighborhood != facts.display_neighborhood:
            value = value.replace(facts.neighborhood, facts.display_neighborhood)
        grade, _ = leaf_grade(facts)
        if grade and (
            f"에 등록된 {facts.title} 가능 학년은" in value
            or "페이지에 제공된 센터 정보 기준으로 영어·수학 수강 가능 학년은" in value
            or "과목별 안내 자료에는" in value
        ):
            return leaf_availability_answer(facts)
        if grade and value.startswith("가능 학년 "):
            return (
                f"가능 학년 {facts.title} 센터 제공 자료의 {grade} 가능 범위는 "
                f"{leaf_availability_summary(facts)}입니다. 현재 개설 여부는 상담 시 확인합니다."
            )
        if grade and (
            "페이지에 제공된 참고 학교는" in value
            or "센터 제공 자료에서 고등학교 정보가 확인되지 않았습니다" in value
        ):
            return school_information_answer(facts)
        return value
    if isinstance(value, list):
        return [normalize_json_strings(item, facts) for item in value]
    if isinstance(value, dict):
        return {key: normalize_json_strings(item, facts) for key, item in value.items()}
    return value


def prune_generic_school(value: Any) -> Any:
    """학교명이 아닌 blanket 문구가 mentions/ItemList 엔티티가 되는 것을 막는다."""
    if isinstance(value, list):
        result = []
        for item in value:
            if isinstance(item, str) and (
                item == GENERIC_SCHOOL or "고등학교 정보가 확인되지 않았습니다" in item
            ):
                continue
            if isinstance(item, dict) and (
                item.get("name") == GENERIC_SCHOOL
                or "고등학교 정보가 확인되지 않았습니다" in str(item.get("name", ""))
            ):
                continue
            result.append(prune_generic_school(item))
        return result
    if isinstance(value, dict):
        return {key: prune_generic_school(item) for key, item in value.items()}
    return value


def visible_h2_names(source: str) -> list[str]:
    without_scripts = re.sub(r"<script\b.*?</script>", "", source, flags=re.I | re.S)
    result: list[str] = []
    for raw in re.findall(r"<h2\b[^>]*>(.*?)</h2>", without_scripts, re.I | re.S):
        name = clean_text(raw)
        if name and name not in result:
            result.append(name)
    return result


def visible_faq_pairs(source: str) -> list[tuple[str, str]]:
    section = re.search(
        r'<section\b[^>]*class=["\'][^"\']*\bparent-faq-section\b[^"\']*["\'][^>]*>'
        r'(.*?)</section>',
        source,
        re.I | re.S,
    )
    if not section:
        return []
    result: list[tuple[str, str]] = []
    for block in re.findall(
        r'<details\b[^>]*class=["\'][^"\']*\bparent-faq-item\b[^"\']*["\'][^>]*>'
        r'(.*?)</details>',
        section.group(1),
        re.I | re.S,
    ):
        summary_match = re.search(
            r"<summary\b[^>]*>(.*?)</summary>", block, re.I | re.S
        )
        summary_html = summary_match.group(1) if summary_match else ""
        # The leading Q badge is presentational, not part of the question text.
        summary_html = re.sub(
            r'<span\b[^>]*class=["\'][^"\']*\bparent-faq-q\b[^"\']*["\'][^>]*>'
            r".*?</span>",
            "",
            summary_html,
            count=1,
            flags=re.I | re.S,
        )
        question = clean_text(summary_html)
        answer = first_match(
            block,
            r'<p\b[^>]*class=["\'][^"\']*\bparent-faq-answer\b[^"\']*["\'][^>]*>'
            r'(.*?)</p>',
        )
        if question and answer:
            result.append((question, answer))
    return result


def visible_checklist_items(source: str) -> list[str]:
    """화면 상담 체크리스트를 JSON-LD ItemList의 단일 기준으로 사용한다."""
    match = re.search(
        r'<ol\b[^>]*class=["\'][^"\']*\bseo-checklist\b[^"\']*["\'][^>]*>'
        r'(.*?)</ol>',
        source,
        re.I | re.S,
    )
    if not match:
        return []
    return [
        clean_text(item)
        for item in re.findall(r"<li\b[^>]*>(.*?)</li>", match.group(1), re.I | re.S)
        if clean_text(item)
    ]


def semantic_json_strings(value: Any, parent_key: str = "") -> list[str]:
    """URL·실주소를 제외한 사람이 읽는 JSON-LD 문자열만 모은다."""
    if parent_key in {"@id", "url", "item", "streetAddress", "image"}:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        result: list[str] = []
        for item in value:
            result.extend(semantic_json_strings(item, parent_key))
        return result
    if isinstance(value, dict):
        result = []
        for key, item in value.items():
            result.extend(semantic_json_strings(item, key))
        return result
    return []


def update_jsonld(source: str, facts: Facts, description: str) -> tuple[str, list[str]]:
    errors: list[str] = []
    visible_sections = visible_h2_names(source)
    visible_faqs = visible_faq_pairs(source)
    visible_checklist = visible_checklist_items(source)

    def replace_script(match: re.Match[str]) -> str:
        try:
            data = json.loads(match.group(2))
        except json.JSONDecodeError as exc:
            errors.append(f"JSON-LD 파싱 오류: {exc}")
            return match.group(0)

        nodes = graph_nodes(data)
        old_ids = [
            node.get("@id")
            for node in nodes
            if {"EducationalOrganization", "LocalBusiness"} & node_types(node)
            and isinstance(node.get("@id"), str)
        ]
        for old_id in old_ids:
            data = replace_exact(data, old_id, facts.organization_id)
        data = prune_generic_school(normalize_json_strings(data, facts))
        nodes = graph_nodes(data)

        for node in nodes:
            types = node_types(node)
            if {"EducationalOrganization", "LocalBusiness"} & types:
                node["@id"] = facts.organization_id
                if facts.center_name:
                    node["name"] = facts.center_name
                if facts.organization_url:
                    node["url"] = facts.organization_url
                else:
                    node.pop("url", None)
                node.pop("hasOfferCatalog", None)
                node.pop("aggregateRating", None)
                node.pop("review", None)
                # CSV에는 센터별 전화·운영시간·연락 창구 근거가 없다. 화면의
                # 사이트 상담 CTA와 지점 LocalBusiness 사실을 분리한다.
                node.pop("telephone", None)
                node.pop("openingHours", None)
                node.pop("contactPoint", None)
                node["address"] = {
                    "@type": "PostalAddress",
                    "streetAddress": facts.address,
                    "addressRegion": facts.address_region,
                    "addressLocality": facts.address_locality,
                    "addressCountry": "KR",
                }
                if facts.map_url:
                    node["image"] = facts.map_url
                if facts.registration_number:
                    node["identifier"] = {
                        "@type": "PropertyValue",
                        "propertyID": "교육지원청 등록번호",
                        "value": facts.registration_number,
                    }
            if "BreadcrumbList" in types:
                node["itemListElement"] = [
                    {
                        "@type": "ListItem",
                        "position": position,
                        "name": entry["name"],
                        "item": entry["item"],
                    }
                    for position, entry in enumerate(breadcrumb_entries(facts), start=1)
                ]
            if "WebPage" in types:
                node["description"] = description
                node["author"] = {"@id": ROOT_ORGANIZATION_ID}
                node["publisher"] = {"@id": ROOT_ORGANIZATION_ID}
                node["dateModified"] = REVIEW_DATE
                if facts.map_url:
                    node["primaryImageOfPage"] = {
                        "@type": "ImageObject",
                        "url": facts.map_url,
                    }
                node["hasPart"] = [
                    {"@type": "WebPageElement", "name": name}
                    for name in visible_sections
                ]
            if "Article" in types:
                node["description"] = description
                node["author"] = {"@id": ROOT_ORGANIZATION_ID}
                node["publisher"] = {"@id": ROOT_ORGANIZATION_ID}
                node["dateModified"] = REVIEW_DATE
                if facts.map_url:
                    node["image"] = facts.map_url
                node["articleSection"] = visible_sections
                node["hasPart"] = [
                    {"@type": "WebPageElement", "name": name}
                    for name in visible_sections
                ]
            if "Service" in types:
                node["provider"] = {"@id": facts.organization_id}
                node.pop("hasOfferCatalog", None)
                node["areaServed"] = {
                    "@type": "Place",
                    "name": facts.display_neighborhood,
                }
            if "FAQPage" in types:
                node["mainEntity"] = [
                    {
                        "@type": "Question",
                        "name": question,
                        "acceptedAnswer": {
                            "@type": "Answer",
                            "text": answer,
                        },
                    }
                    for question, answer in visible_faqs
                ]
            if (
                "ItemList" in types
                and str(node.get("@id", "")).endswith("#checklist")
                and visible_checklist
            ):
                node["itemListElement"] = [
                    {
                        "@type": "ListItem",
                        "position": position,
                        "name": name,
                    }
                    for position, name in enumerate(visible_checklist, start=1)
                ]

        serialized = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
        return match.group(1) + serialized + match.group(3)

    updated, count = JSON_LD_RE.subn(replace_script, source)
    if count == 0:
        errors.append("JSON-LD 블록 없음")
    return updated, errors


def source_note() -> str:
    return (
        '<p class="national-source-note"><strong>정보 기준</strong> '
        f"사이트가 보유한 센터 제공 자료를 {REVIEW_DATE} 재검토했습니다. "
        "현재 개설 과목·반 편성·운영 여부는 상담 시 최종 확인해 주세요. "
        "편집: 학습코칭 연구소.</p>"
    )


def transform(path: Path) -> Plan:
    old_source = path.read_text(encoding="utf-8", errors="strict")
    facts = facts_for(path)
    description = description_for(facts)
    issues: list[str] = []

    source = HIDDEN_IMAGE_RE.sub("\n", old_source)
    if facts.source_address != facts.address:
        # 주소는 현재 HTML을 다시 신뢰하지 않고 권위 CSV 값으로 복구한다.
        # URL·src·href는 보존하고 화면 텍스트/사람이 읽는 속성만 바꾼 뒤,
        # JSON-LD는 아래 update_jsonld()에서 같은 기준값으로 재작성한다.
        source = replace_html_text(source, facts.source_address, facts.address)
        source = replace_text_attributes(source, facts.source_address, facts.address)
    # 사실 근거가 없는 성과 문구와 원고 중복이 집중된 legacy 원고 블록은
    # 결과 문장만 기계 치환하지 않고 통째로 제외한다. 이후 fact-based 섹션,
    # 센터 정보, FAQ와 상담 체크리스트만 유지해 의미와 가독성을 보존한다.
    source = LEGACY_ARTICLE_RE.sub("\n", source, count=1)
    if facts.tuition_url:
        fee_note = (
            "센터 제공 교습비 링크 자료를 확인할 수 있습니다. "
            "실제 개설 과목·횟수·금액은 상담 시 최종 확인해 주세요."
        )
    else:
        fee_note = (
            "센터 제공 교습비 자료 링크가 확인되지 않았습니다. "
            "실제 개설 과목·횟수·금액은 상담 시 확인해 주세요."
        )
    source = FEE_ACCORDION_RE.sub(
        '\n    <p class="wawa-fee-note">' + fee_note + "</p>\n",
        source,
    )
    source = source.replace("<strong>교육지원청</strong>", "<strong>등록 학원명</strong>")
    source = source.replace("<strong>등록번호</strong>", "<strong>교육청 등록번호</strong>")
    source = source.replace("주요 타깃학교(이외 학교도 수업 가능)", "참고 학교 정보")
    source = source.replace("초등 타깃학교", "초등 참고 학교")
    source = source.replace("중등 타깃학교", "중등 참고 학교")
    source = source.replace("고등 타깃학교", "고등 참고 학교")
    source = source.replace(
        '<span class="wawa-empty">학교별 수업 가능 여부는 상담 시 확인</span>',
        '<span class="wawa-empty">센터 제공 자료에서 학교 정보가 확인되지 않았습니다. 실제 학교별 수업·시험 대비 가능 여부는 상담 시 확인해 주세요.</span>',
    )
    source = re.sub(
        rf'<span\b[^>]*class=["\']wawa-pill["\'][^>]*>\s*{re.escape(GENERIC_SCHOOL)}\s*</span>',
        '<span class="wawa-empty">센터 제공 자료에서 고등학교 정보가 확인되지 않았습니다. 실제 학교별 수업 가능 여부는 상담 시 확인해 주세요.</span>',
        source,
        flags=re.I,
    )
    source = rewrite_visible_outcome_elements(source, facts)
    source = normalize_text(source, facts)
    if facts.neighborhood != facts.display_neighborhood:
        source = replace_html_text(
            source, facts.neighborhood, facts.display_neighborhood
        )
        source = replace_text_attributes(
            source, facts.neighborhood, facts.display_neighborhood
        )
    source = rewrite_leaf_availability(source, facts)

    breadcrumb_pattern = re.compile(
        r'<div\b[^>]*class=["\'][^"\']*\bbreadcrumb\b[^"\']*["\'][^>]*>.*?</div>',
        re.I | re.S,
    )
    source, breadcrumb_count = breadcrumb_pattern.subn(render_visible_breadcrumb(facts), source, count=1)
    if breadcrumb_count != 1:
        issues.append(f"화면 breadcrumb 교체 수={breadcrumb_count}")

    source, found = replace_meta(source, "name", "description", description)
    if not found:
        issues.append("meta description 없음")
    source, found = replace_meta(source, "property", "og:description", description)
    if not found:
        issues.append("og:description 없음")
    if meta_content(source, "name", "twitter:description"):
        source, _ = replace_meta(source, "name", "twitter:description", description)
    if facts.map_url:
        source, found = replace_meta(source, "property", "og:image", facts.map_url)
        if not found:
            issues.append("og:image 없음")
        image_alt = f"{facts.title} 센터 위치 지도"
        if meta_content(source, "property", "og:image:alt"):
            source, _ = replace_meta(source, "property", "og:image:alt", image_alt)
        else:
            og_image_tag = re.search(
                r'<meta\b(?=[^>]*\bproperty=["\']og:image["\'])[^>]*>',
                source,
                re.I | re.S,
            )
            if og_image_tag:
                tag = (
                    '<meta property="og:image:alt" content="'
                    + html.escape(image_alt, quote=True)
                    + '">'
                )
                source = source[: og_image_tag.end()] + "\n  " + tag + source[og_image_tag.end() :]
            else:
                issues.append("og:image:alt 삽입 위치 없음")
        if meta_content(source, "name", "twitter:image"):
            source, _ = replace_meta(source, "name", "twitter:image", facts.map_url)
    else:
        issues.append("로컬 지도 이미지 없음")

    note_pattern = re.compile(
        r'<p\b[^>]*class=["\'][^"\']*\bnational-source-note\b[^"\']*["\'][^>]*>.*?</p>',
        re.I | re.S,
    )
    if note_pattern.search(source):
        source = note_pattern.sub(source_note(), source, count=1)
    elif '<div class="parent-review-grid">' in source:
        source = source.replace(
            '<div class="parent-review-grid">',
            source_note() + '\n  <div class="parent-review-grid">',
            1,
        )
    else:
        issues.append("정보 기준 고지 삽입 위치 없음")

    source, json_errors = update_jsonld(source, facts, description)
    issues.extend(json_errors)

    if first_match(source, r'<link\b[^>]*rel=["\']canonical["\'][^>]*href=["\']([^"\']+)') != facts.canonical:
        issues.append("canonical 변경")
    if meta_content(source, "property", "og:url") != facts.og_url:
        issues.append("og:url 변경")
    if facts.canonical != facts.og_url:
        issues.append("기존 canonical/og:url 불일치")
    return Plan(facts, old_source, source, description, issues)


def visible_breadcrumb(source: str) -> list[str]:
    match = re.search(r'<div\b[^>]*class=["\'][^"\']*\bbreadcrumb\b[^"\']*["\'][^>]*>(.*?)</div>', source, re.I | re.S)
    if not match:
        return []
    value = html.unescape(re.sub(r"<[^>]+>", "", match.group(1)))
    return [part.strip() for part in value.split("›") if part.strip()]


def schema_nodes(source: str) -> tuple[list[dict[str, Any]], list[str]]:
    nodes: list[dict[str, Any]] = []
    errors: list[str] = []
    for match in JSON_LD_RE.finditer(source):
        try:
            nodes.extend(graph_nodes(json.loads(match.group(2))))
        except json.JSONDecodeError as exc:
            errors.append(str(exc))
    return nodes, errors


def strict_validate(plans: list[Plan]) -> tuple[list[str], dict[str, int]]:
    errors: list[str] = []
    descriptions: list[str] = []
    physical_ids: dict[str, set[str]] = defaultdict(set)
    physical_urls: dict[str, set[str]] = defaultdict(set)
    profile_keys: set[str] = set()
    fallback_keys: set[str] = set()
    canonical_before: set[str] = set()
    canonical_after: set[str] = set()
    counters = defaultdict(int)

    if len(plans) != EXPECTED_DETAIL_COUNT:
        errors.append(f"상세 수 {len(plans):,} / 예상 {EXPECTED_DETAIL_COUNT:,}")

    for plan in plans:
        facts = plan.facts
        source = plan.new_source
        canonical_before.add(facts.canonical)
        canonical_after.add(first_match(source, r'<link\b[^>]*rel=["\']canonical["\'][^>]*href=["\']([^"\']+)'))
        descriptions.append(meta_content(source, "name", "description"))
        physical_ids[facts.physical_key].add(facts.organization_id)
        if "/%EA%B3%BC%EB%AA%A9%EB%B3%84%ED%95%99%EC%9B%90/" in facts.organization_url:
            profile_keys.add(facts.physical_key)
        else:
            fallback_keys.add(facts.physical_key)
        for issue in plan.issues:
            errors.append(f"{facts.relative}: {issue}")

        expected_crumbs = [entry["name"] for entry in breadcrumb_entries(facts)]
        nodes, json_errors = schema_nodes(source)
        breadcrumb_node = next((node for node in nodes if "BreadcrumbList" in node_types(node)), {})
        schema_crumbs = [
            str(item.get("name", ""))
            for item in breadcrumb_node.get("itemListElement", [])
            if isinstance(item, dict)
        ]
        if visible_breadcrumb(source) != expected_crumbs or schema_crumbs != expected_crumbs:
            errors.append(f"{facts.relative}: breadcrumb 전체 계층/화면·JSON 불일치")

        org_nodes = [
            node for node in nodes if {"EducationalOrganization", "LocalBusiness"} & node_types(node)
        ]
        if not org_nodes or any(node.get("@id") != facts.organization_id for node in org_nodes):
            errors.append(f"{facts.relative}: 물리센터 @id 불일치")
        if not facts.organization_url or facts.organization_id != facts.organization_url + "#organization":
            errors.append(f"{facts.relative}: 물리센터 @id가 dereferenceable URL 기준이 아님")
        for node in org_nodes:
            if isinstance(node.get("url"), str) and node["url"]:
                physical_urls[facts.physical_key].add(node["url"])
            if node.get("url") != facts.organization_url:
                errors.append(f"{facts.relative}: Organization.url 대표 URL 불일치")
        if any("hasOfferCatalog" in node for node in org_nodes):
            errors.append(f"{facts.relative}: Organization 공통 가격 OfferCatalog 잔존")
        if any(
            key in node
            for node in org_nodes
            for key in ("telephone", "openingHours", "contactPoint")
        ):
            errors.append(f"{facts.relative}: 근거 없는 지점 전화/운영시간/contactPoint 잔존")
        if any(
            not isinstance(node.get("identifier"), dict)
            or node["identifier"].get("propertyID") != "교육지원청 등록번호"
            or node["identifier"].get("value") != facts.registration_number
            for node in org_nodes
        ):
            errors.append(f"{facts.relative}: identifier 교육지원청 등록번호 불일치")
        if "wawa-fee-table" in source or "wawa-fee-accordion" in source:
            errors.append(f"{facts.relative}: 공통 가격표 HTML 잔존")
        if "generated-hidden-image" in source:
            errors.append(f"{facts.relative}: hidden 대표 이미지 DOM 잔존")
        if "<strong>교육지원청</strong>" in source:
            errors.append(f"{facts.relative}: 잘못된 등록 학원명 라벨 잔존")
        if "주요 타깃학교(이외 학교도 수업 가능)" in source or "타깃학교" in source:
            errors.append(f"{facts.relative}: blanket 타깃학교 문구 잔존")
        if not facts.has_school_names and "센터 제공 자료에서 학교 정보가 확인되지 않았습니다" not in source:
            errors.append(f"{facts.relative}: 학교 공란 명시 분기 없음")
        if "기록와" in source:
            errors.append(f"{facts.relative}: 기록와 문장 오류 잔존")
        if "평소 공부 기록를" in source:
            errors.append(f"{facts.relative}: 기록 목적격 조사 오류 잔존")
        if OUTCOME_RE.search(source):
            errors.append(f"{facts.relative}: 성적/점수 상승 단정 잔존")
        if AWKWARD_OUTCOME_RE.search(source):
            errors.append(f"{facts.relative}: 성과 문구 기계 치환 흔적 잔존")
        if re.search(r'class=["\'][^"\']*\barticle-main\b', source, re.I):
            errors.append(f"{facts.relative}: legacy article-main 잔존")
        if OLD_CTA_RE.search(source):
            errors.append(f"{facts.relative}: 기존 영수 학습 상담 CTA 잔존")
        if GENERIC_SCHOOL in source:
            errors.append(f"{facts.relative}: blanket 고등학교 문구 잔존")
        if re.search(r"(?:초|고)이\s+포함되어", source):
            errors.append(f"{facts.relative}: 학교명 조사 오류 잔존")
        if source.count("national-source-note") != 1 or REVIEW_DATE not in source:
            errors.append(f"{facts.relative}: 정보 기준/검증일 고지 오류")
        if "편집: 학습코칭 연구소" not in source:
            errors.append(f"{facts.relative}: 편집 주체 고지 없음")
        if "교습비 안내 준비중" in source:
            errors.append(f"{facts.relative}: 교습비 준비중 placeholder 잔존")
        if facts.tuition_url:
            if "센터 제공 교습비 링크 자료를 확인할 수 있습니다" not in source:
                errors.append(f"{facts.relative}: 교습비 링크 있음 안내 분기 오류")
        elif "센터 제공 교습비 자료 링크가 확인되지 않았습니다" not in source:
            errors.append(f"{facts.relative}: 교습비 링크 없음 안내 분기 오류")
        og_image = meta_content(source, "property", "og:image")
        if "/assets/maps/" not in og_image or not og_image.startswith(BASE_URL):
            errors.append(f"{facts.relative}: og:image가 로컬 지도 이미지가 아님")
        if not meta_content(source, "property", "og:image:alt"):
            errors.append(f"{facts.relative}: og:image:alt 없음")
        article_nodes = [node for node in nodes if "Article" in node_types(node)]
        if not article_nodes or any("/assets/maps/" not in str(node.get("image", "")) for node in article_nodes):
            errors.append(f"{facts.relative}: Article image가 로컬 지도 이미지가 아님")
        expected_sections = visible_h2_names(source)
        expected_parts = [
            {"@type": "WebPageElement", "name": name}
            for name in expected_sections
        ]
        webpage_nodes = [node for node in nodes if "WebPage" in node_types(node)]
        if any(node.get("hasPart") != expected_parts for node in webpage_nodes):
            errors.append(f"{facts.relative}: WebPage.hasPart와 visible H2 불일치")
        if any(
            node.get("articleSection") != expected_sections
            or node.get("hasPart") != expected_parts
            for node in article_nodes
        ):
            errors.append(f"{facts.relative}: Article section/hasPart와 visible H2 불일치")
        for node in webpage_nodes + article_nodes:
            if node.get("author") != {"@id": ROOT_ORGANIZATION_ID}:
                errors.append(f"{facts.relative}: WebPage/Article author가 사이트 발행 주체가 아님")
            if node.get("publisher") != {"@id": ROOT_ORGANIZATION_ID}:
                errors.append(f"{facts.relative}: WebPage/Article publisher가 사이트 발행 주체가 아님")
        service_nodes = [node for node in nodes if "Service" in node_types(node)]
        if not service_nodes or any(
            node.get("provider") != {"@id": facts.organization_id}
            for node in service_nodes
        ):
            errors.append(f"{facts.relative}: Service.provider 물리센터 연결 오류")
        if any(
            node.get("areaServed")
            != {"@type": "Place", "name": facts.display_neighborhood}
            for node in service_nodes
        ):
            errors.append(f"{facts.relative}: Service.areaServed 표시 동네 오류")
        visible_faqs = visible_faq_pairs(source)
        faq_nodes = [node for node in nodes if "FAQPage" in node_types(node)]
        schema_faqs: list[tuple[str, str]] = []
        if len(faq_nodes) == 1:
            for item in faq_nodes[0].get("mainEntity", []):
                if not isinstance(item, dict):
                    continue
                accepted = item.get("acceptedAnswer")
                schema_faqs.append(
                    (
                        str(item.get("name", "")),
                        str(accepted.get("text", ""))
                        if isinstance(accepted, dict)
                        else "",
                    )
                )
        if len(visible_faqs) != 5 or schema_faqs != visible_faqs:
            errors.append(
                f"{facts.relative}: visible 5 FAQ/FAQPage exact 불일치 "
                f"({len(visible_faqs)}/{len(schema_faqs)})"
            )
        grade, grade_prefix = leaf_grade(facts)
        if grade:
            generated_parts: list[str] = []
            for pattern in (
                r'<details\b[^>]*class=["\'][^"\']*\bparent-faq-item\b[^"\']*["\'][^>]*>\s*<summary>.*?(?:가능 학년|수강 가능).*?</summary>\s*<p\b[^>]*>(.*?)</p>',
                r'<article\b[^>]*class=["\'][^"\']*\bparent-review-card\b[^"\']*["\'][^>]*>\s*<strong>과목별 수강 범위</strong>\s*<p>(.*?)</p>',
                r'<article>\s*<b>학교·가능 학년</b>\s*<p>(.*?)</p>\s*</article>',
            ):
                generated_parts.extend(re.findall(pattern, source, re.I | re.S))
            generated_text = clean_text(" ".join(generated_parts))
            wrong_grades = [
                value
                for value in re.findall(r"[초중고][1-6]", generated_text)
                if not value.startswith(grade_prefix)
            ]
            if wrong_grades:
                errors.append(
                    f"{facts.relative}: {grade} 상세에 타 학교급 가능학년 유입 {sorted(set(wrong_grades))}"
                )
            for subject in ("영어", "수학"):
                expected = [
                    value
                    for value in facts.available_grades.get(subject, ())
                    if value.startswith(grade_prefix)
                ]
                if not expected and f"{subject} 상담 시 확인" not in generated_text:
                    errors.append(f"{facts.relative}: {subject} {grade} 공란 상담 확인 분기 없음")
        if facts.address.startswith("세종특별자치시"):
            addresses = [
                node.get("address", {})
                for node in org_nodes
                if isinstance(node.get("address"), dict)
            ]
            if not addresses or any(
                item.get("addressRegion") != "세종특별자치시"
                or item.get("addressLocality") != "새롬동"
                for item in addresses
            ):
                errors.append(f"{facts.relative}: 세종 JSON-LD 지리값 오류")
            if "충청 새롬중앙로" in source:
                errors.append(f"{facts.relative}: 세종 화면 표기 오류")
            semantic_text = " ".join(
                text for node in nodes for text in semantic_json_strings(node)
            )
            if re.search(
                r"새롬중앙로\s*(?:학원|학습코칭|지역|의|에서|인근|은|는)",
                semantic_text,
            ):
                errors.append(f"{facts.relative}: 세종 semantic JSON-LD에 도로명 taxonomy 잔존")
        addresses = [
            node.get("address", {})
            for node in org_nodes
            if isinstance(node.get("address"), dict)
        ]
        if not addresses or any(
            item.get("addressRegion") != facts.address_region
            or item.get("addressLocality") != facts.address_locality
            for item in addresses
        ):
            errors.append(f"{facts.relative}: PostalAddress 주소 기반 지리값 오류")
        if facts.neighborhood != facts.display_neighborhood:
            visible_source = re.sub(
                r"<(?:script|style)\b.*?</(?:script|style)>",
                " ",
                source,
                flags=re.I | re.S,
            )
            visible_text = clean_text(visible_source)
            if facts.neighborhood in visible_text:
                errors.append(f"{facts.relative}: hyphen locality 화면 표기 잔존")
            semantic_text = " ".join(
                text for node in nodes for text in semantic_json_strings(node)
            )
            if facts.neighborhood in semantic_text:
                errors.append(f"{facts.relative}: hyphen locality semantic JSON-LD 잔존")

        counters["changed"] += int(plan.old_source != source)
        counters["hidden"] += source.count("generated-hidden-image")
        counters["old_cta"] += len(OLD_CTA_RE.findall(source))
        counters["unsupported_outcomes"] += len(OUTCOME_RE.findall(source))
        counters["legacy_article_blocks"] += len(
            re.findall(r'class=["\'][^"\']*\barticle-main\b', source, re.I)
        )

    if canonical_before != canonical_after:
        errors.append("collection: canonical URL 집합 변경")
    if len(set(descriptions)) != len(plans):
        errors.append(f"collection: 고유 meta description {len(set(descriptions)):,}/{len(plans):,}")
    lengths = [len(value) for value in descriptions]
    if not lengths or min(lengths) < 20 or max(lengths) > 80:
        errors.append(
            f"collection: meta description 길이 {min(lengths, default=0)}~{max(lengths, default=0)}자"
        )
    unstable = [key for key, ids in physical_ids.items() if len(ids) != 1]
    if unstable:
        errors.append(f"collection: 동일 물리센터 복수 @id {len(unstable):,}건")
    unstable_urls = [key for key, urls in physical_urls.items() if len(urls) > 1]
    if unstable_urls:
        errors.append(f"collection: 동일 물리센터 복수 Organization.url {len(unstable_urls):,}건")
    organization_ids = {plan.facts.organization_id for plan in plans}
    if len(physical_ids) != 188 or len(organization_ids) != 188:
        errors.append(
            f"collection: 물리센터/@id 고유 수 {len(physical_ids):,}/{len(organization_ids):,}, 예상 188/188"
        )
    if len(profile_keys) != 182 or len(fallback_keys) != 6:
        errors.append(
            f"collection: 센터 프로필/상세 fallback identity {len(profile_keys):,}/{len(fallback_keys):,}, "
            "예상 182/6"
        )

    counters["details"] = len(plans)
    counters["unique_descriptions"] = len(set(descriptions))
    counters["description_min"] = min(lengths, default=0)
    counters["description_max"] = max(lengths, default=0)
    counters["physical_centers"] = len(physical_ids)
    counters["organization_ids"] = len(organization_ids)
    counters["profile_identities"] = len(profile_keys)
    counters["fallback_identities"] = len(fallback_keys)
    return errors, dict(counters)


def atomic_write(path: Path, value: str) -> None:
    temporary = path.with_name(path.name + ".national-final.tmp")
    temporary.write_text(value, encoding="utf-8", newline="\n")
    temporary.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="전체 검증 통과 후 상세 HTML에 반영")
    parser.add_argument("--sample", type=int, default=3, help="변경 예시 경로 수(기본 3)")
    args = parser.parse_args()

    targets = [
        path
        for path in sorted(NATIONAL_ROOT.rglob("index.html"))
        if len(path.parent.relative_to(NATIONAL_ROOT).parts) in {3, 4}
    ]
    plans: list[Plan] = []
    for index, path in enumerate(targets, start=1):
        try:
            plans.append(transform(path))
        except Exception as exc:
            print(f"변환 준비 실패: {path.relative_to(ROOT)}: {exc}", file=sys.stderr)
            return 2
        if index % 250 == 0:
            print(f"검사 준비 {index:,}/{len(targets):,}", file=sys.stderr)

    errors, summary = strict_validate(plans)
    print(f"mode={'APPLY' if args.apply else 'DRY-RUN'}")
    print(f"detail_pages={summary['details']:,}")
    print(f"changed_pages={summary['changed']:,}")
    print(
        "unique_meta_descriptions="
        f"{summary['unique_descriptions']:,}/{summary['details']:,} "
        f"({summary['description_min']}~{summary['description_max']}자)"
    )
    print(
        f"physical_centers={summary['physical_centers']:,} "
        f"stable_organization_ids={summary['organization_ids']:,}"
    )
    print(
        f"profile_identities={summary['profile_identities']:,} "
        f"detail_fallback_identities={summary['fallback_identities']:,}"
    )
    print(f"hidden_generated_images={summary['hidden']:,}")
    print(f"old_yeongsu_cta={summary['old_cta']:,}")
    print(f"unsupported_outcome_phrases={summary['unsupported_outcomes']:,}")
    print(f"legacy_article_blocks={summary['legacy_article_blocks']:,}")
    print(f"errors={len(errors):,}")
    for error in errors[:80]:
        print(f"ERROR {error}")
    if errors:
        return 1

    for plan in [plan for plan in plans if plan.old_source != plan.new_source][: max(args.sample, 0)]:
        print(f"SAMPLE {plan.facts.relative} | {plan.description}")

    if args.apply:
        for plan in plans:
            if plan.old_source != plan.new_source:
                atomic_write(plan.facts.path, plan.new_source)
        print(f"written_pages={summary['changed']:,}")
    else:
        print("dry-run 완료: 파일을 수정하지 않았습니다. 반영하려면 --apply를 명시하세요.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
