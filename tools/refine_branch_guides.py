"""Evidence-bounded editorial pass; run after the branch/subject/grade generators.

Preserves every existing URL and visible body/map asset. Shared lessons live in
18 study guides. Branch children explain how to prepare for the actual center.
No random wording, fabricated student results, inferred courses or deploy calls.
"""
from __future__ import annotations
import copy
import json
import re
import subprocess
from collections import Counter
from datetime import datetime, timezone
from email.utils import format_datetime
from urllib.parse import unquote, urljoin, urlsplit
from lxml import html, etree
from PIL import Image
import build_grade_pages as grade

subject,base=grade.subject,grade.base
ROOT,DOMAIN,DAY=base.ROOT,base.DOMAIN,base.DAY
DATA=ROOT/'tools/data/branch-refinement'
POLICY='/안내-작성기준/'
e,url,section,buttons=base.e,base.url,base.section,base.buttons
READ=subject.read_json
DESCRIPTIONS=READ(ROOT/'seo-descriptions.json')['pages']
VERS='20260921-review'
COUNTS=Counter()


def guide_path(g,s): return '/학습가이드/'+g+'-'+s+'-공부법/'
def guide_title(g,s): return g+' '+s+' 공부법: '+grade.PROFILES[(g,s)]['title']
def state(c,r): return grade.status_for(c,r)
def stage(g): return {'초':'초등','중':'중등','고':'고등'}[g[0]]
def normalize(t): return ' '.join(t.split())
def physical_region(c):
    first=c['address'].split()[0]
    aliases={'서울특별시':'서울','부산광역시':'부산','대구광역시':'대구','인천광역시':'인천','광주광역시':'광주','대전광역시':'대전','울산광역시':'울산','세종특별자치시':'세종','경기도':'경기','강원특별자치도':'강원','강원도':'강원','충청북도':'충북','충청남도':'충남','전북특별자치도':'전북','전라북도':'전북','전라남도':'전남','경상북도':'경북','경상남도':'경남','제주특별자치도':'제주','제주시':'제주'}
    return first if first in base.REGIONS else aliases.get(first,c['region'])
def read_doc(path): return html.parse(str(subject.file_for(path))).getroot()
def set_section(doc,sid,markup,**where): subject.replace_section(doc,sid,markup,**where)


def supplement(c,r=None):
    # Verified against source workbook 센터정보!AE190, fixed source hash in
    # centers.json. This is a conditional inquiry, not an added confirmed course.
    if c['routeName']!='풍동점' or (r and r['grade']!='고2'):return ''
    return '풍동점의 과목별 학년 표에는 고1까지 기재되어 있고, 비고에는 고2(예비 고3)의 국어·영어·수학을 화상 수업과 병행하는 조건이 안내되어 있습니다. 대면 수업만으로 가능한지와 현재 적용 여부를 먼저 확인하세요.'


def school_view(center):
    """Exclude spreadsheet annotation fragments and speculative candidate matches.

    Keep the provided source manifest intact. Do not equate a candidate city with
    a verified target school. Review exclusions in the private report.
    """
    result={}; excluded=[]
    for level,values in center['schools'].items():
        keep=[]
        for name in values:
            if any(x in name for x in ['[',']','후보','확인',';','기타사립','특성화고','지역내 모든']):
                excluded.append(name); continue
            keep.append(name)
        # Only collapse an abbreviation into an already-present unambiguous name.
        suffix={'초등':'초등학교','중등':'중학교','고등':'고등학교'}[level]
        full=[s for s in keep if s.endswith(suffix)]
        cleaned=[]
        for name in keep:
            if name.endswith(suffix): new=name
            else:
                stem=re.sub(r'(초|중|고)$','',name)
                matches=[s for s in full if s.removesuffix(suffix).endswith(stem)]
                if len(matches)==1: new=matches[0]
                else: new=name
            if new not in cleaned: cleaned.append(new)
        result[level]=cleaned
    # These candidates occur only in annotation-bearing cells, but their short
    # form is independently present in the original center workbook. Keep them
    # as owner-provided references, not a new independently verified fact.
    owner_names={'상암점':{'중등':['덕은한강중학교']},
                 '풍동점':{'중등':['일산양일중학교']},
                 '센트럴점':{'고등':['강일고등학교']}}
    for level,names in owner_names.get(center['routeName'],{}).items():
        for name in names:
            if name not in result[level]:result[level].append(name)
    # Resolve short forms again after adding independently supported full names.
    for level,values in result.items():
        suffix={'초등':'초등학교','중등':'중학교','고등':'고등학교'}[level]
        full=[v for v in values if v.endswith(suffix)];unique=[]
        for value in values:
            stem=re.sub(r'(초|중|고)$','',value)
            matches=[v for v in full if v.removesuffix(suffix).endswith(stem)]
            resolved=matches[0] if not value.endswith(suffix) and len(matches)==1 else value
            if resolved not in unique:unique.append(resolved)
        result[level]=unique
    return result,excluded


def lead_for(c,r):
    p=grade.PROFILES[(r['grade'],r['subject'])]; st=state(c,r)
    scope={'confirmed':f'{c["routeName"]}의 안내 학년에 포함되며, 모집 시간은 별도 확인이 필요합니다.',
           'pending':f'{c["routeName"]}의 해당 수업은 개설 조건 확인이 필요합니다.',
           'unlisted':f'{c["routeName"]}의 개설 학년 목록에는 표시되지 않아 수업 가능 여부를 먼저 확인해야 합니다.'}[st]
    return f'{r["title"]}을 찾는다면 {p["summary"]}부터 점검해 보세요. '+scope


def grade_article(c,r):
    g,s,loc=r['grade'],r['subject'],r['locality']; p=grade.PROFILES[(g,s)]
    checks=grade.source_checks(r); course=grade.course_for(c,s); status=state(c,r)
    schools=c['schools'].get(stage(g),[]); target=guide_path(g,s)
    schooltext=' · '.join(schools)
    body='<article class="hs-article hg-article" aria-label="'+e(r['title'])+' 학습·상담 안내">'
    body+=section('grade-focus',p['title'],
        '<p>'+e(p['summary'])+'부터 확인합니다. 아래 기록을 준비한 뒤 '+e(c['routeName'])+'의 실제 수업 범위와 연결해 상담해 보세요.</p>'+
        '<div class="hr-local-context"><h3>'+e(loc)+'에서 '+e(c['routeName'])+'을 알아볼 때</h3>'+
        '<p>'+e(grade.availability(c,r))+'</p>'+
        '<dl class="hc-facts"><div><dt>실제 수업 장소</dt><dd>'+e(c['address'])+'</dd></div>'+
        '<div><dt>'+e(s)+' 안내 학년</dt><dd>'+e(course['label'])+'</dd></div></dl>'+
        '<p class="hc-small">'+e(loc)+'은 상담 참고 지역이며 별도 지점명은 아닙니다. 이동 시간과 등원 요일은 실제 주소를 기준으로 확인하세요.</p></div>'+
        buttons([('이 학년의 공부 순서·연습 해설',target)]),'GRADE LEARNING')
    body+=section('practice-example','상담 전에 확인할 첫 문제',
        '<div class="hg-example"><p>'+e(p['example'])+'</p><p>답을 보기 전의 생각을 남기고, 설명이 막힌 부분에 표시해 보세요. 아직 배우지 않은 내용이라면 현재 교재에서 같은 수준의 문제로 바꿉니다.</p>'+
        '<a class="hc-text-link" href="'+e(target+'#practice-example')+'">풀이와 확인 기준 보기 →</a></div>'+
        '<p class="hc-small">공부 방법을 설명하는 연습 예시이며 '+e(c['routeName'])+' 학생의 실제 성적·수업 사례가 아닙니다.</p>','BEFORE CONSULTATION')
    body+=section('focused-checks',g+' '+s+'에서 가져갈 두 가지 기록',
        '<div class="hg-checks">'+''.join('<section class="hs-practice"><h3>'+e(x['title'])+'</h3><p>'+e(x['record'])+'</p><p class="hc-small">'+e(p['materials'])+' 중 이 항목이 드러나는 자료를 골라 주세요.</p></section>' for x in checks)+'</div>','FOCUS & FEEDBACK')
    body+=section('grade-center',c['routeName']+' 상담 준비',
        '<p><strong>실제 학원: '+e(c['displayName'])+'</strong></p>'+
        ('<p>'+e(schooltext)+' 등의 재학 자료를 준비할 때도 학교명만으로 진도를 정하지 않습니다. 현재 단원·교재와 학생의 첫 답안을 함께 확인하세요.</p>' if schooltext else '<p>재학 학교와 현재 단원·교재를 알려 주세요. 확인되지 않은 학교별 전용반이나 평가 방식은 안내하지 않습니다.</p>')+
        '<ol class="hc-steps"><li><strong>현재 범위</strong><p>'+e(p['materials'])+'</p></li>'+
        '<li><strong>우선 질문</strong><p>'+e(checks[0]['question'])+' 처음 쓴 답과 고친 답을 함께 준비합니다.</p></li>'+
        '<li><strong>등원 조건</strong><p>'+e(c.get('openingReference') or '상담 가능 시간은 지점에 문의해 주세요.')+'. '+e(c['weekend'])+'</p></li></ol>'+
        ''.join('<p class="hc-notice">'+e(n)+'</p>' for n in course['notes'])+
        ('<p class="hc-notice">'+e(supplement(c,r))+'</p>' if supplement(c,r) else '')+
        '<p class="hc-small">학교 목록은 상담 참고 정보이며 제휴·전용반·통학 지원을 뜻하지 않습니다. 운영 참고 시간도 현재 모집 시간표와 다를 수 있습니다.</p>'+
        buttons([('지점 전체 정보와 학습 공간',r['branchPath'])]),'LOCAL CONSULTATION')
    body+=section('review-plan','상담 후에는 무엇을 다시 확인하나요?',
        '<p>'+e(p['review'])+'</p><p>상담에서 정한 범위와 실제로 혼자 해낸 범위를 나누어 남기세요. 다음 상담에서는 새 교재를 추가하기 전에 남은 질문부터 확인합니다.</p>'+
        buttons([('공부법과 다음 단계 확인',target+'#review-plan'),('상담 질문 정리','/진단상담/')]),'REVIEW CHECK')
    return body+'</article>'


def review_block(c=None):
    text='작성·편집: 학습코칭.kr. 공부 방법은 학습 안내로, 지점 정보는 제공된 센터 자료를 기준으로 구분해 정리했습니다.'
    if c: text+=' 개설 학년 자료와 현재 모집 여부는 다를 수 있습니다.'
    return '<aside class="hr-editorial hc-wrap" id="editorial-note"><p>'+text+'</p><a href="'+POLICY+'">자료 출처와 안내 작성 기준</a></aside>'


def common_guides():
    paths=[]
    for g in grade.GRADES:
        for s in ['영어','수학']:
            p=grade.PROFILES[(g,s)]; path=guide_path(g,s);title=guide_title(g,s)
            desc=f'{g} {s} 학습에서 {p["title"]}. 짧은 연습 문제와 풀이, 복습 기록과 상담 준비 방법을 안내합니다.'
            assert len(desc)<=80,(path,len(desc))
            body=base.hero('STUDY GUIDE · '+grade.grade_name(g),e(title),p['explanation'],[('공부 순서','#learning-steps'),('문제와 해설','#practice-example'),('복습 기준','#review-plan')])
            body+=section('learning-steps','어디서부터 확인하면 좋을까요?',
                '<ol class="hc-steps">'+''.join('<li><strong>'+e(a)+'</strong><p>'+e(b)+'</p></li>' for a,b in p['steps'])+'</ol>','LEARNING STEPS')
            body+=section('practice-example','짧은 연습과 해설',
                '<div class="hg-example"><h3>먼저 풀어 보기</h3><p>'+e(p['example'])+'</p><h3>확인할 내용</h3><p>'+e(p['answer'])+'</p></div>'+
                '<p>이 문제는 공부 방법을 이해하기 위한 예시입니다. 실제 학생의 성적 사례나 지점의 수업 실적이 아니며, 현재 학교·교재에서 배운 범위에 맞춰 활용하세요.</p>','PRACTICE & EXPLANATION')
            body+=section('review-plan','복습 기록을 다음 연습에 연결하기','<p>'+e(p['review'])+'</p><p>'+e(p['next_step'])+'</p><ol class="hc-steps"><li>도움 없이 쓴 첫 답과 그때의 판단을 남깁니다.</li><li>수정한 부분과 바꾼 이유를 적습니다.</li><li>답을 가리고 다시 확인한 결과를 비교합니다.</li></ol>'+buttons([('오답 기록을 정리하는 방법','/학습가이드/#wrong-answer')]),'REVIEW')
            body+=section('prepare','학원 상담에서는 이 자료를 준비하세요','<p>'+e(p['materials'])+'를 준비하세요. 학년 이름만으로 진도와 교재를 정하지 말고 실제 학습 자료와 개설 조건을 함께 확인합니다.</p><p>공통 공부법 안내가 모든 지점의 해당 학년 수업 개설을 의미하지는 않습니다.</p>'+buttons([('지역·지점별 개설 조건 보기','/지점안내/'),('진단상담 준비','/진단상담/')]),'NEXT STEP')
            body+=base.faq([(p['question'],p['explanation']),('이 공부법이 지점의 실제 수업 과정인가요?','이 글은 스스로 해볼 학습 방법을 정리한 안내입니다. 지점별 지도 과목, 개설 학년과 모집 조건은 지점안내에서 확인하고 상담 시 현재 조건을 다시 확인하세요.')])
            links=[('전체 학년별 공부법','/학습가이드/#grade-study-guides'),(g+' '+('수학' if s=='영어' else '영어')+' 공부법',guide_path(g,'수학' if s=='영어' else '영어'))]
            body+=section('related-pages','함께 읽을 안내',buttons(links),'RELATED GUIDES')
            base.page(path,title,desc,body,[('학습가이드','/학습가이드/'),(g+' '+s+' 공부법',path)],'/assets/coaching-program/brand-learning.webp',[base.itemlist(path,'함께 읽을 안내',links)],article=True)
            paths.append(path)
    # Publication responsibility is the existing site organization, not an
    # invented teacher, expert reviewer or branch operator.
    body=base.hero('EDITORIAL POLICY','자료 출처와 안내 작성 기준','학습코칭.kr은 공부 방법과 지점별 상담 정보를 구분해 제공합니다. 확인된 사실과 학습 제안, 연습 예시가 섞이지 않도록 안내합니다.')
    body+=section('responsibility','작성·편집 주체','<p>이 사이트의 콘텐츠 작성·편집 표기는 학습코칭.kr입니다. 지점 소개는 운영자가 제공한 센터 자료와 학교 목록, 사진 자료를 바탕으로 정리합니다. 특정 교사나 의료·심리 전문가가 검토했다고 표시하지 않으며, 학교명만으로 학교와의 제휴를 주장하지 않습니다.</p>')
    body+=section('sources','정보 종류별 확인 기준','<dl class="hc-facts"><div><dt>지점 정보</dt><dd>제공된 센터 자료의 등록명·주소·과목별 학년과 별도 조건을 함께 확인합니다. 학교 목록은 상담에 참고하는 정보입니다.</dd></div><div><dt>공통 프로그램</dt><dd>와와 공식 사이트의 브랜드·코칭·AI 프로그램 안내를 참고합니다. 공통 프로그램의 대상과 개별 지점의 도입 여부는 다를 수 있습니다.</dd></div><div><dt>공부법과 예시</dt><dd>학생이 직접 해볼 점검 방법으로 제안합니다. 연습 문제를 실제 학생 사례·성적 향상 실적으로 표시하지 않습니다.</dd></div><div><dt>사진</dt><dd>지점 사진과 학습 안내용 이미지를 구분하여 사용합니다. 과거에 촬영된 사진은 현재 시설 상태와 다를 수 있습니다.</dd></div></dl>'+buttons([('와와 공식 브랜드 안내','https://www.wawacenter.com/brand/wawacenter'),('공식 코칭 시스템','https://www.wawacenter.com/intro/coachingSystem'),('공식 AI 프로그램','https://www.wawacenter.com/intro/AISystem')]))
    body+=section('course-status','개설 학년과 현재 모집은 다릅니다','<p>과목별 학년 표에 포함된 경우에도 시간표·교재·선택 과목·신규 등록 조건은 별도 확인이 필요합니다. 목록에 없거나 비고와 상충하면 개설을 확정하지 않습니다. 빈칸을 수업 불가로 단정하지도 않습니다.</p><p>직통번호·운영시간·지도 좌표·학생 사례는 확인 자료가 있을 때만 구체적으로 안내합니다.</p>')
    body+=section('updates','수정일과 정정 요청','<p>본문의 안내 검토일과 구조화 데이터, 사이트맵의 변경일을 맞춥니다. 단순 재배포만으로 날짜를 새로 바꾸지 않습니다. 게시일은 생성·공개 기록을 확인할 수 있는 경우에만 표시합니다.</p><p>주소·학교·개설 조건에서 다른 내용을 발견했다면 해당 지점명과 수정할 항목을 함께 알려 주세요.</p>'+buttons([('정보 확인·정정 문의','/상담문의/'),('전국 지점 찾기','/지점안내/')]))
    base.page(POLICY,'자료 출처와 안내 작성 기준 | 학습코칭.kr','학습코칭.kr의 지점 정보 출처, 개설 학년 확인 기준, 학습 예시와 실제 사례의 구분 및 정정 방법을 안내합니다.',body,[('안내 작성 기준',POLICY)],article=True)
    return paths+[POLICY]


def improve_grade(doc,graph,c,r):
    path=r['path']; g,s=r['grade'],r['subject'];p=grade.PROFILES[(g,s)]
    for old in doc.xpath('//main/section[@id="grade-center"]'):
        old.getparent().remove(old)
    article=doc.xpath('//article[contains(@class,"hg-article")]')[0]
    article.getparent().replace(article,subject.html_fragment(grade_article(c,r)))
    lead=doc.xpath('//p[@class="hc-lead"]')[0];lead.text=lead_for(c,r)
    faqs=[(c['routeName']+'의 '+g+' '+s+' 수업을 신청할 수 있나요?',normalize(grade.availability(c,r)+' '+' '.join(grade.course_for(c,s)['notes'])+' '+supplement(c,r))),
          (r['locality']+'에서는 어디로 방문하나요?',c['address']+'의 '+c['displayName']+'으로 안내합니다. '+(c['locationGuide']+' ' if c['locationGuide'] else '')+'이동 경로와 상담 시간은 방문 전에 확인하세요.'),
          (g+' '+s+' 상담에 무엇을 가져가면 좋나요?',p['materials']+'를 준비하세요. '+grade.source_checks(r)[0]['record']),
          ('이 페이지의 연습이 실제 학생 사례인가요?','학습 방법을 설명하는 예시입니다. 실제 학생의 성적·수업 결과가 아니며, 자세한 해설은 연결된 '+g+' '+s+' 공부법에서 확인할 수 있습니다.')]
    set_section(doc,'faq',base.faq(faqs))
    for n in graph:
        if n.get('@type')=='Article':
            n['abstract']=lead.text
            n['mentions']=[{'@type':'EducationalOrganization','name':x} for x in c['schools'].get(stage(g),[])]
            n['citation']=[url(r['branchPath']),url(guide_path(g,s))]
    COUNTS['gradePages']+=1


def apply_schools(doc,graph,c,oldc):
    if c['schools']==oldc['schools']:return
    # Fix source artifacts everywhere they were interpolated, without rewriting
    # unrelated paragraphs or copying raw workbook instructions into the site.
    for level,olds in oldc['schools'].items():
        old=' · '.join(olds);new=' · '.join(c['schools'][level])
        for n in doc.xpath('//main//*[text()]'):
            if n.text and old:n.text=n.text.replace(old,new)
            if n.tail and old:n.tail=n.tail.replace(old,new)
    for n in doc.xpath('//*[@id="schools"]//article'):
        heading=normalize(n.xpath('string(h3)'));level={'초등학교':'초등','중학교':'중등','고등학교':'고등'}.get(heading)
        if level and n.xpath('.//ul'):
            ul=n.xpath('.//ul')[0];ul.clear();ul.set('class','hc-school-list')
            for school in c['schools'][level]:etree.SubElement(ul,'li').text=school
    # Some summaries used only the first one or two schools, so replacing the
    # complete joined list alone does not remove truncated workbook notes.
    for card in doc.xpath('//*[@id="learning"]//article'):
        heading=normalize(card.xpath('string(h3)'))
        s=next((s for s in ['영어','수학'] if heading==s+' 상담에 준비할 내용'),None)
        if not s:continue
        course,rows=subject.stage_rows(c,s)
        first=next((schools[0] for *_,schools in rows if schools),None)
        text=(f'{s} 안내 학년은 {course["label"]}입니다. '+(first+' 등 재학 학교의 ' if first else '현재 공부 중인 ')+'교재에서 혼자 설명하기 어려운 부분을 표시하세요.' if course['grades'] else f'{s}는 개설 범위와 실제 수업 장소부터 확인해야 합니다. 학생의 학년과 현재 공부한 내용을 알려주세요.')
        paragraphs=card.xpath('p')
        if paragraphs:paragraphs[0].text=text+' '.join(course['notes'])
    for detail in doc.xpath('//details[@class="hc-faq"]'):
        question=normalize(detail.xpath('string(summary)'))
        s=next((s for s in ['영어','수학'] if question==s+' 상담을 준비할 때 어떤 학교 자료가 필요한가요?'),None)
        if s:
            _,rows=subject.stage_rows(c,s)
            example=next((' · '.join(schools[:2])+' 등 ' for *_,schools in rows if schools),'')
            detail.find('p').text='현재 교재, 학교의 평가 안내가 있다면 해당 범위, 처음 틀린 답안과 질문을 준비하세요. '+example+'학교명만으로 진도나 시험 난도를 단정하지 않고 학생이 실제로 공부한 자료를 기준으로 의논합니다.'
    for n in graph:
        if n.get('@type')=='Article' and n.get('mentions'):
            if all(x.get('@type')=='EducationalOrganization' for x in n['mentions']):
                if len(urlsplit(n['@id']).path.strip('/').split('/'))==4:
                    n['mentions']=[{'@type':'EducationalOrganization','name':x} for values in c['schools'].values() for x in values]


def search_keywords(doc,centers):
    for card in doc.xpath('//*[@data-center-keywords]'):
        href=card.xpath('string(.//h3/a/@href)')
        c=centers.get(unquote(href))
        assert c,'Unknown center in search directory: '+href
        card.set('data-center-keywords',' '.join([c['displayName'],c['region'],c['district'],c['address'],*c['neighborhoods'],*(s for values in c['schools'].values() for s in values)]))


def photo(c):
    if c and c['photoMode']=='center' and c['photos']:
        return c['photos'][0],c['displayName']+' 제공 지점 사진','center'
    return '/assets/coaching-program/brand-learning.webp','영어·수학 교재와 학습 도구를 표현한 학습 안내 일러스트','learning-illustration'


def finish(path,doc,graph,c,publication):
    # Apply the reviewed short description before schema/RSS generation too.
    # Regeneration must not leave feeds advertising a superseded description.
    description=doc.xpath('string(//meta[@name="description"]/@content)')
    entry=DESCRIPTIONS.get(path.rstrip('/') or '/')
    if entry:
        assert description==entry['description'] or description in entry['sources'], 'Review changed description: '+path
        description=entry['description']
    assert 0<len(description)<=80,(path,len(description))
    for key in ['description','og:description','twitter:description']:subject.set_meta(doc,key,description)
    image,alt,mode=photo(c);imagefile=ROOT/image.lstrip('/')
    with Image.open(imagefile) as im:w,h=im.size;mime=Image.MIME[im.format]
    for key,val in [('og:image',url(image)),('twitter:image',url(image)),('og:image:alt',alt),('twitter:image:alt',alt),('og:image:width',str(w)),('og:image:height',str(h)),('og:image:type',mime)]:subject.set_meta(doc,key,val)
    img={'@type':'ImageObject','url':url(image),'width':w,'height':h,'caption':alt}
    for n in graph:
        typ=n.get('@type');ident=n.get('@id','')
        if c and ident==url(base.route(c))+'#center' and n.get('address'):
            # The preserved navigation region is not necessarily the physical
            # address (e.g. the existing Seoul route for Wirye in Seongnam).
            n['address']['addressRegion']=physical_region(c)
        if ident==DOMAIN+'/#organization':
            n['publishingPrinciples']=url(POLICY);n['url']=DOMAIN+'/'
        if typ in ['WebPage','CollectionPage','Article'] and ident.startswith(url(path)+'#'):
            n['description']=description
            if not n.get('datePublished'):n['datePublished']=publication
            if typ=='Article':
                n['image']=img;n['abstract']=doc.xpath('string(//p[@class="hc-lead"])')
                n['articleSection']=[normalize(x.text_content()) for x in doc.xpath('//main//h2')]
            else:n['primaryImageOfPage']=img
        if typ=='BreadcrumbList':n['itemListElement'][0]['name']='학습코칭'
        if typ=='FAQPage':
            n['mainEntity']=[{'@type':'Question','name':normalize(x.xpath('string(summary)')),'acceptedAnswer':{'@type':'Answer','text':normalize(' '.join(p.text_content() for p in x.findall('p')))}} for x in doc.xpath('//details[@class="hc-faq"]')]
    crumb=doc.xpath('//nav[contains(@class,"hc-breadcrumb")]/a[1]')
    if crumb:crumb[0].text='학습코칭'
    note=doc.xpath('//*[@id="editorial-note"]')
    if note:note[0].getparent().remove(note[0])
    anchor=doc.xpath('//p[contains(@class,"hc-updated")]')[0];anchor.addprevious(subject.html_fragment(review_block(c)))
    footer=doc.xpath('//footer//nav')
    if footer:
        policies=[a for a in footer[0].xpath('a[@href]') if unquote(a.get('href'))==POLICY]
        for duplicate in policies[1:]:footer[0].remove(duplicate)
        if not policies:etree.SubElement(footer[0],'a',href=POLICY).text='안내 작성 기준'
    if not doc.xpath('//link[contains(@href,"branch-refinement.css")]'):
        etree.SubElement(doc.find('head'),'link',rel='stylesheet',href='/assets/branch-refinement.css?v='+VERS)
    if path in NEW_PATHS and path!=POLICY and not doc.xpath('//link[contains(@href,"branch-grades.css")]'):
        etree.SubElement(doc.find('head'),'link',rel='stylesheet',href='/assets/branch-grades.css?v=20260921')
    subject.save_document(path,doc,graph)
    COUNTS['socialImage:'+mode]+=1


def publication_dates(paths):
    # Record additions, not a guessed registration date or a redeploy timestamp.
    mapping={};commit=''
    raw=subprocess.check_output(['git','-c','core.quotepath=false','log','--reverse','--diff-filter=A','--format=COMMIT:%H:%aI','--name-only','--','지점안내'],cwd=ROOT).decode('utf-8')
    evidence=[]
    for line in raw.splitlines():
        if line.startswith('COMMIT:'):
            _,commit,when=line.split(':',2);date=when[:10];evidence.append({'commit':commit,'date':when})
        elif line.endswith('/index.html'):
            mapping['/'+line.removesuffix('index.html')]=date
    assert set(paths).issubset(mapping),set(paths)-set(mapping)
    base.save(DATA/'publication-evidence.json',{'commits':evidence,'pageDates':mapping,'newGuideDate':DAY})
    return mapping


def feeds(newpaths):
    sm=etree.parse(str(ROOT/'sitemap.xml'));root=sm.getroot();ns='http://www.sitemaps.org/schemas/sitemap/0.9'
    urls={unquote(n.findtext('{*}loc')) for n in root}
    for path in newpaths:
        if unquote(url(path)) in urls:continue
        n=etree.SubElement(root,'{'+ns+'}url');etree.SubElement(n,'{'+ns+'}loc').text=url(path);etree.SubElement(n,'{'+ns+'}lastmod').text=DAY
    base.write(ROOT/'sitemap.xml',etree.tostring(sm,encoding='unicode',pretty_print=True))
    rss=etree.parse(str(ROOT/'rss.xml'));channel=rss.find('channel')
    guide_release=DATA/'guide-publication.json'
    if guide_release.exists():created=READ(guide_release)['createdAt']
    else:
        created=datetime.now(timezone.utc).isoformat();base.save(guide_release,{'createdAt':created,'paths':[p for p in newpaths if p!=POLICY]})
    pubdate=format_datetime(datetime.fromisoformat(created),usegmt=True)
    for item in list(channel.findall('item')):
        if unquote(urlsplit(item.findtext('link')).path) in newpaths:channel.remove(item)
    # Newly authored study guides belong in the latest-content feed. Preserve
    # original pubDate on older entries and keep a bounded feed of 50 items.
    first=next(iter(channel.findall('item')),None)
    index=channel.index(first) if first is not None else len(channel)
    for path in [p for p in newpaths if p!=POLICY]:
        d=read_doc(path);item=etree.Element('item')
        for key,value in [('title',d.xpath('string(//title)')),('link',url(path)),('guid',url(path)),('description',d.xpath('string(//meta[@name="description"]/@content)')),('pubDate',pubdate)]:etree.SubElement(item,key).text=value
        etree.SubElement(item,'{http://purl.org/rss/1.0/modules/content/}encoded')
        channel.insert(index,item);index+=1
    for item in channel.findall('item')[50:]:channel.remove(item)
    build=channel.find('lastBuildDate')
    if build is not None:build.text=pubdate
    # Keep genuine publication dates and existing feed entries; refresh their
    # current text rather than arbitrarily re-dating all 12k URLs.
    for item in channel.findall('item'):
        path=unquote(urlsplit(item.findtext('link')).path);file=subject.file_for(path)
        if not file.exists():continue
        doc=read_doc(path);item.find('description').text=doc.xpath('string(//meta[@name="description"]/@content)')
        full=item.find('{http://purl.org/rss/1.0/modules/content/}encoded')
        if full is None:continue
        main=doc.xpath('//main')[0]
        for el in main.xpath('.//*[@href or @src or @srcset]'):
            for attr in ['href','src']:
                if el.get(attr):el.set(attr,urljoin(url(path),el.get(attr)))
            if el.get('srcset'):el.set('srcset',', '.join(urljoin(url(path),v.strip().split()[0])+' '+' '.join(v.strip().split()[1:]) for v in el.get('srcset').split(',')))
        full.text=etree.CDATA(html.tostring(main,encoding='unicode').replace('</source>',''))
    base.write(ROOT/'rss.xml',etree.tostring(rss,encoding='unicode',pretty_print=True))
    llms=ROOT/'llms.txt';text=llms.read_text(encoding='utf-8').split('\n## 학년별 공부법과 작성 기준')[0]
    text+='\n## 학년별 공부법과 작성 기준\n\n공통 공부 원리와 연습 해설은 학년별 공부법에서, 실제 수업 조건과 상담 준비는 지점 하위 페이지에서 확인합니다. 공부법 예시는 지점의 실제 학생 사례가 아닙니다.\n\n'
    for path in newpaths:text+='- ['+('안내 작성 기준' if path==POLICY else path.split('/')[-2])+']('+url(path)+')\n'
    base.write(llms,text)


def main():
    global NEW_PATHS
    COUNTS.clear()
    raw=READ(base.DATA/'centers.json');centers=copy.deepcopy(raw['centers']);old={base.route(c):c for c in raw['centers']}
    previous_file=DATA/'school-display-review.json'
    previous={v['branch']:v['after'] for v in READ(previous_file)} if previous_file.exists() else {}
    for src in raw['sources']:assert base.sha(base.SOURCE/src['file'])==src['sha256'],'Source changed; review it before regenerating'
    school_changes=[]
    for c in centers:
        schools,excluded=school_view(c)
        if schools!=c['schools']:school_changes.append({'branch':c['routeName'],'before':c['schools'],'after':schools,'excludedOrConsolidated':excluded})
        c['schools']=schools
    base.save(DATA/'school-display-review.json',school_changes)
    by_center={base.route(c):c for c in centers}
    records=READ(grade.DATA/'manifest.json')['records'];by_grade={r['path']:r for r in records}
    existing=['/'+p.parent.relative_to(ROOT).as_posix()+'/' for p in (ROOT/'지점안내').rglob('index.html')]
    published=publication_dates(existing)
    NEW_PATHS=common_guides()
    directory=read_doc('/학습가이드/');_,graph=subject.graph_of(directory)
    links=[(g+' '+s+' 공부법',guide_path(g,s)) for g in grade.GRADES for s in ['영어','수학']]
    set_section(directory,'grade-study-guides',section('grade-study-guides','학년별로 공부 방법을 골라 보세요','<p>학년별 점검 순서와 연습 해설을 모았습니다. 실제 수업 개설 여부는 지점안내에서 따로 확인합니다.</p>'+buttons(links),'STUDY BY GRADE'),before='faq' if directory.xpath('//*[@id="faq"]') else None)
    graph=[n for n in graph if n.get('@id')!=url('/학습가이드/')+'#grade-study-list'];node=base.itemlist('/학습가이드/','학년별 공부법',links);node['@id']=url('/학습가이드/')+'#grade-study-list';graph.append(node)
    subject.save_document('/학습가이드/',directory,graph)
    for i,path in enumerate(existing+NEW_PATHS+['/학습가이드/'],1):
        doc=read_doc(path);_,graph=subject.graph_of(doc)
        parts=path.strip('/').split('/');cp='/'+ '/'.join(parts[:3])+'/' if len(parts)>=3 else ''
        c=by_center.get(cp)
        if c:
            if c['routeName'] in previous:
                previous_center=dict(old[cp],schools=previous[c['routeName']])
                apply_schools(doc,graph,c,previous_center)
            apply_schools(doc,graph,c,old[cp])
            if c['schools']!=old[cp]['schools']:COUNTS['schoolPages']+=1
        search_keywords(doc,by_center)
        if path in by_grade:improve_grade(doc,graph,c,by_grade[path])
        if c and len(parts)==3:
            # Make the branch's distinct requirements easier to scan, without
            # inventing service outcomes or copying common lesson paragraphs.
            checklist=[('확인할 과목·학년',' / '.join(v['subject']+' '+v['label'] for v in c['courses'] if v['grades']) or '개설 범위 먼저 문의'),('방문 위치',c['address']),('시간 상담',c.get('openingReference') or '방문 전 조율')]
            markup='<dl class="hc-facts">'+''.join('<div><dt>'+e(a)+'</dt><dd>'+e(b)+'</dd></div>' for a,b in checklist)+'</dl><p>'+e(c['weekend'])+'</p>'+''.join('<p class="hc-notice">'+e(n)+'</p>' for n in c['courseNotes'])+('<p class="hc-notice">'+e(supplement(c))+'</p>' if supplement(c) else '')+buttons([('지점별 개설 조건','#courses'),('방문 주소와 동선','#location')])
            set_section(doc,'visit-checklist',section('visit-checklist',c['routeName']+' 상담 전 확인할 세 가지',markup,'BEFORE YOUR VISIT'),after='center-info')
        finish(path,doc,graph,c,published.get(path,DAY))
        if i%1000==0:print(base.j({'refined':i}),flush=True)
    # The prior description work is deliberately retained, and all descriptions
    # are brought into sync with the graph by the build-time consistency step.
    feeds(NEW_PATHS)
    base.save(DATA/'release.json',{'date':DAY,'paths':existing+NEW_PATHS+['/학습가이드/'],'newPaths':NEW_PATHS,'counts':COUNTS,'schoolCentersReviewed':len(school_changes),'availability':dict(Counter(state(by_center[r['branchPath']],r) for r in records)),'sourceHashesUnchanged':True})
    print(base.j({'counts':COUNTS,'newGuides':18,'newPolicy':1,'existingURLsPreserved':len(existing),'deploy':False}))


if __name__=='__main__':main()
