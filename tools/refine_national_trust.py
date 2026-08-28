from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import quote, urljoin

try:
    from finalize_national_details import (
        center_directory_identity as dereferenceable_center_identity,
        postal_geography,
    )
    from source_copy_utils import VERIFIED_SCHOOL_SOURCE_CORRECTIONS
except ModuleNotFoundError:  # package import
    from .finalize_national_details import (
        center_directory_identity as dereferenceable_center_identity,
        postal_geography,
    )
    from .source_copy_utils import VERIFIED_SCHOOL_SOURCE_CORRECTIONS


ROOT = Path(__file__).resolve().parents[1]
NATIONAL_ROOT = ROOT / "전국학원"
REFERENCE_CSV = ROOT.parent / "참고자료" / "공통자료" / "센터정보 정리.csv"
BASE_URL = "https://xn--ru4bi8s1tac0p.kr"
ROOT_ORGANIZATION_ID = f"{BASE_URL}/#organization"
CENTER_DIRECTORY_ROOT = ROOT / "과목별학원" / "와와학습코칭센터"
DATA_REVIEW_DATE = "2026-08-27"
CROSS_LEVEL_SCHOOL_SOURCE = "오현초호매실중, 능실중, 영신중, 고색중"
CROSS_LEVEL_ELEMENTARY_SCHOOL = "오현초"

JSON_LD_RE = re.compile(
    r'(<script\s+type=["\']application/ld\+json["\'][^>]*>)(.*?)(</script>)',
    re.I | re.S,
)
H1_RE = re.compile(r"<h1\b[^>]*>(.*?)</h1>", re.I | re.S)
FAQ_SECTION_RE = re.compile(
    r'<section\s+class=["\'][^"\']*\bparent-faq-section\b[^"\']*["\'][^>]*>.*?</section>',
    re.I | re.S,
)
REVIEW_SECTION_RE = re.compile(
    r'<section\s+class=["\'][^"\']*\bparent-review-section\b[^"\']*["\'][^>]*>.*?</section>',
    re.I | re.S,
)


def strip_tags(value: str) -> str:
    value = re.sub(r"<[^>]+>", " ", value or "")
    return re.sub(r"\s+", " ", html.unescape(value)).strip()


def page_url(page: Path) -> str:
    rel = page.relative_to(ROOT).as_posix()
    if rel == "index.html":
        suffix = "/"
    else:
        suffix = "/" + rel.removesuffix("index.html")
    return BASE_URL + quote(suffix, safe="/")


def normalize_neighborhood(value: str) -> str:
    value = value.replace("-", " ")
    return re.sub(r"\s+", " ", value).strip()


def display_geography(region: str, district: str, address: str) -> tuple[str, str]:
    """경로 호환성은 유지하면서 실제 주소에 맞는 표시용 지리값을 돌려준다."""
    if address.startswith("세종특별자치시"):
        return "충청·세종", "세종특별자치시"
    return region, district


def center_identity(
    center_name: str, registration_number: str, address: str
) -> tuple[str, str]:
    """프로필 182개/대표 locality 6개에 실제로 연결되는 stable @id."""
    return dereferenceable_center_identity(center_name, registration_number, address)


def stable_index(seed: str, size: int, namespace: str) -> int:
    digest = hashlib.sha256(f"{namespace}|{seed}".encode("utf-8")).hexdigest()
    return int(digest[:12], 16) % size


def pick(seed: str, namespace: str, values: list[str]) -> str:
    return values[stable_index(seed, len(values), namespace)]


def split_csv_list(value: str) -> list[str]:
    text = re.sub(r"\s+", " ", value or "").strip()
    verified = VERIFIED_SCHOOL_SOURCE_CORRECTIONS.get(text)
    if verified:
        return list(verified)
    return [
        part.strip()
        for part in text.split(",")
        if part.strip() and part.strip() != "지역내 모든 고등학교 가능"
    ]


def has_cross_level_school_source(center: dict[str, str]) -> bool:
    value = re.sub(r"\s+", " ", center.get("타깃학교\n(중)", "")).strip()
    return value == CROSS_LEVEL_SCHOOL_SOURCE


def load_centers() -> dict[tuple[str, str, str], dict[str, str]]:
    with REFERENCE_CSV.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    result: dict[tuple[str, str, str], dict[str, str]] = {}
    for row in rows:
        key = (
            row["지역"].strip(),
            row["시or구"].strip(),
            normalize_neighborhood(row["근처 수업가능 동네"]),
        )
        result[key] = row
    return result


def is_detail_page(path: Path) -> bool:
    parts = path.parent.relative_to(NATIONAL_ROOT).parts
    return len(parts) in {3, 4}


def context_for(
    path: Path, source: str, centers: dict[tuple[str, str, str], dict[str, str]]
) -> dict[str, Any]:
    parts = path.parent.relative_to(NATIONAL_ROOT).parts
    region, district, neighborhood = parts[:3]
    child = parts[3] if len(parts) == 4 else ""
    h1_match = H1_RE.search(source)
    title = strip_tags(h1_match.group(1)) if h1_match else f"{neighborhood} {child}".strip()
    key = (region, district, normalize_neighborhood(neighborhood))
    center = centers.get(key)
    if not center:
        raise KeyError(f"센터정보 매칭 실패: {path.relative_to(ROOT)} -> {key}")

    if "고등" in title:
        grade = "고등"
        grade_column = "타깃학교\n(고)"
    elif "중등" in title:
        grade = "중등"
        grade_column = "타깃학교\n(중)"
    elif "초등" in title:
        grade = "초등"
        grade_column = "타깃학교\n(초)"
    else:
        grade = "초·중·고"
        grade_column = ""

    subjects = "영어·수학" if child else "국어·영어·수학"
    schools: list[str] = []
    if grade_column:
        schools = split_csv_list(center.get(grade_column, ""))
        if has_cross_level_school_source(center):
            if grade == "초등" and CROSS_LEVEL_ELEMENTARY_SCHOOL not in schools:
                schools.append(CROSS_LEVEL_ELEMENTARY_SCHOOL)
            elif grade == "중등":
                schools = [
                    school
                    for school in schools
                    if school != CROSS_LEVEL_ELEMENTARY_SCHOOL
                ]
    else:
        for column in ("타깃학교\n(초)", "타깃학교\n(중)", "타깃학교\n(고)"):
            for school in split_csv_list(center.get(column, "")):
                if school not in schools:
                    schools.append(school)

    parent_dir = NATIONAL_ROOT / region / district / neighborhood
    parent_url = page_url(parent_dir / "index.html")
    current_url = page_url(path)
    map_match = re.search(
        r'<img\b[^>]*src=["\']([^"\']*assets/maps/[^"\']+)["\']',
        source,
        re.I | re.S,
    )
    map_url = urljoin(current_url, html.unescape(map_match.group(1))) if map_match else ""
    center_name = center.get("센터명", "").strip() or f"와와학습코칭센터 {neighborhood}점"
    address = center.get("센터 주소", "").strip()
    registration_name = center.get("교육지원청명칭", "").strip()
    registration_number = center.get("교육지원청 등록번호", "").strip()
    tuition_url = center.get("센터 교습비", "").strip()
    display_region, display_district = display_geography(region, district, address)
    address_region, address_locality = postal_geography(address)
    organization_id, organization_url = center_identity(
        center_name, registration_number, address
    )

    available_grades = {
        "국어": split_csv_list(center.get("가능학년\n(국어)", "")),
        "영어": split_csv_list(center.get("가능학년\n(영어)", "")),
        "수학": split_csv_list(center.get("가능학년\n(수학)", "")),
        "과학": split_csv_list(center.get("가능학년\n(과학)", "")),
        "사회": split_csv_list(center.get("가능학년\n(사회)", "")),
    }
    scenario_match = re.search(
        r"<article><b>학생 상황</b><p>(.*?)</p></article>",
        source,
        re.I | re.S,
    )
    focus_match = re.search(
        r"<article><b>학년·과목</b><p>.*?기준으로\s*(.*?)</p></article>",
        source,
        re.I | re.S,
    )
    student_scenario = (
        strip_tags(scenario_match.group(1))
        if scenario_match
        else f"{grade} 학생의 현재 학습 흐름을 구체적으로 확인해야 하는 경우"
    )
    learning_focus = (
        strip_tags(focus_match.group(1))
        if focus_match
        else "현재 교재와 최근 평가 자료를 함께 확인하는 것"
    )

    return {
        "path": path,
        "seed": path.relative_to(ROOT).as_posix(),
        "region": region,
        "district": district,
        "display_region": display_region,
        "display_district": display_district,
        "address_region": address_region,
        "address_locality": address_locality,
        "neighborhood": neighborhood,
        "child": child,
        "is_child": bool(child),
        "title": title,
        "grade": grade,
        "subjects": subjects,
        "schools": schools,
        "center": center,
        "center_name": center_name,
        "address": address,
        "registration_name": registration_name,
        "registration_number": registration_number,
        "tuition_url": tuition_url,
        "available_grades": available_grades,
        "student_scenario": student_scenario,
        "learning_focus": learning_focus,
        "url": current_url,
        "parent_url": parent_url,
        "map_url": map_url,
        "organization_id": organization_id,
        "organization_url": organization_url,
    }


def breadcrumb_items(ctx: dict[str, Any]) -> list[dict[str, str]]:
    def absolute(*parts: str) -> str:
        suffix = "/" + "/".join(part.strip("/") for part in parts if part) + "/"
        return BASE_URL + quote(suffix, safe="/")

    items = [
        {"name": "홈", "item": BASE_URL + "/"},
        {"name": "전국학원", "item": absolute("전국학원")},
        {
            "name": ctx["display_region"],
            "item": absolute("전국학원", ctx["region"]),
        },
        {
            "name": ctx["display_district"],
            "item": absolute("전국학원", ctx["region"], ctx["district"]),
        },
    ]
    if ctx["is_child"]:
        items.append(
            {
                "name": f"{ctx['neighborhood']} 학원",
                "item": ctx["parent_url"],
            }
        )
    items.append({"name": ctx["title"], "item": ctx["url"]})
    return items


def update_visible_breadcrumb(source: str, ctx: dict[str, Any]) -> str:
    items = breadcrumb_items(ctx)
    values = [
        f'<a href="{html.escape(item["item"], quote=True)}">{html.escape(item["name"])}</a>'
        for item in items[:-1]
    ]
    values.append(html.escape(items[-1]["name"]))
    rendered = '<div class="breadcrumb">' + " › ".join(values) + "</div>"
    return re.sub(
        r'<div\b[^>]*class=["\'][^"\']*\bbreadcrumb\b[^"\']*["\'][^>]*>.*?</div>',
        rendered,
        source,
        count=1,
        flags=re.I | re.S,
    )


def types_of(node: dict[str, Any]) -> set[str]:
    value = node.get("@type")
    if isinstance(value, list):
        return {str(item) for item in value}
    return {str(value)} if value else set()


def replace_exact(value: Any, old: str, new: str) -> Any:
    if isinstance(value, str):
        return new if value == old else value
    if isinstance(value, list):
        return [replace_exact(item, old, new) for item in value]
    if isinstance(value, dict):
        return {key: replace_exact(item, old, new) for key, item in value.items()}
    return value


def grade_availability_text(ctx: dict[str, Any]) -> str:
    available = ctx["available_grades"]
    if ctx["is_child"]:
        prefix = {"초등": "초", "중등": "중", "고등": "고"}.get(ctx["grade"], "")
        parts: list[str] = []
        for subject in ("영어", "수학"):
            values = [
                value for value in available.get(subject, []) if prefix and value.startswith(prefix)
            ]
            if values:
                parts.append(f"{subject} {', '.join(values)}")
            else:
                parts.append(f"{subject} 상담 시 확인")
        return " · ".join(parts)

    parts = []
    for subject in ("국어", "영어", "수학"):
        values = available.get(subject, [])
        if values:
            parts.append(f"{subject} {', '.join(values)}")
    return " · ".join(parts) if parts else "과목별 수강 가능 학년은 상담 시 확인"


def school_text(ctx: dict[str, Any]) -> str:
    schools = ctx["schools"]
    if schools:
        visible = ", ".join(schools[:4])
        return f"페이지에 제공된 참고 학교는 {visible}이며, 실제 학교별 진도와 시험 범위는 상담 시 확인합니다."
    return (
        "센터 제공 자료에서 학교 정보가 확인되지 않았습니다. "
        "실제 학교별 수업·시험 대비 가능 여부는 상담 시 확인해 주세요."
    )


def build_faq(ctx: dict[str, Any]) -> list[tuple[str, str]]:
    title = ctx["title"]
    center_name = ctx["center_name"]
    address = ctx["address"]
    availability = grade_availability_text(ctx)
    school_answer = school_text(ctx)
    grade = ctx["grade"]
    seed = ctx["seed"]

    location_questions = [
        f"{title} 상담은 어느 센터에서 진행하나요?",
        f"{title} 센터 위치는 어디인가요?",
        f"{title} 상담 장소를 어떻게 확인할 수 있나요?",
    ]
    location_answers = [
        f"{title} 상담 안내 센터는 {center_name}이며 주소는 {address}입니다. 방문 전 페이지의 지도와 센터 안내를 함께 확인해 주세요.",
        f"{center_name}은 {address}에 있습니다. {title} 상담 전 지도 링크로 위치를 확인하면 방문 동선을 잡기 좋습니다.",
        f"페이지에 연결된 센터는 {center_name}이고 주소는 {address}입니다. 실제 방문 일정은 상담 시 다시 확인해 주세요.",
    ]
    availability_questions = [
        f"{title}에서 확인할 수 있는 수강 가능 학년은 어떻게 되나요?",
        f"{title} 영어·수학 수강 학년은 어디서 확인하나요?",
        f"{title} 상담 전에 과목별 가능 학년을 알 수 있나요?",
    ]
    availability_answers = [
        f"{title} 페이지에 제공된 센터 정보 기준으로 {availability}입니다. 반 편성과 시간표는 학생의 학년과 현재 진도를 확인한 뒤 안내합니다.",
        f"{center_name}에 등록된 {title} 가능 학년은 {availability}입니다. 정확한 수업 가능 여부는 상담 시 과목과 희망 시간대를 함께 확인해 주세요.",
        f"{title} 과목별 안내 자료에는 {availability}로 정리되어 있습니다. 학생별 진도와 수업 일정에 따라 최종 안내가 달라질 수 있습니다.",
    ]
    school_questions = [
        f"{title}을 알아보는 {ctx['neighborhood']} 학생은 학교별 진도를 어떻게 확인하나요?",
        f"{title} 상담에서 학교 정보도 함께 보나요?",
        f"{title} 수업 계획에는 학교 시험 범위를 어떻게 반영하나요?",
    ]

    if grade == "고등":
        learning_pairs = [
            (
                "고등 영어·수학은 내신과 모의고사를 어떻게 나누어 준비하나요?",
                "최근 학교 시험지와 모의고사 결과를 따로 살펴보고, 영어는 어휘·문법·독해를, 수학은 개념·유형·풀이 과정을 구분해 우선순위를 정합니다.",
            ),
            (
                "고등학생이 공부 시간은 긴데 성과가 적다면 무엇을 확인하나요?",
                "과목별 실제 학습 시간, 문제를 푼 뒤 오답을 확인하는 방식, 시험 범위별 완료 여부를 살펴 계획과 실행 사이의 차이를 먼저 찾습니다.",
            ),
            (
                "고등 과정 상담에는 어떤 학습 자료가 필요한가요?",
                "최근 내신 시험지와 모의고사 성적표, 사용 중인 교재, 학교 시험 범위와 평소 주간 공부 기록을 준비하면 상담 방향을 구체화하기 좋습니다.",
            ),
        ]
    elif grade == "중등":
        learning_pairs = [
            (
                "중등 영어·수학 내신 준비는 언제부터 점검하는 것이 좋나요?",
                "평소에는 개념과 숙제 실행을 관리하고, 시험 범위가 확인되면 학교 진도와 반복 오답을 기준으로 복습 순서를 조정하는 방식이 안정적입니다.",
            ),
            (
                "중학생이 같은 유형을 반복해서 틀리면 어떻게 확인하나요?",
                "개념을 모르는지, 문제 조건을 놓치는지, 계산이나 해석 과정에서 실수하는지를 나누어 보고 원인에 맞는 재풀이 방법을 정합니다.",
            ),
            (
                "중등 과정 상담에는 무엇을 준비하면 되나요?",
                "최근 시험지, 수행평가 일정, 사용 중인 교재와 숙제 수행 기록을 준비하면 학교 학습과 평소 공부 습관을 함께 확인할 수 있습니다.",
            ),
        ]
    elif grade == "초등":
        learning_pairs = [
            (
                "초등 영어·수학은 선행보다 무엇을 먼저 확인해야 하나요?",
                "현재 학년의 읽기·계산·개념 이해가 안정적인지, 짧은 분량이라도 스스로 공부하는 습관이 있는지를 먼저 확인하는 편이 좋습니다.",
            ),
            (
                "초등학생이 문제를 빨리 풀지만 실수가 많으면 어떻게 지도하나요?",
                "정답 개수만 보기보다 문제를 읽는 순서와 풀이 흔적을 확인하고, 틀린 이유를 학생이 설명한 뒤 비슷한 문제를 다시 풀어보게 합니다.",
            ),
            (
                "초등 과정 상담에는 어떤 자료가 필요하나요?",
                "사용 중인 교재와 최근 단원평가, 학교 진도, 평소 숙제 시간과 어려워하는 단원을 정리해 오면 현재 학습 상태를 확인하기 좋습니다.",
            ),
        ]
    else:
        learning_pairs = [
            (
                "처음 상담할 때 어떤 자료를 준비하면 되나요?",
                "학생의 현재 학년과 학교, 사용 중인 교재, 최근 시험지 또는 단원평가, 평소 공부 시간과 우선 상담 목표를 함께 준비해 주세요.",
            ),
            (
                "영어·수학 학습 방향은 어떤 기준으로 정하나요?",
                "학년과 학교 진도, 최근 평가 결과, 반복되는 오답과 숙제 실행 정도를 확인해 먼저 보완할 과목과 단원을 정합니다.",
            ),
            (
                "학습계획은 학생마다 다르게 정하나요?",
                "현재 교재와 가용 시간, 시험 일정, 혼자 수행할 수 있는 분량을 기준으로 주간 계획을 조정합니다.",
            ),
        ]

    fee_question = pick(
        seed,
        "fee-question",
        [
            f"{title} 교습비와 수업 횟수는 어디에서 확인할 수 있나요?",
            f"{title} 상담 전에 교습비 안내를 확인할 수 있나요?",
            f"{title} 수업료와 주당 횟수는 어떻게 확인하나요?",
        ],
    )
    fee_answer = (
        f"{title} 페이지의 센터 제공 교습비 링크에서 안내 자료를 확인할 수 있습니다. "
        "실제 수강료와 횟수는 상담 시 최종 확인해 주세요."
        if ctx["tuition_url"]
        else "센터 제공 교습비 자료가 확인되지 않아 실제 금액·횟수와 개설 과목은 상담 시 확인해 주세요."
    )

    location_index = stable_index(seed, len(location_questions), "location")
    availability_index = stable_index(seed, len(availability_questions), "availability")
    school_index = stable_index(seed, len(school_questions), "school")
    learning_question, learning_answer = learning_pairs[
        stable_index(seed, len(learning_pairs), "learning")
    ]
    learning_pair = (
        f"{title} 상담에서 {learning_question}",
        f"{title} 상담에서는 {learning_answer}",
    )

    return [
        (location_questions[location_index], location_answers[location_index]),
        (
            availability_questions[availability_index],
            availability_answers[availability_index],
        ),
        (school_questions[school_index], school_answer),
        learning_pair,
        (fee_question, fee_answer),
    ]


def render_faq(ctx: dict[str, Any], pairs: list[tuple[str, str]]) -> str:
    items: list[str] = []
    for index, (question, answer) in enumerate(pairs):
        open_attr = " open" if index == 0 else ""
        items.append(
            f"""    <details class="parent-faq-item"{open_attr}>
      <summary><span class="parent-faq-q">Q</span>{html.escape(question)}</summary>
      <p class="parent-faq-answer">{html.escape(answer)}</p>
    </details>"""
        )
    return f"""<section class="parent-faq-section" aria-labelledby="parent-faq-title">
  <div class="parent-faq-head">
    <p class="parent-faq-eyebrow">자주 묻는 질문</p>
    <h2 id="parent-faq-title">{html.escape(ctx['title'])} FAQ</h2>
    <p>{html.escape(ctx['center_name'])}의 위치·수강 범위와 상담 준비사항을 실제 제공 정보에 맞춰 정리했습니다.</p>
  </div>
  <div class="parent-faq-list">
{chr(10).join(items)}
  </div>
</section>"""


def guidance_cards(ctx: dict[str, Any]) -> list[tuple[str, str]]:
    title = ctx["title"]
    center_name = ctx["center_name"]
    address = ctx["address"]
    school_summary = school_text(ctx)
    availability = grade_availability_text(ctx)
    grade = ctx["grade"]
    scenario = ctx["student_scenario"]
    focus = ctx["learning_focus"]
    seed = ctx["seed"]

    if grade == "고등":
        grade_material = "최근 내신 시험지·모의고사 결과·학교 시험 범위"
    elif grade == "중등":
        grade_material = "최근 시험지·수행평가 일정·현재 교재"
    elif grade == "초등":
        grade_material = "현재 교재·최근 단원평가·학교 진도"
    else:
        grade_material = "현재 교재·최근 평가 자료·평소 공부 기록"

    prep = pick(
        seed,
        "proof-preparation",
        [
            f"{grade_material}를 준비하고, {scenario}에 해당하는 모습을 함께 정리합니다.",
            f"{focus}을 확인할 수 있도록 {grade_material} 및 최근 공부 기록을 함께 살펴봅니다.",
            f"{title} 상담 전 {grade_material}에서 반복된 어려움과 스스로 해결한 범위를 구분합니다.",
            f"{grade_material} 가운데 {focus}과 관련된 부분을 표시해 상담 질문을 구체화합니다.",
            f"{scenario}인지 판단할 수 있게 {grade_material}와 숙제·복습 기록을 함께 준비합니다.",
            f"{title} 학습 방향을 정하기 위해 {grade_material}와 학생이 어려워한 단원을 간단히 적습니다.",
            f"{grade_material}를 최근 순서로 정리하고, 계획대로 끝낸 범위와 남은 범위를 구분합니다.",
            f"{focus}을 상담에서 확인하려면 {grade_material} 및 오답을 다시 본 날짜를 함께 준비하면 좋습니다.",
        ],
    )

    return [
        (
            "센터와 위치",
            f"{title} 안내 센터는 {center_name}이며 주소는 {address}입니다. 방문 전 지도와 상담 일정을 확인해 주세요.",
        ),
        ("학교·진도 확인", school_summary),
        (
            "과목별 수강 범위",
            f"{title}에 제공된 센터 자료에는 {availability}로 안내되어 있습니다. 최종 반 편성과 시간은 상담 시 확인합니다.",
        ),
        ("상담 자료 준비", prep),
    ]


def render_guidance(ctx: dict[str, Any]) -> str:
    cards = []
    for heading, body in guidance_cards(ctx):
        cards.append(
            f"""    <article class="parent-review-card">
      <strong>{html.escape(heading)}</strong>
      <p>{html.escape(body)}</p>
    </article>"""
        )
    lead = pick(
        ctx["seed"],
        "proof-lead",
        [
            f"{ctx['title']} 상담에 필요한 센터 위치, 학교 참고 정보, 수강 가능 학년과 준비 자료를 구분해 안내합니다.",
            f"{ctx['neighborhood']} 학생의 현재 학습 흐름을 설명하기 전에 센터 정보와 {ctx['grade']} 상담 자료를 먼저 확인하세요.",
            f"{ctx['title']} 선택 시 확인할 사실 정보와 학생별로 달라지는 상담 준비 항목을 나누어 정리했습니다.",
            f"{ctx['center_name']}의 위치·수강 범위와 {ctx['student_scenario']} 상황에 필요한 준비 자료를 함께 확인할 수 있습니다.",
            f"{ctx['title']} 상담을 구체적으로 진행할 수 있도록 센터 제공 정보와 {ctx['learning_focus']} 기준을 정리했습니다.",
            f"{ctx['display_region']} {ctx['display_district']}의 센터 정보와 {ctx['grade']} {ctx['subjects']} 상담 전에 살펴볼 자료를 한곳에 모았습니다.",
            f"{ctx['title']} 페이지에 확인된 위치·학교·학년 정보와 학생 상황을 설명할 자료를 항목별로 살펴보세요.",
            f"{ctx['neighborhood']}에서 {ctx['grade']} 학습 상담을 준비할 때 확인할 센터 정보와 최근 학습 자료를 정리했습니다.",
        ],
    )
    return f"""<section class="parent-review-section learning-proof-section" aria-labelledby="parent-review-title">
  <div class="parent-review-head">
    <p class="parent-review-eyebrow">학습관리 확인 정보</p>
    <h2 id="parent-review-title">{html.escape(ctx['title'])} 상담 전에 확인할 내용</h2>
    <p>{html.escape(lead)}</p>
  </div>
  <p class="national-source-note"><strong>정보 기준</strong> 사이트가 보유한 센터 제공 자료를 {DATA_REVIEW_DATE} 재검토했습니다. 현재 개설 과목·반 편성·운영 여부는 상담 시 최종 확인해 주세요. 편집: 학습코칭.kr.</p>
  <div class="parent-review-grid">
{chr(10).join(cards)}
  </div>
</section>"""


def faq_schema(pairs: list[tuple[str, str]]) -> list[dict[str, Any]]:
    return [
        {
            "@type": "Question",
            "name": question,
            "acceptedAnswer": {"@type": "Answer", "text": answer},
        }
        for question, answer in pairs
    ]


def checklist_from_html(source: str) -> list[str]:
    match = re.search(
        r'<ol class="seo-checklist">(.*?)</ol>', source, re.I | re.S
    )
    if not match:
        return []
    values = []
    for item in re.findall(r"<li\b[^>]*>(.*?)</li>", match.group(1), re.I | re.S):
        text = strip_tags(item)
        if text:
            values.append(text)
    return values


def update_jsonld(
    source: str, ctx: dict[str, Any], pairs: list[tuple[str, str]]
) -> tuple[str, int]:
    changes = 0

    def replace_script(match: re.Match[str]) -> str:
        nonlocal changes
        try:
            data = json.loads(match.group(2))
        except json.JSONDecodeError:
            return match.group(0)

        graph = data.get("@graph") if isinstance(data, dict) else None
        nodes = graph if isinstance(graph, list) else [data] if isinstance(data, dict) else []
        old_org_ids = [
            node.get("@id")
            for node in nodes
            if isinstance(node, dict)
            and {"EducationalOrganization", "LocalBusiness"} & types_of(node)
            and isinstance(node.get("@id"), str)
        ]
        for old_org_id in old_org_ids:
            if old_org_id != ctx["organization_id"]:
                data = replace_exact(data, old_org_id, ctx["organization_id"])

        graph = data.get("@graph") if isinstance(data, dict) else None
        nodes = graph if isinstance(graph, list) else [data] if isinstance(data, dict) else []
        for node in nodes:
            if not isinstance(node, dict):
                continue
            node_types = types_of(node)

            if {"EducationalOrganization", "LocalBusiness"} & node_types:
                node["@id"] = ctx["organization_id"]
                node["name"] = ctx["center_name"]
                if ctx["organization_url"]:
                    node["url"] = ctx["organization_url"]
                else:
                    node.pop("url", None)
                node["branchOf"] = {"@id": ROOT_ORGANIZATION_ID}
                node["areaServed"] = {
                    "@type": "Place",
                    "name": ctx["neighborhood"],
                }
                node["address"] = {
                    "@type": "PostalAddress",
                    "streetAddress": ctx["address"],
                    "addressRegion": ctx["address_region"],
                    "addressLocality": ctx["address_locality"],
                    "addressCountry": "KR",
                }
                node.pop("hasOfferCatalog", None)
                if ctx["map_url"]:
                    node["image"] = ctx["map_url"]
                node.pop("aggregateRating", None)
                node.pop("review", None)
                node.pop("telephone", None)
                node.pop("openingHours", None)
                node.pop("contactPoint", None)
                if ctx["registration_number"]:
                    node["identifier"] = {
                        "@type": "PropertyValue",
                        "propertyID": "교육청 등록번호",
                        "value": ctx["registration_number"],
                    }

            if "WebPage" in node_types:
                node["author"] = {"@id": ROOT_ORGANIZATION_ID}
                node["publisher"] = {"@id": ROOT_ORGANIZATION_ID}
                node["dateModified"] = DATA_REVIEW_DATE
                parts = node.get("hasPart")
                if isinstance(parts, list):
                    for part in parts:
                        if isinstance(part, dict) and part.get("name") == "학부모 후기":
                            part["name"] = "학습관리 확인 정보"

            if "Article" in node_types:
                node["author"] = {"@id": ROOT_ORGANIZATION_ID}
                node["publisher"] = {"@id": ROOT_ORGANIZATION_ID}
                node["dateModified"] = DATA_REVIEW_DATE
                if ctx["map_url"]:
                    node["image"] = ctx["map_url"]
                sections = node.get("articleSection")
                if isinstance(sections, list):
                    node["articleSection"] = [
                        "학습관리 확인 정보" if item == "학부모 후기" else item
                        for item in sections
                    ]

            if "Service" in node_types:
                node["provider"] = {"@id": ctx["organization_id"]}
                node.pop("hasOfferCatalog", None)
                node["areaServed"] = {
                    "@type": "Place",
                    "name": ctx["neighborhood"],
                }

            if "FAQPage" in node_types:
                node["mainEntity"] = faq_schema(pairs)

            if "BreadcrumbList" in node_types:
                node["itemListElement"] = [
                    {
                        "@type": "ListItem",
                        "position": position,
                        "name": item["name"],
                        "item": item["item"],
                    }
                    for position, item in enumerate(breadcrumb_items(ctx), start=1)
                ]

            if "ItemList" in node_types and str(node.get("@id", "")).endswith(
                "#checklist"
            ):
                visible_checklist = checklist_from_html(source)
                if visible_checklist:
                    node["itemListElement"] = [
                        {
                            "@type": "ListItem",
                            "position": index,
                            "name": value,
                        }
                        for index, value in enumerate(visible_checklist, start=1)
                    ]

        encoded = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
        if encoded != match.group(2):
            changes += 1
        return match.group(1) + encoded + match.group(3)

    return JSON_LD_RE.sub(replace_script, source), changes


def clean_pending_information(source: str) -> str:
    # 결과 보장 문구와 중복 원고가 집중된 legacy 블록만 정확한 다음 section
    # 경계까지 제거한다. 파일 끝까지 탐욕적으로 지우지 않는다.
    article_start = source.find('<section class="article-main">')
    if article_start >= 0:
        article_end = source.find(
            '<section class="generated-support-section">', article_start
        )
        if article_end < 0:
            raise ValueError("article-main 다음 generated-support-section 경계 없음")
        source = source[:article_start] + source[article_end:]
    source = re.sub(
        r'\s*<img\b(?=[^>]*class=["\'][^"\']*\bgenerated-hidden-image\b[^"\']*["\'])[^>]*>\s*',
        "\n",
        source,
        flags=re.I | re.S,
    )
    source = re.sub(
        r'\s*<details\b(?=[^>]*class=["\'][^"\']*\bwawa-fee-accordion\b[^"\']*["\'])[^>]*>.*?</details>\s*',
        '\n    <p class="wawa-fee-note">교습비 링크는 센터 제공 자료이며, 실제 개설 과목·횟수·금액은 상담 시 최종 확인해 주세요.</p>\n',
        source,
        flags=re.I | re.S,
    )
    source = source.replace("<strong>교육지원청</strong>", "<strong>등록 학원명</strong>")
    source = source.replace("<strong>등록번호</strong>", "<strong>교육청 등록번호</strong>")
    source = source.replace("주요 타깃학교(이외 학교도 수업 가능)", "참고 학교 정보")
    source = source.replace("초등 타깃학교", "초등 참고 학교")
    source = source.replace("중등 타깃학교", "중등 참고 학교")
    source = source.replace("고등 타깃학교", "고등 참고 학교")
    source = re.sub(
        r'\s*<p class="wawa-register-line">\s*<strong>운영등록일</strong>\s*:\s*정보 준비중\s*</p>',
        "",
        source,
        flags=re.I | re.S,
    )
    source = source.replace(
        '<span class="wawa-empty">수강 가능 학년 정보 준비중</span>',
        '<span class="wawa-empty">수강 가능 여부는 센터 상담 시 확인</span>',
    )
    source = source.replace(
        '<span class="wawa-empty">정보 준비중</span>',
        '<span class="wawa-empty">센터 제공 자료에서 학교 정보가 확인되지 않았습니다. 실제 학교별 수업·시험 대비 가능 여부는 상담 시 확인해 주세요.</span>',
    )
    source = source.replace(
        '<span class="wawa-empty">학교별 수업 가능 여부는 상담 시 확인</span>',
        '<span class="wawa-empty">센터 제공 자료에서 학교 정보가 확인되지 않았습니다. 실제 학교별 수업·시험 대비 가능 여부는 상담 시 확인해 주세요.</span>',
    )
    source = re.sub(
        r'<span\b[^>]*class=["\'][^"\']*\bwawa-pill\b[^"\']*["\'][^>]*>\s*'
        r'지역내 모든 고등학교 가능\s*</span>',
        '<span class="wawa-empty">센터 제공 자료에서 고등학교 정보가 확인되지 않았습니다. 실제 학교별 수업 가능 여부는 상담 시 확인해 주세요.</span>',
        source,
        flags=re.I,
    )
    source = source.replace(
        "교습비 안내 준비중",
        "센터 제공 교습비 자료가 확인되지 않아 실제 금액·횟수는 상담 시 확인해 주세요.",
    )
    source = source.replace("기록와", "기록과")
    source = re.sub(
        r"(초등|중등|고등)\s+영수\s+학습\s+상담",
        r"\1 영어·수학 학습 상담",
        source,
    )
    for old, new in (
        ("성적 상승", "학습 과정 개선"),
        ("성적상승", "학습 과정 개선"),
        ("성적 향상", "학습 과정 개선"),
        ("성적향상", "학습 과정 개선"),
        ("점수 상승", "취약 단원 보완"),
        ("점수상승", "취약 단원 보완"),
        ("점수 향상", "취약 단원 보완"),
        ("점수향상", "취약 단원 보완"),
    ):
        source = source.replace(old, new)
    source = re.sub(r"성적이\s*오르는", "학습 과정이 안정되는", source)
    source = re.sub(r"성적이\s*오르도록", "학습 과정이 안정되도록", source)
    source = re.sub(r"성적이\s*오르게", "학습 과정이 안정되게", source)
    source = re.sub(r"점수가\s*오르는", "취약 단원 대응이 나아지는", source)
    source = re.sub(r"점수가\s*오르도록", "취약 단원 대응이 나아지도록", source)
    source = re.sub(r"점수가\s*오르게", "취약 단원 대응이 나아지게", source)
    source = source.replace("성적을 올리", "학습 과정을 개선하")
    source = source.replace("점수를 올리", "취약 단원을 보완하")
    source = source.replace("~ 와와학습코칭센터", "와와학습코칭센터")
    return source


def process_page(
    path: Path,
    centers: dict[tuple[str, str, str], dict[str, str]],
    write: bool,
) -> tuple[bool, dict[str, Any]]:
    source = path.read_text(encoding="utf-8")
    ctx = context_for(path, source, centers)
    pairs = build_faq(ctx)
    updated = FAQ_SECTION_RE.sub(render_faq(ctx, pairs), source, count=1)
    updated = REVIEW_SECTION_RE.sub(render_guidance(ctx), updated, count=1)
    updated = clean_pending_information(updated)
    updated = update_visible_breadcrumb(updated, ctx)
    updated, json_changes = update_jsonld(updated, ctx, pairs)

    changed = updated != source
    if changed and write:
        path.write_text(updated, encoding="utf-8", newline="\n")
    return changed, {
        "title": ctx["title"],
        "center": ctx["center_name"],
        "faq_count": len(pairs),
        "json_changes": json_changes,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--write",
        action="store_true",
        help="기본값은 dry-run입니다. 실제 파일 수정 시 지정합니다.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="점검할 페이지 수를 제한합니다. 0은 전체입니다.",
    )
    args = parser.parse_args()

    centers = load_centers()
    pages = [
        path
        for path in sorted(NATIONAL_ROOT.rglob("index.html"))
        if is_detail_page(path)
    ]
    if args.limit:
        pages = pages[: args.limit]

    changed = 0
    failures: list[str] = []
    samples: list[dict[str, Any]] = []
    for path in pages:
        try:
            did_change, result = process_page(path, centers, args.write)
            changed += int(did_change)
            if len(samples) < 3:
                samples.append(result)
        except Exception as exc:
            failures.append(f"{path.relative_to(ROOT)}: {exc}")

    mode = "WRITE" if args.write else "DRY-RUN"
    print(f"mode={mode}")
    print(f"pages={len(pages)}")
    print(f"changed={changed}")
    print(f"failures={len(failures)}")
    for sample in samples:
        print("sample=" + json.dumps(sample, ensure_ascii=False))
    for failure in failures[:30]:
        print("ERROR " + failure)
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
