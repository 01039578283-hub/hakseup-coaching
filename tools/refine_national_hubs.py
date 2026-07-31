from __future__ import annotations

import argparse
import html
import json
import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
NATIONAL_ROOT = ROOT / "전국학원"
JSON_RE = re.compile(
    r'(<script\s+type=["\']application/ld\+json["\'][^>]*>)(.*?)(</script>)',
    re.I | re.S,
)


def depth(path: Path) -> int:
    return len(path.relative_to(NATIONAL_ROOT).parts) - 1


def join_names(names: list[str], limit: int = 4) -> str:
    selected = names[:limit]
    if not selected:
        return ""
    text = "·".join(selected)
    return text + (" 등" if len(names) > limit else "")


def hub_description(path: Path) -> str:
    level = depth(path)
    if level == 0:
        return (
            "13개 광역지역과 76개 시군구, 371개 동네 학원 안내를 연결했습니다. "
            "센터 위치와 수강 가능 학년, 학교 참고 정보, 영어·수학 학습관리 기준을 지역별로 확인하세요."
        )

    parts = path.relative_to(NATIONAL_ROOT).parts[:-1]
    if level == 1:
        region = parts[0]
        districts = sorted(
            child.name
            for child in path.parent.iterdir()
            if child.is_dir() and (child / "index.html").is_file()
        )
        neighborhoods = sum(
            1
            for candidate in path.parent.glob("*/*/index.html")
            if len(candidate.parent.relative_to(path.parent).parts) == 2
        )
        return (
            f"{region} 학원 안내를 {join_names(districts, 3)} {len(districts)}개 시군구와 "
            f"{neighborhoods}개 동네로 정리했습니다. 센터 위치, 수강 가능 학년과 학교 참고 정보를 확인하세요."
        )

    region, district = parts[:2]
    neighborhoods = sorted(
        child.name
        for child in path.parent.iterdir()
        if child.is_dir() and (child / "index.html").is_file()
    )
    return (
        f"{region} {district} 학원 안내를 {join_names(neighborhoods)} "
        f"{len(neighborhoods)}개 동네로 정리했습니다. 영어·수학 수강 범위와 센터 위치, "
        "학교 참고 정보 및 상담 준비사항을 확인하세요."
    )


def replace_meta(source: str, key: str, value: str, property_meta: bool = False) -> str:
    attribute = "property" if property_meta else "name"
    escaped = html.escape(value, quote=True)
    pattern = re.compile(
        rf'(<meta\s+[^>]*{attribute}=["\']{re.escape(key)}["\'][^>]*content=["\'])(.*?)(["\'][^>]*>)',
        re.I | re.S,
    )
    return pattern.sub(rf"\g<1>{escaped}\g<3>", source, count=1)


def types_of(node: dict[str, Any]) -> set[str]:
    value = node.get("@type")
    if isinstance(value, list):
        return {str(item) for item in value}
    return {str(value)} if value else set()


def update_json_descriptions(source: str, description: str) -> str:
    def replace(match: re.Match[str]) -> str:
        try:
            data = json.loads(match.group(2))
        except json.JSONDecodeError:
            return match.group(0)
        nodes = data.get("@graph") if isinstance(data, dict) else None
        graph = nodes if isinstance(nodes, list) else [data] if isinstance(data, dict) else []
        changed = False
        for node in graph:
            if isinstance(node, dict) and "CollectionPage" in types_of(node):
                if node.get("description") != description:
                    node["description"] = description
                    changed = True
        if not changed:
            return match.group(0)
        return (
            match.group(1)
            + json.dumps(data, ensure_ascii=False, separators=(",", ":"))
            + match.group(3)
        )

    return JSON_RE.sub(replace, source)


LABEL_REPLACEMENTS = {
    ">academy hub<": ">전국 학원 안내<",
    ">regional academy hub<": ">광역지역 학원 안내<",
    ">city academy hub<": ">시군구 학원 안내<",
    ">local check point<": ">지역 상담 기준<",
    ">learning guide<": ">학습 가이드<",
    ">consultation<": ">상담 안내<",
    ">LEARNING COACHING DIFFERENCE<": ">학습관리 방식<",
}


def transform(path: Path, source: str) -> str:
    description = hub_description(path)
    updated = replace_meta(source, "description", description)
    updated = replace_meta(updated, "og:description", description, property_meta=True)
    updated = update_json_descriptions(updated, description)
    for old, new in LABEL_REPLACEMENTS.items():
        updated = updated.replace(old, new)
    return updated


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()

    pages = [
        path
        for path in sorted(NATIONAL_ROOT.rglob("index.html"))
        if depth(path) <= 2
    ]
    if len(pages) != 90:
        raise SystemExit(f"expected 90 hubs, found {len(pages)}")

    changed = 0
    descriptions: set[str] = set()
    for path in pages:
        source = path.read_text(encoding="utf-8")
        description = hub_description(path)
        descriptions.add(description)
        updated = transform(path, source)
        if updated != source:
            changed += 1
            if args.write:
                path.write_text(updated, encoding="utf-8", newline="\n")

    print("mode=" + ("WRITE" if args.write else "DRY-RUN"))
    print(f"pages={len(pages)}")
    print(f"changed={changed}")
    print(f"unique_descriptions={len(descriptions)}")


if __name__ == "__main__":
    main()
