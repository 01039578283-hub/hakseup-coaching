"""Regeneration check, including ancestor hooks and all discovery documents."""
import json
import build_grade_pages as grade

release=grade.READ(grade.DATA/'release-pages.json')
ancestors=grade.READ(grade.subject.DATA/'release-pages.json')['hubs']
paths=ancestors+release['subjectHubs']+release['newArticles']
files=[grade.subject.file_for(p) for p in paths]+[grade.ROOT/p for p in ['sitemap.xml','rss.xml','llms.txt']]
before={str(p.relative_to(grade.ROOT)):grade.base.sha(p) for p in files}
grade.subject.update_from_manifest()
changed=[p for p,value in before.items() if grade.base.sha(grade.ROOT/p)!=value]
result={'result':'FAIL' if changed else 'PASS','checkedFiles':len(files),'changedCount':len(changed),'changed':changed}
grade.base.save(grade.ROOT/'reports/grade-pages-repeatability.json',result)
print(json.dumps({**result,'changed':changed[:5]},ensure_ascii=False,indent=2))
assert not changed
