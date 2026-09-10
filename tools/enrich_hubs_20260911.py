"""2026-09-11: enrich only the 11 reviewed hub pages from original snapshots.

Do not use old snapshots after another editing session. This release never runs
the legacy nationwide/subject generators or rewrites existing locality pages.
"""
from pathlib import Path
from html import escape
from urllib.parse import quote, urlparse, unquote
import argparse
import json
import re
import zipfile

ROOT = Path(__file__).resolve().parents[1]
BASE = 'https://xn--ru4bi8s1tac0p.kr'
DATE = '2026-09-11'
LD = re.compile(r'(<script[^>]*type="application/ld\+json"[^>]*>)(.*?)(</script>)',re.S)

def array(value):
    return value if isinstance(value,list) else ([value] if value else [])

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--research',type=Path,required=True); args=ap.parse_args()
    content={}
    for name in ['subjects-copy.json','stages-copy.json']:
        data=json.loads((args.research/name).read_text('utf-8-sig'))
        assert not content.keys() & data.keys(); content.update(data)
    assert len(content)==11
    Path(__file__).with_name('hub-content-20260911.json').write_text(json.dumps(content,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')
    centers=[]
    for branch in ['명일점','송촌점','수완점']:
        path='/과목별학원/와와학습코칭센터/'+branch+'/'
        source=(ROOT/path.strip('/')/'index.html').read_text('utf-8-sig')
        graph=json.loads(LD.search(source).group(2))['@graph']
        node=next(n for n in graph if 'EducationalOrganization' in array(n.get('@type')))
        # Retain the existing real-center identity, without adding operating claims.
        centers.append({'node':{k:node[k] for k in ['@type','@id','name','url','address','identifier']},'href':path,'branch':branch})
    with zipfile.ZipFile(args.research/'baseline-snapshots.zip') as archive:
        for route,item in content.items():
            rel=route.strip('/')+'/index.html'
            original=archive.read(rel).decode('utf-8-sig').replace('\r\n','\n')
            current=(ROOT/rel).read_text('utf-8-sig')
            assert current==original or 'hakseup-hub-content:start' in current, 'Unreviewed source change: '+rel
            assert 'hakseup-hub-content:start' not in original
            match=LD.search(original); doc=json.loads(match.group(2)); graph=doc['@graph']
            page=next(n for n in graph if n.get('@type')=='CollectionPage'); url=page['url']
            listing=next(n for n in graph if n.get('@type')=='ItemList')
            if not page.get('mainEntity'):page['mainEntity']={'@id':listing['@id']}
            faq=next((n for n in graph if n.get('@type')=='FAQPage'),None)
            if not faq:
                faq={'@type':'FAQPage','@id':url+'#faq','mainEntity':[]};graph.append(faq)
            faq['mainEntity']=array(faq['mainEntity'])+[{'@type':'Question','name':q['question'],'acceptedAnswer':{'@type':'Answer','text':q['answer']}} for q in item['faqs']]
            parts=[]; lessons=[]
            for i,s in enumerate(item['sections']):
                sid=url+'#'+s['id']; parts.append({'@id':sid})
                graph.append({'@type':'WebPageElement','@id':sid,'url':sid,'name':s['title'],'text':'\n\n'.join(s['paragraphs']),'isPartOf':{'@id':page['@id']}})
                lessons.append('<section class="hk-lesson" id="'+s['id']+'"><span class="hk-number" aria-hidden="true">'+f'{i+1:02}'+'</span><div class="hk-lesson-copy"><h3>'+escape(s['title'])+'</h3>'+''.join('<p>'+escape(p)+'</p>' for p in s['paragraphs'])+'</div></section>')
            cards=[]; mentions=[]
            for c in centers:
                n=c['node'];graph.append(n);mentions.append({'@id':n['@id']})
                region=n['address']['addressRegion']+' '+n['address']['addressLocality']
                cards.append('<article class="hk-center"><p class="hk-region">'+escape(region)+'</p><h3>'+escape(n['name'])+'</h3><p>'+escape(n['address']['streetAddress'])+'</p><p class="hk-registration">'+escape(n['identifier'])+'</p><a href="'+quote(c['href'])+'">'+c['branch']+' 상세 안내</a></article>')
            page['hasPart']=array(page.get('hasPart'))+parts
            if {'@id':faq['@id']} not in page['hasPart']:page['hasPart'].append({'@id':faq['@id']})
            page['mentions']=array(page.get('mentions'))+mentions
            page['dateModified']=DATE
            qhtml=''.join('<details><summary>'+escape(q['question'])+'</summary><p>'+escape(q['answer'])+'</p></details>' for q in item['faqs'])
            photos=''.join(f'<figure><img src="/assets/hub-classroom-{i}.webp" width="{w}" height="{h}" loading="lazy" decoding="async" alt="{escape(item["label"])} 학습 공간 예시 {i}"><figcaption>{caption}</figcaption></figure>' for i,w,h,caption in [(1,500,300,'개별 학습 좌석과 책상 배치 예시'),(2,800,600,'교실 안 학습 공간 구성 예시')])
            reads=''.join('<a href="'+quote(x['href'],safe='/#')+'">'+escape(x['label'])+'</a>' for x in item['readLinks'])
            addition=f'''\n<!-- hakseup-hub-content:start 2026-09-11 -->
<div class="hk-content">
 <div class="hk-intro" id="hub-learning"><p class="hk-kicker">학습 선택 안내</p><h2>{escape(item['label'])}, 학생의 현재 공부에서 출발하기</h2><p>최근 자료에서 확인할 부분과 상담에서 물어볼 질문을 살펴보세요.</p></div>
 <div class="hk-lessons">{''.join(lessons)}</div>
 <section class="hk-centers" id="hub-centers"><div class="hk-intro"><p class="hk-kicker">지점 정보</p><h2>주소와 지점 안내를 함께 확인하세요</h2><p>전국 지점 중 세 곳의 안내 예시입니다. 아래 주소와 상세 페이지를 참고하고, 원하는 지점의 현재 수강 가능 학년·과목과 방문 일정은 상담 시 확인해 주세요.</p></div><div class="hk-center-grid">{''.join(cards)}</div><div class="hk-photos">{photos}</div><p class="hk-photo-note">사진은 공통 학습 공간 예시이며, 특정 지점의 현재 시설을 뜻하지 않습니다.</p></section>
 <section class="hk-faq" id="hub-faq"><div class="hk-intro"><p class="hk-kicker">학습 Q&amp;A</p><h2>자료를 읽고 나서 궁금할 수 있는 질문</h2></div><div class="hk-faq-list">{qhtml}</div></section>
 <nav class="hk-reading" id="hub-reading" aria-label="함께 읽을 학습 안내"><h2>다음 학습을 준비하는 방법</h2><div class="hk-reading-links">{reads}</div></nav>
</div>
<!-- hakseup-hub-content:end -->\n'''
            output=LD.sub(lambda m:m.group(1)+json.dumps(doc,ensure_ascii=False,separators=(',',':'))+m.group(3),original,count=1)
            output=output.replace('</head>','<link rel="stylesheet" href="/assets/hub-guide.css?v=20260911"></head>')
            def body_class(m):
                tag=m.group(0)
                return tag.replace('class="','class="hk-hub-page ',1) if 'class="' in tag else tag[:-1]+' class="hk-hub-page">'
            output=re.sub(r'<body[^>]*>',body_class,output,count=1)
            jump='<nav class="hk-jump" aria-label="허브 내용 바로가기"><a href="#hub-learning">학습 선택 기준</a><a href="#hub-centers">지점 정보</a><a href="#hub-faq">학습 Q&amp;A</a></nav>'
            output=output.replace('</section>','</section>'+jump,1).replace('</main>',addition+'</main>',1)
            output=re.sub(r'^[ \t]+$','',output,flags=re.M)
            (ROOT/rel).write_text(output,encoding='utf-8',newline='\n')
    sitemap=(ROOT/'sitemap.xml').read_text('utf-8'); count=0
    def date(m):
        nonlocal count
        block=m.group(0); loc=re.search(r'<loc>(.*?)</loc>',block).group(1)
        if unquote(urlparse(loc).path) in content:
            count+=1;block=re.sub(r'<lastmod>.*?</lastmod>',f'<lastmod>{DATE}</lastmod>',block)
        return block
    sitemap=re.sub(r'<url>.*?</url>',date,sitemap,flags=re.S);assert count==11
    (ROOT/'sitemap.xml').write_text(sitemap,encoding='utf-8',newline='\n')
    print(json.dumps({'hubs':11,'sections':33,'paragraphs':66,'new_faq':44,'sitemap_dates':count}))

if __name__=='__main__':main()
