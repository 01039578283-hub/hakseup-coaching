from __future__ import annotations

r"""Strict release audit for the 학습코칭.kr 전국학원 collection.

This audit deliberately separates URL immutability from content quality.  The
URL/file/canonical/sitemap sets are compared with a manifest kept outside the
repository, while the nationwide landing pages are checked against the current
content and entity rules.

The default baseline is created at::

    %TEMP%\hakseupcoaching_4743_baseline_manifest.json

Use ``--baseline`` to point at a copied manifest.  This script never rewrites
the baseline or any site file.
"""

import argparse
import csv
import hashlib
import html
import json
import os
import re
import sys
from collections import Counter, defaultdict
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import quote, unquote, urljoin, urlsplit
from xml.etree import ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
NATIONAL_ROOT = ROOT / "전국학원"
CENTER_DIRECTORY_ROOT = ROOT / "과목별학원" / "와와학습코칭센터"
REFERENCE_CSV = ROOT.parent / "참고자료" / "공통자료" / "센터정보 정리.csv"
BASE_URL = "https://xn--ru4bi8s1tac0p.kr"
ROOT_ORGANIZATION_ID = BASE_URL + "/#organization"
BASE_HOSTS = {"xn--ru4bi8s1tac0p.kr", "학습코칭.kr"}
DEFAULT_BASELINE = (
    Path(os.environ.get("TEMP", os.environ.get("TMP", str(ROOT.parent))))
    / "hakseupcoaching_4743_baseline_manifest.json"
)
EXPECTED_PUBLIC_COUNT = 4_743
EXPECTED_BASELINE_SHA256 = (
    "fdf0f33d37b722517667609e8e0e4ca360fbbd808605b21e0394849ed1f0edb0"
)
EXPECTED_NATIONAL_DEPTHS = {0: 1, 1: 13, 2: 76, 3: 371, 4: 1_113}
DETAIL_DEPTHS = {3, 4}
REQUIRED_DETAIL_TYPES = {
    "EducationalOrganization",
    "LocalBusiness",
    "WebPage",
    "Article",
    "Service",
    "FAQPage",
    "BreadcrumbList",
    "ItemList",
}
REQUIRED_HUB_TYPES = {"CollectionPage", "BreadcrumbList", "ItemList"}
EXCLUDED_PARTS = {".git", ".vercel", "__pycache__", "tmp"}
SEJONG_PREFIX = ("충청", "새롬중앙로")
SEJONG_REGION_LABEL = "충청·세종"
SEJONG_LOCALITY_LABEL = "세종특별자치시"
SEJONG_CENTER_LOCALITY = "새롬동"
ADDRESS_REGION_NAMES = {
    "강원": "강원특별자치도",
    "강원특별자치도": "강원특별자치도",
    "경기": "경기도",
    "경기도": "경기도",
    "경남": "경상남도",
    "경상남도": "경상남도",
    "경북": "경상북도",
    "경상북도": "경상북도",
    "광주": "광주광역시",
    "광주광역시": "광주광역시",
    "대구": "대구광역시",
    "대구광역시": "대구광역시",
    "대전": "대전광역시",
    "대전광역시": "대전광역시",
    "부산": "부산광역시",
    "부산광역시": "부산광역시",
    "서울": "서울특별시",
    "서울특별시": "서울특별시",
    "세종특별자치시": "세종특별자치시",
    "울산": "울산광역시",
    "울산광역시": "울산광역시",
    "인천": "인천광역시",
    "인천광역시": "인천광역시",
    "전북특별자치도": "전북특별자치도",
    "제주특별자치도": "제주특별자치도",
    "충남": "충청남도",
    "충청남도": "충청남도",
    "충북": "충청북도",
    "충청북도": "충청북도",
}

SCRIPT_STYLE_RE = re.compile(
    r"<(?:script|style|noscript|svg)\b.*?</(?:script|style|noscript|svg)>",
    re.I | re.S,
)
TAG_RE = re.compile(r"<[^>]+>")
ATTR_RE = re.compile(r"([:\w-]+)\s*=\s*([\"'])(.*?)\2", re.S)
JSON_LD_RE = re.compile(
    r"<script\b[^>]*type=[\"']application/ld\+json[\"'][^>]*>(.*?)</script>",
    re.I | re.S,
)
PLACEHOLDER_RE = re.compile(
    r"정보\s*준비\s*중|콘텐츠\s*준비\s*중|Lorem\s+ipsum|\bTODO\b|\bTBD\b|"
    r"\{\{[^{}]+\}\}|\[\[[^\[\]]+\]\]",
    re.I,
)
OVERCLAIM_RE = re.compile(
    r"끌어올|점수로\s*연결|실력\s*향상|점수(?:를|가|는|도)?\s*안정|"
    r"성과(?:를|가|는|도)?\s*높|"
    r"(?:성적|점수)(?:을|를|이|가|은|는|도)?\s*"
    r"(?:상승|향상|오(?:르|른|를)|올(?:리|려|릴|린|라|랐))"
)
OLD_GRADE_CTA_RE = re.compile(r"(?:초등|중등|고등)\s*영수\s*학습\s*상담")
OLD_FEE_PLACEHOLDER_RE = re.compile(r"교습비\s*안내\s*준비\s*중")
GENERIC_ALL_HIGH_SCHOOL_RE = re.compile(
    r"지역\s*내\s*모든\s*고등학교\s*(?:수업\s*)?가능"
)
GRADE_TOKEN_RE = re.compile(r"(?<![가-힣\d])([초중고][1-6])(?!\d)")
GRADE_RANGE_RE = re.compile(
    r"(?<![가-힣\d])([초중고])([1-6])\s*[~～〜\-–—]\s*([초중고])?([1-6])(?!\d)"
)
AVAILABILITY_CUE_RE = re.compile(
    r"가능\s*(?:학년|범위)|센터\s*제공\s*자료|"
    r"수강\s*(?:가능\s*)?(?:학년|범위)|과목별\s*수강\s*범위|"
    r"(?:센터|제공)\s*자료.{0,30}(?:학년|수강)",
    re.S,
)
CONSULT_CONFIRM_RE = re.compile(
    r"(?:상담.{0,30}확인|확인.{0,30}상담|가능\s*여부.{0,30}상담)", re.S
)
ASSERTIVE_AVAILABILITY_RE = re.compile(
    r"(?:수업|수강(?!료)).{0,20}(?:가능|개설|운영)|"
    r"(?:가능|개설|운영).{0,20}(?:수업|수강(?!료))",
    re.S,
)
EMPTY_SCHOOL_TRUTH_RE = re.compile(
    r"(?:학교|타깃학교).{0,35}(?:제공(?:된)?\s*자료에서\s*확인되지\s*않|"
    r"자료가\s*(?:없|제공되지\s*않)|정보가\s*(?:없|제공되지\s*않|확인되지\s*않))|"
    r"(?:제공(?:된)?\s*자료에서).{0,25}(?:학교|타깃학교).{0,25}확인되지\s*않",
    re.S,
)


def strip_tags(value: str) -> str:
    value = SCRIPT_STYLE_RE.sub(" ", value or "")
    value = TAG_RE.sub(" ", value)
    return re.sub(r"\s+", " ", html.unescape(value)).strip()


def attrs(tag: str) -> dict[str, str]:
    return {
        match.group(1).lower(): html.unescape(match.group(3))
        for match in ATTR_RE.finditer(tag)
    }


def meta_values(source: str, attribute: str, value: str) -> list[str]:
    result: list[str] = []
    for tag in re.findall(r"<meta\b[^>]*>", source, re.I):
        data = attrs(tag)
        if data.get(attribute, "").lower() == value.lower():
            result.append(data.get("content", ""))
    return result


def canonical_values(source: str) -> list[str]:
    result: list[str] = []
    for tag in re.findall(r"<link\b[^>]*>", source, re.I):
        data = attrs(tag)
        if "canonical" in data.get("rel", "").lower().split():
            result.append(data.get("href", ""))
    return result


def node_types(node: dict[str, Any]) -> set[str]:
    value = node.get("@type", [])
    if isinstance(value, str):
        return {value}
    if isinstance(value, list):
        return {str(item) for item in value}
    return set()


def graph_nodes(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, dict) and isinstance(data.get("@graph"), list):
        return [node for node in data["@graph"] if isinstance(node, dict)]
    if isinstance(data, dict):
        return [data]
    if isinstance(data, list):
        return [node for node in data if isinstance(node, dict)]
    return []


def is_noindex(source: str) -> bool:
    for tag in re.findall(r"<meta\b[^>]*>", source, re.I):
        data = attrs(tag)
        if data.get("name", "").lower() == "robots":
            if "noindex" in data.get("content", "").lower():
                return True
    return False


def page_url(path: Path) -> str:
    relative = path.relative_to(ROOT)
    parent = relative.parent.as_posix()
    if parent == ".":
        return BASE_URL + "/"
    return BASE_URL + "/" + quote(parent, safe="/") + "/"


def public_index_pages() -> list[Path]:
    result: list[Path] = []
    for path in sorted(ROOT.rglob("index.html")):
        relative = path.relative_to(ROOT)
        if any(part in EXCLUDED_PARTS for part in relative.parts):
            continue
        source = path.read_text(encoding="utf-8", errors="ignore")
        if not is_noindex(source):
            result.append(path)
    return result


class Findings:
    def __init__(self, sample_limit: int = 5) -> None:
        self.sample_limit = sample_limit
        self.counts: Counter[str] = Counter()
        self.samples: defaultdict[str, list[str]] = defaultdict(list)

    def add(self, code: str, location: str | Path, message: str) -> None:
        self.counts[code] += 1
        if len(self.samples[code]) < self.sample_limit:
            if isinstance(location, Path):
                try:
                    label = location.relative_to(ROOT).as_posix()
                except ValueError:
                    label = str(location)
            else:
                label = location
            self.samples[code].append(f"{label}: {message}")

    def compare_set(
        self,
        code: str,
        current: Iterable[str],
        baseline: Iterable[str],
    ) -> None:
        current_set = set(current)
        baseline_set = set(baseline)
        missing = sorted(baseline_set - current_set)
        extra = sorted(current_set - baseline_set)
        if missing or extra:
            detail = (
                f"missing={len(missing)} extra={len(extra)} "
                f"missing_sample={missing[:2]} extra_sample={extra[:2]}"
            )
            self.add(code, "collection", detail)

    def report(self) -> int:
        total = sum(self.counts.values())
        print(f"strict_errors={total}")
        print(f"strict_error_codes={len(self.counts)}")
        for code in sorted(self.counts):
            print(f"ERROR_COUNT {code}={self.counts[code]}")
            for sample in self.samples[code]:
                print(f"ERROR {code} {sample}")
        return 1 if total else 0


def load_baseline(path: Path, findings: Findings) -> dict[str, Any]:
    try:
        path.relative_to(ROOT.resolve())
    except ValueError:
        pass
    else:
        findings.add(
            "baseline_inside_repository",
            path,
            "immutable baseline must be stored outside the repository",
        )
    if not path.is_file():
        findings.add(
            "baseline_missing",
            path,
            "baseline manifest is required and must remain outside the repository",
        )
        return {}
    try:
        raw = path.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        if digest != EXPECTED_BASELINE_SHA256:
            findings.add(
                "baseline_digest_changed",
                path,
                f"sha256={digest} expected={EXPECTED_BASELINE_SHA256}",
            )
        data = json.loads(raw.decode("utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        findings.add("baseline_invalid", path, str(exc))
        return {}
    required = {"files", "folder_urls", "canonicals", "sitemap_urls", "counts"}
    missing = required - set(data) if isinstance(data, dict) else required
    if missing:
        findings.add("baseline_invalid", path, f"missing keys={sorted(missing)}")
        return {}
    if data.get("base_url") not in {BASE_URL, BASE_URL + "/"}:
        findings.add(
            "baseline_invalid", path, f"base_url={data.get('base_url')!r}"
        )
    if data.get("sets_equal") is not True:
        findings.add("baseline_invalid", path, "sets_equal is not true")
    counts = data.get("counts", {})
    if not isinstance(counts, dict) or any(
        counts.get(key) != EXPECTED_PUBLIC_COUNT
        for key in ("files", "folder_urls", "canonicals", "sitemap_urls")
    ):
        findings.add("baseline_invalid", path, f"counts={counts!r}")
    for key in ("files", "folder_urls", "canonicals", "sitemap_urls"):
        values = data.get(key, [])
        if len(values) != EXPECTED_PUBLIC_COUNT or len(values) != len(set(values)):
            findings.add(
                "baseline_invalid",
                path,
                f"{key} count={len(values)} unique={len(set(values))}",
            )
    if not (
        set(data["folder_urls"])
        == set(data["canonicals"])
        == set(data["sitemap_urls"])
    ):
        findings.add("baseline_invalid", path, "baseline URL sets differ")
    return data


def sitemap_urls(findings: Findings) -> list[str]:
    try:
        tree = ET.parse(ROOT / "sitemap.xml")
    except (OSError, ET.ParseError) as exc:
        findings.add("sitemap_invalid", ROOT / "sitemap.xml", str(exc))
        return []
    namespace = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    entries = tree.findall(".//sm:url", namespace)
    urls: list[str] = []
    for entry in entries:
        location = entry.find("sm:loc", namespace)
        lastmod = entry.find("sm:lastmod", namespace)
        value = (location.text or "").strip() if location is not None else ""
        if not value:
            findings.add("sitemap_invalid", "sitemap.xml", "empty loc")
            continue
        urls.append(value)
        modified = (lastmod.text or "").strip() if lastmod is not None else ""
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", modified):
            findings.add("sitemap_lastmod", value, f"invalid lastmod={modified!r}")
    if len(urls) != len(set(urls)):
        findings.add(
            "sitemap_duplicates",
            "sitemap.xml",
            f"duplicates={len(urls) - len(set(urls))}",
        )
    return urls


def normalize_neighborhood(value: str) -> str:
    return re.sub(r"\s+", " ", value.replace("-", " ")).strip()


def split_csv_list(value: str) -> list[str]:
    return [part.strip() for part in (value or "").split(",") if part.strip()]


def center_records(findings: Findings) -> dict[tuple[str, str, str], dict[str, str]]:
    if not REFERENCE_CSV.is_file():
        findings.add("reference_csv_missing", REFERENCE_CSV, "center CSV not found")
        return {}
    with REFERENCE_CSV.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    result: dict[tuple[str, str, str], dict[str, str]] = {}
    for row in rows:
        key = (
            row.get("지역", "").strip(),
            row.get("시or구", "").strip(),
            normalize_neighborhood(row.get("근처 수업가능 동네", "")),
        )
        if key in result:
            findings.add("reference_csv_duplicate", REFERENCE_CSV, str(key))
        result[key] = row
    if len(result) != 371:
        findings.add(
            "reference_csv_count", REFERENCE_CSV, f"centers={len(result)} expected=371"
        )
    return result


def physical_center_key(record: dict[str, str]) -> tuple[str, str, str]:
    return (
        record.get("센터명", "").strip(),
        record.get("센터 주소", "").strip(),
        record.get("교육지원청 등록번호", "").strip(),
    )


def compact_registration(value: str) -> str:
    return re.sub(r"\s+", "", value or "")


def expected_center_entities(
    records: dict[tuple[str, str, str], dict[str, str]],
    findings: Findings,
) -> tuple[dict[tuple[str, str, str], tuple[str, str]], Counter[str]]:
    profiles: defaultdict[str, set[str]] = defaultdict(set)
    for page in sorted(CENTER_DIRECTORY_ROOT.glob("*/index.html")):
        source = page.read_text(encoding="utf-8")
        match = re.search(
            r"<dt>\s*교육지원청\s*등록번호\s*</dt>\s*<dd>(.*?)</dd>",
            source,
            re.I | re.S,
        )
        canonical = canonical_values(source)
        if not match or len(canonical) != 1:
            continue
        expected_page_url = page_url(page)
        if canonical[0] != expected_page_url:
            findings.add(
                "center_profile_canonical",
                page,
                f"canonical={canonical!r} expected={expected_page_url!r}",
            )
        registration = compact_registration(strip_tags(match.group(1)))
        if registration:
            profiles[registration].add(canonical[0].rstrip("/") + "/")
    profile_urls: dict[str, str] = {}
    for registration, urls in profiles.items():
        if len(urls) != 1:
            findings.add(
                "center_profile_registration_collision",
                CENTER_DIRECTORY_ROOT,
                f"registration={registration!r} urls={sorted(urls)!r}",
            )
        else:
            profile_urls[registration] = next(iter(urls))

    detail_urls: defaultdict[tuple[str, str, str], set[str]] = defaultdict(set)
    for page in sorted(NATIONAL_ROOT.rglob("index.html")):
        parts = page.parent.relative_to(NATIONAL_ROOT).parts
        if len(parts) != 3:
            continue
        record = records.get((parts[0], parts[1], normalize_neighborhood(parts[2])))
        if record:
            detail_urls[physical_center_key(record)].add(page_url(page))

    expected: dict[tuple[str, str, str], tuple[str, str]] = {}
    kinds: Counter[str] = Counter()
    for record in records.values():
        key = physical_center_key(record)
        if key in expected:
            continue
        profile_url = profile_urls.get(compact_registration(key[2]))
        if profile_url:
            entity_url = profile_url
            kinds["directory"] += 1
        else:
            candidates = sorted(detail_urls.get(key, set()))
            if not candidates:
                findings.add(
                    "center_representative_missing",
                    "center entity",
                    f"center={key!r}",
                )
                continue
            entity_url = candidates[0]
            kinds["national_representative"] += 1
        expected[key] = (entity_url + "#organization", entity_url)

        target = resolve_local_reference(NATIONAL_ROOT / "index.html", entity_url)
        if target is None or not target.is_file():
            findings.add(
                "center_entity_not_dereferenceable",
                "center entity",
                f"url={entity_url!r} target={target}",
            )
        else:
            target_canonical = canonical_values(target.read_text(encoding="utf-8"))
            if target_canonical != [entity_url]:
                findings.add(
                    "center_entity_canonical_mismatch",
                    target,
                    f"canonical={target_canonical!r} expected={entity_url!r}",
                )

    if len(expected) != 188 or kinds != Counter(
        {"directory": 182, "national_representative": 6}
    ):
        findings.add(
            "center_entity_expected_counts",
            "center entity",
            f"entities={len(expected)} kinds={dict(kinds)!r}",
        )
    return expected, kinds


def visible_breadcrumb_entries(source: str) -> list[dict[str, str]]:
    match = re.search(r'<div\s+class=["\']breadcrumb["\']>(.*?)</div>', source, re.I | re.S)
    if not match:
        return []
    result: list[dict[str, str]] = []
    for segment in match.group(1).split("›"):
        name = strip_tags(segment)
        if not name:
            continue
        anchor = re.search(r"<a\b([^>]*)>.*?</a>", segment, re.I | re.S)
        href = attrs(anchor.group(1)).get("href", "") if anchor else ""
        result.append({"name": name, "item": href})
    return result


def schema_breadcrumb_entries(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    node = next((item for item in nodes if "BreadcrumbList" in node_types(item)), {})
    entries = node.get("itemListElement", []) if isinstance(node, dict) else []
    return [
        {
            "position": item.get("position"),
            "name": str(item.get("name", "")).strip(),
            "item": str(item.get("item", "")).strip(),
        }
        for item in entries
        if isinstance(item, dict) and str(item.get("name", "")).strip()
    ]


def compact_label(value: str) -> str:
    return re.sub(r"[\s-]+", "", value or "")


def normalized_web_url(page: Path, reference: str) -> str:
    value = html.unescape(reference or "").strip()
    if not value:
        return ""
    joined = urljoin(page_url(page), value)
    split = urlsplit(joined)
    try:
        host = (split.hostname or "").encode("idna").decode("ascii").lower()
    except UnicodeError:
        host = (split.hostname or "").lower()
    port = f":{split.port}" if split.port else ""
    path_value = quote(unquote(split.path or "/"), safe="/")
    return f"{split.scheme.lower()}://{host}{port}{path_value}"


def expected_breadcrumb(path: Path, source: str) -> tuple[list[str], list[str]]:
    parts = path.parent.relative_to(NATIONAL_ROOT).parts
    h1_match = re.search(r"<h1\b[^>]*>(.*?)</h1>", source, re.I | re.S)
    h1 = strip_tags(h1_match.group(1)) if h1_match else ""
    names = ["홈", "전국학원"]
    if parts == ("충청",):
        names.append(SEJONG_REGION_LABEL)
    elif parts[:2] == SEJONG_PREFIX:
        names.extend([SEJONG_REGION_LABEL, SEJONG_LOCALITY_LABEL])
        if len(parts) == 3:
            names.append(h1 or parts[2])
        elif len(parts) == 4:
            names.extend([parts[2], h1 or parts[3]])
    else:
        names.extend(normalize_neighborhood(part) for part in parts)
        if len(parts) >= 3:
            names[-1] = h1 or parts[-1]

    urls = [BASE_URL + "/", BASE_URL + "/" + quote("전국학원") + "/"]
    prefix = ["전국학원"]
    for part in parts:
        prefix.append(part)
        urls.append(BASE_URL + "/" + quote("/".join(prefix), safe="/") + "/")
    return names, urls


def check_breadcrumb_hierarchy(
    path: Path,
    source: str,
    visible_entries: list[dict[str, str]],
    schema_entries: list[dict[str, Any]],
    findings: Findings,
) -> None:
    expected_names, expected_urls = expected_breadcrumb(path, source)
    visible_names = [entry["name"] for entry in visible_entries]
    schema_names = [str(entry["name"]) for entry in schema_entries]
    if len(visible_entries) != len(expected_names):
        findings.add(
            "breadcrumb_hierarchy",
            path,
            f"items={visible_names!r} expected_count={len(expected_names)}",
        )
    for expected, actual in zip(expected_names, visible_names):
        if compact_label(expected) not in compact_label(actual):
            findings.add(
                "breadcrumb_hierarchy",
                path,
                f"expected token={expected!r} actual={actual!r}",
            )
            break
    if len(schema_entries) != len(expected_names):
        findings.add(
            "breadcrumb_schema_hierarchy",
            path,
            f"items={schema_names!r} expected_count={len(expected_names)}",
        )
    for expected, actual in zip(expected_names, schema_names):
        if compact_label(expected) not in compact_label(actual):
            findings.add(
                "breadcrumb_schema_hierarchy",
                path,
                f"expected token={expected!r} actual={actual!r}",
            )
            break

    # Every ancestor must be a real prefix URL; the visible current crumb is
    # intentionally plain text, while JSON-LD includes the current canonical.
    for index, expected_url in enumerate(expected_urls):
        if index < len(visible_entries):
            actual_href = visible_entries[index].get("item", "")
            if index == len(expected_urls) - 1:
                if actual_href:
                    findings.add(
                        "breadcrumb_visible_current_linked",
                        path,
                        f"href={actual_href!r}",
                    )
            elif normalized_web_url(path, actual_href) != expected_url:
                findings.add(
                    "breadcrumb_visible_link",
                    path,
                    f"position={index + 1} href={actual_href!r} expected={expected_url!r}",
                )
        if index < len(schema_entries):
            entry = schema_entries[index]
            if entry.get("position") != index + 1:
                findings.add(
                    "breadcrumb_schema_position",
                    path,
                    f"actual={entry.get('position')!r} expected={index + 1}",
                )
            if normalized_web_url(path, str(entry.get("item", ""))) != expected_url:
                findings.add(
                    "breadcrumb_schema_item",
                    path,
                    f"position={index + 1} item={entry.get('item')!r} expected={expected_url!r}",
                )

    if path.parent.relative_to(NATIONAL_ROOT).parts[:2] == SEJONG_PREFIX:
        legacy = [
            name for name in [*visible_names, *schema_names] if name in {"충청", "새롬중앙로", "세종시"}
        ]
        if legacy:
            findings.add(
                "sejong_breadcrumb_legacy", path, f"legacy geography={legacy!r}"
            )


def visible_faq(source: str) -> list[tuple[str, str]]:
    pairs = re.findall(
        r'<span\s+class=["\']parent-faq-q["\']>Q</span>(.*?)</summary>\s*'
        r'<p\b[^>]*class=["\'][^"\']*parent-faq-answer[^"\']*["\'][^>]*>(.*?)</p>',
        source,
        re.I | re.S,
    )
    return [(strip_tags(question), strip_tags(answer)) for question, answer in pairs]


def schema_faq(nodes: list[dict[str, Any]]) -> list[tuple[str, str]]:
    node = next((item for item in nodes if "FAQPage" in node_types(item)), {})
    result: list[tuple[str, str]] = []
    for question in node.get("mainEntity", []) if isinstance(node, dict) else []:
        if not isinstance(question, dict):
            continue
        answer = question.get("acceptedAnswer", {})
        result.append(
            (
                str(question.get("name", "")).strip(),
                str(answer.get("text", "")).strip() if isinstance(answer, dict) else "",
            )
        )
    return result


def parse_jsonld(
    path: Path, source: str, findings: Findings
) -> list[dict[str, Any]]:
    blocks = JSON_LD_RE.findall(source)
    if not blocks:
        findings.add("jsonld_missing", path, "no application/ld+json block")
        return []
    nodes: list[dict[str, Any]] = []
    for index, block in enumerate(blocks, start=1):
        try:
            nodes.extend(graph_nodes(json.loads(block)))
        except json.JSONDecodeError as exc:
            findings.add("jsonld_invalid", path, f"block={index} {exc}")
    identifiers = [
        str(node.get("@id"))
        for node in nodes
        if isinstance(node.get("@id"), str) and node.get("@id")
    ]
    if len(identifiers) != len(set(identifiers)):
        findings.add(
            "jsonld_duplicate_id",
            path,
            f"duplicate ids={len(identifiers) - len(set(identifiers))}",
        )
    return nodes


def recursive_dicts(value: Any) -> Iterable[dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for item in value.values():
            yield from recursive_dicts(item)
    elif isinstance(value, list):
        for item in value:
            yield from recursive_dicts(item)


def recursive_strings(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from recursive_strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from recursive_strings(item)


def jsonld_descriptions(nodes: list[dict[str, Any]]) -> list[str]:
    result: list[str] = []
    for item in recursive_dicts(nodes):
        description = item.get("description")
        if isinstance(description, str):
            result.append(description)
    return result


def check_sejong(
    path: Path,
    source: str,
    nodes: list[dict[str, Any]],
    authoritative_street_addresses: set[str],
    findings: Findings,
) -> None:
    parts = path.parent.relative_to(NATIONAL_ROOT).parts
    body_match = re.search(r"<body\b[^>]*>(.*?)</body>", source, re.I | re.S)
    body_text = strip_tags(body_match.group(1) if body_match else source)
    for expected in (SEJONG_REGION_LABEL, SEJONG_LOCALITY_LABEL):
        if expected not in body_text:
            findings.add("sejong_visible_geography", path, f"missing {expected}")
    if "세종시" in body_text:
        findings.add(
            "sejong_city_legacy", path, "visible geographic label '세종시' remains"
        )
    road_as_area = re.search(
        r"(?:충청\s+)?새롬중앙로(?:\s+(?:새롬동|다정동))?\s*"
        r"(?:의|에서|인근|지역|학생|학원|학습코칭|센터|수업|상담)",
        body_text,
    )
    if road_as_area:
        findings.add(
            "sejong_road_used_as_area",
            path,
            f"phrase={road_as_area.group(0)!r}",
        )
    serialized = json.dumps(nodes, ensure_ascii=False)
    for expected in (SEJONG_REGION_LABEL, SEJONG_LOCALITY_LABEL):
        if expected not in serialized:
            findings.add("sejong_jsonld_geography", path, f"missing {expected}")
    legacy_json_string = next(
        (value for value in recursive_strings(nodes) if "세종시" in value), None
    )
    if legacy_json_string:
        findings.add(
            "sejong_city_legacy",
            path,
            f"JSON-LD value={legacy_json_string!r}",
        )
    road_json = next(
        (
            match
            for value in recursive_strings(nodes)
            if (
                match := re.search(
                    r"새롬중앙로(?:\s+(?:새롬동|다정동))?\s*"
                    r"(?:의|에서|인근|지역|학생|학원|학습코칭|센터|수업|상담)",
                    value,
                )
            )
        ),
        None,
    )
    if road_json:
        findings.add(
            "sejong_road_used_as_area",
            path,
            f"JSON-LD phrase={road_json.group(0)!r}",
        )
    for item in recursive_dicts(nodes):
        for property_name in ("keywords", "name", "description", "about", "mentions"):
            if property_name not in item:
                continue
            offending = next(
                (
                    value
                    for value in recursive_strings(item[property_name])
                    if "새롬중앙로" in value
                    and not any(
                        address and address in value
                        for address in authoritative_street_addresses
                    )
                ),
                None,
            )
            if offending:
                findings.add(
                    "sejong_road_in_authored_schema",
                    path,
                    f"{property_name} value={offending!r}",
                )
                break
    for item in recursive_dicts(nodes):
        if "addressRegion" in item and item.get("addressRegion") != SEJONG_LOCALITY_LABEL:
            findings.add(
                "sejong_jsonld_geography",
                path,
                f"addressRegion={item.get('addressRegion')!r}",
            )
        if "addressLocality" in item and item.get("addressLocality") != SEJONG_CENTER_LOCALITY:
            findings.add(
                "sejong_jsonld_geography",
                path,
                f"addressLocality={item.get('addressLocality')!r}",
            )
        if "Place" in node_types(item) and item.get("name") in {"충청", "새롬중앙로", "세종시"}:
            findings.add(
                "sejong_jsonld_geography",
                path,
                f"legacy Place={item.get('name')!r}",
            )
        if "BreadcrumbList" in node_types(item):
            legacy = [
                entry.get("name")
                for entry in item.get("itemListElement", [])
                if isinstance(entry, dict)
                and entry.get("name") in {"충청", "새롬중앙로", "세종시"}
            ]
            if legacy:
                findings.add(
                    "sejong_jsonld_geography", path, f"legacy breadcrumb={legacy!r}"
                )

    if len(parts) >= 3:
        organization = next(
            (item for item in nodes if "LocalBusiness" in node_types(item)), {}
        )
        address = organization.get("address", {}) if isinstance(organization, dict) else {}
        if not isinstance(address, dict) or (
            address.get("addressRegion") != SEJONG_LOCALITY_LABEL
            or address.get("addressLocality") != SEJONG_CENTER_LOCALITY
        ):
            findings.add(
                "sejong_organization_address",
                path,
                f"address={address!r}",
            )
        expected_area = parts[2]
        services = [item for item in nodes if "Service" in node_types(item)]
        for service in services:
            area = service.get("areaServed", {})
            actual_area = area.get("name") if isinstance(area, dict) else ""
            if actual_area != expected_area:
                findings.add(
                    "sejong_service_area",
                    path,
                    f"actual={actual_area!r} expected={expected_area!r}",
                )


def check_sejong_region_hub(
    path: Path,
    source: str,
    nodes: list[dict[str, Any]],
    findings: Findings,
) -> None:
    expected_child_url = (
        BASE_URL + "/" + quote("전국학원/충청/새롬중앙로", safe="/") + "/"
    )
    body_match = re.search(r"<body\b[^>]*>(.*?)</body>", source, re.I | re.S)
    body_source = body_match.group(1) if body_match else source
    body_text = strip_tags(body_source)
    h1_match = re.search(r"<h1\b[^>]*>(.*?)</h1>", source, re.I | re.S)
    h1 = strip_tags(h1_match.group(1)) if h1_match else ""
    if SEJONG_REGION_LABEL not in body_text or SEJONG_REGION_LABEL not in h1:
        findings.add(
            "sejong_region_hub_name",
            path,
            f"visible_has={SEJONG_REGION_LABEL in body_text} h1={h1!r}",
        )
    if "새롬중앙로" in body_text or "세종시" in body_text:
        findings.add(
            "sejong_region_hub_legacy_geography",
            path,
            "visible road/city legacy label remains",
        )

    collections = [item for item in nodes if "CollectionPage" in node_types(item)]
    if len(collections) != 1 or SEJONG_REGION_LABEL not in str(
        collections[0].get("name", "") if collections else ""
    ):
        findings.add(
            "sejong_region_hub_collection_name",
            path,
            f"CollectionPage names={[item.get('name') for item in collections]!r}",
        )

    matching_cards: list[str] = []
    for match in re.finditer(r"<a\b([^>]*)>(.*?)</a>", body_source, re.I | re.S):
        data = attrs(match.group(1))
        if "hub-card" not in set(data.get("class", "").split()):
            continue
        if normalized_web_url(path, data.get("href", "")) == expected_child_url:
            matching_cards.append(strip_tags(match.group(2)))
    if len(matching_cards) != 1 or "세종특별자치시 학원" not in matching_cards[0]:
        findings.add(
            "sejong_region_hub_child_card",
            path,
            f"matching cards={matching_cards!r}",
        )
    if any("새롬중앙로" in text or "세종시" in text for text in matching_cards):
        findings.add(
            "sejong_region_hub_child_card",
            path,
            f"legacy child label={matching_cards!r}",
        )

    schema_children: list[str] = []
    for item_list in (item for item in nodes if "ItemList" in node_types(item)):
        for entry in item_list.get("itemListElement", []):
            if not isinstance(entry, dict):
                continue
            reference = str(entry.get("url") or entry.get("item") or "")
            if normalized_web_url(path, reference) == expected_child_url:
                schema_children.append(str(entry.get("name", "")))
    if schema_children != ["세종특별자치시 학원"]:
        findings.add(
            "sejong_region_hub_itemlist",
            path,
            f"matching entries={schema_children!r}",
        )
    schema_legacy = next(
        (
            value
            for value in recursive_strings(nodes)
            if "세종시" in value or re.search(r"새롬중앙로\s*학원", value)
        ),
        None,
    )
    if schema_legacy:
        findings.add(
            "sejong_region_hub_legacy_geography",
            path,
            f"JSON-LD value={schema_legacy!r}",
        )
    for item in recursive_dicts(nodes):
        for property_name in ("keywords", "name", "description", "about", "mentions"):
            if property_name not in item:
                continue
            offending = next(
                (
                    value
                    for value in recursive_strings(item[property_name])
                    if "새롬중앙로" in value
                ),
                None,
            )
            if offending:
                findings.add(
                    "sejong_region_hub_legacy_geography",
                    path,
                    f"{property_name} value={offending!r}",
                )
                break


def check_locality_display(
    path: Path,
    source: str,
    nodes: list[dict[str, Any]],
    record: dict[str, str],
    findings: Findings,
) -> None:
    parts = path.parent.relative_to(NATIONAL_ROOT).parts
    raw_slug = parts[2]
    expected = record.get("근처 수업가능 동네", "").strip()
    h1_match = re.search(r"<h1\b[^>]*>(.*?)</h1>", source, re.I | re.S)
    h1 = strip_tags(h1_match.group(1)) if h1_match else ""
    if expected not in h1:
        findings.add(
            "locality_h1_mismatch",
            path,
            f"h1={h1!r} expected display locality={expected!r}",
        )

    area_names: list[str] = []
    for item in recursive_dicts(nodes):
        if "areaServed" not in item:
            continue
        area = item.get("areaServed")
        values = area if isinstance(area, list) else [area]
        for value in values:
            if isinstance(value, dict):
                area_names.append(str(value.get("name", "")))
            elif isinstance(value, str):
                area_names.append(value)
    service_area_names: list[str] = []
    for service in (item for item in nodes if "Service" in node_types(item)):
        area = service.get("areaServed")
        values = area if isinstance(area, list) else [area]
        for value in values:
            if isinstance(value, dict):
                service_area_names.append(str(value.get("name", "")))
            elif isinstance(value, str):
                service_area_names.append(value)
    if not service_area_names or any(name != expected for name in service_area_names):
        findings.add(
            "locality_area_served_mismatch",
            path,
            f"Service.areaServed={service_area_names!r} expected={expected!r}",
        )

    if "-" not in raw_slug:
        return
    visible_text = strip_tags(SCRIPT_STYLE_RE.sub(" ", source))
    if raw_slug in visible_text or raw_slug in h1:
        findings.add(
            "hyphen_locality_visible",
            path,
            f"raw slug={raw_slug!r} remains; expected={expected!r}",
        )
    if any(raw_slug in name for name in area_names):
        findings.add(
            "hyphen_locality_area_served",
            path,
            f"raw slug={raw_slug!r} areaServed={area_names!r}",
        )
    for item in recursive_dicts(nodes):
        for property_name in ("about", "mentions"):
            if property_name not in item:
                continue
            offending = next(
                (
                    value
                    for value in recursive_strings(item[property_name])
                    if raw_slug in value
                ),
                None,
            )
            if offending:
                findings.add(
                    "hyphen_locality_schema",
                    path,
                    f"{property_name} value={offending!r}",
                )
                return


def check_schema_visible_sections(
    path: Path,
    source: str,
    nodes: list[dict[str, Any]],
    findings: Findings,
) -> None:
    visible_text = strip_tags(SCRIPT_STYLE_RE.sub(" ", source))
    compact_visible = compact_label(visible_text)
    section_classes: set[str] = set()
    for attributes in re.findall(r"<section\b([^>]*)>", source, re.I):
        section_classes.update(attrs(attributes).get("class", "").split())

    def supported(name: str) -> bool:
        compact_name = compact_label(name)
        if compact_name and compact_name in compact_visible:
            return True
        if name == "내부링크":
            return "child-page-links" in section_classes
        if name == "학습코칭 차별화":
            return "coaching-identity-section" in section_classes
        if name == "진단-플래너-오답관리 흐름":
            return (
                {"진단", "플래너", "오답"}
                <= {token for token in ("진단", "플래너", "오답") if token in visible_text}
                and (
                    "generated-support-section" in section_classes
                    or "coaching-identity-section" in section_classes
                )
            )
        if name == "주간 플래너 관리":
            return "주간 플래너" in visible_text
        if name == "오답 원인 분석":
            return (
                "오답 재학습" in visible_text
                and "coaching-identity-section" in section_classes
            )
        return False

    claims: list[tuple[str, str]] = []
    for node in nodes:
        types = node_types(node)
        if "Article" in types:
            article_sections = node.get("articleSection", [])
            if isinstance(article_sections, str):
                article_sections = [article_sections]
            if not isinstance(article_sections, list) or not article_sections:
                findings.add(
                    "article_section_missing", path, "Article.articleSection is empty"
                )
            else:
                claims.extend(
                    ("Article.articleSection", str(value).strip())
                    for value in article_sections
                    if str(value).strip()
                )
            has_part = node.get("hasPart", [])
            if not isinstance(has_part, list) or not has_part:
                findings.add("article_haspart_missing", path, "Article.hasPart is empty")
            else:
                claims.extend(
                    ("Article.hasPart", str(value.get("name", "")).strip())
                    for value in has_part
                    if isinstance(value, dict) and str(value.get("name", "")).strip()
                )
        if "WebPage" in types:
            has_part = node.get("hasPart", [])
            if not isinstance(has_part, list) or not has_part:
                findings.add("webpage_haspart_missing", path, "WebPage.hasPart is empty")
            else:
                claims.extend(
                    ("WebPage.hasPart", str(value.get("name", "")).strip())
                    for value in has_part
                    if isinstance(value, dict) and str(value.get("name", "")).strip()
                )
    for scope, claim in claims:
        if not supported(claim):
            findings.add(
                "schema_claims_removed_section",
                path,
                f"{scope}={claim!r} has no meaningful visible counterpart",
            )


def resolve_local_reference(page: Path, reference: str) -> Path | None:
    value = html.unescape(reference).strip()
    if not value:
        return None
    split = urlsplit(value)
    scheme = split.scheme.lower()
    if scheme in {"mailto", "tel", "sms", "javascript", "data"}:
        return None
    if scheme and scheme not in {"http", "https"}:
        return None
    if split.netloc and (split.hostname or "").lower() not in BASE_HOSTS:
        return None
    raw_path = unquote(split.path)
    if not raw_path:
        return page
    if raw_path.startswith("/"):
        candidate = ROOT / raw_path.lstrip("/")
    else:
        candidate = page.parent / raw_path
    candidate = candidate.resolve()
    try:
        candidate.relative_to(ROOT.resolve())
    except ValueError:
        return candidate
    if raw_path.endswith("/") or candidate.is_dir():
        candidate = candidate / "index.html"
    return candidate


def absolute_asset_url(page: Path, reference: str) -> str:
    split = urlsplit(html.unescape(reference).strip())
    if split.scheme and split.netloc:
        return f"{split.scheme.lower()}://{split.netloc.lower()}{quote(unquote(split.path), safe='/')}"
    target = resolve_local_reference(page, reference)
    if target is None:
        return ""
    try:
        relative = target.relative_to(ROOT).as_posix()
    except ValueError:
        return ""
    return BASE_URL + "/" + quote(relative, safe="/")


def check_links_and_images(
    path: Path,
    source: str,
    nodes: list[dict[str, Any]],
    is_detail: bool,
    findings: Findings,
) -> None:
    for match in re.finditer(r"<a\b([^>]*)>(.*?)</a>", source, re.I | re.S):
        data = attrs(match.group(1))
        href = data.get("href", "").strip()
        label = strip_tags(match.group(2)) or data.get("aria-label", "").strip()
        if not href:
            findings.add("link_empty_href", path, f"anchor={label!r}")
            continue
        if href.lower().startswith("javascript:"):
            findings.add("link_javascript", path, f"href={href!r}")
            continue
        if not label:
            findings.add("link_empty_label", path, f"href={href!r}")
        target = resolve_local_reference(path, href)
        if target is not None and not target.exists():
            findings.add("link_broken", path, f"href={href!r} -> {target}")

    visible_image_urls: set[str] = set()
    image_tags = re.findall(r"<img\b[^>]*>", source, re.I)
    for tag in image_tags:
        data = attrs(tag)
        css_class = data.get("class", "").lower()
        style = data.get("style", "").lower().replace(" ", "")
        if "generated" in css_class and (
            "hidden" in css_class
            or "hidden" in data
            or re.search(r"\shidden(?:\s|/?>)", tag, re.I)
            or "display:none" in style
            or "visibility:hidden" in style
        ):
            # A hidden image is not a visible Article image and is audited
            # separately as forbidden DOM.
            continue
        src = data.get("src", "").strip()
        if not src:
            findings.add("image_missing_src", path, tag[:120])
            continue
        visible_image_urls.add(absolute_asset_url(path, src))
        if not data.get("alt", "").strip():
            findings.add("image_missing_alt", path, f"src={src!r}")
        if is_detail:
            for dimension in ("width", "height"):
                if not re.fullmatch(r"[1-9]\d*", data.get(dimension, "")):
                    findings.add(
                        "image_missing_dimensions",
                        path,
                        f"src={src!r} {dimension}={data.get(dimension)!r}",
                    )
        target = resolve_local_reference(path, src)
        if target is not None:
            if not target.is_file():
                findings.add("image_broken", path, f"src={src!r} -> {target}")
            elif target.stat().st_size == 0:
                findings.add("image_empty_file", path, f"src={src!r}")

    for tag in re.findall(r"<source\b[^>]*>", source, re.I):
        data = attrs(tag)
        srcset = data.get("srcset", "")
        for candidate in srcset.split(","):
            reference = candidate.strip().split()[0] if candidate.strip() else ""
            if not reference:
                findings.add("image_missing_srcset", path, tag[:120])
                continue
            target = resolve_local_reference(path, reference)
            if target is not None and not target.is_file():
                findings.add(
                    "image_broken", path, f"srcset={reference!r} -> {target}"
                )

    og_images = meta_values(source, "property", "og:image")
    og_alts = meta_values(source, "property", "og:image:alt")
    if len(og_images) != 1 or not og_images[0].strip():
        findings.add("og_image", path, f"count={len(og_images)}")
    else:
        og_url = og_images[0].strip()
        visible_image_urls.add(og_url)
        split = urlsplit(og_url)
        if split.scheme != "https" or not split.netloc:
            findings.add("og_image", path, f"not absolute https={og_url!r}")
        target = resolve_local_reference(path, og_url)
        if target is not None and not target.is_file():
            findings.add("og_image", path, f"missing local asset={target}")
    if len(og_alts) != 1 or not og_alts[0].strip():
        findings.add("og_image_alt", path, f"count={len(og_alts)}")

    if is_detail:
        if not any(
            "bulk-responsive-picture" in set(attrs(attributes).get("class", "").split())
            for attributes in re.findall(r"<picture\b([^>]*)>", source, re.I)
        ):
            findings.add("detail_body_picture", path, "responsive picture missing")
        if not re.search(r"assets/maps/[^\"']+", source):
            findings.add("detail_map_image", path, "map asset missing")
        article = next((node for node in nodes if "Article" in node_types(node)), {})
        image_value = article.get("image") if isinstance(article, dict) else None
        article_urls: set[str] = set()
        candidates = image_value if isinstance(image_value, list) else [image_value]
        for candidate in candidates:
            if isinstance(candidate, str):
                article_urls.add(candidate)
            elif isinstance(candidate, dict) and isinstance(candidate.get("url"), str):
                article_urls.add(candidate["url"])
        if not article_urls:
            findings.add("article_image", path, "Article.image missing")
        elif not article_urls & visible_image_urls:
            findings.add(
                "article_image_mismatch",
                path,
                f"article={sorted(article_urls)} visible/og sample={sorted(visible_image_urls)[:3]}",
            )


def school_columns(record: dict[str, str]) -> dict[str, list[str]]:
    high = [
        value
        for value in split_csv_list(record.get("타깃학교\n(고)", ""))
        if not GENERIC_ALL_HIGH_SCHOOL_RE.fullmatch(value)
    ]
    return {
        "elementary": split_csv_list(record.get("타깃학교\n(초)", "")),
        "middle": split_csv_list(record.get("타깃학교\n(중)", "")),
        # This CSV value is a generic marketing assertion, not a verified
        # school name.  Treat it exactly like missing source data.
        "high": high,
    }


def school_name_universe(
    records: Iterable[dict[str, str]],
) -> set[str]:
    result: set[str] = set()
    for record in records:
        for values in school_columns(record).values():
            result.update(values)
    return result


@lru_cache(maxsize=4)
def compiled_school_name_pattern(names: tuple[str, ...]) -> re.Pattern[str]:
    """Compile one longest-first matcher instead of scanning once per school.

    The CSV currently contains about one thousand distinct school strings.  A
    per-name regex loop made every grade leaf scan the same visible/schema text
    more than two thousand times.  Longest-first alternation preserves the
    occupied-span rule for compound CSV values such as ``A고 B고 C고`` while
    reducing each field to a single regex traversal.
    """

    alternatives = "|".join(re.escape(name) for name in names)
    return re.compile(
        rf"(?<![가-힣A-Za-z0-9])(?P<school>{alternatives})"
        r"(?:(?:입니다|에서는|으로는|까지|이며|이고|에서|으로|"
        r"은|는|이|가|을|를|과|와|도|의|로|등))?"
        r"(?![가-힣A-Za-z0-9])"
    )


def mentioned_school_names(value: str, universe: set[str]) -> set[str]:
    names = tuple(
        sorted((name for name in universe if name), key=lambda name: (-len(name), name))
    )
    if not names or not value:
        return set()
    pattern = compiled_school_name_pattern(names)
    return {match.group("school") for match in pattern.finditer(value)}


def check_school_cards(
    path: Path,
    source: str,
    record: dict[str, str],
    findings: Findings,
) -> None:
    for grade, expected in school_columns(record).items():
        match = next(
            (
                candidate
                for candidate in re.finditer(
                    r"<article\b([^>]*)>(.*?)</article>", source, re.I | re.S
                )
                if {"wawa-school-card", f"is-{grade}"}
                <= set(attrs(candidate.group(1)).get("class", "").split())
            ),
            None,
        )
        if not match:
            findings.add("school_card_missing", path, f"grade={grade}")
            continue
        card = match.group(2)
        actual: list[str] = []
        empty_texts: list[str] = []
        for span in re.finditer(r"<span\b([^>]*)>(.*?)</span>", card, re.I | re.S):
            classes = set(attrs(span.group(1)).get("class", "").split())
            text = strip_tags(span.group(2))
            if "wawa-pill" in classes:
                actual.append(text)
            if "wawa-empty" in classes:
                empty_texts.append(text)
        if expected:
            if set(actual) != set(expected):
                findings.add(
                    "school_data_mismatch",
                    path,
                    f"grade={grade} expected={expected!r} actual={actual!r}",
                )
            if empty_texts:
                findings.add(
                    "school_false_empty",
                    path,
                    f"grade={grade} expected schools but empty disclosure remains",
                )
        else:
            if actual:
                findings.add(
                    "school_unverified_names",
                    path,
                    f"grade={grade} actual={actual!r}",
                )
            if len(empty_texts) != 1 or not EMPTY_SCHOOL_TRUTH_RE.search(
                " ".join(empty_texts)
            ):
                findings.add(
                    "school_empty_not_truthful",
                    path,
                    f"grade={grade} disclosure={empty_texts!r}",
                )


GRADE_SEQUENCE = [
    *(f"초{number}" for number in range(1, 7)),
    *(f"중{number}" for number in range(1, 4)),
    *(f"고{number}" for number in range(1, 4)),
]


def expanded_grade_mentions(value: str) -> set[str]:
    result = set(GRADE_TOKEN_RE.findall(value or ""))
    for match in GRADE_RANGE_RE.finditer(value or ""):
        start = match.group(1) + match.group(2)
        end = (match.group(3) or match.group(1)) + match.group(4)
        if start in GRADE_SEQUENCE and end in GRADE_SEQUENCE:
            start_index = GRADE_SEQUENCE.index(start)
            end_index = GRADE_SEQUENCE.index(end)
            if start_index <= end_index:
                result.update(GRADE_SEQUENCE[start_index : end_index + 1])
            else:
                result.update({start, end})
    return result


def grade_subjects(record: dict[str, str], prefix: str) -> dict[str, set[str]]:
    columns = {
        "영어": "가능학년\n(영어)",
        "수학": "가능학년\n(수학)",
    }
    return {
        subject: {
            grade
            for grade in split_csv_list(record.get(column, ""))
            if re.fullmatch(rf"{prefix}[1-6]", grade)
        }
        for subject, column in columns.items()
    }


def grade_guidance_fragments(source: str) -> list[str]:
    class_names = (
        "seo-answer-section",
        "seo-checklist-section",
        "parent-faq-section",
        "parent-review-section",
    )
    blocks: list[str] = []
    for section in re.finditer(r"<section\b([^>]*)>(.*?)</section>", source, re.I | re.S):
        css_classes = set(attrs(section.group(1)).get("class", "").split())
        if css_classes.intersection(class_names):
            blocks.append(section.group(2))
    fragments: list[str] = []
    for block in blocks:
        elements = re.findall(
            r"<(?:p|li)\b[^>]*>(.*?)</(?:p|li)>", block, re.I | re.S
        )
        fragments.extend(strip_tags(item) for item in elements if strip_tags(item))
    return fragments


def check_grade_leaf_accuracy(
    path: Path,
    source: str,
    nodes: list[dict[str, Any]],
    record: dict[str, str],
    school_universe: set[str],
    findings: Findings,
) -> None:
    slug = path.parent.name
    grade_map = {
        "초등영수학원": ("초", "초등", "elementary"),
        "중등영수학원": ("중", "중등", "middle"),
        "고등영수학원": ("고", "고등", "high"),
    }
    if slug not in grade_map:
        findings.add("grade_leaf_slug", path, f"unexpected slug={slug!r}")
        return
    prefix, grade_label, school_level = grade_map[slug]
    expected_by_subject = grade_subjects(record, prefix)
    fragments = grade_guidance_fragments(source)
    guidance_text = " ".join(fragments)

    cross_level = sorted(
        grade for grade in expanded_grade_mentions(guidance_text) if not grade.startswith(prefix)
    )
    if cross_level:
        findings.add(
            "grade_leaf_cross_level",
            path,
            f"page={grade_label} other-level grades={cross_level!r}",
        )

    expected_schools = set(school_columns(record)[school_level])
    visible_schools = mentioned_school_names(guidance_text, school_universe)
    schema_text = " ".join(recursive_strings(nodes))
    schema_schools = mentioned_school_names(schema_text, school_universe)
    if visible_schools != expected_schools:
        findings.add(
            "grade_leaf_visible_school_mismatch",
            path,
            f"expected={sorted(expected_schools)!r} actual={sorted(visible_schools)!r}",
        )
    if schema_schools != expected_schools:
        findings.add(
            "grade_leaf_schema_school_mismatch",
            path,
            f"expected={sorted(expected_schools)!r} actual={sorted(schema_schools)!r}",
        )
    if not expected_schools:
        if not EMPTY_SCHOOL_TRUTH_RE.search(guidance_text):
            findings.add(
                "grade_leaf_visible_school_empty_not_truthful",
                path,
                f"{grade_label} target-school source is empty",
            )
        if not EMPTY_SCHOOL_TRUTH_RE.search(schema_text):
            findings.add(
                "grade_leaf_schema_school_empty_not_truthful",
                path,
                f"{grade_label} target-school source is empty",
            )

    availability = [
        fragment for fragment in fragments if AVAILABILITY_CUE_RE.search(fragment)
    ]
    found_claim: dict[str, bool] = {"영어": False, "수학": False}
    empty_confirmed: dict[str, bool] = {"영어": False, "수학": False}
    mismatches: dict[str, list[set[str]]] = {"영어": [], "수학": []}
    for fragment in availability:
        subject_matches = list(re.finditer(r"영어|수학", fragment))
        for index, subject_match in enumerate(subject_matches):
            subject = subject_match.group(0)
            end = (
                subject_matches[index + 1].start()
                if index + 1 < len(subject_matches)
                else len(fragment)
            )
            chunk = fragment[subject_match.start() : end]
            actual = expanded_grade_mentions(chunk)
            if actual:
                found_claim[subject] = True
                if actual != expected_by_subject[subject]:
                    mismatches[subject].append(actual)
            elif not expected_by_subject[subject] and CONSULT_CONFIRM_RE.search(fragment):
                empty_confirmed[subject] = True

    for subject, expected in expected_by_subject.items():
        if mismatches[subject]:
            findings.add(
                "grade_leaf_subject_mismatch",
                path,
                f"subject={subject} expected={sorted(expected)!r} claims="
                f"{[sorted(value) for value in mismatches[subject]]!r}",
            )
        if expected and not found_claim[subject]:
            findings.add(
                "grade_leaf_subject_missing",
                path,
                f"subject={subject} expected={sorted(expected)!r}",
            )
        if not expected and not empty_confirmed[subject]:
            findings.add(
                "grade_leaf_empty_not_truthful",
                path,
                f"subject={subject} {grade_label} source grades are empty",
            )

    empty_subjects = {
        subject for subject, expected in expected_by_subject.items() if not expected
    }
    if empty_subjects:
        for item in recursive_dicts(nodes):
            if not ({"Service", "Offer"} & node_types(item)):
                continue
            text_value = " ".join(recursive_strings(item))
            assertion = ASSERTIVE_AVAILABILITY_RE.search(text_value)
            if not assertion or CONSULT_CONFIRM_RE.search(text_value):
                continue
            mentioned = {
                subject for subject in empty_subjects if subject in text_value
            }
            if not mentioned and grade_label in text_value:
                mentioned = set(empty_subjects)
            if mentioned:
                findings.add(
                    "grade_leaf_schema_availability_contradiction",
                    path,
                    f"subjects={sorted(mentioned)!r} phrase={assertion.group(0)!r}",
                )
                break


def check_fee_source(
    path: Path,
    source: str,
    nodes: list[dict[str, Any]],
    record: dict[str, str],
    findings: Findings,
) -> None:
    fee_url = record.get("센터 교습비", "").strip()
    links: list[tuple[str, str, str]] = []
    for match in re.finditer(r"<a\b([^>]*)>(.*?)</a>", source, re.I | re.S):
        data = attrs(match.group(1))
        links.append(
            (
                html.unescape(data.get("href", "")).strip(),
                strip_tags(match.group(2)),
                data.get("class", ""),
            )
        )
    fee_links = [
        item
        for item in links
        if "교습비" in item[1]
        or "수강료" in item[1]
        or "tuition" in item[2].lower()
    ]
    if fee_url:
        if not any(href == fee_url for href, _label, _css_class in links):
            findings.add(
                "fee_source_link_missing",
                path,
                f"expected CSV link={fee_url!r}",
            )
        return

    if fee_links:
        findings.add(
            "fee_link_without_source",
            path,
            f"links={[(href, label) for href, label, _ in fee_links]!r}",
        )
    visible_text = strip_tags(SCRIPT_STYLE_RE.sub(" ", source))
    truthful = False
    for match in re.finditer(r"교습비|수강료", visible_text):
        window = visible_text[max(0, match.start() - 100) : match.end() + 320]
        source_absent = re.search(
            r"(?:링크|자료).{0,70}(?:없|확인되지\s*않|제공되지\s*않)|"
            r"(?:없|확인되지\s*않|제공되지\s*않).{0,70}(?:링크|자료)",
            window,
            re.S,
        )
        if source_absent and CONSULT_CONFIRM_RE.search(window):
            truthful = True
            break
    if not truthful:
        findings.add(
            "fee_empty_not_truthful",
            path,
            "CSV fee link is empty; disclose source absence and consultation confirmation",
        )
    unsupported_fee_schema = any(
        "OfferCatalog" in node_types(item)
        or "price" in item
        or "priceCurrency" in item
        for item in recursive_dicts(nodes)
    )
    if unsupported_fee_schema:
        findings.add(
            "fee_schema_without_source",
            path,
            "OfferCatalog/price exists despite an empty CSV fee source",
        )


def reference_id(value: Any) -> str:
    return str(value.get("@id", "")) if isinstance(value, dict) else ""


def check_detail_jsonld(
    path: Path,
    source: str,
    nodes: list[dict[str, Any]],
    canonical: str,
    record: dict[str, str],
    findings: Findings,
) -> tuple[tuple[str, str, str], str, str] | None:
    present: set[str] = set()
    for node in nodes:
        present.update(node_types(node))
    missing = REQUIRED_DETAIL_TYPES - present
    if missing:
        findings.add("jsonld_detail_types", path, f"missing={sorted(missing)}")
    if any(
        "Review" in node_types(item)
        or "aggregateRating" in item
        or "review" in item
        for item in recursive_dicts(nodes)
    ):
        findings.add("unsupported_review_schema", path, "Review/rating schema present")

    visible_pairs = visible_faq(source)
    schema_pairs = schema_faq(nodes)
    if visible_pairs != schema_pairs:
        findings.add(
            "faq_visible_schema_mismatch",
            path,
            f"visible={len(visible_pairs)} schema={len(schema_pairs)}",
        )
    if len(visible_pairs) < 3:
        findings.add("faq_too_few", path, f"visible FAQ={len(visible_pairs)}")

    organizations = [node for node in nodes if "LocalBusiness" in node_types(node)]
    if len(organizations) != 1:
        findings.add(
            "center_jsonld_count", path, f"LocalBusiness nodes={len(organizations)}"
        )
    organization = organizations[0] if organizations else {}
    if not organization:
        return None
    organization_id = str(organization.get("@id", "")).strip()
    if not organization_id.startswith(BASE_URL + "/"):
        findings.add("center_id_invalid", path, f"@id={organization_id!r}")
    if organization_id == ROOT_ORGANIZATION_ID:
        findings.add("center_id_invalid", path, "physical center reuses root @id")
    if reference_id(organization.get("branchOf")) != ROOT_ORGANIZATION_ID:
        findings.add(
            "center_branch_reference_mismatch",
            path,
            f"branchOf={reference_id(organization.get('branchOf'))!r} expected="
            f"{ROOT_ORGANIZATION_ID!r}",
        )
    organization_url = str(organization.get("url", "")).strip()
    if not organization_url.startswith(BASE_URL + "/"):
        findings.add("center_url_invalid", path, f"url={organization_url!r}")
    unsupported_contact = sorted(
        {
            prop
            for item in organizations
            for prop in ("telephone", "openingHours", "contactPoint")
            if prop in item
        }
    )
    if unsupported_contact:
        findings.add(
            "center_jsonld_unsupported_contact",
            path,
            f"CSV has no source for properties={unsupported_contact!r}",
        )

    expected_name = record.get("센터명", "").strip()
    expected_address = record.get("센터 주소", "").strip()
    expected_registration = record.get("교육지원청 등록번호", "").strip()
    visible_text = strip_tags(SCRIPT_STYLE_RE.sub(" ", source))
    for label, expected_value in (
        ("name", expected_name),
        ("address", expected_address),
        ("registration", expected_registration),
    ):
        if expected_value and expected_value not in visible_text:
            findings.add(
                "center_visible_fact_missing",
                path,
                f"{label}={expected_value!r}",
            )
    address = organization.get("address", {})
    actual_address = (
        str(address.get("streetAddress", "")).strip() if isinstance(address, dict) else ""
    )
    identifier = organization.get("identifier", {})
    actual_registration = (
        str(identifier.get("value", "")).strip()
        if isinstance(identifier, dict)
        else ""
    )
    if expected_name and organization.get("name") != expected_name:
        findings.add(
            "center_jsonld_name",
            path,
            f"expected={expected_name!r} actual={organization.get('name')!r}",
        )
    if expected_address and actual_address != expected_address:
        findings.add(
            "center_jsonld_address",
            path,
            f"expected={expected_address!r} actual={actual_address!r}",
        )
    address_tokens = expected_address.split()
    if len(address_tokens) < 2:
        findings.add(
            "reference_address_invalid",
            path,
            f"CSV address={expected_address!r}",
        )
    elif isinstance(address, dict):
        expected_region = ADDRESS_REGION_NAMES.get(address_tokens[0], "")
        expected_locality = (
            SEJONG_CENTER_LOCALITY
            if address_tokens[0] == "세종특별자치시"
            else address_tokens[1]
        )
        if not expected_region:
            findings.add(
                "reference_address_region_unknown",
                path,
                f"first token={address_tokens[0]!r}",
            )
        elif address.get("addressRegion") != expected_region:
            findings.add(
                "postal_address_region",
                path,
                f"actual={address.get('addressRegion')!r} expected={expected_region!r}",
            )
        if address.get("addressLocality") != expected_locality:
            findings.add(
                "postal_address_locality",
                path,
                f"actual={address.get('addressLocality')!r} expected={expected_locality!r}",
            )
    else:
        findings.add("postal_address_missing", path, f"address={address!r}")
    if expected_registration and actual_registration != expected_registration:
        findings.add(
            "center_jsonld_registration",
            path,
            f"expected={expected_registration!r} actual={actual_registration!r}",
        )
    if expected_registration and (
        not isinstance(identifier, dict)
        or identifier.get("@type") != "PropertyValue"
        or identifier.get("propertyID") != "교육지원청 등록번호"
    ):
        findings.add(
            "center_jsonld_identifier",
            path,
            f"identifier={identifier!r}",
        )

    web_page = next((node for node in nodes if "WebPage" in node_types(node)), {})
    web_page_id = str(web_page.get("@id", "")) if isinstance(web_page, dict) else ""
    expected_web_page_id = canonical + "#webpage" if canonical else ""
    if web_page_id != expected_web_page_id:
        findings.add(
            "webpage_id_mismatch",
            path,
            f"actual={web_page_id!r} expected={expected_web_page_id!r}",
        )
    service_nodes = [node for node in nodes if "Service" in node_types(node)]
    service_id = str(service_nodes[0].get("@id", "")) if service_nodes else ""
    for node in nodes:
        types = node_types(node)
        if "WebPage" in types:
            if node.get("url") != canonical:
                findings.add(
                    "jsonld_page_url", path, f"WebPage.url={node.get('url')!r}"
                )
            for property_name in ("author", "publisher"):
                if reference_id(node.get(property_name)) != ROOT_ORGANIZATION_ID:
                    findings.add(
                        "root_reference_mismatch",
                        path,
                        f"WebPage.{property_name}="
                        f"{reference_id(node.get(property_name))!r} expected="
                        f"{ROOT_ORGANIZATION_ID!r}",
                    )
            if reference_id(node.get("mainEntity")) != service_id:
                findings.add(
                    "webpage_main_entity_mismatch",
                    path,
                    f"actual={reference_id(node.get('mainEntity'))!r} "
                    f"expected={service_id!r}",
                )
        if "Article" in types:
            for property_name in ("author", "publisher"):
                if reference_id(node.get(property_name)) != ROOT_ORGANIZATION_ID:
                    findings.add(
                        "root_reference_mismatch",
                        path,
                        f"Article.{property_name}="
                        f"{reference_id(node.get(property_name))!r} expected="
                        f"{ROOT_ORGANIZATION_ID!r}",
                    )
            if reference_id(node.get("mainEntityOfPage")) != web_page_id:
                findings.add(
                    "article_main_entity_mismatch",
                    path,
                    f"actual={reference_id(node.get('mainEntityOfPage'))!r} "
                    f"expected={web_page_id!r}",
                )
        if "Service" in types and reference_id(node.get("provider")) != organization_id:
            findings.add(
                "center_reference_mismatch",
                path,
                f"Service.provider={reference_id(node.get('provider'))!r}",
            )

    center_key = (expected_name, expected_address, expected_registration)
    return center_key, organization_id, organization_url


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--baseline",
        type=Path,
        default=DEFAULT_BASELINE,
        help="immutable 4,743-URL manifest outside the repository",
    )
    parser.add_argument(
        "--sample-limit",
        type=int,
        default=5,
        help="maximum sample messages printed for each error code",
    )
    args = parser.parse_args()
    findings = Findings(sample_limit=max(1, args.sample_limit))
    baseline = load_baseline(args.baseline.resolve(), findings)

    public_pages = public_index_pages()
    public_files = [path.relative_to(ROOT).as_posix() for path in public_pages]
    public_folder_urls = [page_url(path) for path in public_pages]
    current_canonicals: list[str] = []
    sources: dict[Path, str] = {}

    for path in public_pages:
        source = path.read_text(encoding="utf-8")
        sources[path] = source
        canonical = canonical_values(source)
        og_url = meta_values(source, "property", "og:url")
        expected = page_url(path)
        if len(canonical) != 1:
            findings.add("canonical_count", path, f"count={len(canonical)}")
        else:
            current_canonicals.append(canonical[0])
            if canonical[0] != expected:
                findings.add(
                    "canonical_folder_mismatch",
                    path,
                    f"canonical={canonical[0]!r} expected={expected!r}",
                )
        if len(og_url) != 1 or not canonical or og_url[0] != canonical[0]:
            findings.add(
                "canonical_og_mismatch",
                path,
                f"canonical={canonical!r} og:url={og_url!r}",
            )

    current_sitemap_urls = sitemap_urls(findings)
    if len(public_pages) != EXPECTED_PUBLIC_COUNT:
        findings.add(
            "public_count",
            "collection",
            f"files={len(public_pages)} expected={EXPECTED_PUBLIC_COUNT}",
        )
    if len(current_canonicals) != len(set(current_canonicals)):
        findings.add(
            "canonical_duplicates",
            "collection",
            f"duplicates={len(current_canonicals)-len(set(current_canonicals))}",
        )
    current_url_sets_equal = (
        set(public_folder_urls)
        == set(current_canonicals)
        == set(current_sitemap_urls)
    )
    if not current_url_sets_equal:
        findings.add(
            "current_url_sets_differ",
            "collection",
            "folder/canonical/sitemap sets are not identical",
        )
    baseline_sets_unchanged = False
    if baseline:
        baseline_sets_unchanged = (
            set(public_files) == set(baseline["files"])
            and set(public_folder_urls) == set(baseline["folder_urls"])
            and set(current_canonicals) == set(baseline["canonicals"])
            and set(current_sitemap_urls) == set(baseline["sitemap_urls"])
        )
        findings.compare_set("baseline_files_changed", public_files, baseline["files"])
        findings.compare_set(
            "baseline_folders_changed", public_folder_urls, baseline["folder_urls"]
        )
        findings.compare_set(
            "baseline_canonicals_changed", current_canonicals, baseline["canonicals"]
        )
        findings.compare_set(
            "baseline_sitemap_changed",
            current_sitemap_urls,
            baseline["sitemap_urls"],
        )

    national_pages = [
        path
        for path in public_pages
        if path == NATIONAL_ROOT / "index.html" or NATIONAL_ROOT in path.parents
    ]
    depths = Counter(
        len(path.parent.relative_to(NATIONAL_ROOT).parts) for path in national_pages
    )
    if len(national_pages) != 1_574:
        findings.add(
            "national_count",
            "전국학원",
            f"pages={len(national_pages)} expected=1574",
        )
    if dict(depths) != EXPECTED_NATIONAL_DEPTHS:
        findings.add(
            "national_depth_counts",
            "전국학원",
            f"actual={dict(sorted(depths.items()))} expected={EXPECTED_NATIONAL_DEPTHS}",
        )

    centers = center_records(findings)
    expected_entities, expected_entity_kinds = expected_center_entities(
        centers, findings
    )
    all_school_names = school_name_universe(centers.values())
    center_ids: defaultdict[tuple[str, str, str], set[str]] = defaultdict(set)
    center_urls: defaultdict[tuple[str, str, str], set[str]] = defaultdict(set)
    id_centers: defaultdict[str, set[tuple[str, str, str]]] = defaultdict(set)
    url_centers: defaultdict[str, set[tuple[str, str, str]]] = defaultdict(set)
    national_titles: defaultdict[str, list[Path]] = defaultdict(list)
    national_h1s: defaultdict[str, list[Path]] = defaultdict(list)
    national_descriptions: defaultdict[str, list[Path]] = defaultdict(list)
    sejong_pages = 0

    for path in national_pages:
        source = sources[path]
        relative_parts = path.parent.relative_to(NATIONAL_ROOT).parts
        depth = len(relative_parts)
        is_detail = depth in DETAIL_DEPTHS
        canonical = canonical_values(source)
        canonical_value = canonical[0] if len(canonical) == 1 else ""

        title_matches = re.findall(r"<title>(.*?)</title>", source, re.I | re.S)
        h1_matches = re.findall(r"<h1\b[^>]*>(.*?)</h1>", source, re.I | re.S)
        descriptions = meta_values(source, "name", "description")
        og_descriptions = meta_values(source, "property", "og:description")
        if len(title_matches) != 1:
            findings.add("title_count", path, f"count={len(title_matches)}")
        else:
            national_titles[strip_tags(title_matches[0])].append(path)
        if len(h1_matches) != 1:
            findings.add("h1_count", path, f"count={len(h1_matches)}")
        else:
            national_h1s[strip_tags(h1_matches[0])].append(path)
        if len(descriptions) != 1 or not descriptions[0].strip():
            findings.add("description_count", path, f"count={len(descriptions)}")
        else:
            description = html.unescape(descriptions[0]).strip()
            national_descriptions[re.sub(r"\s+", " ", description)].append(path)
            if len(description) > 80:
                findings.add(
                    "description_too_long", path, f"length={len(description)}"
                )
            if (
                len(og_descriptions) != 1
                or html.unescape(og_descriptions[0]).strip() != description
            ):
                findings.add(
                    "description_og_mismatch",
                    path,
                    f"meta={descriptions!r} og={og_descriptions!r}",
                )

        visible_source = SCRIPT_STYLE_RE.sub(" ", source)
        visible_text = strip_tags(visible_source)
        if re.search(
            r"<strong\b[^>]*>\s*교육지원청\s*</strong>\s*:",
            visible_source,
            re.I | re.S,
        ):
            findings.add(
                "wrong_education_office_label", path, "교육지원청 label contains academy name"
            )
        grammar_record = re.search(r"기록(?:와|를)", source)
        if grammar_record:
            findings.add(
                "grammar_record_particle",
                path,
                f"phrase={grammar_record.group(0)!r}",
            )
        if re.search(r"(?:초|고)이\s*포함", source):
            findings.add("grammar_school_particle", path, "'초이/고이 포함' remains")
        if OVERCLAIM_RE.search(visible_text):
            findings.add(
                "unsupported_outcome_claim",
                path,
                f"scope=visible phrase={OVERCLAIM_RE.search(visible_text).group(0)!r}",
            )
        if OLD_GRADE_CTA_RE.search(visible_text):
            findings.add(
                "old_grade_cta",
                path,
                f"phrase={OLD_GRADE_CTA_RE.search(visible_text).group(0)!r}",
            )
        if depth == 4 and "영어·수학 학습 상담" not in visible_text:
            findings.add(
                "grade_cta_missing_subjects",
                path,
                "expected '영어·수학 학습 상담'",
            )
        if OLD_FEE_PLACEHOLDER_RE.search(visible_text):
            findings.add(
                "old_fee_placeholder",
                path,
                f"phrase={OLD_FEE_PLACEHOLDER_RE.search(visible_text).group(0)!r}",
            )
        if any(
            "article-main" in set(attrs(tag).get("class", "").split())
            for tag in re.findall(r"<section\b([^>]*)>", source, re.I)
        ):
            findings.add(
                "legacy_article_main",
                path,
                '<section class="article-main"> remains',
            )
        if PLACEHOLDER_RE.search(visible_text):
            findings.add(
                "placeholder",
                path,
                f"phrase={PLACEHOLDER_RE.search(visible_text).group(0)!r}",
            )
        generic_school = GENERIC_ALL_HIGH_SCHOOL_RE.search(visible_text)
        if generic_school:
            findings.add(
                "generic_all_high_school_claim",
                path,
                f"scope=visible phrase={generic_school.group(0)!r}",
            )
        hidden_generated_found = False
        for tag in re.findall(r"<img\b[^>]*>", source, re.I):
            data = attrs(tag)
            css_class = data.get("class", "").lower()
            style = data.get("style", "").lower().replace(" ", "")
            if "generated" in css_class and (
                "hidden" in css_class
                or "hidden" in data
                or re.search(r"\shidden(?:\s|/?>)", tag, re.I)
                or "display:none" in style
                or "visibility:hidden" in style
            ):
                hidden_generated_found = True
        if hidden_generated_found:
            findings.add(
                "hidden_generated_image_dom", path, "hidden generated-image DOM remains"
            )

        nodes = parse_jsonld(path, source, findings)
        description_claim = next(
            (
                match
                for description in jsonld_descriptions(nodes)
                if (match := OVERCLAIM_RE.search(description))
            ),
            None,
        )
        if description_claim:
            findings.add(
                "unsupported_outcome_claim",
                path,
                f"scope=JSON-LD description phrase={description_claim.group(0)!r}",
            )
        json_generic = next(
            (
                match
                for value in recursive_strings(nodes)
                if (match := GENERIC_ALL_HIGH_SCHOOL_RE.search(value))
            ),
            None,
        )
        if json_generic:
            findings.add(
                "generic_all_high_school_claim",
                path,
                f"scope=JSON-LD phrase={json_generic.group(0)!r}",
            )
        present_types: set[str] = set()
        for node in nodes:
            present_types.update(node_types(node))
        required = REQUIRED_DETAIL_TYPES if is_detail else REQUIRED_HUB_TYPES
        missing_types = required - present_types
        if missing_types:
            findings.add(
                "jsonld_required_types", path, f"missing={sorted(missing_types)}"
            )
        for required_type in required:
            count = sum(required_type in node_types(node) for node in nodes)
            if required_type != "ItemList" and count > 1:
                findings.add(
                    "jsonld_type_count",
                    path,
                    f"type={required_type} count={count} expected at most 1",
                )
        if is_detail:
            check_schema_visible_sections(path, source, nodes, findings)

        visible_crumbs = visible_breadcrumb_entries(source)
        schema_crumbs = schema_breadcrumb_entries(nodes)
        visible_crumb_names = [entry["name"] for entry in visible_crumbs]
        schema_crumb_names = [str(entry["name"]) for entry in schema_crumbs]
        if visible_crumb_names != schema_crumb_names:
            findings.add(
                "breadcrumb_visible_schema_mismatch",
                path,
                f"visible={visible_crumb_names!r} schema={schema_crumb_names!r}",
            )
        check_breadcrumb_hierarchy(
            path, source, visible_crumbs, schema_crumbs, findings
        )

        if relative_parts[:2] == SEJONG_PREFIX:
            sejong_pages += 1
            authoritative_street_addresses: set[str] = set()
            if len(relative_parts) >= 3:
                sejong_record = centers.get(
                    (
                        relative_parts[0],
                        relative_parts[1],
                        normalize_neighborhood(relative_parts[2]),
                    )
                )
                if sejong_record:
                    authoritative_address = sejong_record.get("센터 주소", "").strip()
                    if authoritative_address:
                        authoritative_street_addresses.add(authoritative_address)
            check_sejong(
                path,
                source,
                nodes,
                authoritative_street_addresses,
                findings,
            )
        if relative_parts == ("충청",):
            check_sejong_region_hub(path, source, nodes, findings)

        if is_detail:
            key = (
                relative_parts[0],
                relative_parts[1],
                normalize_neighborhood(relative_parts[2]),
            )
            record = centers.get(key)
            if not record:
                findings.add("center_record_missing", path, f"key={key!r}")
            else:
                check_school_cards(path, source, record, findings)
                check_fee_source(path, source, nodes, record, findings)
                check_locality_display(path, source, nodes, record, findings)
                if depth == 4:
                    check_grade_leaf_accuracy(
                        path,
                        source,
                        nodes,
                        record,
                        all_school_names,
                        findings,
                    )
                center_result = check_detail_jsonld(
                    path,
                    source,
                    nodes,
                    canonical_value,
                    record,
                    findings,
                )
                if center_result:
                    center_key, organization_id, organization_url = center_result
                    center_ids[center_key].add(organization_id)
                    center_urls[center_key].add(organization_url)
                    id_centers[organization_id].add(center_key)
                    url_centers[organization_url].add(center_key)

        check_links_and_images(path, source, nodes, is_detail, findings)

    if sejong_pages != 9:
        findings.add(
            "sejong_page_count", "전국학원/충청/새롬중앙로", f"pages={sejong_pages} expected=9"
        )
    for code, values in (
        ("duplicate_title", national_titles),
        ("duplicate_h1", national_h1s),
        ("duplicate_description", national_descriptions),
    ):
        for value, paths in values.items():
            if value and len(paths) > 1:
                findings.add(
                    code,
                    "전국학원",
                    f"count={len(paths)} value={value!r} "
                    f"pages={[path.relative_to(ROOT).as_posix() for path in paths[:3]]!r}",
                )
    for center_key, identifiers in center_ids.items():
        if len(identifiers) != 1:
            findings.add(
                "center_id_not_stable",
                "center entity",
                f"center={center_key!r} ids={sorted(identifiers)!r}",
            )
        urls = center_urls[center_key]
        if len(urls) != 1:
            findings.add(
                "center_url_not_stable",
                "center entity",
                f"center={center_key!r} urls={sorted(urls)!r}",
            )
        expected_identity = expected_entities.get(center_key)
        if expected_identity and identifiers != {expected_identity[0]}:
            findings.add(
                "center_id_not_authoritative",
                "center entity",
                f"center={center_key!r} actual={sorted(identifiers)!r} "
                f"expected={expected_identity[0]!r}",
            )
        if expected_identity and urls != {expected_identity[1]}:
            findings.add(
                "center_url_not_authoritative",
                "center entity",
                f"center={center_key!r} actual={sorted(urls)!r} "
                f"expected={expected_identity[1]!r}",
            )
    for identifier, keys in id_centers.items():
        if identifier and len(keys) != 1:
            findings.add(
                "center_id_collision",
                "center entity",
                f"id={identifier!r} centers={sorted(keys)!r}",
            )
    for organization_url, keys in url_centers.items():
        if organization_url and len(keys) != 1:
            findings.add(
                "center_url_collision",
                "center entity",
                f"url={organization_url!r} centers={sorted(keys)!r}",
            )
    if len(center_ids) != 188:
        findings.add(
            "physical_center_count",
            "center entity",
            f"physical centers={len(center_ids)} expected=188",
        )
    unique_center_ids = {identifier for values in center_ids.values() for identifier in values}
    unique_center_urls = {value for values in center_urls.values() for value in values}
    if len(unique_center_ids) != 188:
        findings.add(
            "organization_id_count",
            "center entity",
            f"unique ids={len(unique_center_ids)} expected=188",
        )
    if len(unique_center_urls) != 188:
        findings.add(
            "organization_url_count",
            "center entity",
            f"unique urls={len(unique_center_urls)} expected=188",
        )

    print(f"baseline={args.baseline.resolve()}")
    print(f"baseline_loaded={bool(baseline)}")
    print(f"baseline_sets_unchanged={baseline_sets_unchanged}")
    print(f"current_url_sets_equal={current_url_sets_equal}")
    print(f"public_pages={len(public_pages)}")
    print(f"sitemap_urls={len(current_sitemap_urls)}")
    print(f"national_pages={len(national_pages)}")
    print(f"national_depths={dict(sorted(depths.items()))}")
    print(f"physical_centers={len(center_ids)}")
    print(f"organization_ids={len(unique_center_ids)}")
    print(f"organization_urls={len(unique_center_urls)}")
    print(f"expected_center_entity_kinds={dict(expected_entity_kinds)}")
    print(f"sejong_pages={sejong_pages}")
    return findings.report()


if __name__ == "__main__":
    raise SystemExit(main())
