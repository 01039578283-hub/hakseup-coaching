"""Deterministic local and optional HTTP release checks; no website mutations."""
import argparse
import hashlib
import json
import re
import subprocess
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import unquote, urljoin, urlsplit
from lxml import html, etree
from PIL import Image
from build_coaching_directory import ROOT, DATA, DOMAIN, DAY, SOURCE, route, url, MENU

BASELINE='dbadcc1947351b4723c5c29eb8eaf45dfc4dd36c'

def audit():
    release=json.loads((DATA/'release-pages.json').read_text(encoding='utf-8'))
    manifest=json.loads((DATA/'centers.json').read_text(encoding='utf-8'))
    errors=[];titles=set();descriptions=set();assets=set(); newpaths=[]
    sitemap=etree.parse(str(ROOT/'sitemap.xml'))
    sm={unquote(s) for s in sitemap.xpath('//*[local-name()="loc"]/text()')}
    rss=etree.parse(str(ROOT/'rss.xml'))
    if len(sm)!=len(sitemap.xpath('//*[local-name()="loc"]')):errors.append('Duplicate sitemap URLs')
    assert 'Sitemap: '+DOMAIN+'/sitemap.xml' in (ROOT/'robots.txt').read_text()
    for path in release:
        f=ROOT/path.strip('/')/'index.html' if path!='/' else ROOT/'index.html'
        doc=html.parse(str(f)); raw=f.read_text(encoding='utf-8')
        title=doc.xpath('string(//title)');desc=doc.xpath('string(//meta[@name="description"]/@content)')
        if title in titles:errors.append((path,'Duplicate title'))
        titles.add(title)
        if not desc:errors.append((path,'Missing description'))
        descriptions.add(desc)
        if len(doc.xpath('//h1'))!=1:errors.append((path,'H1 count'))
        canonical=doc.xpath('//link[@rel="canonical"]/@href')
        if len(canonical)!=1 or unquote(canonical[0])!=unquote(url(path)):errors.append((path,'Canonical',canonical))
        if unquote(url(path)) not in sm:errors.append((path,'Missing sitemap'))
        if not doc.xpath('//html[@lang="ko"]'):errors.append((path,'Language'))
        isnew=path.startswith('/지점안내/') or path in ['/','/학습가이드/','/진단상담/']
        if isnew:
            newpaths.append(path)
            if doc.xpath('string(//meta[@property="og:url"]/@content)')!=url(path):errors.append((path,'OG URL'))
            for key,expected in [('og:title',title),('twitter:title',title),('og:description',desc),('twitter:description',desc)]:
                attr='property' if key.startswith('og:') else 'name'
                if doc.xpath(f'string(//meta[@{attr}="{key}"]/@content)')!=expected:errors.append((path,key))
        for sc in doc.xpath('//script[@type="application/ld+json"]'):
            try: data=json.loads(sc.text)
            except Exception as ex:errors.append((path,'JSON',str(ex)));continue
            nodes=data.get('@graph',[data])
            for node in nodes:
                if isnew and node.get('@type')=='WebPage' and node.get('dateModified')!=DAY:errors.append((path,'Modification date'))
                if isnew and node.get('@type')=='Service':
                    audience=node.get('audience',{})
                    if audience.get('@type')!='EducationalAudience' or 'educationalLevel' in audience or not audience.get('audienceType'):errors.append((path,'Educational audience vocabulary'))
                if node.get('@type')=='FAQPage' and isnew:
                    actual=[(' '.join(x.xpath('string(summary)').split()),' '.join(' '.join(p.text_content().split()) for p in x.findall('p'))) for x in doc.xpath('//details[contains(@class,"hc-faq")]')]
                    schema=[(q['name'],q['acceptedAnswer']['text']) for q in node['mainEntity']]
                    if actual!=schema:errors.append((path,'FAQ mismatch'))
                if node.get('@type')=='BreadcrumbList' and isnew:
                    items=node['itemListElement']
                    if [v['position'] for v in items]!=list(range(1,len(items)+1)) or items[-1]['item']!=url(path):errors.append((path,'Breadcrumb'))
                if node.get('@type')=='ItemList' and 'numberOfItems' in node and node['numberOfItems']!=len(node['itemListElement']):errors.append((path,'ItemList'))
        nav=doc.xpath('//header[contains(@class,"hc-header")]//div[@class="hc-desktop-menu"]/a/@href')
        if nav!=[p for _,p in MENU]:errors.append((path,'Shared navigation'))
        for el in doc.xpath('//*[@href or @src]'):
            ref=el.get('href') or el.get('src')
            if ref.startswith(('tel:','sms:','mailto:','data:')):continue
            u=urlsplit(urljoin(url(path),ref))
            if u.hostname!=urlsplit(DOMAIN).hostname:continue
            local=ROOT/unquote(u.path).lstrip('/')
            if local.is_dir():local=local/'index.html'
            if not local.is_file():errors.append((path,'Missing link or asset',ref));continue
            if u.path.startswith('/assets/'):assets.add(unquote(u.path))
            if u.fragment and local.suffix=='.html':
                target=doc if local==f else html.parse(str(local))
                if u.fragment not in target.xpath('//@id'):errors.append((path,'Broken anchor',ref))
        if isnew:
            for img in doc.xpath('//img'):
                if not img.get('alt') or not img.get('width') or not img.get('height'):errors.append((path,'Image attributes',img.get('src')))
    for c in manifest['centers']:
        p=ROOT/route(c).strip('/')/'index.html';doc=html.parse(str(p))
        # Literal factual fields present, no borrowed brand/center map.
        body=doc.xpath('string(//main)')
        for fact in [c['address'],c['registeredName'],c['registrationNumber']]:
            if fact not in body:errors.append((route(c),'Missing fact',fact))
        rep=doc.xpath('//img[@hidden]/@src')
        if rep!=[c['primaryMedia']['representative']['src']]:errors.append((route(c),'Representative image'))
        for key,suffix in [('body','본문'),('map','지도')]:
            expected=c['primaryMedia'][key]['src'];matches=doc.xpath('//img[@src=$src]',src=expected)
            if len(matches)!=1 or matches[0].get('alt')!=c['displayName']+' '+suffix:errors.append((route(c),'Primary image',key))
        ids=doc.xpath('//main/section/@id')
        if ids.index('center-images')+1!=ids.index('learning-space'):errors.append((route(c),'Media placement'))
        if doc.xpath('//details[contains(@class,"hc-gallery-toggle")]/@open'):errors.append((route(c),'Gallery must start closed'))
        if c['photoMode']=='common' and any(c['routeName'] in a for a in doc.xpath('//div[contains(@class,"hc-gallery")]//img/@alt')):errors.append((route(c),'Shared photo mislabeled'))
    for source in manifest['sources']:
        if hashlib.sha256((SOURCE/source['file']).read_bytes()).hexdigest()!=source['sha256']:errors.append(('Source workbook changed',source['file']))
    # Batch-read original Git blobs to prove old manuscripts, images and metadata
    # outside upgraded hub pages were not accidentally rewritten.
    tree=subprocess.check_output(['git','ls-tree','-r','-z',BASELINE],cwd=ROOT)
    entries=[]
    for entry in tree.split(b'\0'):
        if not entry:continue
        head,p=entry.split(b'\t',1);path=p.decode('utf-8')
        if path.endswith('.html') and not path.startswith(('tmp/','tools/')):
            key='/'+str(Path(path).parent).replace('\\','/').strip('.')+'/'
            if key.replace('//','/') not in release:entries.append((path,head.split()[2]))
    output=subprocess.check_output(['git','cat-file','--batch'],cwd=ROOT,input=b'\n'.join(v for _,v in entries)+b'\n')
    pos=0
    def strip(s):
        s=re.sub(r'<header\b.*?</header>','',s,flags=re.S)
        s=re.sub(r'<link rel="stylesheet" href="/assets/coaching-upgrade.css\?v=20260921">\s*','',s)
        return s.replace('\r\n','\n').strip()
    for p,_ in entries:
        end=output.index(b'\n',pos);size=int(output[pos:end].split()[-1]);old=output[end+1:end+1+size].decode('utf-8');pos=end+size+2
        now=(ROOT/p).read_text(encoding='utf-8')
        if strip(old)!=strip(now):errors.append((p,'Legacy content changed outside navigation'))
    for item in rss.findall('channel/item'):
        if unquote(item.findtext('link')) not in sm:errors.append(('RSS outside sitemap',item.findtext('link')))
    result={'date':DAY,'contentPages':len(release),'newDirectoryPages':len([p for p in newpaths if p.startswith('/지점안내/')]),'centers':len(manifest['centers']),'uniqueTitles':len(titles),'uniqueDescriptions':len(descriptions),'sitemapUrls':len(sm),'rssItems':len(rss.findall('channel/item')),'legacyPagesPreserved':len(entries),'linkedAssets':len(assets),'errors':errors}
    (ROOT/'reports').mkdir(exist_ok=True)
    (ROOT/'reports/coaching-directory-local.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')
    print(json.dumps(result,ensure_ascii=False,indent=2))
    if errors:raise SystemExit(1)
    return release,assets


def http(base,release,assets):
    jobs=list(release)+sorted(assets)+['/sitemap.xml','/rss.xml','/robots.txt','/llms.txt']
    errors=[];preview_mime_warnings=[]
    def check(path):
        try:
            request=urllib.request.Request(base.rstrip('/')+quote_path(path),headers={'User-Agent':'Mozilla/5.0 HakseupReleaseQA/1.0'})
            with urllib.request.urlopen(request,timeout=50) as response:
                data=response.read();ct=response.headers.get('Content-Type','')
                if response.status!=200:return (path,'HTTP',response.status)
                if path in release:
                    d=html.fromstring(data)
                    if d.xpath('string(//title)')!=release[path]['title']:return(path,'Stale title')
                    if '/지점안내/' not in [unquote(a) for a in d.xpath('//header//a/@href')]:return(path,'Missing deployed nav')
                    canonical=d.xpath('string(//link[@rel="canonical"]/@href)')
                    if unquote(canonical)!=unquote(url(path)):return(path,'Canonical mismatch')
                    local=(ROOT/path.strip('/')/'index.html').read_text(encoding='utf-8') if path!='/' else (ROOT/'index.html').read_text(encoding='utf-8')
                    expected=html.fromstring(local).xpath('string(//main)')
                    if ' '.join(d.xpath('string(//main)').split())!=' '.join(expected.split()):return(path,'Main content mismatch')
                elif path.endswith(('.webp','.jpg','.png','.gif','.avif')):
                    if not ct.startswith('image/'):
                        if urlsplit(base).hostname in ('127.0.0.1','localhost') and ct=='application/octet-stream' and path.endswith(('.webp','.avif')):
                            preview_mime_warnings.append(path)
                        else:return(path,'Image MIME',ct)
                    if data!=(ROOT/path.lstrip('/')).read_bytes():return(path,'Image bytes differ')
                elif path.endswith(('.css','.js')):
                    if data.replace(b'\r\n',b'\n')!=(ROOT/path.lstrip('/')).read_bytes().replace(b'\r\n',b'\n'):return(path,'Static bytes differ')
            return None
        except Exception as ex:return(path,str(ex))
    with ThreadPoolExecutor(max_workers=5) as pool:
        for result in pool.map(check,jobs):
            if result:errors.append(result)
    report={'base':base,'checks':len(jobs),'contentPages':len(release),'assets':len(assets),'previewOnlyWindowsMimeWarnings':len(preview_mime_warnings),'errors':errors}
    (ROOT/'reports/coaching-directory-http.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')
    print(json.dumps({**report,'errorCount':len(errors),'errors':errors[:8]},ensure_ascii=False,indent=2))
    if errors:raise SystemExit(1)


def quote_path(p):
    from urllib.parse import quote
    return quote(unquote(p),safe='/')


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--base');args=parser.parse_args()
    release,assets=audit()
    if args.base:http(args.base,release,assets)
