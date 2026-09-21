"""Verify the image-position-only release against a supplied Git baseline."""
import argparse
import json
import subprocess
from lxml import html
import build_grade_pages as grade


def comparable(raw, move=False):
    doc = html.fromstring(raw)
    media = doc.xpath('//*[@id="center-images"]')[0]
    article = doc.xpath('//article[@class="hs-article hg-article"]')[0]
    if move:
        media.getparent().remove(media)
        article.addprevious(media)
    script, graph = grade.subject.graph_of(doc)
    # These arrays describe the same sections in the new visual order.
    # Preserve and compare all values; only their ordering may change.
    for item in graph:
        for key in ['hasPart', 'articleSection']:
            if key in item:
                item[key] = sorted(item[key], key=lambda x: json.dumps(x, sort_keys=True, ensure_ascii=False))
    script.text = json.dumps(graph, sort_keys=True, ensure_ascii=False)
    return html.tostring(doc, encoding='utf-8', method='html')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--baseline', required=True)
    args = parser.parse_args()
    baseline = subprocess.check_output(['git', 'rev-parse', args.baseline], cwd=grade.ROOT, text=True).strip()
    records = grade.READ(grade.DATA / 'manifest.json')['records']
    errors = []
    proc = subprocess.Popen(['git', 'cat-file', '--batch'], cwd=grade.ROOT, stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    try:
        for i, record in enumerate(records, 1):
            file = grade.subject.file_for(record['path'])
            relative = file.relative_to(grade.ROOT).as_posix()
            proc.stdin.write((baseline + ':' + relative + '\n').encode('utf-8'))
            proc.stdin.flush()
            header = proc.stdout.readline().decode('utf-8').split()
            if len(header) != 3 or header[1] != 'blob':
                raise RuntimeError('Missing baseline page: ' + relative)
            raw = proc.stdout.read(int(header[2]))
            assert proc.stdout.read(1) == b'\n'
            if comparable(raw, move=True) != comparable(file.read_bytes()):
                errors.append(record['path'])
            if i % 1000 == 0:
                print(json.dumps({'compared': i, 'unexpectedChanges': len(errors)}), flush=True)
    finally:
        proc.stdin.close()
        proc.stdout.close()
        proc.wait()
    report = {'baseline': baseline, 'gradePages': len(records), 'unexpectedPageChanges': errors,
              'allowedChanges': ['Move center-images before GRADE LEARNING', 'Reorder corresponding schema section arrays'],
              'status': 'PASS' if not errors else 'FAIL'}
    grade.base.save(grade.ROOT / 'reports/grade-media-placement.json', report)
    print(json.dumps(report, ensure_ascii=False))
    if errors:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
