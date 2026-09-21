"""Read-only manuscript workbook inspection. Never execute supplied HTML."""
import json
import re
import difflib
from pathlib import Path
from collections import Counter
import openpyxl
from lxml import html

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(r'C:\Users\1992k\Desktop\홈페이지 정리\참고자료\원고모음(엑셀)')


def clean(value):
    return ' '.join(value.split())


def rows(sheet):
    return [(i + 1, str(row[0])) for i, row in enumerate(sheet.iter_rows(values_only=True))
            if row and row[0] and '<h1' in str(row[0])]


def main():
    for subject in ['영어', '수학']:
        book = openpyxl.load_workbook(SOURCE / (subject + '학원 원고.xlsx'), read_only=True, data_only=True)
        primary = rows(book['A열_텍스트파일'])
        alternate = rows(book['Sheet1'])
        normalized = lambda value: clean(html.fromstring(value.replace('_x000D_', '\r')).text_content())
        print(subject, 'normalized sheet matches', sum(normalized(a) == normalized(b)
                                                     for (_, a), (_, b) in zip(primary, alternate)))
        semantic = lambda value: re.sub(r'[\W_]+', '', normalized(value))
        mismatch = [(row,a,b) for (row,a),(_,b) in zip(primary,alternate) if semantic(a)!=semantic(b)]
        for row,a,b in mismatch:
            x,y=semantic(a),semantic(b)
            diff=difflib.SequenceMatcher(None,x,y,autojunk=False)
            changes=[{'export':x[max(0,i-25):j+25], 'original':y[max(0,k-25):l+25]}
                     for tag,i,j,k,l in diff.get_opcodes() if tag!='equal']
            print(json.dumps({'subject':subject,'row':row,'changes':changes},ensure_ascii=False))
        print('SEMANTIC DIFFERING ROWS',[row for row,_,_ in mismatch])
        book.close()


if __name__ == '__main__':
    main()
