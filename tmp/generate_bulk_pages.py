import csv
import hashlib
import html
import json
import os
import random
import re
from pathlib import Path
from urllib.parse import urljoin


ROOT = Path.cwd()
CSV_PATH = Path.home() / "Desktop" / "홈페이지 새로할거 자료" / "대량 등록할 파일.csv"
CONTENT_POOL_PATH = ROOT / "tmp" / "page_content_pool.json"

SITE_NAME = "학습코칭 연구소"
SITE_DESCRIPTION = "학생별 학습 진단, 플래너 관리, 오답 재학습을 중심으로 영어·수학·국어 학습 방향을 안내하는 상담형 학원 정보 사이트입니다."
PHONE = "010-3957-8283"
PHONE_INTL = "+82-10-3957-8283"
FORM_URL = "https://docs.google.com/forms/d/e/1FAIpQLSdb2oE5Qk5YS0TfYDxyV1w-IOTkhkjOCmmpAKTI9FmqpVj6Yg/viewform"

CANONICAL_TEXT_REPLACEMENTS = {
    "봉담3지구": "봉담2지구",
}

REGION_NAMES = {
    "서울": "서울",
    "경기": "경기",
    "인천": "인천",
    "대전": "대전",
    "충청": "충청",
    "대구": "대구",
    "울산": "울산",
    "부산": "부산",
    "경상": "경상",
    "광주": "광주",
    "전라": "전라",
    "강원": "강원",
    "제주": "제주",
}


def clean_text(value: str) -> str:
    value = re.sub(r"<[^>]+>", " ", value or "")
    value = html.unescape(value)
    return re.sub(r"\s+", " ", value).strip()


def canonical_text(value: str) -> str:
    value = value or ""
    for wrong, right in CANONICAL_TEXT_REPLACEMENTS.items():
        value = value.replace(wrong, right)
    return value


def normalize_slug(value: str) -> str:
    value = canonical_text(value)
    value = (value or "").strip().replace("\\", "/").strip("/")
    value = re.sub(r"\s+", "-", value)
    return re.sub(r"-{2,}", "-", value).strip("-")


def rel_to_root(page_dir: Path) -> str:
    rel = os.path.relpath(ROOT, start=page_dir).replace("\\", "/")
    return "." if rel == "." else rel


def root_url_for(page_dir: Path) -> str:
    rel = page_dir.relative_to(ROOT).as_posix()
    return "/" + rel.strip("/") + "/" if rel else "/"


def clean_index_href(href: str) -> str:
    href = href.replace("\\", "/")
    if href == "index.html":
        return "./"
    if href.endswith("/index.html"):
        return href[: -len("index.html")]
    if href.endswith("index.html"):
        return href[: -len("index.html")] or "./"
    return href


def rel_href(from_dir: Path, target_index: Path) -> str:
    return clean_index_href(os.path.relpath(target_index, start=from_dir).replace("\\", "/"))


def strip_academy_suffix(title: str) -> str:
    title = clean_text(title)
    return re.sub(r"\s*학원\s*$", "", title).strip() or title


def local_area_parts(page_dir: Path) -> list[str]:
    center_root = (ROOT / "전국학원").resolve()
    try:
        parts = list(page_dir.resolve().relative_to(center_root).parts)
    except ValueError:
        return []
    return parts[:3]


def article_guide_heading(title: str, page_dir: Path) -> str:
    title = clean_text(title)
    if "와와학습코칭센터" in title:
        return title
    return f"{title} 와와학습코칭센터".strip()


def normalize_article_heading(article_html: str, title: str, page_dir: Path) -> str:
    heading = html.escape(article_guide_heading(title, page_dir))
    pattern = re.compile(
        r'(<p\s+class=["\']article-eyebrow["\']>).*?(</p>\s*)<h1[^>]*>.*?</h1>',
        flags=re.S | re.I,
    )
    if pattern.search(article_html):
        return pattern.sub(rf"\1LOCAL ACADEMY GUIDE\2<h1>{heading}</h1>", article_html, count=1)
    return re.sub(r"<h1[^>]*>.*?</h1>", f"<h1>{heading}</h1>", article_html, count=1, flags=re.S | re.I)


def title_from_index(page_dir: Path) -> str:
    index = page_dir / "index.html"
    if not index.exists():
        return page_dir.name
    text = index.read_text(encoding="utf-8", errors="ignore")
    match = re.search(r"<title>(.*?)</title>", text, flags=re.S | re.I)
    if match:
        return clean_text(match.group(1).split("|")[0])
    match = re.search(r"<h1[^>]*>(.*?)</h1>", text, flags=re.S | re.I)
    if match:
        return clean_text(match.group(1))
    return page_dir.name


def is_academy_page_dir(page_dir: Path) -> bool:
    index = page_dir / "index.html"
    if not index.exists():
        return False
    text = index.read_text(encoding="utf-8", errors="ignore")
    return "parent-review-section" in text and "parent-faq-section" in text


def collect_academy_titles() -> dict[Path, str]:
    center_root = ROOT / "전국학원"
    if not center_root.exists():
        return {}
    titles = {}
    for index in center_root.rglob("index.html"):
        page_dir = index.parent
        if is_academy_page_dir(page_dir):
            titles[page_dir] = title_from_index(page_dir)
    return titles


def csv_rows() -> list[list[str]]:
    with CSV_PATH.open("r", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.reader(f))
    return [row for row in rows[1:] if len(row) >= 8 and row[0].strip() and row[6].strip() and row[7].strip()]


def load_pool() -> dict:
    return json.loads(CONTENT_POOL_PATH.read_text(encoding="utf-8"))


POOL = load_pool()
FAQ_POOL = POOL["faqPool"]
REVIEW_POOL = POOL["reviewPool"]


def select_items(pool: list, page_dir: Path, salt: str, count: int) -> list:
    seed = int(hashlib.sha256((page_dir.relative_to(ROOT).as_posix() + "::" + salt).encode("utf-8")).hexdigest(), 16)
    return random.Random(seed).sample(pool, min(count, len(pool)))


def selected_reviews(page_dir: Path) -> list[dict]:
    reviews = select_items(REVIEW_POOL, page_dir, "reviews", 6)
    seed = int(hashlib.sha256((page_dir.relative_to(ROOT).as_posix() + "::review-rating").encode("utf-8")).hexdigest(), 16)
    four_index = seed % len(reviews)
    return [
        {"body": body, "rating": "4" if index == four_index else "5"}
        for index, body in enumerate(reviews)
    ]


def asset_src(root_rel: str, folder: str, filename: str) -> str:
    filename = (filename or "").strip()
    if not filename:
        return ""
    stem = Path(filename).stem
    suffix = Path(filename).suffix
    suffixes = [suffix] if suffix else []
    suffixes.extend(ext for ext in [".jpg", ".jpeg", ".png", ".webp"] if ext not in suffixes)
    stems = [stem, re.sub(r"\s+", "-", stem)]
    for candidate_stem in dict.fromkeys(stems):
        for candidate_suffix in suffixes:
            candidate = ROOT / folder / f"{candidate_stem}{candidate_suffix}"
            if candidate.exists():
                return f"{root_rel}/{folder}/{candidate.name}"
    return f"{root_rel}/{folder}/{filename}"


def img_src_from_html(value: str) -> str:
    match = re.search(r"<img[^>]+src=[\"']([^\"']+)[\"']", value or "", flags=re.I)
    return match.group(1).strip() if match else ""


def hidden_image_markup(raw: str, title: str) -> str:
    src = img_src_from_html(raw)
    if not src:
        return ""
    alt = f"{title} {SITE_NAME}"
    return f'<img class="generated-hidden-image" src="{html.escape(src)}" alt="{html.escape(alt)}">'


def image_alt(title: str, filename: str, kind: str) -> str:
    stem = Path(filename or "").stem.lower()
    if kind == "class" and stem in {"local", "seoul"}:
        return f"{title} {SITE_NAME}"
    if kind == "map":
        return f"{title} 위치 안내"
    return f"{title} {SITE_NAME}"


def image_card(title: str, src: str, alt: str, heading: str) -> str:
    if not src:
        return ""
    return f"""      <article class="bulk-image-card">
        <h2>{html.escape(heading)}</h2>
        <img src="{html.escape(src)}" alt="{html.escape(alt)}" loading="lazy">
      </article>
"""


def normalize_fragment(fragment: str) -> str:
    fragment = (fragment or "").strip()
    if not fragment or "#ERROR!" in fragment:
        return ""
    fragment = re.sub(r"<main([^>]*)>", r"<section\1>", fragment, count=1, flags=re.I)
    fragment = re.sub(r"</main>", "</section>", fragment, count=1, flags=re.I)
    return fragment


def fallback_article(title: str) -> str:
    place = strip_academy_suffix(title)
    return f"""<section class="article-main">
  <section class="article-hero">
    <p class="article-eyebrow">LOCAL ACADEMY GUIDE</p>
    <h1>{html.escape(title)} 학습관리 안내</h1>
  </section>
  <p class="article-intro">{html.escape(place)}에서 학원을 찾는 학생과 학부모를 위해 상담, 진단, 플래너 관리, 오답 재학습 흐름을 기준으로 학습 방향을 정리했습니다.</p>
  <h2>{html.escape(place)} 학원 선택 전 확인할 점</h2>
  <p>수업을 듣는 것만큼 중요한 것은 학생이 어떤 단원에서 막히는지, 숙제와 복습을 얼마나 실천하는지, 틀린 문제를 다시 해결할 수 있는지 확인하는 과정입니다.</p>
  <h2>학습관리 핵심</h2>
  <p>초기 상담에서 출발점을 잡고, 개인별 학습계획과 플래너 점검, 오답 원인 분석을 통해 공부 습관이 실제 행동으로 이어지도록 관리합니다.</p>
</section>"""


def support_section(title: str) -> str:
    place = strip_academy_suffix(title)
    return f"""<section class="generated-support-section">
  <p class="generated-kicker">COACHING CHECK</p>
  <h2>{html.escape(place)} 학원 상담에서 함께 보면 좋은 기준</h2>
  <div class="generated-support-grid">
    <article class="generated-support-card"><h3>진단</h3><p>최근 성적, 학교 진도, 과목별 약점과 공부 습관을 함께 확인합니다.</p></article>
    <article class="generated-support-card"><h3>플래너</h3><p>계획표 작성에서 끝나지 않고 실제 실행 여부와 미완료 원인을 점검합니다.</p></article>
    <article class="generated-support-card"><h3>오답</h3><p>틀린 문제의 원인을 분류하고 유사 문제로 다시 확인해 반복 실수를 줄입니다.</p></article>
  </div>
</section>
"""


CHILD_LINKS_START = "<!-- child-page-links:start -->"
CHILD_LINKS_END = "<!-- child-page-links:end -->"


def neighborhood_page_links_section(current_dir: Path, neighborhood_dir: Path, pages: list[dict]) -> str:
    neighborhood_title = strip_academy_suffix(title_from_index(neighborhood_dir))
    cards = []
    other_pages = [item for item in pages if item["page_dir"] != current_dir]
    other_pages.sort(key=lambda value: (0 if value.get("kind") == "parent" else 1, value["title"]))
    for item in other_pages:
        label = "LOCAL MAIN" if item.get("kind") == "parent" else "DETAIL GUIDE"
        description = (
            f"{neighborhood_title} 전체 수업 안내와 센터 정보를 한 번에 확인할 수 있습니다."
            if item.get("kind") == "parent"
            else f"{html.escape(strip_academy_suffix(item['title']))} 과정의 진단, 수업 흐름, 오답 관리 기준을 확인할 수 있습니다."
        )
        cards.append(f"""    <a class="child-link-card" href="{html.escape(rel_href(current_dir, item['page_dir'] / 'index.html'))}">
      <span>{html.escape(label)}</span>
      <strong>{html.escape(item['title'])}</strong>
      <p>{description}</p>
    </a>""")
    return f"""
    {CHILD_LINKS_START}
    <section class="child-page-links" aria-labelledby="child-page-links-title">
      <div class="child-page-links-head">
        <p class="parent-faq-eyebrow">LOCAL DETAIL LINKS</p>
        <h2 id="child-page-links-title">{html.escape(neighborhood_title)} 같은 동네 학원 안내 바로가기</h2>
        <p>같은 동네 안에서 함께 보면 좋은 학원 안내 페이지를 모았습니다. 필요한 과정으로 바로 이동해 보세요.</p>
      </div>
      <div class="child-link-grid">
{chr(10).join(cards)}
      </div>
    </section>
    {CHILD_LINKS_END}
"""


def update_parent_child_link_sections(created: list[dict]) -> None:
    center_root = ROOT / "전국학원"
    grouped: dict[Path, dict[Path, dict]] = {}
    for item in created:
        grouped.setdefault(item["parent_dir"], {})[item["page_dir"]] = {
            **item,
            "kind": "child",
        }

    if center_root.exists():
        for index in center_root.rglob("index.html"):
            parent_dir = index.parent
            try:
                depth = len(parent_dir.relative_to(center_root).parts)
            except ValueError:
                continue
            if depth == 3 and is_academy_page_dir(parent_dir):
                grouped.setdefault(parent_dir, {})

    for parent_dir in list(grouped):
        if not parent_dir.exists():
            continue
        if is_academy_page_dir(parent_dir):
            grouped[parent_dir].setdefault(parent_dir, {
                "title": title_from_index(parent_dir),
                "page_dir": parent_dir,
                "parent_dir": parent_dir,
                "kind": "parent",
            })
        for child in sorted([p for p in parent_dir.iterdir() if p.is_dir()], key=lambda p: p.name):
            if is_academy_page_dir(child):
                grouped[parent_dir].setdefault(child, {
                    "title": title_from_index(child),
                    "page_dir": child,
                    "parent_dir": parent_dir,
                    "kind": "child",
                })

    block_pattern = re.compile(
        rf"\s*{re.escape(CHILD_LINKS_START)}.*?{re.escape(CHILD_LINKS_END)}\s*",
        flags=re.S,
    )
    for parent_dir, pages_by_dir in grouped.items():
        pages = list(pages_by_dir.values())
        for current in pages:
            current_dir = current["page_dir"]
            index = current_dir / "index.html"
            if not index.exists() or not is_academy_page_dir(current_dir):
                continue
            text = index.read_text(encoding="utf-8")
            text = block_pattern.sub("\n", text)
            other_count = sum(1 for item in pages if item["page_dir"] != current_dir)
            if other_count == 0:
                index.write_text(text, encoding="utf-8")
                continue
            section = neighborhood_page_links_section(current_dir, parent_dir, pages)
            marker = "</main>"
            insert_at = text.find(marker)
            if insert_at == -1:
                continue
            text = text[:insert_at] + section + text[insert_at:]
            index.write_text(text, encoding="utf-8")


def faq_section(title: str, faqs: list[dict]) -> str:
    items = []
    for index, item in enumerate(faqs):
        open_attr = " open" if index == 0 else ""
        items.append(f"""    <details class="parent-faq-item"{open_attr}>
      <summary><span class="parent-faq-q">Q</span>{html.escape(item["question"])}</summary>
      <p class="parent-faq-answer">{html.escape(item["answer"])}</p>
    </details>""")
    return f"""<section class="parent-faq-section" aria-labelledby="parent-faq-title">
  <div class="parent-faq-head">
    <p class="parent-faq-eyebrow">PARENT FAQ</p>
    <h2 id="parent-faq-title">{html.escape(strip_academy_suffix(title))} 학부모 FAQ</h2>
    <p>{html.escape(title)} 상담 전 자주 확인하시는 내용을 정리했습니다.</p>
  </div>
  <div class="parent-faq-list">
{chr(10).join(items)}
  </div>
</section>
"""


def stars(rating: str) -> str:
    return "★★★★☆" if rating == "4" else "★★★★★"


def review_section(title: str, reviews: list[dict]) -> str:
    cards = []
    for item in reviews:
        cards.append(f"""    <article class="parent-review-card">
      <div class="parent-review-stars" aria-label="{item['rating']}점 후기">{stars(item['rating'])}</div>
      <p>{html.escape(item["body"])}</p>
      <strong>학부모 후기</strong>
    </article>""")
    return f"""<section class="parent-review-section" aria-labelledby="parent-review-title">
  <div class="parent-review-head">
    <p class="parent-review-eyebrow">PARENT REVIEWS</p>
    <h2 id="parent-review-title">{html.escape(strip_academy_suffix(title))} 학부모 후기</h2>
    <p>실제 상담과 학습관리에서 자주 언급되는 만족 포인트를 정리했습니다. 평균 평점 4.8점 기준입니다.</p>
  </div>
  <div class="parent-review-grid">
{chr(10).join(cards)}
  </div>
</section>
"""


def extract_address(center_html: str) -> str:
    match = re.search(r'<span class="wawa-label">\s*주소\s*</span>\s*<p[^>]*>(.*?)</p>', center_html or "", flags=re.S)
    return clean_text(match.group(1)) if match else ""


def extract_registration(center_html: str) -> str:
    text = clean_text(center_html)
    if "교육지원청" not in text:
        return ""
    match = re.search(r"([가-힣]+교육지원청\s*등록\s*제[0-9A-Za-z가-힣-]+호)", text)
    return match.group(1) if match else ""


def tuition_catalog() -> dict:
    groups = [
        ("서울 기준 · 1회 90~100분", [("주 3회", "초등", 249000), ("주 3회", "중등", 266000), ("주 3회", "고등", 299000), ("주 4회", "초등", 319000), ("주 4회", "중등", 341000), ("주 4회", "고등", 384000), ("주 5회", "초등", 389000), ("주 5회", "중등", 416000), ("주 5회", "고등", 469000)]),
        ("서울 외 지역 기준 · 1회 90~100분", [("주 3회", "초등", 219000), ("주 3회", "중등", 236000), ("주 3회", "고등", 269000), ("주 4회", "초등", 279000), ("주 4회", "중등", 301000), ("주 4회", "고등", 344000), ("주 5회", "초등", 339000), ("주 5회", "중등", 366000), ("주 5회", "고등", 419000)]),
    ]
    return {
        "@type": "OfferCatalog",
        "name": "수강료 안내",
        "itemListElement": [
            {
                "@type": "Offer",
                "name": f"{group} · {count} · {grade}",
                "price": str(price),
                "priceCurrency": "KRW",
                "description": "1회 90~100분 기준이며, 실제 수강료는 지역과 지점 운영 기준에 따라 달라질 수 있습니다.",
            }
            for group, rows in groups
            for count, grade, price in rows
        ],
    }


def breadcrumb_chain(page_dir: Path, title: str) -> list[dict]:
    parts = page_dir.relative_to(ROOT).parts
    items = [{"name": SITE_NAME, "url": "/"}]
    current = ROOT
    for part in parts:
        current = current / part
        items.append({"name": strip_academy_suffix(title) if current == page_dir else part, "url": root_url_for(current)})
    return items


def breadcrumb_json(items: list[dict]) -> dict:
    return {
        "@type": "BreadcrumbList",
        "@id": items[-1]["url"] + "#breadcrumb",
        "itemListElement": [
            {"@type": "ListItem", "position": idx, "name": item["name"], "item": item["url"]}
            for idx, item in enumerate(items, start=1)
        ],
    }


def page_json_ld(page_dir: Path, title: str, article_html: str, center_html: str, faqs: list[dict], reviews: list[dict], image_url: str) -> dict:
    url = root_url_for(page_dir)
    org_id = url + "#educational-organization"
    address = extract_address(center_html)
    registration = extract_registration(center_html)
    description = f"{title} 안내입니다. 상담, 학습 진단, 플래너 관리, 오답 재학습과 센터 위치 정보를 확인해보세요."
    article_headline = article_guide_heading(title, page_dir)
    org = {
        "@type": "EducationalOrganization",
        "@id": org_id,
        "name": f"{strip_academy_suffix(title)} 학습관리 안내",
        "url": url,
        "telephone": PHONE,
        "openingHours": "Mo-Sa 12:00-24:00",
        "areaServed": {"@type": "Place", "name": strip_academy_suffix(title)},
        "contactPoint": {"@type": "ContactPoint", "telephone": PHONE_INTL, "contactType": "customer support", "availableLanguage": "Korean"},
        "aggregateRating": {"@type": "AggregateRating", "ratingValue": "4.8", "bestRating": "5", "ratingCount": "6", "reviewCount": "6"},
        "review": [
            {
                "@type": "Review",
                "author": {"@type": "Person", "name": "학부모"},
                "reviewBody": item["body"],
                "reviewRating": {"@type": "Rating", "ratingValue": item["rating"], "bestRating": "5"},
            }
            for item in reviews
        ],
        "hasOfferCatalog": tuition_catalog(),
    }
    if address:
        org["address"] = {"@type": "PostalAddress", "streetAddress": address, "addressCountry": "KR"}
    if registration:
        org["identifier"] = {"@type": "PropertyValue", "propertyID": "교육지원청 등록번호", "value": registration}

    items = breadcrumb_chain(page_dir, title)
    graph = [
        org,
        {
            "@type": "WebPage",
            "@id": url + "#webpage",
            "url": url,
            "name": title,
            "description": description,
            "inLanguage": "ko-KR",
            "publisher": {"@id": org_id},
            "breadcrumb": {"@id": url + "#breadcrumb"},
        },
        breadcrumb_json(items),
        {
            "@type": "Article",
            "@id": url + "#article",
            "headline": article_headline,
            "description": clean_text(article_html)[:240] or description,
            "image": image_url,
            "inLanguage": "ko-KR",
            "author": {"@id": org_id},
            "publisher": {"@type": "Organization", "name": SITE_NAME, "url": "/"},
            "mainEntityOfPage": {"@id": url + "#webpage"},
        },
        {
            "@type": "FAQPage",
            "@id": url + "#faq",
            "mainEntity": [
                {"@type": "Question", "name": item["question"], "acceptedAnswer": {"@type": "Answer", "text": item["answer"]}}
                for item in faqs
            ],
        },
    ]
    return {"@context": "https://schema.org", "@graph": graph}


def header(root_rel: str, active: str = "전국학원") -> str:
    def nav(label: str, href: str) -> str:
        active_class = ' class="active"' if label == active else ""
        return f'<a{active_class} href="{href}">{label}</a>'
    return f"""  <header class="site-header">
    <nav class="nav" aria-label="주요 메뉴">
      <a class="brand" href="{root_rel}/"><span class="brand-mark">L</span><span>{SITE_NAME}</span></a>
      <div class="nav-links">
        {nav("홈", root_rel + "/")}
        {nav("학습관리", root_rel + "/학습관리/")}
        {nav("진단상담", root_rel + "/진단상담/")}
        {nav("학습가이드", root_rel + "/학습가이드/")}
        {nav("전국학원", root_rel + "/전국학원/")}
        {nav("상담문의", root_rel + "/상담문의/")}
      </div>
      <a class="nav-cta" href="{root_rel}/상담문의/">상담 신청</a>
    </nav>
  </header>
"""


def consult_footer(root_rel: str, title: str) -> str:
    return f"""
  <section class="consult-strip" aria-label="상담 신청 안내">
    <div class="wrap consult-strip-card">
      <div>
        <p class="eyebrow">consultation</p>
        <h2>{html.escape(strip_academy_suffix(title))} 학습 상담이 필요하다면 현재 상태부터 정리해 보세요.</h2>
        <p>학년, 과목, 최근 시험과 반복되는 고민을 알려주시면 필요한 관리 기준을 함께 확인할 수 있습니다.</p>
      </div>
      <div class="consult-strip-actions">
        <a class="btn btn-primary" href="{FORM_URL}" target="_blank" rel="noopener">상담 신청</a>
        <a class="btn" href="tel:{PHONE}">전화 문의</a>
      </div>
    </div>
  </section>

  <footer class="site-footer"><div class="wrap footer-inner"><strong>{SITE_NAME}</strong><div class="footer-links"><a href="{root_rel}/학습관리/">학습관리</a><a href="{root_rel}/진단상담/">진단상담</a><a href="{root_rel}/전국학원/">전국학원</a><a href="{root_rel}/상담문의/">상담문의</a></div><div class="footer-contact"><span>상담 전화</span><a href="tel:{PHONE}">{PHONE}</a></div></div></footer>
  <div class="floating-actions" aria-label="빠른 상담 메뉴">
    <a href="tel:{PHONE}" class="fab-call"><span class="fab-icon">&#128222;</span><span class="fab-text">전화문의</span></a>
    <a href="https://blogsms.net/01039578283" target="_blank" rel="noopener" class="fab-sms"><span class="fab-icon">&#128172;</span><span class="fab-text">문자문의</span></a>
    <a href="{FORM_URL}" target="_blank" rel="noopener" class="fab-consult pulse-effect"><span class="fab-icon">&#128221;</span><span class="fab-text">상담신청</span></a>
  </div>
"""


def create_page(row: list[str]) -> dict:
    title, hidden, class_image, map_image, article_raw, center_raw, parent_raw, slug_raw = [canonical_text(item.strip()) for item in row[:8]]
    parent_dir = ROOT / normalize_slug(parent_raw)
    slug = normalize_slug(slug_raw)
    page_dir = parent_dir / slug
    page_dir.mkdir(parents=True, exist_ok=True)
    root_rel = rel_to_root(page_dir)
    url = root_url_for(page_dir)
    faqs = select_items(FAQ_POOL, page_dir, "faq", 5)
    reviews = selected_reviews(page_dir)
    class_src = asset_src(root_rel, "assets/centers/common", class_image)
    map_src = asset_src(root_rel, "assets/maps", map_image)
    image_url = img_src_from_html(hidden) or urljoin(url, class_src)
    article_html = normalize_article_heading(normalize_fragment(article_raw) or fallback_article(title), title, page_dir)
    center_html = normalize_fragment(center_raw)
    ld = page_json_ld(page_dir, title, article_html, center_html, faqs, reviews, image_url)

    page = f"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)} | {SITE_NAME}</title>
  <meta name="description" content="{html.escape(title)} 안내입니다. 학습 진단, 플래너 관리, 오답 재학습과 센터 위치 정보를 확인해보세요.">
  <meta name="robots" content="index, follow">
  <link rel="icon" type="image/png" href="{root_rel}/assets/favicon.png">
  <link rel="stylesheet" href="{root_rel}/assets/site.css">
  <script type="application/ld+json">{json.dumps(ld, ensure_ascii=False)}</script>
</head>
<body>
  <a class="skip-link" href="#main">본문 바로가기</a>
{header(root_rel)}
  <main id="main">
    <section class="page-hero generated-page-hero">
      <div class="wrap page-hero-inner">
        <div>
          <div class="breadcrumb"><a href="{root_rel}/">홈</a> › <a href="{root_rel}/전국학원/">전국학원</a> › {html.escape(strip_academy_suffix(title))}</div>
          <p class="eyebrow">local academy guide</p>
          <h1>{html.escape(title)} 학습 안내</h1>
          <p>{html.escape(strip_academy_suffix(title))}에서 학원을 찾는 학생과 학부모를 위해 상담, 진단, 플래너, 오답 관리 기준을 정리했습니다.</p>
        </div>
      </div>
    </section>
    {hidden_image_markup(hidden, title)}
    <section class="section">
      <div class="wrap bulk-image-grid">
{image_card(title, class_src, image_alt(title, class_image, "class"), f"{title} 수업 안내")}{image_card(title, map_src, image_alt(title, map_image, "map"), f"{title} 위치 안내")}
      </div>
    </section>
    {article_html}
    {support_section(title)}
    {center_html}
    {faq_section(title, faqs)}
    {review_section(title, reviews)}
  </main>
{consult_footer(root_rel, title)}
</body>
</html>
"""
    (page_dir / "index.html").write_text(page, encoding="utf-8")
    return {"title": title, "page_dir": page_dir, "parent_dir": parent_dir, "slug": slug}


def hub_json_ld(hub_dir: Path, title: str, child_items: list[dict]) -> dict:
    url = root_url_for(hub_dir)
    return {
        "@context": "https://schema.org",
        "@graph": [
            {"@type": "CollectionPage", "@id": url + "#webpage", "url": url, "name": title, "description": f"{title} 지역별 학원 페이지 모음입니다.", "inLanguage": "ko-KR", "breadcrumb": {"@id": url + "#breadcrumb"}},
            breadcrumb_json(breadcrumb_chain(hub_dir, title)),
            {"@type": "ItemList", "@id": url + "#item-list", "name": title, "itemListElement": [{"@type": "ListItem", "position": i, "name": item["name"], "url": item["url"]} for i, item in enumerate(child_items, 1)]},
        ],
    }


def child_names_for_card(child_dir: Path, academy_titles: dict[Path, str]) -> list[str]:
    names = []
    for sub in sorted([p for p in child_dir.iterdir() if p.is_dir()], key=lambda p: p.name):
        if sub in academy_titles:
            names.append(strip_academy_suffix(academy_titles[sub]))
        else:
            names.append(sub.name)
    return names


def hub_child_html(names: list[str], limit: int = 8) -> str:
    if not names:
        return ""
    shown = names[:limit]
    parts = [f"<em>{html.escape(name)}</em>" for name in shown]
    if len(names) > limit:
        parts.append(f'<em class="more">+{len(names) - limit}</em>')
    return f'<div class="hub-child-list">{"".join(parts)}</div>'


def guide_preview_section(root_rel: str) -> str:
    items = [
        ("학습 진단 상담 준비", "성적표, 오답, 공부 습관을 상담 전 어떻게 정리하면 좋은지 안내합니다.", f"{root_rel}/진단상담/"),
        ("플래너 관리 방법", "계획표를 쓰는 데서 끝나지 않고 실행률을 높이는 관리 기준을 설명합니다.", f"{root_rel}/학습관리/"),
        ("오답 관리 방법", "틀린 문제를 점수로 연결하기 위해 원인을 나누고 반복 주기를 정합니다.", f"{root_rel}/학습관리/"),
        ("시험 기간 계획표", "시험 4주 전부터 직전까지 영어·수학 공부 순서를 나누는 기준을 정리합니다.", f"{root_rel}/학습가이드/"),
        ("지역별 학원 선택 기준", "가까운 위치뿐 아니라 상담 구조와 학습관리 방식을 함께 비교합니다.", f"{root_rel}/전국학원/"),
        ("중고등 영어수학 관리", "학년이 올라갈수록 필요한 내신 대비, 개념 정리, 오답 루틴을 구분합니다.", f"{root_rel}/학습관리/"),
    ]
    cards = "\n".join(
        f"""        <a class="guide-card hub-guide-card" href="{html.escape(href)}"><small>GUIDE</small><h3>{html.escape(title)}</h3><p>{html.escape(desc)}</p></a>"""
        for title, desc, href in items
    )
    return f"""    <section class="section hub-guide-section">
      <div class="wrap">
        <div class="section-head"><div><p class="eyebrow">learning guide</p><h2>학원 선택 전 함께 보면 좋은 학습가이드</h2></div><p>지역 페이지를 보기 전, 학생에게 필요한 관리 기준을 짧게 확인할 수 있도록 핵심 가이드를 모았습니다.</p></div>
        <div class="guide-grid">
{cards}
        </div>
      </div>
    </section>
"""


def write_hub_page(hub_dir: Path, title: str, child_items: list[dict], guide_preview: bool = False) -> None:
    hub_dir.mkdir(parents=True, exist_ok=True)
    root_rel = rel_to_root(hub_dir)
    def card_description(item: dict) -> str:
        if item.get("lesson_meta"):
            return """<div class="hub-lesson-meta" aria-label="수업 가능 정보"><div><small>수업 가능 과목</small><b>국어 · 영어 · 수학</b></div><div><small>수업 가능 학년</small><b>고등반 · 중등반 · 초등반</b></div></div>"""
        return f"<p>{html.escape(item['description'])}</p>"

    cards = "\n".join(
        f"""        <a class="hub-card" href="{html.escape(item['href'])}"><span>{html.escape(item['kicker'])}</span><strong>{html.escape(item['name'])}</strong>{card_description(item)}{item.get('children_html', '')}</a>"""
        for item in child_items
    )
    guide_section = guide_preview_section(root_rel) if guide_preview else ""
    ld = hub_json_ld(hub_dir, title, child_items)
    page = f"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)} | {SITE_NAME}</title>
  <meta name="description" content="{html.escape(title)} 지역별 학원 안내 페이지입니다.">
  <meta name="robots" content="index, follow">
  <link rel="icon" type="image/png" href="{root_rel}/assets/favicon.png">
  <link rel="stylesheet" href="{root_rel}/assets/site.css">
  <script type="application/ld+json">{json.dumps(ld, ensure_ascii=False)}</script>
</head>
<body>
  <a class="skip-link" href="#main">본문 바로가기</a>
{header(root_rel)}
  <main id="main">
    <section class="hub-hero page-hero">
      <div class="wrap">
        <div class="hub-hero-head">
          <div class="breadcrumb"><a href="{root_rel}/">홈</a> › <a href="{root_rel}/전국학원/">전국학원</a> › {html.escape(title)}</div>
          <p class="eyebrow">academy hub</p>
          <h1>{html.escape(title)} 바로가기</h1>
          <p>아래 지역 버튼에서 하위 지역을 확인하고 원하는 학원 안내 페이지로 이동하세요.</p>
        </div>
        <div class="hub-grid">
{cards}
        </div>
      </div>
    </section>
{guide_section}  </main>
{consult_footer(root_rel, title)}
</body>
</html>
"""
    (hub_dir / "index.html").write_text(page, encoding="utf-8")


def build_hubs(created: list[dict]) -> None:
    center_root = ROOT / "전국학원"
    academy_titles = collect_academy_titles()
    academy_titles.update({item["page_dir"]: item["title"] for item in created})
    academy_dirs = set(academy_titles)
    leaf_dirs = sorted(academy_dirs)
    hub_dirs = set()
    for leaf in leaf_dirs:
        current = leaf.parent
        while current != ROOT and current.is_relative_to(center_root):
            if current not in academy_dirs:
                hub_dirs.add(current)
            current = current.parent
    hub_dirs.add(center_root)

    for hub_dir in sorted(hub_dirs, key=lambda p: len(p.relative_to(ROOT).parts), reverse=True):
        if hub_dir in academy_dirs:
            continue
        child_dirs = sorted([p for p in hub_dir.iterdir() if p.is_dir()])
        items = []
        for child in child_dirs:
            if child.name in {"assets", "tmp"}:
                continue
            if child in academy_titles:
                name = strip_academy_suffix(academy_titles[child])
                kicker = "ACADEMY"
                desc = "국어, 영어, 수학 수업과 고3부터 초1까지 학년별 학습 관리를 안내합니다."
                lesson_meta = True
            else:
                name = child.name
                kicker = "AREA"
                desc = "하위 지역 학원 페이지를 확인할 수 있습니다."
                lesson_meta = False
            if not (child / "index.html").exists() and child not in academy_titles:
                continue
            child_names = child_names_for_card(child, academy_titles)
            items.append({
                "name": name,
                "href": rel_href(hub_dir, child / "index.html"),
                "url": root_url_for(child),
                "kicker": kicker,
                "description": desc,
                "lesson_meta": lesson_meta,
                "children_html": hub_child_html(child_names, 10 if hub_dir == center_root else 12),
            })
        title = "전국학원" if hub_dir == center_root else hub_dir.name
        write_hub_page(hub_dir, title, items, guide_preview=True)


def main() -> None:
    rows = csv_rows()
    created = [create_page(row) for row in rows]
    update_parent_child_link_sections(created)
    build_hubs(created)
    print(f"created_pages={len(created)}")
    print(f"first={created[0]['page_dir'].relative_to(ROOT).as_posix() if created else ''}")
    print(f"last={created[-1]['page_dir'].relative_to(ROOT).as_posix() if created else ''}")


if __name__ == "__main__":
    main()
