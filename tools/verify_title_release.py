"""Verify every changed page locally, or a stratified sample on production."""
from __future__ import annotations

import argparse
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import re
from urllib.request import urlopen, Request
from xml.etree import ElementTree as ET

from personalize_title_suffixes import ROOT, REPORT, title_of, masked, sha, META_RE, attrs


def verify_source(row, source):
    errors=[]
    if any(x in row['path'] for x in ('초등','중등','중학생')) and '모의고사' in row['suffix']:
        errors.append('grade-inappropriate exam suffix')
    if title_of(source)!=row['after']:
        errors.append('title mismatch')
    if sha(masked(source))!=row['unchangedContentSha256']:
        errors.append('non-title content changed')
    for tag in META_RE.findall(source):
        values=attrs(tag)
        if values.get('property')=='og:title' or values.get('name')=='twitter:title':
            if values.get('content')!=row['after']:
                errors.append('social title mismatch')
    for raw in re.findall(r'<script\b[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',source,re.I|re.S):
        json.loads(raw)
    return errors


def selection(entries):
    groups=defaultdict(list)
    for row in entries:
        p=row['path'].split('/')[:-1]
        if p[0]=='전국학원':
            key='national-'+str(len(p)) + ('-'+p[-1] if len(p)==5 else '')
        else:
            key='subject-'+p[1]+('-hub' if len(p)==2 else '')
        groups[key].append(row)
    result={}
    for key, rows in groups.items():
        for i in sorted({0,len(rows)//2,len(rows)-1}):
            result[rows[i]['path']]=rows[i]
    for row in entries:
        if '명일' in row['path']:
            result[row['path']]=row
    return list(result.values())


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--public',action='store_true')
    args=parser.parse_args()
    report=json.loads(REPORT.read_text(encoding='utf-8'))
    entries=selection(report['entries']) if args.public else report['entries']

    def check(row):
        try:
            if args.public:
                req=Request(row['url'],headers={'User-Agent':'Hakseup-Release-Verification/1.0'})
                with urlopen(req,timeout=30) as response:
                    status=response.status
                    source=response.read().decode('utf-8')
            else:
                status=None
                source=(ROOT/row['path']).read_bytes().decode('utf-8')
            return dict(path=row['path'],url=row['url'],status=status,title=title_of(source),errors=verify_source(row,source))
        except Exception as exc:
            return dict(path=row['path'],url=row['url'],errors=[str(exc)])

    with ThreadPoolExecutor(max_workers=8) as pool:
        results=list(pool.map(check,entries))
    failures=[r for r in results if r['errors']]
    if not args.public:
        sitemap=ET.parse(ROOT/'sitemap.xml')
        rss=ET.parse(ROOT/'rss.xml')
        if len(sitemap.findall('.//{http://www.sitemaps.org/schemas/sitemap/0.9}url'))!=4743:
            raise ValueError('sitemap count changed')
        if len(rss.findall('.//item'))!=50:
            raise ValueError('RSS count changed')
    summary=dict(mode='public' if args.public else 'local',checked=len(results),failures=len(failures),
                 checkedAt=datetime.now(timezone.utc).isoformat(),results=results)
    destination=REPORT.with_name('title-suffix-'+summary['mode']+'-verification.json')
    destination.write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')
    print(json.dumps({k:v for k,v in summary.items() if k!='results'},ensure_ascii=False))
    for failure in failures[:20]:
        print(json.dumps(failure,ensure_ascii=False))
    if failures:
        raise SystemExit(1)
    print('TITLE_RELEASE_'+summary['mode'].upper()+'_PASS')


if __name__=='__main__':
    main()
