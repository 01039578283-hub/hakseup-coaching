from __future__ import annotations

import argparse
import html
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote


ROOT = Path(__file__).resolve().parents[1]
NATIONAL_ROOT = ROOT / "전국학원"
BASE_URL = "https://xn--ru4bi8s1tac0p.kr"
EXPECTED_HUB_COUNT = 90
JSON_RE = re.compile(
    r'(<script\b[^>]*type=["\']application/ld\+json["\'][^>]*>)(.*?)(</script>)',
    re.I | re.S,
)
URL_KEYS = {"@id", "url", "item", "contentUrl", "sameAs"}
LABEL_REPLACEMENTS = {
    ">academy hub<": ">전국 학원 안내<",
    ">regional academy hub<": ">광역지역 학원 안내<",
    ">city academy hub<": ">시군구 학원 안내<",
    ">local check point<": ">지역 상담 기준<",
    ">learning guide<": ">학습 가이드<",
    ">consultation<": ">상담 안내<",
    ">LEARNING COACHING DIFFERENCE<": ">학습관리 방식<",
    "틀린 문제를 점수로 연결하기 위해 원인을 나누고 반복 주기를 정합니다.":
        "틀린 문제의 원인을 나누고 다시 확인할 주기를 정합니다.",
}


@dataclass
class Plan:
    path: Path
    old_source: str
    new_source: str
    description: str
    issues: list[str]


def depth(path: Path) -> int:
    return len(path.relative_to(NATIONAL_ROOT).parts) - 1


def raw_parts(path: Path) -> tuple[str, ...]:
    return path.relative_to(NATIONAL_ROOT).parts[:-1]


def display_region(region: str) -> str:
    return "충청·세종" if region == "충청" else region


def display_district(region: str, district: str) -> str:
    return "세종특별자치시" if (region, district) == ("충청", "새롬중앙로") else district


def absolute_url(*parts: str) -> str:
    suffix = "/" + "/".join(part.strip("/") for part in parts if part) + "/"
    return BASE_URL + quote(suffix, safe="/")


def breadcrumb_items(path: Path) -> list[dict[str, str]]:
    parts = raw_parts(path)
    items = [{"name": "홈", "item": BASE_URL + "/", "href": "/"}]
    items.append(
        {
            "name": "전국학원",
            "item": absolute_url("전국학원"),
            "href": "/전국학원/",
        }
    )
    if parts:
        items.append(
            {
                "name": display_region(parts[0]),
                "item": absolute_url("전국학원", parts[0]),
                "href": f"/전국학원/{parts[0]}/",
            }
        )
    if len(parts) == 2:
        items.append(
            {
                "name": display_district(parts[0], parts[1]),
                "item": absolute_url("전국학원", parts[0], parts[1]),
                "href": f"/전국학원/{parts[0]}/{parts[1]}/",
            }
        )
    return items


def render_breadcrumb(path: Path) -> str:
    items = breadcrumb_items(path)
    rendered = [
        f'<a href="{html.escape(item["href"], quote=True)}">{html.escape(item["name"])}</a>'
        for item in items[:-1]
    ]
    rendered.append(html.escape(items[-1]["name"]))
    return '<div class="breadcrumb">' + " › ".join(rendered) + "</div>"


def hub_description(path: Path) -> str:
    parts = raw_parts(path)
    if not parts:
        return (
            "전국 13개 광역·76개 시군구·371개 동네의 영어·수학 학원, "
            "센터 위치, 학년·과목, 학교 참고 정보와 상담 기준을 안내합니다."
        )
    if len(parts) == 1:
        districts = [
            child for child in path.parent.iterdir()
            if child.is_dir() and (child / "index.html").is_file()
        ]
        neighborhoods = sum(
            1 for candidate in path.parent.glob("*/*/index.html")
            if len(candidate.parent.relative_to(path.parent).parts) == 2
        )
        value = (
            f"{display_region(parts[0])}의 {len(districts)}개 시군구·{neighborhoods}개 동네 학원과 "
            "영어·수학 학년 범위, 센터 위치, 학교 참고 정보와 상담 전 확인사항을 안내합니다."
        )
    else:
        region, district = parts
        neighborhoods = [
            child for child in path.parent.iterdir()
            if child.is_dir() and (child / "index.html").is_file()
        ]
        value = (
            f"{display_region(region)} {display_district(region, district)}의 "
            f"{len(neighborhoods)}개 동네 영어·수학 학원, 센터 위치, 학년·과목, "
            "학교 참고 정보와 학습 상담 기준을 안내합니다."
        )
        if len(value) > 80:
            value = (
                f"{display_region(region)} {display_district(region, district)} "
                f"{len(neighborhoods)}개 동네의 영어·수학 학원, 센터 위치와 "
                "학년·과목별 상담 기준을 안내합니다."
            )
    if not 55 <= len(value) <= 80:
        raise ValueError(f"허브 meta description 길이 오류({len(value)}): {path}")
    return value


def meta_content(source: str, kind: str, key: str) -> str:
    for match in re.finditer(r"<meta\b[^>]*>", source, re.I | re.S):
        attrs = {
            name.lower(): html.unescape(value)
            for name, _, value in re.findall(
                r'([:\w-]+)\s*=\s*(["\'])(.*?)\2', match.group(0), re.I | re.S
            )
        }
        if attrs.get(kind.lower(), "").lower() == key.lower():
            return attrs.get("content", "")
    return ""


def replace_meta(source: str, kind: str, key: str, value: str) -> tuple[str, bool]:
    escaped = html.escape(value, quote=True)
    pattern = re.compile(
        rf'(<meta\b(?=[^>]*\b{re.escape(kind)}=["\']{re.escape(key)}["\'])'
        rf'[^>]*\bcontent=["\'])(.*?)(["\'][^>]*>)',
        re.I | re.S,
    )
    updated, count = pattern.subn(
        lambda match: match.group(1) + escaped + match.group(3), source, count=1
    )
    return updated, bool(count)


def canonical_url(source: str) -> str:
    match = re.search(
        r'<link\b[^>]*rel=["\']canonical["\'][^>]*href=["\']([^"\']+)', source, re.I | re.S
    )
    return html.unescape(match.group(1)) if match else ""


def href_values(source: str) -> tuple[str, ...]:
    return tuple(
        html.unescape(value)
        for value in re.findall(r'<a\b[^>]*href=["\']([^"\']+)', source, re.I | re.S)
    )


def types_of(node: dict[str, Any]) -> set[str]:
    value = node.get("@type")
    return {str(item) for item in value} if isinstance(value, list) else {str(value)} if value else set()


def graph_nodes(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, dict) and isinstance(data.get("@graph"), list):
        return [node for node in data["@graph"] if isinstance(node, dict)]
    return [data] if isinstance(data, dict) else []


def json_url_values(source: str) -> tuple[tuple[str, str], ...]:
    result: list[tuple[str, str]] = []

    def walk(value: Any, parent_key: str = "") -> None:
        if parent_key in URL_KEYS and isinstance(value, str):
            result.append((parent_key, value))
        elif isinstance(value, list):
            for item in value:
                walk(item, parent_key)
        elif isinstance(value, dict):
            for key, item in value.items():
                walk(item, key)

    for match in JSON_RE.finditer(source):
        try:
            walk(json.loads(match.group(2)))
        except json.JSONDecodeError:
            result.append(("parse-error", match.group(2)))
    return tuple(result)


def semantic_terms(path: Path) -> dict[str, str]:
    parts = raw_parts(path)
    if not parts:
        return {
            "충청·세종": "충청·세종",
            "새롬중앙로": "세종특별자치시",
            "충청": "충청·세종",
        }
    if parts[0] != "충청":
        return {}
    return {
        "충청·세종": "충청·세종",
        "충청 새롬중앙로": "충청·세종 세종특별자치시",
        "새롬중앙로 안의": "세종특별자치시의",
        "새롬중앙로는": "세종특별자치시는",
        "충청에는": "충청·세종 권역에는",
        "충청권": "충청·세종 권역",
        "새롬중앙로": "세종특별자치시",
        "충청": "충청·세종",
    }


def replace_terms(value: str, terms: dict[str, str]) -> str:
    if not terms:
        return value
    pattern = re.compile("|".join(re.escape(term) for term in sorted(terms, key=len, reverse=True)))
    return pattern.sub(lambda match: terms[match.group(0)], value)


def replace_visible_text(source: str, terms: dict[str, str]) -> str:
    protected = re.compile(r"<(?:script|style)\b.*?</(?:script|style)>|<[^>]+>", re.I | re.S)
    result: list[str] = []
    cursor = 0
    for match in protected.finditer(source):
        result.append(replace_terms(source[cursor:match.start()], terms))
        result.append(match.group(0))
        cursor = match.end()
    result.append(replace_terms(source[cursor:], terms))
    return "".join(result)


def replace_text_attributes(source: str, terms: dict[str, str]) -> str:
    pattern = re.compile(r'((?:alt|title|aria-label)=["\'])(.*?)(["\'])', re.I | re.S)
    return pattern.sub(
        lambda match: match.group(1) + replace_terms(match.group(2), terms) + match.group(3), source
    )


def semantic_walk(value: Any, terms: dict[str, str], parent_key: str = "") -> Any:
    if parent_key in URL_KEYS:
        return value
    if isinstance(value, str):
        return replace_terms(value, terms)
    if isinstance(value, list):
        return [semantic_walk(item, terms, parent_key) for item in value]
    if isinstance(value, dict):
        return {key: semantic_walk(item, terms, key) for key, item in value.items()}
    return value


def update_jsonld(source: str, path: Path, description: str) -> tuple[str, list[str]]:
    errors: list[str] = []
    terms = semantic_terms(path)
    crumbs = breadcrumb_items(path)
    parts = raw_parts(path)

    def replace(match: re.Match[str]) -> str:
        try:
            data = json.loads(match.group(2))
        except json.JSONDecodeError as exc:
            errors.append(f"JSON-LD parse: {exc}")
            return match.group(0)
        data = semantic_walk(data, terms)
        for node in graph_nodes(data):
            types = types_of(node)
            if "CollectionPage" in types:
                node["description"] = description
            if "BreadcrumbList" in types:
                node["itemListElement"] = [
                    {"@type": "ListItem", "position": position, "name": item["name"], "item": item["item"]}
                    for position, item in enumerate(crumbs, start=1)
                ]
            if "ItemList" in types and parts == ("충청",):
                for item in node.get("itemListElement", []):
                    if isinstance(item, dict) and item.get("name") == "세종특별자치시":
                        item["name"] = "세종특별자치시 학원"
        return match.group(1) + json.dumps(data, ensure_ascii=False, separators=(",", ":")) + match.group(3)

    return JSON_RE.sub(replace, source), errors


def transform(path: Path, source: str) -> Plan:
    issues: list[str] = []
    description = hub_description(path)
    terms = semantic_terms(path)
    baseline = (
        canonical_url(source),
        meta_content(source, "property", "og:url"),
        href_values(source),
        json_url_values(source),
    )
    updated, found = replace_meta(source, "name", "description", description)
    if not found:
        issues.append("meta description 없음")
    updated, found = replace_meta(updated, "property", "og:description", description)
    if not found:
        issues.append("og:description 없음")
    for property_name in ("og:title", "og:image:alt"):
        current = meta_content(updated, "property", property_name)
        if current:
            updated, _ = replace_meta(updated, "property", property_name, replace_terms(current, terms))
    updated = replace_visible_text(updated, terms)
    updated = replace_text_attributes(updated, terms)
    for old, new in LABEL_REPLACEMENTS.items():
        updated = updated.replace(old, new)
    if raw_parts(path) == ("충청",):
        updated = re.sub(
            r'(<a\b[^>]*class=["\'][^"\']*\bhub-card\b[^"\']*["\'][^>]*href=["\']새롬중앙로/["\'][^>]*>.*?<strong>).*?(</strong>)',
            r"\1세종특별자치시 학원\2", updated, count=1, flags=re.I | re.S,
        )
    updated = re.sub(
        r'<div\b[^>]*class=["\'][^"\']*\bbreadcrumb\b[^"\']*["\'][^>]*>.*?</div>',
        render_breadcrumb(path), updated, count=1, flags=re.I | re.S,
    )
    updated, json_errors = update_jsonld(updated, path, description)
    issues.extend(json_errors)
    after = (
        canonical_url(updated),
        meta_content(updated, "property", "og:url"),
        href_values(updated),
        json_url_values(updated),
    )
    if after != baseline:
        issues.append("canonical/og:url/href/JSON URL manifest 변경")
    return Plan(path, source, updated, description, issues)


def visible_breadcrumb(source: str) -> list[str]:
    match = re.search(
        r'<div\b[^>]*class=["\'][^"\']*\bbreadcrumb\b[^"\']*["\'][^>]*>(.*?)</div>',
        source, re.I | re.S,
    )
    if not match:
        return []
    text = html.unescape(re.sub(r"<[^>]+>", "", match.group(1)))
    return [part.strip() for part in text.split("›") if part.strip()]


def visible_text(source: str) -> str:
    value = re.sub(r"<(?:script|style)\b.*?</(?:script|style)>", " ", source, flags=re.I | re.S)
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", value))).strip()


def semantic_json_text(source: str) -> str:
    values: list[str] = []

    def walk(value: Any, parent_key: str = "") -> None:
        if parent_key in URL_KEYS:
            return
        if isinstance(value, str):
            values.append(value)
        elif isinstance(value, list):
            for item in value:
                walk(item, parent_key)
        elif isinstance(value, dict):
            for key, item in value.items():
                walk(item, key)

    for match in JSON_RE.finditer(source):
        try:
            walk(json.loads(match.group(2)))
        except json.JSONDecodeError:
            values.append("JSON_PARSE_ERROR")
    return " ".join(values)


def validate(plans: list[Plan]) -> list[str]:
    errors: list[str] = []
    descriptions: list[str] = []
    for plan in plans:
        source = plan.new_source
        rel = plan.path.relative_to(ROOT).as_posix()
        parts = raw_parts(plan.path)
        descriptions.append(plan.description)
        errors.extend(f"{rel}: {issue}" for issue in plan.issues)
        if meta_content(source, "name", "description") != plan.description:
            errors.append(f"{rel}: meta description 불일치")
        if meta_content(source, "property", "og:description") != plan.description:
            errors.append(f"{rel}: og:description 불일치")
        expected_crumbs = [item["name"] for item in breadcrumb_items(plan.path)]
        if visible_breadcrumb(source) != expected_crumbs:
            errors.append(f"{rel}: visible breadcrumb 전체 계층 불일치")
        schema_crumbs: list[str] = []
        collection_description = ""
        item_names: list[str] = []
        for match in JSON_RE.finditer(source):
            try:
                data = json.loads(match.group(2))
            except json.JSONDecodeError:
                continue
            for node in graph_nodes(data):
                types = types_of(node)
                if "BreadcrumbList" in types:
                    schema_crumbs = [str(item.get("name", "")) for item in node.get("itemListElement", []) if isinstance(item, dict)]
                if "CollectionPage" in types:
                    collection_description = str(node.get("description", ""))
                if "ItemList" in types:
                    item_names = [str(item.get("name", "")) for item in node.get("itemListElement", []) if isinstance(item, dict)]
        if schema_crumbs != expected_crumbs:
            errors.append(f"{rel}: JSON BreadcrumbList 전체 계층 불일치")
        if collection_description != plan.description:
            errors.append(f"{rel}: CollectionPage description 불일치")
        if not parts or parts[0] == "충청":
            visible = visible_text(source)
            semantic = semantic_json_text(source)
            if "새롬중앙로" in visible or "새롬중앙로" in semantic:
                errors.append(f"{rel}: authored 지리명 새롬중앙로 잔존")
            if "세종시" in visible or "세종시" in semantic:
                errors.append(f"{rel}: 부정확한 세종시 표기 잔존")
        if parts == ("충청",):
            h1 = re.search(r"<h1\b[^>]*>(.*?)</h1>", source, re.I | re.S)
            if not h1 or "충청·세종" not in html.unescape(re.sub(r"<[^>]+>", "", h1.group(1))):
                errors.append(f"{rel}: 충청·세종 H1 표시 없음")
            if "세종특별자치시 학원" not in item_names:
                errors.append(f"{rel}: 세종 child ItemList 표시명 오류")
            card = re.search(
                r'<a\b[^>]*class=["\'][^"\']*\bhub-card\b[^"\']*["\'][^>]*href=["\']새롬중앙로/["\'][^>]*>.*?<strong>(.*?)</strong>',
                source, re.I | re.S,
            )
            if not card or re.sub(r"<[^>]+>", "", card.group(1)).strip() != "세종특별자치시 학원":
                errors.append(f"{rel}: 세종 child hub-card 표시명 오류")
        if parts == ("충청", "새롬중앙로"):
            h1 = re.search(r"<h1\b[^>]*>(.*?)</h1>", source, re.I | re.S)
            if not h1 or "세종특별자치시" not in html.unescape(re.sub(r"<[^>]+>", "", h1.group(1))):
                errors.append(f"{rel}: 세종특별자치시 H1 표시 없음")
    if len(plans) != EXPECTED_HUB_COUNT:
        errors.append(f"collection: hubs {len(plans)}/{EXPECTED_HUB_COUNT}")
    if len(set(descriptions)) != len(plans):
        errors.append(f"collection: unique descriptions {len(set(descriptions))}/{len(plans)}")
    lengths = [len(value) for value in descriptions]
    if not lengths or min(lengths) < 55 or max(lengths) > 80:
        errors.append(f"collection: description lengths {min(lengths, default=0)}~{max(lengths, default=0)}")
    return errors


def atomic_write(path: Path, value: str) -> None:
    temporary = path.with_name(path.name + ".hub.tmp")
    temporary.write_text(value, encoding="utf-8", newline="\n")
    temporary.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    pages = [path for path in sorted(NATIONAL_ROOT.rglob("index.html")) if depth(path) <= 2]
    plans = [transform(path, path.read_text(encoding="utf-8")) for path in pages]
    errors = validate(plans)
    descriptions = [plan.description for plan in plans]
    lengths = [len(value) for value in descriptions]
    print("mode=" + ("WRITE" if args.write else "DRY-RUN"))
    print(f"pages={len(plans)}")
    print(f"changed={sum(plan.old_source != plan.new_source for plan in plans)}")
    print(f"unique_descriptions={len(set(descriptions))}/{len(plans)}")
    print(f"description_length={min(lengths, default=0)}~{max(lengths, default=0)}")
    print("url_manifest_changes=0" if not any("manifest" in error for error in errors) else "url_manifest_changes=ERROR")
    print(f"errors={len(errors)}")
    for error in errors[:80]:
        print("ERROR " + error)
    if errors:
        return 1
    if args.write:
        for plan in plans:
            if plan.old_source != plan.new_source:
                atomic_write(plan.path, plan.new_source)
        print(f"written={sum(plan.old_source != plan.new_source for plan in plans)}")
    else:
        print("dry-run 완료: 파일을 수정하지 않았습니다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
