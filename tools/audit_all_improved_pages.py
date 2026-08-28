from __future__ import annotations

"""Read-only audit for all eight improved locality page families."""

import html
import json
import random
import re
import statistics
from datetime import date
from pathlib import Path
from urllib.parse import unquote, urlsplit


ROOT = Path(__file__).resolve().parents[1]
CATEGORIES = (
    "초등학생학원",
    "중학생학원",
    "고등학생학원",
    "중등영어학원",
    "중등수학학원",
    "고등영어학원",
    "고등수학학원",
    "영수학원",
)
GRADE_CATEGORIES = {"초등학생학원", "중학생학원", "고등학생학원"}
FAQ_COUNT = {"초등학생학원": 4, "중학생학원": 4}
JSON_RE = re.compile(
    r'<script\b[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
    re.I | re.S,
)
EDITORIAL_RESIDUE = re.compile(
    r"(?<![가-힣])원고(?![가-힣])|PARENT CONSULTATION CASE|후기 예시 [12]\."
)
REQUIRED_TYPES = {
    "EducationalOrganization",
    "LocalBusiness",
    "WebPage",
    "Article",
    "Service",
    "FAQPage",
    "BreadcrumbList",
    "ItemList",
}
INTERNAL_HOST = "xn--ru4bi8s1tac0p.kr"


def plain(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", value))).strip()


def visible_text(source: str) -> str:
    value = re.sub(r"<script\b[^>]*>.*?</script>", " ", source, flags=re.I | re.S)
    value = re.sub(r"<style\b[^>]*>.*?</style>", " ", value, flags=re.I | re.S)
    return plain(value)


def node_types(node: dict) -> set[str]:
    value = node.get("@type", [])
    return set(value if isinstance(value, list) else [value])


def node_of(nodes: list[dict], schema_type: str) -> dict:
    found = [node for node in nodes if schema_type in node_types(node)]
    if len(found) != 1:
        raise ValueError(f"{schema_type} node count={len(found)}")
    return found[0]


def local_target(page: Path, value: str) -> Path | None:
    value = html.unescape(value.strip())
    if not value or value.startswith(("#", "tel:", "sms:", "mailto:", "javascript:", "data:")):
        return None
    parsed = urlsplit(value)
    if parsed.netloc and parsed.netloc.lower() != INTERNAL_HOST:
        return None
    route = unquote(parsed.path)
    if not route:
        return page
    target = ROOT / route.lstrip("/") if route.startswith("/") else page.parent / route
    if route.endswith("/") or target.is_dir() or not target.suffix:
        target = target / "index.html"
    try:
        target.resolve().relative_to(ROOT.resolve())
    except ValueError:
        return ROOT / ".invalid-outside-root"
    return target


def main() -> int:
    errors: list[str] = []
    report: dict[str, dict[str, object]] = {}
    checked_local_references = 0
    for category in CATEGORIES:
        paths = sorted((ROOT / "과목별학원" / category).glob("*/index.html"))
        if len(paths) != 371:
            errors.append(f"{category}: pages={len(paths)}")
            continue
        titles: list[str] = []
        h1s: list[str] = []
        canonicals: list[str] = []
        faq_questions: list[str] = []
        faq_answers: list[str] = []
        texts: list[str] = []
        modified_dates: set[str] = set()
        published_dates: set[str] = set()
        for path in paths:
            slug = path.parent.name
            source = path.read_text(encoding="utf-8")
            try:
                title = plain(re.findall(r"<title>(.*?)</title>", source, re.I | re.S)[0])
                h1 = plain(re.findall(r"<h1\b[^>]*>(.*?)</h1>", source, re.I | re.S)[0])
                canonical = re.findall(r'<link\s+rel="canonical"\s+href="([^"]+)"', source, re.I)[0]
                payload = json.loads(JSON_RE.findall(source)[0])
                nodes = payload.get("@graph", [])
                schema_types = {item for node in nodes for item in node_types(node)}
                if not REQUIRED_TYPES <= schema_types:
                    errors.append(f"{category}/{slug}: schema types")
                webpage = node_of(nodes, "WebPage")
                article = node_of(nodes, "Article")
                faq = node_of(nodes, "FAQPage")
                webpage_modified = str(webpage.get("dateModified"))
                article_modified = str(article.get("dateModified"))
                if webpage_modified != article_modified:
                    errors.append(
                        f"{category}/{slug}: WebPage/Article modified mismatch "
                        f"{webpage_modified}/{article_modified}"
                    )
                modified_dates.update((webpage_modified, article_modified))
                published_dates.add(str(article.get("datePublished")))

                visible_questions = [plain(value) for value in re.findall(
                    r"<summary><span>Q</span>(.*?)</summary>", source, re.I | re.S
                )]
                visible_answers = [plain(value) for value in re.findall(
                    r'<div\s+class="subject-faq-answer"><span>A</span><p>(.*?)</p>',
                    source,
                    re.I | re.S,
                )]
                schema_questions = [str(item.get("name", "")) for item in faq.get("mainEntity", [])]
                schema_answers = [
                    str(item.get("acceptedAnswer", {}).get("text", ""))
                    for item in faq.get("mainEntity", [])
                ]
                expected_faq_count = FAQ_COUNT.get(category, 5)
                if not (
                    len(visible_questions) == len(visible_answers) == expected_faq_count
                    and visible_questions == schema_questions
                    and visible_answers == schema_answers
                ):
                    errors.append(f"{category}/{slug}: FAQ visible/schema mismatch")
                if EDITORIAL_RESIDUE.search(visible_text(source)):
                    errors.append(f"{category}/{slug}: editorial residue")
                references = re.findall(r'<a\b[^>]*href="([^"]+)"', source, re.I)
                references += re.findall(r'<(?:img|script|source)\b[^>]*src="([^"]+)"', source, re.I)
                for value in references:
                    target = local_target(path, value)
                    if target is None:
                        continue
                    checked_local_references += 1
                    if not target.is_file():
                        errors.append(f"{category}/{slug}: broken local reference {value}")
                titles.append(title)
                h1s.append(h1)
                canonicals.append(canonical)
                faq_questions.extend(visible_questions)
                faq_answers.extend(visible_answers)
                texts.append(visible_text(source))
            except Exception as exc:
                errors.append(f"{category}/{slug}: {type(exc).__name__}: {exc}")

        expected_published = "2026-07-23" if category in GRADE_CATEGORIES else "2026-08-13"
        # A scoped release legitimately produces more than one modification
        # date inside a category.  Validate each page's paired dates and every
        # distinct value instead of requiring a category-wide timestamp.
        for modified_value in modified_dates:
            try:
                modified_date = date.fromisoformat(modified_value)
                if modified_date > date.today():
                    errors.append(f"{category}: future modified={modified_value}")
            except ValueError:
                errors.append(f"{category}: invalid modified={modified_value}")
        if published_dates != {expected_published}:
            errors.append(f"{category}: published={sorted(published_dates)}")
        faq_total = 371 * FAQ_COUNT.get(category, 5)
        for label, values, expected in (
            ("title", titles, 371),
            ("h1", h1s, 371),
            ("canonical", canonicals, 371),
            ("faq_questions", faq_questions, faq_total),
            ("faq_answers", faq_answers, faq_total),
        ):
            if len(values) != expected or len(set(values)) != expected:
                errors.append(f"{category}: {label}={len(values)}/{len(set(values))}")

        rng = random.Random(20260826)
        pair_scores: list[float] = []
        for _ in range(350):
            left, right = rng.sample(range(len(texts)), 2)
            left_shingles = {texts[left][i : i + 4] for i in range(len(texts[left]) - 3)}
            right_shingles = {texts[right][i : i + 4] for i in range(len(texts[right]) - 3)}
            pair_scores.append(
                len(left_shingles & right_shingles) / len(left_shingles | right_shingles)
            )
        report[category] = {
            "pages": len(texts),
            "visible_chars_avg": round(statistics.mean(map(len, texts))) if texts else 0,
            "sample_raw_4_shingle_avg": round(statistics.mean(pair_scores), 4),
            "sample_raw_4_shingle_max": round(max(pair_scores), 4),
            "unique_titles": len(set(titles)),
            "unique_faq_questions": len(set(faq_questions)),
            "unique_faq_answers": len(set(faq_answers)),
            "date_modified": next(iter(modified_dates)) if len(modified_dates) == 1 else sorted(modified_dates),
        }

    output = {
        "ok": not errors,
        "categories": report,
        "checked_local_references": checked_local_references,
        "errors": len(errors),
        "samples": errors[:30],
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
