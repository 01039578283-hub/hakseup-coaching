"""Create English/math branch children and enrich only the branch directory.

Input workbooks are read-only. There is no push or deployment operation here.
"""
from __future__ import annotations
import argparse
import copy
import hashlib
import json
import os
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urljoin
import openpyxl
from lxml import etree, html
import build_coaching_directory as base
from subject_editorial import choose, STAGES

ROOT = base.ROOT
DATA = ROOT / 'tools/data/subject-pages'
SOURCE = Path(r'C:\Users\1992k\Desktop\홈페이지 정리\참고자료\원고모음(엑셀)')
DAY = '2026-09-21'
e, url, section, buttons, cards = base.e, base.url, base.section, base.buttons, base.cards

# Explicitly reviewed against the other subject workbook and center manifest.
# Rows refer to the A열_텍스트파일 sheet, including its single header row.
CORRECTIONS = {
    '영어': {107:'단대동', 135:'대야동', 215:'삼산동', 221:'연수동', 286:'도남지구',
             357:'중화산동', 312:'반구동', 363:'개운동'},
    '수학': {113:'수진동', 121:'호매실', 136:'은행동', 186:'이충동', 222:'송도',
             348:'첨단', 361:'단구동', 312:'반구동', 363:'개운동'},
}


def norm(value): return ' '.join(str(value).split())
def compact(value): return re.sub(r'\s+', '', value)
def read_json(path): return json.loads(path.read_text(encoding='utf-8'))
def file_for(path): return ROOT / path.strip('/') / 'index.html'
def subject_path(c, locality, subject): return base.route(c) + compact(locality) + subject + '학원/'
def html_fragment(value): return html.fragment_fromstring(value)


def capture_baseline():
    target = DATA / 'baseline.json'
    if target.exists(): return
    files = {}
    for current, dirs, names in os.walk(ROOT):
        dirs[:] = [d for d in dirs if d not in {'.git','.vercel','tools','tmp','reports','지점안내','node_modules'}]
        for name in names:
            p = Path(current)/name
            rel = p.relative_to(ROOT).as_posix()
            if rel == 'assets/branch-subjects.css': continue
            if p.suffix in ['.html','.css','.js','.jpg','.png','.gif','.webp','.avif'] or rel in ['robots.txt','vercel.json','wawa-analytics-build.mjs']:
                files[rel] = base.sha(p)
    branches = {}
    for p in (ROOT / '지점안내').rglob('index.html'):
        doc = html.parse(str(p))
        path = '/' + p.parent.relative_to(ROOT).as_posix() + '/'
        branches[path] = {
            'title':doc.xpath('string(//title)'),
            'images':[(i.get('src'), i.get('alt')) for i in doc.xpath('//main//img')],
            'sections':{sid:norm(doc.xpath('string(//*[@id=$sid])',sid=sid))
                        for sid in ['center-info','courses','schools','location','learning-space']
                        if doc.xpath('//*[@id=$sid]',sid=sid)},
        }
    base.save(target, {'day':DAY, 'protectedFiles':files, 'branches':branches,
                       'sitemap':(ROOT/'sitemap.xml').read_text(encoding='utf-8'),
                       'rss':(ROOT/'rss.xml').read_text(encoding='utf-8')})


def extract(centers):
    lookup = {n:c for c in centers for n in c['neighborhoods']}
    assert len(lookup) == 371
    names = sorted(lookup, key=lambda value:-len(compact(value)))
    records, sources, corrections = [], [], []
    matches_by_subject = {}
    for subject in ['영어', '수학']:
        path = SOURCE / (subject+'학원 원고.xlsx')
        book = openpyxl.load_workbook(path, read_only=True, data_only=True)
        sheets = {}
        for sheet_name in ['A열_텍스트파일', 'Sheet1']:
            sheets[sheet_name] = [(i+1, re.sub(r'_x000D_', '\r', str(row[0])))
                                 for i,row in enumerate(book[sheet_name].iter_rows(values_only=True))
                                 if row and row[0] and '<h1' in str(row[0])]
        a, b = sheets.values()
        assert len(a) == len(b) == 371
        semantic = lambda value: re.sub(r'[\W_]+','',html.fromstring(value).text_content())
        # Export also drops one stray Persian word (meaning "base") in English
        # row 58. The rewritten copy never imports this foreign drafting artifact.
        assert all(semantic(x) == semantic(y.replace('پایه','') if subject=='영어' and row==58 else y)
                   for (row,x),(_,y) in zip(a,b)), 'Unexpected difference between duplicate workbook sheets'
        punctuation_rows = [row for (row,x),(_,y) in zip(a,b) if norm(html.fromstring(x).text_content()) != norm(html.fromstring(y).text_content())]
        sources.append({'file':path.name,'sha256':base.sha(path),'sheet':'Sheet1',
                        'cells':371,'duplicateSheet':'A열_텍스트파일','duplicateRecordsIgnored':371,
                        'exportPunctuationRepairRows':punctuation_rows,
                        'discardedForeignDraftArtifactRows':[58] if subject=='영어' else []})
        matched = []
        for (row, _), (original_row, raw) in zip(a,b):
            doc = html.fromstring(raw)
            # Supplied scripts, links and claims are never inserted as executable HTML.
            for node in doc.xpath('//script|//style|//iframe'): node.drop_tree()
            title = norm(doc.xpath('string(//h1)'))
            locality = next((n for n in names if compact(title).startswith(compact(n))), None)
            if row in CORRECTIONS[subject]:
                fixed = CORRECTIONS[subject][row]
                assert compact(fixed) in compact(doc.text_content()), (subject,row,fixed)
                corrections.append({'subject':subject,'sourceRow':row,'originalTitle':title,'locality':fixed,
                                    'reason':'Compared paired workbook row and verified center neighborhoods; discarded incorrect city prefix.'})
                locality = fixed
            assert locality in lookup, (subject,row,title)
            c = lookup[locality]
            paragraphs = [norm(p.text_content()) for p in doc.xpath('//p') if norm(p.text_content())]
            source_text = '\n'.join(paragraphs)
            focused, scores = choose(subject, source_text)
            record = {'locality':locality,'subject':subject,'branch':c['routeName'],'region':c['region'],
                      'parentPath':base.route(c),'path':subject_path(c,locality,subject),
                      'title':locality+' '+subject+'학원','focuses':[p['key'] for p in focused],
                      'focusScores':scores,'sourceFile':path.name,'sourceSheet':'Sheet1',
                      'sourceCell':'A'+str(original_row),'exportCell':'A'+str(row),'sourceTitle':title,'sourceText':source_text,
                      'sourceTextSha256':hashlib.sha256(source_text.encode()).hexdigest()}
            records.append(record); matched.append(locality)
        assert len(set(matched)) == 371 and set(matched) == set(lookup), Counter(matched)
        matches_by_subject[subject] = matched
        book.close()
    assert matches_by_subject['영어'] == matches_by_subject['수학'], 'Paired rows do not identify the same neighborhood'
    assert len({r['path'] for r in records}) == 742
    old = read_json(DATA/'manifest.json') if (DATA/'manifest.json').exists() else {}
    manifest = {'createdAt':old.get('createdAt',datetime.now(timezone.utc).isoformat()),
                'modifiedAt':DAY,'sources':sources,'corrections':corrections,'records':records}
    base.save(DATA/'manifest.json',manifest)
    print(base.j({'workbooks':2,'neighborhoods':371,'newPages':742,'duplicateSheetRecordsIgnored':742,
                  'reviewedTitleMappings':len(corrections),'focusCombinations':len({(r['subject'],*r['focuses']) for r in records})}))
    return manifest


def graph_of(doc):
    node = doc.xpath('//script[@type="application/ld+json"]')[0]
    return node, json.loads(node.text)['@graph']


def set_meta(doc, key, value):
    attr = 'property' if key.startswith('og:') else 'name'
    nodes = doc.xpath('//meta[@'+attr+'=$key]',key=key)
    if nodes: nodes[0].set('content',value)
    else: etree.SubElement(doc.find('head'),'meta',**{attr:key,'content':value})


def add_styles(doc):
    if not doc.xpath('//link[contains(@href,"branch-subjects.css")]'):
        etree.SubElement(doc.find('head'),'link',rel='stylesheet',href='/assets/branch-subjects.css?v=20260921')


def save_document(path, doc, graph=None):
    if graph is not None:
        script,_ = graph_of(doc)
        script.text = base.j({'@context':'https://schema.org','@graph':graph})
    add_styles(doc)
    # lxml's HTML4 serializer does not know the HTML5 void element source.
    markup = html.tostring(doc,encoding='unicode',method='html').replace('</source>','')
    base.write(file_for(path), '<!doctype html>\n'+markup)


def stage_rows(c, subject):
    course = next(v for v in c['courses'] if v['subject']==subject)
    selected = []
    for level, prefix in [('초등','초'),('중등','중'),('고등','고')]:
        grades = [g for g in course['grades'] if g.startswith(prefix)]
        if not grades: continue
        title, message = STAGES[subject][level]
        schools = c['schools'].get(level,[])
        selected.append((level,grades,title,message,schools))
    return course, selected


def subject_media(c, title):
    media = copy.deepcopy(c)
    media['displayName'] = title
    return base.primary_media(media)


def render_subject(c, r, all_records):
    subject, locality, title, path = r['subject'],r['locality'],r['title'],r['path']
    course, stage = stage_rows(c, subject)
    focus, _ = choose(subject,r['sourceText'])
    parent = base.route(c)
    grade_sentence = (f'{subject} 안내 학년은 {course["label"]}입니다.' if course['grades']
                      else f'{subject}의 현재 개설 학년과 수업 장소는 {c["routeName"]}에 먼저 확인해 주세요.')
    lead = f'{locality}에서 {subject}학원을 알아본다면 {c["displayName"]}의 수업 범위부터 살펴보세요. {grade_sentence} 이 글에서는 {focus[0]["summary"]}과 상담에 가져갈 학습 기록을 정리했습니다.'
    description = f'{title}을 찾는 학생을 위한 {c["routeName"]} 안내. '+(f'{subject} {course["label"]}, ' if course['grades'] else '개설 여부 확인, ')+f'{focus[0]["summary"]}, 학교 자료와 방문 위치를 확인하세요.'
    body = base.hero(c['region']+' · '+c['district']+' / '+c['routeName'],e(title),lead,
                     [('학습 점검부터','#study-focus'),('개설 학년·학교','#subject-courses'),('지점 기본정보',parent)])
    body += section('subject-location','어느 지점의 안내인가요?',
                    f'<p><strong>{e(c["displayName"])}</strong>의 주소는 {e(c["address"])}입니다. {e(locality)} 일대는 이 지점의 상담 참고 지역이며, 별도의 학원 지점을 뜻하지 않습니다.</p>'+
                    (f'<p class="hc-notice">이 페이지에서 연결하는 실제 학원은 {e(c["registeredName"])}입니다.</p>' if '모두' in c['brand'] else '')+
                    (''.join(f'<p class="hc-notice">{e(n)}</p>' for n in course['notes'])),'CENTER & SUBJECT')
    body += '<article class="hs-article" aria-label="'+e(title)+' 학습 안내">'
    body += section('study-focus',focus[0]['title'],f'<p>{e(focus[0]["explain"])}</p><div class="hs-practice"><h3>현재 교재로 해볼 점검</h3><p>{e(focus[0]["task"])}</p><p>{e(focus[0]["record"])}</p></div>'+f'<p class="hc-small">학생이 직접 해볼 수 있는 학습 방법입니다. 실제 수업 과정과 복습 주기는 {e(c["routeName"])} 상담에서 확인하세요.</p>','LEARNING CHECK')
    body += section('study-next',focus[1]['title'],f'<p>{e(focus[1]["explain"])}</p><p>{e(focus[1]["task"])}</p><p>{e(focus[1]["record"])}</p>','NEXT PRACTICE')
    body += section('subject-courses',c['routeName']+' '+subject+' 학년별 확인 사항',
                    f'<p class="hs-grade-summary"><strong>{e(subject)} 안내 학년</strong> {e(course["label"])}</p>'+''.join(f'<p class="hc-notice">{e(n)}</p>' for n in course['notes'])+
                    ('<div class="hc-grid">'+''.join('<section class="hc-card"><h3>'+e(' · '.join(grades))+'</h3><p><strong>'+e(label)+'</strong></p><p>'+e(msg)+'</p>'+('<p class="hc-small">상담 참고 학교: '+e(' · '.join(schools))+'</p>' if schools else '')+'</section>' for _,grades,label,msg,schools in stage)+'</div>' if stage else '<p>확인된 개설 학년을 임의로 표시하지 않았습니다. 학생의 학년과 희망 과목을 알려주고 수업 가능 범위를 확인하세요.</p>')+
                    '<p class="hc-small">학교 이름은 상담 자료를 준비할 때 참고하는 목록이며 제휴나 전용반을 뜻하지 않습니다. 현재 모집, 시간표와 최종 교육비는 지점에서 확인하세요.</p>','GRADES & SCHOOL MATERIALS')
    body += section('prepare-records','상담 후에도 활용할 학습 기록',
                    '<ol class="hc-steps"><li><strong>처음 풀었던 흔적</strong><p>답을 고치기 전의 문제와 풀이를 남겨 어디에서 멈췄는지 보여주세요.</p></li><li><strong>혼자 다시 확인한 내용</strong><p>'+e(focus[0]['record'])+'</p></li><li><strong>다음에 물어볼 질문</strong><p>'+e(focus[1]['question'])+' 질문과 가능한 등원 요일을 함께 정리하면 수업 조건을 구체적으로 의논하기 좋습니다.</p></li></ol>'+
                    buttons([('오답과 복습 기록 방법','/학습가이드/#wrong-answer'),('학습 진단에 준비할 자료','/진단상담/')]),'RECORD & FEEDBACK')
    body += '</article>'
    faqs = [(locality+' '+subject+'학원 안내에서 어떤 학년을 확인할 수 있나요?', grade_sentence+' '+(' '.join(course['notes'])+' ' if course['notes'] else '')+'현재 등록 가능한 요일과 시간표는 지점에 확인하세요.'),
            (focus[0]['question'],focus[0]['answer']),
            (subject+' 상담을 준비할 때 어떤 학교 자료가 필요한가요?', '현재 교재, 학교의 평가 안내가 있다면 해당 범위, 처음 틀린 답안과 질문을 준비하세요. '+(next(( ' · '.join(schools[:2])+' 등 ' for _,_,_,_,schools in stage if schools),''))+'학교명만으로 진도나 시험 난도를 단정하지 않고 학생이 실제로 공부한 자료를 기준으로 의논합니다.'),
            (c['routeName']+' 방문 위치는 어디인가요?',c['address']+'입니다. '+(c['locationGuide']+' ' if c['locationGuide'] else '')+'방문 전에 상담 시간과 건물 입실 방법을 확인하세요.')]
    body += base.faq(faqs)
    related = [('지점 주소·사진·전체 과목',parent),('다른 '+c['region']+' 지점',f'/지점안내/{c["region"]}/')]
    sibling = next(x for x in all_records if x['locality']==locality and x['subject']!=subject)
    related.append((sibling['title']+' 학습 안내',sibling['path']))
    others = [x for x in all_records if x['parentPath']==parent and x['subject']==subject and x['locality']!=locality]
    related += [(x['title'],x['path']) for x in others[:3]]
    body += section('related-pages','같은 지점의 학습 안내 이어보기',buttons(related),'RELATED GUIDES')
    body += subject_media(c,title)
    parent_doc = html.parse(str(file_for(parent)))
    _, parent_graph = graph_of(parent_doc)
    org = copy.deepcopy(next(n for n in parent_graph if n.get('@id')==url(parent)+'#center'))
    service = next((copy.deepcopy(n) for n in parent_graph if n.get('@id')==url(parent)+'#service-'+subject),None)
    extra = [org,*([service] if service else []),base.itemlist(path,'관련 지점과 과목 안내',related)]
    base.page(path,title+' | '+focus[0]['title'],description,body,
              [('지점안내','/지점안내/'),(c['region'],f'/지점안내/{c["region"]}/'),(c['routeName'],parent),(title,path)],
              c['primaryMedia']['representative']['src'],extra,article=True)
    doc = html.parse(str(file_for(path))).getroot(); _,graph = graph_of(doc)
    webpage = next(n for n in graph if n.get('@type')=='WebPage')
    article = next(n for n in graph if n.get('@type')=='Article')
    webpage['isPartOf'] = {'@id':url(parent)+'#webpage'}
    webpage['mainEntity'] = {'@id':url(path)+'#article'}
    webpage['about'] = [{'@id':org['@id']},{'@type':'Thing','name':subject+' 학습'}]
    if service: webpage['mentions'] = [{'@id':service['@id']}]
    article.update({'about':webpage['about'],'abstract':lead,
                    'isPartOf':{'@id':url(parent)+'#webpage'},
                    'mentions':[{'@type':'EducationalOrganization','name':s} for _,_,_,_,schools in stage for s in schools]})
    article['articleSection'] = [focus[0]['title'],focus[1]['title'],c['routeName']+' '+subject+' 학년별 확인 사항','상담 후에도 활용할 학습 기록']
    save_document(path,doc,graph)


def replace_section(doc, sid, markup, after=None, before=None):
    existing = doc.xpath('//*[@id=$sid]',sid=sid)
    node = html_fragment(markup)
    if existing: existing[0].getparent().replace(existing[0],node)
    elif after:
        anchor = doc.xpath('//*[@id=$sid]',sid=after)[0];anchor.addnext(node)
    elif before:
        anchor = doc.xpath('//*[@id=$sid]',sid=before)[0];anchor.addprevious(node)
    else:
        hero = doc.xpath('//main/section[contains(@class,"hc-hero")]')[0];hero.addnext(node)


def enrich_hubs(centers, records):
    by_path = {base.route(c):c for c in centers}
    hub_paths = ['/지점안내/']+[f'/지점안내/{r}/' for r in base.REGIONS if any(c['region']==r for c in centers)]+list(by_path)
    for path in hub_paths:
        doc = html.parse(str(file_for(path))).getroot(); _,graph = graph_of(doc)
        if path in by_path:
            c = by_path[path]; own = [r for r in records if r['parentPath']==path]
            grade_labels = [s['subject']+' '+s['label'] for s in c['courses'] if s['subject'] in ['영어','수학']]
            first = c['displayName']+'은 '+c['address']+'에 있습니다. 안내된 영어·수학 범위는 '+', '.join(grade_labels)+'입니다. '+(' · '.join(c['neighborhoods'])+'에서 상담을 준비한다면 ' if c['neighborhoods'] else '')+'과목별 조건과 아래 학습 방법을 함께 확인하세요.'
            doc.xpath('//p[@class="hc-lead"]')[0].text = first
            description = c['displayName']+'의 '+', '.join(grade_labels)+'. '+('동네별 영어·수학 학습 안내, ' if own else '')+'학교 자료, 실제 방문 주소와 학습 공간을 확인하세요.'
            checkpoint = []
            for subject in ['영어','수학']:
                course, stage = stage_rows(c,subject)
                school = next((schools[0] for _,_,_,_,schools in stage if schools),None)
                point = (f'{subject} 안내 학년은 {course["label"]}입니다. '+(school+' 등 재학 학교의 ' if school else '현재 공부 중인 ')+'교재에서 혼자 설명하기 어려운 부분을 표시하세요.' if course['grades'] else f'{subject}는 개설 범위와 실제 수업 장소부터 확인해야 합니다. 학생의 학년과 현재 공부한 내용을 알려주세요.')
                point += (' '.join(course['notes']))
                checkpoint.append((subject+' 상담에 준비할 내용',point))
            topics = [base.QUESTIONS[k] for k in c['managementTopics'] if k in base.QUESTIONS]
            checkpoint.append((topics[0][0],topics[0][1]) if topics else ('수업 후에 확인할 기록','진도 외에 질문했던 내용, 혼자 다시 푼 문제, 다음에 보완할 부분도 전달받을 수 있는지 확인하세요. 공유 방식과 주기는 지점 상담에서 의논합니다.'))
            replace_section(doc,'learning',section('learning',c['routeName']+'에서 학습 계획을 구체화하려면',
                            '<p>수업 과목을 정한 뒤에는 학생이 혼자 할 수 있는 범위와 설명이 필요한 부분을 나누어 보세요. 아래 항목은 상담할 때 준비하고 질문할 내용입니다.</p>'+cards(checkpoint)+
                            buttons([('진단부터 계획을 세우는 방법','/진단상담/'),('수업과 복습을 연결하는 흐름','/학습가이드/#management-flow')]),'PLAN YOUR LEARNING'))
            links = [(r['title'],r['path']) for r in sorted(own,key=lambda r:(r['locality'],r['subject']))]
            if links:
                text = '<p>지점의 주소와 수업 조건을 확인했다면 관심 있는 동네의 과목별 학습 방법을 살펴보세요. 영어와 수학을 따로 정리해 현재 학습에서 점검할 내용을 쉽게 고를 수 있습니다.</p>'
                replace_section(doc,'neighborhood-pages',section('neighborhood-pages','동네별 영어·수학 학습 안내',text+buttons(links),'NEIGHBORHOOD GUIDES'),after='faq')
                hero_links = doc.xpath('//section[contains(@class,"hc-hero")]//div[@class="hc-links"]')[0]
                if not hero_links.xpath('a[@href="#neighborhood-pages"]'):
                    hero_links.append(html_fragment('<a href="#neighborhood-pages">동네별 과목 안내 <span aria-hidden="true">↗</span></a>'))
            list_node = base.itemlist(path,'동네별 영어·수학 학습 안내',links) if links else None
            if list_node: list_node['@id'] = url(path)+'#neighborhood-list'
            for org in graph:
                if org.get('@id') == url(path)+'#center':
                    org['address']['addressLocality'] = c['district']
            about = {'@id':url(path)+'#center'}
            title = c['displayName']+' | 영어·수학 개설 학년과 '+('동네 안내' if own else '방문 정보')
        else:
            regional = centers if path=='/지점안내/' else [c for c in centers if c['region']==path.split('/')[2]]
            label = '전국' if path=='/지점안내/' else path.split('/')[2]
            first = f'{label}의 센터를 지점명·동네·학교로 찾을 수 있습니다. 각 지점에서 영어·수학의 개설 학년과 방문 주소를 확인하고, 동네별 과목 안내에서 공부 방법과 상담 준비를 이어서 살펴보세요.'
            doc.xpath('//p[@class="hc-lead"]')[0].text = first
            description = f'{label} 지점의 주소·영어·수학 개설 학년·주변 학교를 확인하세요. 동네와 학교 검색, 과목별 학습 안내, 학습 공간 사진으로 상담 준비를 돕습니다.'
            body = cards([('지점에서 조건 확인','영어와 수학은 같은 지점에서도 개설 학년이 다를 수 있습니다. 학생의 학년과 희망 요일을 준비하고 과목별 표를 먼저 확인하세요.'),
                          ('동네별 글에서 학습 점검','지점 페이지의 동네별 영어·수학 안내로 이동하면 교재에서 직접 확인할 문제와 복습 기록을 살펴볼 수 있습니다.'),
                          ('질문을 정리해 상담','틀린 답안, 학교 평가 안내와 가능한 등원 요일을 모아 주세요. 공부 방법에 대한 제안과 실제 시간표·교습비를 구분해 확인합니다.')])
            replace_section(doc,'subject-paths',section('subject-paths','지점 정보와 과목별 학습 방법을 함께 보세요',body+buttons([('학교·동네로 지점 찾기','#center-list'),('학습 진단 상담 준비','/진단상담/')]),'FIND A LEARNING PATH'))
            list_node = base.itemlist(path,label+' 지점 목록',[(c['displayName'],base.route(c)) for c in regional])
            list_node['@id'] = url(path)+'#center-list-items'
            about = {'@type':'Thing','name':label+' 지점별 학습 상담'}
            title = ('전국 지점안내' if path=='/지점안내/' else label+' 지점안내')+' | 영어·수학 학년과 동네별 학습 찾기'
        doc.find('head/title').text = title
        for key,value in [('description',description),('og:title',title),('twitter:title',title),('og:description',description),('twitter:description',description)]: set_meta(doc,key,value)
        graph = [n for n in graph if n.get('@id') not in [url(path)+'#neighborhood-list',url(path)+'#center-list-items',url(path)+'#hub-article']]
        if list_node: graph.append(list_node)
        web = next(n for n in graph if n.get('@id')==url(path)+'#webpage')
        web.update({'@type':'CollectionPage' if list_node else 'WebPage','name':title,'description':description,'abstract':first,
                    'dateModified':DAY,'about':about,'mainEntity':{'@id':list_node['@id']} if list_node else about})
        parent = '/' if path=='/지점안내/' else '/'.join(path.rstrip('/').split('/')[:-1])+'/'
        web['isPartOf'] = {'@id':url(parent)+'#webpage'}
        web['hasPart'] = [{'@type':'WebPageElement','@id':url(path)+'#'+s.get('id'),'name':norm(s.xpath('string(.//h2)'))}
                          for s in doc.xpath('//main/section[@id]') if s.xpath('.//h2')]
        if list_node: web['hasPart'] += [{'@id':item['url']+'#webpage'} for item in list_node['itemListElement']]
        graph.append({'@type':'Article','@id':url(path)+'#hub-article','headline':title,'abstract':first,
                      'description':description,'inLanguage':'ko-KR','dateModified':DAY,
                      'author':{'@id':base.DOMAIN+'/#organization'},'publisher':{'@id':base.DOMAIN+'/#organization'},
                      'mainEntityOfPage':{'@id':web['@id']},'about':about,
                      'image':doc.xpath('string(//meta[@property="og:image"]/@content)'),
                      'articleSection':[norm(s.xpath('string(.//h2)')) for s in doc.xpath('//main/section[@id="learning" or @id="neighborhood-pages" or @id="subject-paths" or @id="center-list"]')]})
        save_document(path,doc,graph)
    return hub_paths


def discovery(records, hub_paths, created_at):
    manifest = read_json(base.DATA/'release-pages.json')
    for path in [*hub_paths,*(r['path'] for r in records)]:
        doc = html.parse(str(file_for(path)))
        manifest[path] = {'title':doc.xpath('string(//title)'), 'description':doc.xpath('string(//meta[@name="description"]/@content)')}
    base.save(base.DATA/'release-pages.json',manifest)
    tree = etree.parse(str(ROOT/'sitemap.xml')); ns={'s':'http://www.sitemaps.org/schemas/sitemap/0.9'}; root=tree.getroot()
    indexed = {unquote(n.findtext('s:loc',namespaces=ns)):n for n in root}
    for path in [*hub_paths,*(r['path'] for r in records)]:
        u = url(path); node = indexed.get(unquote(u))
        if node is None:
            node=etree.SubElement(root,'{'+ns['s']+'}url');etree.SubElement(node,'{'+ns['s']+'}loc').text=u
        modified=node.find('s:lastmod',ns)
        if modified is None: modified=etree.SubElement(node,'{'+ns['s']+'}lastmod')
        modified.text=DAY
    base.write(ROOT/'sitemap.xml',etree.tostring(tree,encoding='unicode',pretty_print=True))
    # Keep 30 prior items and add 20 real new articles, balanced across regions.
    original = read_json(DATA/'baseline.json')['rss']
    rss=etree.fromstring(original.encode());channel=rss.find('channel');previous=list(channel.findall('item'))
    for item in previous:channel.remove(item)
    selected=[]
    regions=[region for region in base.REGIONS if any(r['region']==region for r in records)]
    for offset in range(2):
        for i,region in enumerate(regions):
            subject=['영어','수학'][(i+offset)%2]
            candidate=next(r for r in records if r['region']==region and r['subject']==subject)
            if len(selected)<20 and candidate not in selected:selected.append(candidate)
    pubdate=datetime.fromisoformat(created_at).strftime('%a, %d %b %Y %H:%M:%S GMT')
    for r in selected:
        item=etree.SubElement(channel,'item'); info=manifest[r['path']]
        for key,value in [('title',info['title']),('link',url(r['path'])),('guid',url(r['path'])),('description',info['description']),('pubDate',pubdate)]:
            etree.SubElement(item,key).text=value
        doc=html.parse(str(file_for(r['path'])))
        content=etree.SubElement(item,'{http://purl.org/rss/1.0/modules/content/}encoded')
        main=doc.xpath('//main')[0]
        for element in main.xpath('.//*[@href or @src or @srcset]'):
            for attribute in ['href','src']:
                if element.get(attribute):element.set(attribute,urljoin(url(r['path']),element.get(attribute)))
            if element.get('srcset'):
                element.set('srcset',', '.join(urljoin(url(r['path']),part.strip().split()[0])+' '+ ' '.join(part.strip().split()[1:]) for part in element.get('srcset').split(',')))
        content.text=etree.CDATA(html.tostring(main,encoding='unicode').replace('</source>',''))
    for old in previous[:30]:
        p=unquote(old.findtext('link','')).removeprefix(base.DOMAIN)
        if p in manifest:
            for field in ['title','description']:
                node=old.find(field)
                if node is not None:node.text=manifest[p][field]
        channel.append(old)
    build=channel.find('lastBuildDate')
    if build is not None:build.text=pubdate
    base.write(ROOT/'rss.xml',etree.tostring(rss,encoding='unicode',pretty_print=True))
    llms=ROOT/'llms.txt'; content=llms.read_text(encoding='utf-8')
    content=re.sub(r'\n## 지점별 영어·수학 학습 안내[\s\S]*','',content)
    content+='\n## 지점별 영어·수학 학습 안내\n\n- [지점과 동네별 과목 찾기]('+url('/지점안내/#subject-paths')+')\n- [학습 진단 상담 준비]('+url('/진단상담/')+')\n\n지점 주소 아래에 동네별 영어학원·수학학원 안내가 연결됩니다. 각 글은 학습 점검과 복습 방법을 설명하며 실제 개설 학년·수업 장소는 연결 지점의 과목별 조건을 따릅니다. 학교 목록은 상담 참고 정보이며 제휴나 전용반을 뜻하지 않습니다.\n'
    base.write(llms,content)
    base.save(DATA/'release-pages.json',{'modifiedAt':DAY,'hubs':hub_paths,'articles':[r['path'] for r in records],
                                       'rssNewItems':[r['path'] for r in selected]})


def update_from_manifest():
    centers=read_json(base.DATA/'centers.json')['centers']
    manifest=read_json(DATA/'manifest.json');records=manifest['records']
    lookup={base.route(c):c for c in centers}
    hubs=enrich_hubs(centers,records)
    for r in records:render_subject(lookup[r['parentPath']],r,records)
    discovery(records,hubs,manifest['createdAt'])
    if (ROOT/'tools/data/grade-pages/manifest.json').exists():
        from build_grade_pages import update_from_manifest as update_grades
        update_grades()
    print(base.j({'newSubjectPages':len(records),'enrichedHubs':len(hubs),'deploy':False}))


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--extract-only',action='store_true');args=parser.parse_args()
    capture_baseline()
    centers=read_json(base.DATA/'centers.json')['centers']
    extract(centers)
    if not args.extract_only:update_from_manifest()


if __name__=='__main__':main()
