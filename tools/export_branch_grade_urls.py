"""Export only the requested branch hierarchy after checking the public sitemap."""
import argparse
import json
from pathlib import Path
from urllib.parse import unquote
from urllib.request import Request,urlopen
from lxml import etree
import build_grade_pages as grade


def export(origin):
    centers=grade.READ(grade.base.DATA/'centers.json')['centers']
    parents=grade.READ(grade.subject.DATA/'manifest.json')['records']
    records=grade.READ(grade.DATA/'manifest.json')['records']
    regions=[v for v in grade.base.REGIONS if any(c['region']==v for c in centers)]
    order={v:i for i,v in enumerate(regions)}
    centers.sort(key=lambda c:(order[c['region']],c['routeName']))
    parents.sort(key=lambda r:(order[r['region']],r['branch'],r['locality'],r['subject']))
    paths=['/','/지점안내/']+['/지점안내/'+r+'/' for r in regions]+[grade.base.route(c) for c in centers]+[r['path'] for r in parents]
    childset={r['path'] for r in records}
    for r in parents:
        for g in grade.GRADES:
            p=r['path']+g+'/'
            assert p in childset
            paths.append(p)
    assert len(paths)==7631 and len(set(paths))==7631
    assert all(p=='/' or p.startswith('/지점안내/') for p in paths)
    assert '/지점안내/서울/명일점/명일동수학학원/고1/' in paths
    with urlopen(Request(origin.rstrip('/')+'/sitemap.xml',headers={'User-Agent':'HakseupURLExport/1.0'}),timeout=60) as response:
        assert response.status==200
        xml=response.read()
    doc=etree.fromstring(xml)
    public={unquote(u).removeprefix(grade.base.DOMAIN) for u in doc.xpath('//*[local-name()="loc"]/text()')}
    branch={p for p in public if p.startswith('/지점안내/')}
    assert branch==set(paths)-{'/'},('Public branch sitemap differs',len(branch),len(paths))
    assert '/' in public
    domain='https://학습코칭.kr'
    lines=[domain+p for p in paths]
    assert not any('%' in v or '#' in v or '?' in v or 'xn--' in v for v in lines)
    destination=Path.home()/'Desktop'/f'학습코칭.kr_지점안내_URL_허브순_{len(lines)}개_{grade.DAY}.txt'
    content='\n'.join(lines)+'\n'
    if destination.exists():
        assert destination.read_text(encoding='utf-8-sig')==content,'Existing export differs; preserve it and choose a versioned name.'
    else:
        destination.write_text(content,encoding='utf-8-sig',newline='\n')
    assert destination.read_text(encoding='utf-8-sig').splitlines()==lines
    report={'file':str(destination),'lines':len(lines),'unique':len(set(lines)),
            'home':1,'directory':1,'regions':16,'centers':193,'subjectHubs':742,'gradePages':6678,
            'order':'Home -> directory -> all regions -> all branches -> all subject hubs -> grade pages grouped by subject hub, elementary to high school',
            'publicSitemapMatched':True,'outsideScope':0,'encoding':'UTF-8 BOM, LF, one Korean URL per line'}
    grade.base.save(grade.ROOT/'reports/grade-url-export.json',report)
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--origin',default=grade.base.DOMAIN);args=parser.parse_args();export(args.origin)
