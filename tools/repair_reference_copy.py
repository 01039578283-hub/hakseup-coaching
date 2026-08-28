from __future__ import annotations

"""Repair two source-copy defects without changing routes or page design.

The evidence CSV remains byte-for-byte unchanged.  Presentation corrections are
kept in versioned code so the raw source can still be audited, while current and
future generated pages receive readable location notes and independently
confirmed school names.

The default mode is a full in-memory dry run.  ``--apply`` writes only verified
HTML documents under ``전국학원`` and ``과목별학원`` plus their sitemap dates.
"""

import argparse
import copy
import html
import json
import os
import re
import tempfile
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence

try:
    from source_copy_utils import (
        LOCATION_NOTE_CORRECTIONS,
        VERIFIED_SCHOOL_SOURCE_CORRECTIONS,
    )
except ModuleNotFoundError:  # package import
    from .source_copy_utils import (
        LOCATION_NOTE_CORRECTIONS,
        VERIFIED_SCHOOL_SOURCE_CORRECTIONS,
    )


ROOT = Path(__file__).resolve().parents[1]
REPAIR_DATE = "2026-08-28"
SITE_ROOTS = ("전국학원", "과목별학원")
SUBJECT_CATEGORIES = (
    "고등수학학원",
    "고등영어학원",
    "고등학생학원",
    "영수학원",
    "중등수학학원",
    "중등영어학원",
    "중학생학원",
    "초등학생학원",
)
LOCATION_LOCALITIES = {
    next(new for old, new in LOCATION_NOTE_CORRECTIONS.items() if old.startswith("경기도 하남시")): ("덕풍동",),
    next(new for old, new in LOCATION_NOTE_CORRECTIONS.items() if old.startswith("북일프라자")): ("송도동",),
    next(new for old, new in LOCATION_NOTE_CORRECTIONS.items() if old.startswith("광주광역시")): (
        "산월동",
        "쌍암동",
        "월계동",
        "첨단",
        "첨단지구",
    ),
    next(new for old, new in LOCATION_NOTE_CORRECTIONS.items() if old.startswith("경기 김포시")): ("운양동",),
    next(new for old, new in LOCATION_NOTE_CORRECTIONS.items() if old.startswith("경기도 광명시")): ("철산동", "하안동"),
    next(new for old, new in LOCATION_NOTE_CORRECTIONS.items() if old.startswith("경기 남양주시")): ("호평동",),
}
LOCATION_CENTER_PROFILES = {
    "덕풍동": "하남풍산점",
    "송도동": "웰카운티점",
    "산월동": "첨단점",
    "쌍암동": "첨단점",
    "월계동": "첨단점",
    "첨단": "첨단점",
    "첨단지구": "첨단점",
    "운양동": "운양점",
    "철산동": "철산점",
    "하안동": "철산점",
    "호평동": "호평점",
}
_CROSS_LEVEL_TOKEN = "오현초호매실중"
FUSED_SCHOOLS = {
    **VERIFIED_SCHOOL_SOURCE_CORRECTIONS,
    # Materialized HTML contains the first two names as one atomic token even
    # though the complete CSV cell also includes three comma-delimited schools.
    _CROSS_LEVEL_TOKEN: ("오현초", "호매실중"),
}

# Exact locality/level projections.  Keeping the level boundary here prevents
# the elementary school 오현초 from being presented as a middle school.
SCHOOL_CORRECTIONS_BY_LOCALITY = {
    "성사동": {
        "elementary": FUSED_SCHOOLS["성라초 성사초"],
        "middle": FUSED_SCHOOLS["화수중 성사중 원당중"],
        "high": FUSED_SCHOOLS["성사고 화수고"],
    },
    "주교동": {
        "elementary": FUSED_SCHOOLS["성라초 성사초"],
        "middle": FUSED_SCHOOLS["화수중 성사중 원당중"],
        "high": FUSED_SCHOOLS["성사고 화수고"],
    },
    "진접읍": {
        "elementary": FUSED_SCHOOLS["해밀초 화봉초"],
        "middle": FUSED_SCHOOLS["풍양중 주곡중"],
        "high": FUSED_SCHOOLS["진접고 오남고"],
    },
    "부천상동": {
        "elementary": FUSED_SCHOOLS["석천초 상인초"],
        "middle": FUSED_SCHOOLS["석천중 상동중 상일중 부인중"],
        "high": FUSED_SCHOOLS["상동고 상일고 상원고 중흥고 중원고"],
    },
    **{
        locality: {
            "elementary": FUSED_SCHOOLS["이화초 가내초 자란초"],
            "middle": FUSED_SCHOOLS["비전중 한광중 한광여중 평택여중 소사벌중"],
            "high": FUSED_SCHOOLS["비전고 한광고 한광여고 평택여고"],
        }
        for locality in ("비전동", "소사벌", "죽백동", "동삭동")
    },
    **{
        locality: {
            "middle": FUSED_SCHOOLS["수곡중 산남중"],
            "high": FUSED_SCHOOLS["충북고 운호고 충북여고 산남고"],
        }
        for locality in ("산남동", "수곡동")
    },
    **{
        locality: {"middle": FUSED_SCHOOLS["학남중 강북중"]}
        for locality in ("도남동", "국우동", "도남지구")
    },
    **{
        locality: {
            "elementary": FUSED_SCHOOLS["양덕초 양서초 장흥초"],
            "middle": FUSED_SCHOOLS["양덕중 장흥중 대도중 환호여중"],
            "high": FUSED_SCHOOLS["장성고 포고 포여고 유성여고"],
        }
        for locality in ("양덕동", "장량동")
    },
    "호매실": {
        "elementary": ("오현초",),
        "middle": ("호매실중", "능실중", "영신중", "고색중"),
    },
    "수원금곡동": {
        "elementary": ("오현초",),
        "middle": ("호매실중", "능실중", "영신중", "고색중"),
    },
}


def _school_names(levels: dict[str, tuple[str, ...]]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(name for names in levels.values() for name in names))


SCHOOL_LOCALITIES = {
    locality: _school_names(levels)
    for locality, levels in SCHOOL_CORRECTIONS_BY_LOCALITY.items()
}
SCHOOL_NATIONAL_SLUGS = {
    "부천상동": "부천-상동",
    "수원금곡동": "수원-금곡동",
}
SCHOOL_CENTER_LOCALITIES = {
    "원당점": ("성사동", "주교동"),
    "진접점": ("진접읍",),
    "상동점": ("부천상동",),
    "비전점": ("비전동", "소사벌", "죽백동", "동삭동"),
    "산남점": ("산남동", "수곡동"),
    "대구도남점": ("도남동", "국우동", "도남지구"),
    "양덕점": ("양덕동", "장량동"),
    "서수원점": ("호매실", "수원금곡동"),
}
SCHOOL_CENTER_PROFILES = {
    profile: tuple(
        dict.fromkeys(
            name
            for locality in localities
            for name in SCHOOL_LOCALITIES[locality]
        )
    )
    for profile, localities in SCHOOL_CENTER_LOCALITIES.items()
}
NEW_SCHOOL_PAGE_CATEGORIES = (
    "초등학생학원",
    "중학생학원",
    "중등수학학원",
    "중등영어학원",
    "고등학생학원",
    "영수학원",
)
NEW_LEVELS_BY_CATEGORY = {
    "초등학생학원": ("elementary", "middle"),
    "중학생학원": ("elementary", "middle"),
    "중등수학학원": ("middle",),
    "중등영어학원": ("middle",),
    "고등학생학원": ("elementary", "middle"),
    "영수학원": ("elementary", "middle"),
}
HIGH_SCHOOL_PAGE_CATEGORIES = (
    "고등수학학원",
    "고등영어학원",
    "고등학생학원",
    "영수학원",
    "중학생학원",
    "초등학생학원",
)
SOURCE_CHIP_CATEGORIES = {
    "elementary": ("초등학생학원", "영수학원"),
    "middle": ("중학생학원", "중등수학학원", "중등영어학원", "영수학원"),
    "high": ("고등학생학원", "고등수학학원", "고등영어학원", "영수학원"),
}

JSONLD_RE = re.compile(
    r'(<script\b[^>]*type=["\']application/ld\+json["\'][^>]*>)(.*?)(</script>)',
    re.I | re.S,
)
CANONICAL_RE = re.compile(
    r'<link\b(?=[^>]*\brel=["\']canonical["\'])[^>]*\bhref=["\']([^"\']+)',
    re.I | re.S,
)
TITLE_RE = re.compile(r"<title>(.*?)</title>", re.I | re.S)
H1_RE = re.compile(r"<h1\b[^>]*>(.*?)</h1>", re.I | re.S)
META_DESCRIPTION_RE = re.compile(
    r'<meta\b(?=[^>]*\bname=["\']description["\'])[^>]*\bcontent=["\']([^"\']*)',
    re.I | re.S,
)
OG_TITLE_RE = re.compile(
    r'<meta\b(?=[^>]*\bproperty=["\']og:title["\'])[^>]*\bcontent=["\']([^"\']*)',
    re.I | re.S,
)
TWITTER_TITLE_RE = re.compile(
    r'<meta\b(?=[^>]*\bname=["\']twitter:title["\'])[^>]*\bcontent=["\']([^"\']*)',
    re.I | re.S,
)
URL_BLOCK_RE = re.compile(r"<url>.*?</url>", re.S)
LOC_RE = re.compile(r"<loc>(.*?)</loc>", re.S)
LASTMOD_RE = re.compile(r"(<lastmod>)(.*?)(</lastmod>)", re.S)


class RepairError(RuntimeError):
    pass


@dataclass(frozen=True)
class PagePlan:
    path: Path
    before: str
    after: str
    location_changes: int
    school_changes: int
    jsonld_scripts: int

    @property
    def changed(self) -> bool:
        return self.before != self.after


def type_values(node: dict[str, Any]) -> set[str]:
    value = node.get("@type")
    if isinstance(value, list):
        return {str(item) for item in value}
    return {str(value)} if value else set()


def replace_school_text(value: str) -> str:
    for fused, names in FUSED_SCHOOLS.items():
        value = value.replace(fused, ", ".join(names))
    return value


def transform_schema(value: Any, bump_date: bool = False) -> Any:
    if isinstance(value, str):
        return replace_school_text(value)
    if isinstance(value, list):
        result: list[Any] = []
        for item in value:
            if isinstance(item, dict):
                fused = item.get("name")
                if fused in FUSED_SCHOOLS and type_values(item) & {
                    "EducationalOrganization",
                    "School",
                    "ElementarySchool",
                    "MiddleSchool",
                    "HighSchool",
                    "ListItem",
                }:
                    for name in FUSED_SCHOOLS[str(fused)]:
                        replacement = copy.deepcopy(item)
                        replacement["name"] = name
                        result.append(transform_schema(replacement, bump_date))
                    continue
            result.append(transform_schema(item, bump_date))
        return result
    if isinstance(value, dict):
        result = {
            key: transform_schema(item, bump_date)
            for key, item in value.items()
        }
        elements = result.get("itemListElement")
        if isinstance(elements, list):
            for position, item in enumerate(elements, start=1):
                if isinstance(item, dict) and "position" in item:
                    item["position"] = position
            if "numberOfItems" in result:
                result["numberOfItems"] = len(elements)
        if bump_date and "dateModified" in result:
            result["dateModified"] = max(str(result["dateModified"]), REPAIR_DATE)
        return result
    return value


def rewrite_jsonld(source: str, bump_date: bool) -> tuple[str, int, int]:
    scripts = 0
    changed = 0

    def replace(match: re.Match[str]) -> str:
        nonlocal scripts, changed
        scripts += 1
        try:
            data = json.loads(match.group(2))
        except json.JSONDecodeError as exc:
            raise RepairError(f"JSON-LD parse failure: {exc}") from exc
        transformed = transform_schema(data, bump_date)
        if transformed == data:
            return match.group(0)
        body = json.dumps(transformed, ensure_ascii=False, separators=(",", ":"))
        if body != match.group(2):
            changed += 1
        return match.group(1) + body + match.group(3)

    return JSONLD_RE.sub(replace, source), scripts, changed


SCHOOL_CARD_RE = re.compile(
    r'<(?P<tag>article|section)\b'
    r'(?=[^>]*\bwawa-school-card\b)'
    r'(?=[^>]*\bis-(?P<level>elementary|middle)\b)'
    r'[^>]*>.*?</(?P=tag)>',
    re.I | re.S,
)
PILLS_RE = re.compile(
    r'(<div\b(?=[^>]*\bwawa-pills\b)[^>]*>)(.*?)(</div>)',
    re.I | re.S,
)


def repair_cross_level_cards(source: str) -> tuple[str, int]:
    """Move 오현초 into the elementary card and keep 호매실중 in middle.

    The malformed source joins one elementary and one middle-school name.  A
    flat replacement would create a new factual error by labelling 오현초 as a
    middle school, so the visual school cards are repaired with level context.
    """

    if _CROSS_LEVEL_TOKEN not in html.unescape(source):
        return source, 0
    total = 0

    def replace_card(match: re.Match[str]) -> str:
        nonlocal total
        block = match.group(0)
        level = match.group("level").lower()
        if level == "middle" and _CROSS_LEVEL_TOKEN in block:
            block, count = re.subn(
                re.escape(_CROSS_LEVEL_TOKEN),
                "호매실중",
                block,
            )
            total += count
            return block
        if level != "elementary" or "오현초" in html.unescape(block):
            return block

        def append_chip(pills: re.Match[str]) -> str:
            nonlocal total
            contents = pills.group(2)
            if "data-school-level" in block:
                chip = (
                    '<span class="wawa-pill is-elementary" '
                    'data-source-school="오현초">오현초</span>'
                )
            else:
                chip = '<span class="wawa-pill">오현초</span>'
            total += 1
            return pills.group(1) + contents + chip + pills.group(3)

        return PILLS_RE.sub(append_chip, block, count=1)

    return SCHOOL_CARD_RE.sub(replace_card, source), total


def repair_cross_level_elementary_guidance(
    path: Path,
    source: str,
) -> tuple[str, int]:
    """Add the moved elementary name to the two national elementary leaves."""

    if "초등영수학원" not in path.parts or path.parent.parent.name not in {
        "호매실",
        "수원-금곡동",
    }:
        return source, 0
    total = 0
    for pattern, replacement in (
        (r"능실초, 금호초(?!, 오현초)", "능실초, 금호초, 오현초"),
        (r"능실초·금호초(?!·오현초)", "능실초·금호초·오현초"),
    ):
        source, count = re.subn(pattern, replacement, source)
        total += count
    return source, total


def split_school_spans(source: str) -> tuple[str, int]:
    total = 0
    for fused, names in FUSED_SCHOOLS.items():
        pattern = re.compile(
            rf'(<span\b(?=[^>]*(?:\bwawa-pill\b|\bdata-source-school\b))[^>]*>)'
            rf'{re.escape(fused)}(</span>)',
            re.I,
        )

        def replace(match: re.Match[str]) -> str:
            nonlocal total
            total += 1
            parts: list[str] = []
            selected_names = names
            if fused == _CROSS_LEVEL_TOKEN:
                opening_classes = html.unescape(match.group(1))
                if "is-middle" in opening_classes:
                    selected_names = ("호매실중",)
                elif "is-elementary" in opening_classes:
                    selected_names = ("오현초",)
            for name in selected_names:
                opening = match.group(1).replace(fused, name)
                parts.append(opening + html.escape(name) + match.group(2))
            return "".join(parts)

        source = pattern.sub(replace, source)
    return source, total


def replace_location_notes(source: str) -> tuple[str, int]:
    total = 0
    for raw, corrected in LOCATION_NOTE_CORRECTIONS.items():
        variants = {
            raw,
            html.escape(raw, quote=True),
            raw.replace("'", "&#39;"),
        }
        for variant in variants:
            pattern = re.compile(re.escape(variant).replace(r"\ ", r"\s+"))
            replacement = html.escape(corrected, quote=True) if "&" in variant else corrected
            source, count = pattern.subn(lambda _match: replacement, source)
            total += count
    return source, total


def first(pattern: re.Pattern[str], source: str) -> str:
    match = pattern.search(source)
    return match.group(1) if match else ""


def validate_page(before: str, after: str, path: Path) -> int:
    for label, pattern in (
        ("title", TITLE_RE),
        ("h1", H1_RE),
        ("canonical", CANONICAL_RE),
        ("meta description", META_DESCRIPTION_RE),
        ("og:title", OG_TITLE_RE),
        ("twitter:title", TWITTER_TITLE_RE),
    ):
        if first(pattern, before) != first(pattern, after):
            raise RepairError(f"{path}: {label} changed")
    if before.count("<section") != after.count("<section") or before.count("</section>") != after.count("</section>"):
        raise RepairError(f"{path}: section balance changed")
    parsed = 0
    for match in JSONLD_RE.finditer(after):
        json.loads(match.group(2))
        parsed += 1
    if not parsed:
        raise RepairError(f"{path}: JSON-LD missing")
    for raw in LOCATION_NOTE_CORRECTIONS:
        if raw in html.unescape(after):
            raise RepairError(f"{path}: stale location note remains")
    for fused in FUSED_SCHOOLS:
        if fused in html.unescape(after):
            raise RepairError(f"{path}: fused school remains")
    return parsed


def transform_page(path: Path, force_modified: bool = False) -> PagePlan:
    before = path.read_text(encoding="utf-8", errors="strict")
    after, location_changes = replace_location_notes(before)
    after, cross_card_changes = repair_cross_level_cards(after)
    after, cross_guidance_changes = repair_cross_level_elementary_guidance(
        path,
        after,
    )
    if (
        path.parent.parent.name in {"중학생학원", "중등수학학원", "중등영어학원"}
        or "중등영수학원" in path.parts
    ):
        # These are middle-only documents; prose and schema should never gain
        # the elementary-school name merely because the source cell was fused.
        after = after.replace(_CROSS_LEVEL_TOKEN, "호매실중")
    after, span_changes = split_school_spans(after)
    had_fused_school = any(fused in html.unescape(after) for fused in FUSED_SCHOOLS)
    after, scripts, schema_changes = rewrite_jsonld(
        after,
        bump_date=bool(
            force_modified or location_changes or span_changes or had_fused_school
        ),
    )
    school_text_changes = 0
    for fused, names in FUSED_SCHOOLS.items():
        count = after.count(fused)
        if count:
            after = after.replace(fused, ", ".join(names))
            school_text_changes += count
    parsed = validate_page(before, after, path)
    if parsed != scripts:
        raise RepairError(f"{path}: JSON-LD script count drift")
    return PagePlan(
        path=path,
        before=before,
        after=after,
        location_changes=location_changes,
        school_changes=(
            cross_card_changes
            + cross_guidance_changes
            + span_changes
            + school_text_changes
            + int(had_fused_school and schema_changes > 0)
        ),
        jsonld_scripts=scripts,
    )


def iter_html(root: Path) -> Iterable[Path]:
    for folder in SITE_ROOTS:
        yield from sorted((root / folder).rglob("*.html"))


def expected_location_paths(root: Path) -> set[Path]:
    result: set[Path] = set()
    for corrected, localities in LOCATION_LOCALITIES.items():
        if not corrected:
            raise RepairError("empty corrected location note")
        for locality in localities:
            for category in SUBJECT_CATEGORIES:
                result.add(root / "과목별학원" / category / locality / "index.html")
            parents = [
                path
                for path in (root / "전국학원").glob(f"*/*/{locality}/index.html")
                if path.is_file()
            ]
            if len(parents) != 1:
                raise RepairError(f"{locality}: national parent count={len(parents)}")
            result.add(parents[0])
            for child in ("초등영수학원", "중등영수학원", "고등영수학원"):
                result.add(parents[0].parent / child / "index.html")
    for profile in set(LOCATION_CENTER_PROFILES.values()):
        result.add(root / "과목별학원" / "와와학습코칭센터" / profile / "index.html")
    if len(result) != 138:
        raise RepairError(f"location target cardinality={len(result)}, expected=138")
    missing = sorted(path for path in result if not path.is_file())
    if missing:
        raise RepairError(f"location target missing: {missing[:5]}")
    return result


def validate_location_coverage(plans: dict[Path, PagePlan], expected: set[Path]) -> None:
    note_for_locality = {
        locality: corrected
        for corrected, localities in LOCATION_LOCALITIES.items()
        for locality in localities
    }
    for path in expected:
        source = plans[path].after
        if "와와학습코칭센터" in path.parts and path.parent.parent.name == "와와학습코칭센터":
            profile = path.parent.name
            localities = [key for key, value in LOCATION_CENTER_PROFILES.items() if value == profile]
            expected_notes = {note_for_locality[item] for item in localities}
        else:
            locality = next((part for part in path.parts if part in note_for_locality), "")
            expected_notes = {note_for_locality[locality]} if locality else set()
        if len(expected_notes) != 1:
            raise RepairError(f"{path}: expected location-note mapping={expected_notes}")
        note = next(iter(expected_notes))
        if note not in html.unescape(source):
            raise RepairError(f"{path}: corrected location note missing")


def school_page_categories(levels: dict[str, tuple[str, ...]]) -> tuple[str, ...]:
    categories: set[str] = set()
    if set(levels) & {"elementary", "middle"}:
        categories.update(NEW_SCHOOL_PAGE_CATEGORIES)
    if "high" in levels:
        categories.update(HIGH_SCHOOL_PAGE_CATEGORIES)
    return tuple(sorted(categories))


def validate_school_coverage(plans: dict[Path, PagePlan], root: Path) -> None:
    for locality, levels in SCHOOL_CORRECTIONS_BY_LOCALITY.items():
        names = SCHOOL_LOCALITIES[locality]
        categories = school_page_categories(levels)
        national_slug = SCHOOL_NATIONAL_SLUGS.get(locality, locality)
        subject_pages = {
            category: root / "과목별학원" / category / locality / "index.html"
            for category in categories
        }
        parents = [
            path
            for path in (root / "전국학원").glob(f"*/*/{national_slug}/index.html")
            if path.is_file()
        ]
        if len(parents) != 1:
            raise RepairError(f"{locality}: national parent count={len(parents)}")
        national_pages = [
            parents[0],
            *(parents[0].parent / child / "index.html" for child in (
                "초등영수학원",
                "중등영수학원",
                "고등영수학원",
            )),
        ]
        expected_count = len(categories) + 4
        if len(subject_pages) + len(national_pages) != expected_count:
            raise RepairError(
                f"{locality}: school page count={len(subject_pages) + len(national_pages)}, "
                f"expected={expected_count}"
            )
        for category, path in subject_pages.items():
            expected_names: list[str] = []
            if category in NEW_SCHOOL_PAGE_CATEGORIES:
                for level in NEW_LEVELS_BY_CATEGORY[category]:
                    expected_names.extend(levels.get(level, ()))
            if category in HIGH_SCHOOL_PAGE_CATEGORIES:
                expected_names.extend(levels.get("high", ()))
            text = html.unescape(plans[path].after)
            if not all(name in text for name in expected_names):
                raise RepairError(f"{path}: separated school names missing")
        for path in national_pages:
            text = html.unescape(plans[path].after)
            if not all(name in text for name in names):
                raise RepairError(f"{path}: separated school names missing")
        for level, level_names in levels.items():
            for category in SOURCE_CHIP_CATEGORIES[level]:
                if category not in categories:
                    continue
                page = root / "과목별학원" / category / locality / "index.html"
                text = html.unescape(plans[page].after)
                for name in level_names:
                    if f'data-source-school="{name}"' not in text:
                        raise RepairError(f"{page}: school source chip missing {name}")
    for profile, names in SCHOOL_CENTER_PROFILES.items():
        page = root / "과목별학원" / "와와학습코칭센터" / profile / "index.html"
        text = html.unescape(plans[page].after)
        if not all(name in text for name in names):
            raise RepairError(f"{page}: center profile school split missing")


def expected_school_paths(root: Path) -> set[Path]:
    result: set[Path] = set()
    for locality, levels in SCHOOL_CORRECTIONS_BY_LOCALITY.items():
        national_slug = SCHOOL_NATIONAL_SLUGS.get(locality, locality)
        result.update(
            root / "과목별학원" / category / locality / "index.html"
            for category in school_page_categories(levels)
        )
        parents = [
            path
            for path in (root / "전국학원").glob(
                f"*/*/{national_slug}/index.html"
            )
            if path.is_file()
        ]
        if len(parents) != 1:
            raise RepairError(
                f"{locality}: national parent count={len(parents)}"
            )
        result.add(parents[0])
        result.update(
            parents[0].parent / child / "index.html"
            for child in ("초등영수학원", "중등영수학원", "고등영수학원")
        )
    result.update(
        root / "과목별학원" / "와와학습코칭센터" / profile / "index.html"
        for profile in SCHOOL_CENTER_PROFILES
    )
    if len(result) != 202:
        raise RepairError(f"school target cardinality={len(result)}, expected=202")
    missing = sorted(path for path in result if not path.is_file())
    if missing:
        raise RepairError(f"school target missing: {missing[:5]}")
    return result


def page_canonicals(plans: Iterable[PagePlan]) -> set[str]:
    result: set[str] = set()
    for plan in plans:
        canonical = html.unescape(first(CANONICAL_RE, plan.after)).strip()
        if not canonical or canonical in result:
            raise RepairError(f"{plan.path}: missing or duplicate canonical")
        result.add(canonical)
    return result


def update_sitemap(source: str, canonicals: set[str]) -> tuple[str, int]:
    seen: set[str] = set()
    changed = 0

    def replace(match: re.Match[str]) -> str:
        nonlocal changed
        block = match.group(0)
        loc_match = LOC_RE.search(block)
        if not loc_match:
            return block
        url = html.unescape(loc_match.group(1)).strip()
        if url not in canonicals:
            return block
        if url in seen:
            raise RepairError(f"duplicate sitemap URL: {url}")
        seen.add(url)
        updated, count = LASTMOD_RE.subn(
            lambda item: item.group(1) + max(item.group(2), REPAIR_DATE) + item.group(3),
            block,
            count=1,
        )
        if count != 1:
            raise RepairError(f"sitemap lastmod missing: {url}")
        changed += int(updated != block)
        return updated

    updated = URL_BLOCK_RE.sub(replace, source)
    missing = canonicals - seen
    if missing:
        raise RepairError(f"sitemap URLs missing: {sorted(missing)[:5]}")
    return updated, changed


def atomic_write(path: Path, value: str) -> None:
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        newline="\n",
        delete=False,
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    ) as handle:
        handle.write(value)
        temporary = Path(handle.name)
    os.replace(temporary, path)


def run(root: Path, apply: bool) -> dict[str, Any]:
    paths = list(iter_html(root))
    location_paths = expected_location_paths(root)
    school_paths = expected_school_paths(root)
    target_paths = location_paths | school_paths
    if len(target_paths) != 340:
        raise RepairError(
            f"combined target cardinality={len(target_paths)}, expected=340"
        )
    plans = {
        path: transform_page(path, force_modified=path in target_paths)
        for path in paths
    }
    validate_location_coverage(plans, location_paths)
    validate_school_coverage(plans, root)

    changed_pages = [plan for plan in plans.values() if plan.changed]
    canonicals = page_canonicals(plans[path] for path in sorted(target_paths))
    sitemap = root / "sitemap.xml"
    sitemap_before = sitemap.read_text(encoding="utf-8", errors="strict")
    sitemap_after, sitemap_changes = update_sitemap(sitemap_before, canonicals)

    if apply:
        for plan in changed_pages:
            atomic_write(plan.path, plan.after)
        if sitemap_after != sitemap_before:
            atomic_write(sitemap, sitemap_after)

    by_root = Counter(plan.path.relative_to(root).parts[0] for plan in changed_pages)
    location_changed_files = sum(plan.location_changes > 0 for plan in changed_pages)
    school_changed_files = sum(plan.school_changes > 0 for plan in changed_pages)
    return {
        "ok": True,
        "mode": "apply" if apply else "dry-run",
        "html_checked": len(paths),
        "jsonld_scripts_checked": sum(plan.jsonld_scripts for plan in plans.values()),
        "location_target_files": len(location_paths),
        "school_target_files": len(school_paths),
        "changed_html": len(changed_pages),
        "changed_by_root": dict(sorted(by_root.items())),
        "location_changed_files": location_changed_files,
        "school_changed_files": school_changed_files,
        "sitemap_urls_checked": len(canonicals),
        "sitemap_lastmods_changed": sitemap_changes,
        "changed_paths": [plan.path.relative_to(root).as_posix() for plan in changed_pages],
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument(
        "--show-paths",
        action="store_true",
        help="Include every changed relative path in the JSON report.",
    )
    args = parser.parse_args(argv)
    try:
        report = run(args.root.resolve(), args.apply)
    except (OSError, UnicodeError, json.JSONDecodeError, RepairError) as exc:
        print(json.dumps({"ok": False, "error": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False, indent=2))
        return 1
    if not args.show_paths:
        report.pop("changed_paths", None)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
