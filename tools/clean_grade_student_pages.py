from __future__ import annotations

"""Clean editorial residue in the three student-grade locality page families.

The existing pages already have strong locality-specific variation, so this tool
does not regenerate them.  It removes manuscript/review wording, reduces forced
secondary-keyword repetition, and replaces legacy mixed-level school sentences
with the source-verified school list already embedded in each page.
"""

import argparse
import json
import re
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TODAY = date.today().isoformat()
CATEGORIES = {
    "초등학생학원": ("초등학교", "elementary"),
    "중학생학원": ("중학교", "middle"),
    "고등학생학원": ("고등학교", "high"),
}
JSON_RE = re.compile(
    r'(<script\b[^>]*type=["\']application/ld\+json["\'][^>]*>)(.*?)(</script>)',
    re.I | re.S,
)
H1_RE = re.compile(r"<h1\b[^>]*>(.*?)</h1>", re.I | re.S)
SCHOOL_BLOCK_RE = re.compile(
    r"<!-- school-reference:start -->.*?<!-- school-reference:end -->",
    re.S,
)


def _extract_locality(source: str, category: str) -> str:
    match = H1_RE.search(source)
    if not match:
        raise ValueError("H1이 없습니다")
    heading = re.sub(r"<[^>]+>", "", match.group(1)).strip()
    suffix = f" {category}"
    if not heading.endswith(suffix):
        raise ValueError(f"H1 유형 오류: {heading}")
    return heading[: -len(suffix)].strip()


def _verified_schools(source: str, level: str) -> tuple[str, ...]:
    block_match = SCHOOL_BLOCK_RE.search(source)
    if not block_match:
        raise ValueError("source-verified school block이 없습니다")
    block = block_match.group(0)
    if f'data-school-level="{level}"' not in block:
        raise ValueError(f"학교 학제 블록이 없습니다: {level}")
    return tuple(dict.fromkeys(re.findall(r'data-source-school="([^"]+)"', block)))


def _extract_secondary_keyword(source: str, category: str) -> str:
    patterns = {
        "초등학생학원": (
            r"<h2>([^<]{2,28}) 관련 질문을 구체적으로 바꾸는 방법</h2>",
            r"<summary><span>Q</span>([^<]{2,28})은? [^<]*상담",
        ),
        "중학생학원": (
            r"<h2>‘([^’]{2,28})’ 검색 의도에 답하는",
            r"<h2>[^<]*과 ‘([^’]{2,28})’: 무엇을 비교할까</h2>",
            r"<h2>[^<]*‘([^’]{2,28})’[^<]*</h2>",
        ),
        "고등학생학원": (
            r"<h2>([^<]{2,28}) 상담에서 바로 물어볼 세 가지</h2>",
            r"<summary><span>Q</span>[^<]*에서 ([가-힣A-Za-z0-9]{2,28})(?:은|는) 상담",
        ),
    }
    for pattern in patterns[category]:
        match = re.search(pattern, source)
        if match:
            return match.group(1).strip(" ‘’.:—")
    return ""


def _soften_secondary_keyword(source: str, keyword: str) -> str:
    if not keyword:
        return source
    quoted = f"‘{keyword}’"
    replacements = (
        (f"{quoted} 조건까지 함께 고려하면", "관련 운영 조건까지 함께 고려하면"),
        (f"{keyword} 조건까지 함께 고려하면", "관련 운영 조건까지 함께 고려하면"),
        (f"{quoted} 관련 검색에서는", f"{keyword}를 알아볼 때는"),
        (f"{quoted} 관련 상담 질문", "관련 상담 질문"),
        (f"{quoted} 설명", "관련 설명"),
        (f"{quoted} 항목", "해당 항목"),
        (f"{quoted} 조건", "해당 조건"),
        (f"{keyword} 관련 검색에서는", f"{keyword}를 알아볼 때는"),
        (f"{keyword} 관련 상담 질문", "관련 상담 질문"),
        (f"{keyword} 항목", "해당 항목"),
    )
    for before, after in replacements:
        source = source.replace(before, after)
    return source


def _replace_legacy_school_sentence(
    source: str,
    locality: str,
    level_label: str,
    names: tuple[str, ...],
) -> str:
    if names:
        replacement = (
            f"원자료에서 확인되는 {level_label} 실제 수업 가능 학교는 "
            f"{'·'.join(names)}입니다."
        )
    else:
        replacement = (
            f"원자료에는 {level_label} 실제 수업 가능 학교명이 별도로 기재되어 있지 않습니다."
        )
    escaped = re.escape(locality)
    patterns = (
        rf"제공 자료상 {escaped} 수업학교로 확인되는 명칭은 [^.<]{{1,220}}?등입니다\.",
        rf"제공 자료에는 {escaped} 수업학교로 [^.<]{{1,220}}?등이 기재되어 있습니다\.",
    )
    for pattern in patterns:
        source = re.sub(pattern, replacement, source)
    return source


def _update_jsonld_dates(source: str) -> str:
    def replace(match: re.Match[str]) -> str:
        payload = json.loads(match.group(2))
        graph = payload.get("@graph", [])
        for node in graph:
            if "dateModified" in node:
                node["dateModified"] = TODAY
        packed = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        return match.group(1) + packed + match.group(3)

    updated, count = JSON_RE.subn(replace, source, count=1)
    if count != 1:
        raise ValueError(f"JSON-LD 개수 오류: {count}")
    return updated


def clean_page(source: str, category: str) -> tuple[str, dict[str, object]]:
    level_label, level = CATEGORIES[category]
    locality = _extract_locality(source, category)
    names = _verified_schools(source, level)
    keyword = _extract_secondary_keyword(source, category)

    cleaned = source
    replacements = (
        ("원고에 정리된 상담 질문과 답변을 그대로 확인하세요.", "상담 전에 확인할 질문과 답변을 정리했습니다."),
        (f"{locality} {category} 원고에서 가정한 사례는", f"{locality} {category} 상담 준비 사례는"),
        ("원고에서 가정한 사례는", "상담 준비 사례는"),
        ("원고에서 가정한", "상담 준비를 위해 구성한"),
        ("제공된 수업학교 명칭만", "확인된 실제 수업 가능 학교명만"),
        ("PARENT CONSULTATION CASE", "CONSULTATION CHECK EXAMPLE"),
        ("상담 사례 메모", "상담 준비 예시"),
        ("후기 예시 1.", "상담 메모 예시 1."),
        ("후기 예시 2.", "상담 메모 예시 2."),
        ("실제 수강생 후기 인용이 아닙니다", "실제 수강생의 발언을 인용한 것이 아닙니다"),
    )
    for before, after in replacements:
        cleaned = cleaned.replace(before, after)
    cleaned = _soften_secondary_keyword(cleaned, keyword)
    cleaned = _replace_legacy_school_sentence(cleaned, locality, level_label, names)
    cleaned = _update_jsonld_dates(cleaned)
    return cleaned, {
        "locality": locality,
        "keyword": keyword,
        "schools": len(names),
        "changed": cleaned != source,
    }


def build_plan(root: Path) -> tuple[dict[Path, str], dict[str, object]]:
    outputs: dict[Path, str] = {}
    category_stats: dict[str, dict[str, int]] = {}
    for category in CATEGORIES:
        paths = sorted((root / "과목별학원" / category).glob("*/index.html"))
        if len(paths) != 371:
            raise ValueError(f"{category} 페이지 수 오류: {len(paths)}")
        changed = 0
        keywords = 0
        for path in paths:
            source = path.read_text(encoding="utf-8")
            cleaned, info = clean_page(source, category)
            outputs[path] = cleaned
            changed += int(bool(info["changed"]))
            keywords += int(bool(info["keyword"]))
        category_stats[category] = {"pages": len(paths), "changed": changed, "keywords": keywords}

    projected = list(outputs.values())
    forbidden = (
        "원고에 정리된 상담 질문과 답변을 그대로 확인하세요.",
        "원고에서 가정한 사례는",
        "PARENT CONSULTATION CASE",
        "후기 예시 1.",
        "후기 예시 2.",
    )
    residue = {token: sum(text.count(token) for text in projected) for token in forbidden}
    if any(residue.values()):
        raise ValueError(f"편집 흔적 잔존: {residue}")
    return outputs, {"categories": category_stats, "residue": residue}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    root = args.root.resolve()
    outputs, diagnostics = build_plan(root)
    if args.apply:
        for path, source in outputs.items():
            path.write_text(source, encoding="utf-8", newline="\n")
    print(json.dumps({**diagnostics, "written": args.apply}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
