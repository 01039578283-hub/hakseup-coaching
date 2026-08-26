from __future__ import annotations

import csv
import hashlib
import html
import json
import re
from collections import defaultdict
from datetime import date
from pathlib import Path
from urllib.parse import quote


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


def unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def split_values(value: object) -> list[str]:
    return [compact(item) for item in re.split(r"[,/\n]+", str(value or "")) if compact(item)]


def short_name(title: str) -> str:
    return compact(title).removeprefix("와와학습코칭센터 ")


def absolute_url(*parts: str) -> str:
    path = "/" + "/".join(part.strip("/") for part in parts if part) + "/"
    return BASE_URL + quote(path, safe="/")


def deterministic_index(key: str, size: int, salt: str = "") -> int:
    return int(hashlib.sha256(f"{key}|{salt}".encode()).hexdigest()[:12], 16) % size


def load_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def load_representatives() -> list[str]:
    source = REPRESENTATIVE_CSV.read_text(encoding="utf-8-sig", errors="ignore")
    return unique(re.findall(r'https://[^"\s>,]+?\.(?:jpg|jpeg|png|webp)', source, re.I))


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
    return f'''<header class="site-header"><nav class="nav" aria-label="주요 메뉴"><a class="brand" href="/"><span class="brand-mark">L</span><span>{SITE_NAME}</span></a><div class="nav-links">{items}</div><a class="nav-cta" href="/상담문의/">상담 신청</a></nav></header>'''


def footer() -> str:
    return f'''<footer class="site-footer"><div class="wrap footer-inner"><strong>{SITE_NAME}</strong><div class="footer-links"><a href="/학습가이드/">학습가이드</a><a href="/전국학원/">전국학원</a><a href="/과목별학원/">과목별학원</a></div><div class="footer-contact"><span>상담 전화</span><a href="tel:{PHONE}">{PHONE}</a></div></div></footer><div class="floating-actions" aria-label="빠른 상담 메뉴"><a href="tel:{PHONE}" class="fab-call"><span class="fab-icon">&#128222;</span><span class="fab-text">전화문의</span></a><a href="{SMS_URL}" target="_blank" rel="noopener" class="fab-sms"><span class="fab-icon">&#128172;</span><span class="fab-text">문자문의</span></a><a href="{FORM_URL}" target="_blank" rel="noopener" class="fab-consult pulse-effect"><span class="fab-icon">&#128221;</span><span class="fab-text">상담신청</span></a></div>'''


def build_profiles() -> list[dict]:
    titles = unique([compact(line) for line in TITLE_FILE.read_text(encoding="utf-8-sig").splitlines() if compact(line)])
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
                "address": compact(first.get("센터 주소")), "location_note": compact(first.get("위치안내")),
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


def meta_description(profile: dict) -> str:
    local = profile["locality"]
    options = [
        f"{profile['title']}의 주소, 수업 가능 학년과 과목, 인근 학교, 교습비 확인 링크를 정리했습니다. {local} 학생의 상담 전 준비사항과 학습관리 흐름도 확인하세요.",
        f"{local} {profile['title']} 방문 전 주소와 가능 학년·과목, 학교 참고 정보, 교습비 안내를 확인하세요. 진단·플래너·오답 재학습 상담 기준을 함께 안내합니다.",
        f"{profile['title']} 센터 정보와 수업 대상, 가능 과목, 인근 학교를 한눈에 확인하세요. {local} 학부모가 상담 전에 준비할 자료와 확인 질문도 정리했습니다.",
    ]
    return options[deterministic_index(profile["title"], len(options), "meta")]


def page_faq(profile: dict) -> list[tuple[str, str]]:
    title, local = profile["title"], profile["locality"]
    subjects = "·".join(profile["subjects"].keys()) if profile["subjects"] else "수업 과목"
    grades = "; ".join(f"{key} {value}" for key, value in profile["subjects"].items())
    schools = ", ".join(profile["schools"][:6])
    faq = [
        (f"{title} 상담 전에는 어떤 자료를 준비하면 좋나요?", f"최근 시험지와 현재 교재, 학교 시험 범위, 평소 공부 시간, 반복해서 틀리는 문제를 준비하면 {local} 학생에게 필요한 학습 순서를 더 구체적으로 확인할 수 있습니다."),
        (f"{title}의 수업 가능 학년과 과목은 어떻게 확인하나요?", f"공통자료에서 확인되는 안내는 {grades}입니다." if grades else "지점별 운영 학년과 과목이 달라질 수 있으므로 상담 신청 전에 현재 학년과 희망 과목을 알려 주고 가능 여부를 확인해야 합니다."),
        (f"{local} 학생의 학습계획은 어떤 순서로 세우나요?", "최근 답안에서 개념 부족·문제 해석·계산 실수·학습량 부족을 나눈 뒤, 과목·단원·분량·완료 기준을 주간 플래너에 기록하고 실행 결과에 따라 다음 계획을 조정합니다."),
        (f"{title}에서 {subjects} 오답은 어떻게 관리하면 좋나요?", "정답만 고치기보다 틀린 원인을 먼저 분류하고 필요한 개념으로 돌아갑니다. 설명 직후 재풀이와 일정 시간이 지난 뒤의 재확인을 연결해야 같은 유형의 반복 실수를 줄이는 데 도움이 됩니다."),
        (f"{title} 관련 학교 정보는 어떻게 활용하나요?", f"공통자료에 기재된 참고 학교는 {schools}입니다. 학교명이 같아도 학년과 실제 시험 범위는 다를 수 있으므로 학생이 받은 범위표와 학교 자료를 최종 기준으로 확인해야 합니다." if schools else "확인되지 않은 학교명은 임의로 안내하지 않습니다. 상담 시 학생이 재학 중인 학교와 실제 시험 범위표, 학교 자료를 함께 확인해 내신 준비 순서를 정하는 것이 좋습니다."),
    ]
    return faq


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
    webpage = {"@type": "WebPage", "@id": page_url + "#webpage", "url": page_url, "name": profile["title"], "description": meta, "inLanguage": "ko-KR", "breadcrumb": {"@id": page_url + "#breadcrumb"}, "mainEntity": {"@id": page_url + "#service"}, "about": about, "mentions": mentions, "hasPart": [{"@type": "WebPageElement", "name": name} for name in ["센터 핵심 정보", "수업 가능 학년과 과목", "학습관리 흐름", "학교 참고 정보", "FAQ", "관련 페이지"]]}
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
    rep = f'<img class="subject-hidden-representative" src="{esc(profile["representative"])}" alt="{esc(title)} {SITE_NAME} 대표" style="display:none;">' if profile["representative"] else ""
    kind = "seoul" if profile["region"] == "서울" else "local"
    map_html = f'''<figure class="subject-map-card center-profile-map"><div class="subject-media-label"><span>02</span><strong>{esc(title)} 위치 안내</strong></div><img src="../../../assets/maps/{esc(profile['map_file'])}" alt="{esc(title)} 지도 {SITE_NAME}" loading="lazy" decoding="async"><figcaption>{esc(profile['address'])}</figcaption></figure>''' if profile["map_file"] else ""
    tuition = f'<a class="center-profile-tuition" href="{esc(profile["tuition_url"])}" target="_blank" rel="noopener">센터 교습비 안내 확인 <span>→</span></a>' if profile["tuition_url"] else '<p class="center-profile-empty">교습비는 상담 시 현재 등록 기준을 확인해 주세요.</p>'
    registration = "".join(part for part in [f'<dt>교육지원청 등록명칭</dt><dd>{esc(profile["registration_name"])}</dd>' if profile["registration_name"] else "", f'<dt>교육지원청 등록번호</dt><dd>{esc(profile["registration_number"])}</dd>' if profile["registration_number"] else ""])
    base_scenario = profile["review"] or "학생이 계획을 세우고도 실행하지 못한다면, 계획의 양보다 완료 기준과 점검 시점을 먼저 조정할 필요가 있습니다."
    scenario = f"{base_scenario} {title} 상담에서는 이런 변화가 필요한 원인을 최근 시험지와 실제 학습 기록으로 먼저 확인합니다."
    graph = json.dumps(schema(profile, faq, related, meta), ensure_ascii=False, separators=(",", ":"))
    return f'''<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>{esc(title)} | {SITE_NAME}</title><meta name="description" content="{esc(meta)}"><meta name="robots" content="index, follow, max-image-preview:large"><link rel="canonical" href="{absolute_url('과목별학원','와와학습코칭센터',profile['slug'])}"><meta property="og:locale" content="ko_KR"><meta property="og:site_name" content="{SITE_NAME}"><meta property="og:type" content="article"><meta property="og:title" content="{esc(title)} | {SITE_NAME}"><meta property="og:description" content="{esc(meta)}"><meta property="og:url" content="{absolute_url('과목별학원','와와학습코칭센터',profile['slug'])}">{f'<meta property="og:image" content="{esc(profile["representative"])}">' if profile['representative'] else ''}<link rel="icon" type="image/png" href="../../../assets/favicon.png"><link rel="stylesheet" href="../../../assets/subject.css"><script type="application/ld+json">{graph}</script></head><body class="subject-academy-page center-profile-page"><a class="skip-link" href="#main">본문 바로가기</a>{root_nav('과목별학원')}<main id="main">
<section class="subject-local-hero center-profile-hero"><div class="wrap"><nav class="subject-breadcrumb" aria-label="현재 위치"><a href="/">홈</a><span>›</span><a href="/과목별학원/">과목별학원</a><span>›</span><a href="/과목별학원/와와학습코칭센터/">와와학습코칭센터</a><span>›</span><strong>{esc(title)}</strong></nav><p class="subject-kicker">WAWA LEARNING COACHING CENTER · {esc(profile['region'])} {esc(profile['city'])}</p><h1>{esc(title)}</h1><p class="subject-hero-answer">{esc(meta)}</p><div class="subject-hero-tags"><span>{esc(profile['region'])}</span><span>{esc(profile['city'])}</span><span>{esc(local)}</span><span>진단·계획·오답관리</span></div></div></section>
<section class="subject-media-section center-profile-media"><div class="wrap">{rep}<figure class="subject-body-card"><div class="subject-media-label"><span>01</span><strong>{esc(title)} 수업 안내</strong></div><picture><source media="(max-width:720px)" srcset="../../../assets/centers/common/{kind}-mobile.webp"><img src="../../../assets/centers/common/{kind}.webp" alt="{esc(title)} 본문 {SITE_NAME}" width="918" height="16116" loading="lazy" decoding="async"></picture></figure>{map_html}</div></section>
<section class="center-profile-overview"><div class="wrap center-profile-overview-grid"><div><p class="subject-kicker">CENTER AT A GLANCE</p><h2>{esc(title)} 방문 전 핵심 정보</h2><p>{esc(local)}을 포함한 안내 지역과 실제 주소, 수업 가능 학년·과목을 먼저 확인하세요. 지점별 운영 범위는 달라질 수 있으므로 상담 시 현재 정보를 다시 확인하는 것이 안전합니다.</p><div class="center-profile-localities">{localities}</div></div><dl class="center-profile-facts"><dt>주소</dt><dd>{esc(profile['address'])}</dd>{f'<dt>위치 안내</dt><dd>{esc(profile["location_note"])}</dd>' if profile['location_note'] else ''}{registration}</dl></div></section>
<section class="center-profile-grade"><div class="wrap"><div class="subject-section-head"><p>SUBJECT &amp; GRADE</p><h2>수업 가능 학년과 과목</h2><span>공통자료에 확인된 범위만 표시했습니다.</span></div><div class="center-profile-grade-grid">{grade_cards(profile)}</div>{tuition}</div></section>
<section class="center-profile-flow"><div class="wrap"><div class="subject-section-head"><p>LEARNING FLOW</p><h2>{esc(local)} 학생의 학습관리 흐름</h2><span>점수만 보고 진도를 정하지 않고 학습 행동과 오답 원인을 함께 확인합니다.</span></div><div class="subject-guide-grid"><article><span>01</span><h3>상담·학습 진단</h3><p>최근 시험지와 교재를 살펴 개념 결손, 문제 해석, 계산 실수, 학습량 부족을 구분합니다.</p></article><article><span>02</span><h3>개인 계획·실행 점검</h3><p>과목·단원·분량·완료 기준을 플래너에 기록하고 실제 수행 결과에 맞춰 다음 계획을 조정합니다.</p></article><article><span>03</span><h3>오답 원인·재학습</h3><p>틀린 이유에 맞춰 개념으로 돌아가고, 즉시 재풀이와 일정 시간이 지난 뒤의 재확인을 연결합니다.</p></article></div></div></section>
<section class="center-profile-school"><div class="wrap center-profile-school-grid"><div><p class="subject-kicker">SCHOOL REFERENCE</p><h2>{esc(title)} 학교 참고 정보</h2><p>학교명은 상담 준비를 위한 참고 정보입니다. 실제 내신 계획은 학생이 받은 시험 범위와 학교 자료를 기준으로 정해야 합니다.</p></div><div class="center-profile-school-list">{school_cards(profile)}</div></div></section>
<section class="subject-review-section"><div class="wrap subject-narrow"><div class="subject-review-card"><p class="subject-review-label">PARENT CONSULTATION SCENARIO</p><h2>{esc(title)} 상담 상황 예시</h2><blockquote>{esc(scenario)}</blockquote><p class="subject-review-note">공통 상담 자료를 바탕으로 학부모가 확인할 수 있는 상황을 예시로 정리한 문장입니다. 특정 학생의 성적 결과를 보장하거나 실제 후기를 인증하는 내용은 아닙니다.</p></div></div></section>
<section class="subject-faq-section"><div class="wrap subject-narrow"><div class="subject-section-head"><p>QUESTIONS &amp; ANSWERS</p><h2>{esc(title)} 자주 묻는 질문</h2><span>화면의 질문과 답변은 FAQ 구조화 데이터와 동일합니다.</span></div><div class="subject-faq-list">{faq_html}</div></div></section>
<section class="subject-related-section"><div class="wrap subject-narrow"><div class="subject-section-head"><p>RELATED PAGES</p><h2>{esc(title)} 관련 안내 이어보기</h2><span>센터 전체 목록과 같은 지역의 학년별 안내를 함께 확인할 수 있습니다.</span></div><div class="subject-related-grid">{links_html}</div></div></section>
<section class="consult-strip"><div class="wrap consult-strip-inner"><div><p class="eyebrow">상담 전 체크</p><h2>최근 시험지·교재·학교 일정을 준비해 주세요</h2><p>현재 자료가 구체적일수록 학생에게 먼저 필요한 수업과 관리 순서를 정확하게 구분할 수 있습니다.</p></div><a class="btn btn-primary" href="/상담문의/">상담 준비하기</a></div></section></main>{footer()}</body></html>'''


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


def main() -> None:
    profiles = build_profiles()
    TARGET.mkdir(parents=True, exist_ok=True)
    (TARGET / "index.html").write_text(render_hub(profiles), encoding="utf-8", newline="\n")
    for index, profile in enumerate(profiles):
        folder = TARGET / profile["slug"]
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "index.html").write_text(render_page(profile, profiles, index), encoding="utf-8", newline="\n")
    print(json.dumps({"hub": 1, "detail_pages": len(profiles), "target": str(TARGET)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
