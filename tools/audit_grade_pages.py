"""Full local checks for 6,678 grade pages, plus optional real HTTP verification."""
import argparse
import json
import re
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from urllib.parse import unquote,urlsplit,urljoin,quote
from urllib.request import urlopen,Request
from lxml import html,etree
import build_grade_pages as grade

base,subject,ROOT,DATA=grade.base,grade.subject,grade.ROOT,grade.DATA


@lru_cache(maxsize=256)
def ids_at(path):
    return set(html.parse(str(path)).xpath('//@id'))


def audit():
    manifest=grade.READ(DATA/'manifest.json');records=manifest['records']
    parents=grade.READ(subject.DATA/'manifest.json')['records'];by_parent={p['path']:p for p in parents}
    centers=grade.READ(base.DATA/'centers.json')['centers'];by_center={base.route(c):c for c in centers}
    release=grade.READ(DATA/'release-pages.json');sm=etree.parse(str(ROOT/'sitemap.xml'))
    smurls=sm.xpath('//*[local-name()="loc"]/text()');smset=set(unquote(u) for u in smurls)
    errors=[];titles=set();descriptions=set();headlines=set();assets=set();faqs=0;status=Counter();body_lengths=[];source_copies=[]
    def check(condition,*info):
        if not condition:errors.append(info)
    check(len(records)==6678,'Grade page count',len(records))
    check(len(smurls)==12373 and len(smurls)==len(smset),'Sitemap size or duplicates',len(smurls),len(smset))
    check(Counter((r['grade'],r['subject']) for r in records)==Counter({(g,s):371 for g in grade.GRADES for s in ['영어','수학']}),'18 workbook coverage')
    check(len({r['path'] for r in records})==6678,'Duplicate grade path')
    check(len({r['parentPath'] for r in records})==742,'Parent coverage')
    check(sum(r['replacementForError'] for r in records)==7,'Error replacements')
    for src in manifest['sources']:check(base.sha(grade.SOURCE/src['file'])==src['sha256'],'Source workbook changed',src['file'])
    for r in records:
        path=r['path'];c=by_center[r['branchPath']];p=grade.PROFILES[(r['grade'],r['subject'])]
        file=subject.file_for(path);doc=html.parse(str(file));raw=file.read_text(encoding='utf-8')
        title=doc.xpath('string(//title)');desc=doc.xpath('string(//meta[@name="description"]/@content)')
        h1=doc.xpath('string(//h1)');canonical=base.url(path);_,graph=subject.graph_of(doc)
        title_expected=r['title']+' | '+p['title']
        check(title==title_expected,path,'Title does not match grade content')
        check(title not in titles,path,'Duplicate title');titles.add(title)
        check(desc not in descriptions and r['title'] in desc,path,'Duplicate or mismatched description');descriptions.add(desc)
        check(h1==r['title'] and len(doc.xpath('//h1'))==1,path,'H1');headlines.add(h1)
        check(doc.xpath('//link[@rel="canonical"]/@href')==[canonical],path,'Canonical')
        check(unquote(canonical) in smset,path,'Not in sitemap')
        check(doc.xpath('//meta[@name="robots"]/@content')==['index,follow'],path,'Robots')
        for key,value in [('og:title',title),('twitter:title',title),('og:description',desc),('twitter:description',desc),('og:url',canonical)]:
            attr='property' if key.startswith('og:') else 'name'
            check(doc.xpath('//meta[@'+attr+'=$k]/@content',k=key)==[value],path,key)
        for attr in ['og:image','twitter:image']:
            typ='property' if attr.startswith('og:') else 'name'
            image=doc.xpath('string(//meta[@'+typ+'=$k]/@content)',k=attr)
            check(image==base.url(c['primaryMedia']['representative']['src']),path,attr)
        check([unquote(v) for v in doc.xpath('//header//div[@class="hc-desktop-menu"]/a/@href')]==[p for _,p in base.MENU],path,'Menu drift')
        ids=doc.xpath('//@id');check(len(ids)==len(set(ids)),path,'Duplicate IDs')
        gids=[n['@id'] for n in graph if '@id' in n];check(len(gids)==len(set(gids)),path,'Duplicate schema identities')
        article=next(n for n in graph if n.get('@type')=='Article');web=next(n for n in graph if n.get('@type')=='WebPage')
        lead=doc.xpath('string(//p[@class="hc-lead"])')
        check(article['abstract']==lead,path,'Abstract/visible lead mismatch')
        check(p['summary'] in lead and grade.availability(c,r) in lead,path,'First-answer or course wording drift')
        check(web['isPartOf']=={'@id':base.url(r['parentPath'])+'#webpage'},path,'Parent schema')
        check(article['isPartOf']=={'@id':web['@id']},path,'Article/page relation')
        check(web['mainEntity']=={'@id':article['@id']},path,'WebPage mainEntity')
        check(article['dateModified']==grade.DAY and article['datePublished']==grade.DAY,path,'Article dates')
        check(doc.xpath('//time/@datetime')==[grade.DAY],path,'Visible date')
        crumb=next(n for n in graph if n.get('@type')=='BreadcrumbList')['itemListElement']
        expected=['/','/지점안내/','/지점안내/'+r['region']+'/',r['branchPath'],r['parentPath'],path]
        check([unquote(n['item']).removeprefix(base.DOMAIN) for n in crumb]==expected,path,'Breadcrumb hierarchy')
        check([n['position'] for n in crumb]==list(range(1,7)),path,'Breadcrumb positions')
        faq=next(n for n in graph if n.get('@type')=='FAQPage')
        visible=[(subject.norm(n.xpath('string(summary)')),subject.norm(' '.join(x.text_content() for x in n.findall('p')))) for n in doc.xpath('//details[@class="hc-faq"]')]
        structured=[(subject.norm(n['name']),subject.norm(n['acceptedAnswer']['text'])) for n in faq['mainEntity']]
        check(visible==structured and len(visible)==4,path,'FAQ mismatch');faqs+=len(visible)
        org=next(n for n in graph if n.get('@id')==base.url(r['branchPath'])+'#center')
        check({'EducationalOrganization','LocalBusiness'}.issubset(org['@type']),path,'Center types')
        check(org['name']==c['displayName'] and org['address']['streetAddress']==c['address'],path,'Center identity')
        state=grade.status_for(c,r);status[state]+=1
        services=[n for n in graph if n.get('@type')=='Service']
        check(len(services)==(1 if state=='confirmed' else 0),path,'Unsupported grade Service')
        if services:
            check(services[0]['provider']=={'@id':org['@id']},path,'Service provider')
            check(services[0]['audience']['audienceType']==grade.grade_name(r['grade'])+' 학생',path,'Service grade')
        centertext=doc.xpath('string(//*[@id="grade-center"])')
        for fact in [c['address'],c['displayName'],grade.availability(c,r),*grade.course_for(c,r['subject'])['notes']]:check(fact in centertext,path,'Missing verified condition',fact)
        for school in c['schools'].get({'초':'초등','중':'중등','고':'고등'}[r['grade'][0]],[]):check(school in centertext,path,'School level mismatch',school)
        check(p['example'] in doc.xpath('string(//*[@id="practice-example"])'),path,'Grade example missing')
        check(p['answer'] in doc.xpath('string(//*[@id="practice-example"])'),path,'Example explanation missing')
        body=subject.norm(doc.xpath('string(//article[@class="hs-article hg-article"])'));body_lengths.append(len(body))
        check(len(body)>600,path,'Learning text too short')
        check(not any(x in raw for x in ['#ERROR!','_x000D_','○○','</source>']),path,'Draft artifacts')
        for node in doc.xpath('//article[@class="hs-article hg-article"]//p'):
            val=subject.norm(node.text_content())
            if len(val)>=50 and grade.digest(val) in r['sourceParagraphHashes']:source_copies.append(path)
        images=doc.xpath('//*[@id="center-images"]//img')
        check(len(images)==3,path,'Primary media count')
        for img,key,suffix in zip(images,['representative','body','map'],['대표이미지','본문','지도']):
            check(unquote(img.get('src'))==c['primaryMedia'][key]['src'] and img.get('alt')==r['title']+' '+suffix,path,'Image/ALT',key)
            check(img.get('width') and img.get('height'),path,'Image size',key)
        check(images[0].get('hidden') is not None and all(i.get('hidden') is None for i in images[1:]),path,'Media visibility')
        check(not doc.xpath('//*[@id="center-images"]//details'),path,'Body/map image collapsed')
        linklist=next(n for n in graph if n.get('@type')=='ItemList')
        shown=[unquote(v) for v in doc.xpath('//*[@id="related-pages"]//a/@href')]
        check([unquote(n['url']).removeprefix(base.DOMAIN) for n in linklist['itemListElement']]==shown,path,'ItemList/visible links')
        check(4<=len(shown)<=5,path,'Excessive/missing related links')
        refs=doc.xpath('//@href|//@src')
        refs += [part.strip().split()[0] for src in doc.xpath('//@srcset') for part in src.split(',')]
        for ref in refs:
            if ref.startswith(('tel:','sms:','mailto:','data:')):continue
            target=urlsplit(urljoin(canonical,ref))
            if target.hostname!=urlsplit(base.DOMAIN).hostname:continue
            relative=unquote(target.path);local=ROOT/relative.lstrip('/')
            if local.is_dir():local=local/'index.html'
            check(local.is_file(),path,'Missing link or asset',ref)
            if relative.startswith('/assets/'):assets.add(relative)
            if local.is_file() and target.fragment and local.suffix=='.html':check(unquote(target.fragment) in ids_at(local),path,'Broken fragment',ref)
    for parent in parents:
        doc=html.parse(str(subject.file_for(parent['path'])));_,graph=subject.graph_of(doc)
        links=[unquote(v) for v in doc.xpath('//*[@id="grade-pages"]//a/@href')]
        check(links==[parent['path']+g+'/' for g in grade.GRADES],parent['path'],'Nine grade button order')
        ids=doc.xpath('//main/section/@id');check(ids.index('grade-pages')==ids.index('faq')+1,parent['path'],'Grade links placement')
        schema=next(n for n in graph if n.get('@id')==base.url(parent['path'])+'#grade-list')
        check(schema['numberOfItems']==9,parent['path'],'Grade list schema')
    check(not source_copies,'Source paragraph copied unchanged',source_copies[:5])
    rss=etree.parse(str(ROOT/'rss.xml'));items=rss.findall('channel/item')
    check(len(items)==50 and len(set(x.findtext('link') for x in items))==50,'RSS size/duplicates')
    check({unquote(x.findtext('link')) for x in items}.issubset(smset),'RSS URLs outside sitemap')
    for item in items[:30]:
        content=item.findtext('{http://purl.org/rss/1.0/modules/content/}encoded')
        check(bool(content),'New RSS item lacks full content',item.findtext('link'))
        if content:
            d=html.fromstring(content)
            check(all(v.startswith(('https://','tel:','sms:')) for v in d.xpath('//@href|//@src')),'RSS relative URLs',item.findtext('link'))
    check('Sitemap: '+base.DOMAIN+'/sitemap.xml' in (ROOT/'robots.txt').read_text(encoding='utf-8'),'robots sitemap')
    check('동네별 과목과 학년 학습 안내' in (ROOT/'llms.txt').read_text(encoding='utf-8'),'llms guide')
    result={'result':'FAIL' if errors else 'PASS','gradeArticles':len(records),'subjectHubs':len(parents),
            'titles':len(titles),'descriptions':len(descriptions),'H1s':len(headlines),'FAQPairs':faqs,
            'sitemapUrls':len(smurls),'RSSItems':len(items),'assets':len(assets),'availability':dict(status),
            'sourceParagraphCopies':len(source_copies),'sourceErrorsReplaced':7,'sourceMappingReviews':len(manifest['repairs']),
            'learningTextCharacters':{'min':min(body_lengths),'max':max(body_lengths)},'errors':errors}
    base.save(ROOT/'reports/grade-pages-local.json',result)
    print(json.dumps({**result,'errorCount':len(errors),'errors':errors[:6]},ensure_ascii=False,indent=2))
    assert not errors
    return [r['path'] for r in records],assets


def http(origin, paths, assets, public=False):
    jobs=paths+sorted(assets)+['/sitemap.xml','/rss.xml','/robots.txt','/llms.txt'];errors=[]
    def check(path):
        try:
            request=Request(origin.rstrip('/')+quote(path,safe='/'),headers={'User-Agent':'Mozilla/5.0 HakseupReleaseQA/1.0'})
            with urlopen(request,timeout=50) as response:
                data=response.read();local=subject.file_for(path) if path.endswith('/') else ROOT/path.lstrip('/')
                if response.status!=200:return(path,'Not HTTP 200')
                if path.endswith('/'):
                    doc=html.fromstring(data);expected=html.parse(str(local))
                    for selector in ['string(//title)','string(//main)','string(//link[@rel="canonical"]/@href)']:
                        if subject.norm(doc.xpath(selector))!=subject.norm(expected.xpath(selector)):return(path,'Deployed content mismatch',selector)
                    if doc.xpath('//meta[@name="robots"]/@content')!=['index,follow']:return(path,'Robots')
                    if public and len(doc.xpath('//script[contains(@src,"wawa-visit-collector") and @data-site="wawa-03"]'))!=1:return(path,'Analytics integration')
                elif data.replace(b'\r\n',b'\n')!=local.read_bytes().replace(b'\r\n',b'\n'):return(path,'Different static bytes')
        except Exception as ex:return(path,str(ex))
    with ThreadPoolExecutor(max_workers=6) as pool:
        for item in pool.map(check,jobs):
            if item:errors.append(item)
    result={'result':'FAIL' if errors else 'PASS','origin':origin,'checks':len(jobs),'htmlPages':len(paths),'errors':errors}
    base.save(ROOT/('reports/grade-pages-public.json' if public else 'reports/grade-pages-http.json'),result)
    print(json.dumps({**result,'errors':errors[:6]},ensure_ascii=False,indent=2));assert not errors


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--base');parser.add_argument('--public',action='store_true');args=parser.parse_args()
    paths,assets=audit()
    if args.base:
        if args.public:
            records=grade.READ(DATA/'manifest.json')['records']
            chosen=set(paths[::109])
            for g in grade.GRADES:
                for s in ['영어','수학']:chosen.add(next(r['path'] for r in records if r['grade']==g and r['subject']==s))
            chosen.update(r['path'] for r in records if r['replacementForError'])
            centers=grade.READ(base.DATA/'centers.json')['centers'];by_center={base.route(c):c for c in centers}
            chosen.update(next(r['path'] for r in records if grade.status_for(by_center[r['branchPath']],r)==state) for state in ['pending','unlisted'])
            chosen.update(['/','/지점안내/','/지점안내/서울/','/지점안내/서울/명일점/','/지점안내/서울/명일점/명일동수학학원/'])
            paths=sorted(chosen)
            assets={'/assets/branch-grades.css','/assets/branch-subjects.css'}|set(sorted(assets)[::37])
        http(args.base,paths,assets,args.public)
