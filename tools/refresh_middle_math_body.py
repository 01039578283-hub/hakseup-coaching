from __future__ import annotations

"""Refresh the 371 middle-math article bodies from the source workbook.

The command is a validated dry run by default. ``--apply`` replaces only the
visible ``subject-copy-flow`` block and the WebPage/Article modification date.
All navigation, facts, school evidence, FAQ, title metadata, canonical URL,
images, and post-generated internal-link/search-intent blocks are preserved.
"""

import argparse
import html
import itertools
import json
import re
import statistics
from dataclasses import dataclass
from pathlib import Path

from generate_middle_subject_pages import configure
from source_copy_utils import source_paragraphs


ROOT = Path(__file__).resolve().parents[1]
CATEGORY = "중등수학학원"
TARGET = ROOT / "과목별학원" / CATEGORY
RELEASE_DATE = "2026-08-28"
FLOW_RE = re.compile(
    r'(<div\s+class="subject-copy-flow">)(.*?)(</div></article>)',
    re.I | re.S,
)
JSONLD_RE = re.compile(
    r'(<script\b[^>]*type=["\']application/ld\+json["\'][^>]*>)(.*?)(</script>)',
    re.I | re.S,
)
SCHOOL_RE = re.compile(
    r"<!-- school-reference:start -->.*?<!-- school-reference:end -->",
    re.I | re.S,
)
NETWORK_RE = re.compile(
    r"<!-- local-study-network:start -->.*?<!-- local-study-network:end -->",
    re.I | re.S,
)
INTENT_RE = re.compile(
    r"<!-- priority-search-intent:start -->.*?<!-- priority-search-intent:end -->",
    re.I | re.S,
)
SCRIPT_STYLE_RE = re.compile(
    r"<(?:script|style|header|footer|nav|noscript|svg)\b.*?</(?:script|style|header|footer|nav|noscript|svg)>",
    re.I | re.S,
)
TAG_RE = re.compile(r"<[^>]+>")


@dataclass(frozen=True)
class Plan:
    path: Path
    before: str
    after: str
    source_paragraphs: tuple[str, ...]


def clean(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(TAG_RE.sub(" ", value))).strip()


def visible_text(source: str) -> str:
    main = re.search(r"<main\b.*?</main>", source, re.I | re.S)
    value = main.group(0) if main else source
    return clean(SCRIPT_STYLE_RE.sub(" ", value))


def article_text(source: str) -> str:
    match = FLOW_RE.search(source)
    return clean(match.group(2)) if match else ""


def shingles(value: str, size: int = 4) -> set[tuple[str, ...]]:
    words = re.findall(r"[가-힣A-Za-z0-9]+", value.lower())
    return {
        tuple(words[index : index + size])
        for index in range(max(0, len(words) - size + 1))
    }


def similarity(values: list[str], sample_size: int = 90) -> dict[str, float]:
    if len(values) > sample_size:
        indices = [
            round(index * (len(values) - 1) / (sample_size - 1))
            for index in range(sample_size)
        ]
        values = [values[index] for index in indices]
    sets = [shingles(value) for value in values]
    scores = [
        len(left & right) / len(left | right)
        for left, right in itertools.combinations(sets, 2)
    ]
    ordered = sorted(scores)
    return {
        "average": round(statistics.mean(scores), 4),
        "p90": round(ordered[int(len(ordered) * 0.9)], 4),
        "max": round(max(scores), 4),
    }


def source_copy(record: object) -> tuple[str, ...]:
    schools = tuple(getattr(record, "schools"))
    excluded_schools = tuple(
        school
        for school in schools
        if not (school.endswith("중") or school.endswith("중학교"))
    )
    return tuple(
        source_paragraphs(
            getattr(record, "source_html"),
            useful_terms=("수학", "개념", "문제", "풀이", "학습", "학생", "오답", "시험", "상담"),
            blocked_terms=("영어", "국어", "초등", "고등", "고교"),
            excluded_school_names=excluded_schools,
            limit=12,
        )
    )


def update_jsonld(source: str) -> str:
    updated = False

    def replace(match: re.Match[str]) -> str:
        nonlocal updated
        if updated:
            return match.group(0)
        data = json.loads(match.group(2))
        graph = data.get("@graph", []) if isinstance(data, dict) else []
        page_nodes = 0
        article_nodes = 0
        for node in graph:
            if not isinstance(node, dict):
                continue
            node_type = node.get("@type", [])
            types = set(node_type if isinstance(node_type, list) else [node_type])
            if "WebPage" in types:
                node["dateModified"] = RELEASE_DATE
                page_nodes += 1
            if "Article" in types:
                node["dateModified"] = RELEASE_DATE
                article_nodes += 1
        if page_nodes != 1 or article_nodes != 1:
            raise ValueError(
                f"WebPage/Article schema count={page_nodes}/{article_nodes}"
            )
        updated = True
        payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
        return match.group(1) + payload + match.group(3)

    result = JSONLD_RE.sub(replace, source, count=1)
    if not updated:
        raise ValueError("JSON-LD graph not updated")
    return result


def transform(record: object, module: object) -> Plan:
    path = TARGET / getattr(record, "slug") / "index.html"
    before = path.read_text(encoding="utf-8", errors="strict")
    answer, sections = module.content_sections(record)
    del answer
    rendered = module.base.render_sections(sections)
    if FLOW_RE.search(before) is None:
        raise ValueError(f"{path.relative_to(ROOT)}: subject-copy-flow missing")
    after = FLOW_RE.sub(
        lambda match: match.group(1) + rendered + match.group(3),
        before,
        count=1,
    )
    after = update_jsonld(after)
    return Plan(path, before, after, source_copy(record))


def unchanged_block(pattern: re.Pattern[str], before: str, after: str) -> bool:
    before_match = pattern.search(before)
    after_match = pattern.search(after)
    return bool(
        before_match
        and after_match
        and before_match.group(0) == after_match.group(0)
    )


def validate(plans: list[Plan]) -> list[str]:
    errors: list[str] = []
    if len(plans) != 371:
        errors.append(f"pages={len(plans)}/371")
    normalized_source_df: dict[str, int] = {}
    for plan in plans:
        relative = plan.path.relative_to(ROOT).as_posix()
        for label, pattern in (
            ("school evidence", SCHOOL_RE),
            ("local study network", NETWORK_RE),
            ("priority intent", INTENT_RE),
        ):
            if not unchanged_block(pattern, plan.before, plan.after):
                errors.append(f"{relative}: {label} changed")
        for pattern, label in (
            (r"<title>(.*?)</title>", "title"),
            (r"<h1\b[^>]*>(.*?)</h1>", "H1"),
            (r'<link\s+rel="canonical"\s+href="([^"]+)"', "canonical"),
            (r'<section\b[^>]*class="subject-faq-section".*?</section>', "FAQ"),
        ):
            before_match = re.search(pattern, plan.before, re.I | re.S)
            after_match = re.search(pattern, plan.after, re.I | re.S)
            if not before_match or not after_match or before_match.group(0) != after_match.group(0):
                errors.append(f"{relative}: {label} changed")
        flow = FLOW_RE.search(plan.after)
        flow_source = flow.group(2) if flow else ""
        if flow_source.count('class="subject-copy-section"') != 6:
            errors.append(f"{relative}: copy sections count")
        for paragraph in plan.source_paragraphs:
            if clean(flow_source).count(clean(paragraph)) != 1:
                errors.append(f"{relative}: source paragraph missing/duplicated")
            normalized = re.sub(r"\W+", "", paragraph)
            normalized_source_df[normalized] = normalized_source_df.get(normalized, 0) + 1
        try:
            match = JSONLD_RE.search(plan.after)
            data = json.loads(match.group(2)) if match else {}
            nodes = data.get("@graph", []) if isinstance(data, dict) else []
            modified: set[str] = set()
            for node in nodes:
                if not isinstance(node, dict):
                    continue
                node_type = node.get("@type", [])
                types = set(node_type if isinstance(node_type, list) else [node_type])
                if {"WebPage", "Article"} & types:
                    modified.add(str(node.get("dateModified")))
            if modified != {RELEASE_DATE}:
                errors.append(f"{relative}: dateModified={sorted(modified)}")
        except Exception as exc:
            errors.append(f"{relative}: JSON-LD {type(exc).__name__}: {exc}")
    if normalized_source_df and max(normalized_source_df.values()) > 3:
        errors.append(
            f"source paragraph max document frequency={max(normalized_source_df.values())}/3"
        )
    return errors


def atomic_write(path: Path, value: str) -> None:
    temporary = path.with_name(path.name + ".source-led.tmp")
    temporary.write_text(value, encoding="utf-8", newline="\n")
    temporary.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    module = configure("math")
    records = module.make_records(module.DEFAULT_WORKBOOK)
    module.preflight(records)
    plans = [transform(record, module) for record in records]
    errors = validate(plans)
    before_full = [visible_text(plan.before) for plan in plans]
    after_full = [visible_text(plan.after) for plan in plans]
    before_article = [article_text(plan.before) for plan in plans]
    after_article = [article_text(plan.after) for plan in plans]
    report = {
        "mode": "APPLY" if args.apply else "DRY-RUN",
        "pages": len(plans),
        "changed": sum(plan.before != plan.after for plan in plans),
        "source_paragraphs": {
            "total": sum(len(plan.source_paragraphs) for plan in plans),
            "min_per_page": min(map(lambda plan: len(plan.source_paragraphs), plans)),
            "average_per_page": round(
                statistics.mean(len(plan.source_paragraphs) for plan in plans), 2
            ),
            "max_per_page": max(map(lambda plan: len(plan.source_paragraphs), plans)),
        },
        "visible_chars_average": {
            "before": round(statistics.mean(map(len, before_full)), 1),
            "after": round(statistics.mean(map(len, after_full)), 1),
        },
        "full_page_similarity": {
            "before": similarity(before_full),
            "after": similarity(after_full),
        },
        "article_similarity": {
            "before": similarity(before_article),
            "after": similarity(after_article),
        },
        "errors": len(errors),
        "samples": errors[:30],
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if errors:
        return 1
    if args.apply:
        for plan in plans:
            if plan.before != plan.after:
                atomic_write(plan.path, plan.after)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
