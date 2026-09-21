"""Read-only regression and release audit for the revised branch directory."""
import argparse,copy,hashlib,json,sys,zipfile,re
from pathlib import Path
from collections import Counter,defaultdict,deque
from datetime import datetime
from functools import lru_cache
from urllib.parse import unquote,urlsplit,urljoin,quote
from urllib.request import urlopen,Request,build_opener,HTTPRedirectHandler
from urllib.error import HTTPError
from concurrent.futures import ThreadPoolExecutor
from lxml import html,etree
import refine_branch_guides as refine

ROOT,base,grade,subject=refine.ROOT,refine.base,refine.grade,refine.subject
DOMAIN=base.DOMAIN
OUT=ROOT/'reports/branch-refinement'
BASELINE=ROOT/'tmp/branch-improvement-20260921'
def norm(s):return ' '.join(s.split())
def sha(b):return hashlib.sha256(b).hexdigest()
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def file_for(path):
    p=ROOT/unquote(path).lstrip('/')
    return p/'index.html' if path.endswith('/') else p
def output(name,value):
    OUT.mkdir(exist_ok=True,parents=True);(OUT/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def graph(doc):
    result=[]
    for s in doc.xpath('//script[@type="application/ld+json"]/text()'):
        j=json.loads(s);result.extend(j.get('@graph',[j]) if isinstance(j,dict) else j)
    return result
def types(n):return n.get('@type',[]) if isinstance(n.get('@type'),list) else [n.get('@type')]

def audit():
    before=read(BASELINE/'baseline.json');release=read(refine.DATA/'release.json');scope=set(release['paths'])
    records=read(grade.DATA/'manifest.json')['records'];grades={r['path']:r for r in records}
    centers=read(base.DATA/'centers.json')['centers'];centers={base.route(c):c for c in centers}
    xml=etree.parse(str(ROOT/'sitemap.xml'));urls=xml.xpath('//*[local-name()="loc"]/text()')
    sitemap={unquote(n.findtext('{*}loc')):n.findtext('{*}lastmod') for n in xml.getroot()}
    errors=defaultdict(list);counts=Counter();titles=defaultdict(list);descs=defaultdict(list);ids={};links={};fragments=[];paths=[];newparas=Counter();oldparas=Counter();oldchars=0;newchars=0;allparagraphchars=0;beforeparagraphchars=0
    def check(ok,key,path,detail=None):
        if not ok:errors[key].append({'path':path,'detail':detail})
    check(len(urls)==len(sitemap)==12392,'sitemap count','/',len(urls))
    for i,(u,date) in enumerate(sitemap.items(),1):
        path=urlsplit(u).path;f=file_for(path);paths.append(path)
        check(f.is_file(),'missing page',path)
        if not f.is_file():continue
        doc=html.parse(str(f));meta={n.get('name') or n.get('property'):n.get('content','') for n in doc.xpath('//head/meta')}
        title=norm(doc.xpath('string(//title)'));description=meta.get('description','');canonical=doc.xpath('string(//link[@rel="canonical"]/@href)')
        counts['pages']+=1;check(unquote(canonical)==u,'canonical',path,canonical)
        check(len(doc.xpath('//head/title'))==1 and bool(title),'title',path)
        check(len(doc.xpath('//h1'))==1,'H1',path)
        check(0<len(description)<=80,'description length',path,len(description))
        check(meta.get('og:description')==description,'OG description',path)
        check(len(doc.xpath('//meta[@name="description"]'))==len(doc.xpath('//meta[@property="og:description"]'))==1,'description duplicates',path)
        check('noindex' not in meta.get('robots',''),'noindex',path)
        if path not in scope:continue
        counts['fullAudit']+=1;depth=len(path.strip('/').split('/'));titles[title].append(path);descs[description].append(path)
        check(meta.get('twitter:description')==description,'Twitter description',path)
        for name in ['og:title','twitter:title']:check(meta.get(name)==title,'social title',path,name)
        for name in ['og:image','twitter:image','og:image:alt','twitter:image:alt','og:image:width','og:image:height','og:image:type']:
            check(bool(meta.get(name)),'missing social image field',path,name)
        check(meta.get('og:image')==meta.get('twitter:image'),'image mismatch',path)
        imagepath=unquote(urlsplit(meta.get('og:image','')).path);check(file_for(imagepath).is_file(),'missing image',path,imagepath)
        nodes=graph(doc);ids[path]=set(doc.xpath('//@id'))
        check(len(ids[path])==len(doc.xpath('//@id')),'duplicate IDs',path)
        graphids=[n['@id'] for n in nodes if '@id' in n];check(len(graphids)==len(set(graphids)),'duplicate schema ID',path)
        for t in ['EducationalOrganization','LocalBusiness','WebPage','CollectionPage','Article','Service','FAQPage','BreadcrumbList','ItemList']:
            if any(t in types(n) for n in nodes):counts['schema:'+t]+=1
        for n in nodes:
            if 'LocalBusiness' in types(n):
                center_path=unquote(urlsplit(n['@id']).path)
                c=centers[center_path]
                check(n['address']['streetAddress']==c['address'] and n['address']['addressRegion']==refine.physical_region(c),'physical center address',path)
        web=next(n for n in nodes if any(t in types(n) for t in ['WebPage','CollectionPage']))
        article=next(n for n in nodes if n.get('@type')=='Article')
        lead=doc.xpath('string(//p[@class="hc-lead"])')
        check(article['abstract']==lead,'Article abstract',path)
        check(web['description']==article['description']==description,'schema description',path)
        check(article['headline']==title,'Article headline',path)
        check(web.get('datePublished')==article.get('datePublished')==base.DAY,'publication date',path)
        check(web['dateModified']==article['dateModified']==date,'modified date',path)
        check(date in doc.xpath('//time/@datetime'),'visible date',path)
        breadcrumbs=next(n for n in nodes if n.get('@type')=='BreadcrumbList')['itemListElement']
        check(breadcrumbs[0]['name']=='학습코칭','brand breadcrumb',path)
        check([n['position'] for n in breadcrumbs]==list(range(1,len(breadcrumbs)+1)),'breadcrumb positions',path)
        visiblecrumbs=[unquote(urljoin(canonical,x)) for x in doc.xpath('//nav[contains(@class,"hc-breadcrumb")]//a/@href')]
        check(visiblecrumbs==[unquote(n['item']) for n in breadcrumbs[:-1]],'breadcrumb visible match',path)
        visible=[(norm(n.xpath('string(summary)')),norm(' '.join(x.text_content() for x in n.findall('p')))) for n in doc.xpath('//details[@class="hc-faq"]')]
        structured=[(norm(n['name']),norm(n['acceptedAnswer']['text'])) for f in nodes if f.get('@type')=='FAQPage' for n in f['mainEntity']]
        check(visible==structured,'FAQ match',path)
        check(len(doc.xpath('//*[@id="editorial-note"]'))==1,'editorial identity',path)
        check(len([x for x in doc.xpath('//footer//nav//a/@href') if unquote(x)==refine.POLICY])==1,'single policy link',path)
        allmain=norm(doc.xpath('string(//main)'))
        searchtext=' '.join(doc.xpath('//@data-center-keywords'))
        check(not any(x in allmain+searchtext+json.dumps(nodes,ensure_ascii=False) for x in ['[후보','지역 확인 필요;','대상 미확인]','폐교]','_x000D_','#ERROR!']),'source annotations',path)
        outgoing=set();hrefs=set()
        for ref in doc.xpath('//@href|//@src'):
            if ref.startswith(('mailto:','tel:','sms:','data:')):continue
            target=urlsplit(urljoin(canonical,ref))
            if target.hostname!=urlsplit(DOMAIN).hostname:continue
            dest=unquote(target.path);hrefs.add(dest);p=file_for(dest)
            check(p.is_file(),'broken link or asset',path,ref)
            if dest in scope:outgoing.add(dest)
            if target.fragment and p.suffix=='.html':fragments.append((path,dest,unquote(target.fragment)))
        links[path]=outgoing
        for n in nodes:
            if n.get('@type')=='ItemList':
                values=n.get('itemListElement',[])
                check(n.get('numberOfItems')==len(values),'ItemList count',path)
                check([x['position'] for x in values]==list(range(1,len(values)+1)),'ItemList positions',path)
                for x in values:check(unquote(urlsplit(x.get('url','')).path) in hrefs,'ItemList visible',path,x)
        relative=f.relative_to(ROOT).as_posix();old=before.get(relative)
        if old:
            check(title==old['title'],'title preservation',path)
            check(canonical==old['canonical'],'URL preservation',path)
            check([(n.get('src'),n.get('alt')) for n in doc.xpath('//main//img')]==[tuple(v) for v in old['images']],'visible images preservation',path)
            for sid,text in old['facts'].items():
                check(norm(doc.xpath('string(//*[@id=$v])',v=sid))==text,'center facts preservation',path,sid)
        if path in grades:
            r=grades[path];c=centers[r['branchPath']];st=grade.status_for(c,r)
            counts['availability:'+st]+=1
            check(len([n for n in nodes if n.get('@type')=='Service'])==(1 if st=='confirmed' else 0),'Service truthfulness',path)
            for wanted in [c['displayName'],c['address'],grade.course_for(c,r['subject'])['label'],*grade.course_for(c,r['subject'])['notes']]:
                check(wanted in allmain,'source facts',path,wanted)
            if st!='confirmed':check('확인' in lead,'availability caveat',path)
            art=doc.xpath('//article[contains(@class,"hg-article")]')[0]
            media=doc.xpath('//*[@id="center-images"]')[0]
            check(media.getnext() is art and art[0].get('id')=='grade-focus','media placement',path)
            check(not media.xpath('.//details'),'uncollapsed body image',path)
            imgs=media.xpath('.//img');check(imgs[0].get('hidden') is not None and all(x.get('hidden') is None for x in imgs[1:]),'image visibility',path)
            check(refine.guide_path(r['grade'],r['subject']) in outgoing,'shared guide link',path)
            oldchars+=len(old['article']);newchars+=len(norm(art.text_content()))
            for p in art.xpath('.//p'):
                val=norm(p.text_content());allparagraphchars+=len(val)
                if len(val)>=80:newparas[val]+=1
        if i%2000==0:print(json.dumps({'audited':i}),flush=True)
    for path,dest,frag in fragments:
        if dest not in ids and file_for(dest).is_file():ids[dest]=set(html.parse(str(file_for(dest))).xpath('//@id'))
        check(frag in ids.get(dest,set()),'broken anchor',path,dest+'#'+frag)
    reached={'/지점안내/'};q=deque(reached)
    while q:
        for p in links.get(q.popleft(),[]):
            if p not in reached:reached.add(p);q.append(p)
    missing=scope-reached
    check(not missing,'unreachable pages','/',sorted(missing)[:20])
    check(not [v for v in titles.values() if len(v)>1],'duplicate titles','/')
    check(not [v for v in descs.values() if len(v)>1],'duplicate descriptions','/')
    with zipfile.ZipFile(BASELINE/'before.zip') as z:
        for r in records:
            d=html.fromstring(z.read(r['path'].lstrip('/')+'index.html'))
            for p in d.xpath('//article[contains(@class,"hg-article")]//p'):
                val=norm(p.text_content());beforeparagraphchars+=len(val)
                if len(val)>=80:oldparas[val]+=1
    rss=etree.parse(str(ROOT/'rss.xml'));items=rss.findall('channel/item')
    check(len(items)==50,'RSS size','/',len(items));check(len({n.findtext('link') for n in items})==50,'RSS duplicates','/')
    for n in items:
        u=unquote(n.findtext('link'));check(u in sitemap,'RSS sitemap','/',u)
        path=urlsplit(u).path;doc=html.parse(str(file_for(path)))
        check(n.findtext('description')==doc.xpath('string(//meta[@name="description"]/@content)'),'RSS description',path)
        content=n.findtext('{http://purl.org/rss/1.0/modules/content/}encoded');check(bool(content),'RSS full body',path)
        if content:check(norm(html.fromstring(content).text_content())==norm(doc.xpath('string(//main)')),'RSS current body',path)
    check('Sitemap: '+DOMAIN+'/sitemap.xml' in (ROOT/'robots.txt').read_text(),'robots sitemap','/')
    def repeated(c):return sum(len(p)*n for p,n in c.items() if n>1)
    report={'checkedAt':datetime.now().astimezone().isoformat(),'counts':dict(counts),'errors':{k:{'count':len(v),'examples':v[:12]} for k,v in errors.items()},'totalErrors':sum(len(v) for v in errors.values()),'unreachable':sorted(missing),
            'repetition':{'definition':'Exact paragraphs of 80+ characters repeated on multiple grade pages; structural facts may legitimately repeat.', 'beforeRepeatedCharacters':repeated(oldparas),'afterRepeatedCharacters':repeated(newparas),'beforeAllParagraphChars':beforeparagraphchars,'afterAllParagraphChars':allparagraphchars,'beforeCoreArticleChars':oldchars,'afterCoreArticleChars':newchars},
            'sitemapUrls':len(sitemap),'rssItems':len(items),'newPages':release['newPaths'],'gradeGuides':len(records)}
    output('local-audit.json',report);print(json.dumps({k:v for k,v in report.items() if k!='newPages'},ensure_ascii=False,indent=2))
    return report['totalErrors']


def public():
    release=read(refine.DATA/'release.json');paths=release['paths'];selected={p for p in paths if len(p.strip('/').split('/'))<=3}
    for depth,step in [(4,17),(5,109)]:selected.update([p for p in paths if p.startswith('/지점안내/') and len(p.strip('/').split('/'))==depth][::step])
    records=read(grade.DATA/'manifest.json')['records']
    selected.update(next(r['path'] for r in records if r['grade']==g and r['subject']==s) for g in grade.GRADES for s in ['영어','수학'])
    selected.update(r['path'] for r in records if r['replacementForError'])
    selected.update(['/', '/지점안내/경기/풍동점/풍동수학학원/고2/'])
    def payload(d):
        return {'title':d.xpath('string(//title)'),'canonical':d.xpath('//link[@rel="canonical"]/@href'),'meta':sorted((n.get('name') or n.get('property') or '',n.get('content','')) for n in d.xpath('//head/meta')),'graph':graph(d),'main':norm(d.xpath('string(//main)')),'links':d.xpath('//main//a/@href')}
    def visit(p):
        try:
            with urlopen(Request(DOMAIN+quote(p,safe='/'),headers={'User-Agent':'Mozilla/5.0 HakseupReleaseCheck/1.0'}),timeout=40) as res:
                d=html.fromstring(res.read());same=payload(d)==payload(html.parse(str(file_for(p))))
                return {'path':p,'status':res.status,'matchesLocal':same,'ok':res.status==200 and same and 'noindex' not in res.headers.get('X-Robots-Tag','')}
        except Exception as ex:return {'path':p,'ok':False,'error':str(ex)}
    with ThreadPoolExecutor(max_workers=6) as pool:results=list(pool.map(visit,sorted(selected)))
    feeds=[]
    for p in ['/sitemap.xml','rss.xml','robots.txt','llms.txt']:
        p='/'+p.lstrip('/')
        with urlopen(DOMAIN+p,timeout=40) as res:feeds.append({'path':p,'status':res.status,'contentType':res.headers.get('Content-Type'),'matchesLocal':res.read().replace(b'\r\n',b'\n')==file_for(p).read_bytes().replace(b'\r\n',b'\n')})
    class NoRedirect(HTTPRedirectHandler):
        def redirect_request(self,*a,**k):return None
    op=build_opener(NoRedirect);sample='/지점안내/서울/명일점/명일동수학학원/고1/';variants=[]
    destination=DOMAIN+quote(sample,safe='/')
    cases=[(DOMAIN+quote(sample.rstrip('/'),safe='/'),308,destination),
           (DOMAIN+quote(sample+'index.html',safe='/'),308,destination),
           (DOMAIN.replace('https:','http:')+quote(sample,safe='/'),308,destination),
           (DOMAIN+'/not-an-existing-release-page/',404,None)]
    for p in ['/', '/지점안내/', sample, '/학습가이드/고1-수학-공부법/', '/robots.txt']:
        suffix=quote(p,safe='/')+'?ref=qa&from=naver'
        cases.append(('https://academy-site-2.vercel.app'+suffix,308,DOMAIN+suffix))
    for u,expected_status,expected_location in cases:
        try:
            with op.open(u,timeout=35) as res:variant={'url':u,'status':res.status,'location':res.headers.get('Location')}
        except HTTPError as ex:variant={'url':u,'status':ex.code,'location':ex.headers.get('Location')}
        actual_location=urljoin(u,variant['location']) if variant['location'] else None
        variant['ok']=variant['status']==expected_status and actual_location==expected_location
        variant['expectedLocation']=expected_location
        variants.append(variant)
    assets=set()
    for p in selected:
        d=html.parse(str(file_for(p)));assets.update(unquote(urlsplit(u).path) for u in d.xpath('//meta[@property="og:image"]/@content'))
    def asset(p):
        try:
            with urlopen(DOMAIN+quote(p,safe='/'),timeout=35) as res:return {'path':p,'ok':res.status==200 and res.read()==file_for(p).read_bytes(),'contentType':res.headers.get('Content-Type')}
        except Exception as ex:return {'path':p,'ok':False,'error':str(ex)}
    with ThreadPoolExecutor(max_workers=6) as pool:images=list(pool.map(asset,sorted(assets)))
    report={'checkedAt':datetime.now().astimezone().isoformat(),'pages':len(results),'passed':sum(v['ok'] for v in results),'errors':[v for v in results if not v['ok']],'feeds':feeds,'variants':variants,'images':len(images),'imageErrors':[v for v in images if not v['ok']]}
    output('public-audit.json',report);print(json.dumps(report,ensure_ascii=False,indent=2))
    return len(report['errors'])+len(report['imageErrors'])+sum(not v['matchesLocal'] for v in feeds)+sum(not v['ok'] for v in variants)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--public',action='store_true');a=p.parse_args();sys.exit(public() if a.public else audit())
