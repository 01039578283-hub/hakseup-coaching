from __future__ import annotations

import hashlib
import html
import json
import re
from collections import defaultdict
from datetime import date
from pathlib import Path
from urllib.parse import quote, urlparse
from zipfile import ZipFile


ROOT = Path(__file__).resolve().parents[1]
ZIP_PATH = Path.home() / "Desktop" / "학습코칭.kr 추가 원고" / "고등학생학원.zip"
BASE_URL = "https://xn--ru4bi8s1tac0p.kr"
SITE_NAME = "학습코칭 연구소"
CATEGORY = "고등학생학원"
SUBJECT_ROOT = ROOT / "과목별학원"
TARGET_ROOT = SUBJECT_ROOT / CATEGORY
TODAY = date.today().isoformat()
PHONE = "010-3957-8283"
SMS_URL = "https://blogsms.net/01039578283"
FORM_URL = "https://docs.google.com/forms/d/e/1FAIpQLSdb2oE5Qk5YS0TfYDxyV1w-IOTkhkjOCmmpAKTI9FmqpVj6Yg/viewform"


def compact(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def esc(value: str) -> str:
    return html.escape(value, quote=True)


def absolute_url(*parts: str) -> str:
    path = "/" + "/".join(part.strip("/") for part in parts if part) + "/"
    return BASE_URL + quote(path, safe="/")


def decode_text(data: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "cp949"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            pass
    raise UnicodeDecodeError("unknown", data, 0, 1, "unsupported manuscript encoding")


def parse_sections(text: str) -> dict[str, str]:
    pattern = re.compile(r"^\[([^\]]+)\]\s*$", re.MULTILINE)
    matches = list(pattern.finditer(text))
    result: dict[str, str] = {}
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        result[match.group(1).strip()] = text[match.end():end].strip()
    return result


def parse_faq(value: str) -> list[tuple[str, str]]:
    lines = [line.strip() for line in value.splitlines() if line.strip()]
    pairs: list[tuple[str, str]] = []
    question = ""
    answer: list[str] = []
    for line in lines:
        if re.match(r"^Q\d+\.\s*", line):
            if question and answer:
                pairs.append((question, compact(" ".join(answer))))
            question = re.sub(r"^Q\d+\.\s*", "", line).strip()
            answer = []
        elif re.match(r"^A\d+\.\s*", line):
            answer.append(re.sub(r"^A\d+\.\s*", "", line).strip())
        elif question:
            answer.append(line)
    if question and answer:
        pairs.append((question, compact(" ".join(answer))))
    return pairs


def parse_review(value: str) -> tuple[str, str]:
    lines = [line.strip() for line in value.splitlines() if line.strip()]
    note = ""
    body: list[str] = []
    for line in lines:
        if line.startswith("※") and not note:
            note = line
        else:
            body.append(line.strip("“”\""))
    if not note:
        note = "아래 내용은 상담 상황을 이해하기 위한 사례형 문구이며, 실제 이용자의 성적 결과를 보장하는 내용이 아닙니다."
    return note, compact(" ".join(body))


def individualize_high_body(value: str, locality: str, index: int) -> str:
    """Disperse one source-bank sentence without changing its factual meaning."""
    repeated = (
        f"{locality} 페이지에 제공된 학교들도 학년과 시험 범위가 다를 수 있으므로 "
        "학생이 받은 범위표, 학교 자료, 최근 시험지를 기준으로 준비 순서를 다시 나눠야 합니다."
    )
    variants = [
        f"{locality}에서 같은 학교를 다니더라도 학년과 시험 범위는 달라질 수 있습니다. 학생이 받은 범위표와 학교 자료, 최근 시험지를 먼저 대조한 뒤 준비 순서를 정합니다.",
        f"{locality} 학교 정보는 상담의 출발점으로만 활용합니다. 실제 계획은 학생의 학년, 학교 범위표, 배부 자료와 최근 시험지를 확인해 다시 세웁니다.",
        f"학교명이 같아도 {locality} 학생마다 학년과 시험 범위가 다릅니다. 범위표·학교 자료·최근 시험지를 함께 놓고 현재 필요한 준비부터 구분합니다.",
        f"{locality}의 학교별 일정만 보고 진도를 정하지 않습니다. 학생이 받은 시험 범위와 수업 자료, 최근 시험 결과를 확인해 우선순위를 조정합니다.",
        f"상담에서는 {locality} 학교명보다 학생에게 안내된 실제 범위를 먼저 봅니다. 범위표와 프린트, 최근 시험지를 바탕으로 준비 단계를 나눕니다.",
        f"{locality} 페이지에 안내된 학교 학생이라도 준비 내용은 서로 다를 수 있습니다. 학년별 범위표와 학교 자료, 최근 시험지를 확인한 뒤 순서를 정리합니다.",
        f"시험 준비는 {locality}의 학교 정보만으로 결정하지 않습니다. 학생의 학년과 현재 범위, 학교 배부물, 최근 시험지를 기준으로 학습 순서를 다시 맞춥니다.",
        f"{locality} 학생의 내신 계획은 실제 학교 자료에서 시작합니다. 범위표와 수업 프린트, 최근 시험지를 비교해 먼저 보완할 내용을 가립니다.",
        f"같은 {locality} 생활권 안에서도 학년과 시험 범위가 달라집니다. 상담 시 범위표·학교 자료·최근 시험지를 확인하고 준비 순서를 학생별로 조정합니다.",
        f"{locality} 학교 안내는 참고 정보이며, 최종 계획은 학생이 받은 시험 범위와 학교 자료를 기준으로 합니다. 최근 시험지까지 살펴 학습 순서를 구체화합니다.",
        f"학생별 계획을 세울 때에는 {locality} 학교명만 확인하지 않습니다. 학년, 실제 시험 범위, 배부 자료와 최근 시험지를 함께 검토합니다.",
        f"{locality}에서 내신을 준비한다면 먼저 학생의 범위표와 학교 자료를 확인해야 합니다. 최근 시험 결과를 더해 지금 필요한 순서로 계획을 다시 배열합니다.",
    ]
    return value.replace(repeated, variants[index % len(variants)])


def compact_high_meta(value: str) -> str:
    meta = compact(value)
    if len(meta) > 100:
        meta = meta.replace("주소·통학, ", "").replace("상담 질문", "상담")
    if len(meta) > 100:
        meta = meta[:97].rstrip(" ,·") + "…"
    return meta


def varied_review_note(locality: str, title: str, index: int) -> str:
    variants = [
        f"※ {locality} 학부모가 상담 기준을 이해하도록 구성한 가상 사례이며, 실제 수강생의 발언이나 성적 결과를 의미하지 않습니다.",
        f"※ 이 문구는 {title} 상담에서 확인할 관점을 설명하기 위한 예시입니다. 실제 후기 또는 성과 보장 사례가 아닙니다.",
        f"※ {locality} 학생의 학습 상황을 가정해 정리한 상담 예시로, 특정 이용자의 경험이나 결과를 재현한 내용이 아닙니다.",
        f"※ 아래 사례는 {title} 선택 기준을 이해하기 위한 설명용 구성입니다. 실제 수강 후기와는 구분해 읽어 주세요.",
        f"※ {locality} 상담 과정에서 살펴볼 항목을 보여 주는 가상 문구이며, 개인의 성적 향상을 보장하지 않습니다.",
        f"※ 학부모의 이해를 돕기 위해 {title} 상담 상황을 재구성한 예시입니다. 실제 학생의 발언이나 결과가 아닙니다.",
        f"※ 이 사례는 {locality} 고등 학습 상담의 확인 순서를 설명하려고 작성했으며, 실제 이용 후기로 제시한 내용이 아닙니다.",
        f"※ {title} 페이지의 상담 메모는 정보 제공을 위한 가상 사례입니다. 특정 학생의 경험이나 성과를 뜻하지 않습니다.",
        f"※ 아래 내용은 {locality} 학생에게 필요한 상담 질문을 보여 주기 위한 예시이며, 실제 후기나 결과 보장 표현이 아닙니다.",
        f"※ {title} 상담 시 확인할 학습 조건을 이해하기 쉽게 구성한 사례형 문구입니다. 실제 수강생 사례와는 다릅니다.",
        f"※ {locality} 학부모가 준비 항목을 살펴볼 수 있도록 만든 설명용 사례이며, 실제 성적 변화나 이용 경험을 나타내지 않습니다.",
        f"※ 다음 문구는 {title}의 상담 흐름을 설명하기 위해 가정한 내용입니다. 실제 학생 후기 또는 성과 자료가 아닙니다.",
    ]
    return variants[index % len(variants)]


def inline_markup(value: str) -> str:
    safe = esc(value)
    return re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", safe)


def render_blocks(value: str) -> str:
    blocks = re.split(r"\n\s*\n", value.strip())
    rendered: list[str] = []
    for block in blocks:
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        if not lines:
            continue
        if all(re.match(r"^[-*]\s+", line) for line in lines):
            items = "".join(f"<li>{inline_markup(re.sub(r'^[-*]\\s+', '', line))}</li>" for line in lines)
            rendered.append(f'<ul class="subject-copy-list">{items}</ul>')
        else:
            rendered.append(f"<p>{inline_markup(' '.join(lines))}</p>")
    return "\n".join(rendered)


def parse_body(value: str) -> tuple[str, list[tuple[str, str]]]:
    matches = list(re.finditer(r"^##\s+(.+?)\s*$", value, re.MULTILINE))
    if not matches:
        return value.strip(), []
    intro = value[:matches[0].start()].strip()
    sections: list[tuple[str, str]] = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(value)
        sections.append((match.group(1).strip(), value[match.end():end].strip()))
    return intro, sections


def extract_graph(page: str) -> list[dict]:
    for raw in re.findall(r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', page, re.S | re.I):
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            graph = data.get("@graph")
            if isinstance(graph, list):
                return [node for node in graph if isinstance(node, dict)]
            return [data]
    return []


def has_type(node: dict, expected: str) -> bool:
    value = node.get("@type")
    return expected in value if isinstance(value, list) else value == expected


def graph_node(graph: list[dict], expected: str) -> dict:
    return next((node for node in graph if has_type(node, expected)), {})


def normalize_slug(value: str) -> str:
    return re.sub(r"[\s-]+", "", value)


def extract_source_pages() -> dict[str, dict]:
    nation = ROOT / "전국학원"
    child_names = ["고등영수학원", "중등영수학원", "초등영수학원"]
    result: dict[str, dict] = {}
    for index_path in nation.rglob("index.html"):
        folder = index_path.parent
        if not all((folder / name / "index.html").exists() for name in child_names):
            continue
        page = index_path.read_text(encoding="utf-8")
        rel = folder.relative_to(nation).parts
        if len(rel) != 3:
            continue
        region, city, source_slug = rel
        graph = extract_graph(page)
        org = graph_node(graph, "EducationalOrganization") or graph_node(graph, "LocalBusiness")
        canonical_match = re.search(r'<link rel="canonical" href="([^"]+)"', page)
        map_match = re.search(r'assets/maps/([^"\']+)', page)
        rep_match = re.search(r'<img[^>]+class="[^"]*generated-hidden-image[^"]*"[^>]+src="([^"]+)"', page)
        if not rep_match:
            rep_match = re.search(r'<meta property="og:image" content="([^"]+)"', page)
        snippet_match = re.search(r'(<section class="wawa-center-snippet".*?</section>)', page, re.S)
        result[normalize_slug(source_slug)] = {
            "region": region,
            "city": city,
            "source_slug": source_slug,
            "source_url": canonical_match.group(1) if canonical_match else absolute_url("전국학원", region, city, source_slug),
            "map_file": map_match.group(1) if map_match else "",
            "representative": rep_match.group(1) if rep_match else "",
            "center_snippet": snippet_match.group(1) if snippet_match else "",
            "organization": org,
        }
    return result


def root_nav(active: str) -> str:
    links = [
        ("홈", "/"),
        ("진단상담", "/진단상담/"),
        ("학습가이드", "/학습가이드/"),
        ("전국학원", "/전국학원/"),
        ("과목별학원", "/과목별학원/"),
        ("상담문의", "/상담문의/"),
    ]
    rendered = "".join(
        f'<a{" class=\"active\"" if label == active else ""} href="{href}">{label}</a>'
        for label, href in links
    )
    return f'''<header class="site-header">
    <nav class="nav" aria-label="주요 메뉴">
      <a class="brand" href="/"><span class="brand-mark">L</span><span>{SITE_NAME}</span></a>
      <div class="nav-links">{rendered}</div>
      <a class="nav-cta" href="/상담문의/">상담 신청</a>
    </nav>
  </header>'''


def footer() -> str:
    return f'''<footer class="site-footer"><div class="wrap footer-inner">
    <strong>{SITE_NAME}</strong>
    <div class="footer-links"><a href="/학습가이드/">학습가이드</a><a href="/전국학원/">전국학원</a><a href="/과목별학원/">과목별학원</a></div>
    <div class="footer-contact"><span>상담 전화</span><a href="tel:{PHONE}">{PHONE}</a></div>
  </div></footer>
  <div class="floating-actions" aria-label="빠른 상담 메뉴">
    <a href="tel:{PHONE}" class="fab-call"><span class="fab-icon">&#128222;</span><span class="fab-text">전화문의</span></a>
    <a href="{SMS_URL}" target="_blank" rel="noopener" class="fab-sms"><span class="fab-icon">&#128172;</span><span class="fab-text">문자문의</span></a>
    <a href="{FORM_URL}" target="_blank" rel="noopener" class="fab-consult pulse-effect"><span class="fab-icon">&#128221;</span><span class="fab-text">상담신청</span></a>
  </div>'''


def make_graph(
    *, title: str, meta: str, summary: str, faq: list[tuple[str, str]], source: dict,
    locality: str, slug: str, related: list[tuple[str, str]], representative: str,
    section_titles: list[str], json_summary: str,
) -> dict:
    page_url = absolute_url("과목별학원", CATEGORY, slug)
    category_url = absolute_url("과목별학원", CATEGORY)
    parent_url = absolute_url("과목별학원")
    org_source = source["organization"]
    org_name = org_source.get("name") or f"{locality} 학원"
    about = [
        {"@type": "Thing", "name": title},
        {"@type": "Thing", "name": "고등학생 학습코칭"},
        {"@type": "Thing", "name": "고등학생 내신 및 입시 학습관리"},
        {"@type": "Place", "name": locality},
        {"@type": "Place", "name": source["city"]},
        {"@type": "Place", "name": source["region"]},
    ]
    mentions = [
        {"@type": "Thing", "name": "학습 진단"},
        {"@type": "Thing", "name": "주간 플래너 관리"},
        {"@type": "Thing", "name": "내신 대비"},
        {"@type": "Thing", "name": "오답 재학습"},
        {"@type": "Thing", "name": "고등학생 학원 선택 기준"},
    ]
    offers = [
        {"@type": "Offer", "name": "고등학생 학습 진단", "itemOffered": {"@type": "Service", "name": f"{title} 학습 진단"}},
        {"@type": "Offer", "name": "고등학생 학습관리", "itemOffered": {"@type": "Service", "name": f"{title} 플래너·오답 관리"}},
    ]
    org: dict = {
        "@type": ["EducationalOrganization", "LocalBusiness"],
        "@id": page_url + "#organization",
        "name": org_name,
        "alternateName": org_source.get("alternateName", ["와와학습코칭학원", "와와학습코칭센터"]),
        "url": page_url,
        "telephone": org_source.get("telephone", PHONE),
        "areaServed": {"@type": "Place", "name": locality},
        "address": org_source.get("address", {"@type": "PostalAddress", "addressRegion": source["region"], "addressLocality": source["city"], "addressCountry": "KR"}),
        "knowsAbout": ["고등학생 학습관리", "내신 대비", "학습 플래너", "오답 재학습"],
        "makesOffer": offers,
    }
    if representative:
        org["image"] = representative
    if org_source.get("hasOfferCatalog"):
        org["hasOfferCatalog"] = org_source["hasOfferCatalog"]
    breadcrumb = {
        "@type": "BreadcrumbList", "@id": page_url + "#breadcrumb",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "홈", "item": BASE_URL + "/"},
            {"@type": "ListItem", "position": 2, "name": "과목별학원", "item": parent_url},
            {"@type": "ListItem", "position": 3, "name": CATEGORY, "item": category_url},
            {"@type": "ListItem", "position": 4, "name": locality, "item": page_url},
        ],
    }
    has_parts = [{"@type": "WebPageElement", "name": value} for value in ["핵심 요약", *section_titles, "FAQ", "상담 사례 메모", "센터 정보", "관련 페이지"]]
    webpage = {
        "@type": "WebPage", "@id": page_url + "#webpage", "url": page_url,
        "name": title, "description": meta, "inLanguage": "ko-KR",
        "publisher": {"@id": page_url + "#organization"},
        "breadcrumb": {"@id": page_url + "#breadcrumb"},
        "mainEntity": {"@id": page_url + "#service"},
        "about": about, "mentions": mentions, "hasPart": has_parts,
    }
    article = {
        "@type": "Article", "@id": page_url + "#article", "headline": title,
        "description": json_summary or meta, "inLanguage": "ko-KR",
        "author": {"@id": page_url + "#organization"},
        "publisher": {"@id": page_url + "#organization"},
        "mainEntityOfPage": {"@id": page_url + "#webpage"},
        "datePublished": TODAY, "dateModified": TODAY,
        "articleSection": ["고등학생학원", source["region"], source["city"], locality, *section_titles],
        "about": about, "mentions": mentions, "hasPart": has_parts,
    }
    if representative:
        article["image"] = representative
    service = {
        "@type": "Service", "@id": page_url + "#service", "name": f"{title} 학습코칭",
        "serviceType": "고등학생 내신·입시 학습관리",
        "description": summary, "provider": {"@id": page_url + "#organization"},
        "areaServed": {"@type": "Place", "name": locality},
        "audience": {"@type": "EducationalAudience", "educationalRole": "student", "educationalLevel": "high school"},
        "about": about, "mentions": mentions, "makesOffer": offers,
    }
    faq_node = {
        "@type": "FAQPage", "@id": page_url + "#faq",
        "mainEntity": [{"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in faq],
    }
    item_list = {
        "@type": "ItemList", "@id": page_url + "#related", "name": f"{locality} 관련 학원 안내",
        "itemListElement": [{"@type": "ListItem", "position": i + 1, "name": label, "url": url} for i, (label, url) in enumerate(related)],
    }
    return {"@context": "https://schema.org", "@graph": [org, webpage, breadcrumb, article, service, faq_node, item_list]}


def render_local_page(record: dict, all_records: list[dict], index: int) -> str:
    sections = record["sections"]
    source = record["source"]
    title = compact(sections["페이지타이틀"])
    meta = compact_high_meta(sections["메타설명"])
    json_summary = compact(sections["JSON-LD 요약"])
    locality = record["locality"]
    slug = record["slug"]
    body_value = individualize_high_body(sections["본문"], locality, index)
    intro, body_sections = parse_body(body_value)
    faq = parse_faq(sections["FAQ"])
    _, review_text = parse_review(sections["학부모후기"])
    review_note = varied_review_note(locality, title, index)
    if len(faq) != 5 or len(body_sections) < 5:
        raise ValueError(f"Invalid manuscript structure: {title}")
    category_url = absolute_url("과목별학원", CATEGORY)
    page_url = absolute_url("과목별학원", CATEGORY, slug)
    previous = all_records[(index - 1) % len(all_records)]
    following = all_records[(index + 1) % len(all_records)]
    related = [
        (f"{CATEGORY} 전체 보기", category_url),
        (f"{locality} 지역 학원 안내", source["source_url"]),
        (previous["sections"]["페이지타이틀"], absolute_url("과목별학원", CATEGORY, previous["slug"])),
        (following["sections"]["페이지타이틀"], absolute_url("과목별학원", CATEGORY, following["slug"])),
    ]
    graph = make_graph(
        title=title, meta=meta, summary=compact(intro), faq=faq, source=source,
        locality=locality, slug=slug, related=related,
        representative=source["representative"],
        section_titles=[heading for heading, _ in body_sections], json_summary=json_summary,
    )
    articles = "\n".join(
        f'<section class="subject-copy-section"><h2>{inline_markup(heading)}</h2>{render_blocks(copy)}</section>'
        for heading, copy in body_sections
    )
    faq_html = "\n".join(
        f'<details class="subject-faq-item"><summary><span>Q</span>{esc(q)}</summary><div class="subject-faq-answer"><span>A</span><p>{esc(a)}</p></div></details>'
        for q, a in faq
    )
    related_html = "\n".join(
        f'<a href="{esc(url)}"><span>{"CATEGORY" if pos == 0 else "LOCAL" if pos == 1 else "NEARBY"}</span><strong>{esc(label)}</strong><i aria-hidden="true">→</i></a>'
        for pos, (label, url) in enumerate(related)
    )
    rep_html = ""
    if source["representative"]:
        rep_html = f'<img class="subject-hidden-representative" src="{esc(source["representative"])}" alt="{esc(title)} {SITE_NAME} 대표" style="display:none;">'
    body_kind = "seoul" if source["region"] == "서울" else "local"
    body_src = f"../../../assets/centers/common/{body_kind}.webp"
    body_mobile_src = f"../../../assets/centers/common/{body_kind}-mobile.webp"
    map_src = f"../../../assets/maps/{source['map_file']}" if source["map_file"] else ""
    map_card = ""
    if map_src:
        map_card = f'''<figure class="subject-map-card"><div class="subject-media-label"><span>02</span><strong>{esc(locality)} 위치 안내</strong></div><img src="{esc(map_src)}" alt="{esc(title)} 지도 {SITE_NAME}" loading="lazy"><figcaption>정확한 주소와 방문 가능 시간은 상담 전화로 확인해 주세요.</figcaption></figure>'''
    center_snippet = source["center_snippet"]
    schema = json.dumps(graph, ensure_ascii=False, separators=(",", ":"))
    return f'''<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{esc(title)} | {SITE_NAME}</title>
  <meta name="description" content="{esc(meta)}">
  <meta name="robots" content="index, follow, max-image-preview:large">
  <link rel="canonical" href="{page_url}">
  <meta property="og:locale" content="ko_KR">
  <meta property="og:site_name" content="{SITE_NAME}">
  <meta property="og:type" content="article">
  <meta property="og:title" content="{esc(title)} | {SITE_NAME}">
  <meta property="og:description" content="{esc(meta)}">
  <meta property="og:url" content="{page_url}">
  {f'<meta property="og:image" content="{esc(source["representative"])}">' if source["representative"] else ''}
  <link rel="icon" type="image/png" href="../../../assets/favicon.png">
  <link rel="stylesheet" href="../../../assets/subject.css">
  <script type="application/ld+json">{schema}</script>
</head>
<body class="subject-academy-page">
  <a class="skip-link" href="#main">본문 바로가기</a>
  {root_nav("과목별학원")}
  <main id="main">
    <section class="subject-local-hero"><div class="wrap">
      <nav class="subject-breadcrumb" aria-label="현재 위치"><a href="/">홈</a><span>›</span><a href="/과목별학원/">과목별학원</a><span>›</span><a href="/과목별학원/{CATEGORY}/">{CATEGORY}</a><span>›</span><strong>{esc(locality)}</strong></nav>
      <p class="subject-kicker">HIGH SCHOOL COACHING · {esc(source['region'])} {esc(source['city'])}</p>
      <h1>{esc(title)}</h1>
      <p class="subject-hero-answer">{esc(meta)}</p>
      <div class="subject-hero-tags"><span>{esc(source['region'])}</span><span>{esc(source['city'])}</span><span>고등학생</span><span>학습 진단·관리</span></div>
    </div></section>
    <section class="subject-media-section"><div class="wrap">
      {rep_html}
      <figure class="subject-body-card"><div class="subject-media-label"><span>01</span><strong>{esc(locality)} 수업 안내</strong></div><picture><source media="(max-width: 720px)" srcset="{body_mobile_src}"><img src="{body_src}" alt="{esc(title)} 본문 {SITE_NAME}" width="918" height="16116" loading="lazy" decoding="async"></picture></figure>
      {map_card}
    </div></section>
    <article class="subject-manuscript wrap" aria-labelledby="manuscript-title">
      <header class="subject-copy-head"><p>LOCAL HIGH SCHOOL GUIDE</p><h2 id="manuscript-title">{esc(title)} 선택 전 확인할 학습 기준</h2></header>
      <div class="subject-answer-box"><span>핵심 답변</span>{render_blocks(intro)}</div>
      <div class="subject-copy-flow">{articles}</div>
    </article>
    <section class="subject-faq-section"><div class="wrap subject-narrow"><div class="subject-section-head"><p>QUESTIONS &amp; ANSWERS</p><h2>{esc(title)} 자주 묻는 질문</h2><span>원고에 정리된 상담 질문과 답변을 그대로 확인하세요.</span></div><div class="subject-faq-list">{faq_html}</div></div></section>
    <section class="subject-review-section"><div class="wrap subject-narrow"><div class="subject-review-card"><p class="subject-review-label">PARENT CONSULTATION CASE</p><h2>{esc(title)} 상담 사례 메모</h2><blockquote>{esc(review_text)}</blockquote><p class="subject-review-note">{esc(review_note)}</p></div></div></section>
    {center_snippet}
    <section class="subject-related-section"><div class="wrap subject-narrow"><div class="subject-section-head"><p>RELATED PAGES</p><h2>{esc(locality)} 학원 정보 이어보기</h2><span>같은 지역 안내와 인접한 고등학생학원 페이지를 함께 확인할 수 있습니다.</span></div><div class="subject-related-grid">{related_html}</div></div></section>
    <section class="consult-strip"><div class="wrap consult-strip-inner"><div><p class="eyebrow">상담 전 체크</p><h2>현재 교재·시험지·학습 시간을 함께 알려주세요</h2><p>학생의 상황을 구체적으로 확인해야 우선순위를 더 정확히 정리할 수 있습니다.</p></div><a class="btn btn-primary" href="/상담문의/">상담 준비하기</a></div></section>
  </main>
  {footer()}
</body>
</html>'''


def hub_item_list(records: list[dict], hub_url: str) -> dict:
    return {
        "@type": "ItemList", "@id": hub_url + "#local-list", "name": f"전국 {CATEGORY} 지역 페이지",
        "numberOfItems": len(records),
        "itemListElement": [
            {"@type": "ListItem", "position": index + 1, "name": record["sections"]["페이지타이틀"], "url": absolute_url("과목별학원", CATEGORY, record["slug"])}
            for index, record in enumerate(records)
        ],
    }


def render_hub(records: list[dict]) -> str:
    hub_url = absolute_url("과목별학원", CATEGORY)
    parent_url = absolute_url("과목별학원")
    description = "전국 371개 동네별 고등학생학원 선택 기준을 정리했습니다. 지역·학교 자료·학생 상황을 반영한 학습 진단, 내신, 오답·주간관리 안내를 확인하세요."
    grouped: dict[str, dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))
    for record in records:
        grouped[record["source"]["region"]][record["source"]["city"]].append(record)
    region_html: list[str] = []
    for region, cities in grouped.items():
        city_html: list[str] = []
        for city, local_records in cities.items():
            buttons = "".join(
                f'<a class="subject-local-button" data-local-name="{esc(item["sections"]["페이지타이틀"])}" href="/{quote("과목별학원")}/{quote(CATEGORY)}/{quote(item["slug"])}/"><strong>{esc(item["locality"])}</strong><span>고등학생학원</span></a>'
                for item in local_records
            )
            city_html.append(f'<section class="subject-city-group" data-city-group><h3>{esc(city)} <small>{len(local_records)}</small></h3><div class="subject-local-grid">{buttons}</div></section>')
        opened = " open" if region == "서울" else ""
        region_html.append(f'<details class="subject-region-group"{opened}><summary><span>{esc(region)}</span><strong>{sum(len(v) for v in cities.values())}개 지역</strong></summary><div class="subject-region-content">{"".join(city_html)}</div></details>')
    graph = {
        "@context": "https://schema.org", "@graph": [
            {"@type": "CollectionPage", "@id": hub_url + "#webpage", "url": hub_url, "name": f"전국 {CATEGORY}", "description": description, "inLanguage": "ko-KR", "about": [{"@type": "Thing", "name": CATEGORY}, {"@type": "Thing", "name": "고등학생 학습관리"}], "hasPart": {"@id": hub_url + "#local-list"}, "breadcrumb": {"@id": hub_url + "#breadcrumb"}},
            {"@type": "BreadcrumbList", "@id": hub_url + "#breadcrumb", "itemListElement": [{"@type": "ListItem", "position": 1, "name": "홈", "item": BASE_URL + "/"}, {"@type": "ListItem", "position": 2, "name": "과목별학원", "item": parent_url}, {"@type": "ListItem", "position": 3, "name": CATEGORY, "item": hub_url}]},
            hub_item_list(records, hub_url),
        ]}
    schema = json.dumps(graph, ensure_ascii=False, separators=(",", ":"))
    return f'''<!doctype html><html lang="ko"><head>
  <meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
  <title>전국 {CATEGORY} 지역별 안내 | {SITE_NAME}</title>
  <meta name="description" content="{description}"><meta name="robots" content="index, follow">
  <link rel="canonical" href="{hub_url}"><meta property="og:locale" content="ko_KR"><meta property="og:site_name" content="{SITE_NAME}"><meta property="og:type" content="website"><meta property="og:title" content="전국 {CATEGORY} 지역별 안내 | {SITE_NAME}"><meta property="og:description" content="{description}"><meta property="og:url" content="{hub_url}">
  <link rel="icon" type="image/png" href="../../assets/favicon.png"><link rel="stylesheet" href="../../assets/subject.css"><script type="application/ld+json">{schema}</script>
</head><body class="subject-hub-page"><a class="skip-link" href="#main">본문 바로가기</a>{root_nav("과목별학원")}<main id="main">
  <section class="subject-hub-hero"><div class="wrap"><nav class="subject-breadcrumb" aria-label="현재 위치"><a href="/">홈</a><span>›</span><a href="/과목별학원/">과목별학원</a><span>›</span><strong>{CATEGORY}</strong></nav><p class="subject-kicker">HIGH SCHOOL ACADEMY DIRECTORY</p><h1>동네별 {CATEGORY} 선택 기준</h1><p>{description}</p><div class="subject-hub-stats"><span><strong>371</strong>지역 안내</span><span><strong>1:1</strong>원고 반영</span><span><strong>5</strong>페이지별 FAQ</span></div></div></section>
  <section class="subject-directory-section"><div class="wrap"><div class="subject-directory-head"><div><p>LOCAL DIRECTORY</p><h2>지역명으로 고등학생학원 찾기</h2></div><label class="subject-search"><span class="sr-only">지역명 검색</span><input id="subject-local-search" type="search" placeholder="예: 명일동, 불당동" autocomplete="off"></label></div><p id="subject-search-status" class="subject-search-status" aria-live="polite"></p><div id="subject-region-list">{"".join(region_html)}</div></div></section>
  <section class="subject-hub-guide"><div class="wrap"><div class="subject-section-head"><p>SELECTION GUIDE</p><h2>고등학생 학원은 수업 전후의 관리 흐름까지 확인하세요</h2></div><div class="subject-guide-grid"><article><span>01</span><h3>현재 수준 진단</h3><p>최근 시험지와 교재, 오답 패턴을 기준으로 우선순위를 정합니다.</p></article><article><span>02</span><h3>내신·입시 계획</h3><p>학교 일정과 목표를 함께 보고 주간 학습량을 조정합니다.</p></article><article><span>03</span><h3>실행·오답 점검</h3><p>계획의 이행 여부와 틀린 이유를 나누어 다음 학습에 반영합니다.</p></article></div></div></section>
</main>{footer()}<script>
(() => {{ const input=document.getElementById('subject-local-search'); const status=document.getElementById('subject-search-status'); const buttons=[...document.querySelectorAll('[data-local-name]')]; const groups=[...document.querySelectorAll('[data-city-group]')]; input.addEventListener('input',()=>{{ const q=input.value.trim().toLowerCase(); let count=0; buttons.forEach(button=>{{const match=!q||button.dataset.localName.toLowerCase().includes(q); button.hidden=!match; if(match) count++;}}); groups.forEach(group=>{{group.hidden=![...group.querySelectorAll('[data-local-name]')].some(button=>!button.hidden); if(q&&!group.hidden) group.closest('details').open=true;}}); status.textContent=q?`${{count}}개 지역을 찾았습니다.`:''; }}); }})();
</script></body></html>'''


def render_parent() -> str:
    parent_url = absolute_url("과목별학원")
    category_url = absolute_url("과목별학원", CATEGORY)
    description = "학년과 학습 목표에 맞는 학원 안내를 과목별로 정리합니다. 먼저 고등학생학원 371개 지역 페이지에서 내신, 학습 플래너, 오답 재학습 기준을 확인할 수 있습니다."
    graph = {"@context": "https://schema.org", "@graph": [
        {"@type": "CollectionPage", "@id": parent_url + "#webpage", "url": parent_url, "name": "과목별학원", "description": description, "inLanguage": "ko-KR", "hasPart": {"@id": parent_url + "#categories"}, "breadcrumb": {"@id": parent_url + "#breadcrumb"}},
        {"@type": "BreadcrumbList", "@id": parent_url + "#breadcrumb", "itemListElement": [{"@type": "ListItem", "position": 1, "name": "홈", "item": BASE_URL + "/"}, {"@type": "ListItem", "position": 2, "name": "과목별학원", "item": parent_url}]},
        {"@type": "ItemList", "@id": parent_url + "#categories", "name": "과목별학원 카테고리", "numberOfItems": 1, "itemListElement": [{"@type": "ListItem", "position": 1, "name": CATEGORY, "url": category_url}]},
    ]}
    schema = json.dumps(graph, ensure_ascii=False, separators=(",", ":"))
    return f'''<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>과목별학원 | {SITE_NAME}</title><meta name="description" content="{description}"><meta name="robots" content="index, follow"><link rel="canonical" href="{parent_url}"><meta property="og:locale" content="ko_KR"><meta property="og:site_name" content="{SITE_NAME}"><meta property="og:type" content="website"><meta property="og:title" content="과목별학원 | {SITE_NAME}"><meta property="og:description" content="{description}"><meta property="og:url" content="{parent_url}"><link rel="icon" type="image/png" href="../assets/favicon.png"><link rel="stylesheet" href="../assets/subject.css"><script type="application/ld+json">{schema}</script></head><body class="subject-parent-page"><a class="skip-link" href="#main">본문 바로가기</a>{root_nav("과목별학원")}<main id="main"><section class="subject-hub-hero"><div class="wrap"><nav class="subject-breadcrumb"><a href="/">홈</a><span>›</span><strong>과목별학원</strong></nav><p class="subject-kicker">ACADEMY BY LEARNING GOAL</p><h1>학년과 목표에 맞는 학원 안내</h1><p>{description}</p></div></section><section class="subject-category-section"><div class="wrap"><div class="subject-section-head"><p>CATEGORY</p><h2>학습 대상별 지역 안내</h2><span>원고가 준비된 카테고리부터 정확하게 연결합니다.</span></div><a class="subject-category-card" href="/{quote("과목별학원")}/{quote(CATEGORY)}/"><span class="subject-category-number">01</span><div><p>HIGH SCHOOL</p><h3>{CATEGORY}</h3><strong>371개 동네별 안내</strong><small>내신·플래너·오답 재학습 기준</small></div><i aria-hidden="true">→</i></a></div></section></main>{footer()}</body></html>'''


def load_records() -> list[dict]:
    if not ZIP_PATH.exists():
        raise FileNotFoundError(ZIP_PATH)
    sources = extract_source_pages()
    required = {"페이지타이틀", "메타설명", "본문", "FAQ", "학부모후기", "JSON-LD 요약"}
    records: list[dict] = []
    with ZipFile(ZIP_PATH) as archive:
        for name in archive.namelist():
            if not name.lower().endswith(".txt"):
                continue
            sections = parse_sections(decode_text(archive.read(name)))
            missing = required - set(sections)
            if missing:
                raise ValueError(f"Missing sections in {name}: {sorted(missing)}")
            title = compact(sections["페이지타이틀"])
            locality = re.sub(r"\s*고등학생학원\s*$", "", title).strip()
            slug = normalize_slug(locality)
            source = sources.get(slug)
            if not source:
                raise KeyError(f"No source center for {title} ({slug})")
            records.append({"sections": sections, "locality": locality, "slug": slug, "source": source})
    records.sort(key=lambda item: (item["source"]["region"], item["source"]["city"], item["locality"]))
    if len(records) != 371 or len({item["slug"] for item in records}) != 371:
        raise ValueError(f"Expected 371 unique records, got {len(records)}")
    return records


def update_llms() -> None:
    path = ROOT / "llms.txt"
    if not path.exists():
        return
    text = path.read_text(encoding="utf-8")
    block = f"\n## 과목별학원\n- [과목별학원]({absolute_url('과목별학원')})\n- [고등학생학원 371개 지역 안내]({absolute_url('과목별학원', CATEGORY)})\n"
    if "## 과목별학원" not in text:
        text = text.rstrip() + "\n" + block
    path.write_text(text.rstrip() + "\n", encoding="utf-8", newline="\n")


def main() -> None:
    records = load_records()
    TARGET_ROOT.mkdir(parents=True, exist_ok=True)
    for index, record in enumerate(records):
        output = TARGET_ROOT / record["slug"] / "index.html"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(render_local_page(record, records, index).rstrip() + "\n", encoding="utf-8", newline="\n")
    (TARGET_ROOT / "index.html").write_text(render_hub(records).rstrip() + "\n", encoding="utf-8", newline="\n")
    update_llms()
    print(json.dumps({"local_pages": len(records), "hub": str(TARGET_ROOT / 'index.html'), "parent": str(SUBJECT_ROOT / 'index.html')}, ensure_ascii=True))


if __name__ == "__main__":
    main()
