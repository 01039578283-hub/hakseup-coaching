"""학습코칭.kr: fact-backed branch directory and editorial learning upgrade.

Run --import-source once to verify and snapshot the owner-supplied workbooks and
photos. Subsequent runs use the reviewed, private manifest, not a remote crawl.
Old academy manuscripts/URLs are not rewritten; shared navigation is replaced.
"""
from __future__ import annotations
import argparse
import copy
import hashlib
import importlib.util
import json
import re
import shutil
import sys
from collections import Counter
from html import escape
from pathlib import Path
from urllib.parse import quote, unquote, urljoin, urlsplit
from lxml import etree, html
from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'tools/data/coaching-directory'
DOMAIN = 'https://xn--ru4bi8s1tac0p.kr'
DAY = '2026-09-21'
SOURCE = Path(r'C:\Users\1992k\Desktop\센터정보')
REFERENCE = Path(r'C:\Users\1992k\Desktop\CodexData\worktrees\wawa-branch-seo\홈페이지')
OFFICIAL = Path(r'C:\Users\1992k\Desktop\홈페이지 정리\새 홈페이지\assets\official-learning')
REGIONS = ['서울','경기','인천','부산','대구','광주','대전','울산','세종','강원','충북','충남','전북','전남','경북','경남','제주']
SUBJECTS = ['국어','영어','수학','과학','사회']
MENU = [('홈','/'),('지점안내','/지점안내/'),('학습가이드','/학습가이드/'),('진단상담','/진단상담/'),('전국학원','/전국학원/'),('과목별학원','/과목별학원/'),('상담문의','/상담문의/')]
EDITORIAL = {}


def e(s): return escape(str(s), quote=True)
def j(s): return json.dumps(s, ensure_ascii=False, separators=(',', ':')).replace('</', '<\\/')
def url(path): return DOMAIN + quote(path, safe='/#-')
def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    normalized=text.rstrip()+'\n'
    if path.exists() and path.read_bytes()==normalized.encode('utf-8'):return
    path.write_text(normalized, encoding='utf-8', newline='\n')
def save(path, value): write(path, json.dumps(value, ensure_ascii=False, indent=2))
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def text(node): return ' '.join(node.text_content().split())
def route(c): return f'/지점안내/{c["region"]}/{c["routeName"]}/'


def import_source():
    """Use reviewed factual joins only; none of the reference site's articles."""
    DATA.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(REFERENCE/'tools'))
    import generate_branch_directory as source
    import branch_course_guidance as guidance
    guidance.verify_source(SOURCE/'코칭센터_데이터_.xlsx')
    old = json.loads((REFERENCE/'tools/data/branch-directory/branches.json').read_text(encoding='utf-8'))
    latest, excluded = source.load_centers()
    by_name = {c['routeName']: c for c in latest}
    assert set(by_name) == {c['routeName'] for c in old['centers']}
    rules = json.loads((REFERENCE/'tools/data/branch-directory/course-guidance.json').read_text(encoding='utf-8'))
    save(DATA/'course-conditions.json', rules)
    photos = []
    for c in old['centers']:
        fresh = by_name[c['routeName']]
        for field in ['subjects','schools','neighborhoods','sourceRow','sourceName','registeredName','registrationNumber']:
            assert c[field] == fresh[field], (c['routeName'], field)
        # Whitespace-only normalization may differ in the saved address.
        assert re.sub(r'\s','',c['address']) == re.sub(r'\s','',fresh['address']), c['routeName']
        c['courses'] = [guidance.course_guidance(c, s) for s in SUBJECTS]
        c['courseNotes'] = guidance.center_notes(c)
        c['weekend'] = guidance.weekend_guidance(c)
        c['displayName'] = ('모두오름학습코칭학원 ' if '모두' in c['brand'] else '와와학습코칭학원 ') + c['routeName']
        # Keep a point only as an evidence-backed consultation question.
        c['managementTopics'] = [v[0] for v in fresh.get('managementPoints', [])]
        c.pop('managementPoints', None)
        selected = source.select_photos(SOURCE/'센터별 사진'/c['sourceName'])
        common = source.select_photos(SOURCE/'센터별 사진/1 공용사진')
        common_hashes = {sha(p) for p in common}
        generic = not selected or all(sha(p) in common_hashes for p in selected)
        if generic: selected = common
        c['photoMode'] = 'common' if generic else 'center'
        c['photos'] = []
        for i, p in enumerate(selected, 1):
            dest = ROOT/'assets/coaching-centers'/('common' if generic else f'{c["region"]}/{c["routeName"]}')/f'photo-{i:02}.webp'
            if not dest.exists():
                dest.parent.mkdir(parents=True, exist_ok=True)
                with Image.open(p) as im:
                    im = ImageOps.exif_transpose(im).convert('RGB')
                    im.thumbnail((1200,1200))
                    im.save(dest, 'WEBP', quality=82, method=6)
            c['photos'].append('/'+dest.relative_to(ROOT).as_posix())
            photos.append({'center': c['routeName'], 'source': str(p), 'sha256': sha(p), 'destination': c['photos'][-1], 'mode': c['photoMode']})
        # Previously verified maps remain tied to the source row/registration.
        def copy_media(value):
            if isinstance(value, dict): return {k: copy_media(v) for k,v in value.items()}
            if isinstance(value, list): return [copy_media(v) for v in value]
            if isinstance(value, str) and value.startswith('/assets/branch-directory/'):
                src = REFERENCE/value.lstrip('/')
                dest = ROOT/value.lstrip('/')
                assert src.is_file(), src
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dest)
            return value
        copy_media(c['primaryMedia'])
        for k in ['representative','body','map']:
            m=c['primaryMedia'][k]
            assert sha(ROOT/m['src'].lstrip('/')) == m['sha256']
        c['informationReviewedAt'] = DAY
    save(DATA/'centers.json', {'reviewedAt': DAY, 'sources':[{'file':p.name,'sha256':sha(p)} for p in [SOURCE/'코칭센터_데이터_.xlsx',SOURCE/'타깃학교 v2.xlsx']], 'centers':old['centers'],'excluded':excluded})
    save(DATA/'photo-provenance.json', photos)
    save(DATA/'sources.json', {'reviewedAt': DAY, 'references': ['https://www.wawacenter.com/brand/wawacenter','https://www.wawacenter.com/intro/coachingSystem','https://www.wawacenter.com/intro/AISystem'], 'videos':['avpJfW7eIV0','f_skFu40U04','UIXUaBZdNXU'], 'policy':'Branch facts are source-bound. General program descriptions do not prove center-specific availability or outcomes.'})
    for p in OFFICIAL.iterdir():
        if p.suffix not in ('.png','.jpg'): continue
        dest = ROOT/'assets/coaching-program'/f'{p.stem}.webp'
        dest.parent.mkdir(parents=True, exist_ok=True)
        with Image.open(p) as im:
            im.convert('RGB').save(dest,'WEBP',quality=86,method=6)
    print('Verified source import:',len(old['centers']), 'centers,',Counter(c['photoMode'] for c in old['centers']))


def header(path):
    def active(p): return (p=='/' and path=='/') or (p!='/' and path.startswith(p))
    links=''.join(f'<a href="{p}"'+(' aria-current="page"' if active(p) else '')+f'>{n}</a>' for n,p in MENU)
    return f'''<header class="site-header hc-header"><nav class="hc-nav" aria-label="주요 메뉴">
<a class="hc-brand" href="/" aria-label="학습코칭 홈"><span aria-hidden="true">L</span>학습코칭</a>
<div class="hc-desktop-menu">{links}</div><details class="hc-mobile-menu"><summary>메뉴 <span aria-hidden="true">＋</span></summary><div>{links}</div></details>
</nav></header>'''


def footer():
    return '''<footer class="hc-footer"><div class="hc-wrap"><strong>학습코칭.kr</strong><p>공부 방법을 이해하고, 우리 동네 수업 조건을 확인하세요.</p><nav aria-label="하단 메뉴"><a href="/지점안내/">지점안내</a><a href="/학습가이드/">학습가이드</a><a href="/상담문의/">상담문의</a><a href="/rss.xml">RSS</a></nav></div></footer>
<nav class="hc-contact" aria-label="빠른 상담"><a href="tel:010-3957-8283">전화 문의</a><a href="https://blogsms.net/01039578283" target="_blank" rel="noopener">문자 문의</a><a href="/상담문의/">상담 안내</a></nav>'''


def picture(src, alt, eager=False):
    with Image.open(ROOT/src.lstrip('/')) as im: w,h=im.size
    return f'<img src="{e(src)}" alt="{e(alt)}" width="{w}" height="{h}" loading="{"eager" if eager else "lazy"}" decoding="async">'


def figure(name, alt, caption='', eager=False):
    return '<figure class="hc-figure">'+picture('/assets/coaching-program/'+name+'.webp', alt, eager)+(f'<figcaption>{e(caption)}</figcaption>' if caption else '')+'</figure>'


def buttons(items):
    return '<div class="hc-links">'+''.join(f'<a href="{e(p)}">{e(n)} <span aria-hidden="true">↗</span></a>' for n,p in items)+'</div>'


def section(id, title, body, eyebrow='', cls=''):
    return f'<section id="{id}" class="hc-section {cls}"><div class="hc-wrap">'+(f'<p class="hc-kicker">{e(eyebrow)}</p>' if eyebrow else '')+f'<h2>{e(title)}</h2>{body}</div></section>'


def cards(items):
    return '<div class="hc-grid">'+''.join(f'<article class="hc-card"><h3>{e(a)}</h3><p>{e(b)}</p></article>' for a,b in items)+'</div>'


def faq(items):
    return section('faq','먼저 궁금한 내용', ''.join(f'<details class="hc-faq"><summary>{e(q)}</summary><p>{e(a)}</p></details>' for q,a in items),'QUESTIONS')


def hero(kicker,title,description,actions=(),aside=''):
    return '<section class="hc-hero"><div class="hc-wrap hc-hero-grid"><div>'+f'<p class="hc-kicker">{e(kicker)}</p><h1>{title}</h1><p class="hc-lead">{e(description)}</p>'+buttons(actions)+f'</div>{aside}</div></section>'


def page(path, title, description, body, crumbs, image='/assets/coaching-program/brand-learning.webp', graph_extra=(), article=False):
    canonical=url(path)
    crumbitems=[('홈','/'),*crumbs]
    graph=[{'@type':'Organization','@id':DOMAIN+'/#organization','name':'학습코칭.kr','url':DOMAIN+'/','logo':DOMAIN+'/assets/favicon.png'},
           {'@type':'WebSite','@id':DOMAIN+'/#website','url':DOMAIN+'/','name':'학습코칭.kr','inLanguage':'ko-KR','publisher':{'@id':DOMAIN+'/#organization'}},
           {'@type':'WebPage','@id':canonical+'#webpage','url':canonical,'name':title,'description':description,'inLanguage':'ko-KR','dateModified':DAY,'isPartOf':{'@id':DOMAIN+'/#website'},'breadcrumb':{'@id':canonical+'#breadcrumb'},'primaryImageOfPage':{'@type':'ImageObject','url':url(image)}},
           {'@type':'BreadcrumbList','@id':canonical+'#breadcrumb','itemListElement':[{'@type':'ListItem','position':i,'name':n,'item':url(p)} for i,(n,p) in enumerate(crumbitems,1)]}]
    doc=html.fromstring('<div>'+body+'</div>')
    faqs=doc.xpath('//details[contains(@class,"hc-faq")]')
    if faqs:
        graph.append({'@type':'FAQPage','@id':canonical+'#faq','isPartOf':{'@id':canonical+'#webpage'},'mainEntity':[{'@type':'Question','name':text(x.find('summary')),'acceptedAnswer':{'@type':'Answer','text':' '.join(text(p) for p in x.findall('p'))}} for x in faqs]})
    if article:
        graph.append({'@type':'Article','@id':canonical+'#article','headline':title,'description':description,'abstract':doc.xpath('string(//p[@class="hc-lead"])'),'inLanguage':'ko-KR','dateModified':DAY,'author':{'@id':DOMAIN+'/#organization'},'publisher':{'@id':DOMAIN+'/#organization'},'mainEntityOfPage':{'@id':canonical+'#webpage'},'image':url(image),'articleSection':[text(x) for x in doc.xpath('//h2')],'about':[{'@type':'Thing','name':'학습코칭'},{'@type':'Thing','name':'학습 진단과 복습 계획'}]})
    graph.extend(graph_extra)
    center_node=next((n for n in graph_extra if isinstance(n.get('@type'),list) and 'LocalBusiness' in n['@type']),None)
    if center_node:
        graph[2]['mainEntity']={'@id':center_node['@id']}
        graph[2]['about']={'@id':center_node['@id']}
    else:
        collection=next((n for n in graph_extra if n.get('@type')=='ItemList'),None)
        if collection:graph[2]['mainEntity']={'@id':collection['@id']}
    graph[2]['hasPart']=[{'@type':'WebPageElement','@id':canonical+'#'+s.get('id'),'name':s.xpath('string(.//h2)')} for s in doc.xpath('//section[@id]') if s.xpath('.//h2')]
    crumb='<nav class="hc-breadcrumb hc-wrap" aria-label="현재 위치">'+''.join(f'<a href="{e(p)}">{e(n)}</a>' for n,p in crumbitems[:-1])+f'<span aria-current="page">{e(crumbitems[-1][0])}</span></nav>' if crumbs else ''
    document=f'''<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(title)}</title><meta name="description" content="{e(description)}"><meta name="robots" content="index,follow">
<meta name="naver-site-verification" content="2a31a5b0ca9bc7ea33092692e93e1cc3ef67759a"><meta name="google-site-verification" content="y1oKPETiVrMA3NwTXeOp0_RB50F3tmV1XkRIBHw-nDI">
<link rel="canonical" href="{canonical}"><link rel="alternate" type="application/rss+xml" title="학습코칭 새 안내" href="{DOMAIN}/rss.xml"><link rel="icon" href="/assets/favicon.png">
<meta property="og:type" content="{'article' if article else 'website'}"><meta property="og:locale" content="ko_KR"><meta property="og:site_name" content="학습코칭.kr"><meta property="og:title" content="{e(title)}"><meta property="og:description" content="{e(description)}"><meta property="og:url" content="{canonical}"><meta property="og:image" content="{url(image)}"><meta property="og:image:alt" content="{e(title)}">
<meta name="twitter:card" content="summary_large_image"><meta name="twitter:title" content="{e(title)}"><meta name="twitter:description" content="{e(description)}"><meta name="twitter:image" content="{url(image)}">
<link rel="stylesheet" href="/assets/site.css"><link rel="stylesheet" href="/assets/coaching-upgrade.css?v=20260921"><script defer src="/assets/coaching-directory.js?v=20260921"></script>
<script type="application/ld+json">{j({'@context':'https://schema.org','@graph':graph})}</script></head><body class="hc-page"><a class="skip-link" href="#main">본문 바로가기</a>{header(path)}{crumb}<main id="main">{body}<p class="hc-updated hc-wrap">안내 검토일 <time datetime="{DAY}">2026년 9월 21일</time></p></main>{footer()}</body></html>'''
    dest=ROOT/path.strip('/')/'index.html' if path!='/' else ROOT/'index.html'
    write(dest,document)
    EDITORIAL[path]={'title':title,'description':description}


def program_summary():
    return section('learning-paths','알아야 할 내용부터 골라 보세요',buttons([
        ('공부 계획과 오답 점검','/학습가이드/#management-flow'),
        ('AI 학습이 맡는 역할','/학습가이드/#ai-learning'),
        ('처음 상담할 때 준비할 것','/진단상담/'),
        ('가까운 지점의 개설 학년','/지점안내/')]),'LEARNING PATHS')


def video_section():
    videos=[('avpJfW7eIV0','video-student','학생들이 이야기하는 학습 경험','공부 습관과 수업 경험을 학생의 이야기로 살펴보세요.'),('f_skFu40U04','video-coaching','센터장이 설명하는 학습코칭','수업과 학생 관리에 대한 운영 관점을 확인하세요.'),('UIXUaBZdNXU','video-exam','시험 준비를 돌아보는 사례','개별 경험을 참고해 우리 아이에게 필요한 질문을 정리해 보세요.')]
    return section('coaching-videos','이야기로 이해하는 학습코칭','<p>공식 홈페이지에 소개된 영상입니다. 특정 학생의 경험이 모든 학생의 결과를 의미하지는 않습니다.</p><div class="hc-grid">'+''.join(f'<a class="hc-video" href="https://www.youtube.com/watch?v={vid}" target="_blank" rel="noopener">{picture("/assets/coaching-program/"+img+".webp",title)}<span class="hc-video-body"><strong>{title}</strong><span>{desc}</span><small>영상 보기 · YouTube 새 창 ↗</small></span></a>' for vid,img,title,desc in videos)+'</div>','WATCH & UNDERSTAND')


def learning_pages():
    oldhome=html.parse(str(ROOT/'index.html'))
    # Preserve the owner's current tuition amounts, without presenting a universal offer.
    fee=oldhome.xpath('//div[contains(concat(" ",normalize-space(@class)," ")," tuition-panel ")]')
    if fee:
        save(DATA/'existing-fees.json', [html.tostring(x,encoding='unicode') for x in fee])
    else:
        fee=[html.fromstring(x) for x in json.loads((DATA/'existing-fees.json').read_text(encoding='utf-8'))]
    feehtml=''.join(html.tostring(x,encoding='unicode') for x in fee)
    feehtml=feehtml.replace('수업료는 기존 운영 기준과 동일하게 정리했습니다. 실제 등록 전에는 지역, 지점, 수업 조건에 따라 최종 안내가 달라질 수 있습니다.','월 수강료 참고 기준입니다. 선택한 지점의 수업 시간·과목 구성·신고 교습비를 확인한 뒤 최종 비용을 안내받으세요.')
    main=hero('LEARNING COACHING','공부의 다음 단계,<br>아이의 현재에서 찾습니다.',
        '학습코칭은 진도를 정하기 전에 이해 수준과 공부 습관을 함께 살피는 과정입니다. 학습 방법을 알아본 뒤, 지점별 개설 과목과 학년을 비교해 보세요.',
        [('지점부터 찾기','/지점안내/'),('코칭 방식 알아보기','/학습가이드/')],figure('brand-learning','학생별 학습을 안내하는 와와 코칭 프로그램',eager=True))
    main+=program_summary()
    main+=section('coaching-principle','같은 시간표보다, 서로 다른 출발점을 봅니다',
        '<div class="hc-split"><div><p>진도가 느린 이유가 모두 같은 것은 아닙니다. 개념을 설명하기 어려운 학생과, 이해한 내용을 혼자 적용하지 못하는 학생에게는 다른 연습이 필요합니다.</p><p>와와의 개별 맞춤 관리와 4C 흐름을 바탕으로, 이 사이트에서는 <strong>진단에서 무엇을 확인하고 다음 공부를 어떻게 정할지</strong>를 안내합니다. 별도 공간에서 선생님을 독점하는 과외 수업을 뜻하지는 않습니다.</p>'+buttons([('진단·계획·점검 흐름 읽기','/학습가이드/#management-flow')])+'</div>'+figure('four-c','진단과 학습 방향 조정을 연결하는 4C 관리 안내')+'</div>','COACHING, IN PRACTICE')
    main+=section('ai-overview','AI 결과는 다음 연습을 고르는 출발점',cards([
        ('어느 부분에서 막혔는지','영어는 영역별 이해, 수학은 단원과 풀이 과정을 살펴 취약한 부분을 좁힙니다.'),
        ('무엇을 다시 연습할지','진단 결과에 맞는 학습 자료와 오답 유형을 확인하고, 교사의 설명이 필요한 부분을 구분합니다.'),
        ('지점에서 무엇을 물어볼지','AI 프로그램의 대상 학년과 실제 지점의 도입 과목은 다를 수 있습니다. 이용 방식과 비용을 함께 확인하세요.')])+buttons([('과목별 AI 학습 범위','/학습가이드/#ai-learning'),('영어·수학 학원 안내','/과목별학원/')]),'AI & HUMAN COACHING')
    main+=video_section()
    main+=section('tuition','수강 전 비용도 확인하세요',feehtml,'TUITION')
    main+=faq([('학습 방법과 지점 정보 중 무엇부터 보면 좋을까요?','과목이나 공부 방법이 고민이라면 학습가이드부터, 통학과 시간표가 우선이라면 지점안내부터 확인하세요. 지점 페이지에서 개설 학년과 주변 학교를 함께 볼 수 있습니다.'),('AI 프로그램을 모든 지점에서 이용할 수 있나요?','공식 프로그램의 학년 범위는 공통 안내입니다. 지점별 도입 여부와 적용 과목, 수업료 포함 여부는 선택한 센터에 확인해야 합니다.'),('개별 맞춤 관리가 일대일 과외와 같은 뜻인가요?','공동 학습 공간에서도 학생별 교재와 설명, 점검 방법을 다르게 적용할 수 있습니다. 실제 수업 인원과 교사의 지도 방식은 상담에서 구체적으로 확인하세요.')])
    page('/','학습코칭 | 공부 방법·AI 학습·전국 지점안내','학생별 학습 진단과 계획·오답 점검, 과목별 AI 프로그램을 알아보세요. 전국 지점의 주소·개설 학년·주변 학교·학습 공간을 함께 안내합니다.',main,[])

    guide=hero('STUDY GUIDE','많이 하는 공부에서,<br>확인하며 하는 공부로.',
        '학습 기록은 학생을 평가하는 표에 그치지 않아야 합니다. 어디까지 이해했고 무엇을 다시 해볼지 정할 수 있도록, 코칭의 흐름과 AI 도구의 역할을 나누어 살펴봅니다.', [('코칭 흐름','#management-flow'),('AI 과목 안내','#ai-learning'),('지점 찾기','/지점안내/')])
    guide+=section('management-flow','진단과 계획 사이에, 해석하는 시간이 필요합니다',
        cards([('1. 현재 상태 읽기','최근 풀이와 학습 습관을 함께 살펴 개념 부족인지, 적용 연습 부족인지, 실행이 어려운 상황인지 구분합니다.'),('2. 우선할 공부 정하기','모든 약점을 한 번에 해결하려 하지 않고 먼저 연습할 개념과 교재 범위, 확인 방법을 고릅니다.'),('3. 실행 결과 보기','공부한 분량뿐 아니라 혼자 설명한 내용과 다시 막힌 문제를 남겨 다음 계획의 근거로 삼습니다.')])+'<p>공식 4C 관리 과정의 진단·처방·학습지도·상담은 한 번의 반 배정으로 끝나는 단계가 아닙니다. 실제 수업의 점검 주기와 기록 방식은 지점 운영에 따라 달라집니다.</p>'+figure('four-c','학습 진단에서 상담까지 연결되는 4C 흐름'),'COACHING FLOW')
    guide+=section('planner','계획표에는 분량과 확인 방법을 함께 적습니다',
        '<div class="hc-split"><div><p>“수학 1시간”보다 “틀린 유형 3문제를 해설 없이 풀고 막힌 줄을 표시하기”처럼 끝낸 상태가 보이는 계획이 점검하기 쉽습니다. 아래는 학습 방법을 설명하기 위한 예시이며 실제 수업 사례는 아닙니다.</p>'+cards([('시작 전','오늘 끝낼 범위와 다른 일정에 쓸 시간을 먼저 나눕니다.'),('마친 뒤','완료 여부 옆에 질문할 내용이나 시간이 더 걸린 이유를 한 줄 적습니다.')])+'</div>'+figure('learning-planner','플래너를 활용해 계획과 실행을 살펴보는 학습 관리 안내')+'</div>','PLAN & REFLECT')
    guide+=section('wrong-answer','오답을 남기는 이유는 다음 풀이를 바꾸기 위해서입니다',cards([('이유를 구분하기','개념을 몰랐는지, 조건을 놓쳤는지, 계산에서 어긋났는지를 풀이의 해당 부분에서 찾습니다.'),('한 가지 방법 바꾸기','공식을 다시 적는 대신 조건에 밑줄을 긋거나 식을 세운 이유를 말로 설명하는 등 원인에 맞는 행동을 고릅니다.'),('도움 없이 확인하기','다시 풀 때 정답뿐 아니라 풀이 근거를 설명할 수 있는지 봅니다. 어려움이 남으면 설명과 연습 범위를 다시 조정합니다.')]),'RELEARNING')
    guide+=section('ai-learning','AI 학습은 과목마다 살피는 내용이 다릅니다','<p>아래 대상은 공식 AI 프로그램 기준이며, 개별 센터의 수강 가능 학년이나 도입 여부를 대신하지 않습니다.</p><div class="hc-grid hc-two">'+''.join(
        f'<article class="hc-card" id="ai-{key}"><span class="hc-tag">{grade}</span><h3>{name}</h3><p>{desc}</p>{figure(img,name+" 프로그램 안내")}<p class="hc-small">상담 질문: {question}</p></article>' for key,grade,name,desc,img,question in [
            ('english','초1~고3','AI 영어','레벨 진단과 영역별 연습을 연결합니다. 기초 소리·문자 학습에서 어휘, 문장 구조와 읽기·듣기까지 필요한 영역을 구분해 볼 수 있습니다.','ai-english','현재 수준에 맞는 영역과 교사의 피드백은 어떻게 연결되나요?'),
            ('math','초1~고3','AI 수학','성취도에 맞춘 문제와 오답 유형을 활용합니다. 유사·변형 문제에서 같은 개념을 적용하는지 확인하는 데 목적을 둡니다.','ai-math','틀린 유형을 다시 연습할 때 풀이 과정도 확인하나요?'),
            ('korean','중1~고3','AI 국어','독서·문학·문법의 학습 결과를 나누어 보고, 취약한 개념에 맞는 문제와 해설을 활용합니다.','ai-korean','재학 학교의 학습 범위와 기초 독해 연습을 어떻게 나누나요?'),
            ('reading','초1~중2','AI 독서','관심 분야와 진로를 고려한 도서 선택, 읽은 내용을 정리하는 활동과 포트폴리오를 연결합니다.','ai-reading','책을 읽은 뒤 이해한 내용을 어떤 방식으로 확인하나요?')])+'</div>'+buttons([('지점별 개설 과목 확인','/지점안내/'),('과목별 학원 비교','/과목별학원/')]),'AI LEARNING')
    guide+=section('learning-environment','혼자 해보는 시간과 질문하는 시간이 연결되는 공간',
        '<div class="hc-split">'+figure('learning-space','선생님을 중심으로 학습하는 공간 구성 안내')+'<div><p>공식 안내의 둥지형 학습 공간은 선생님 주변에서 각자 공부하며 질문과 확인을 이어가는 구성을 설명합니다. 모든 센터의 배치나 수업 인원이 같다는 뜻은 아닙니다.</p><p>지점 사진을 볼 때는 좌석 모양만 보기보다 질문할 수 있는 방식, 개인별 진도 확인, 자습 이용 조건을 함께 물어보세요.</p>'+buttons([('센터 사진과 수업 조건','/지점안내/')])+'</div></div>','SPACE & FEEDBACK')
    guide+=video_section()
    guide+=faq([('플래너를 쓰는데도 공부가 밀리면 어떻게 하나요?','처음부터 모든 과목을 촘촘히 채우기보다 실제 걸린 시간과 미룬 이유를 적어 보세요. 이해가 어려워 시작하지 못한 경우와 분량이 과한 경우의 해결 방법은 다릅니다.'),('AI 점수가 높으면 복습을 끝내도 되나요?','점수만으로 판단하지 말고 설명 없이 풀 수 있는지, 풀이의 근거를 말할 수 있는지 확인해 보세요. 프로그램 결과는 교사의 관찰과 함께 해석할 자료입니다.'),('학습 관리와 생활 관리의 차이는 무엇인가요?','학습 관리는 교재·이해·오답 등 공부 내용을 살피고, 생활 관리는 실행에 영향을 주는 일정과 습관, 소통을 살핍니다. 센터에서 실제로 관리하는 범위와 공유 방식은 상담 때 확인하세요.')])
    page('/학습가이드/','학습코칭 가이드 | 플래너·오답 점검과 과목별 AI 학습','학습 진단, 실행 가능한 계획, 오답 원인 점검을 차례로 살펴봅니다. AI 영어·수학·국어·독서의 대상과 역할, 상담에서 확인할 질문을 정리했습니다.',guide,[('학습가이드','/학습가이드/')],article=True)

    diagnosis=hero('BEFORE YOUR VISIT','상담에서 남겨야 할 것은<br>다음 공부의 기준입니다.', '학년과 희망 과목만으로 수업을 결정하기보다 최근 풀이, 공부 일정, 혼자 하기 어려운 부분을 함께 정리해 보세요. 진단 결과를 다음 학습 계획에 연결하는 질문을 안내합니다.',[('상담할 지점 찾기','/지점안내/'),('상담 연락 안내','/상담문의/')])
    diagnosis+=section('consultation-questions','이 세 가지를 가져가면 이야기가 구체적입니다',cards([('최근에 푼 교재','정답뿐 아니라 학생이 남긴 식과 표시를 보면 설명이 필요한 지점을 찾기 쉽습니다. 일부 문제만 가져가도 괜찮습니다.'),('학교와 학년, 평가 일정','같은 학년이어도 수업 범위와 평가 일정이 다릅니다. 재학 학교와 준비해야 할 내용을 함께 전달하세요.'),('가능한 요일과 시간','통학과 다른 일정을 고려해 실제로 지속할 수 있는 시간을 정리합니다. 현재 자리와 시간표는 센터 확인이 필요합니다.')]),'PREPARE')
    diagnosis+=section('after-diagnosis','진단 결과를 들은 다음에는 이렇게 물어보세요',
        '<div class="hc-split"><div><ol class="hc-steps"><li><strong>먼저 보완할 내용은 무엇인가요?</strong><p>여러 약점 중 출발점이 되는 개념이나 습관을 구체적으로 확인합니다.</p></li><li><strong>수업과 집에서 할 일을 어떻게 나누나요?</strong><p>설명이 필요한 공부와 혼자 연습할 범위가 구분되는지 확인합니다.</p></li><li><strong>다음 점검에서는 무엇을 비교하나요?</strong><p>완료 분량만 볼지, 풀이와 이해 변화까지 확인할지 질문합니다.</p></li></ol></div>'+figure('teacher-coaching','학생의 이해와 실행을 함께 살피는 코칭 안내')+'</div>','ASK & DECIDE')
    diagnosis+=section('next-step','등록 전에는 조건을 한 번 더 맞춰보세요','<p>진단 결과와 실제 개설 학년은 별개입니다. 과목, 시간표, 교재비와 프로그램 비용, 보강 방식은 선택한 센터에서 확인하세요. 모든 지점이 동일한 AI 도구나 피드백 주기를 운영한다고 가정하지 않습니다.</p>'+buttons([('지점별 수업 범위','/지점안내/'),('AI 프로그램 이해하기','/학습가이드/#ai-learning'),('수강료 참고 기준','/#tuition')]),'NEXT STEP')
    diagnosis+=faq([('상담 전에 시험 결과가 꼭 있어야 하나요?','없어도 현재 학습 상황을 설명할 수 있습니다. 최근에 어려웠던 문제나 사용 중인 교재, 공부를 시작하기 어려운 순간을 적어 오면 상담에 도움이 됩니다.'),('수업 가능한 학년이면 바로 등록할 수 있나요?','개설 학년은 수업 범위 안내입니다. 현재 정원과 시간표, 과목 조합에 따라 등록 가능 여부가 달라질 수 있으므로 센터에 확인하세요.')])
    page('/진단상담/','학습 진단 상담 준비 | 교재·학교 일정·수업 조건 체크','학습 진단 상담에 준비할 교재와 일정, 진단 후 물어볼 질문을 정리했습니다. 학생의 현재 상태와 지점별 수업 조건을 함께 확인하세요.',diagnosis,[('진단상담','/진단상담/')],article=True)


def itemlist(path, name, pairs):
    return {'@type':'ItemList','@id':url(path)+'#list','name':name,'numberOfItems':len(pairs),'itemListElement':[{'@type':'ListItem','position':i,'name':n,'url':url(p)} for i,(n,p) in enumerate(pairs,1)]}


def search_panel():
    return '''<form class="hc-search" role="search" data-branch-search><label for="center-query">지점명·동네·학교로 찾기</label><div><input id="center-query" type="search" placeholder="예: 명일점, 천호동, 명일중학교" autocomplete="off"><button type="reset">초기화</button></div><p role="status" aria-live="polite" data-search-status>목록에서 지점을 선택하세요.</p></form><p data-search-empty hidden>검색 결과가 없습니다. 동네명 일부나 가까운 지역으로 다시 검색해 주세요.</p>'''


def branch_card(c):
    keywords=' '.join([c['displayName'],c['region'],c['district'],c['address'],*c['neighborhoods'],*(s for v in c['schools'].values() for s in v)])
    return f'<article class="hc-branch-card" data-center-keywords="{e(keywords)}"><span class="hc-tag">{e(c["region"])} · {e(c["district"])}</span><h3><a href="{e(route(c))}">{e(c["displayName"])}</a></h3><p>{e(c["address"])}</p><p class="hc-small">'+e(' · '.join(c['neighborhoods'][:4]) or '개설 과목과 학년을 지점에서 확인하세요')+f'</p><a class="hc-text-link" href="{e(route(c))}">수업 범위와 사진 보기 →</a></article>'


def directories(centers):
    groups={r:[c for c in centers if c['region']==r] for r in REGIONS}
    groups={r:cs for r,cs in groups.items() if cs}
    body=hero('FIND YOUR CENTER','통학할 곳을 찾고,<br>수업 조건까지 살펴보세요.',
        '지점명뿐 아니라 동네와 학교 이름으로도 찾을 수 있습니다. 센터별 주소, 과목별 개설 학년, 주변 학교와 학습 공간을 확인한 뒤 상담을 준비하세요.', [('지역 선택','#regions'),('지점 검색','#center-list'),('상담 준비','/진단상담/')])
    body+=section('regions','가까운 지역부터',buttons([(r,f'/지점안내/{r}/') for r in groups]),'REGIONS')
    body+=section('center-list','학교나 동네로 찾는 지점 목록',search_panel()+''.join(f'<section class="hc-region-group" data-region-group><h3>{r}</h3><div class="hc-grid">'+''.join(branch_card(c) for c in cs)+'</div></section>' for r,cs in groups.items()),'CENTER DIRECTORY')
    body+=section('choose-center','주소 다음에는 개설 학년을 확인하세요',cards([('수업 범위','영어와 수학의 개설 학년이 다를 수 있습니다. 지점 페이지에서 과목별로 구분해 확인하세요.'),('통학 조건','표시된 주변 학교는 상담 참고 범위입니다. 학교와의 제휴나 모든 시간대 수강을 뜻하지 않습니다.'),('학습 방식','공통 코칭 원리는 학습가이드에서 먼저 읽고, 적용 방식과 실제 시간표는 지점 상담에서 확인하세요.')])+buttons([('개별 관리와 AI 학습','/학습가이드/'),('지역별 학원 글','/전국학원/')]),'CHECK BEFORE VISITING')
    body+=faq([('학교 이름이 검색되지 않으면 수업을 들을 수 없나요?','주변 학교 목록은 상담을 위한 참고 정보이며 수강 자격을 제한하는 명단이 아닙니다. 학교가 없으면 가까운 동네나 지점명으로 검색한 뒤 희망 학년과 과목을 확인해 주세요.'),('지점안내와 전국학원 메뉴는 어떻게 다른가요?','지점안내는 센터 주소와 실제 개설 범위를 확인하는 메뉴입니다. 전국학원은 동네·과목을 기준으로 공부와 상담 내용을 찾아보는 기존 안내입니다.')])
    page('/지점안내/','전국 지점안내 | 동네·학교별 센터 찾기 · 학습코칭','전국 193개 센터의 주소, 과목별 개설 학년과 주변 학교를 찾아보세요. 지역·동네·학교 검색과 지점별 학습 공간 사진을 제공합니다.',body,[('지점안내','/지점안내/')],graph_extra=[itemlist('/지점안내/','시·도별 지점안내',[(r,f'/지점안내/{r}/') for r in groups])])
    for r,cs in groups.items():
        districts=list(dict.fromkeys(c['district'] for c in cs))
        description=f'{r} {", ".join(districts[:6])}'+(' 등' if len(districts)>6 else '')+'의 센터를 찾아보세요. 지점별 주소·수업 학년·주변 학교를 비교하고 상담 준비로 연결합니다.'
        body=hero(f'{r} / CENTER DIRECTORY',f'{e(r)}, 우리 아이가 다닐 지점 찾기',description,[('전체 지역','/지점안내/'),('이 지역 검색','#center-list')])
        body+=section('center-list',f'{r} 지점 안내',search_panel()+'<div class="hc-grid">'+''.join(branch_card(c) for c in cs)+'</div>','SELECT A CENTER')
        body+=section('visit-preparation',f'{r}에서 지점을 고르기 전','<p>동일 지역 안에서도 개설 과목과 학년이 다릅니다. 집이나 학교에서 이동할 수 있는지 살핀 뒤, 희망 과목의 개설 학년과 실제 수업 시간을 구분해 확인하세요.</p>'+buttons([('진단 상담 질문','/진단상담/'),('플래너와 오답 관리','/학습가이드/'),('과목별 학원 안내','/과목별학원/')]),'PREPARE YOUR VISIT')
        page(f'/지점안내/{r}/',f'{r} 지점안내 | 개설 학년·주소·학교별 센터 찾기',description,body,[('지점안내','/지점안내/'),(r,f'/지점안내/{r}/')],graph_extra=[itemlist(f'/지점안내/{r}/',r+' 센터 목록',[(c['displayName'],route(c)) for c in cs])])


QUESTIONS={
 '플래너 점검':('계획을 실행하는 방식','과목별 분량과 마감일을 누가 정하고, 계획이 밀렸을 때 어떻게 조정하나요?','/학습가이드/#planner'),
 '오답 재학습':('틀린 문제를 다시 보는 방식','오답 원인을 구분한 뒤, 도움 없이 다시 풀 수 있는지 어떤 방식으로 확인하나요?','/학습가이드/#wrong-answer'),
 '학교별 내신 준비':('학교 평가에 맞추는 준비','재학 학교의 시험 범위와 수업 진도를 언제 확인하고 계획에 반영하나요?','/진단상담/'),
 '시험기간 계획':('시험 전 학습 배분','학교 평가 일정이 겹칠 때 과목별 공부량과 질문 시간을 어떻게 나누나요?','/진단상담/'),
 '학습 기록':('공부 결과를 남기는 기준','수업 후 기록에는 진도 외에 질문과 재학습할 내용도 함께 남기나요?','/학습가이드/#management-flow'),
 '보호자 피드백':('가정과 나누는 학습 정보','어떤 기록을 어떤 주기로 공유하며, 가정에서 확인할 부분은 어떻게 안내하나요?','/학습가이드/#learning-environment'),
 '독서 활동':('읽기와 이해 확인','책을 선택하고 읽은 뒤 생각을 정리하는 과정은 어떻게 이루어지나요?','/학습가이드/#ai-reading'),
 '고등 학습 상담':('고등 공부의 우선순위','학교 수업과 진로 계획을 고려해 과목별 학습 순서를 어떻게 상담하나요?','/진단상담/'),
 '자습 운영':('스스로 공부하는 시간','자습이 가능한 요일과 이용 조건, 질문할 수 있는 시간을 확인하고 싶습니다.','/진단상담/'),
 '학습 도구 활용':('AI 도구와 수업의 연결','실제 도입한 AI 과목과 결과를 해석하는 방법, 추가 비용이 있나요?','/학습가이드/#ai-learning'),
 '과목 연계 관리':('여러 과목을 조율하는 기준','여러 과목을 함께 공부할 때 숙제와 평가 준비가 겹치지 않도록 어떻게 조정하나요?','/학습가이드/#planner'),
}


def primary_media(c):
    m=c['primaryMedia']; body=m['body']; name=c['displayName']
    hidden=f'<img class="hc-representative" hidden loading="lazy" src="{e(m["representative"]["src"])}" alt="{e(name)} 대표이미지" width="{m["representative"]["width"]}" height="{m["representative"]["height"]}">'
    # Entire source image remains visible; no clipping, overlays, or read-more gate.
    sources=''
    for typ, variants in body.get('variants',{}).items():
        sources+=f'<source type="image/{typ}" srcset="'+e(', '.join(v['src']+' '+str(v['width'])+'w' for v in variants))+'" sizes="(max-width: 720px) calc(100vw - 40px), 760px">'
    bodypic='<picture>'+sources+picture(body['src'],name+' 본문')+'</picture>'
    return section('center-images','수업과 방문 위치 안내',hidden+'<div class="hc-primary-media"><figure>'+bodypic+f'<figcaption>{e(name)} 본문</figcaption></figure><figure>'+picture(m['map']['src'],name+' 지도')+f'<figcaption>{e(name)} 지도</figcaption></figure></div>','CENTER INFORMATION')


def branch_pages(centers):
    for c in centers:
        name=c['displayName']; branch=c['routeName']; path=route(c); canonical=url(path)
        if branch=='덕이점':
            c['weekend']='토요일 모의고사 관련 특강이 안내돼 있습니다. 수업 과목과 대상 학년, 현재 일정은 센터 상담에서 확인해 주세요.'
        grades=[v['subject']+' '+v['label'] for v in c['courses'] if v['grades']]
        neighborhoods=' · '.join(c['neighborhoods'])
        intro=f'{name}은 {c["address"]}에 있습니다. '+(f'{neighborhoods}에서 통학을 고려한다면 ' if neighborhoods else '')+'아래 과목별 개설 학년과 학교 정보를 먼저 살펴보세요.'
        description=f'{name}의 주소와 수업 안내. '+(' / '.join(grades[:3])+'. ' if grades else '')+'주변 학교, 학습 공간 사진, 방문 전 확인할 조건을 정리했습니다.'
        body=hero(c['region']+' · '+c['district'],e(name),intro,[('개설 과목·학년','#courses'),('학교·동네','#schools'),('위치 확인','#location')])
        body+=section('center-info',branch+' 기본정보',f'<dl class="hc-facts"><div><dt>센터 주소</dt><dd>{e(c["address"])}</dd></div><div><dt>등록 학원명</dt><dd>{e(c["registeredName"])}</dd></div><div><dt>등록번호</dt><dd>{e(c["registrationNumber"])}</dd></div><div><dt>상담 참고 지역</dt><dd>{e(neighborhoods or c["district"])}</dd></div></dl>','CENTER FACTS')
        courses=''
        for v in c['courses']:
            if not v['rawGrades'] and not v['notes']: continue
            courses+=f'<article class="hc-course"><h3>{v["subject"]}</h3><p class="hc-course-grades">{e(v["label"])}</p>'+''.join(f'<p class="hc-small">{e(n)}</p>' for n in v['notes'])+'</article>'
        body+=section('courses','과목마다 개설 학년이 다를 수 있습니다','<div class="hc-grid hc-course-grid">'+courses+'</div>'+''.join(f'<p class="hc-notice">{e(n)}</p>' for n in c['courseNotes'])+'<p class="hc-small">개설 학년과 현재 등록 가능한 시간표는 별개입니다. 희망 과목·요일의 배정 여부를 확인해 주세요.</p>','SUBJECTS & GRADES')
        schools=''
        for level,items in c['schools'].items():
            if not items: continue
            label={'초등':'초등학교','중등':'중학교','고등':'고등학교'}[level]
            schools+=f'<article class="hc-card"><h3>{label}</h3><ul class="hc-school-list">'+''.join(f'<li>{e(s)}</li>' for s in items)+'</ul></article>'
        body+=section('schools',branch+' 상담에 참고할 학교와 동네',f'<p>{e(neighborhoods+"의 " if neighborhoods else "")}학교 일정과 학생의 현재 진도를 함께 알려주시면 상담 내용을 구체화하는 데 도움이 됩니다.</p><div class="hc-grid">'+schools+'</div><p class="hc-small">학교 목록은 상담 참고 정보입니다. 학교와의 제휴, 통학 지원 또는 모든 학년의 수업 개설을 의미하지 않습니다.</p>','SCHOOL & NEIGHBORHOOD')
        chosen=[QUESTIONS[k] for k in c['managementTopics'] if k in QUESTIONS][:3]
        if chosen:
            body+=section('learning','이 지점에서 구체적으로 물어볼 내용','<p>지점의 학습관리 안내 항목을 상담 질문으로 정리했습니다. 실제 운영 범위와 점검 주기는 상담에서 확인하세요.</p><div class="hc-grid">'+''.join(f'<article class="hc-card"><h3>{e(a)}</h3><p>{e(b)}</p><a class="hc-text-link" href="{u}">관련 학습 방법 읽기 →</a></article>' for a,b,u in chosen)+'</div>','YOUR CONSULTATION')
        else:
            body+=section('learning',branch+' 상담을 구체적으로 준비하려면',f'<p>{e(c["schools"].get("중등",[""])[0] if c["schools"].get("중등") else c["district"])} 등 재학 학교와 학년, 최근에 어려웠던 교재 내용을 함께 정리해 보세요. 위 표의 개설 범위 안에서 설명이 필요한 과목과 혼자 연습할 부분을 나누어 상담할 수 있습니다.</p>'+buttons([('준비할 자료와 상담 질문','/진단상담/'),('플래너·오답 점검 방법','/학습가이드/')]),'YOUR CONSULTATION')
        location=c['locationGuide']
        # Prefer verified address over malformed conversational directions.
        if branch=='갈매점': location='에스엠타워 6층 602호입니다. 건물 출입구와 입실 방법을 방문 전에 확인해 주세요.'
        loc=f'<p class="hc-address">{e(c["address"])}</p>'+(f'<p>{e(location)}</p>' if location else '')
        if c.get('openingReference'): loc+=f'<p>운영 참고 시간: {e(c["openingReference"])}. 상담 가능 시간과 수업 시작 시간은 방문 전에 확인해 주세요.</p>'
        loc+=f'<p>{e(c["weekend"])}</p><p class="hc-small">건물 내 입점 점포와 출입 안내는 바뀔 수 있으므로 주소를 기준으로 확인해 주세요.</p>'
        loc+=f'<a class="hc-map-link" href="https://map.naver.com/p/search/{quote(c["registeredName"]+" "+c["address"],safe="")}" target="_blank" rel="noopener">네이버 지도에서 주소 확인 ↗</a>'
        body+=section('location','처음 방문할 때 확인하세요',loc,'VISIT')
        faqitems=[(branch+'에서는 어떤 과목과 학년을 안내하나요?',('안내 범위는 '+', '.join(grades)+'. ' if grades else '개설 학년은 센터 문의가 필요합니다. ')+'과목별 조건은 위 개설 학년 항목을 함께 확인하고, 현재 수강 가능한 시간대를 상담해 주세요.'),
            (branch+' 방문 주소는 어디인가요?',c['address']+'입니다. '+(location+' ' if location else '')+'방문 전 상담 시간을 정한 뒤 이동해 주세요.'),
            ('주변 학교 목록에 없으면 상담이 어려운가요?','목록은 수업 상담에 참고할 학교를 정리한 것이며 대상 학생을 제한하지 않습니다. 실제 재학 학교·학년·희망 과목을 전달해 개설 범위와 시간표를 확인해 주세요.'),
            ('AI 프로그램과 수강료는 어떻게 확인하나요?','공식 프로그램의 학년 범위와 센터의 실제 도입 과목은 다를 수 있습니다. '+branch+' 상담에서 이용 가능한 도구, 교재와 추가 비용, 주당 수업 시간과 최종 교습비를 함께 확인하세요.')]
        body+=faq(faqitems)
        related=[('다른 '+c['region']+' 지점',f'/지점안내/{c["region"]}/'),('AI와 개별 맞춤 관리','/학습가이드/#ai-learning')]
        regionold={'강원':'강원','경기':'경기','서울':'서울','충남':'충청','충북':'충청','경북':'경상','경남':'경상','전북':'전라','전남':'전라'}.get(c['region'],c['region'])
        if (ROOT/'전국학원'/regionold/'index.html').exists(): related.append((c['region']+' 지역 학원 글',f'/전국학원/{regionold}/'))
        body+=section('related-pages','이어서 확인할 정보',buttons(related),'NEXT READING')
        body+=primary_media(c)
        gallery=''.join('<figure>'+picture(p,(name+' 학습 공간 ' if c['photoMode']=='center' else '학습 공간 구성 ')+str(i))+'</figure>' for i,p in enumerate(c['photos'],1))
        body+=section('learning-space','학습 공간 살펴보기','<details class="hc-gallery-toggle"><summary>사진 펼쳐 보기</summary><div class="hc-grid hc-two hc-gallery">'+gallery+'</div></details>','LEARNING SPACE')
        orgid=canonical+'#center'
        services=[{'@type':'Service','@id':canonical+'#service-'+s['subject'],'name':name+' '+s['subject']+' 수업 안내','serviceType':s['subject']+' 학습코칭','provider':{'@id':orgid},'areaServed':{'@type':'AdministrativeArea','name':c['region']+' '+c['district']},'audience':{'@type':'EducationalAudience','educationalRole':'student','audienceType':s['label']+' 학생'},'description':s['subject']+' '+s['label']+'. '+' '.join(s['notes'])} for s in c['courses'] if s['grades']]
        org={'@type':['EducationalOrganization','LocalBusiness'],'@id':orgid,'name':name,'legalName':c['registeredName'],'url':canonical,'address':{'@type':'PostalAddress','addressCountry':'KR','addressRegion':c['region'],'streetAddress':c['address']},'image':[url(p) for p in c['photos']] if c['photoMode']=='center' else [url(c['primaryMedia']['map']['src'])],'hasOfferCatalog':{'@type':'OfferCatalog','name':'과목별 개설 안내','itemListElement':[{'@type':'Offer','itemOffered':{'@id':s['@id']}} for s in services]}}
        page(path,name+' | 개설 학년·학교·위치 안내',description,body,[('지점안내','/지점안내/'),(c['region'],f'/지점안내/{c["region"]}/'),(branch,path)],c['primaryMedia']['representative']['src'],[org,*services,itemlist(path,'함께 읽을 안내',related)])


def hub_upgrades(centers):
    paths=[ROOT/'전국학원/index.html',ROOT/'과목별학원/index.html',*sorted((ROOT/'전국학원').glob('*/index.html')),*sorted((ROOT/'과목별학원').glob('*/index.html'))]
    for p in paths:
        s=p.read_text(encoding='utf-8'); s=re.sub(r'<!-- COACHING CONNECTION START -->.*?<!-- COACHING CONNECTION END -->','',s,flags=re.S)
        path='/'+p.parent.relative_to(ROOT).as_posix()+'/'
        topic=p.parent.name
        if path.startswith('/전국학원/') and path.count('/')==3:
            regions={'경상':['경북','경남'],'전라':['전북'],'충청':['충북','충남']}.get(topic,[topic])
            selected=[r for r in regions if any(c['region']==r for c in centers)]
            prose=f'{topic} 지역 글에서 공부 방향을 살펴보았다면, 실제 센터의 주소와 과목별 개설 학년을 함께 확인해 보세요. 같은 지역에서도 운영 과목과 시간표가 다를 수 있습니다.'
            links=[(r+' 센터 정보',f'/지점안내/{r}/') for r in selected]+[('진단 상담 준비','/진단상담/')]
        else:
            if '수학' in topic: focus='개념을 설명할 수 있는지와 문제에 적용할 수 있는지는 다를 수 있습니다. 풀이에서 막힌 단계와 오답 유형을 먼저 정리한 뒤, 필요한 수업 범위를 센터에서 상담해 보세요.'; anchor='ai-math'
            elif '영어' in topic: focus='어휘를 외우는 공부와 문장 구조를 읽어내는 공부를 구분해 보세요. 진단 결과에서 부족한 영역을 살핀 뒤 수업과 혼자 할 연습을 어떻게 연결할지 확인합니다.'; anchor='ai-english'
            elif '고등' in topic: focus='학교 평가 일정과 과목별 이해 차이를 함께 놓고 우선순위를 정하는 것이 중요합니다. 시험 범위와 최근 풀이를 준비해, 설명이 필요한 단원과 혼자 연습할 범위를 나누어 상담하세요.'; anchor='management-flow'
            elif '중학' in topic: focus='숙제를 끝낸 것과 내용을 이해한 것은 다를 수 있습니다. 풀이를 설명하거나 틀린 이유를 찾는 기록으로 점검하고, 학교 일정에 맞춰 복습 범위를 조정하는 방법을 확인해 보세요.'; anchor='wrong-answer'
            elif '초등' in topic: focus='오래 앉아 있기보다 스스로 시작하고 마치는 경험을 먼저 살펴보세요. 읽은 내용을 말하거나 풀이를 설명하는 짧은 확인 과정과, 실제로 지킬 수 있는 공부 분량을 상담합니다.'; anchor='planner'
            else: focus='개별 맞춤 관리는 모든 학생에게 같은 시간표를 적용하는 방식과 다릅니다. 학습 진단으로 출발점을 정하고 계획·실행·재학습을 연결하는 방법을 알아본 뒤, 센터의 수업 조건을 확인하세요.'; anchor='management-flow'
            prose=focus
            links=[('코칭 방법 자세히 보기','/학습가이드/#'+anchor),('개설 과목·학년 확인','/지점안내/')]
        content=section('center-connection','학습 방법에서 실제 수업 조건으로',f'<p>{e(prose)}</p>'+buttons(links)+f'<p class="hc-small">안내 보완일 <time datetime="{DAY}">2026년 9월 21일</time></p>','COACHING & CENTER')
        s=s.replace('</main>','<!-- COACHING CONNECTION START -->'+content+'<!-- COACHING CONNECTION END --></main>',1)
        def update_graph(m):
            data=json.loads(m.group(1))
            for node in data.get('@graph',[data]):
                if node.get('@type') in ('WebPage','CollectionPage','Article'):
                    node['dateModified']=DAY
                    parts=node.setdefault('hasPart',[])
                    if isinstance(parts,dict):parts=[parts];node['hasPart']=parts
                    parts[:]=[x for x in parts if x.get('@id')!=url(path)+'#center-connection']
                    parts.append({'@type':'WebPageElement','@id':url(path)+'#center-connection','name':'학습 방법에서 실제 수업 조건으로'})
            return '<script type="application/ld+json">'+j(data)+'</script>'
        s=re.sub(r'<script type="application/ld\+json">(.*?)</script>',update_graph,s,flags=re.S)
        doc=html.fromstring(s)
        title=doc.xpath('string(//title)');desc=doc.xpath('string(//meta[@name="description"]/@content)')
        image=doc.xpath('string(//meta[@property="og:image"]/@content)') or url('/assets/coaching-program/brand-learning.webp')
        for key,value in [('og:title',title),('og:description',desc),('twitter:card','summary_large_image'),('twitter:title',title),('twitter:description',desc),('twitter:image',image)]:
            attr='property' if key.startswith('og:') else 'name'
            tag=f'<meta {attr}="{key}" content="{e(value)}">'
            pattern=r'<meta\s+(?:name|property)="'+re.escape(key)+r'"[^>]*>'
            if re.search(pattern,s):s=re.sub(pattern,lambda _:tag,s)
            else:s=s.replace('</head>',tag+'\n</head>',1)
        write(p,s)
        doc=html.fromstring(s);EDITORIAL[path]={'title':doc.xpath('string(//title)'),'description':doc.xpath('string(//meta[@name="description"]/@content)')}


def unify_navigation():
    count=0
    for p in ROOT.rglob('*.html'):
        if any(x in {'tools','tmp','.git'} for x in p.relative_to(ROOT).parts): continue
        s=p.read_text(encoding='utf-8')
        if '<header' not in s: continue
        path='/'+p.parent.relative_to(ROOT).as_posix().strip('.')+'/'
        path=path.replace('//','/')
        s,n=re.subn(r'<header\b.*?</header>',lambda _:header(path),s,count=1,flags=re.S)
        if 'coaching-upgrade.css' not in s:
            s=s.replace('</head>','<link rel="stylesheet" href="/assets/coaching-upgrade.css?v=20260921">\n</head>',1)
        write(p,s);count+=n
    return count


def discovery():
    p=ROOT/'sitemap.xml'; tree=etree.parse(str(p)); ns={'s':'http://www.sitemaps.org/schemas/sitemap/0.9'}; root=tree.getroot()
    indexed={unquote(n.find('s:loc',ns).text):n for n in root}
    for path in EDITORIAL:
        u=url(path); node=indexed.get(unquote(u))
        if node is None:
            node=etree.SubElement(root,'{'+ns['s']+'}url'); etree.SubElement(node,'{'+ns['s']+'}loc').text=u
        lm=node.find('s:lastmod',ns)
        if lm is None: lm=etree.SubElement(node,'{'+ns['s']+'}lastmod')
        lm.text=DAY
    write(p,etree.tostring(tree,encoding='unicode',pretty_print=True))
    # Latest useful entries, not a claim that every historic page changed today.
    rss=etree.parse(str(ROOT/'rss.xml'));ch=rss.find('channel')
    for node in list(ch.findall('item')): ch.remove(node)
    recent=['/','/학습가이드/','/진단상담/','/지점안내/']+[p for p in EDITORIAL if p.startswith('/지점안내/') and p.count('/')==3]+[p for p in EDITORIAL if p.startswith('/지점안내/') and p.count('/')==4][:30]
    for path in recent:
        v=EDITORIAL[path];item=etree.SubElement(ch,'item')
        for key,value in [('title',v['title']),('link',url(path)),('guid',url(path)),('description',v['description']),('pubDate','Sun, 20 Sep 2026 22:58:58 GMT')]: etree.SubElement(item,key).text=value
    for tag in ['lastBuildDate','pubDate']:
        for node in ch.findall(tag): node.text='Sun, 20 Sep 2026 22:58:58 GMT'
    write(ROOT/'rss.xml',etree.tostring(rss,encoding='unicode',pretty_print=True))
    p=ROOT/'llms.txt';s=p.read_text(encoding='utf-8');s=re.sub(r'\n## 지점안내와 학습 프로그램[\s\S]*','',s)
    s+='\n## 지점안내와 학습 프로그램\n\n- [전국 지점안내]('+url('/지점안내/')+')\n- [코칭과 AI 학습가이드]('+url('/학습가이드/')+')\n- [상담 준비]('+url('/진단상담/')+')\n\n지점별 주소·등록명·과목별 학년·주변 학교를 안내합니다. 개설 학년과 현재 등록 가능 여부는 다릅니다. 공통 AI 프로그램의 대상은 개별 지점의 도입 여부를 보장하지 않습니다. 실제 운영 조건은 지점 상담에서 확인합니다.\n'
    write(p,s)
    save(DATA/'release-pages.json',EDITORIAL)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--import-source',action='store_true');args=parser.parse_args()
    if args.import_source: import_source()
    for p in DATA.glob('*.json'):write(p,p.read_text(encoding='utf-8'))
    centers=json.loads((DATA/'centers.json').read_text(encoding='utf-8'))['centers']
    learning_pages();directories(centers);branch_pages(centers);hub_upgrades(centers)
    nav=unify_navigation();discovery()
    print(j({'centers':len(centers),'regions':len({c['region'] for c in centers}),'contentPages':len(EDITORIAL),'navigationPages':nav}))


if __name__=='__main__':main()
