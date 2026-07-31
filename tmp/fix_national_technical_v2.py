from __future__ import annotations

"""
학습코칭.kr 전국학원 기술 SEO 보강 스크립트.

기본 실행은 DRY-RUN이며 파일을 쓰지 않는다.

미리보기:
    python tmp/fix_national_technical_v2.py

실제 적용:
    python tmp/fix_national_technical_v2.py --apply

Vercel의 /index.html 정규 URL 리디렉션도 함께 적용:
    python tmp/fix_national_technical_v2.py --apply --patch-vercel-index-redirects

LocalBusiness는 기본값에서 절대 변경하지 않는다. 실제 지점으로 확인된 URL 목록이
준비된 경우에만 아래처럼 명시적으로 보수적 변환을 요청할 수 있다.

    python tmp/fix_national_technical_v2.py \
        --local-business-mode verified-only \
        --verified-centers tmp/verified_centers.txt \
        --acknowledge-local-business-downgrade \
        --apply

verified_centers.txt는 한 줄에 URL 하나를 적는다. URL 끝에 '*'를 붙이면 해당
URL 이하의 자식페이지까지 실제 지점 페이지로 인정한다.
"""

import argparse
import html
import json
import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import quote, unquote, urljoin, urlsplit, urlunsplit


ROOT = Path(__file__).resolve().parents[1]
NATIONAL_ROOT = ROOT / "전국학원"
SITEMAP_PATH = ROOT / "sitemap.xml"
VERCEL_PATH = ROOT / "vercel.json"

BASE_URL = "https://xn--ru4bi8s1tac0p.kr"
NATIONAL_URL = BASE_URL + "/" + quote("전국학원") + "/"
DEFAULT_OG_IMAGE = BASE_URL + "/assets/generated/academy-hero-v2.png"

EXPECTED_TOTAL = 1574
EXPECTED_HUBS = 90

H1_RE = re.compile(
    r"(<h1\b[^>]*>)(.*?)(</h1>)",
    re.IGNORECASE | re.DOTALL,
)
BREADCRUMB_RE = re.compile(
    r'(<div\b[^>]*\bclass=(["\'])[^"\']*\bbreadcrumb\b[^"\']*\2[^>]*>)(.*?)(</div>)',
    re.IGNORECASE | re.DOTALL,
)
JSON_LD_RE = re.compile(
    r'(<script\b[^>]*\btype=(["\'])application/ld\+json\2[^>]*>)(.*?)(</script>)',
    re.IGNORECASE | re.DOTALL,
)
CANONICAL_RE = re.compile(
    r'<link\b[^>]*\brel=(["\'])canonical\1[^>]*\bhref=(["\'])(.*?)\2[^>]*>',
    re.IGNORECASE | re.DOTALL,
)
OG_URL_RE = re.compile(
    r'<meta\b[^>]*\bproperty=(["\'])og:url\1[^>]*\bcontent=(["\'])(.*?)\2[^>]*>',
    re.IGNORECASE | re.DOTALL,
)
OG_IMAGE_RE = re.compile(
    r'<meta\b[^>]*\bproperty=(["\'])og:image\1[^>]*>',
    re.IGNORECASE | re.DOTALL,
)
OG_URL_TAG_RE = re.compile(
    r'(<meta\b[^>]*\bproperty=(["\'])og:url\2[^>]*>)',
    re.IGNORECASE | re.DOTALL,
)
HEAD_CLOSE_RE = re.compile(r"</head\s*>", re.IGNORECASE)
TAG_RE = re.compile(r"<[^>]+>")

SITEMAP_URL_RE = re.compile(
    r"(<url>\s*.*?<loc>(.*?)</loc>.*?</url>)",
    re.IGNORECASE | re.DOTALL,
)
LASTMOD_RE = re.compile(
    r"<lastmod>.*?</lastmod>",
    re.IGNORECASE | re.DOTALL,
)

# 실제 지점이 아닌 서비스 지역 페이지에서 제거하는 최소한의 business-specific 필드.
# EducationalOrganization 및 Service 노드는 유지하므로 페이지의 교육 안내 의미는 보존한다.
UNVERIFIED_BUSINESS_FIELDS = {
    "openingHours",
    "openingHoursSpecification",
    "aggregateRating",
    "review",
    "address",
}


@dataclass(frozen=True)
class Crumb:
    name: str
    url: str


@dataclass
class PageResult:
    path: Path
    canonical: str
    original: str
    updated: str
    depth: int
    changes: set[str] = field(default_factory=set)

    @property
    def changed(self) -> bool:
        return self.original != self.updated


def clean_text(value: str) -> str:
    return " ".join(html.unescape(TAG_RE.sub("", value)).split())


def normalize_url(value: str) -> str:
    """비교용 URL. 호스트는 소문자, 경로는 percent-encoding을 통일한다."""
    value = html.unescape(value.strip())
    parts = urlsplit(value)
    path = quote(unquote(parts.path), safe="/:@-._~")
    if path != "/" and not path.endswith("/"):
        path += "/"
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, "", ""))


def canonical_url(source: str, path: Path) -> str:
    match = CANONICAL_RE.search(source)
    if match:
        return normalize_url(match.group(3))

    match = OG_URL_RE.search(source)
    if match:
        return normalize_url(match.group(3))

    rel = path.relative_to(ROOT).as_posix()
    if rel == "index.html":
        route = "/"
    else:
        route = "/" + rel[: -len("index.html")]
    return normalize_url(BASE_URL + quote(route, safe="/"))


def page_depth(path: Path) -> int:
    """전국학원/index.html=0, 광역=1, 시군구=2, 동네=3, 자식=4."""
    return len(path.relative_to(NATIONAL_ROOT).parts) - 1


def page_h1(source: str) -> str:
    match = H1_RE.search(source)
    return clean_text(match.group(2)) if match else ""


def replace_first_h1(source: str, value: str) -> tuple[str, bool]:
    match = H1_RE.search(source)
    if not match:
        return source, False
    replacement = match.group(1) + html.escape(value) + match.group(3)
    if replacement == match.group(0):
        return source, False
    return source[: match.start()] + replacement + source[match.end() :], True


def district_name_counts(paths: Iterable[Path]) -> Counter[str]:
    return Counter(
        path.parent.name
        for path in paths
        if page_depth(path) == 2
    )


def qualify_duplicate_district_h1(
    source: str,
    path: Path,
    district_counts: Counter[str],
) -> tuple[str, bool]:
    if page_depth(path) != 2:
        return source, False

    district = path.parent.name
    if district_counts[district] < 2:
        return source, False

    region = path.parent.parent.name
    current = page_h1(source)
    if not current or current.startswith(f"{region} {district}"):
        return source, False

    if current.startswith(district):
        revised = f"{region} {current}"
    else:
        revised = f"{region} {district} {current}"
    return replace_first_h1(source, revised)


def breadcrumb_items(path: Path, source: str, canonical: str) -> list[Crumb]:
    """
    기존에 사용자가 요청한 짧은 상세페이지 브레드크럼을 보존한다.

    허브:
      홈 > 전국학원 > 광역 > 시군구
    동네/자식:
      홈 > 전국학원 > 현재 H1
    """
    depth = page_depth(path)
    crumbs = [
        Crumb("홈", BASE_URL + "/"),
        Crumb("전국학원", NATIONAL_URL),
    ]

    parts = path.relative_to(NATIONAL_ROOT).parts[:-1]
    if depth == 1:
        crumbs.append(Crumb(parts[0], canonical))
    elif depth == 2:
        region = parts[0]
        region_url = NATIONAL_URL + quote(region) + "/"
        crumbs.extend(
            [
                Crumb(region, region_url),
                Crumb(parts[1], canonical),
            ]
        )
    elif depth >= 3:
        current = page_h1(source)
        if not current:
            current = path.parent.name
        crumbs.append(Crumb(current, canonical))

    return crumbs


def visible_breadcrumb_html(crumbs: list[Crumb]) -> str:
    parts: list[str] = []
    for index, crumb in enumerate(crumbs):
        label = html.escape(crumb.name)
        if index == len(crumbs) - 1:
            parts.append(label)
        else:
            # 내부 링크는 사람이 읽기 쉬운 Unicode root-relative 경로를 쓴다.
            parsed = urlsplit(crumb.url)
            href = unquote(parsed.path or "/")
            parts.append(f'<a href="{html.escape(href, quote=True)}">{label}</a>')
    return " › ".join(parts)


def update_visible_breadcrumb(
    source: str,
    crumbs: list[Crumb],
) -> tuple[str, bool]:
    match = BREADCRUMB_RE.search(source)
    if not match:
        return source, False
    replacement = match.group(1) + visible_breadcrumb_html(crumbs) + match.group(4)
    if replacement == match.group(0):
        return source, False
    return source[: match.start()] + replacement + source[match.end() :], True


def graph_nodes(data: Any) -> list[dict[str, Any]]:
    if not isinstance(data, dict):
        return []
    graph = data.get("@graph")
    if isinstance(graph, list):
        return [node for node in graph if isinstance(node, dict)]
    return [data]


def node_has_type(node: dict[str, Any], wanted: str) -> bool:
    node_type = node.get("@type")
    if isinstance(node_type, str):
        return node_type == wanted
    if isinstance(node_type, list):
        return wanted in node_type
    return False


def remove_node_type(node: dict[str, Any], unwanted: str) -> None:
    node_type = node.get("@type")
    if isinstance(node_type, list):
        revised = [item for item in node_type if item != unwanted]
        if len(revised) == 1:
            node["@type"] = revised[0]
        elif revised:
            node["@type"] = revised
        else:
            node["@type"] = "Organization"
    elif node_type == unwanted:
        node["@type"] = "Organization"


def matches_verified_rule(url: str, rules: list[str]) -> bool:
    normalized = normalize_url(url)
    for rule in rules:
        if rule.endswith("*"):
            prefix = normalize_url(rule[:-1])
            if normalized.startswith(prefix):
                return True
        elif normalized == normalize_url(rule):
            return True
    return False


def update_json_ld(
    source: str,
    crumbs: list[Crumb],
    canonical: str,
    local_business_mode: str,
    verified_rules: list[str],
) -> tuple[str, set[str], int]:
    changes: set[str] = set()
    local_business_seen = 0
    encoded_crumbs = [
        {
            "@type": "ListItem",
            "position": position,
            "name": crumb.name,
            "item": normalize_url(crumb.url),
        }
        for position, crumb in enumerate(crumbs, start=1)
    ]

    def replace(match: re.Match[str]) -> str:
        nonlocal local_business_seen
        raw = match.group(3).strip()
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return match.group(0)

        script_changed = False
        for node in graph_nodes(data):
            if node_has_type(node, "BreadcrumbList"):
                if node.get("itemListElement") != encoded_crumbs:
                    node["itemListElement"] = encoded_crumbs
                    script_changed = True
                    changes.add("jsonld_breadcrumb")

            if node_has_type(node, "LocalBusiness"):
                local_business_seen += 1
                if (
                    local_business_mode == "verified-only"
                    and not matches_verified_rule(canonical, verified_rules)
                ):
                    remove_node_type(node, "LocalBusiness")
                    for key in UNVERIFIED_BUSINESS_FIELDS:
                        node.pop(key, None)
                    script_changed = True
                    changes.add("local_business_downgrade")

        if not script_changed:
            return match.group(0)
        encoded = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
        return match.group(1) + encoded + match.group(4)

    return JSON_LD_RE.sub(replace, source), changes, local_business_seen


def update_article_modified(source: str, modified_date: str) -> tuple[str, bool]:
    changed = False

    def replace(match: re.Match[str]) -> str:
        nonlocal changed
        raw = match.group(3).strip()
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return match.group(0)

        script_changed = False
        for node in graph_nodes(data):
            if node_has_type(node, "Article") and node.get("dateModified") != modified_date:
                node["dateModified"] = modified_date
                script_changed = True
                changed = True

        if not script_changed:
            return match.group(0)
        encoded = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
        return match.group(1) + encoded + match.group(4)

    return JSON_LD_RE.sub(replace, source), changed


def add_hub_og_image(source: str) -> tuple[str, bool]:
    if OG_IMAGE_RE.search(source):
        return source, False

    title_match = re.search(
        r"<title\b[^>]*>(.*?)</title>",
        source,
        re.IGNORECASE | re.DOTALL,
    )
    title = clean_text(title_match.group(1)) if title_match else "학습코칭 연구소"
    tags = (
        f'\n  <meta property="og:image" content="{DEFAULT_OG_IMAGE}">'
        f'\n  <meta property="og:image:alt" content="{html.escape(title, quote=True)} 대표 이미지">'
    )

    og_url = OG_URL_TAG_RE.search(source)
    if og_url:
        position = og_url.end()
        return source[:position] + tags + source[position:], True

    head = HEAD_CLOSE_RE.search(source)
    if head:
        return source[: head.start()] + tags + "\n" + source[head.start() :], True
    return source, False


def read_verified_rules(path: Path | None) -> list[str]:
    if path is None:
        return []
    raw = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        data = json.loads(raw)
        if not isinstance(data, list) or not all(isinstance(item, str) for item in data):
            raise ValueError("verified centers JSON must be an array of URL strings")
        return [item.strip() for item in data if item.strip()]
    return [
        line.strip()
        for line in raw.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]


def transform_page(
    path: Path,
    district_counts: Counter[str],
    modified_date: str,
    local_business_mode: str,
    verified_rules: list[str],
) -> tuple[PageResult, int]:
    original = path.read_text(encoding="utf-8")
    source = original
    changes: set[str] = set()

    source, changed = qualify_duplicate_district_h1(source, path, district_counts)
    if changed:
        changes.add("district_h1")

    canonical = canonical_url(source, path)
    crumbs = breadcrumb_items(path, source, canonical)

    source, changed = update_visible_breadcrumb(source, crumbs)
    if changed:
        changes.add("visible_breadcrumb")

    source, schema_changes, local_business_seen = update_json_ld(
        source,
        crumbs,
        canonical,
        local_business_mode,
        verified_rules,
    )
    changes.update(schema_changes)

    if page_depth(path) <= 2:
        source, changed = add_hub_og_image(source)
        if changed:
            changes.add("hub_og_image")

    # 수정일은 실제 기술·콘텐츠 변경이 있었던 페이지에만 기록한다.
    # 이미 정리된 페이지를 재실행해 날짜만 매번 바꾸는 일을 방지한다.
    if source != original:
        source, changed = update_article_modified(source, modified_date)
        if changed:
            changes.add("article_date_modified")

    return (
        PageResult(
            path=path,
            canonical=canonical,
            original=original,
            updated=source,
            depth=page_depth(path),
            changes=changes,
        ),
        local_business_seen,
    )


def update_sitemap(
    source: str,
    changed_dates: dict[str, str],
) -> tuple[str, int, list[str]]:
    updated_count = 0
    found: set[str] = set()

    def replace(match: re.Match[str]) -> str:
        nonlocal updated_count
        block = match.group(1)
        loc = normalize_url(html.unescape(match.group(2).strip()))
        wanted = changed_dates.get(loc)
        if not wanted:
            return block
        found.add(loc)
        replacement = f"<lastmod>{wanted}</lastmod>"
        if LASTMOD_RE.search(block):
            revised = LASTMOD_RE.sub(replacement, block, count=1)
        else:
            loc_end = re.search(r"</loc>", block, re.IGNORECASE)
            if not loc_end:
                return block
            revised = (
                block[: loc_end.end()]
                + "\n    "
                + replacement
                + block[loc_end.end() :]
            )
        if revised != block:
            updated_count += 1
        return revised

    updated = SITEMAP_URL_RE.sub(replace, source)
    missing = sorted(set(changed_dates) - found)
    return updated, updated_count, missing


def patch_vercel_redirects(source: str) -> tuple[str, bool]:
    data = json.loads(source)
    redirects = data.setdefault("redirects", [])
    if not isinstance(redirects, list):
        raise ValueError("vercel.json redirects must be an array")

    desired = [
        {
            "source": "/index.html",
            "destination": "/",
            "permanent": True,
        },
        {
            "source": "/:path*/index.html",
            "destination": "/:path*/",
            "permanent": True,
        },
    ]
    existing_sources = {
        item.get("source")
        for item in redirects
        if isinstance(item, dict)
    }
    missing = [item for item in desired if item["source"] not in existing_sources]
    if not missing:
        return source, False

    # 구체적인 /index.html 규칙이 catch-all보다 먼저 평가되도록 앞에 둔다.
    data["redirects"] = missing + redirects
    return json.dumps(data, ensure_ascii=False, indent=2) + "\n", True


def validate_transformed_pages(results: list[PageResult]) -> dict[str, int]:
    failures = Counter()
    district_h1s: dict[str, list[Path]] = {}

    for result in results:
        source = result.updated
        if not H1_RE.search(source):
            failures["missing_h1"] += 1
        if not BREADCRUMB_RE.search(source):
            failures["missing_visible_breadcrumb"] += 1
        if result.depth <= 2 and not OG_IMAGE_RE.search(source):
            failures["hub_missing_og_image"] += 1

        expected = breadcrumb_items(result.path, source, result.canonical)
        expected_json = [
            {
                "@type": "ListItem",
                "position": position,
                "name": crumb.name,
                "item": normalize_url(crumb.url),
            }
            for position, crumb in enumerate(expected, start=1)
        ]
        json_breadcrumbs: list[list[dict[str, Any]]] = []
        for match in JSON_LD_RE.finditer(source):
            try:
                data = json.loads(match.group(3))
            except json.JSONDecodeError:
                failures["jsonld_parse_error"] += 1
                continue
            for node in graph_nodes(data):
                if node_has_type(node, "BreadcrumbList"):
                    items = node.get("itemListElement")
                    if isinstance(items, list):
                        json_breadcrumbs.append(items)

        if not json_breadcrumbs:
            failures["missing_jsonld_breadcrumb"] += 1
        elif any(items != expected_json for items in json_breadcrumbs):
            failures["breadcrumb_mismatch"] += 1

        if result.depth == 2:
            district = result.path.parent.name
            district_h1s.setdefault(page_h1(source), []).append(result.path)

    duplicate_h1_groups = sum(
        1 for paths in district_h1s.values() if len(paths) > 1
    )
    failures["duplicate_district_h1_groups"] = duplicate_h1_groups
    return dict(failures)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="학습코칭.kr 전국학원 기술 SEO 보강 (기본 DRY-RUN)"
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="검증 후 실제 파일에 기록",
    )
    parser.add_argument(
        "--modified-date",
        default=date.today().isoformat(),
        help="이번 실행에서 실제 변경된 페이지의 dateModified/lastmod (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--local-business-mode",
        choices=("preserve", "verified-only"),
        default="preserve",
        help="기본 preserve. verified-only는 확인 목록 밖 페이지의 LocalBusiness만 보수적으로 낮춤",
    )
    parser.add_argument(
        "--verified-centers",
        type=Path,
        help="실제 지점으로 검증한 URL 목록(txt/json). '*' 접미사는 하위 URL 포함",
    )
    parser.add_argument(
        "--acknowledge-local-business-downgrade",
        action="store_true",
        help="verified-only 변환의 의미를 확인했다는 명시적 승인",
    )
    parser.add_argument(
        "--patch-vercel-index-redirects",
        action="store_true",
        help="/index.html을 trailing-slash canonical URL로 308 리디렉션하는 규칙 추가",
    )
    return parser.parse_args()


def validate_args(args: argparse.Namespace) -> None:
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", args.modified_date):
        raise SystemExit("--modified-date must use YYYY-MM-DD")
    try:
        date.fromisoformat(args.modified_date)
    except ValueError as exc:
        raise SystemExit(f"invalid --modified-date: {exc}") from exc

    if args.local_business_mode == "verified-only":
        if args.verified_centers is None:
            raise SystemExit(
                "verified-only requires --verified-centers; "
                "LocalBusiness is never removed without a verification manifest"
            )
        if not args.acknowledge_local_business_downgrade:
            raise SystemExit(
                "verified-only requires --acknowledge-local-business-downgrade"
            )
        if not args.verified_centers.is_file():
            raise SystemExit(f"verified centers file not found: {args.verified_centers}")


def main() -> int:
    args = parse_args()
    validate_args(args)

    paths = sorted(NATIONAL_ROOT.rglob("index.html"))
    if len(paths) != EXPECTED_TOTAL:
        raise SystemExit(
            f"safety stop: expected {EXPECTED_TOTAL} national pages, found {len(paths)}"
        )

    hub_count = sum(page_depth(path) <= 2 for path in paths)
    if hub_count != EXPECTED_HUBS:
        raise SystemExit(
            f"safety stop: expected {EXPECTED_HUBS} hubs, found {hub_count}"
        )

    verified_rules = read_verified_rules(args.verified_centers)
    if args.local_business_mode == "verified-only" and not verified_rules:
        raise SystemExit("verified centers manifest is empty")

    counts = district_name_counts(paths)
    results: list[PageResult] = []
    local_business_seen = 0
    for path in paths:
        result, seen = transform_page(
            path,
            counts,
            args.modified_date,
            args.local_business_mode,
            verified_rules,
        )
        results.append(result)
        local_business_seen += seen

    failures = validate_transformed_pages(results)
    blocking_failures = {
        key: value
        for key, value in failures.items()
        if value
    }
    if blocking_failures:
        print("VALIDATION FAILED", file=sys.stderr)
        for key, value in sorted(blocking_failures.items()):
            print(f"  {key}={value}", file=sys.stderr)
        return 2

    changed_results = [result for result in results if result.changed]
    changed_dates = {
        normalize_url(result.canonical): args.modified_date
        for result in changed_results
    }

    sitemap_source = SITEMAP_PATH.read_text(encoding="utf-8")
    sitemap_updated, sitemap_updates, sitemap_missing = update_sitemap(
        sitemap_source,
        changed_dates,
    )
    if sitemap_missing:
        print(
            f"safety stop: {len(sitemap_missing)} changed URLs are missing from sitemap",
            file=sys.stderr,
        )
        for item in sitemap_missing[:20]:
            print(f"  MISSING {item}", file=sys.stderr)
        return 3

    vercel_source = VERCEL_PATH.read_text(encoding="utf-8")
    vercel_updated = vercel_source
    vercel_changed = False
    if args.patch_vercel_index_redirects:
        vercel_updated, vercel_changed = patch_vercel_redirects(vercel_source)

    change_counts = Counter(
        change
        for result in results
        for change in result.changes
    )
    print("MODE=" + ("APPLY" if args.apply else "DRY-RUN"))
    print(f"national_pages={len(results)}")
    print(f"hubs={hub_count}")
    print(f"changed_pages={len(changed_results)}")
    print(f"local_business_nodes_seen={local_business_seen}")
    print(f"sitemap_lastmod_updates={sitemap_updates}")
    print(f"vercel_index_redirect_patch={int(vercel_changed)}")
    for key, value in sorted(change_counts.items()):
        print(f"{key}={value}")
    print("validation_errors=0")

    if not args.apply:
        print(
            "DRY-RUN complete: no files were written. "
            "Run again with --apply after reviewing the counts."
        )
        return 0

    for result in changed_results:
        result.path.write_text(result.updated, encoding="utf-8", newline="")
    if sitemap_updated != sitemap_source:
        SITEMAP_PATH.write_text(sitemap_updated, encoding="utf-8", newline="")
    if vercel_changed:
        VERCEL_PATH.write_text(vercel_updated, encoding="utf-8", newline="\n")

    print("APPLY complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
