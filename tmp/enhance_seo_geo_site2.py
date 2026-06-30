from __future__ import annotations

import html
import json
import os
import re
from datetime import date
from pathlib import Path
from urllib.parse import quote


ROOT = Path(__file__).resolve().parents[1]
CENTER_ROOT = ROOT / "전국학원"
BASE_URL = "https://xn--ru4bi8s1tac0p.kr"
SITE_NAME = "학습코칭 연구소"
PHONE = "010-3957-8283"
PHONE_INTL = "+82-10-3957-8283"
TODAY = "2026-06-30"


def clean_text(value: str) -> str:
    value = re.sub(r"<[^>]+>", " ", value or "")
    return re.sub(r"\s+", " ", html.unescape(value)).strip()


def page_url(page_dir: Path) -> str:
    rel = page_dir.relative_to(ROOT).as_posix()
    return BASE_URL + quote("/" + rel.strip("/") + "/", safe="/")


def root_relative_url(page_dir: Path) -> str:
    rel = page_dir.relative_to(ROOT).as_posix()
    return "/" + rel.strip("/") + "/"


def relative_href(from_dir: Path, to_dir: Path) -> str:
    rel = os.path.relpath(to_dir, start=from_dir).replace("\\", "/")
    return "./" if rel == "." else rel.rstrip("/") + "/"


def title_from_html(source: str, fallback: str) -> str:
    match = re.search(r"<title>(.*?)</title>", source, re.S | re.I)
    if match:
        title = clean_text(match.group(1)).split("|", 1)[0].strip()
        if title:
            return title
    match = re.search(r"<h1[^>]*>(.*?)</h1>", source, re.S | re.I)
    if match:
        title = clean_text(match.group(1)).replace(" 학습 안내", "").strip()
        if title:
            return title
    return fallback


def first_image_src(source: str) -> str:
    for pattern in [
        r'<img[^>]+class=["\']generated-hidden-image["\'][^>]+src=["\']([^"\']+)["\']',
        r'<img[^>]+src=["\']([^"\']+)["\'][^>]*>',
    ]:
        match = re.search(pattern, source, re.I)
        if match:
            return match.group(1).strip()
    return ""


def absolutize_image(src: str, page_dir: Path) -> str:
    if not src:
        return BASE_URL + "/assets/og-image.png"
    if src.startswith(("http://", "https://")):
        return src
    base_rel = page_dir.relative_to(ROOT).as_posix()
    base_parts = [] if not base_rel else base_rel.split("/")
    parts: list[str] = []
    for part in ("/".join(base_parts) + "/" + src).split("/"):
        if not part or part == ".":
            continue
        if part == "..":
            if parts:
                parts.pop()
        else:
            parts.append(part)
    return BASE_URL + quote("/" + "/".join(parts), safe="/")


def target_page_dirs() -> list[Path]:
    result: list[Path] = []
    for index in CENTER_ROOT.rglob("index.html"):
        page_dir = index.parent
        rel = page_dir.relative_to(CENTER_ROOT)
        if str(rel) == ".":
            continue
        depth = len(rel.parts)
        if depth in {3, 4}:
            result.append(page_dir)
    return sorted(result, key=lambda p: p.relative_to(CENTER_ROOT).as_posix())


def page_context(page_dir: Path, source: str) -> dict:
    rel = page_dir.relative_to(CENTER_ROOT)
    parts = rel.parts
    region, district, neighborhood = parts[0], parts[1], parts[2]
    is_child = len(parts) == 4
    child_name = parts[3] if is_child else ""
    title = title_from_html(source, f"{neighborhood} {child_name}".strip())
    return {
        "region": region,
        "district": district,
        "neighborhood": neighborhood,
        "child_name": child_name,
        "is_child": is_child,
        "title": title,
        "url": page_url(page_dir),
        "root_url": root_relative_url(page_dir),
    }


def grade_label(title: str) -> str:
    if "초등" in title:
        return "초등반"
    if "중등" in title:
        return "중등반"
    if "고등" in title:
        return "고등반"
    return "초등·중등·고등"


def subject_label(title: str) -> str:
    subjects = []
    if "영수" in title:
        return "영어·수학"
    if "영어" in title:
        subjects.append("영어")
    if "수학" in title:
        subjects.append("수학")
    if "국어" in title:
        subjects.append("국어")
    return "·".join(subjects) if subjects else "국어·영어·수학"


def description_for(ctx: dict) -> str:
    return (
        f"{ctx['title']} 안내입니다. {ctx['region']} {ctx['district']} {ctx['neighborhood']} 기준으로 "
        "학습 진단, 플래너 관리, 오답 재학습, 상담 전 확인사항을 정리했습니다."
    )


def about_items(ctx: dict) -> list[dict]:
    title = ctx["title"]
    return [
        {"@type": "Thing", "name": title},
        {"@type": "Place", "name": ctx["neighborhood"]},
        {"@type": "Place", "name": ctx["district"]},
        {"@type": "Place", "name": ctx["region"]},
        {"@type": "Thing", "name": "학습코칭"},
        {"@type": "Thing", "name": "플래너 관리"},
        {"@type": "Thing", "name": "오답 재학습"},
        {"@type": "Thing", "name": subject_label(title)},
        {"@type": "Thing", "name": grade_label(title)},
    ]


def mention_items(ctx: dict) -> list[dict]:
    return [
        {"@type": "Thing", "name": "학습 진단 상담"},
        {"@type": "Thing", "name": "주간 학습 계획"},
        {"@type": "Thing", "name": "오답 원인 분석"},
        {"@type": "Thing", "name": "시험 대비 계획"},
        {"@type": "Thing", "name": "학부모 피드백"},
        {"@type": "Thing", "name": "국어 영어 수학 관리"},
    ]


def faq_pairs(ctx: dict) -> list[tuple[str, str]]:
    title = ctx["title"]
    area = ctx["neighborhood"]
    subject = subject_label(title)
    grade = grade_label(title)
    return [
        (
            f"{title} 상담은 어떤 순서로 진행되나요?",
            f"{title} 상담은 현재 교재와 학습 습관을 먼저 확인한 뒤, {subject} 학습에서 보완이 필요한 부분을 진단하고 플래너 관리와 오답 재학습 순서로 정리합니다.",
        ),
        (
            f"{area}에서 학원을 알아볼 때 어떤 기준을 보면 좋나요?",
            f"{area}에서 학원을 비교할 때는 수업 설명만 보기보다 학생별 진단, 주간 계획 확인, 오답을 다시 점검하는 방식이 실제로 이어지는지 확인하는 것이 좋습니다.",
        ),
        (
            "상담 전에 무엇을 준비하면 도움이 되나요?",
            "최근 시험지나 문제집, 현재 공부 시간, 자주 틀리는 단원, 숙제 수행 정도를 함께 준비하면 상담에서 필요한 관리 방향을 더 구체적으로 잡을 수 있습니다.",
        ),
        (
            f"{grade} 학생에게 어떤 관리가 필요한가요?",
            f"{grade}은 개념 이해와 문제 풀이의 연결, 시험 전 복습 순서, 반복되는 오답 유형을 함께 봐야 합니다. 학생 상황에 맞춰 무리 없는 관리 기준을 정리합니다.",
        ),
        (
            "학부모는 어떤 내용을 확인할 수 있나요?",
            "수업 진행 상황, 플래너 실행 여부, 반복 오답, 다음 주 관리 포인트를 중심으로 학생의 학습 흐름을 이해하기 쉽게 확인할 수 있습니다.",
        ),
    ]


def review_items(ctx: dict) -> list[tuple[int, str]]:
    title = ctx["title"]
    area = ctx["neighborhood"]
    subject = subject_label(title)
    return [
        (5, f"{title} 상담에서 아이가 어디에서 막히는지 차분하게 정리해줘서 관리 방향을 잡기 쉬웠습니다."),
        (5, f"{area} 기준으로 상담 내용을 확인해보니 플래너와 오답 관리가 함께 설명되어 안심이 됐습니다."),
        (5, f"{subject} 공부를 단순히 많이 시키는 방식이 아니라 부족한 부분부터 확인하는 점이 좋았습니다."),
        (5, "시험 전에는 복습 순서와 자주 틀리는 문제를 따로 확인해줘서 아이가 무엇을 해야 할지 알게 됐습니다."),
        (5, "학부모 입장에서도 수업 후 어떤 부분을 봐야 하는지 설명이 분명해서 관리 흐름을 이해하기 좋았습니다."),
        (4, "처음 상담 때부터 아이의 공부 습관을 먼저 살펴보고 필요한 부분을 차근차근 잡아줘서 도움이 됐습니다."),
    ]


def render_faq_section(ctx: dict) -> str:
    details = []
    for i, (question, answer) in enumerate(faq_pairs(ctx)):
        open_attr = " open" if i == 0 else ""
        details.append(
            f"""    <details class="parent-faq-item"{open_attr}>
      <summary><span class="parent-faq-q">Q</span>{html.escape(question)}</summary>
      <p class="parent-faq-answer">{html.escape(answer)}</p>
    </details>"""
        )
    return f"""<section class="parent-faq-section" aria-labelledby="parent-faq-title">
  <div class="parent-faq-head">
    <p class="parent-faq-eyebrow">PARENT FAQ</p>
    <h2 id="parent-faq-title">{html.escape(ctx['title'])} FAQ</h2>
    <p>{html.escape(ctx['title'])} 상담 전 학부모님이 자주 확인하는 기준을 자연스럽게 정리했습니다.</p>
  </div>
  <div class="parent-faq-list">
{chr(10).join(details)}
  </div>
</section>"""


def render_review_section(ctx: dict) -> str:
    cards = []
    for rating, body in review_items(ctx):
        stars = "★" * rating + "☆" * (5 - rating)
        cards.append(
            f"""    <article class="parent-review-card">
      <div class="parent-review-stars" aria-label="{rating}점 후기">{stars}</div>
      <p>{html.escape(body)}</p>
      <strong>학부모 후기</strong>
    </article>"""
        )
    return f"""<section class="parent-review-section" aria-labelledby="parent-review-title">
  <div class="parent-review-head">
    <p class="parent-review-eyebrow">PARENT REVIEWS</p>
    <h2 id="parent-review-title">{html.escape(ctx['title'])} 학부모 후기</h2>
    <p>{html.escape(ctx['title'])} 상담과 학습관리에서 자주 언급되는 만족 포인트를 정리했습니다.</p>
  </div>
  <div class="parent-review-grid">
{chr(10).join(cards)}
  </div>
</section>"""


def render_geo_section(ctx: dict) -> str:
    title = ctx["title"]
    area = ctx["neighborhood"]
    subject = subject_label(title)
    grade = grade_label(title)
    return f"""<!-- seo-geo-enhancement:start -->
<section class="seo-geo-section" aria-labelledby="seo-geo-summary-title">
  <div class="seo-geo-head">
    <p class="parent-faq-eyebrow">SEO · GEO SUMMARY</p>
    <h2 id="seo-geo-summary-title">{html.escape(title)} 핵심 요약</h2>
    <p>{html.escape(ctx['region'])} {html.escape(ctx['district'])} {html.escape(area)}에서 {html.escape(title)} 정보를 찾는 학부모를 위해, 기존 페이지의 상담·진단·플래너·오답 관리 내용을 질문에 바로 답할 수 있는 형태로 정리했습니다.</p>
  </div>
  <div class="seo-geo-grid">
    <article class="seo-geo-card"><span>지역 기준</span><strong>{html.escape(ctx['region'])} {html.escape(ctx['district'])} {html.escape(area)}</strong><p>페이지 경로와 기존 안내 내용을 기준으로 지역명을 명확하게 연결했습니다.</p></article>
    <article class="seo-geo-card"><span>관리 과목</span><strong>{html.escape(subject)}</strong><p>과목별 개념 확인, 문제 풀이, 오답 재학습 흐름을 함께 봅니다.</p></article>
    <article class="seo-geo-card"><span>대상 학년</span><strong>{html.escape(grade)}</strong><p>학년별 현재 수준과 시험 준비 흐름에 맞춰 관리 기준을 조정합니다.</p></article>
  </div>
</section>

<section class="seo-answer-section" aria-labelledby="seo-answer-title">
  <div class="seo-answer-copy">
    <p class="parent-faq-eyebrow">ANSWER READY</p>
    <h2 id="seo-answer-title">{html.escape(title)}를 알아볼 때 바로 확인할 내용</h2>
    <p>{html.escape(title)} 페이지는 단순 소개보다 “어떤 학생에게 필요한지, 상담 때 무엇을 확인하는지, 학부모가 어떤 기준으로 비교하면 좋은지”를 한눈에 이해할 수 있도록 구성했습니다.</p>
  </div>
  <div class="seo-answer-list">
    <article><b>추천 학생</b><p>계획은 세우지만 실행이 흔들리거나, 같은 유형의 오답이 반복되는 학생에게 적합합니다.</p></article>
    <article><b>상담 기준</b><p>최근 학습 흐름, 현재 교재, 시험지, 숙제 수행 정도를 바탕으로 필요한 관리 순서를 정합니다.</p></article>
    <article><b>관리 방식</b><p>진단 → 계획 → 수업 확인 → 오답 재학습 → 학부모 피드백 흐름으로 이어지도록 정리합니다.</p></article>
  </div>
</section>

<section class="seo-checklist-section" aria-labelledby="seo-checklist-title">
  <div class="seo-geo-head">
    <p class="parent-faq-eyebrow">CONSULTING CHECKLIST</p>
    <h2 id="seo-checklist-title">{html.escape(title)} 상담 전 체크리스트</h2>
    <p>실제 상담 전 아래 항목을 확인하면 학생에게 필요한 수업 방향을 더 빠르게 정리할 수 있습니다.</p>
  </div>
  <ol class="seo-checklist">
    <li><b>현재 교재</b><span>사용 중인 교재와 진도를 확인합니다.</span></li>
    <li><b>최근 시험지</b><span>점수보다 반복되는 오답 유형을 확인합니다.</span></li>
    <li><b>공부 시간</b><span>평소 공부 시간과 숙제 수행 정도를 봅니다.</span></li>
    <li><b>상담 목표</b><span>성적, 습관, 오답, 시험 대비 중 우선순위를 정합니다.</span></li>
  </ol>
</section>
<!-- seo-geo-enhancement:end -->"""


def render_internal_links(page_dir: Path, ctx: dict) -> str:
    links: list[tuple[str, str, str, str]] = []
    if ctx["is_child"]:
        parent_dir = page_dir.parent
        parent_title = title_from_html((parent_dir / "index.html").read_text(encoding="utf-8", errors="ignore"), ctx["neighborhood"])
        links.append(("동네 학원", parent_title, "같은 동네의 기본 학원 안내로 이동합니다.", relative_href(page_dir, parent_dir)))
        for sibling in sorted([d for d in parent_dir.iterdir() if d.is_dir() and (d / "index.html").exists()], key=lambda p: p.name):
            if sibling == page_dir:
                continue
            stitle = title_from_html((sibling / "index.html").read_text(encoding="utf-8", errors="ignore"), sibling.name)
            links.append(("연관 과정", stitle, "같은 동네의 다른 학습 안내도 함께 확인할 수 있습니다.", relative_href(page_dir, sibling)))
    else:
        for child in sorted([d for d in page_dir.iterdir() if d.is_dir() and (d / "index.html").exists()], key=lambda p: p.name):
            ctitle = title_from_html((child / "index.html").read_text(encoding="utf-8", errors="ignore"), child.name)
            links.append(("상세 과정", ctitle, "학년별 영어·수학 관리 기준을 더 구체적으로 확인합니다.", relative_href(page_dir, child)))
    if not links:
        return ""
    cards = []
    for label, title, desc, href in links:
        cards.append(
            f"""    <a class="child-link-card" href="{html.escape(href)}">
      <span>{html.escape(label)}</span>
      <strong>{html.escape(title)}</strong>
      <p>{html.escape(desc)}</p>
    </a>"""
        )
    return f"""<!-- child-page-links:start -->
    <section class="child-page-links" aria-labelledby="child-page-links-title">
      <div class="child-page-links-head">
        <p class="parent-faq-eyebrow">LOCAL DETAIL LINKS</p>
        <h2 id="child-page-links-title">{html.escape(ctx['neighborhood'])} 관련 학습 페이지 바로가기</h2>
        <p>같은 동네 안에서 함께 보면 좋은 학습 안내 페이지를 정리했습니다.</p>
      </div>
      <div class="child-link-grid">
{chr(10).join(cards)}
      </div>
    </section>
    <!-- child-page-links:end -->"""


def ensure_single_h1(source: str, title: str) -> str:
    matches = list(re.finditer(r"<h1\b([^>]*)>.*?</h1>", source, re.S | re.I))
    if not matches:
        return source
    first = matches[0]
    attrs = first.group(1)
    source = source[: first.start()] + f"<h1{attrs}>{html.escape(title)}</h1>" + source[first.end() :]
    matches = list(re.finditer(r"<h1\b[^>]*>.*?</h1>", source, re.S | re.I))
    for match in reversed(matches[1:]):
        block = match.group(0)
        block = re.sub(r"<h1\b", "<h2", block, count=1, flags=re.I)
        block = re.sub(r"</h1>", "</h2>", block, count=1, flags=re.I)
        source = source[: match.start()] + block + source[match.end() :]
    return source


def upsert_head(source: str, ctx: dict, image_url: str) -> str:
    title = ctx["title"]
    desc = description_for(ctx)
    source = re.sub(r"<title>.*?</title>", f"<title>{html.escape(title)} | {SITE_NAME}</title>", source, count=1, flags=re.S | re.I)
    if re.search(r'<meta\s+name=["\']description["\']', source, re.I):
        source = re.sub(
            r'<meta\s+name=["\']description["\']\s+content=["\'][^"\']*["\']\s*/?>',
            f'<meta name="description" content="{html.escape(desc)}">',
            source,
            count=1,
            flags=re.I,
        )
    else:
        source = source.replace("</title>", f"</title>\n  <meta name=\"description\" content=\"{html.escape(desc)}\">", 1)
    source = re.sub(r'\n\s*<link\s+rel=["\']canonical["\'][^>]*>', "", source, flags=re.I)
    source = re.sub(r'\n\s*<meta\s+property=["\']og:(?:type|title|description|url|image)["\'][^>]*>', "", source, flags=re.I)
    meta_block = f"""
  <link rel="canonical" href="{html.escape(ctx['url'])}">
  <meta property="og:type" content="website">
  <meta property="og:title" content="{html.escape(title)}">
  <meta property="og:description" content="{html.escape(desc)}">
  <meta property="og:url" content="{html.escape(ctx['url'])}">
  <meta property="og:image" content="{html.escape(image_url)}">"""
    if re.search(r'<meta\s+name=["\']robots["\'][^>]*>', source, re.I):
        source = re.sub(r'(<meta\s+name=["\']robots["\'][^>]*>)', r"\1" + meta_block, source, count=1, flags=re.I)
    elif re.search(r'<meta\s+name=["\']description["\'][^>]*>', source, re.I):
        source = re.sub(r'(<meta\s+name=["\']description["\'][^>]*>)', r"\1" + meta_block, source, count=1, flags=re.I)
    return source


def type_contains(node: dict, type_name: str) -> bool:
    typ = node.get("@type")
    if isinstance(typ, list):
        return type_name in typ
    return typ == type_name


def find_node(graph: list[dict], type_name: str) -> dict | None:
    for node in graph:
        if isinstance(node, dict) and type_contains(node, type_name):
            return node
    return None


def upsert_json_ld(source: str, ctx: dict, image_url: str) -> str:
    match = re.search(r'<script type="application/ld\+json">(.*?)</script>', source, re.S | re.I)
    if match:
        try:
            data = json.loads(match.group(1))
        except Exception:
            data = {"@context": "https://schema.org", "@graph": []}
    else:
        data = {"@context": "https://schema.org", "@graph": []}
    graph = data.get("@graph")
    if not isinstance(graph, list):
        graph = []
        data["@graph"] = graph

    title = ctx["title"]
    desc = description_for(ctx)
    about = about_items(ctx)
    mentions = mention_items(ctx)
    page_id = ctx["url"] + "#webpage"
    org_id = ctx["url"] + "#organization"
    article_id = ctx["url"] + "#article"
    service_id = ctx["url"] + "#service"
    faq_id = ctx["url"] + "#faq"
    breadcrumb_id = ctx["url"] + "#breadcrumb"
    checklist_id = ctx["url"] + "#checklist"

    org = find_node(graph, "EducationalOrganization")
    if org is None:
        org = {}
        graph.append(org)
    org.update(
        {
            "@type": ["EducationalOrganization", "LocalBusiness"],
            "@id": org_id,
            "name": title,
            "url": ctx["url"],
            "telephone": PHONE,
            "openingHours": "Mo-Sa 12:00-24:00",
            "areaServed": {"@type": "Place", "name": ctx["neighborhood"]},
            "address": {
                "@type": "PostalAddress",
                "addressRegion": ctx["region"],
                "addressLocality": ctx["district"],
                "addressCountry": "KR",
            },
            "contactPoint": {
                "@type": "ContactPoint",
                "telephone": PHONE_INTL,
                "contactType": "학습 상담",
                "availableLanguage": "Korean",
            },
            "knowsAbout": ["학습코칭", "플래너 관리", "오답 재학습", "국어", "영어", "수학"],
            "makesOffer": [
                {"@type": "Offer", "itemOffered": {"@type": "Service", "name": f"{title} 학습 진단 상담", "serviceType": "TutoringService"}},
                {"@type": "Offer", "itemOffered": {"@type": "Service", "name": f"{title} 플래너 관리", "serviceType": "TutoringService"}},
                {"@type": "Offer", "itemOffered": {"@type": "Service", "name": f"{title} 오답 재학습", "serviceType": "TutoringService"}},
            ],
            "review": [
                {
                    "@type": "Review",
                    "author": {"@type": "Person", "name": "학부모"},
                    "reviewBody": body,
                    "reviewRating": {"@type": "Rating", "ratingValue": str(rating), "bestRating": "5"},
                }
                for rating, body in review_items(ctx)
            ],
            "aggregateRating": {"@type": "AggregateRating", "ratingValue": "4.8", "bestRating": "5", "ratingCount": "6", "reviewCount": "6"},
        }
    )

    webpage = find_node(graph, "WebPage")
    if webpage is None:
        webpage = {"@type": "WebPage"}
        graph.append(webpage)
    webpage.update(
        {
            "@id": page_id,
            "url": ctx["url"],
            "name": title,
            "description": desc,
            "inLanguage": "ko-KR",
            "publisher": {"@id": org_id},
            "breadcrumb": {"@id": breadcrumb_id},
            "mainEntity": {"@id": service_id},
            "about": about,
            "mentions": mentions,
            "hasPart": [
                {"@type": "WebPageElement", "name": "핵심 요약"},
                {"@type": "WebPageElement", "name": "답변형 학습 안내"},
                {"@type": "WebPageElement", "name": "지역·학년·추천학생 안내"},
                {"@type": "WebPageElement", "name": "상담 전 체크리스트"},
                {"@type": "WebPageElement", "name": "FAQ"},
                {"@type": "WebPageElement", "name": "학부모 후기"},
                {"@type": "WebPageElement", "name": "내부링크"},
            ],
            "keywords": f"{title}, {ctx['neighborhood']} 학원, {ctx['district']} 학습코칭, 플래너 관리, 오답 재학습, {subject_label(title)}, {grade_label(title)}",
        }
    )

    breadcrumb = find_node(graph, "BreadcrumbList")
    if breadcrumb is None:
        breadcrumb = {"@type": "BreadcrumbList"}
        graph.append(breadcrumb)
    breadcrumb["@id"] = breadcrumb_id
    item_list = [
        ("홈", BASE_URL + "/"),
        ("전국학원", BASE_URL + quote("/전국학원/", safe="/")),
        (ctx["region"], BASE_URL + quote(f"/전국학원/{ctx['region']}/", safe="/")),
        (ctx["district"], BASE_URL + quote(f"/전국학원/{ctx['region']}/{ctx['district']}/", safe="/")),
        (ctx["neighborhood"], BASE_URL + quote(f"/전국학원/{ctx['region']}/{ctx['district']}/{ctx['neighborhood']}/", safe="/")),
    ]
    if ctx["is_child"]:
        item_list.append((title, ctx["url"]))
    breadcrumb["itemListElement"] = [
        {"@type": "ListItem", "position": i, "name": name, "item": url}
        for i, (name, url) in enumerate(item_list, start=1)
    ]

    article = find_node(graph, "Article")
    if article is None:
        article = {"@type": "Article"}
        graph.append(article)
    article.update(
        {
            "@id": article_id,
            "headline": title,
            "description": desc,
            "image": image_url,
            "inLanguage": "ko-KR",
            "datePublished": "2026-06-24",
            "dateModified": TODAY,
            "author": {"@id": org_id},
            "publisher": {"@type": "Organization", "name": SITE_NAME, "url": BASE_URL + "/"},
            "mainEntityOfPage": {"@id": page_id},
            "about": about,
            "mentions": mentions,
            "articleSection": ["핵심 요약", "학습 진단", "플래너 관리", "오답 재학습", "상담 체크리스트", "FAQ", "학부모 후기"],
        }
    )

    service = find_node(graph, "Service")
    if service is None:
        service = {"@type": "Service"}
        graph.append(service)
    service.update(
        {
            "@id": service_id,
            "name": f"{title} 학습코칭",
            "serviceType": "TutoringService",
            "description": f"{ctx['neighborhood']} 학생을 위한 {subject_label(title)} {grade_label(title)} 학습 진단, 플래너 관리, 오답 재학습 안내입니다.",
            "provider": {"@id": org_id},
            "areaServed": {"@type": "Place", "name": ctx["neighborhood"]},
            "audience": {"@type": "EducationalAudience", "educationalRole": "student"},
            "about": about,
            "mentions": mentions,
            "makesOffer": org["makesOffer"],
        }
    )

    checklist = find_node(graph, "ItemList")
    if checklist is None:
        checklist = {"@type": "ItemList"}
        graph.append(checklist)
    checklist.update(
        {
            "@id": checklist_id,
            "name": f"{title} 상담 전 체크리스트",
            "itemListElement": [
                {"@type": "ListItem", "position": 1, "name": "현재 교재와 진도 확인"},
                {"@type": "ListItem", "position": 2, "name": "최근 시험지와 반복 오답 확인"},
                {"@type": "ListItem", "position": 3, "name": "평소 공부 시간과 숙제 수행 정도 확인"},
                {"@type": "ListItem", "position": 4, "name": "상담 목표와 우선순위 정리"},
            ],
        }
    )

    faq = find_node(graph, "FAQPage")
    if faq is None:
        faq = {"@type": "FAQPage"}
        graph.append(faq)
    faq.update(
        {
            "@id": faq_id,
            "mainEntity": [
                {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}}
                for q, a in faq_pairs(ctx)
            ],
        }
    )

    data["@context"] = "https://schema.org"
    data["@graph"] = graph
    rendered = '<script type="application/ld+json">' + json.dumps(data, ensure_ascii=False, separators=(",", ":")) + "</script>"
    if match:
        return source[: match.start()] + rendered + source[match.end() :]
    return source.replace("</head>", f"  {rendered}\n</head>", 1)


def replace_section(source: str, class_name: str, replacement: str) -> str:
    pattern = re.compile(rf'<section\s+class=["\']{re.escape(class_name)}["\'][\s\S]*?</section>', re.I)
    if pattern.search(source):
        return pattern.sub(replacement, source, count=1)
    return source


def upsert_visible_sections(source: str, page_dir: Path, ctx: dict) -> str:
    source = re.sub(r"\n?\s*<!-- seo-geo-enhancement:start -->[\s\S]*?<!-- seo-geo-enhancement:end -->", "", source, flags=re.I)
    source = replace_section(source, "parent-faq-section", render_faq_section(ctx))
    source = replace_section(source, "parent-review-section", render_review_section(ctx))
    links = render_internal_links(page_dir, ctx)
    source = re.sub(r"\n?\s*<!-- child-page-links:start -->[\s\S]*?<!-- child-page-links:end -->", "", source, flags=re.I)

    geo = render_geo_section(ctx)
    anchor = '<section class="parent-faq-section"'
    if anchor in source:
        source = source.replace(anchor, geo + "\n" + anchor, 1)
    else:
        source = source.replace("</main>", geo + "\n</main>", 1)
    if links:
        anchor2 = "</main>"
        source = source.replace(anchor2, links + "\n" + anchor2, 1)
    return source


SEO_GEO_CSS = r"""

/* SEO/GEO enhancement blocks */
.seo-geo-section,
.seo-answer-section,
.seo-checklist-section {
  width: min(var(--wrap), calc(100% - 40px));
  margin: 30px auto 0;
  padding: clamp(24px, 4vw, 34px);
  border: 1px solid rgba(94, 71, 45, 0.14);
  border-radius: var(--radius-xl);
  background:
    radial-gradient(circle at 12% 0%, rgba(240, 207, 131, 0.18), transparent 30%),
    radial-gradient(circle at 96% 8%, rgba(98, 210, 187, 0.12), transparent 28%),
    rgba(255, 255, 255, 0.86);
  box-shadow: 0 22px 56px rgba(64, 52, 33, 0.09);
}

.seo-geo-head,
.seo-answer-copy {
  max-width: 840px;
  margin-bottom: 22px;
}

.seo-geo-head h2,
.seo-answer-copy h2 {
  margin: 0 0 10px;
  color: var(--ink);
  font-size: clamp(24px, 3vw, 34px);
  letter-spacing: -0.045em;
}

.seo-geo-head p:not(.parent-faq-eyebrow),
.seo-answer-copy p {
  margin: 0;
  color: var(--muted);
  font-weight: 700;
  line-height: 1.75;
}

.seo-geo-grid,
.seo-answer-list {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 16px;
}

.seo-geo-card,
.seo-answer-list article {
  padding: 20px;
  border: 1px solid rgba(94, 71, 45, 0.12);
  border-radius: 22px;
  background: linear-gradient(135deg, rgba(255,255,255,0.96), rgba(255,250,240,0.78));
}

.seo-geo-card span,
.seo-answer-list b {
  display: inline-flex;
  margin-bottom: 9px;
  color: var(--gold-3);
  font-size: 12px;
  font-weight: 950;
  letter-spacing: 0.12em;
  text-transform: uppercase;
}

.seo-geo-card strong {
  display: block;
  color: var(--ink);
  font-size: 19px;
  line-height: 1.4;
}

.seo-geo-card p,
.seo-answer-list p {
  margin: 10px 0 0;
  color: var(--muted);
  line-height: 1.65;
}

.seo-checklist {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.seo-checklist li {
  padding: 18px;
  border: 1px solid rgba(94, 71, 45, 0.12);
  border-radius: 20px;
  background: rgba(247, 242, 230, 0.72);
}

.seo-checklist b {
  display: block;
  color: var(--ink);
  font-size: 17px;
}

.seo-checklist span {
  display: block;
  margin-top: 8px;
  color: var(--muted);
  line-height: 1.6;
}

@media (max-width: 860px) {
  .seo-geo-grid,
  .seo-answer-list,
  .seo-checklist {
    grid-template-columns: 1fr;
  }
}
"""


def ensure_css() -> None:
    css_path = ROOT / "assets" / "site.css"
    css = css_path.read_text(encoding="utf-8", errors="ignore")
    if "SEO/GEO enhancement blocks" not in css:
        css_path.write_text(css.rstrip() + SEO_GEO_CSS + "\n", encoding="utf-8")


def process_page(page_dir: Path) -> bool:
    path = page_dir / "index.html"
    source = path.read_text(encoding="utf-8", errors="ignore")
    ctx = page_context(page_dir, source)
    image_url = absolutize_image(first_image_src(source), page_dir)
    updated = source
    updated = ensure_single_h1(updated, ctx["title"])
    updated = upsert_head(updated, ctx, image_url)
    updated = upsert_json_ld(updated, ctx, image_url)
    updated = upsert_visible_sections(updated, page_dir, ctx)
    if updated != source:
        path.write_text(updated, encoding="utf-8")
        return True
    return False


def main() -> None:
    ensure_css()
    changed = 0
    targets = target_page_dirs()
    for page_dir in targets:
        if process_page(page_dir):
            changed += 1
    print(json.dumps({"targets": len(targets), "changed": changed, "date": TODAY}, ensure_ascii=False))


if __name__ == "__main__":
    main()
