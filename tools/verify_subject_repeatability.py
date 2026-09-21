"""Check regenerating the same manifest produces the same public files."""
import json
import build_subject_pages as subject

release=subject.read_json(subject.DATA/'release-pages.json')
paths=release['hubs']+release['articles']
files=[subject.file_for(p) for p in paths]
files += [subject.ROOT/p for p in ['sitemap.xml','rss.xml','llms.txt']]
before={str(p.relative_to(subject.ROOT)):subject.base.sha(p) for p in files}
subject.update_from_manifest()
changed=[p for p,digest in before.items() if subject.base.sha(subject.ROOT/p)!=digest]
result={'result':'FAIL' if changed else 'PASS','checkedFiles':len(files),'changed':changed}
subject.base.save(subject.ROOT/'reports/subject-pages-repeatability.json',result)
print(json.dumps(result,ensure_ascii=False,indent=2))
assert not changed
