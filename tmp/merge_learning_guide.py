from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GUIDE = ROOT / "학습가이드" / "index.html"
OLD = ROOT / "학습관리" / "index.html"
OLD_ENCODED = "%ED%95%99%EC%8A%B5%EA%B4%80%EB%A6%AC"
GUIDE_ENCODED = "%ED%95%99%EC%8A%B5%EA%B0%80%EC%9D%B4%EB%93%9C"
SITE = "https://xn--ru4bi8s1tac0p.kr"
GUIDE_URL = f"{SITE}/{GUIDE_ENCODED}/"


def write_if_changed(path: Path, text: str) -> None:
    old = path.read_text(encoding="utf-8") if path.exists() else ""
    if old != text:
        path.write_text(text, encoding="utf-8", newline="\n")


def remove_old_nav_and_retarget_links() -> None:
    old_nav = re.compile(
        r'<a\b[^>]*href="[^"]*학습관리/"[^>]*>\s*학습관리\s*</a>',
        re.IGNORECASE,
    )
    for path in ROOT.rglob("index.html"):
        if ".vercel" in path.parts:
            continue
        html = path.read_text(encoding="utf-8")
        updated = old_nav.sub("", html)
        updated = updated.replace("학습관리/", "학습가이드/")
        updated = updated.replace(OLD_ENCODED, GUIDE_ENCODED)
        write_if_changed(path, updated)


def add_guide_to_footers() -> None:
    """Keep the integrated guide discoverable where the old management footer link was removed."""
    for path in ROOT.rglob("index.html"):
        if ".vercel" in path.parts or path in {GUIDE, OLD}:
            continue
        html = path.read_text(encoding="utf-8")
        nav = re.search(r'<div class="nav-links">(.*?)</div>', html, re.DOTALL)
        footer = re.search(r'<div class="footer-links">(.*?)</div>', html, re.DOTALL)
        if not nav or not footer or ">학습가이드</a>" in footer.group(1):
            continue
        guide_link = re.search(r'<a\b[^>]*href="([^"]*학습가이드/)"[^>]*>\s*학습가이드\s*</a>', nav.group(1))
        if not guide_link:
            continue
        link = f'<a href="{guide_link.group(1)}">학습가이드</a>'
        updated_footer = f'<div class="footer-links">{link}{footer.group(1)}</div>'
        updated = html[:footer.start()] + updated_footer + html[footer.end():]
        write_if_changed(path, updated)


def clean_html_whitespace() -> None:
    for path in ROOT.rglob("index.html"):
        if ".vercel" in path.parts:
            continue
        html = path.read_text(encoding="utf-8")
        cleaned = "\n".join(line.rstrip() for line in html.splitlines()) + "\n"
        write_if_changed(path, cleaned)


def schema_graph() -> dict:
    organization = {
        "@type": "EducationalOrganization",
        "@id": f"{SITE}/#organization",
        "name": "학습코칭 연구소",
        "url": f"{SITE}/",
        "logo": f"{SITE}/assets/favicon.png",
        "image": f"{SITE}/assets/generated/academy-hero-v2.webp",
        "telephone": "010-3957-8283",
        "areaServed": "KR",
        "description": "학생의 현재 학습 상태를 진단하고 플래너 실행, 오답 재학습, 학부모 피드백을 연결하는 학습코칭 안내 홈페이지입니다.",
        "contactPoint": [{
            "@type": "ContactPoint",
            "telephone": "+82-10-3957-8283",
            "contactType": "customer support",
            "availableLanguage": "Korean",
        }],
        "knowsAbout": ["학습 진단", "주간 플래너", "실행 점검", "오답 재학습", "시험 대비", "학부모 피드백"],
    }
    webpage = {
        "@type": "CollectionPage",
        "@id": f"{GUIDE_URL}#webpage",
        "url": GUIDE_URL,
        "name": "학습관리와 학습가이드",
        "description": "학생의 현재 상태를 진단하고 주간 플래너, 실행 점검, 오답 재학습, 학부모 피드백까지 연결하는 초중고 영어·수학 학습관리 가이드입니다.",
        "inLanguage": "ko-KR",
        "isPartOf": {"@id": f"{SITE}/#website"},
        "publisher": {"@id": f"{SITE}/#organization"},
        "breadcrumb": {"@id": f"{GUIDE_URL}#breadcrumb"},
        "about": [
            {"@type": "Thing", "name": "학습 진단"},
            {"@type": "Thing", "name": "주간 플래너 관리"},
            {"@type": "Thing", "name": "오답 재학습"},
            {"@type": "Thing", "name": "초등·중등·고등 영어·수학 학습관리"},
        ],
        "hasPart": [
            {"@type": "WebPageElement", "name": "학습 진단", "description": "현재 교재, 최근 시험지, 숙제 실행 정도를 바탕으로 막힌 지점을 확인합니다."},
            {"@type": "WebPageElement", "name": "주간 플래너", "description": "과목, 단원, 분량과 완료 기준을 학생이 실행할 수 있는 단위로 정합니다."},
            {"@type": "WebPageElement", "name": "실행 점검", "description": "완료 여부와 실제 소요 시간, 미완료 원인을 다음 계획에 반영합니다."},
            {"@type": "WebPageElement", "name": "오답 재학습", "description": "오답 원인을 나누고 일정 시간이 지난 뒤 재풀이와 유사 문제로 확인합니다."},
        ],
    }
    return {
        "@context": "https://schema.org",
        "@graph": [
            organization,
            {
                "@type": "WebSite",
                "@id": f"{SITE}/#website",
                "name": "학습코칭 연구소",
                "url": f"{SITE}/",
                "inLanguage": "ko-KR",
                "publisher": {"@id": f"{SITE}/#organization"},
            },
            webpage,
            {
                "@type": "BreadcrumbList",
                "@id": f"{GUIDE_URL}#breadcrumb",
                "itemListElement": [
                    {"@type": "ListItem", "position": 1, "name": "학습코칭 연구소", "item": f"{SITE}/"},
                    {"@type": "ListItem", "position": 2, "name": "학습가이드", "item": GUIDE_URL},
                ],
            },
            {
                "@type": "Article",
                "@id": f"{GUIDE_URL}#article",
                "headline": "진단부터 오답 재학습까지 이어지는 학습관리 가이드",
                "description": webpage["description"],
                "inLanguage": "ko-KR",
                "author": {"@id": f"{SITE}/#organization"},
                "publisher": {"@id": f"{SITE}/#organization"},
                "mainEntityOfPage": {"@id": f"{GUIDE_URL}#webpage"},
                "articleSection": ["학습 진단", "주간 플래너", "실행 점검", "오답 재학습", "학부모 피드백"],
                "about": ["학습관리", "학습가이드", "영어·수학 학습법", "시험 대비 계획"],
            },
            {
                "@type": "Service",
                "@id": f"{GUIDE_URL}#service",
                "name": "학습 진단 및 학습관리 안내",
                "serviceType": "초중고 영어·수학 학습코칭 안내",
                "provider": {"@id": f"{SITE}/#organization"},
                "areaServed": {"@type": "Country", "name": "대한민국"},
                "description": "현재 학습 상태를 확인하고 계획, 실행, 오답 재학습과 학부모 피드백의 관리 기준을 안내합니다.",
            },
            {
                "@type": "HowTo",
                "@id": f"{GUIDE_URL}#management-flow",
                "name": "학습관리 4단계",
                "description": "진단에서 시작해 계획, 실행 확인, 오답 재학습으로 이어지는 학습관리 흐름입니다.",
                "step": [
                    {"@type": "HowToStep", "position": 1, "name": "현재 상태 진단", "text": "교재, 최근 시험지, 숙제 실행 정도를 함께 확인합니다."},
                    {"@type": "HowToStep", "position": 2, "name": "실행 가능한 계획", "text": "과목, 단원, 분량과 완료 기준을 구체적으로 정합니다."},
                    {"@type": "HowToStep", "position": 3, "name": "실행 결과 점검", "text": "실제 수행 여부와 미완료 원인을 확인해 다음 계획을 조정합니다."},
                    {"@type": "HowToStep", "position": 4, "name": "오답 재학습", "text": "오답 원인을 구분하고 재풀이와 유사 문제로 이해 여부를 확인합니다."},
                ],
            },
            {
                "@type": "ItemList",
                "@id": f"{GUIDE_URL}#guide-list",
                "name": "학습관리 가이드 바로가기",
                "itemListElement": [
                    {"@type": "ListItem", "position": 1, "name": "학습관리 흐름", "url": f"{GUIDE_URL}#management-flow"},
                    {"@type": "ListItem", "position": 2, "name": "플래너 관리", "url": f"{GUIDE_URL}#planner"},
                    {"@type": "ListItem", "position": 3, "name": "오답 재학습", "url": f"{GUIDE_URL}#wrong-answer"},
                    {"@type": "ListItem", "position": 4, "name": "진단 상담 준비", "url": f"{SITE}/%EC%A7%84%EB%8B%A8%EC%83%81%EB%8B%B4/"},
                ],
            },
        ],
    }


MAIN = '''<main id="main">
    <section class="page-hero integrated-guide-hero">
      <div class="wrap page-hero-inner">
        <div>
          <div class="breadcrumb"><a href="../">홈</a> › 학습가이드</div>
          <p class="eyebrow">learning management guide</p>
          <h1>진단부터 오답 재학습까지,<br>한 흐름으로 보는 학습가이드</h1>
          <p>공부 계획은 세우는 것으로 끝나지 않습니다. 학생의 현재 상태를 먼저 확인하고, 실행할 수 있는 분량으로 나눈 뒤 결과를 점검해 다음 학습으로 연결해야 합니다.</p>
        </div>
        <aside class="badge-box"><strong>4-step</strong><span>진단 · 계획 · 실행 확인 · 오답 재학습</span></aside>
      </div>
    </section>

    <section class="section integrated-guide-intro" id="management-flow">
      <div class="wrap">
        <div class="section-head integrated-guide-head">
          <div><p class="eyebrow">management flow</p><h2>학생의 공부가 끊기는 지점을<br>순서대로 확인합니다.</h2></div>
          <p>성적표만으로는 계획을 못 지키는 이유나 같은 실수가 반복되는 원인을 알기 어렵습니다. 아래 네 단계를 함께 보면 학생에게 필요한 관리가 진도 보강인지, 습관 조정인지 더 분명해집니다.</p>
        </div>
        <div class="integrated-flow-grid">
          <article><span>01</span><h3>현재 상태 진단</h3><p>최근 시험지와 교재, 숙제 실행 정도를 함께 보며 개념·습관·시간 배분 중 어디에서 막히는지 확인합니다.</p></article>
          <article><span>02</span><h3>실행 가능한 계획</h3><p>과목과 단원, 문제 수, 암기 범위와 완료 기준을 학생이 지킬 수 있는 크기로 나누어 정합니다.</p></article>
          <article><span>03</span><h3>실행 결과 점검</h3><p>완료 여부뿐 아니라 실제 걸린 시간과 미룬 이유를 기록하고 다음 주 분량과 우선순위를 조정합니다.</p></article>
          <article><span>04</span><h3>오답 재학습</h3><p>틀린 원인을 구분한 뒤 일정 시간이 지나 다시 풀고, 조건이 바뀐 유사 문제로 이해 여부를 확인합니다.</p></article>
        </div>
      </div>
    </section>

    <section class="section integrated-guide-principles">
      <div class="wrap card-grid">
        <article class="plain-card"><h3>플래너 관리</h3><p>학교 일정과 학생의 체력을 고려해 실천 가능한 공부량으로 조정합니다.</p></article>
        <article class="plain-card"><h3>복습 루틴</h3><p>수업 직후, 다음 수업 전, 시험 준비 기간으로 복습 시점을 나누어 기억의 공백을 줄입니다.</p></article>
        <article class="plain-card"><h3>숙제 점검</h3><p>완료 여부만 보지 않고 어떤 문제에서 오래 걸렸는지와 미완료 원인을 함께 확인합니다.</p></article>
        <article class="plain-card"><h3>오답 관리</h3><p>틀린 문제를 원인별로 분류하고 설명과 재풀이가 가능한 상태까지 관리합니다.</p></article>
        <article class="plain-card"><h3>시험 전 전략</h3><p>시험 범위에 맞춰 기본 개념, 응용, 서술형과 누적 오답의 공부 순서를 정합니다.</p></article>
        <article class="plain-card"><h3>학부모 피드백</h3><p>현재 실행 상태와 다음 관리 포인트를 가정에서도 이해할 수 있도록 구체적으로 정리합니다.</p></article>
      </div>
    </section>

    <section class="section detail-section" id="planner">
      <div class="wrap">
        <div class="section-head">
          <div><p class="eyebrow">planner coaching</p><h2>플래너는 시간표보다<br>실행을 확인하는 도구에 가깝습니다.</h2></div>
          <p>“수학 공부하기”처럼 막연한 계획보다 과목, 단원, 분량, 완료 기준이 분명한 계획이 필요합니다. 그래야 학생은 무엇을 끝내야 하는지 알고, 코치는 실행 결과를 확인할 수 있습니다.</p>
        </div>
        <div class="detail-grid">
          <article class="detail-card"><span>01</span><h3>목표를 구체화</h3><p>오늘 해야 할 공부를 과목과 단원, 문제 수, 암기 범위까지 나누어 적습니다.</p><ul><li>영어 본문 해석 후 핵심 문장 암기</li><li>수학 특정 유형 1~20번 풀이</li><li>지난주 오답 8문제 다시 풀기</li></ul></article>
          <article class="detail-card"><span>02</span><h3>실행 결과 확인</h3><p>실제 걸린 시간, 어려웠던 부분과 다시 공부할 내용을 함께 확인합니다.</p><ul><li>완료·미완료 표시</li><li>틀린 문제 수와 막힌 단원 기록</li><li>숙제를 못한 이유 확인</li></ul></article>
          <article class="detail-card"><span>03</span><h3>다음 계획에 반영</h3><p>양이 많았는지 습관이 흔들렸는지 구분해 다음 주 계획을 현실적으로 조정합니다.</p><ul><li>특정 과목만 계속 미루는지 확인</li><li>수행평가와 학교 시험 일정 반영</li><li>오답 복습 시간을 실제 일정에 포함</li></ul></article>
        </div>
      </div>
    </section>

    <section class="section" id="wrong-answer">
      <div class="wrap integrated-wrong-answer">
        <div>
          <p class="eyebrow">wrong answer routine</p>
          <h2>오답은 답을 고치는 일이 아니라<br>틀린 이유를 줄이는 과정입니다.</h2>
          <p>같은 점수의 학생이라도 개념 부족, 계산 실수, 조건 누락처럼 원인은 다를 수 있습니다. 원인이 다르면 다시 공부하는 방법도 달라야 합니다.</p>
        </div>
        <ul class="check-list">
          <li>개념 부족, 공식 적용 오류, 조건 누락과 계산 실수를 구분합니다.</li>
          <li>설명을 들은 직후뿐 아니라 일정 시간이 지난 뒤 다시 풉니다.</li>
          <li>숫자나 조건이 바뀐 유사 문제로 실제 이해 여부를 확인합니다.</li>
          <li>반복되는 유형은 시험 전 우선 복습 목록으로 누적합니다.</li>
        </ul>
      </div>
    </section>

    <section class="section integrated-guide-links" aria-labelledby="guide-next-title">
      <div class="wrap">
        <div class="section-head"><div><p class="eyebrow">next guide</p><h2 id="guide-next-title">다음 확인 단계도 한 번에 이어보세요.</h2></div><p>학생의 자료를 준비하는 방법부터 지역별 상담 기준까지 필요한 순서대로 확인할 수 있습니다.</p></div>
        <div class="guide-grid">
          <a class="guide-card" href="../진단상담/"><h3>진단 상담 준비</h3><p>최근 시험지, 교재, 반복 오답과 공부 습관 중 상담 전에 준비하면 좋은 자료를 정리합니다.</p></a>
          <a class="guide-card" href="../전국학원/"><h3>지역별 학원 찾기</h3><p>지역별 센터 안내와 함께 학생에게 맞는 관리 방식과 상담 기준을 비교합니다.</p></a>
          <a class="guide-card" href="../상담문의/"><h3>상담 전에 확인할 질문</h3><p>수업 방식, 피드백 주기, 플래너와 오답 관리 방법을 상담에서 구체적으로 확인합니다.</p></a>
        </div>
      </div>
    </section>

    <section class="coaching-identity-section" aria-labelledby="coaching-identity-title">
      <div class="coaching-identity-head"><p class="parent-faq-eyebrow">LEARNING COACHING DIFFERENCE</p><h2 id="coaching-identity-title">좋은 학습관리는 수업 전후의 흐름까지 봅니다.</h2><p>수업을 얼마나 많이 들었는지보다 배운 내용을 계획에 옮기고, 실행 결과와 오답을 다음 학습에 반영하는지가 중요합니다.</p></div>
      <div class="coaching-loop-grid">
        <article><span>학습 진단</span><p>현재 교재와 시험지, 숙제 실행 정도를 보며 먼저 막힌 지점을 찾습니다.</p></article>
        <article><span>주간 플래너</span><p>이번 주에 끝낼 분량을 작게 나누고 실제로 지킬 수 있는 계획으로 조정합니다.</p></article>
        <article><span>실행 점검</span><p>계획을 수행했는지와 미룬 이유가 무엇인지까지 확인합니다.</p></article>
        <article><span>오답 재학습</span><p>왜 틀렸는지 설명하고 다시 풀 수 있는 단계까지 확인합니다.</p></article>
        <article><span>학부모 피드백</span><p>학생의 변화와 다음 관리 포인트를 가정에서도 이해할 수 있게 정리합니다.</p></article>
      </div>
      <div class="coaching-parent-note"><strong>학부모가 상담에서 확인할 핵심</strong><p>초등·중등·고등 과정 모두 진도 속도만 보기보다 개념 이해 → 문제 적용 → 오답 원인 확인 → 재풀이가 끊기지 않는지 확인하는 것이 좋습니다. 수업 후 복습과 플래너 실행이 실제 행동으로 이어지는지도 함께 물어보세요.</p></div>
    </section>
  </main>'''


def rebuild_guide() -> None:
    html = GUIDE.read_text(encoding="utf-8")
    replacements = {
        r"<title>.*?</title>": "<title>학습관리·학습가이드 | 학습코칭 연구소</title>",
        r'<meta name="description" content="[^"]*">': '<meta name="description" content="학생의 현재 상태를 진단하고 주간 플래너, 실행 점검, 오답 재학습, 학부모 피드백까지 연결하는 초중고 영어·수학 학습관리 가이드입니다.">',
        r'<meta property="og:description" content="[^"]*">': '<meta property="og:description" content="진단, 계획, 실행 확인, 오답 재학습을 한 흐름으로 정리한 초중고 영어·수학 학습관리 가이드입니다.">',
        r'<meta property="og:title" content="[^"]*">': '<meta property="og:title" content="학습관리·학습가이드 | 학습코칭 연구소">',
    }
    for pattern, value in replacements.items():
        html = re.sub(pattern, value, html, count=1, flags=re.DOTALL)
    schema = json.dumps(schema_graph(), ensure_ascii=False, separators=(",", ":"))
    html = re.sub(
        r'<script type="application/ld\+json">.*?</script>',
        f'<script type="application/ld+json">{schema}</script>',
        html,
        count=1,
        flags=re.DOTALL,
    )
    html = re.sub(r'<main id="main">.*?</main>', MAIN, html, count=1, flags=re.DOTALL)
    html = html.replace(
        '<div class="footer-links"><a href="../학습가이드/">학습관리</a><a href="../전국학원/">전국학원</a></div>',
        '<div class="footer-links"><a href="../진단상담/">진단상담</a><a href="../전국학원/">전국학원</a></div>',
    )
    write_if_changed(GUIDE, html)


def old_page_fallback() -> None:
    html = f'''<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>학습가이드로 이동합니다 | 학습코칭 연구소</title>
  <meta name="robots" content="noindex, follow">
  <meta http-equiv="refresh" content="0; url=../학습가이드/">
  <link rel="canonical" href="{GUIDE_URL}">
  <link rel="stylesheet" href="../assets/site.css">
</head>
<body>
  <main id="main" class="redirect-page">
    <div class="redirect-card">
      <p class="eyebrow">page moved</p>
      <h1>학습관리 내용이 학습가이드로 통합되었습니다.</h1>
      <p>진단, 플래너, 실행 점검과 오답 재학습 내용을 한 페이지에서 확인할 수 있습니다.</p>
      <a class="btn btn-primary" href="../학습가이드/">통합 학습가이드 보기</a>
    </div>
  </main>
</body>
</html>
'''
    write_if_changed(OLD, html)


def update_vercel() -> None:
    path = ROOT / "vercel.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    redirects = [r for r in data.get("redirects", []) if r.get("source") not in {"/학습관리", "/학습관리/"}]
    redirects.insert(0, {"source": "/학습관리", "destination": "/학습가이드", "permanent": True})
    data["redirects"] = redirects
    write_if_changed(path, json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def update_sitemap() -> None:
    path = ROOT / "sitemap.xml"
    xml = path.read_text(encoding="utf-8")
    xml = re.sub(
        rf"\s*<url>\s*<loc>{re.escape(SITE)}/{OLD_ENCODED}/</loc>.*?</url>",
        "",
        xml,
        count=1,
        flags=re.DOTALL,
    )
    guide_block = re.compile(rf"(<url>\s*<loc>{re.escape(GUIDE_URL)}</loc>)(.*?</url>)", re.DOTALL)
    match = guide_block.search(xml)
    if match:
        tail = re.sub(r"<lastmod>.*?</lastmod>", "<lastmod>2026-07-23</lastmod>", match.group(2), count=1)
        if "<lastmod>" not in tail:
            tail = "\n    <lastmod>2026-07-23</lastmod>" + tail
        xml = xml[:match.start()] + match.group(1) + tail + xml[match.end():]
    write_if_changed(path, xml)


def update_llms() -> None:
    text = '''# 학습코칭.kr

학습코칭.kr은 초등·중등·고등 학생의 현재 학습 상태를 진단하고, 영어·수학 공부 계획과 플래너 실행, 오답 재학습, 상담 준비 기준을 안내하는 학습코칭 정보 사이트입니다.

## 핵심 주제

- 학습 진단과 상담 준비
- 주간 플래너와 실행 점검
- 영어·수학 복습과 오답 재학습
- 지역별 학원 안내와 상담 기준
- 학부모가 상담 전에 확인할 질문과 체크리스트

## 주요 페이지

- 홈: https://xn--ru4bi8s1tac0p.kr/
- 학습가이드: https://xn--ru4bi8s1tac0p.kr/%ED%95%99%EC%8A%B5%EA%B0%80%EC%9D%B4%EB%93%9C/
- 진단상담: https://xn--ru4bi8s1tac0p.kr/%EC%A7%84%EB%8B%A8%EC%83%81%EB%8B%B4/
- 전국학원: https://xn--ru4bi8s1tac0p.kr/%EC%A0%84%EA%B5%AD%ED%95%99%EC%9B%90/
- 상담문의: https://xn--ru4bi8s1tac0p.kr/%EC%83%81%EB%8B%B4%EB%AC%B8%EC%9D%98/

## 크롤링 안내

공개 페이지는 검색엔진과 생성형 검색 서비스가 요약·인용 목적으로 접근할 수 있습니다. 최신 URL 목록은 sitemap.xml을 우선 참고해 주세요.

- Sitemap: https://xn--ru4bi8s1tac0p.kr/sitemap.xml
- Robots: https://xn--ru4bi8s1tac0p.kr/robots.txt
'''
    write_if_changed(ROOT / "llms.txt", text)


if __name__ == "__main__":
    remove_old_nav_and_retarget_links()
    add_guide_to_footers()
    rebuild_guide()
    old_page_fallback()
    update_vercel()
    update_sitemap()
    update_llms()
    clean_html_whitespace()
