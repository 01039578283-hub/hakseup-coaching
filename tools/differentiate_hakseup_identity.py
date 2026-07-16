from __future__ import annotations

import hashlib
import html
import json
import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
BASE_URL = "https://xn--ru4bi8s1tac0p.kr"
SITE_NAME = "학습코칭.kr"
BRAND_NAME = "학습코칭 연구소"

SKIP_DIRS = {".git", ".vercel", "tmp"}
SERVICE_SLUGS = {"고등영수학원", "중등영수학원", "초등영수학원"}
TOP_LEVEL_RELS = {
    "index.html",
    "학습가이드/index.html",
    "학습관리/index.html",
    "진단상담/index.html",
    "상담문의/index.html",
    "전국학원/index.html",
}

START = "<!-- coaching-identity:start -->"
END = "<!-- coaching-identity:end -->"
CSS_START = "/* coaching-identity:start */"
CSS_END = "/* coaching-identity:end */"


def stable_pick(seed: str, items: list[str], offset: int = 0) -> str:
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    return items[(int(digest[offset : offset + 8], 16) + offset) % len(items)]


def escape(value: str) -> str:
    return html.escape(value, quote=True)


def topic_particle(value: str) -> str:
    value = (value or "").strip()
    if not value:
        return "은"
    last = value[-1]
    code = ord(last)
    if 0xAC00 <= code <= 0xD7A3:
        return "은" if (code - 0xAC00) % 28 else "는"
    return "은"


def strip_tags(value: str) -> str:
    value = re.sub(r"<br\s*/?>", " ", value or "", flags=re.I)
    value = re.sub(r"<[^>]+>", " ", value)
    value = html.unescape(value)
    return re.sub(r"\s+", " ", value).strip()


def get_tag_text(doc: str, tag: str) -> str:
    match = re.search(rf"<{tag}\b[^>]*>(.*?)</{tag}>", doc, re.I | re.S)
    return strip_tags(match.group(1)) if match else ""


def get_meta_description(doc: str) -> str:
    match = re.search(
        r'<meta\s+name="description"\s+content="([^"]*)"', doc, re.I | re.S
    )
    return html.unescape(match.group(1)).strip() if match else ""


def replace_meta_description(doc: str, description: str) -> str:
    description = escape(description)
    pattern = r'(<meta\s+name="description"\s+content=")([^"]*)(")'
    if re.search(pattern, doc, re.I | re.S):
        return re.sub(pattern, rf"\g<1>{description}\g<3>", doc, count=1, flags=re.I | re.S)
    head = re.search(r"</head>", doc, re.I)
    if head:
        return doc[: head.start()] + f'  <meta name="description" content="{description}">\n' + doc[head.start() :]
    return doc


def page_rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def is_real_html(path: Path) -> bool:
    if path.name != "index.html":
        return False
    rel_parts = path.relative_to(ROOT).parts
    return not any(part in SKIP_DIRS for part in rel_parts)


def is_target_page(path: Path) -> bool:
    rel = page_rel(path)
    return rel in TOP_LEVEL_RELS or rel.startswith("전국학원/")


def clean_display_title(h1: str, title: str) -> str:
    base = h1 or title.split("|")[0].strip()
    base = re.sub(r"\s+", " ", base).strip()
    return base or "학습코칭"


def page_context(path: Path, doc: str) -> dict[str, str]:
    rel = page_rel(path)
    h1 = clean_display_title(get_tag_text(doc, "h1"), get_tag_text(doc, "title"))
    dirs = path.relative_to(ROOT).parts[:-1]

    top_titles = {
        "index.html": "학습코칭.kr",
        "학습가이드/index.html": "학습가이드",
        "학습관리/index.html": "학습관리 방식",
        "진단상담/index.html": "진단상담",
        "상담문의/index.html": "상담문의",
        "전국학원/index.html": "전국학원 안내",
    }
    if rel in top_titles:
        h1 = top_titles[rel]

    context = {
        "rel": rel,
        "title": h1,
        "location": h1,
        "area": "",
        "city": "",
        "service": "",
        "grade": "초등·중등·고등",
        "subject": "국어·영어·수학",
        "kind": "top",
    }

    top_locations = {
        "index.html": "학습코칭",
        "학습가이드/index.html": "학습가이드",
        "학습관리/index.html": "학습관리",
        "진단상담/index.html": "진단상담",
        "상담문의/index.html": "상담문의",
        "전국학원/index.html": "전국학원",
    }
    if rel in top_locations:
        context["location"] = top_locations[rel]

    if dirs and dirs[0] == "전국학원":
        context["kind"] = "academy"
        if len(dirs) >= 2:
            context["area"] = dirs[1]
        if len(dirs) >= 3:
            context["city"] = dirs[2]
        if dirs[-1] in SERVICE_SLUGS and len(dirs) >= 2:
            context["kind"] = "child"
            context["service"] = dirs[-1]
            context["location"] = dirs[-2]
        elif len(dirs) >= 4:
            context["kind"] = "local"
            context["location"] = dirs[-1]
        elif len(dirs) >= 2:
            context["kind"] = "hub"
            context["location"] = dirs[-1]

    title = context["title"]
    if "고등" in title:
        context["grade"] = "고등"
    elif "중등" in title:
        context["grade"] = "중등"
    elif "초등" in title:
        context["grade"] = "초등"

    if "영수" in title:
        context["subject"] = "영어·수학"
    elif "수학" in title:
        context["subject"] = "수학"
    elif "영어" in title:
        context["subject"] = "영어"

    return context


def identity_copy(ctx: dict[str, str]) -> dict[str, str]:
    title = ctx["title"]
    location = ctx["location"]
    subject = ctx["subject"]
    grade = ctx["grade"]
    rel = ctx["rel"]

    lead_variants = [
        f"{title}을 알아볼 때는 수업 과목만 보는 것보다, 학생이 스스로 계획을 지키고 오답을 다시 설명할 수 있는 관리 흐름까지 확인하는 편이 좋습니다.",
        f"{title} 상담은 단순 시간표 안내가 아니라 현재 학습 상태를 진단하고, 주간 플래너와 오답 재학습이 이어지는지 확인하는 과정으로 잡는 것이 좋습니다.",
        f"{title} 페이지는 가까운 학원 정보만 나열하기보다, {subject} 학습에서 놓치기 쉬운 실행 점검과 피드백 기준을 함께 볼 수 있게 구성했습니다.",
        f"{title}을 찾는 학부모라면 성적표보다 먼저 숙제 실행률, 반복 오답, 시험 전 계획이 어떻게 관리되는지 확인해 보는 것이 현실적입니다.",
    ]
    parent_variants = [
        f"{location} 기준으로 상담할 때는 아이가 어느 단원에서 막히는지, 계획을 왜 미루는지, 오답을 다시 풀 때 어떤 설명이 필요한지까지 함께 정리합니다.",
        f"{location} 학습 상담에서는 과목 선택보다 먼저 공부 습관과 시험 준비 리듬을 확인하고, 필요한 관리 강도를 단계별로 맞추는 것이 핵심입니다.",
        f"{location}에서 {subject} 관리를 고민한다면, 수업 후 복습이 실제 행동으로 이어지는지와 학부모 피드백이 꾸준히 전달되는지를 함께 보시면 좋습니다.",
        f"{location} 학생에게 맞는 학습코칭은 더 많은 숙제보다, 해야 할 공부를 작게 쪼개고 지킨 내용을 확인하는 방식에서 차이가 납니다.",
    ]
    answer_variants = [
        f"{grade} 학생에게 필요한 것은 ‘오늘 무엇을 배웠는지’보다 ‘이번 주에 무엇을 끝냈고, 어떤 오답을 다시 설명할 수 있는지’입니다.",
        f"{grade} 과정은 진도만 빠르게 나가는 것보다, 개념 이해 → 문제 적용 → 오답 원인 확인 → 재풀이 흐름이 끊기지 않는지가 중요합니다.",
        f"{grade} 상담에서는 최근 시험지와 교재, 숙제 실행 정도를 함께 보면서 다음 2~4주 동안의 관리 우선순위를 잡는 것이 좋습니다.",
        f"{grade} 학습은 학생마다 흔들리는 지점이 달라서, 플래너·숙제·오답 피드백을 한 번에 연결해 보는 방식이 더 실용적입니다.",
    ]

    return {
        "lead": stable_pick(rel + "lead", lead_variants),
        "parent": stable_pick(rel + "parent", parent_variants, 4),
        "answer": stable_pick(rel + "answer", answer_variants, 8),
    }


def make_identity_section(ctx: dict[str, str]) -> str:
    title = ctx["title"]
    title_with_particle = f"{title}{topic_particle(title)}"
    location = ctx["location"]
    subject = ctx["subject"]
    grade = ctx["grade"]
    copy = identity_copy(ctx)
    seed = ctx["rel"]

    labels = [
        ("학습 진단", "현재 교재·최근 시험지·숙제 실행 정도를 함께 보며 먼저 막힌 지점을 찾습니다."),
        ("주간 플래너", "이번 주에 끝낼 분량을 작게 나누고, 학생이 실제로 지킬 수 있는 계획으로 조정합니다."),
        ("실행 점검", "수업을 들었는지보다 계획을 수행했는지, 미룬 이유가 무엇인지까지 확인합니다."),
        ("오답 재학습", "틀린 문제를 다시 푸는 데서 끝내지 않고, 왜 틀렸는지 말로 설명하는 단계까지 봅니다."),
        ("학부모 피드백", "상담 후에도 학부모가 아이의 변화와 다음 관리 포인트를 이해할 수 있게 정리합니다."),
    ]
    rotated = labels[:]
    shift = int(hashlib.sha1(seed.encode("utf-8")).hexdigest()[:2], 16) % len(labels)
    rotated = rotated[shift:] + rotated[:shift]

    cards = "\n".join(
        f'      <article><span>{escape(name)}</span><p>{escape(desc)}</p></article>'
        for name, desc in rotated
    )

    return f"""{START}
<section class="coaching-identity-section" aria-labelledby="coaching-identity-title">
  <div class="coaching-identity-head">
    <p class="parent-faq-eyebrow">LEARNING COACHING DIFFERENCE</p>
    <h2 id="coaching-identity-title">{escape(title_with_particle)} 수업보다 관리 흐름을 먼저 봅니다</h2>
    <p>{escape(copy["lead"])}</p>
  </div>
  <div class="coaching-loop-grid">
{cards}
  </div>
  <div class="coaching-parent-note">
    <strong>{escape(location)} {escape(subject)} 상담에서 확인할 핵심</strong>
    <p>{escape(copy["parent"])} {escape(copy["answer"])}</p>
  </div>
</section>
{END}"""


def replace_between(doc: str, start: str, end: str, block: str) -> str:
    pattern = re.compile(re.escape(start) + r".*?" + re.escape(end), re.S)
    if pattern.search(doc):
        return pattern.sub(block, doc, count=1)
    return doc


def insert_identity_section(doc: str, section: str) -> str:
    if START in doc and END in doc:
        return replace_between(doc, START, END, section)

    anchors = [
        "<!-- child-page-links:start -->",
        "<section class=\"parent-faq-section\"",
        "</main>",
        "<footer",
    ]

    if "<!-- seo-geo-enhancement:end -->" in doc:
        anchor = "<!-- seo-geo-enhancement:end -->"
        return doc.replace(anchor, anchor + "\n" + section, 1)

    for anchor in anchors:
        idx = doc.find(anchor)
        if idx != -1:
            return doc[:idx] + section + "\n" + doc[idx:]
    return doc + "\n" + section


def node_types(node: dict[str, Any]) -> set[str]:
    t = node.get("@type")
    if isinstance(t, list):
        return {str(x) for x in t}
    if t:
        return {str(t)}
    return set()


def listify(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def add_unique_named(items: list[Any], name: str, type_: str = "Thing") -> list[Any]:
    existing = {
        item.get("name")
        for item in items
        if isinstance(item, dict) and isinstance(item.get("name"), str)
    }
    if name not in existing:
        items.append({"@type": type_, "name": name})
    return items


def add_article_section(node: dict[str, Any], labels: list[str]) -> None:
    current = listify(node.get("articleSection"))
    for label in labels:
        if label not in current:
            current.append(label)
    node["articleSection"] = current


def add_has_part(node: dict[str, Any], ctx: dict[str, str]) -> None:
    parts = listify(node.get("hasPart"))
    existing = {
        item.get("name")
        for item in parts
        if isinstance(item, dict) and isinstance(item.get("name"), str)
    }
    templates = [
        ("학습 진단", f"{ctx['title']} 상담 전 현재 성적, 교재, 숙제 실행 정도를 확인합니다."),
        ("주간 플래너 관리", "학생이 지킬 수 있는 주간 계획으로 분량과 우선순위를 조정합니다."),
        ("실행 점검", "계획을 실제로 수행했는지 확인하고 미룬 원인을 함께 정리합니다."),
        ("오답 원인 분석", "반복되는 오답을 개념·풀이 습관·문제 해석 단계로 나누어 봅니다."),
        ("학부모 피드백", "상담 후 가정에서 확인할 변화와 다음 관리 포인트를 안내합니다."),
    ]
    for name, desc in templates:
        if name not in existing:
            parts.append({"@type": "WebPageElement", "name": name, "description": desc})
    node["hasPart"] = parts


def add_makes_offer(node: dict[str, Any], ctx: dict[str, str]) -> None:
    offers = listify(node.get("makesOffer"))
    existing = {
        item.get("name")
        for item in offers
        if isinstance(item, dict) and isinstance(item.get("name"), str)
    }
    offer_templates = [
        ("학습 진단 상담", f"{ctx['title']} 학생의 현재 학습 상태를 점검합니다."),
        ("플래너 관리", "주간 계획과 실행 여부를 함께 관리합니다."),
        ("오답 재학습 관리", "오답 원인을 확인하고 재풀이 흐름을 잡습니다."),
    ]
    for name, desc in offer_templates:
        if name not in existing:
            offers.append(
                {
                    "@type": "Offer",
                    "name": name,
                    "itemOffered": {
                        "@type": "Service",
                        "name": name,
                        "description": desc,
                    },
                }
            )
    node["makesOffer"] = offers


def enrich_node(node: dict[str, Any], ctx: dict[str, str]) -> None:
    types = node_types(node)
    title = ctx["title"]
    location = ctx["location"]
    subject = ctx["subject"]
    grade = ctx["grade"]

    about_terms = [
        title,
        location,
        f"{location} 학습코칭",
        "학습 진단",
        "주간 플래너 관리",
        "오답 재학습",
        "자기주도학습",
        subject,
        grade,
    ]
    mention_terms = [
        "진단 상담",
        "플래너 실행 점검",
        "오답 원인 분석",
        "시험 대비 계획",
        "학부모 피드백",
        f"{title} 상담 기준",
    ]

    if types & {"Article", "WebPage", "Service"}:
        about = listify(node.get("about"))
        for term in about_terms:
            add_unique_named(about, term, "Place" if term == location else "Thing")
        node["about"] = about

        mentions = listify(node.get("mentions"))
        for term in mention_terms:
            add_unique_named(mentions, term)
        node["mentions"] = mentions

    if "Article" in types:
        add_article_section(
            node,
            ["학습코칭 차별화", "진단-플래너-오답관리 흐름", "학부모 피드백"],
        )
        add_has_part(node, ctx)

    if "WebPage" in types:
        add_has_part(node, ctx)

    if "Service" in types:
        service_type = node.get("serviceType")
        add_text = "학습코칭·플래너·오답관리 상담"
        if isinstance(service_type, str):
            if add_text not in service_type:
                node["serviceType"] = f"{service_type} / {add_text}"
        elif isinstance(service_type, list):
            if add_text not in service_type:
                service_type.append(add_text)
            node["serviceType"] = service_type
        else:
            node["serviceType"] = f"{title} {add_text}"
        add_makes_offer(node, ctx)

    if types & {"EducationalOrganization", "LocalBusiness"}:
        knows = listify(node.get("knowsAbout"))
        for term in ["학습코칭", "학습 진단", "주간 플래너", "오답 관리", "학부모 피드백", subject, grade]:
            if term not in knows:
                knows.append(term)
        node["knowsAbout"] = knows
        node.setdefault("slogan", "진단부터 플래너, 오답 재학습까지 이어지는 학습관리")


def update_json_ld(doc: str, ctx: dict[str, str]) -> str:
    pattern = re.compile(
        r'(<script\s+type="application/ld\+json">)(.*?)(</script>)',
        re.I | re.S,
    )

    def repl(match: re.Match[str]) -> str:
        raw = match.group(2).strip()
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return match.group(0)

        nodes: list[dict[str, Any]] = []
        if isinstance(data, dict) and isinstance(data.get("@graph"), list):
            nodes = [node for node in data["@graph"] if isinstance(node, dict)]
        elif isinstance(data, dict):
            nodes = [data]

        for node in nodes:
            enrich_node(node, ctx)

        dumped = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
        return f"{match.group(1)}{dumped}{match.group(3)}"

    return pattern.sub(repl, doc)


TOP_DESCRIPTIONS = {
    "index.html": "학원 선택 전 학생의 현재 상태를 진단하고, 주간 플래너·실행 점검·오답 재학습·학부모 피드백 흐름으로 학습관리를 안내하는 학습코칭 전문 사이트입니다.",
    "학습가이드/index.html": "초등·중등·고등 학생을 위한 학습 진단, 시험 기간 계획, 플래너 관리, 오답 재학습 방법을 학부모가 이해하기 쉽게 정리한 학습코칭 가이드입니다.",
    "학습관리/index.html": "공부 계획이 실제 행동으로 이어지도록 학습 진단, 주간 플래너, 숙제 실행 점검, 오답 원인 분석, 학부모 피드백 흐름을 안내합니다.",
    "진단상담/index.html": "영어·수학 학원 상담 전 학생의 성적, 공부 습관, 과목별 약점, 반복 오답을 점검해 필요한 학습관리 방향을 찾는 진단상담 안내입니다.",
    "상담문의/index.html": "상담 전 준비할 자료와 질문을 정리하고, 학생에게 필요한 학습 진단·플래너 관리·오답 재학습 방향을 확인할 수 있는 상담문의 페이지입니다.",
    "전국학원/index.html": "지역별 학원 안내와 함께 학습 진단, 플래너 관리, 오답 재학습, 학부모 피드백 기준을 비교할 수 있는 전국 학습코칭 안내 페이지입니다.",
}


def update_page(path: Path) -> bool:
    doc = path.read_text(encoding="utf-8")
    original = doc
    rel = page_rel(path)
    ctx = page_context(path, doc)

    section = make_identity_section(ctx)
    doc = insert_identity_section(doc, section)
    doc = update_json_ld(doc, ctx)

    if rel in TOP_DESCRIPTIONS:
        doc = replace_meta_description(doc, TOP_DESCRIPTIONS[rel])

    if doc != original:
        path.write_text(doc, encoding="utf-8", newline="")
        return True
    return False


COACHING_CSS = f"""{CSS_START}
.coaching-identity-section {{
  margin: clamp(36px, 6vw, 72px) auto;
  padding: clamp(26px, 5vw, 48px);
  border: 1px solid rgba(45, 64, 89, .12);
  border-radius: 32px;
  background:
    radial-gradient(circle at 14% 18%, rgba(121, 190, 255, .20), transparent 32%),
    linear-gradient(135deg, rgba(255,255,255,.96), rgba(245,249,255,.90));
  box-shadow: 0 24px 70px rgba(38, 61, 95, .10);
}}
.coaching-identity-head {{
  max-width: 840px;
  margin-bottom: 24px;
}}
.coaching-identity-head h2 {{
  margin: 8px 0 12px;
  font-size: clamp(1.55rem, 3.4vw, 2.35rem);
  letter-spacing: -.045em;
  color: #152235;
}}
.coaching-identity-head p {{
  margin: 0;
  color: #526070;
  line-height: 1.85;
}}
.coaching-loop-grid {{
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 14px;
}}
.coaching-loop-grid article {{
  min-height: 150px;
  padding: 20px 18px;
  border-radius: 22px;
  background: rgba(255, 255, 255, .88);
  border: 1px solid rgba(74, 95, 122, .11);
}}
.coaching-loop-grid span {{
  display: inline-flex;
  margin-bottom: 12px;
  padding: 6px 10px;
  border-radius: 999px;
  background: rgba(33, 120, 255, .10);
  color: #1d5fbf;
  font-size: .82rem;
  font-weight: 800;
}}
.coaching-loop-grid p {{
  margin: 0;
  color: #526070;
  line-height: 1.72;
  font-size: .95rem;
}}
.coaching-parent-note {{
  margin-top: 18px;
  padding: 20px 22px;
  border-radius: 22px;
  background: linear-gradient(135deg, rgba(32, 44, 63, .94), rgba(41, 71, 111, .90));
  color: #fff;
}}
.coaching-parent-note strong {{
  display: block;
  margin-bottom: 8px;
  font-size: 1.05rem;
}}
.coaching-parent-note p {{
  margin: 0;
  color: rgba(255,255,255,.82);
  line-height: 1.78;
}}
@media (max-width: 980px) {{
  .coaching-loop-grid {{
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }}
}}
@media (max-width: 620px) {{
  .coaching-identity-section {{
    padding: 22px 16px;
    border-radius: 24px;
  }}
  .coaching-loop-grid {{
    grid-template-columns: 1fr;
  }}
  .coaching-loop-grid article {{
    min-height: 0;
  }}
}}
{CSS_END}
"""


def update_css() -> bool:
    css_path = ROOT / "assets" / "site.css"
    css = css_path.read_text(encoding="utf-8")
    block = COACHING_CSS.strip()
    if CSS_START in css and CSS_END in css:
        new_css = replace_between(css, CSS_START, CSS_END, block)
    else:
        new_css = css.rstrip() + "\n\n" + block + "\n"
    if new_css != css:
        css_path.write_text(new_css, encoding="utf-8", newline="")
        return True
    return False


def main() -> None:
    targets = [path for path in ROOT.rglob("index.html") if is_real_html(path) and is_target_page(path)]
    changed = 0
    for path in targets:
        if update_page(path):
            changed += 1
    css_changed = update_css()
    print(
        json.dumps(
            {
                "target_pages": len(targets),
                "changed_pages": changed,
                "css_changed": css_changed,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
