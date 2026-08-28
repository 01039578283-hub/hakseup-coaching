from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import re
from collections import defaultdict
from datetime import date
from pathlib import Path
from urllib.parse import quote

try:
    from source_copy_utils import (
        VERIFIED_SCHOOL_SOURCE_CORRECTIONS,
        normalize_location_note,
    )
except ModuleNotFoundError:  # package import
    from .source_copy_utils import (
        VERIFIED_SCHOOL_SOURCE_CORRECTIONS,
        normalize_location_note,
    )


ROOT = Path(__file__).resolve().parents[1]
DESKTOP = Path.home() / "Desktop"
COMMON = DESKTOP / "홈페이지 정리" / "참고자료" / "공통자료"
TITLE_FILE = DESKTOP / "와와학습코칭센터.txt"
CENTER_CSV = COMMON / "센터정보 정리.csv"
IMAGE_CSV = COMMON / "이미지링크.csv"
REPRESENTATIVE_CSV = COMMON / "대표 이미지 url.csv"
REVIEW_FILE = COMMON / "학부모 후기.txt"
TARGET = ROOT / "과목별학원" / "와와학습코칭센터"
BASE_URL = "https://xn--ru4bi8s1tac0p.kr"
SITE_NAME = "학습코칭 학원 안내"
PHONE = "010-3957-8283"
SMS_URL = "https://blogsms.net/01039578283"
FORM_URL = "https://docs.google.com/forms/d/e/1FAIpQLSdb2oE5Qk5YS0TfYDxyV1w-IOTkhkjOCmmpAKTI9FmqpVj6Yg/viewform"
TODAY = date.today().isoformat()


SUPPLEMENTAL = {
    "와와학습코칭센터 다산지금점": {
        "region": "경기", "city": "남양주시", "locality": "다산동",
        "address": "경기 남양주시 다산지금로 139 3층 308호",
        "map_file": "dasandong.jpg", "subjects": {"국어": "초1~고3", "영어": "초1~고3", "수학": "초1~고3", "과학": "초1~고3", "사회": "초1~고3"},
        "schools": ["다산한강초", "다산한강중", "가운고"],
        "registration_name": "다산지금점와와학습코칭학원",
        "registration_number": "구리남양주교육지원청 제4349-1호",
    },
    "와와학습코칭센터 별가람점": {
        "region": "경기", "city": "남양주시", "locality": "별내동",
        "address": "경기 남양주시 덕송1로55번길 20 503호", "map_file": "byeolnaedong.jpg",
        "subjects": {}, "schools": [],
    },
    "와와학습코칭센터 옥길스타점": {
        "region": "경기", "city": "부천시", "locality": "옥길동",
        "address": "경기 부천시 소사구 범안로 231-15 옥길중앙타워 201호", "map_file": "okgildong.jpg",
        "subjects": {}, "schools": [],
    },
    "와와학습코칭센터 송파위례점": {
        "region": "서울", "city": "송파구", "locality": "장지동",
        "address": "서울 송파구 위례광장로 188 아이온스퀘어 8층 816호", "map_file": "jangjidong.jpg",
        "subjects": {}, "schools": [],
    },
    "와와학습코칭센터 위례창곡점": {
        "region": "경기", "city": "성남시", "locality": "창곡동",
        "address": "경기 성남시 수정구 위례동로 141 우성메디피아 401호", "map_file": "changgokdong.jpg",
        "subjects": {}, "schools": [],
    },
}


def esc(value: object) -> str:
    return html.escape(str(value or ""), quote=True)


def compact(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def with_particle(value: str, consonant: str, vowel: str) -> str:
    last = next((char for char in reversed(value) if "가" <= char <= "힣"), "")
    has_batchim = bool(last) and (ord(last) - ord("가")) % 28 != 0
    return value + (consonant if has_batchim else vowel)


def unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def split_values(value: object) -> list[str]:
    text = compact(value)
    verified = VERIFIED_SCHOOL_SOURCE_CORRECTIONS.get(text)
    if verified:
        return list(verified)
    return [compact(item) for item in re.split(r"[,/\n]+", text) if compact(item)]


def short_name(title: str) -> str:
    return compact(title).removeprefix("와와학습코칭센터 ")


def absolute_url(*parts: str) -> str:
    path = "/" + "/".join(part.strip("/") for part in parts if part) + "/"
    return BASE_URL + quote(path, safe="/")


def deterministic_index(key: str, size: int, salt: str = "") -> int:
    return int(hashlib.sha256(f"{key}|{salt}".encode()).hexdigest()[:12], 16) % size


def load_titles() -> list[str]:
    if TITLE_FILE.exists():
        titles = [
            compact(line)
            for line in TITLE_FILE.read_text(encoding="utf-8-sig").splitlines()
            if compact(line)
        ]
        return unique(titles)

    hub = TARGET / "index.html"
    if hub.exists():
        source = hub.read_text(encoding="utf-8", errors="strict")
        match = re.search(
            r'<script\s+type="application/ld\+json">(.*?)</script>',
            source,
            re.I | re.S,
        )
        if match:
            data = json.loads(match.group(1))
            graph = data.get("@graph", []) if isinstance(data, dict) else []
            item_list = next(
                (
                    node
                    for node in graph
                    if isinstance(node, dict)
                    and node.get("@type") == "ItemList"
                    and str(node.get("@id", "")).endswith("#centers")
                ),
                {},
            )
            titles = [
                compact(item.get("name"))
                for item in item_list.get("itemListElement", [])
                if isinstance(item, dict) and compact(item.get("name"))
            ]
            if titles:
                return unique(titles)

    return [
        f"와와학습코칭센터 {path.name}"
        for path in sorted(TARGET.iterdir(), key=lambda value: value.name)
        if path.is_dir() and (path / "index.html").exists()
    ]


def load_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def load_representatives() -> list[str]:
    if REPRESENTATIVE_CSV.exists():
        source = REPRESENTATIVE_CSV.read_text(encoding="utf-8-sig", errors="ignore")
        return unique(
            re.findall(r'https://[^"\s>,]+?\.(?:jpg|jpeg|png|webp)', source, re.I)
        )
    recovered: list[str] = []
    for page in sorted(TARGET.glob("*/index.html")):
        source = page.read_text(encoding="utf-8", errors="ignore")
        match = re.search(
            r'<img\b[^>]*class="subject-hidden-representative"[^>]*src="([^"]+)"',
            source,
            re.I,
        )
        if match:
            recovered.append(match.group(1))
    return unique(recovered)


def load_reviews() -> list[str]:
    return unique([compact(line) for line in REVIEW_FILE.read_text(encoding="utf-8-sig").splitlines() if compact(line)])


def map_file_for(locality: str, images: dict[str, str]) -> str:
    value = images.get(locality, "")
    for candidate in unique([value, value.replace(" ", "-")]):
        if candidate and (ROOT / "assets" / "maps" / candidate).exists():
            return candidate
    return ""


def root_nav(active: str) -> str:
    links = [("홈", "/"), ("진단상담", "/진단상담/"), ("학습가이드", "/학습가이드/"), ("전국학원", "/전국학원/"), ("과목별학원", "/과목별학원/"), ("상담문의", "/상담문의/")]
    items = "".join(f'<a{" class=\"active\"" if label == active else ""} href="{href}">{label}</a>' for label, href in links)
    return f'''<header class="site-header"><nav class="nav" aria-label="주요 메뉴"><a class="brand" href="/"><span class="brand-mark">L</span><span>학습코칭</span></a><div class="nav-links">{items}</div><a class="nav-cta" href="/상담문의/">상담 신청</a></nav></header>'''


def footer() -> str:
    return f'''<footer class="site-footer"><div class="wrap footer-inner"><strong>학습코칭.kr</strong><div class="footer-links"><a href="/학습가이드/">학습가이드</a><a href="/전국학원/">전국학원</a><a href="/과목별학원/">과목별학원</a></div><div class="footer-contact"><span>상담 전화</span><a href="tel:{PHONE}">{PHONE}</a></div></div></footer><div class="floating-actions" aria-label="빠른 상담 메뉴"><a href="tel:{PHONE}" class="fab-call"><span class="fab-icon">&#128222;</span><span class="fab-text">전화문의</span></a><a href="{SMS_URL}" target="_blank" rel="noopener" class="fab-sms"><span class="fab-icon">&#128172;</span><span class="fab-text">문자문의</span></a><a href="{FORM_URL}" target="_blank" rel="noopener" class="fab-consult pulse-effect"><span class="fab-icon">&#128221;</span><span class="fab-text">상담신청</span></a></div>'''


def build_profiles() -> list[dict]:
    titles = load_titles()
    rows = load_csv(CENTER_CSV)
    images = {compact(row.get("제목")): compact(row.get("지도")) for row in load_csv(IMAGE_CSV)}
    reps = load_representatives()
    reviews = load_reviews()
    rep_order = sorted(reps, key=lambda value: hashlib.sha256(f"center-representative|{value}".encode()).hexdigest())
    review_order = sorted(reviews, key=lambda value: hashlib.sha256(f"center-review|{value}".encode()).hexdigest())
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        grouped[compact(row.get("센터명"))].append(row)

    profiles: list[dict] = []
    for title in titles:
        center_rows = grouped.get(title, [])
        if center_rows:
            first = center_rows[0]
            localities = unique([compact(row.get("근처 수업가능 동네")) for row in center_rows])
            primary = next((name for name in localities if map_file_for(name, images)), localities[0])
            schools: list[str] = []
            subjects: dict[str, str] = {}
            for row in center_rows:
                for key, value in row.items():
                    if key and "타깃학교" in key:
                        schools.extend(split_values(value))
            for subject in ("국어", "영어", "수학", "과학", "사회"):
                grade_values: list[str] = []
                for row in center_rows:
                    for key, value in row.items():
                        if key and "가능학년" in key and subject in key:
                            grade_values.extend(split_values(value))
                if grade_values:
                    subjects[subject] = ", ".join(unique(grade_values))
            profile = {
                "title": title,
                "slug": short_name(title),
                "region": compact(first.get("지역")), "city": compact(first.get("시or구")),
                "locality": primary, "localities": localities,
                "address": compact(first.get("센터 주소")), "location_note": normalize_location_note(first.get("위치안내")),
                "tuition_url": compact(first.get("센터 교습비")),
                "registration_name": compact(first.get("교육지원청명칭")),
                "registration_number": compact(first.get("교육지원청 등록번호")),
                "subjects": subjects, "schools": unique(schools),
                "map_file": map_file_for(primary, images),
            }
        else:
            if title not in SUPPLEMENTAL:
                raise KeyError(f"센터 자료를 찾을 수 없습니다: {title}")
            profile = {"title": title, "slug": short_name(title), "localities": [SUPPLEMENTAL[title]["locality"]], "location_note": "", "tuition_url": "", "registration_name": "", "registration_number": "", **SUPPLEMENTAL[title]}
        profile["representative"] = rep_order[len(profiles) % len(rep_order)] if rep_order else ""
        profile["review"] = review_order[len(profiles) % len(review_order)] if review_order else ""
        profiles.append(profile)
    if len(profiles) != 187 or len({item["slug"] for item in profiles}) != 187:
        raise ValueError(f"187개 고유 지점이 필요합니다: {len(profiles)}")
    return profiles


def choose(profile: dict, salt: str, options: list[str]) -> str:
    return options[deterministic_index(profile["title"], len(options), salt)]


def topic_form(value: str) -> str:
    last = ord(value[-1]) if value else 0
    has_final_consonant = 0xAC00 <= last <= 0xD7A3 and (last - 0xAC00) % 28 != 0
    return value + ("은" if has_final_consonant else "는")


def subject_names(profile: dict) -> str:
    names = list(profile["subjects"])
    return "·".join(names) if names else "희망 과목"


def grade_evidence(profile: dict) -> str:
    if not profile["subjects"]:
        return choose(profile, "grade-evidence-missing", [
            "공통자료에 지점별 가능 학년과 과목이 별도로 기재되지 않았습니다. 현재 학년과 희망 과목을 상담할 때 다시 확인해야 합니다.",
            "과목별 학년 범위를 확인할 원자료가 없어 임의로 채우지 않았습니다. 학생 정보와 희망 조건을 상담에서 직접 알려 주세요.",
            "제공 자료의 가능 학년 항목이 비어 있습니다. 현재 개설 과목과 시간표는 상담 날짜를 기준으로 확인해야 합니다.",
            "학년·과목 정보가 미기재 상태이므로 가능 여부를 단정하지 않습니다. 재학 학년과 필요한 과목을 먼저 전달해 주세요.",
            "원자료만으로는 수업 범위를 확인할 수 없습니다. 학생의 현재 진도와 희망 요일을 포함해 최신 운영 내용을 문의하세요.",
            "확인되지 않은 과목이나 학년을 페이지에 추가하지 않았습니다. 상담 시 실제 개설 상태를 대조해야 합니다.",
            "센터 제공 자료에 학년별 과목 범위가 없습니다. 원하는 과목, 학년, 가능한 시간을 함께 알려 주는 것이 좋습니다.",
            "페이지 근거 자료에는 수업 학년이 적혀 있지 않습니다. 미기재가 수업 불가를 뜻하지 않으므로 별도 확인이 필요합니다.",
            "현재 자료에서 가능 학년을 확정할 수 없어 빈 항목으로 유지했습니다. 최신 학년·과목 안내는 상담으로 확인하세요.",
            "과목 운영 범위를 뒷받침하는 기록이 없어 추정 안내를 하지 않습니다. 학생 조건에 맞춰 직접 문의해 주세요.",
            "공통자료에 학년 정보가 제공되지 않았습니다. 학교, 학년, 희망 과목과 시간을 상담할 때 구체적으로 전달하세요.",
            "수업 가능 학년에 대한 원자료가 비어 있습니다. 현재 반 편성과 과목 개설 여부는 페이지 밖의 상담 확인 사항입니다.",
        ])
    items = [f"{topic_form(subject)} {grades}" for subject, grades in profile["subjects"].items()]
    evidence = "; ".join(items)
    options = [
        f"공통자료 기준 {evidence}로 기재되어 있습니다. 현재 개설 여부와 시간은 상담 시 다시 확인하세요.",
        f"과목별 학년 표시는 {evidence}입니다. 학생의 희망 요일과 진도를 함께 전달한 뒤 실제 운영 범위를 확인해야 합니다.",
        f"센터 제공 자료에는 {evidence}로 정리되어 있습니다. 이 표시는 반 편성이나 좌석 가능 여부를 뜻하지 않습니다.",
        f"확인된 가능 학년 자료는 {evidence}입니다. 과목별 일정은 변경될 수 있어 상담 날짜를 기준으로 대조하세요.",
        f"페이지에 옮긴 학년 근거는 {evidence}입니다. 재학 학년이 보여도 실제 시간표와 개설 상태는 별도 확인이 필요합니다.",
        f"원자료가 제시한 범위는 {evidence}입니다. 학생의 현재 진도와 희망 과목을 알려 주고 최종 가능 여부를 확인하세요.",
        f"수업 학년 항목은 {evidence}로 확인됩니다. 자료에 없는 범위를 임의로 늘리지 않았으며 최신 운영은 상담에서 확인합니다.",
        f"공통자료의 과목별 내용은 {evidence}입니다. 학년 표시와 실제 반 구성은 서로 다른 정보로 살펴봐야 합니다.",
        f"현재 페이지가 가진 학년 정보는 {evidence}입니다. 원하는 시간대의 수업 여부는 이 자료만으로 확정할 수 없습니다.",
        f"센터 자료에서 읽을 수 있는 범위는 {evidence}입니다. 상담 전 학년·과목·요일을 함께 정리해 최신 상태를 문의하세요.",
        f"가능 학년 근거를 옮기면 {evidence}입니다. 과목별 시작 시점과 시간표는 학생 조건에 따라 다시 확인해야 합니다.",
        f"확인 가능한 과목·학년은 {evidence}입니다. 이는 제공 자료의 기록이며 현재 등록 가능성을 보장하는 문구가 아닙니다.",
    ]
    return choose(profile, "grade-evidence", options)


def school_evidence(profile: dict) -> str:
    schools = profile["schools"]
    if not schools:
        return choose(profile, "school-evidence-missing", [
            "공통자료에는 개별 학교명이 기재되어 있지 않습니다. 재학 학교와 실제 시험 범위표를 상담 자료로 직접 준비해 주세요.",
            "학교 참고 항목이 비어 있어 이름을 추정해 넣지 않았습니다. 학생이 받은 범위표와 학교 공지를 직접 가져가세요.",
            "원자료에서 특정 학교를 확인하지 못했습니다. 재학 학교, 학년, 시험 일정을 상담 때 정확히 알려 주는 것이 좋습니다.",
            "개별 학교 목록이 제공되지 않았습니다. 학교 정보의 미기재와 실제 수업 가능 여부는 별개의 항목입니다.",
            "확인된 학교명이 없어 페이지에 추가하지 않았습니다. 학생의 최신 학교 자료로 내신 상담 범위를 대조하세요.",
            "센터 자료의 학교 칸이 비어 있습니다. 재학 학교와 과목별 시험 범위를 준비해 현재 가능 여부를 문의하세요.",
            "학교 근거 자료가 없어 임의의 인근 학교를 표시하지 않습니다. 실제 공지와 교재 진도를 상담 자료로 사용하세요.",
            "페이지에서 학교명을 확정할 수 없습니다. 학생이 받은 수행평가 일정과 시험 범위표를 함께 제시해 주세요.",
            "공통자료에 학교 정보가 미기재된 지점입니다. 이는 수업 불가를 뜻하지 않으므로 상담으로 별도 확인해야 합니다.",
            "참고할 개별 학교명이 없습니다. 상담 시 학교·학년·희망 과목을 전달하고 내신 준비 가능 범위를 확인하세요.",
            "원자료에 학교 목록이 없어 빈 상태를 유지했습니다. 확인되지 않은 이름을 넣기보다 학생 자료를 우선해야 합니다.",
            "학교 참고 정보가 제공되지 않았습니다. 실제 시험 범위와 학교 일정을 준비해 상담 내용의 기준으로 삼으세요.",
        ])
    preview = ", ".join(schools[:6])
    remainder = len(schools) - min(len(schools), 6)
    suffix = f" 외 {remainder}곳" if remainder else ""
    options = [
        f"학교 참고 자료에는 {preview}{suffix}, 총 {len(schools)}곳이 기재되어 있습니다. 학교별 실제 범위는 학생이 받은 자료로 다시 대조해야 합니다.",
        f"공통자료에서 확인되는 학교는 {preview}{suffix}이며 전체 {len(schools)}곳입니다. 목록은 상담 준비용이고 시간표를 뜻하지 않습니다.",
        f"센터 자료의 학교 항목은 {preview}{suffix}, 합계 {len(schools)}곳입니다. 현재 시험 일정과 학년 공지를 최종 기준으로 확인하세요.",
        f"기재된 참고 학교 {len(schools)}곳 가운데 {preview}{suffix}을 확인할 수 있습니다. 실제 내신 범위는 학생 자료가 우선합니다.",
        f"학교 대조용 원자료에는 {preview}{suffix} 등 {len(schools)}곳이 있습니다. 이 이름만으로 수업 가능 여부를 확정하지 마세요.",
        f"확인된 학교 목록은 모두 {len(schools)}곳이며 {preview}{suffix}이 포함됩니다. 상담에는 실제 범위표와 교재를 함께 준비하세요.",
        f"페이지 근거 자료에 {preview}{suffix}, 총 {len(schools)}곳이 적혀 있습니다. 학교별 학년·시기 차이는 별도로 확인해야 합니다.",
        f"공통자료의 학교 수는 {len(schools)}곳이고 앞선 항목은 {preview}{suffix}입니다. 최신 학교 공지를 함께 대조해 주세요.",
        f"상담 참고 학교로 {preview}{suffix} 등 {len(schools)}곳이 기재되어 있습니다. 등록 가능성과 실제 시험 범위는 다른 정보입니다.",
        f"원자료에서 읽을 수 있는 학교는 {preview}{suffix}, 전체 {len(schools)}곳입니다. 학생의 재학 학년 자료를 기준으로 활용하세요.",
        f"학교 정보는 {preview}{suffix}을 포함해 {len(schools)}곳입니다. 이름이 같더라도 현재 범위와 일정은 학생 자료로 확인해야 합니다.",
        f"확인된 {len(schools)}곳의 학교 가운데 {preview}{suffix}이 표시됩니다. 목록에 없는 최신 내용은 상담 때 직접 전달해 주세요.",
    ]
    return choose(profile, "school-evidence", options)


def location_evidence(profile: dict) -> str:
    address = profile["address"] or "센터 제공 주소 미기재"
    note = profile.get("location_note", "")
    if note:
        options = [
            f"센터 제공 주소는 {address}입니다. 위치 안내에는 ‘{note}’라고 적혀 있으므로 방문 전에 상담 시간과 출입 동선을 함께 확인하세요.",
            f"방문 주소는 {address}이며 제공된 길 안내는 ‘{note}’입니다. 일정과 건물 출입 방법은 출발 전에 다시 확인해 주세요.",
            f"자료에 기록된 위치는 {address}입니다. ‘{note}’라는 설명을 지도와 함께 대조하고 상담 가능 시간을 확인하세요.",
            f"{address}로 안내된 지점입니다. 센터 자료의 ‘{note}’ 문구를 참고하되 실제 방문 동선은 최신 지도에서 다시 살펴보세요.",
            f"주소 항목에는 {address}가 기재되어 있습니다. 추가 안내 ‘{note}’를 확인한 뒤 층수와 예약 시간을 함께 점검하세요.",
            f"센터 위치 근거는 {address}이고 세부 설명은 ‘{note}’입니다. 방문 전 건물명과 상담 일정을 한 번 더 확인하는 것이 좋습니다.",
            f"제공 자료상 주소는 {address}입니다. 길 찾기 메모 ‘{note}’와 현재 지도를 비교해 이동 경로를 준비하세요.",
            f"{address}에 있는 지점으로 안내됩니다. 위치 설명에는 ‘{note}’라고 되어 있어 출발 전에 정확한 출입구와 시간을 확인해야 합니다.",
            f"방문할 곳은 자료 기준 {address}입니다. ‘{note}’라는 안내가 있으므로 건물과 층 정보를 지도에서 함께 대조하세요.",
            f"센터가 제공한 주소는 {address}, 위치 메모는 ‘{note}’입니다. 상담 예약 뒤 실제 찾아가는 방법을 다시 확인해 주세요.",
            f"페이지 주소 정보는 {address}입니다. 현장 안내 ‘{note}’를 참고하고 변경 가능성이 있는 방문 시간은 별도로 문의하세요.",
            f"자료에서 확인한 지점 위치는 {address}입니다. 세부 문구 ‘{note}’를 바탕으로 이동하되 최신 건물 정보를 함께 살펴보세요.",
        ]
        return choose(profile, "location-evidence", options)
    options = [
        f"센터 제공 주소는 {address}입니다. 별도 위치 설명이 없어 방문 전에 상담 시간과 건물명·층수를 다시 확인하는 편이 안전합니다.",
        f"자료에 기재된 방문 주소는 {address}입니다. 길 안내 문구가 없으므로 지도와 건물 정보를 출발 전에 대조하세요.",
        f"주소 항목은 {address}로 확인됩니다. 상세 동선이 제공되지 않아 상담 예약 뒤 출입구와 층수를 확인하는 것이 좋습니다.",
        f"페이지가 가진 위치 정보는 {address}입니다. 별도 안내가 없으니 방문 시간과 정확한 건물 위치를 다시 문의하세요.",
        f"센터 자료에는 {address}가 주소로 적혀 있습니다. 현장 설명이 없는 경우 최신 지도와 상담 일정을 함께 확인해야 합니다.",
        f"방문 근거 주소는 {address}입니다. 추가 길 찾기 정보가 없어 건물명, 층, 출입 방법을 사전에 확인해 주세요.",
        f"{address}로 안내된 지점입니다. 세부 위치 문구는 없으므로 예약 후 찾아가는 방법을 다시 점검하는 편이 안전합니다.",
        f"제공된 위치는 {address}입니다. 별도의 이동 안내가 없어 출발 전에 지도와 실제 상담 가능 시간을 확인하세요.",
        f"센터 주소 자료는 {address}로 확인됩니다. 건물 내 동선과 방문 일정은 페이지 정보만으로 확정하지 마세요.",
        f"자료상 지점 주소는 {address}입니다. 위치 설명이 비어 있어 최신 건물 정보와 층수를 별도로 대조해야 합니다.",
        f"방문할 주소로 {address}가 기재되어 있습니다. 길 안내가 없는 만큼 상담 예약 때 정확한 출입 정보를 물어보세요.",
        f"주소는 센터 제공 자료 기준 {address}입니다. 추가 설명이 없어 지도 확인과 방문 시간 확인을 함께 진행하세요.",
    ]
    return choose(profile, "location-evidence-missing", options)


def overview_copy(profile: dict) -> str:
    title = profile["title"]
    local = profile["locality"]
    city = profile["city"]
    subjects = subject_names(profile)
    localities = "·".join(profile["localities"])
    schools = len(profile["schools"])
    options = [
        f"{title} 자료를 확인할 때는 {localities} 안내 범위와 실제 주소를 먼저 맞춰 보세요. 이어서 {subjects} 가능 학년, 학교 참고 정보 {schools}건을 학생 자료와 대조하면 상담 질문을 구체화할 수 있습니다.",
        f"{city}에서 {title} 방문을 준비한다면 주소와 위치 설명을 먼저 확인한 뒤 {subjects} 학년 범위를 살펴보는 순서가 좋습니다. 학교 정보는 등록 가능 여부가 아니라 시험 자료를 준비하기 위한 참고 항목입니다.",
        f"이 페이지는 {local} 학생의 상담 준비를 위해 센터 주소, {subjects} 학년 정보, 학교 참고 자료를 서로 구분해 보여 줍니다. 각 항목은 확인 시점이 다를 수 있으므로 최종 운영 여부는 상담 때 다시 확인하세요.",
        f"{title}에 관한 핵심 자료는 위치, 과목별 학년, 학교 참고 정보의 세 묶음으로 나뉩니다. {localities}에서 상담을 준비할 때 현재 교재와 시험 범위를 함께 놓고 필요한 항목부터 확인해 보세요.",
        f"먼저 {title}의 주소가 방문하려는 지점과 일치하는지 살펴보고, 다음으로 {subjects} 가능 학년을 확인하세요. {local} 학교 자료는 학생의 실제 범위표와 비교할 때 활용하는 참고 정보입니다.",
        f"{local}에서 학습 상담을 알아볼 때 지점 이름만 비교하면 필요한 정보를 놓치기 쉽습니다. {title}의 주소, 과목별 학년, 기재된 학교 수 {schools}건을 차례로 확인해 상담 준비표를 만들 수 있습니다.",
        f"{title} 페이지는 {city}의 센터 위치와 {subjects} 안내 범위를 한곳에 정리합니다. 재학 학교와 최근 답안을 준비한 뒤 표시된 자료와 다른 점을 상담 질문으로 남겨 두세요.",
        f"{localities} 안내와 연결된 {title}의 자료를 주소·수업 범위·학교 정보 순서로 정리했습니다. 실제 반 편성이나 시간표를 뜻하는 정보는 아니므로 현재 운영 내용은 별도로 확인해야 합니다.",
        f"상담 전에는 {title}의 위치를 먼저 확정하고 {subjects} 가운데 필요한 과목의 학년 표시를 찾아보세요. 이후 {local} 학생이 받은 학교 시험 자료를 참고 학교 목록과 함께 확인하면 됩니다.",
        f"{city} {title} 자료에는 방문 주소와 과목별 가능 학년, 학교 참고 항목이 포함되어 있습니다. 이 세 정보를 학생의 현재 학년·과목·시험 일정과 나란히 비교해 질문 순서를 정해 보세요.",
        f"{with_particle(title, '을', '를')} 검토하는 출발점은 {localities} 지역 표시와 실제 주소의 일치 여부입니다. 그다음 {subjects} 학년 범위와 학교 자료를 확인하면 상담에서 꼭 물어볼 내용을 빠르게 추릴 수 있습니다.",
        f"{local} 학부모가 {title} 상담을 준비할 때 필요한 확인 항목을 위치, 과목, 학년, 학교 자료로 나누었습니다. 자료에 없는 운영 내용은 추정하지 않고 상담 시점에 확인하는 것이 좋습니다.",
    ]
    return choose(profile, "overview", options)


def context_cards(profile: dict) -> str:
    subjects = subject_names(profile)
    school_heading = (
        f"{profile['schools'][0]} 등 학교 자료"
        if profile["schools"]
        else "재학 학교 자료 준비"
    )
    cards = [
        ("01", f"{profile['city']} 방문 정보", location_evidence(profile)),
        ("02", f"{subjects} 학년 근거", grade_evidence(profile)),
        ("03", school_heading, school_evidence(profile)),
    ]
    return "".join(
        f'<article><span>{number}</span><h3>{esc(heading)}</h3><p>{esc(body)}</p></article>'
        for number, heading, body in cards
    )


def learning_flow(profile: dict) -> list[tuple[str, str]]:
    local = profile["locality"]
    title = profile["title"]
    subjects = subject_names(profile)
    school = profile["schools"][0] if profile["schools"] else "재학 학교"
    diagnostic = choose(profile, "flow-diagnostic", [
        f"{local} 학생의 최근 시험지를 펼쳐 {subjects} 중 점수 손실이 큰 과목과 반복 오답을 먼저 표시합니다.",
        f"현재 교재, {school} 시험 범위표, 최근 답안을 나란히 놓고 개념 부족과 풀이 실수를 구분해 질문합니다.",
        f"상담에서는 공부 시간이 부족한지, 알고도 틀리는지, 단원 이해가 비어 있는지를 최근 기록으로 구분해 보세요.",
        f"{title} 상담 전 일주일 공부 기록을 모아 과목별 시작 시간·완료량·오답 수를 확인하면 진단의 출발점이 선명해집니다.",
        f"{subjects} 답안에서 틀린 문제만 모으기보다 문제를 읽지 못한 경우와 개념을 모른 경우를 따로 표시해 가져가세요.",
        f"{local} 학생이 사용하는 교재 목차에 완료·미완료 단원을 표시하고 최근 시험 결과와 비교하면 우선순위를 정하기 쉽습니다.",
        f"최근 두 번의 평가 자료를 비교해 계속 틀리는 유형과 이번에 처음 틀린 유형을 나눈 뒤 상담 질문을 작성합니다.",
        f"{school} 일정과 현재 진도를 대조해 시험 전까지 남은 기간, 필요한 단원, 실제 공부 가능 시간을 먼저 계산해 보세요.",
        f"학생이 어려웠다고 말한 부분과 답안에서 실제로 막힌 지점을 따로 기록하면 {subjects} 학습 상태를 더 정확히 설명할 수 있습니다.",
        f"상담 자료에는 점수뿐 아니라 풀이 흔적과 빈 문제, 고친 횟수를 포함해 {local} 학생의 학습 행동을 함께 확인하세요.",
        f"진단 질문은 ‘몇 점인가’에서 끝내지 말고 어떤 단원에서 왜 멈췄는지, 다시 풀었을 때 해결됐는지까지 이어가야 합니다.",
        f"{title}에 전달할 최근 자료를 과목·단원·오답 원인으로 구분하면 현재 필요한 설명과 연습을 혼동하지 않게 됩니다.",
    ])
    planning = choose(profile, "flow-planning", [
        f"진단에서 확인한 우선 단원을 주간 계획에 넣고 {subjects}마다 분량과 완료 기준을 다르게 적습니다.",
        f"{local} 학생의 학교 일정부터 고정한 뒤 실제 공부 가능한 날에 개념 확인·문제 풀이·복습을 나누어 배치합니다.",
        f"계획표에는 ‘수학 공부’처럼 넓게 쓰지 말고 교재명, 쪽수, 문제 수, 확인할 오답까지 기록해 실행 여부를 판단합니다.",
        f"처음부터 많은 양을 배정하기보다 지난주 완료율을 기준으로 다음 분량을 조정하고 미완료 이유를 한 줄로 남깁니다.",
        f"{school} 평가 일정이 있다면 역산한 주차별 목표와 평소 학습 목표를 분리해 과도한 계획을 피합니다.",
        f"{subjects} 가운데 시급한 과목과 유지할 과목을 나누고 하루에 실제로 끝낼 수 있는 분량을 먼저 정해 보세요.",
        f"주간 계획은 시작 시각보다 완료 조건을 분명히 적고, 끝내지 못한 항목은 다음 날로 옮기기 전에 원인을 확인합니다.",
        f"학생이 스스로 확인할 항목과 상담에서 점검받을 항목을 분리하면 계획표가 단순한 할 일 목록으로 끝나지 않습니다.",
        f"{title} 상담에서는 학교 일정, 현재 진도, 가정 학습 시간을 함께 제시해 실행 가능한 주간 순서를 비교해 보세요.",
        f"과목마다 필요한 반복 간격이 다르므로 새 내용, 당일 복습, 누적 확인을 서로 다른 칸에 배치하는 방법을 검토합니다.",
        f"계획을 세운 날과 실제 완료한 날을 함께 기록하면 {local} 학생에게 무리한 분량과 적정 분량을 구분할 수 있습니다.",
        f"한 주의 필수 과제와 여유가 있을 때 할 과제를 나누고, 시험 일정이 바뀌면 우선순위부터 다시 조정합니다.",
    ])
    relearning = choose(profile, "flow-relearning", [
        f"오답은 정답을 옮겨 적는 것으로 끝내지 않고 {subjects}별 원인을 표시한 뒤 일정 간격을 두고 다시 풉니다.",
        f"틀린 문제 옆에 개념 부족·조건 누락·계산 실수·시간 부족을 표시하고 원인에 맞는 재확인 날짜를 정합니다.",
        f"설명을 들은 직후의 재풀이와 며칠 뒤 빈 종이 재풀이를 구분해야 실제로 혼자 해결할 수 있는지 확인할 수 있습니다.",
        f"{school} 시험 준비에서는 같은 단원 안에서 형태가 달라진 문제도 풀어 보며 암기한 풀이인지 이해한 풀이인지 점검합니다.",
        f"{local} 학생의 반복 실수는 문제 번호보다 원인별로 모아 보고, 같은 원인이 다시 나타났는지 주 단위로 확인합니다.",
        f"맞힌 문제라도 오래 걸렸거나 힌트를 사용했다면 재학습 목록에 남겨 다음 확인에서 혼자 해결해 보도록 합니다.",
        f"{subjects} 오답 기록에는 처음 풀이, 수정 과정, 다시 푼 날짜를 남겨 변화가 있었는지 비교할 수 있게 합니다.",
        f"개념을 다시 읽은 뒤 곧바로 동일 문제만 풀지 말고 유사 문제와 혼합 문제를 거쳐 적용 여부를 확인합니다.",
        f"재학습 우선순위는 자주 틀린 문제, 다음 단원과 연결되는 개념, 시험 범위에 포함된 항목 순으로 검토합니다.",
        f"{title} 상담에 오답 노트를 가져갈 때는 많이 적는 것보다 다시 풀어 맞힌 기록이 있는지를 함께 보여 주세요.",
        f"한 번 고친 문제는 완료로 지우지 말고 다음 주 확인 목록에 남겨 장기 기억으로 이어지는지 살펴봅니다.",
        f"틀린 이유를 학생의 말로 짧게 설명하고 다음 풀이에서 바꿀 행동을 적으면 같은 실수를 발견하기 쉬워집니다.",
    ])
    return [
        ("상담 자료로 상태 구분", diagnostic),
        ("실행 가능한 주간 계획", planning),
        ("원인별 오답 재확인", relearning),
    ]


def flow_cards(profile: dict) -> str:
    return "".join(
        f'<article><span>{index:02d}</span><h3>{esc(heading)}</h3><p>{esc(body)}</p></article>'
        for index, (heading, body) in enumerate(learning_flow(profile), 1)
    )


def school_intro(profile: dict) -> str:
    local = profile["locality"]
    title = profile["title"]
    options = [
        f"{title} 자료에 기재된 학교를 상담 준비용으로 정리했습니다. {local} 학생이 받은 시험 범위와 학년 공지를 최종 기준으로 비교하세요.",
        f"아래 학교명은 수업이나 성적 결과를 보장하는 목록이 아닙니다. 재학 학교가 보인다면 실제 범위표와 일정표를 함께 준비해 상담 질문에 활용하세요.",
        f"학교 참고 정보는 {local} 내신 계획을 자동으로 정하는 기준이 아닙니다. 같은 학교도 학년과 시기에 따라 범위가 달라 학생 자료를 우선해야 합니다.",
        f"공통자료에서 {title}와 연결된 학교명만 표시했습니다. 목록에 없거나 이름이 달라진 경우에는 상담 시 재학 학교를 직접 알려 주세요.",
        f"표시된 학교는 센터 자료의 참고 항목입니다. 시험 대비 순서는 학생이 받은 교과 진도표, 수행평가 일정, 실제 시험 범위를 확인한 뒤 정해야 합니다.",
        f"{local} 학교 정보를 볼 때는 학교명보다 현재 학년의 범위와 교재를 먼저 확인하세요. 아래 목록은 상담 자료를 빠뜨리지 않기 위한 대조용입니다.",
        f"{title} 관련 학교 자료를 원문에 기재된 범위에서만 보여 줍니다. 수업 가능 여부와 시간표는 이 목록만으로 판단하지 말고 별도로 확인해야 합니다.",
        f"학교별 준비 내용은 같은 지역 안에서도 다를 수 있습니다. 아래 이름을 확인한 뒤 학생이 실제로 받은 공지와 답안을 상담 자료로 가져가세요.",
        f"학교명은 지역 상담의 맥락을 확인하기 위한 참고 정보입니다. {local} 학생의 현재 시험 일정과 과목별 범위가 페이지 목록보다 우선합니다.",
        f"이 목록은 공통자료에 있는 학교명을 옮긴 것입니다. 학교가 표시되어도 학년·과목별 실제 운영 여부는 {title} 상담에서 다시 확인하세요.",
        f"내신 준비는 학교 이름만으로 동일하게 구성할 수 없습니다. 아래 학교 자료와 학생의 최근 시험지를 함께 비교해 필요한 과목과 단원을 정리하세요.",
        f"{title} 페이지에서는 확인된 학교만 제시하고 누락된 이름을 추정해 추가하지 않습니다. 재학 학교 정보가 다르면 상담 때 최신 내용을 전달해 주세요.",
    ]
    return choose(profile, "school-intro", options)


def scenario_note(profile: dict) -> str:
    options = [
        "공통 상담 자료에서 학부모가 점검할 상황을 재구성했습니다. 특정 학생의 실제 후기나 성적 향상을 보장하는 문장이 아닙니다.",
        "상담 준비 과정을 설명하기 위한 예시이며 개인의 이용 경험을 인증한 후기가 아닙니다. 학생마다 필요한 순서는 달라질 수 있습니다.",
        "학부모 질문을 구체화하기 위한 가상 상황입니다. 실제 수업 결과·등급 변화·합격을 약속하거나 증명하지 않습니다.",
        "센터 상담에서 확인할 자료를 보여 주기 위해 구성한 사례입니다. 특정 학생의 성과나 재원 경험으로 해석해서는 안 됩니다.",
        "공통 학습관리 자료를 토대로 만든 설명용 장면입니다. 개인 후기 인용이나 결과 보증에 해당하지 않습니다.",
        "상담 전에 살펴볼 행동과 기록을 예시로 정리했습니다. 실제 학생의 신원·성적·수강 결과를 담은 내용은 아닙니다.",
        "학습 문제를 설명하는 방법을 돕기 위한 예시 문장입니다. 센터별 실적 또는 특정 학부모의 체험을 주장하지 않습니다.",
        "학생 상태를 상담에서 어떻게 전달할지 보여 주는 재구성 사례입니다. 성적 변화는 개인별 조건에 따라 달라질 수 있습니다.",
        "상담 질문의 맥락을 위한 가상 시나리오이며 실제 후기나 광고성 성과 사례가 아닙니다.",
        "학부모가 준비할 자료를 이해하도록 만든 예시입니다. 특정 결과의 재현 가능성이나 수업 효과를 보장하지 않습니다.",
        "공통자료의 상담 주제를 바탕으로 편집한 상황입니다. 실제 이용자 발언이나 센터의 성과 증빙으로 사용하지 않습니다.",
        "학습 기록을 설명하는 연습용 사례로 구성했습니다. 학생 개인의 실제 경험 또는 성적 결과를 나타내지 않습니다.",
    ]
    return choose(profile, "scenario-note", options)


def consult_copy(profile: dict) -> tuple[str, str]:
    local = profile["locality"]
    subjects = subject_names(profile)
    options = [
        (f"{local} 상담 자료를 한 번에 준비하세요", f"최근 시험지, 현재 교재, 학교 일정, {subjects} 반복 오답을 모으면 확인 순서를 빠르게 정할 수 있습니다."),
        ("점수보다 풀이 기록을 먼저 챙기세요", f"{local} 학생이 어디에서 멈추는지 보여 주는 답안과 주간 공부 기록이 구체적인 상담에 도움이 됩니다."),
        ("학교 범위와 현재 진도를 함께 확인하세요", f"{subjects} 교재 목차에 현재 위치를 표시하고 실제 시험 범위표를 준비해 차이를 질문하세요."),
        ("완료하지 못한 계획도 중요한 자료입니다", f"{local} 학생의 미완료 항목과 이유를 지우지 말고 가져가면 실행 가능한 분량을 검토하기 좋습니다."),
        ("오답은 틀린 이유까지 표시해 주세요", f"{subjects} 문제를 개념 부족·조건 누락·실수로 나누면 재학습 우선순위를 비교하기 쉽습니다."),
        ("상담 전에 세 가지 질문을 적어 보세요", f"현재 가장 어려운 과목, 가능한 공부 시간, {local} 학교 일정을 정리하면 필요한 안내를 놓치지 않습니다."),
        ("최근 두 번의 평가 자료를 비교하세요", f"{subjects}에서 반복된 실수와 새로 생긴 어려움을 나누어 표시하면 변화의 원인을 설명하기 쉽습니다."),
        ("학생이 실제로 쓰는 자료를 가져오세요", f"새 문제집보다 현재 교재와 답안, 학교 공지, {local} 학생의 공부 기록이 상담 기준을 구체적으로 만듭니다."),
        ("희망 시간과 주간 일정을 미리 정리하세요", f"{subjects} 학습에 쓸 수 있는 요일과 시간을 알려 주면 과도하지 않은 계획을 비교할 수 있습니다."),
        ("재학 학교와 학년을 정확히 알려 주세요", f"{local} 학교 자료는 학년과 시기별로 달라 실제 범위표를 함께 확인해야 합니다."),
        ("무엇을 얼마나 했는지 기록해 오세요", f"{subjects}별 공부 시간보다 완료한 단원·문제 수·재풀이 여부를 적으면 실행 상태를 파악하기 좋습니다."),
        ("상담 질문을 과목별로 나누어 준비하세요", f"{local} 학생의 현재 진도와 반복 오답을 {subjects}별로 구분하면 확인할 내용을 빠뜨리지 않습니다."),
    ]
    return options[deterministic_index(profile["title"], len(options), "consult")]


def meta_description(profile: dict) -> str:
    local = profile["locality"]
    options = [
        f"{profile['title']}의 주소, 수업 가능 학년과 과목, 인근 학교, 교습비 확인 링크를 정리했습니다. {local} 학생의 상담 전 준비사항과 학습관리 흐름도 확인하세요.",
        f"{local} {profile['title']} 방문 전 주소와 가능 학년·과목, 학교 참고 정보, 교습비 안내를 확인하세요. 진단·플래너·오답 재학습 상담 기준을 함께 안내합니다.",
        f"{profile['title']} 센터 정보와 수업 대상, 가능 과목, 인근 학교를 한눈에 확인하세요. {local} 학부모가 상담 전에 준비할 자료와 확인 질문도 정리했습니다.",
        f"{profile['city']} {profile['title']}의 위치와 {subject_names(profile)} 가능 학년, 학교 참고 자료를 확인하세요. {local} 상담에 가져갈 시험지·교재·오답 기록도 안내합니다.",
        f"{profile['title']} 방문을 준비하는 {local} 학생을 위해 주소, 과목별 학년, 학교 정보와 상담 질문을 분리해 정리했습니다. 현재 운영 내용은 상담 시 확인하세요.",
        f"{local} {profile['title']}의 주소와 위치 설명, {subject_names(profile)} 학년 정보, 학교 참고 목록을 살펴보고 최근 답안과 학습 기록을 준비하세요.",
        f"{profile['title']}에 관한 센터 제공 자료를 위치·과목·학년·학교 기준으로 확인하세요. {local} 학생의 상담 전 점검 순서와 오답 재확인 방법도 담았습니다.",
        f"{profile['city']}에서 {with_particle(profile['title'], '을', '를')} 찾는 학부모를 위해 실제 주소와 가능 학년·과목, 학교 자료, 상담 준비 체크리스트를 한 페이지에 정리했습니다.",
        f"{profile['title']}의 {local} 안내 범위, 센터 주소, {subject_names(profile)} 정보와 학교 참고 항목을 확인하고 시험 범위·교재·주간 계획을 함께 준비하세요.",
        f"{local} 학습 상담 전 {profile['title']}의 위치와 과목별 학년, 학교 참고 정보를 확인하세요. 페이지에 없는 반 편성·시간표는 상담 시 다시 확인해야 합니다.",
        f"{profile['title']} 센터 자료에서 확인되는 주소, {subject_names(profile)} 학년 범위와 학교 정보를 정리했습니다. {local} 학생의 최근 시험지와 오답도 함께 준비하세요.",
        f"{profile['city']} {local}의 {profile['title']} 정보를 찾는 분을 위해 위치·가능 과목·학년·학교 자료와 상담 전 확인사항을 구분해 안내합니다.",
    ]
    return options[deterministic_index(profile["title"], len(options), "meta")]


def page_faq(profile: dict) -> list[tuple[str, str]]:
    title, local = profile["title"], profile["locality"]
    subjects = "·".join(profile["subjects"].keys()) if profile["subjects"] else "수업 과목"
    grades = "; ".join(f"{key} {value}" for key, value in profile["subjects"].items())
    schools = ", ".join(profile["schools"][:6])
    prep_questions = [
        f"{title} 상담 전에 꼭 가져갈 자료는 무엇인가요?",
        f"{local} 학생이 상담을 준비할 때 무엇부터 챙기면 되나요?",
        f"{title}에 학습 상태를 설명하려면 어떤 기록이 필요한가요?",
        f"처음 {title} 상담을 받을 때 준비할 항목이 있나요?",
        f"{local} 학습 상담 전에 시험지와 교재를 준비해야 하나요?",
        f"{title} 상담 질문을 구체화하는 데 필요한 자료는 무엇인가요?",
        f"현재 공부 상태를 {title}에 정확히 전달하려면 어떻게 하나요?",
        f"{local} 학생의 최근 학습 흐름을 보여 줄 자료는 무엇인가요?",
        f"{title} 방문 전에 정리해 둘 학습 정보가 있나요?",
        f"상담 시간을 효율적으로 쓰려면 어떤 자료를 모아야 하나요?",
        f"{title} 상담용 체크리스트에는 무엇을 넣어야 하나요?",
        f"{local} 학생의 어려움을 설명할 때 점수 외에 무엇이 필요한가요?",
    ]
    prep_answers = [
        f"최근 시험지, 현재 교재, 학교 범위표, 일주일 공부 기록을 준비하세요. {local} 학생이 반복해서 틀린 문제에 표시하면 확인 순서를 정하기 좋습니다.",
        f"사용 중인 교재의 진도 위치와 최근 답안, 미완료 계획표를 함께 가져가세요. 잘된 기록보다 막힌 지점을 보여 주는 자료가 {local} 상담에 도움이 됩니다.",
        f"과목별 점수만 적기보다 틀린 문제, 풀이 흔적, 다시 푼 날짜를 모아 주세요. 학교 일정과 실제 공부 가능 시간도 함께 정리하는 것이 좋습니다.",
        f"최근 두 번의 평가 자료와 현재 교재 목차, 주간 계획을 준비하세요. 반복 오답과 새로 생긴 어려움을 구분해 표시하면 상담 질문이 구체적입니다.",
        f"학교 시험 범위, 수행평가 일정, 과목별 교재, 평소 완료량을 한곳에 정리하세요. {title}에 희망 과목과 가능한 요일도 함께 알려 주세요.",
        f"답안에서 비운 문제와 오래 걸린 문제, 고친 문제를 나누어 표시해 가져가세요. {local} 학생이 혼자 공부할 수 있는 시간도 빠뜨리지 않는 것이 좋습니다.",
        f"현재 학년·재학 학교·희망 과목과 함께 최근 시험지, 교재, 오답 기록을 준비하세요. 자료가 실제 상태와 가까울수록 확인할 질문을 줄일 수 있습니다.",
        f"완료한 계획과 끝내지 못한 계획을 모두 가져가고 이유를 짧게 적어 주세요. 시험지의 반복 실수와 학교 일정도 함께 보면 우선순위를 비교하기 쉽습니다.",
        f"학생이 쓰는 교재를 새로 정리할 필요는 없습니다. 실제 답안, 학교 공지, 일주일 공부 시간, 어려운 단원을 그대로 준비하면 됩니다.",
        f"{subjects} 가운데 상담할 과목별로 최근 답안 한 부, 교재 진도, 시험 범위, 오답 노트를 준비해 현재 상태를 설명하세요.",
        f"최근 점수와 함께 문제를 푼 과정, 재풀이 여부, 주간 완료량을 적어 주세요. {local} 학교 일정이 있다면 날짜도 함께 확인해야 합니다.",
        f"교재명·진도·반복 오답·평소 학습 시간을 과목별로 나누고 가장 먼저 해결하고 싶은 문제를 한 가지씩 적어 오세요.",
    ]
    grade_questions = [
        f"{title}의 가능 학년과 과목은 어디에서 확인하나요?",
        f"{local} 지점의 {subjects} 학년 정보는 어떻게 보나요?",
        f"페이지에 표시된 수업 가능 범위가 현재와 같나요?",
        f"{title}에서 상담 가능한 학년·과목 자료가 있나요?",
        f"과목마다 표시된 가능 학년이 다른 이유는 무엇인가요?",
        f"{local} 학생의 학년이 표시되어 있으면 바로 등록할 수 있나요?",
        f"{title}의 학년 정보는 어떤 기준으로 적었나요?",
        f"희망 과목이 페이지에 없을 때는 어떻게 확인하나요?",
        f"{subjects} 가능 학년 표시는 어떻게 활용해야 하나요?",
        f"센터별 수업 과목과 학년은 모두 동일한가요?",
        f"{title}의 현재 반 편성도 페이지에서 알 수 있나요?",
        f"가능 학년 자료와 실제 수업 여부는 같은 의미인가요?",
    ]
    if grades:
        grade_endings = [
            "현재 반 편성과 시간표는 달라질 수 있어 상담 시 다시 확인해야 합니다.",
            "표시가 있어도 희망 요일의 실제 운영 여부는 별도 확인이 필요합니다.",
            "이 내용은 공통자료 기준이며 등록 가능 여부를 보장하지 않습니다.",
            "학생의 현재 진도와 희망 시간대를 전달한 뒤 최종 가능 여부를 확인하세요.",
            "과목별 개설 상태와 일정은 상담하는 날짜를 기준으로 다시 확인하는 것이 안전합니다.",
            "페이지의 학년 표시는 확인 출발점이며 실제 수업 시간과 반 구성은 별도 정보입니다.",
            "같은 학년이라도 과목과 진도에 따라 안내가 달라질 수 있습니다.",
            "원자료에 있는 범위만 옮겼으며 없는 학년을 임의로 추가하지 않았습니다.",
            "운영 내용은 변경될 수 있으므로 재학 학교와 희망 과목을 함께 알려 주세요.",
            "최종 안내를 받을 때 현재 학년, 과목, 가능한 요일을 다시 대조하세요.",
            "학년 범위와 실제 좌석·시간표는 서로 다른 항목으로 확인해야 합니다.",
            "상담 전 최신 개설 여부를 확인하면 페이지 정보와 현재 운영의 차이를 줄일 수 있습니다.",
        ]
        grade_answer = f"공통자료에는 {grades}로 기재되어 있습니다. " + choose(profile, "faq-grade-ending", grade_endings)
    else:
        grade_answer = choose(profile, "faq-grade-missing", [
            "공통자료에 개별 학년과 과목이 적혀 있지 않습니다. 현재 학년, 희망 과목, 가능한 요일을 알려 주고 상담 시 운영 여부를 확인하세요.",
            "페이지 원자료에서 가능 범위를 확인하지 못했습니다. 학년과 과목을 임의로 추정하지 않으므로 최신 개설 정보는 상담으로 확인해야 합니다.",
            "센터별 학년 자료가 미기재 상태입니다. 학생의 학년과 필요한 과목을 먼저 전달한 뒤 수업 가능 여부와 시간을 문의하세요.",
            "확인된 학년·과목 표가 없어 페이지에 추가하지 않았습니다. 상담 날짜를 기준으로 희망 과목의 실제 운영 상태를 확인해 주세요.",
            "공통자료만으로는 현재 가능 학년을 판단할 수 없습니다. 재학 학교, 학년, 과목, 희망 시간대를 함께 알려 주는 것이 좋습니다.",
            "수업 범위를 뒷받침할 원자료가 없어 안내를 비워 두었습니다. 최신 과목과 반 편성은 지점 상담에서 확인하세요.",
            "기재되지 않은 학년을 가능하다고 표시하지 않습니다. 필요한 과목과 현재 진도를 전달하고 실제 상담 가능 여부를 확인해야 합니다.",
            "페이지가 보유한 자료에는 과목별 학년 정보가 없습니다. 시간표와 개설 과목을 포함한 현재 내용은 별도 확인이 필요합니다.",
            "가능 범위가 자료에 명시되지 않아 추정 안내를 하지 않습니다. 학생 정보와 희망 조건을 상담 때 구체적으로 알려 주세요.",
            "원자료의 학년·과목 칸이 비어 있습니다. 현재 운영 내용은 달라질 수 있으므로 상담 시점에 직접 확인하세요.",
            "학년 표시가 없다는 사실이 수업 불가를 뜻하지는 않습니다. 반대로 가능하다는 의미도 아니므로 상담 확인이 필요합니다.",
            "제공 자료만으로 학년 범위를 확정할 수 없습니다. 과목과 요일을 포함한 최신 운영 여부를 먼저 문의해 주세요.",
        ])
    plan_questions = [
        f"{local} 학생의 주간 계획은 어떤 순서로 정하면 좋나요?",
        f"시험 일정이 있을 때 학습계획은 어떻게 조정하나요?",
        f"계획을 자주 끝내지 못하는 학생은 무엇부터 바꿔야 하나요?",
        f"{subjects} 공부량은 어떤 기준으로 나누면 되나요?",
        f"{title} 상담에서 플래너는 어떻게 확인하면 좋나요?",
        f"학교 진도와 개인 진도를 함께 계획하는 방법이 있나요?",
        f"{local} 학생에게 무리하지 않은 분량은 어떻게 찾나요?",
        f"주간 계획에 반드시 적어야 할 완료 기준은 무엇인가요?",
        f"학습 시간을 늘리기 전에 먼저 확인할 항목은 무엇인가요?",
        f"미완료 계획은 다음 주에 그대로 옮겨도 되나요?",
        f"과목별 우선순위를 정할 때 어떤 자료를 보나요?",
        f"플래너가 할 일 목록으로 끝나지 않게 하려면 어떻게 하나요?",
    ]
    plan_answers = [
        f"학교 일정을 먼저 고정하고 {subjects}별 단원·분량·완료 기준을 적으세요. 지난주 완료 결과에 따라 다음 계획의 양을 조정하는 것이 좋습니다.",
        f"{local} 학생이 실제로 공부할 수 있는 요일을 정한 뒤 필수 과제와 여유 과제를 나누세요. 미완료 이유는 지우지 말고 다음 계획에 반영합니다.",
        "계획표에는 과목 이름만 쓰지 말고 교재명, 쪽수, 문제 수, 재확인 날짜를 적어야 완료 여부를 판단할 수 있습니다.",
        f"{subjects} 가운데 시험이 임박한 과목과 꾸준히 유지할 과목을 구분하세요. 하루 분량은 최근 실제 완료량을 기준으로 정합니다.",
        "학교 진도와 개인 복습을 다른 칸에 기록하고, 수행평가나 시험 일정이 바뀌면 우선순위부터 다시 조정하세요.",
        f"{title} 상담에는 계획한 양과 끝낸 양을 함께 보여 주세요. 차이가 생긴 이유를 확인해야 {local} 학생에게 맞는 분량을 찾을 수 있습니다.",
        "새 학습, 당일 복습, 누적 확인을 한꺼번에 적지 말고 서로 다른 시점에 배치하세요. 각 항목의 완료 조건도 짧게 남기는 것이 좋습니다.",
        f"{subjects}별로 이번 주에 반드시 끝낼 항목을 하나씩 정하고 남은 과제는 선택 항목으로 분리하면 과도한 계획을 줄일 수 있습니다.",
        "미완료 항목을 다음 주로 그대로 넘기기 전에 시간 부족, 난도, 이해 부족 가운데 원인을 표시하고 양이나 순서를 바꾸세요.",
        f"{local} 학교 일정에서 남은 날짜를 확인한 뒤 개념 점검·문제 풀이·오답 재확인을 주차별로 나누어 배치하세요.",
        "학생이 스스로 점검할 일과 상담에서 확인받을 일을 분리해 기록하면 플래너가 단순한 할 일 목록으로 끝나지 않습니다.",
        f"{title}에 현재 진도와 가능한 공부 시간을 알려 주고, {subjects} 과목마다 현실적으로 끝낼 수 있는 기준을 비교해 보세요.",
    ]
    error_questions = [
        f"{title} 상담에서 {subjects} 오답을 어떻게 보여 주면 좋나요?",
        f"같은 문제를 반복해서 틀릴 때 무엇을 확인해야 하나요?",
        f"오답 노트는 정답을 적는 것만으로 충분한가요?",
        f"{local} 학생의 재학습 시점은 어떻게 정하면 되나요?",
        f"맞혔지만 오래 걸린 문제도 다시 봐야 하나요?",
        f"{subjects} 오답 원인을 어떤 기준으로 나누나요?",
        f"설명을 들은 뒤에는 언제 다시 풀어야 하나요?",
        f"시험 전 오답이 많을 때 우선순위를 어떻게 정하나요?",
        f"유사 문제까지 확인해야 하는 이유는 무엇인가요?",
        f"{title} 상담용 오답 기록에는 날짜도 필요한가요?",
        f"한 번 고친 문제를 완료 처리해도 되나요?",
        f"학생이 틀린 이유를 직접 적는 것이 도움이 되나요?",
    ]
    error_answers = [
        f"{subjects} 오답을 개념 부족·조건 누락·실수·시간 부족으로 나누고 수정한 날짜와 다시 푼 날짜를 따로 기록하세요.",
        "정답을 확인한 직후 한 번, 며칠 뒤 빈 종이에서 한 번 더 풀어야 설명을 기억한 것인지 스스로 해결한 것인지 구분할 수 있습니다.",
        f"{local} 학생이 자주 틀리는 문제는 번호가 아니라 원인별로 모으세요. 다음 주에 같은 원인이 다시 나타났는지 확인하는 것이 중요합니다.",
        "맞힌 문제라도 오래 걸렸거나 힌트를 썼다면 재확인 목록에 남기세요. 혼자 제한 시간 안에 해결했을 때 완료로 보는 편이 좋습니다.",
        f"시험 전에는 {subjects} 오답 가운데 반복 횟수가 많고 다음 단원과 연결되며 실제 범위에 포함된 문제부터 다시 확인하세요.",
        "개념을 읽은 뒤 동일 문제만 외워 풀지 말고 숫자나 조건이 바뀐 유사 문제를 거쳐 적용 여부를 점검해야 합니다.",
        f"{title} 상담용 기록에는 처음 풀이, 고친 과정, 재풀이 결과를 함께 남겨 주세요. 정답만 적힌 노트보다 원인을 찾기 쉽습니다.",
        "한 번 고친 문제를 바로 지우지 말고 다음 주 목록에 남기세요. 시간이 지난 뒤에도 풀이 과정을 설명할 수 있는지 확인해야 합니다.",
        f"{subjects}별 오답 이유를 학생의 말로 한 줄 적고 다음 풀이에서 바꿀 행동을 함께 기록하면 반복 실수를 발견하기 쉽습니다.",
        "빈 문제, 계산이 길어진 문제, 조건을 잘못 읽은 문제를 다른 표시로 구분하세요. 원인마다 필요한 재학습 방법이 다릅니다.",
        f"{local} 학교 시험 범위 안의 문제는 재풀이 날짜를 정하고, 범위 밖의 누적 개념은 주간 복습 목록으로 따로 관리하세요.",
        "풀이를 설명할 수 있는지, 유사 문제에도 적용되는지, 일정 시간이 지난 뒤 다시 해결되는지를 차례로 확인하세요.",
    ]
    school_questions = [
        f"{title}의 학교 참고 정보는 어떻게 사용하나요?",
        f"목록에 학교명이 있으면 내신 수업이 가능한가요?",
        f"{local} 학교 자료는 무엇을 기준으로 확인해야 하나요?",
        f"재학 학교가 페이지에 없으면 상담할 수 없나요?",
        f"학교명이 같아도 학년별 시험 범위가 다른가요?",
        f"{title} 관련 학교 목록은 최신 시간표를 뜻하나요?",
        f"학교 참고 정보와 실제 수업 가능 여부는 같은가요?",
        f"내신 상담 전에 학교에서 받은 자료를 가져가야 하나요?",
        f"페이지에 없는 학교명을 왜 임의로 추가하지 않나요?",
        f"{local} 학교별 계획을 세울 때 가장 중요한 자료는 무엇인가요?",
        f"학교 목록만 보고 시험 대비 내용을 정할 수 있나요?",
        f"{title} 학교 정보가 현재와 다르면 어떻게 하나요?",
    ]
    if schools:
        school_answer = choose(profile, "faq-school-answer", [
            f"공통자료에 기재된 참고 학교는 {schools}입니다. 학생이 받은 실제 시험 범위와 학년 공지를 최종 기준으로 사용하세요.",
            f"페이지에는 {schools}이 참고 학교로 적혀 있습니다. 학교명만으로 수업 가능 여부나 내신 계획을 확정할 수는 없습니다.",
            f"확인된 학교 가운데 앞선 항목은 {schools}입니다. 같은 학교도 시기·학년별 범위가 달라 실제 자료를 다시 대조해야 합니다.",
            f"센터 자료에서 확인되는 학교는 {schools}입니다. 목록은 상담 준비용이며 현재 시간표나 등록 가능성을 뜻하지 않습니다.",
            f"{schools}이 공통자료에 기재되어 있습니다. 학생의 시험 범위표, 수행평가 일정, 교재 진도를 함께 확인해 주세요.",
            f"참고 가능한 학교명은 {schools}입니다. 학교 정보가 달라졌거나 누락됐다면 상담 시 최신 내용을 직접 전달해야 합니다.",
            f"원자료의 학교 항목에는 {schools}이 포함됩니다. 내신 준비 순서는 페이지가 아니라 학생이 받은 학교 자료로 결정하세요.",
            f"{schools}을 상담 대조용으로 표시했습니다. 학교가 보인다는 이유만으로 특정 과목의 수업을 보장하지는 않습니다.",
            f"공통자료상 {schools}이 연결되어 있습니다. 실제 시험 일정과 범위가 확인될 때 비로소 과목별 계획을 구체화할 수 있습니다.",
            f"학교 참고 목록은 {schools}입니다. 같은 이름의 학교라도 학생의 학년과 현재 공지가 우선하므로 자료를 함께 가져가세요.",
            f"{schools}이 페이지 근거 자료에 있습니다. 운영 여부, 시간표, 과목 편성은 학교 목록과 별도로 상담해야 합니다.",
            f"표시된 참고 학교는 {schools}입니다. 여기에 없는 학교를 추정해 추가하지 않으며 재학 학교는 상담 때 다시 확인합니다.",
        ])
    else:
        school_answer = choose(profile, "faq-school-missing", [
            "공통자료에 개별 학교명이 없어 임의로 추가하지 않았습니다. 재학 학교와 실제 시험 범위표를 상담 때 직접 알려 주세요.",
            "학교 목록이 비어 있다는 사실만으로 수업 가능 여부를 판단할 수 없습니다. 학생의 학교·학년·과목을 별도로 확인해야 합니다.",
            "확인된 학교명이 없으므로 추정 안내를 하지 않습니다. 학교 공지와 시험 자료를 준비해 상담에서 현재 범위를 대조하세요.",
            "페이지 원자료에는 특정 학교가 기재되지 않았습니다. 최신 학교 정보와 내신 대비 가능 여부는 상담으로 확인해 주세요.",
            "학교 참고 항목이 미기재 상태입니다. 재학 학교 이름과 학년별 시험 범위를 직접 전달하는 것이 가장 정확합니다.",
            "원자료에 없는 학교명을 만들어 넣지 않았습니다. 학생이 받은 범위표와 교재 진도를 상담 자료로 준비하세요.",
            "개별 학교 자료를 확인하지 못해 목록을 표시하지 않습니다. 이는 수업 가능·불가능을 뜻하지 않으므로 별도 확인이 필요합니다.",
            "학교 정보가 제공되지 않아 페이지에서 확정할 수 없습니다. 재학 학교와 희망 과목을 알려 주고 내신 상담 가능 여부를 문의하세요.",
            "공통자료의 학교 칸이 비어 있습니다. 현재 학교별 운영 내용은 상담 시점의 자료로 다시 확인해야 합니다.",
            "확인되지 않은 학교를 포함시키지 않았습니다. 상담할 때 학교명, 학년, 시험 일정, 범위표를 함께 제시해 주세요.",
            "학교 참고 목록이 없는 페이지입니다. 실제 학교 자료가 있으면 가져가 과목별 준비 순서를 상담에서 확인하세요.",
            "자료에 학교명이 없으므로 학교별 가능 여부를 주장하지 않습니다. 학생의 최신 정보로 상담 내용을 보완해야 합니다.",
        ])
    return [
        (choose(profile, "faq-prep-question", prep_questions), choose(profile, "faq-prep-answer", prep_answers)),
        (choose(profile, "faq-grade-question", grade_questions), grade_answer),
        (choose(profile, "faq-plan-question", plan_questions), choose(profile, "faq-plan-answer", plan_answers)),
        (choose(profile, "faq-error-question", error_questions), choose(profile, "faq-error-answer", error_answers)),
        (choose(profile, "faq-school-question", school_questions), school_answer),
    ]


def grade_cards(profile: dict) -> str:
    if not profile["subjects"]:
        return '<article><span>확인</span><h3>학년·과목 상담 확인</h3><p>지점별 운영 범위가 다를 수 있어 학생의 학년과 희망 과목을 먼저 전달한 뒤 가능 여부를 확인합니다.</p></article>'
    return "".join(f'<article><span>{esc(subject)}</span><h3>{esc(subject)} 수업 가능 학년</h3><p>{esc(grades)}</p></article>' for subject, grades in profile["subjects"].items())


def school_cards(profile: dict) -> str:
    if not profile["schools"]:
        return '<p class="center-profile-empty">공통자료에서 확인되지 않은 학교명은 임의로 추가하지 않았습니다. 상담 시 재학 학교와 실제 시험 범위를 알려 주세요.</p>'
    return "".join(f'<span>{esc(school)}</span>' for school in profile["schools"][:14])


def locality_links(profile: dict) -> list[tuple[str, str]]:
    result = []
    for locality in profile["localities"][:6]:
        locality_slug = locality.replace(" ", "")
        result.append((f"{locality} 고등학생학원", absolute_url("과목별학원", "고등학생학원", locality_slug)))
        result.append((f"{locality} 중학생학원", absolute_url("과목별학원", "중학생학원", locality_slug)))
        result.append((f"{locality} 초등학생학원", absolute_url("과목별학원", "초등학생학원", locality_slug)))
    return result


def schema(profile: dict, faq: list[tuple[str, str]], related: list[tuple[str, str]], meta: str) -> dict:
    page_url = absolute_url("과목별학원", "와와학습코칭센터", profile["slug"])
    hub_url = absolute_url("과목별학원", "와와학습코칭센터")
    parent_url = absolute_url("과목별학원")
    about = [{"@type": "Thing", "name": value} for value in [profile["title"], "학습 진단", "주간 플래너", "오답 재학습"]]
    about.extend({"@type": "Place", "name": value} for value in unique([profile["region"], profile["city"], *profile["localities"]]))
    mentions = [{"@type": "Thing", "name": value} for value in ["학습 진단", "주간 플래너 관리", "오답 원인 분석", "재학습"]]
    mentions.extend({"@type": "Thing", "name": f"{subject} 학습관리"} for subject in profile["subjects"])
    mentions.extend({"@type": "EducationalOrganization", "name": school} for school in profile["schools"][:14])
    offers = [{"@type": "Offer", "name": "학생별 학습 진단", "itemOffered": {"@type": "Service", "name": f"{profile['title']} 학습 진단"}}, {"@type": "Offer", "name": "플래너·오답 관리", "itemOffered": {"@type": "Service", "name": f"{profile['title']} 학습관리"}}]
    org = {"@type": ["EducationalOrganization", "LocalBusiness"], "@id": page_url + "#organization", "name": profile["title"], "url": page_url, "telephone": PHONE, "address": {"@type": "PostalAddress", "streetAddress": profile["address"], "addressRegion": profile["region"], "addressLocality": profile["city"], "addressCountry": "KR"}, "areaServed": [{"@type": "Place", "name": item} for item in profile["localities"]], "knowsAbout": [f"{key} 학습관리" for key in profile["subjects"]] or ["학생별 학습 진단", "학습 플래너", "오답 재학습"], "makesOffer": offers}
    if profile["representative"]:
        org["image"] = profile["representative"]
    if profile["registration_number"]:
        org["identifier"] = profile["registration_number"]
    webpage = {"@type": "WebPage", "@id": page_url + "#webpage", "url": page_url, "name": profile["title"], "description": meta, "inLanguage": "ko-KR", "breadcrumb": {"@id": page_url + "#breadcrumb"}, "mainEntity": {"@id": page_url + "#service"}, "about": about, "mentions": mentions, "hasPart": [{"@type": "WebPageElement", "name": name} for name in ["센터 핵심 정보", "센터별 상담 자료", "수업 가능 학년과 과목", "학습관리 흐름", "학교 참고 정보", "FAQ", "관련 페이지"]]}
    article = {"@type": "Article", "@id": page_url + "#article", "headline": profile["title"], "description": meta, "inLanguage": "ko-KR", "author": {"@id": page_url + "#organization"}, "publisher": {"@id": page_url + "#organization"}, "mainEntityOfPage": {"@id": page_url + "#webpage"}, "datePublished": TODAY, "dateModified": TODAY, "articleSection": ["와와학습코칭센터", profile["region"], profile["city"], profile["locality"]], "about": about, "mentions": mentions}
    if profile["representative"]:
        webpage["primaryImageOfPage"] = {"@type": "ImageObject", "url": profile["representative"]}
        article["image"] = profile["representative"]
    nodes = [org, webpage,
        {"@type": "BreadcrumbList", "@id": page_url + "#breadcrumb", "itemListElement": [{"@type": "ListItem", "position": 1, "name": "홈", "item": BASE_URL + "/"}, {"@type": "ListItem", "position": 2, "name": "과목별학원", "item": parent_url}, {"@type": "ListItem", "position": 3, "name": "와와학습코칭센터", "item": hub_url}, {"@type": "ListItem", "position": 4, "name": profile["title"], "item": page_url}]},
        article,
        {"@type": "Service", "@id": page_url + "#service", "name": f"{profile['title']} 학습코칭", "serviceType": "초·중·고 학생별 학습 진단과 관리", "description": meta, "provider": {"@id": page_url + "#organization"}, "areaServed": [{"@type": "Place", "name": item} for item in profile["localities"]], "audience": {"@type": "EducationalAudience", "educationalRole": "student"}, "about": about, "mentions": mentions, "makesOffer": offers},
        {"@type": "FAQPage", "@id": page_url + "#faq", "mainEntity": [{"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in faq]},
        {"@type": "ItemList", "@id": page_url + "#related", "name": f"{profile['title']} 관련 학원 안내", "itemListElement": [{"@type": "ListItem", "position": i + 1, "name": label, "url": url} for i, (label, url) in enumerate(related)]},
    ]
    return {"@context": "https://schema.org", "@graph": nodes}


def render_page(profile: dict, profiles: list[dict], index: int) -> str:
    title, local = profile["title"], profile["locality"]
    meta = meta_description(profile)
    faq = page_faq(profile)
    previous = profiles[(index - 1) % len(profiles)]
    following = profiles[(index + 1) % len(profiles)]
    related = [("와와학습코칭센터 전체 보기", absolute_url("과목별학원", "와와학습코칭센터")), *locality_links(profile)[:3], (previous["title"], absolute_url("과목별학원", "와와학습코칭센터", previous["slug"])), (following["title"], absolute_url("과목별학원", "와와학습코칭센터", following["slug"]))]
    faq_html = "".join(f'<details class="subject-faq-item"><summary><span>Q</span>{esc(q)}</summary><div class="subject-faq-answer"><span>A</span><p>{esc(a)}</p></div></details>' for q, a in faq)
    links_html = "".join(f'<a href="{esc(url)}"><span>LINK</span><strong>{esc(label)}</strong><i aria-hidden="true">→</i></a>' for label, url in related)
    localities = "".join(f"<span>{esc(value)}</span>" for value in profile["localities"])
    rep = f'<img class="subject-hidden-representative" src="{esc(profile["representative"])}" alt="{esc(title)} 대표" style="display:none;">' if profile["representative"] else ""
    kind = "seoul" if profile["region"] == "서울" else "local"
    map_html = f'''<figure class="subject-map-card center-profile-map"><div class="subject-media-label"><span>02</span><strong>{esc(title)} 위치 안내</strong></div><img src="../../../assets/maps/{esc(profile['map_file'])}" alt="{esc(title)} 지도" loading="lazy" decoding="async"><figcaption>{esc(profile['address'])}</figcaption></figure>''' if profile["map_file"] else ""
    tuition = f'<a class="center-profile-tuition" href="{esc(profile["tuition_url"])}" target="_blank" rel="noopener">센터 교습비 안내 확인 <span>→</span></a>' if profile["tuition_url"] else '<p class="center-profile-empty">교습비는 상담 시 현재 등록 기준을 확인해 주세요.</p>'
    registration = "".join(part for part in [f'<dt>교육지원청 등록명칭</dt><dd>{esc(profile["registration_name"])}</dd>' if profile["registration_name"] else "", f'<dt>교육지원청 등록번호</dt><dd>{esc(profile["registration_number"])}</dd>' if profile["registration_number"] else ""])
    scenario_lead = choose(profile, "scenario-lead", [
        f"{local} 학생이 계획을 세우고도 자주 끝내지 못한다면 계획량과 완료 기준을 함께 살펴볼 필요가 있습니다.",
        f"최근 점수는 비슷하지만 {subject_names(profile)} 풀이 시간이 길어졌다면 답안의 멈춘 지점을 먼저 확인해야 합니다.",
        "시험 직전에는 공부했지만 같은 유형을 반복해서 틀린다면 오답 원인과 재풀이 간격을 나누어 볼 수 있습니다.",
        f"{local} 학교 일정과 개인 진도가 자주 어긋난다면 실제 공부 가능 시간을 기준으로 주간 계획을 다시 비교해 보세요.",
        "교재 진도는 나갔지만 혼자 풀 때 막힌다면 설명을 들은 문제와 스스로 해결한 문제를 구분해 기록하는 것이 좋습니다.",
        f"{subject_names(profile)} 가운데 한 과목에 시간이 몰린다면 시급한 과목과 유지할 과목의 분량을 따로 정해야 합니다.",
        "오답 노트는 많지만 다시 푼 기록이 없다면 문제 수보다 재확인 날짜와 해결 여부를 먼저 점검해 보세요.",
        f"{local} 학생이 공부 시작을 미루는 날이 많다면 시작 시간보다 작게 끝낼 수 있는 첫 과제를 정하는 방법을 검토할 수 있습니다.",
        "학교 시험 범위와 현재 교재 진도가 다르다면 남은 기간에 필요한 단원을 나누고 우선순위를 다시 세워야 합니다.",
        f"{subject_names(profile)} 답안에서 빈 문제와 실수한 문제의 비율이 다르다면 각각 다른 학습 방법이 필요할 수 있습니다.",
        "계획표에는 많은 항목이 있지만 완료 표시가 적다면 지난주 실행 결과를 기준으로 다음 분량을 줄여 볼 수 있습니다.",
        f"{local} 학생이 개념은 설명하지만 문제에 적용하지 못한다면 유사 문제와 시간차 재풀이 기록을 함께 확인해 보세요.",
    ])
    scenario_tail = choose(profile, "scenario-tail", [
        f"{title} 상담에서는 최근 시험지와 실제 학습 기록을 비교해 이런 어려움이 생긴 지점을 설명할 수 있습니다.",
        f"{local} 학생의 경우에도 결과만 말하기보다 교재 진도와 완료 기록을 함께 보여 주는 것이 좋습니다.",
        f"이 상황을 상담할 때는 {subject_names(profile)} 답안과 주간 계획에서 반복된 문제를 먼저 표시해 보세요.",
        f"{title}에 현재 상태를 전달하려면 점수 변화와 함께 공부 시간, 미완료 계획, 재풀이 기록을 준비하면 됩니다.",
        f"상담에서는 학생이 언제 멈추고 무엇을 반복해서 놓치는지 실제 자료로 구분해 질문해야 합니다.",
        f"{local} 학교 일정과 현재 진도를 나란히 놓고 계획의 양이 적절했는지부터 확인해 볼 수 있습니다.",
        f"이런 변화가 필요하다면 최근 답안에서 개념 부족과 실행 부족을 서로 다른 항목으로 표시해 가져가세요.",
        f"{title} 상담 전에 학생이 끝낸 일과 끝내지 못한 일을 모두 기록하면 다음 계획을 더 현실적으로 비교할 수 있습니다.",
        f"같은 문제가 이어질 때는 정답보다 틀린 이유와 다시 푼 날짜를 상담 자료에 남기는 것이 중요합니다.",
        f"{subject_names(profile)} 학습 기록을 과목별로 나누면 학생에게 먼저 필요한 설명과 연습을 구분하기 쉽습니다.",
        f"{local} 학생의 최근 두 평가를 비교해 반복된 실수와 새로 생긴 어려움을 따로 설명해 보세요.",
        f"이 사례처럼 상담 목표를 한 문장으로 정하고 이를 뒷받침할 시험지·교재·계획표를 함께 준비하면 됩니다.",
    ])
    scenario = (
        f"{scenario_lead} {title} 상담을 준비할 때 다음 기준을 함께 보세요. "
        f"{scenario_tail}"
    )
    consult_heading, consult_body = consult_copy(profile)
    graph = json.dumps(schema(profile, faq, related, meta), ensure_ascii=False, separators=(",", ":"))
    return f'''<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>{esc(title)} | {SITE_NAME}</title><meta name="description" content="{esc(meta)}"><meta name="robots" content="index, follow, max-image-preview:large"><link rel="canonical" href="{absolute_url('과목별학원','와와학습코칭센터',profile['slug'])}"><meta property="og:locale" content="ko_KR"><meta property="og:site_name" content="{SITE_NAME}"><meta property="og:type" content="article"><meta property="og:title" content="{esc(title)} | {SITE_NAME}"><meta property="og:description" content="{esc(meta)}"><meta property="og:url" content="{absolute_url('과목별학원','와와학습코칭센터',profile['slug'])}">{f'<meta property="og:image" content="{esc(profile["representative"])}">' if profile['representative'] else ''}<link rel="icon" type="image/png" href="../../../assets/favicon.png"><link rel="stylesheet" href="../../../assets/subject.css"><script type="application/ld+json">{graph}</script></head><body class="subject-academy-page center-profile-page"><a class="skip-link" href="#main">본문 바로가기</a>{root_nav('과목별학원')}<main id="main">
<section class="subject-local-hero center-profile-hero"><div class="wrap"><nav class="subject-breadcrumb" aria-label="현재 위치"><a href="/">홈</a><span>›</span><a href="/과목별학원/">과목별학원</a><span>›</span><a href="/과목별학원/와와학습코칭센터/">와와학습코칭센터</a><span>›</span><strong>{esc(title)}</strong></nav><p class="subject-kicker">WAWA LEARNING COACHING CENTER · {esc(profile['region'])} {esc(profile['city'])}</p><h1>{esc(title)}</h1><p class="subject-hero-answer">{esc(meta)}</p><div class="subject-hero-tags"><span>{esc(profile['region'])}</span><span>{esc(profile['city'])}</span><span>{esc(local)}</span><span>진단·계획·오답관리</span></div></div></section>
<section class="subject-media-section center-profile-media"><div class="wrap">{rep}<figure class="subject-body-card"><div class="subject-media-label"><span>01</span><strong>{esc(title)} 수업 안내</strong></div><picture><source media="(max-width:720px)" srcset="../../../assets/centers/common/{kind}-mobile.webp"><img src="../../../assets/centers/common/{kind}.webp" alt="{esc(title)} 본문" width="918" height="16116" loading="lazy" decoding="async"></picture></figure>{map_html}</div></section>
<section class="center-profile-overview"><div class="wrap center-profile-overview-grid"><div><p class="subject-kicker">CENTER AT A GLANCE</p><h2>{esc(title)} 방문 전 핵심 정보</h2><p>{esc(overview_copy(profile))}</p><div class="center-profile-localities">{localities}</div></div><dl class="center-profile-facts"><dt>주소</dt><dd>{esc(profile['address'])}</dd>{f'<dt>위치 안내</dt><dd>{esc(profile["location_note"])}</dd>' if profile['location_note'] else ''}{registration}</dl></div></section>
<section class="center-profile-context"><div class="wrap"><div class="subject-section-head"><p>LOCAL SOURCE GUIDE</p><h2>{esc(title)} 상담 자료를 읽는 세 가지 기준</h2><span>센터 제공 자료와 학생이 직접 받은 자료를 구분해 확인하세요.</span></div><div class="subject-guide-grid center-profile-context-grid">{context_cards(profile)}</div></div></section>
<section class="center-profile-grade"><div class="wrap"><div class="subject-section-head"><p>SUBJECT &amp; GRADE</p><h2>수업 가능 학년과 과목</h2><span>공통자료에 확인된 범위만 표시했습니다.</span></div><div class="center-profile-grade-grid">{grade_cards(profile)}</div>{tuition}</div></section>
<section class="center-profile-flow"><div class="wrap"><div class="subject-section-head"><p>LEARNING FLOW</p><h2>{esc(local)} 학생의 기록을 상담 계획으로 바꾸는 순서</h2><span>현재 자료에서 확인할 질문과 실행 기준을 단계별로 정리했습니다.</span></div><div class="subject-guide-grid">{flow_cards(profile)}</div></div></section>
<section class="center-profile-school"><div class="wrap center-profile-school-grid"><div><p class="subject-kicker">SCHOOL REFERENCE</p><h2>{esc(title)} 학교 참고 정보</h2><p>{esc(school_intro(profile))}</p></div><div class="center-profile-school-list">{school_cards(profile)}</div></div></section>
<section class="subject-review-section"><div class="wrap subject-narrow"><div class="subject-review-card"><p class="subject-review-label">PARENT CONSULTATION SCENARIO</p><h2>{esc(title)} 상담 상황 예시</h2><blockquote>{esc(scenario)}</blockquote><p class="subject-review-note">{esc(scenario_note(profile))}</p></div></div></section>
<section class="subject-faq-section"><div class="wrap subject-narrow"><div class="subject-section-head"><p>QUESTIONS &amp; ANSWERS</p><h2>{esc(title)} 자주 묻는 질문</h2><span>화면의 질문과 답변은 FAQ 구조화 데이터와 동일합니다.</span></div><div class="subject-faq-list">{faq_html}</div></div></section>
<section class="subject-related-section"><div class="wrap subject-narrow"><div class="subject-section-head"><p>RELATED PAGES</p><h2>{esc(title)} 관련 안내 이어보기</h2><span>센터 전체 목록과 같은 지역의 학년별 안내를 함께 확인할 수 있습니다.</span></div><div class="subject-related-grid">{links_html}</div></div></section>
<section class="consult-strip"><div class="wrap consult-strip-inner"><div><p class="eyebrow">상담 전 체크</p><h2>{esc(consult_heading)}</h2><p>{esc(consult_body)}</p></div><a class="btn btn-primary" href="/상담문의/">상담 준비하기</a></div></section></main>{footer()}</body></html>'''


def render_hub(profiles: list[dict]) -> str:
    hub_url = absolute_url("과목별학원", "와와학습코칭센터")
    grouped: dict[str, list[dict]] = defaultdict(list)
    for profile in profiles:
        grouped[profile["region"]].append(profile)
    region_parts = []
    for region in sorted(grouped, key=lambda value: (value != "서울", value)):
        cards = "".join(f'<a class="center-directory-card" data-center-name="{esc(item["title"])} {esc(item["city"])} {esc(item["locality"])}" href="/{quote("과목별학원")}/{quote("와와학습코칭센터")}/{quote(item["slug"])}/"><span>{esc(item["city"])}</span><strong>{esc(short_name(item["title"]))}</strong><small>{esc(item["locality"])}</small><i aria-hidden="true">→</i></a>' for item in grouped[region])
        region_parts.append(f'<details class="center-directory-region"{(" open" if region == "서울" else "")}><summary><span>{esc(region)}</span><strong>{len(grouped[region])}개 지점</strong></summary><div class="center-directory-grid">{cards}</div></details>')
    description = "와와학습코칭센터 187개 지점의 주소와 수업 가능 학년·과목, 학교 참고 정보, 교습비 안내를 확인하고 지역명이나 지점명으로 찾아볼 수 있습니다."
    item_list = [{"@type": "ListItem", "position": index + 1, "name": item["title"], "url": absolute_url("과목별학원", "와와학습코칭센터", item["slug"])} for index, item in enumerate(profiles)]
    graph = {"@context": "https://schema.org", "@graph": [{"@type": "CollectionPage", "@id": hub_url + "#webpage", "url": hub_url, "name": "와와학습코칭센터 지점 안내", "description": description, "inLanguage": "ko-KR", "breadcrumb": {"@id": hub_url + "#breadcrumb"}, "hasPart": {"@id": hub_url + "#centers"}}, {"@type": "BreadcrumbList", "@id": hub_url + "#breadcrumb", "itemListElement": [{"@type": "ListItem", "position": 1, "name": "홈", "item": BASE_URL + "/"}, {"@type": "ListItem", "position": 2, "name": "과목별학원", "item": absolute_url("과목별학원")}, {"@type": "ListItem", "position": 3, "name": "와와학습코칭센터", "item": hub_url}]}, {"@type": "ItemList", "@id": hub_url + "#centers", "name": "와와학습코칭센터 지점 목록", "numberOfItems": len(profiles), "itemListElement": item_list}]}
    return f'''<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>와와학습코칭센터 지점 안내 | {SITE_NAME}</title><meta name="description" content="{description}"><meta name="robots" content="index, follow"><link rel="canonical" href="{hub_url}"><meta property="og:locale" content="ko_KR"><meta property="og:site_name" content="{SITE_NAME}"><meta property="og:type" content="website"><meta property="og:title" content="와와학습코칭센터 지점 안내 | {SITE_NAME}"><meta property="og:description" content="{description}"><meta property="og:url" content="{hub_url}"><link rel="icon" type="image/png" href="../../assets/favicon.png"><link rel="stylesheet" href="../../assets/subject.css"><script type="application/ld+json">{json.dumps(graph,ensure_ascii=False,separators=(',',':'))}</script></head><body class="subject-hub-page center-directory-page"><a class="skip-link" href="#main">본문 바로가기</a>{root_nav('과목별학원')}<main id="main"><section class="subject-hub-hero center-directory-hero"><div class="wrap"><nav class="subject-breadcrumb" aria-label="현재 위치"><a href="/">홈</a><span>›</span><a href="/과목별학원/">과목별학원</a><span>›</span><strong>와와학습코칭센터</strong></nav><p class="subject-kicker">WAWA CENTER DIRECTORY</p><h1>와와학습코칭센터<br>지점별 안내</h1><p>{description}</p><div class="subject-hub-stats"><span><strong>187</strong>지점별 페이지</span><span><strong>확인</strong>주소·학년·과목</span><span><strong>4단계</strong>진단부터 재학습</span></div></div></section><section class="center-directory-section"><div class="wrap"><div class="center-directory-head"><div><p>FIND A CENTER</p><h2>지역명이나 지점명으로 찾기</h2><span>광역지역별로 펼쳐 보고 원하는 지점을 선택하세요.</span></div><label class="center-directory-search"><span class="sr-only">센터 검색</span><input id="center-search" type="search" placeholder="예: 명일점, 강동구, 명일동" autocomplete="off"></label></div><p id="center-search-status" class="subject-search-status" aria-live="polite"></p><div id="center-regions">{"".join(region_parts)}</div></div></section><section class="subject-hub-guide"><div class="wrap"><div class="subject-section-head"><p>CONSULTATION GUIDE</p><h2>지점 상담 전 세 가지를 확인하세요</h2></div><div class="subject-guide-grid"><article><span>01</span><h3>현재 자료 준비</h3><p>최근 시험지와 교재, 학교 시험 범위, 반복 오답을 함께 준비합니다.</p></article><article><span>02</span><h3>가능 학년·과목 확인</h3><p>지점마다 운영 범위가 다를 수 있으므로 등록 전 현재 가능 여부를 다시 확인합니다.</p></article><article><span>03</span><h3>실행 관리 질문</h3><p>설명 이후 플래너 점검과 오답 재학습이 어떻게 연결되는지 확인합니다.</p></article></div></div></section></main>{footer()}<script>(()=>{{const input=document.getElementById('center-search');const status=document.getElementById('center-search-status');const cards=[...document.querySelectorAll('[data-center-name]')];const groups=[...document.querySelectorAll('.center-directory-region')];input.addEventListener('input',()=>{{const q=input.value.trim().toLowerCase();let count=0;cards.forEach(card=>{{const match=!q||card.dataset.centerName.toLowerCase().includes(q);card.hidden=!match;if(match)count++;}});groups.forEach(group=>{{const visible=[...group.querySelectorAll('[data-center-name]')].some(card=>!card.hidden);group.hidden=!visible;if(q&&visible)group.open=true;}});status.textContent=q?`${{count}}개 지점을 찾았습니다.`:'';}});}})();</script></body></html>'''


def atomic_write(path: Path, value: str) -> None:
    temporary = path.with_name(path.name + ".center.tmp")
    temporary.parent.mkdir(parents=True, exist_ok=True)
    temporary.write_text(value, encoding="utf-8", newline="\n")
    temporary.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser(description="187개 센터 상세 페이지와 허브를 생성합니다.")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    profiles = build_profiles()
    outputs = {TARGET / "index.html": render_hub(profiles)}
    for index, profile in enumerate(profiles):
        outputs[TARGET / profile["slug"] / "index.html"] = render_page(
            profile, profiles, index
        )
    changed = sum(
        not path.exists() or path.read_text(encoding="utf-8", errors="strict") != value
        for path, value in outputs.items()
    )
    report = {
        "mode": "APPLY" if args.apply else "DRY-RUN",
        "hub": 1,
        "detail_pages": len(profiles),
        "changed": changed,
        "target": str(TARGET),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if args.apply:
        for path, value in outputs.items():
            if not path.exists() or path.read_text(encoding="utf-8", errors="strict") != value:
                atomic_write(path, value)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
