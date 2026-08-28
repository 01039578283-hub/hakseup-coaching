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
FUSED_SCHOOLS = VERIFIED_SCHOOL_SOURCE_CORRECTIONS
SCHOOL_LOCALITIES = {
    "성사동": FUSED_SCHOOLS["성사고 화수고"],
    "주교동": FUSED_SCHOOLS["성사고 화수고"],
    "진접읍": FUSED_SCHOOLS["진접고 오남고"],
    "부천상동": FUSED_SCHOOLS["상동고 상일고 상원고 중흥고 중원고"],
    "비전동": FUSED_SCHOOLS["비전고 한광고 한광여고 평택여고"],
    "소사벌": FUSED_SCHOOLS["비전고 한광고 한광여고 평택여고"],
    "죽백동": FUSED_SCHOOLS["비전고 한광고 한광여고 평택여고"],
    "동삭동": FUSED_SCHOOLS["비전고 한광고 한광여고 평택여고"],
    "산남동": FUSED_SCHOOLS["충북고 운호고 충북여고 산남고"],
    "수곡동": FUSED_SCHOOLS["충북고 운호고 충북여고 산남고"],
    "양덕동": FUSED_SCHOOLS["장성고 포고 포여고 유성여고"],
    "장량동": FUSED_SCHOOLS["장성고 포고 포여고 유성여고"],
}
SCHOOL_NATIONAL_SLUGS = {"부천상동": "부천-상동"}
SCHOOL_CENTER_PROFILES = {
    "원당점": FUSED_SCHOOLS["성사고 화수고"],
    "진접점": FUSED_SCHOOLS["진접고 오남고"],
    "상동점": FUSED_SCHOOLS["상동고 상일고 상원고 중흥고 중원고"],
    "비전점": FUSED_SCHOOLS["비전고 한광고 한광여고 평택여고"],
    "산남점": FUSED_SCHOOLS["충북고 운호고 충북여고 산남고"],
    "양덕점": FUSED_SCHOOLS["장성고 포고 포여고 유성여고"],
}
SCHOOL_PAGE_CATEGORIES = (
    "고등수학학원",
    "고등영어학원",
    "고등학생학원",
    "영수학원",
    "중학생학원",
    "초등학생학원",
)

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
            for name in names:
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
    for label, pattern in (("title", TITLE_RE), ("h1", H1_RE), ("canonical", CANONICAL_RE)):
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
        school_changes=span_changes + school_text_changes + int(had_fused_school and schema_changes > 0),
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


def validate_school_coverage(plans: dict[Path, PagePlan], root: Path) -> None:
    for locality, names in SCHOOL_LOCALITIES.items():
        national_slug = SCHOOL_NATIONAL_SLUGS.get(locality, locality)
        matching = [
            root / "과목별학원" / category / locality / "index.html"
            for category in SCHOOL_PAGE_CATEGORIES
        ]
        parents = [
            path
            for path in (root / "전국학원").glob(f"*/*/{national_slug}/index.html")
            if path.is_file()
        ]
        if len(parents) != 1:
            raise RepairError(f"{locality}: national parent count={len(parents)}")
        matching.extend(
            [
                parents[0],
                *(parents[0].parent / child / "index.html" for child in (
                    "초등영수학원",
                    "중등영수학원",
                    "고등영수학원",
                )),
            ]
        )
        if len(matching) != 10:
            raise RepairError(f"{locality}: school page count={len(matching)}, expected=10")
        for path in matching:
            text = html.unescape(plans[path].after)
            if not all(name in text for name in names):
                raise RepairError(f"{path}: separated school names missing")
        for category in ("고등수학학원", "고등영어학원", "고등학생학원", "영수학원"):
            page = root / "과목별학원" / category / locality / "index.html"
            text = html.unescape(plans[page].after)
            for name in names:
                if f'data-source-school="{name}"' not in text:
                    raise RepairError(f"{page}: school source chip missing {name}")
    for profile, names in SCHOOL_CENTER_PROFILES.items():
        page = root / "과목별학원" / "와와학습코칭센터" / profile / "index.html"
        text = html.unescape(plans[page].after)
        if not all(name in text for name in names):
            raise RepairError(f"{page}: center profile school split missing")


def expected_school_paths(root: Path) -> set[Path]:
    result: set[Path] = set()
    for locality in SCHOOL_LOCALITIES:
        national_slug = SCHOOL_NATIONAL_SLUGS.get(locality, locality)
        result.update(
            root / "과목별학원" / category / locality / "index.html"
            for category in SCHOOL_PAGE_CATEGORIES
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
    if len(result) != 126:
        raise RepairError(f"school target cardinality={len(result)}, expected=126")
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
