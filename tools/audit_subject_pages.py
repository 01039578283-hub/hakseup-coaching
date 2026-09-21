"""Local structural, editorial, source-preservation and optional HTTP checks."""
import argparse
import hashlib
import json
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import unquote, urljoin, urlsplit, quote
from urllib.request import Request, urlopen
from lxml import etree, html
import build_subject_pages as subject
from subject_editorial import choose

ROOT, DATA, base = subject.ROOT, subject.DATA, subject.base


def check():
    manifest=subject.read_json(DATA/'manifest.json');records=manifest['records']
    release=subject.read_json(DATA/'release-pages.json')
    baseline=subject.read_json(DATA/'baseline.json')
    centers=subject.read_json(base.DATA/'centers.json')['centers']
    by_parent={base.route(c):c for c in centers}
    paths=release['hubs']+release['articles']
    errors=[];assets=set();titles=set();descriptions=set();faq_count=0;source_overlap=[]
    cache={}
    def document(path):
        if path not in cache:cache[path]=html.parse(str(subject.file_for(path)))
        return cache[path]
    def require(condition,*message):
        if not condition:errors.append(message)
    sm=etree.parse(str(ROOT/'sitemap.xml'))
    smurls=sm.xpath('//*[local-name()="loc"]/text()')
    smdecoded=[unquote(u) for u in smurls]
    oldsm=etree.fromstring(baseline['sitemap'].encode())
    oldurls=set(unquote(u) for u in oldsm.xpath('//*[local-name()="loc"]/text()'))
    grade_manifest=ROOT/'tools/data/grade-pages/manifest.json'
    grades=subject.read_json(grade_manifest)['records'] if grade_manifest.exists() else []
    require(len(smurls)==5695+len(grades),'Sitemap count',len(smurls))
    require(len(smurls)==len(set(smdecoded)),'Duplicate sitemap URLs')
    require(set(smdecoded)-oldurls=={unquote(base.url(r['path'])) for r in records+grades},'Sitemap additions differ from subject and grade manifests')
    require(oldurls.issubset(set(smdecoded)),'An old sitemap URL was removed')
    for path in paths:
        doc=document(path);title=doc.xpath('string(//title)');desc=doc.xpath('string(//meta[@name="description"]/@content)')
        require('</source>' not in subject.file_for(path).read_text(encoding='utf-8'),path,'HTML5 source void tag')
        require(title not in titles,path,'Duplicate title'); titles.add(title)
        require(desc not in descriptions,path,'Duplicate description');descriptions.add(desc)
        require(len(doc.xpath('//h1'))==1,path,'H1 count')
        require(doc.xpath('//link[@rel="canonical"]/@href')==[base.url(path)],path,'Canonical')
        require(unquote(base.url(path)) in smdecoded,path,'Missing sitemap')
        require(doc.xpath('string(//meta[@name="robots"]/@content)')=='index,follow',path,'Robots')
        require(doc.xpath('string(//meta[@name="naver-site-verification"]/@content)')=='2a31a5b0ca9bc7ea33092692e93e1cc3ef67759a',path,'Naver tag')
        for key,value in [('og:title',title),('twitter:title',title),('og:description',desc),('twitter:description',desc),('og:url',base.url(path))]:
            attr='property' if key.startswith('og:') else 'name'
            require(doc.xpath('//meta[@'+attr+'=$key]/@content',key=key)==[value],path,key)
        require([unquote(p) for p in doc.xpath('//header//div[@class="hc-desktop-menu"]/a/@href')]==[p for _,p in base.MENU],path,'Navigation drift')
        ids=doc.xpath('//@id'); require(len(ids)==len(set(ids)),path,'Duplicate DOM IDs')
        _,graph=subject.graph_of(doc)
        gids=[n['@id'] for n in graph if '@id' in n];require(len(gids)==len(set(gids)),path,'Duplicate schema IDs')
        for n in graph:
            if n.get('@type')=='FAQPage':
                shown=[(subject.norm(x.xpath('string(summary)')),subject.norm(' '.join(p.text_content() for p in x.findall('p')))) for x in doc.xpath('//details[@class="hc-faq"]')]
                structured=[(subject.norm(q['name']),subject.norm(q['acceptedAnswer']['text'])) for q in n['mainEntity']]
                require(shown==structured,path,'FAQ mismatch');faq_count+=len(shown)
            if n.get('@type')=='ItemList':
                require(n.get('numberOfItems')==len(n['itemListElement']),path,'ItemList count')
                require(bool(n['itemListElement']),path,'Empty ItemList')
                visible={unquote(urljoin(base.url(path),a)) for a in doc.xpath('//main//a/@href')}
                require(all(unquote(item['url']) in visible for item in n['itemListElement']),path,'ItemList has invisible links')
            if n.get('@type')=='BreadcrumbList':
                items=n['itemListElement'];require(items[-1]['item']==base.url(path),path,'Breadcrumb self')
                require(len(items)==len(path.strip('/').split('/'))+1,path,'Breadcrumb depth')
                for item in items:require(subject.file_for(unquote(urlsplit(item['item']).path)).is_file(),path,'Breadcrumb target',item['item'])
            require(n.get('@type') not in ['Review','AggregateRating'],path,'Unverified review markup')
            if n.get('@type') in ['WebPage','CollectionPage','Article']:
                require(n.get('dateModified')==subject.DAY,path,'Page update date',n.get('@id'))
        for source in doc.xpath('//*[@srcset]'):
            for candidate in source.get('srcset').split(','):
                asset=unquote(urlsplit(urljoin(base.url(path),candidate.strip().split()[0])).path)
                require((ROOT/asset.lstrip('/')).is_file(),path,'Missing responsive image',asset)
                assets.add(asset)
        for node in doc.xpath('//*[@href or @src]'):
            ref=node.get('href') or node.get('src')
            if ref.startswith(('tel:','sms:','mailto:','data:')):continue
            target=urlsplit(urljoin(base.url(path),ref))
            if target.hostname!=urlsplit(base.DOMAIN).hostname:continue
            relative=unquote(target.path);local=ROOT/relative.lstrip('/')
            if local.is_dir():local=local/'index.html'
            require(local.is_file(),path,'Missing destination',ref)
            if not local.is_file():continue
            if relative.startswith('/assets/'):assets.add(relative)
            if target.fragment and local.suffix=='.html':
                targetpath=relative if relative.endswith('/') else relative+'/'
                require(target.fragment in document(targetpath).xpath('//@id'),path,'Broken anchor',ref)
        for image in doc.xpath('//img'):
            require(all(image.get(attr) for attr in ['alt','width','height']),path,'Image attributes',image.get('src'))
        main=subject.norm(doc.xpath('string(//main)'))
        require('_x000D_' not in main and 'LOCAL ACADEMY GUIDE' not in main,path,'Workbook or draft text leaked')
    course_unknown=0;pending=0
    for r in records:
        path=r['path'];doc=document(path);c=by_parent[r['parentPath']]
        course=next(v for v in c['courses'] if v['subject']==r['subject'])
        focus,_=choose(r['subject'],r['sourceText']);_,graph=subject.graph_of(doc)
        require(doc.xpath('string(//h1)')==r['title'],path,'H1 subject/locality')
        require(doc.xpath('string(//*[@id="subject-location"])').find(c['address'])>=0,path,'Wrong center address')
        if '모두' in c['brand']:
            require(c['registeredName'] in doc.xpath('string(//*[@id="subject-location"])'),path,'Actual brand not visible')
        article=next(n for n in graph if n.get('@type')=='Article')
        web=next(n for n in graph if n.get('@type')=='WebPage')
        require(article['abstract']==doc.xpath('string(//p[@class="hc-lead"])'),path,'First answer and abstract')
        require(web['isPartOf']=={'@id':base.url(r['parentPath'])+'#webpage'},path,'Parent relationship')
        require(focus[0]['title'] in doc.xpath('string(//title)'),path,'Title not grounded in content')
        service=next((n for n in graph if n.get('@type')=='Service'),None)
        if not course['grades']:
            course_unknown+=1;require(service is None,path,'Unverified Service added')
            require('확인' in doc.xpath('string(//p[@class="hc-lead"])'),path,'Unavailable course notice missing')
        else:
            require(service is not None and course['label'] in service['audience']['audienceType'],path,'Service audience')
        if course['pendingGrades']:pending+=1
        for note in course['notes']:require(note in doc.xpath('string(//*[@id="subject-courses"])'),path,'Missing course condition',note)
        for key,suffix in [('representative','대표이미지'),('body','본문'),('map','지도')]:
            src=c['primaryMedia'][key]['src'];found=doc.xpath('//img[@src=$src]',src=src)
            require(len(found)==1 and found[0].get('alt')==r['title']+' '+suffix,path,'Image selection or ALT',key)
        imgs=doc.xpath('//*[@id="center-images"]//img')
        require([i.get('src') for i in imgs]==[c['primaryMedia'][k]['src'] for k in ['representative','body','map']],path,'Image order')
        require(imgs[0].get('hidden') is not None,path,'Representative not hidden')
        require(not doc.xpath('//*[@id="center-images"]//details'),path,'Body image collapsed')
        pairs=[x for x in records if x['locality']==r['locality'] and x['subject']!=r['subject']]
        require(pairs[0]['path'] in [unquote(p) for p in doc.xpath('//main//a/@href')],path,'Missing sibling subject')
        authored=subject.norm(doc.xpath('string(//article[@class="hs-article"])'))
        originals=[p for p in r['sourceText'].splitlines() if len(p)>50]
        source_overlap.extend([(path,p) for p in originals if p in authored])
    for path,old in baseline['branches'].items():
        doc=document(path)
        require([(unquote(i.get('src')),i.get('alt')) for i in doc.xpath('//main//img')]==[(unquote(p),a) for p,a in old['images']],path,'Existing branch images changed')
        for sid,value in old['sections'].items():
            require(subject.norm(doc.xpath('string(//*[@id=$sid])',sid=sid))==value,path,'Verified existing facts changed',sid)
        if path in by_parent:
            own={r['path'] for r in records if r['parentPath']==path}
            require({unquote(p) for p in doc.xpath('//*[@id="neighborhood-pages"]//a/@href')}==own,path,'Child hub coverage')
            if own:
                ids=doc.xpath('//main/section/@id')
                require(ids.index('neighborhood-pages')==ids.index('faq')+1,path,'Child links not after FAQ')
            ids=doc.xpath('//main/section/@id')
            require(ids.index('center-images')+1==ids.index('learning-space'),path,'Original media placement changed')
    require(not source_overlap,'Long source paragraphs copied unchanged',source_overlap[:3])
    for relative,digest in baseline['protectedFiles'].items():
        require((ROOT/relative).is_file() and base.sha(ROOT/relative)==digest,'Unrelated file modified',relative)
    for source in manifest['sources']:
        require(base.sha(subject.SOURCE/source['file'])==source['sha256'],'Input workbook changed',source['file'])
    rss=etree.parse(str(ROOT/'rss.xml'));items=rss.findall('channel/item')
    require(len(items)==50,'RSS count',len(items))
    require(all(unquote(item.findtext('link')) in smdecoded for item in items),'RSS URL outside sitemap')
    require(len(set(item.findtext('link') for item in items))==len(items),'Duplicate RSS URL')
    require(len(items[:20])==len([i for i in items[:20] if i.find('{http://purl.org/rss/1.0/modules/content/}encoded') is not None]),'New RSS articles missing full content')
    result={'result':'FAIL' if errors else 'PASS','newArticles':len(records),'enrichedHubs':len(release['hubs']),
            'uniqueTitles':len(titles),'uniqueDescriptions':len(descriptions),'sitemapUrls':len(smurls),
            'FAQPairs':faq_count,'verifiedAssets':len(assets),'unverifiedCoursePages':course_unknown,
            'pendingGradePages':pending,'sourceLongParagraphCopies':len(source_overlap),
            'protectedFiles':len(baseline['protectedFiles']),'rssItems':len(items),
            'focusCombinations':dict(Counter(r['subject']+':'+','.join(r['focuses']) for r in records)),
            'errors':errors}
    base.save(ROOT/'reports/subject-pages-local.json',result)
    print(json.dumps({**result,'errorCount':len(errors),'errors':errors[:8]},ensure_ascii=False,indent=2))
    assert not errors
    return paths,assets


def http(origin,paths,assets):
    jobs=paths+sorted(assets)+['/sitemap.xml','/rss.xml','/robots.txt','/llms.txt'];errors=[]
    def visit(path):
        try:
            with urlopen(Request(origin.rstrip('/')+quote(path,safe='/'),headers={'User-Agent':'HakseupLocalQA/1.0'}),timeout=30) as response:
                received=response.read()
                file=subject.file_for(path) if path in paths else ROOT/path.lstrip('/')
                if response.status!=200 or received!=file.read_bytes():return(path,'HTTP status or bytes differ')
        except Exception as error:return(path,str(error))
    with ThreadPoolExecutor(max_workers=8) as pool:
        errors=[r for r in pool.map(visit,jobs) if r]
    result={'result':'FAIL' if errors else 'PASS','origin':origin,'checks':len(jobs),'errors':errors}
    base.save(ROOT/'reports/subject-pages-http.json',result);print(json.dumps(result,ensure_ascii=False,indent=2));assert not errors


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--base');args=parser.parse_args()
    paths,assets=check()
    if args.base:http(args.base,paths,assets)
