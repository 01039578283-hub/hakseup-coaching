# -*- coding: utf-8 -*-
"""학습코칭.kr 1순위/2순위 보강.

- 전국학원 하위 동네/자식 페이지의 검색의도 답변 섹션을 더 선명하게 교체
- 동네 부모 페이지의 붙은 키워드(예: 명일동학원)를 자연 검색어(명일동 학원)로 정리
- 누락된 봉담2지구 고등영수학원 페이지 생성
- 실제 존재하는 자식 페이지 기준으로 내부링크 갱신
- JSON-LD / sitemap 함께 정리
"""

from __future__ import annotations

import html
import json
import re
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import quote


BASE_URL = "https://xn--ru4bi8s1tac0p.kr"
SITE_SUFFIX = "학습코칭 연구소"
TODAY = "2026-07-16"
SEO_START = "<!-- seo-geo-enhancement:start -->"
SEO_END = "<!-- seo-geo-enhancement:end -->"
LINK_START = "<!-- child-page-links:start -->"
LINK_END = "<!-- child-page-links:end -->"
LOCAL_ROOT_NAME = "전국학원"
CHILD_ORDER = ["고등영수학원", "중등영수학원", "초등영수학원"]


def strip_tags(value: str) -> str:
    value = re.sub(r"<[^>]+>", " ", value, flags=re.S)
    return html.unescape(re.sub(r"\s+", " ", value).strip())


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def write(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8", newline="\n")


def url_for(root: Path, page: Path) -> str:
    rel = page.relative_to(root).as_posix()
    if rel.endswith("index.html"):
        rel = rel[: -len("index.html")]
    return BASE_URL + "/" + quote(rel, safe="/") if rel else BASE_URL + "/"


def page_parts(page: Path, local_root: Path) -> tuple[str, ...]:
    return page.relative_to(local_root).parts[:-1]


def is_local_or_child(page: Path, local_root: Path) -> bool:
    depth = len(page_parts(page, local_root))
    return depth in (3, 4)


def is_parent_page(page: Path, local_root: Path) -> bool:
    return len(page_parts(page, local_root)) == 3


def context_for(page: Path, root: Path, local_root: Path, text: str) -> dict[str, str]:
    parts = page_parts(page, local_root)
    region, city, dong = parts[0], parts[1], parts[2]
    child = parts[3] if len(parts) == 4 else ""
    h1 = re.search(r"<h1\b[^>]*>(.*?)</h1>", text, flags=re.S | re.I)
    raw_title = strip_tags(h1.group(1)) if h1 else dong + (" " + child if child else " 학원")
    old_parent_title = f"{dong}학원"
    if not child and raw_title == old_parent_title:
        display_title = f"{dong} 학원"
    else:
        display_title = raw_title
    topic = display_title.replace(dong, "", 1).strip() if display_title.startswith(dong) else display_title
    topic = topic or "학원"
    grade = "초등·중등·고등"
    if "고등" in display_title:
        grade = "고등"
    elif "중등" in display_title:
        grade = "중등"
    elif "초등" in display_title:
        grade = "초등"
    subjects = "영어·수학"
    if not child:
        subjects = "국어·영어·수학"
    return {
        "region": region,
        "city": city,
        "dong": dong,
        "child": child,
        "raw_title": raw_title,
        "display_title": display_title,
        "topic": topic,
        "grade": grade,
        "subjects": subjects,
        "region_line": f"{region} {city} {dong}",
        "url": url_for(root, page),
    }


def description_for(ctx: dict[str, str]) -> str:
    title = ctx["display_title"]
    if ctx["child"]:
        return (
            f"{title} 안내입니다. {ctx['region']} {ctx['city']} {ctx['dong']} 기준으로 "
            f"{ctx['subjects']} 학습 진단, {ctx['grade']} 수업 흐름, 플래너 관리, "
            "오답 재학습, 상담 전 확인사항을 정리했습니다."
        )
    return (
        f"{title} 안내입니다. {ctx['region']} {ctx['city']} {ctx['dong']}에서 "
        "영어·수학 학원 선택 전 학습 진단, 플래너 관리, 오답 재학습, "
        "초등·중등·고등 상담 기준을 한 번에 확인하세요."
    )


def replace_meta(text: str, name: str, content: str) -> str:
    escaped = html.escape(content, quote=True)
    pattern1 = re.compile(
        rf'(<meta\s+[^>]*name=["\']{re.escape(name)}["\'][^>]*content=["\'])(.*?)(["\'][^>]*>)',
        flags=re.I | re.S,
    )
    if pattern1.search(text):
        return pattern1.sub(rf"\g<1>{escaped}\g<3>", text, count=1)
    pattern2 = re.compile(
        rf'(<meta\s+[^>]*content=["\'])(.*?)(["\'][^>]*name=["\']{re.escape(name)}["\'][^>]*>)',
        flags=re.I | re.S,
    )
    if pattern2.search(text):
        return pattern2.sub(rf"\g<1>{escaped}\g<3>", text, count=1)
    return text


def replace_property(text: str, prop: str, content: str) -> str:
    escaped = html.escape(content, quote=True)
    pattern = re.compile(
        rf'(<meta\s+[^>]*property=["\']{re.escape(prop)}["\'][^>]*content=["\'])(.*?)(["\'][^>]*>)',
        flags=re.I | re.S,
    )
    return pattern.sub(rf"\g<1>{escaped}\g<3>", text, count=1)


def type_contains(node: dict[str, Any], needle: str) -> bool:
    node_type = node.get("@type")
    if isinstance(node_type, list):
        return needle in node_type
    return node_type == needle


def replace_strings(value: Any, old: str, new: str) -> Any:
    if isinstance(value, str):
        return value.replace(old, new)
    if isinstance(value, list):
        return [replace_strings(v, old, new) for v in value]
    if isinstance(value, dict):
        return {k: replace_strings(v, old, new) for k, v in value.items()}
    return value


def update_jsonld(text: str, ctx: dict[str, str], desc: str) -> str:
    m = re.search(r'<script type="application/ld\+json">(.*?)</script>', text, flags=re.S | re.I)
    if not m:
        return text
    try:
        data = json.loads(m.group(1))
    except json.JSONDecodeError:
        return text

    if ctx["raw_title"] != ctx["display_title"]:
        data = replace_strings(data, ctx["raw_title"], ctx["display_title"])

    graph = data.get("@graph") if isinstance(data, dict) else None
    nodes = graph if isinstance(graph, list) else [data] if isinstance(data, dict) else []
    for node in nodes:
        if not isinstance(node, dict):
            continue
        if "url" in node:
            node["url"] = ctx["url"]
        if type_contains(node, "WebPage"):
            node["name"] = ctx["display_title"]
            node["description"] = desc
        if type_contains(node, "Article"):
            node["headline"] = ctx["display_title"]
            node["description"] = desc
            node["dateModified"] = TODAY
            node["articleSection"] = [
                "검색의도 요약",
                "지역·학년·추천학생",
                "답변형 학습 안내",
                "상담 전 체크리스트",
                "FAQ",
                "학부모 후기",
                "내부링크",
            ]
        if type_contains(node, "Service"):
            node["name"] = f"{ctx['display_title']} 학습코칭"
            node["serviceType"] = f"{ctx['display_title']} 상담 및 학습관리"
            node["description"] = (
                f"{ctx['region_line']} 학생을 위한 {ctx['subjects']} 학습 진단, "
                "플래너 관리, 오답 재학습 안내입니다."
            )
        if type_contains(node, "EducationalOrganization") or type_contains(node, "LocalBusiness"):
            if node.get("name") == ctx["raw_title"] or node.get("name") == ctx["display_title"]:
                node["name"] = ctx["display_title"]
        if type_contains(node, "ItemList"):
            node["name"] = f"{ctx['display_title']} 상담 전 체크리스트"
        if type_contains(node, "BreadcrumbList"):
            for item in node.get("itemListElement", []):
                if isinstance(item, dict) and item.get("position") == len(node.get("itemListElement", [])):
                    if isinstance(item.get("item"), dict):
                        item["item"]["name"] = ctx["display_title"]
                    else:
                        item["name"] = ctx["display_title"]

    new_json = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    return text[: m.start()] + f'<script type="application/ld+json">{new_json}</script>' + text[m.end() :]


def seo_block(ctx: dict[str, str]) -> str:
    title = html.escape(ctx["display_title"])
    dong = html.escape(ctx["dong"])
    region_line = html.escape(ctx["region_line"])
    topic = html.escape(ctx["topic"])
    grade = html.escape(ctx["grade"])
    subjects = html.escape(ctx["subjects"])
    grade_student = {
        "고등": "고등학생",
        "중등": "중학생",
        "초등": "초등학생",
    }.get(ctx["grade"], "초등·중등·고등 학생")

    if ctx["child"]:
        student_line = f"{html.escape(grade_student)} 중 {subjects} 개념은 아는데 시험·숙제·오답 관리가 흔들리는 경우"
        first_answer = (
            f"{region_line}에서 {topic}을 찾는다면, 먼저 학생의 현재 단원 이해도와 "
            "반복 오답, 시험 전 계획 실행 여부를 함께 확인하는 것이 좋습니다."
        )
    else:
        student_line = "초등·중등·고등 중 현재 공부 습관과 과목별 공백을 함께 점검해야 하는 경우"
        first_answer = (
            f"{region_line}에서 {title}을 찾는다면, 단순히 가까운 학원인지보다 "
            "학습 진단, 주간 플래너, 오답 재학습, 학부모 피드백이 이어지는지 먼저 확인하는 것이 좋습니다."
        )

    return f"""{SEO_START}
<section class="seo-answer-section" aria-labelledby="seo-intent-title">
  <div class="seo-answer-copy">
    <p class="parent-faq-eyebrow">SEARCH INTENT ANSWER</p>
    <h2 id="seo-intent-title">{title}, 먼저 이렇게 확인하세요</h2>
    <p>{first_answer}</p>
  </div>
  <div class="seo-answer-list">
    <article><b>찾는 의도</b><p>{dong}에서 {topic}을 알아보는 학부모가 수업 전 확인해야 할 기준을 바로 정리했습니다.</p></article>
    <article><b>추천 학생</b><p>{student_line}에 특히 적합합니다.</p></article>
    <article><b>상담 핵심</b><p>최근 시험지, 현재 교재, 숙제 실행 정도, 반복 오답을 바탕으로 관리 순서를 정합니다.</p></article>
  </div>
</section>

<section class="seo-geo-section" aria-labelledby="seo-geo-summary-title">
  <div class="seo-geo-head">
    <p class="parent-faq-eyebrow">SEO · AEO · GEO SUMMARY</p>
    <h2 id="seo-geo-summary-title">{title} 핵심 요약</h2>
    <p>{region_line} 기준으로 {subjects} 학습 진단, 플래너 관리, 오답 재학습, 상담 전 확인사항을 답변형으로 정리했습니다.</p>
  </div>
  <div class="seo-geo-grid">
    <article class="seo-geo-card"><span>지역 기준</span><strong>{region_line}</strong><p>페이지의 지역명과 실제 상담 생활권을 분명하게 연결해 검색 의도를 좁혔습니다.</p></article>
    <article class="seo-geo-card"><span>관리 과목</span><strong>{subjects}</strong><p>개념 확인, 문제 풀이, 오답 재학습, 시험 전 계획을 한 흐름으로 봅니다.</p></article>
    <article class="seo-geo-card"><span>대상 학년</span><strong>{grade}</strong><p>학년별 현재 수준과 시험 준비 흐름에 맞춰 상담 기준을 조정합니다.</p></article>
  </div>
</section>

<section class="seo-answer-section" aria-labelledby="seo-answer-title">
  <div class="seo-answer-copy">
    <p class="parent-faq-eyebrow">ANSWER READY</p>
    <h2 id="seo-answer-title">{title} 상담에서 바로 물어볼 내용</h2>
    <p>이 페이지는 단순 소개보다 “우리 아이에게 필요한 관리인지, 어떤 자료를 가져가야 하는지, 상담 후 어떤 기준으로 결정하면 좋은지”를 빠르게 판단하도록 구성했습니다.</p>
  </div>
  <div class="seo-answer-list">
    <article><b>현재 수준</b><p>점수보다 단원별 이해도, 풀이 과정, 숙제 수행 정도를 먼저 봅니다.</p></article>
    <article><b>관리 방식</b><p>진단 → 계획 → 수업 확인 → 오답 재학습 → 학부모 피드백 흐름으로 이어지는지 확인합니다.</p></article>
    <article><b>비교 기준</b><p>수업 횟수만 비교하지 말고 학생에게 필요한 피드백 강도와 시험 전 계획표를 함께 봅니다.</p></article>
  </div>
</section>

<section class="seo-checklist-section" aria-labelledby="seo-checklist-title">
  <div class="seo-geo-head">
    <p class="parent-faq-eyebrow">CONSULTING CHECKLIST</p>
    <h2 id="seo-checklist-title">{title} 상담 전 체크리스트</h2>
    <p>상담 전에 아래 자료를 정리하면 학생에게 맞는 관리 방식을 더 정확하게 찾을 수 있습니다.</p>
  </div>
  <ol class="seo-checklist">
    <li><b>현재 교재</b><span>사용 중인 교재와 진도, 어려워하는 단원을 확인합니다.</span></li>
    <li><b>최근 시험지</b><span>점수보다 반복되는 오답 유형과 실수 패턴을 봅니다.</span></li>
    <li><b>공부 루틴</b><span>평일·주말 공부 시간과 숙제 실행 정도를 정리합니다.</span></li>
    <li><b>상담 목표</b><span>성적, 습관, 오답, 시험 대비 중 우선순위를 정합니다.</span></li>
  </ol>
</section>
{SEO_END}"""


def replace_between(text: str, start: str, end: str, replacement: str) -> tuple[str, bool]:
    a = text.find(start)
    b = text.find(end)
    if a == -1 or b == -1 or b < a:
        return text, False
    b += len(end)
    return text[:a] + replacement + text[b:], True


def available_children(local_dir: Path) -> list[str]:
    children = [c.name for c in local_dir.iterdir() if c.is_dir() and (c / "index.html").exists()]
    return sorted(children, key=lambda x: (CHILD_ORDER.index(x) if x in CHILD_ORDER else 99, x))


def link_card_text(child: str) -> tuple[str, str]:
    if "고등" in child:
        return "고등 과정", "내신·모의고사 흐름과 영어·수학 오답 관리를 확인합니다."
    if "중등" in child:
        return "중등 과정", "학교 진도, 수행평가, 시험 대비 흐름을 함께 확인합니다."
    if "초등" in child:
        return "초등 과정", "기초 개념, 학습 습관, 영어·수학 기본기를 함께 확인합니다."
    return "상세 과정", "학년별 영어·수학 관리 기준을 더 구체적으로 확인합니다."


def display_child_name(child: str) -> str:
    return (
        child.replace("고등영수학원", "고등 영수학원")
        .replace("중등영수학원", "중등 영수학원")
        .replace("초등영수학원", "초등 영수학원")
    )


def child_links_block(page: Path, local_root: Path, ctx: dict[str, str]) -> str:
    parts = page_parts(page, local_root)
    local_dir = local_root / parts[0] / parts[1] / parts[2]
    children = available_children(local_dir)
    title = html.escape(ctx["dong"])

    cards: list[str] = []
    if len(parts) == 4:
        cards.append(
            f'''    <a class="child-link-card" href="../">
      <span>지역 종합</span>
      <strong>{html.escape(ctx['dong'])} 학원 안내</strong>
      <p>{html.escape(ctx['dong'])} 위치, 상담 기준, 학년별 학습 흐름을 한 번에 확인합니다.</p>
    </a>'''
        )
    for child in children:
        if len(parts) == 4 and child == parts[3]:
            continue
        label, desc = link_card_text(child)
        href = f"{child}/" if len(parts) == 3 else f"../{child}/"
        name = display_child_name(child)
        cards.append(
            f'''    <a class="child-link-card" href="{html.escape(href)}">
      <span>{html.escape(label)}</span>
      <strong>{html.escape(ctx['dong'])} {html.escape(name)}</strong>
      <p>{html.escape(desc)}</p>
    </a>'''
        )

    return f'''{LINK_START}
    <section class="child-page-links" aria-labelledby="child-page-links-title">
      <div class="child-page-links-head">
        <p class="parent-faq-eyebrow">LOCAL STUDY LINKS</p>
        <h2 id="child-page-links-title">{title} 학습 페이지 바로가기</h2>
        <p>{title} 안에서 학년별 영어·수학 관리 페이지를 깔끔하게 비교할 수 있도록 정리했습니다.</p>
      </div>
      <div class="child-link-grid">
{chr(10).join(cards)}
      </div>
    </section>
    {LINK_END}'''


def update_head_and_text(text: str, ctx: dict[str, str], desc: str) -> str:
    title = f"{ctx['display_title']} | {SITE_SUFFIX}"
    text = re.sub(r"<title[^>]*>.*?</title>", f"<title>{html.escape(title)}</title>", text, count=1, flags=re.S | re.I)
    text = replace_meta(text, "description", desc)
    text = replace_property(text, "og:title", title)
    text = replace_property(text, "og:description", desc)
    text = replace_property(text, "og:url", ctx["url"])
    text = replace_property(text, "twitter:title", title)
    text = replace_property(text, "twitter:description", desc)
    canonical = re.compile(r'(<link\s+rel=["\']canonical["\']\s+href=["\'])(.*?)(["\'][^>]*>)', flags=re.S | re.I)
    text = canonical.sub(rf"\g<1>{html.escape(ctx['url'], quote=True)}\g<3>", text, count=1)
    if ctx["raw_title"] != ctx["display_title"]:
        text = text.replace(ctx["raw_title"], ctx["display_title"])
    return text


def update_page(page: Path, root: Path, local_root: Path) -> bool:
    text = read(page)
    ctx = context_for(page, root, local_root, text)
    desc = description_for(ctx)
    new = update_head_and_text(text, ctx, desc)
    ctx = context_for(page, root, local_root, new)
    desc = description_for(ctx)
    new = update_jsonld(new, ctx, desc)
    new, ok = replace_between(new, SEO_START, SEO_END, seo_block(ctx))
    if not ok:
        raise RuntimeError(f"SEO block markers not found: {page}")
    new, link_ok = replace_between(new, LINK_START, LINK_END, child_links_block(page, local_root, ctx))
    if not link_ok:
        raise RuntimeError(f"child link markers not found: {page}")
    if new != text:
        write(page, new)
        return True
    return False


def create_missing_bongdam_page(root: Path, local_root: Path) -> Path:
    city_dir = local_root / "경기" / "화성시"
    src = city_dir / "봉담읍" / "고등영수학원" / "index.html"
    dst_dir = city_dir / "봉담2지구" / "고등영수학원"
    dst = dst_dir / "index.html"
    if dst.exists():
        return dst
    dst_dir.mkdir(parents=True, exist_ok=True)
    text = read(src)
    old = "봉담읍"
    new = "봉담2지구"
    text = text.replace(old, new)
    text = text.replace(quote(old), quote(new))
    text = text.replace("bongdameup", "bongdam2jigu")
    text = text.replace("Bongdam Eup", "Bongdam 2 Jigu")
    write(dst, text)
    return dst


def update_sitemap(root: Path) -> None:
    sitemap = root / "sitemap.xml"
    urls: list[str] = []
    for p in sorted(x for x in root.rglob("index.html") if ".git" not in x.parts and ".vercel" not in x.parts and "tmp" not in x.parts):
        urls.append(url_for(root, p))
    # Keep only site files and remove duplicates.
    seen: set[str] = set()
    unique: list[str] = []
    for u in urls:
        if u not in seen:
            unique.append(u)
            seen.add(u)
    body = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for u in unique:
        body.append("  <url>")
        body.append(f"    <loc>{u}</loc>")
        body.append(f"    <lastmod>{TODAY}</lastmod>")
        body.append("  </url>")
    body.append("</urlset>")
    write(sitemap, "\n".join(body) + "\n")


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    local_root = root / LOCAL_ROOT_NAME
    missing = create_missing_bongdam_page(root, local_root)
    pages = [p for p in sorted(local_root.rglob("index.html")) if is_local_or_child(p, local_root)]
    updated = 0
    for page in pages:
        if update_page(page, root, local_root):
            updated += 1
    update_sitemap(root)
    print(f"missing page ensured: {missing.relative_to(root).as_posix()}")
    print(f"target pages: {len(pages)}")
    print(f"updated pages: {updated}")


if __name__ == "__main__":
    main()
