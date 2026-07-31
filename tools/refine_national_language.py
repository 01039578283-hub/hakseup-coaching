from __future__ import annotations

import argparse
import html
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
NATIONAL_ROOT = ROOT / "전국학원"


def target_pages() -> list[Path]:
    pages: list[Path] = []
    for path in NATIONAL_ROOT.rglob("index.html"):
        depth = len(path.relative_to(NATIONAL_ROOT).parts) - 1
        if depth in {3, 4}:
            pages.append(path)
    return sorted(pages)


def replace_hero_description(source: str, title: str) -> tuple[str, int]:
    pattern = re.compile(
        r'(<section class="page-hero generated-page-hero">.*?<h1>.*?</h1>\s*)'
        r"<p>.*?</p>",
        re.S,
    )
    replacement = (
        r"\1"
        f"<p>{html.escape(title)}을 알아보는 학생과 학부모를 위해 "
        "학습 진단, 주간 계획, 오답 관리와 상담 기준을 정리했습니다.</p>"
    )
    return pattern.subn(replacement, source, count=1)


def transform(source: str) -> tuple[str, list[str]]:
    issues: list[str] = []
    title_match = re.search(r"<h1>(.*?)</h1>", source, re.S)
    if not title_match:
        return source, ["H1 없음"]
    title = re.sub(r"<[^>]+>", "", title_match.group(1)).strip()

    result = source
    result = result.replace(
        '<p class="eyebrow">local academy guide</p>',
        '<p class="eyebrow">지역 학원 안내</p>',
    )
    result = result.replace(
        '<p class="article-eyebrow">LOCAL ACADEMY GUIDE</p>',
        '<p class="article-eyebrow">지역별 학습 안내</p>',
    )
    result = result.replace(
        '<p class="generated-kicker">COACHING CHECK</p>',
        '<p class="generated-kicker">학습관리 확인</p>',
    )
    result = result.replace(
        '<p class="parent-faq-eyebrow">LEARNING COACHING DIFFERENCE</p>',
        '<p class="parent-faq-eyebrow">학습코칭 운영 방식</p>',
    )
    result = result.replace(
        '<p class="parent-faq-eyebrow">LOCAL STUDY LINKS</p>',
        '<p class="parent-faq-eyebrow">지역 학습 페이지</p>',
    )
    result, hero_count = replace_hero_description(result, title)
    if hero_count != 1:
        issues.append(f"상단 소개 문구 교체 수 오류: {hero_count}")

    # 생성 초기 문구에 남은 불필요한 띄어쓰기를 화면 제목에서만 바로잡는다.
    result = re.sub(
        r"(<h2>[^<]*?)\b(초등|중등|고등) 영수 학원(\s+상담[^<]*</h2>)",
        r"\1\2 영수학원\3",
        result,
    )
    return result, issues


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()

    pages = target_pages()
    failures: list[tuple[str, str]] = []
    changed = 0
    planned: list[tuple[Path, str]] = []
    for path in pages:
        source = path.read_text(encoding="utf-8")
        updated, issues = transform(source)
        if issues:
            failures.extend((str(path.relative_to(ROOT)), issue) for issue in issues)
        if updated != source:
            changed += 1
            planned.append((path, updated))

    if len(pages) != 1484:
        failures.append(("collection", f"예상 1,484페이지, 실제 {len(pages)}페이지"))
    if failures:
        print(f"failures={len(failures)}")
        for path, issue in failures[:20]:
            print(f"{path}: {issue}")
        return 1

    if args.write:
        for path, updated in planned:
            path.write_text(updated, encoding="utf-8", newline="\n")

    print(f"mode={'WRITE' if args.write else 'DRY-RUN'}")
    print(f"pages={len(pages)}")
    print(f"changed={changed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
