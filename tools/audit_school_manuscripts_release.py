from __future__ import annotations

"""Independent release audit for the 2,968 local school manuscripts.

The checker deliberately does not import parsing or rendering helpers from the
generator.  It reads the authoritative CSV again, derives the target routes,
and can audit either the materialized tree or a generator's in-memory plan.
It never writes project files.
"""

import argparse
import csv
import hashlib
import html
import importlib.util
import inspect
import json
import os
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from types import ModuleType
from typing import Any, Iterable, Iterator, Mapping, Sequence
from urllib.parse import quote
from xml.etree import ElementTree as ET


sys.dont_write_bytecode = True


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_COMMON = ROOT.parent / "참고자료" / "공통자료"
SOURCE_NAME = "타깃학교.csv"
BASE_URL = "https://xn--ru4bi8s1tac0p.kr"
SITEMAP = "sitemap.xml"
MODIFIED_DATE = "2026-08-19"

START_MARKER = "<!-- school-reference:start -->"
END_MARKER = "<!-- school-reference:end -->"

LEVEL_COLUMN = {
    "elementary": "타깃학교\n(초)",
    "middle": "타깃학교\n(중)",
    "high": "타깃학교\n(고)",
}
LEVEL_KOREAN = {
    "elementary": "초등",
    "middle": "중등",
    "high": "고등",
}
CATEGORY_LEVELS: dict[str, tuple[str, ...]] = {
    "고등수학학원": ("high",),
    "고등영어학원": ("high",),
    "고등학생학원": ("high",),
    "영수학원": ("elementary", "middle", "high"),
    "중등수학학원": ("middle",),
    "중등영어학원": ("middle",),
    "중학생학원": ("middle",),
    "초등학생학원": ("elementary",),
}
CATEGORY_COPY_VALUES: dict[str, tuple[str, ...]] = {
    "고등수학학원": ("고등수학학원", "고등 수학학원", "고등 수학"),
    "고등영어학원": ("고등영어학원", "고등 영어학원", "고등 영어"),
    "고등학생학원": ("고등학생학원", "고등학생 과정"),
    "영수학원": ("영수학원", "영어 또는 수학"),
    "중등수학학원": ("중등수학학원", "중등 수학학원", "중등 수학"),
    "중등영어학원": ("중등영어학원", "중등 영어학원", "중등 영어"),
    "중학생학원": ("중학생학원", "중학생 과정"),
    "초등학생학원": ("초등학생학원", "초등학생 과정", "초등 과정"),
}
GENERIC_HIGH = "지역내 모든 고등학교 가능"
CHANGWON_LOCALITIES = {"상남동", "신월동", "사파동"}
CHANGWON_HIGH_CATEGORIES = {"고등수학학원", "고등영어학원"}
CHANGWON_MIDDLE_CATEGORIES = {"중등수학학원", "중등영어학원"}
STANDALONE_CHANGWON_MIDDLE = re.compile(
    r"(?<![가-힣A-Za-z0-9])창원중(?=(?:은|는|이|가|을|를|와|과|의|도|에|로|에서|입니다|이며|이고|[,，./|·;\s]|$))"
)
STANDALONE_BROKEN_HIGH = re.compile(
    r"(?<![가-힣A-Za-z0-9])앙여고(?=(?:은|는|이|가|을|를|와|과|의|도|에|로|에서|입니다|이며|이고|[,，./|·;\s]|$))"
)

EXPECTED_ROWS = 371
EXPECTED_DETAILS = 2968
EXPECTED_GROUPS = 3710
EXPECTED_PROVIDED_GROUPS = 3090
EXPECTED_COVERAGE_GROUPS = 8
EXPECTED_MISSING_GROUPS = 612
EXPECTED_NAMED_OCCURRENCES = 8336
EXPECTED_SITEMAP_URLS = 4743
EXPECTED_COMPACTED_LOCALITIES = 14
EXPECTED_LEVEL_SOURCE = {
    "elementary": {"named_rows": 297, "missing": 74, "coverage": 0, "deduped": 640},
    "middle": {"named_rows": 318, "missing": 53, "coverage": 0, "deduped": 854},
    "high": {"named_rows": 306, "missing": 63, "coverage": 2, "deduped": 910},
}

MAX_PARAGRAPH_DF = 34
MAX_SENTENCE_DF = 34
MAX_H2_DF = 40

SCHOOL_TYPES = {
    "EducationalOrganization",
    "School",
    "ElementarySchool",
    "MiddleSchool",
    "HighSchool",
}
PRUNE_DIRS = {".git", ".vercel", "node_modules", "tmp", "__pycache__"}
SKIP_VISIBLE = {"script", "style", "template", "noscript", "svg", "header", "footer", "nav"}

AUTHORING_SEEDS = (
    "핵심 키워드",
    "보조 키워드",
    "세부 키워드",
    "검색 의도",
    "메타 디스크립션",
    "검색엔진",
    "SEO",
    "AEO",
    "GEO",
    "이 글에서는",
    "이 페이지에서는",
    "원고",
    "학원창업",
    "학원전자계약",
    "학원고객관리",
    "학원회원관리",
    "학원운영",
    "학원재등록",
    "학원휴원",
    "학원미납관리",
    "학원매출관리",
    "학원수납관리",
    "학원관리솔루션",
    "학원개원",
    "학원행정",
    "학원출결앱",
    "검색 결과",
    "검색한 학부모",
    "검색어",
    "검색 시",
    "검색에서",
)
SENSITIVE_SCHOOL_TERMS = re.compile(
    r"(?:시험\s*(?:범위|일정)|교과서|진도|시간표|학사\s*일정|수업\s*(?:시간|일정)|"
    r"출제\s*(?:경향|범위)|수행평가|중간고사|기말고사|내신\s*(?:범위|일정)|커리큘럼|반\s*편성)"
)
SAFE_EPISTEMIC_TERMS = re.compile(
    r"(?:확인|대조|문의|상담|학교\s*공지|최신\s*자료|직접\s*자료|달라질|변동|자료를\s*가져|"
    r"최신\s*설명|담당\s*설명|회신\s*내용|안내(?:받은|\s*문구)|상담\s*답변|직접\s*물어)"
)
UNSUPPORTED_OPERATION = re.compile(
    r"(?:저희|본원|우리\s*학원|(?:학원|센터|강사진?|교사진?|선생님)(?:은|는|이|가|에서)?)"
    r"[^.!?\n]{0,70}(?:운영|진행|지도|관리|제공|보장|맞춤)(?:하고\s*있|합니|해\s*드|드립|됩니)"
)
POSITIVE_SCHOOL_CUE = re.compile(r"(?:실제\s*)?수업.{0,14}(?:가능|대상)|(?:수강|지도).{0,10}가능")
WEAK_REFERENCE_CUE = re.compile(r"(?:참고\s*(?:학교|정보)|학교\s*참고)" )
MISSING_CUE = re.compile(
    r"(?:원자료|공통자료|제공\s*자료).{0,55}"
    r"(?:미기재|표시되지|제공되지|목록이\s*없|확인되지|기재(?:되어\s*있지|되지)|"
    r"적혀\s*있지|비어\s*있|빈칸|(?:이름|학교명)이?\s*없|제시하지|기록되지)"
)
POSITIVE_MISSING_SCHOOL = re.compile(r"(?:모든|인근|주변|지역\s*내).{0,20}학교.{0,20}(?:가능|대상|수업)")
OVERBROAD_SCHOOL_CLAIM = re.compile(
    r"(?:(?:모든|전)\s*(?:학년|과목)|영어(?:와|·|\s*및\s*)수학\s*모두).{0,25}(?:가능|수업|지도|대상|제공)"
)
NEGATIVE_LIMIT_CUE = re.compile(r"(?:아니|않|못|보장하지|의미하지|별도\s*확인|원자료.{0,20}미기재)")
ADJACENT_WORD_REPEAT = re.compile(r"(?<![가-힣A-Za-z0-9])([가-힣]{2,})\s+\1(?![가-힣A-Za-z0-9])")


def norm(value: Any) -> str:
    return re.sub(r"\s+", " ", html.unescape(str(value or ""))).strip()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def slugify(value: str) -> str:
    # The 14 disambiguated source labels map to existing routes by whitespace
    # removal only (for example ``부천 상동`` -> ``부천상동``).
    return re.sub(r"\s+", "", norm(value))


def split_school_source(raw: str) -> tuple[str, ...]:
    """Split only the delimiters that occur in the authoritative field.

    Suffix inference is forbidden: it was the source of the historic
    ``창원중앙여고 -> 창원중 + 앙여고`` corruption.
    """

    text = norm(raw)
    if not text or text == GENERIC_HIGH:
        return ()
    result: list[str] = []
    for part in re.split(r"\s*[,/.]+\s*", text):
        token = norm(part)
        if token and token not in result:
            result.append(token)
    return tuple(result)


def source_state(raw: str) -> str:
    text = norm(raw)
    if not text:
        return "missing"
    if text == GENERIC_HIGH:
        return "coverage"
    return "provided"


@dataclass(frozen=True)
class SchoolLevelSource:
    raw: str
    state: str
    schools: tuple[str, ...]


@dataclass(frozen=True)
class SourceRow:
    slug: str
    source_locality: str
    locality: str
    region: str
    city: str
    levels: Mapping[str, SchoolLevelSource]


@dataclass
class Finding:
    code: str
    location: str
    message: str


@dataclass
class Audit:
    errors: list[Finding] = field(default_factory=list)
    observations: dict[str, Any] = field(default_factory=dict)

    def error(self, code: str, location: str | Path, message: str) -> None:
        if isinstance(location, Path):
            try:
                shown = location.resolve().relative_to(ROOT.resolve()).as_posix()
            except ValueError:
                shown = str(location)
        else:
            shown = location
        self.errors.append(Finding(code, shown, message))


def load_source(common: Path, audit: Audit) -> tuple[list[SourceRow], str]:
    path = common / SOURCE_NAME
    if not path.is_file():
        audit.error("source_missing", path, "authoritative CSV missing")
        return [], ""
    raw_bytes = path.read_bytes()
    try:
        with path.open(encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
    except (OSError, UnicodeError, csv.Error) as exc:
        audit.error("source_read", path, str(exc))
        return [], sha256_bytes(raw_bytes)
    required = {"근처 수업가능 동네", "지역", "시or구", *LEVEL_COLUMN.values()}
    columns = set(rows[0]) if rows else set()
    if missing := required - columns:
        audit.error("source_columns", path, f"missing columns={sorted(missing)}")
        return [], sha256_bytes(raw_bytes)

    result: list[SourceRow] = []
    seen: set[str] = set()
    level_metrics: dict[str, Counter[str]] = {level: Counter() for level in LEVEL_COLUMN}
    for number, row in enumerate(rows, start=2):
        source_locality = norm(row["근처 수업가능 동네"])
        slug = slugify(source_locality)
        if not slug or slug in seen:
            audit.error("source_slug", path, f"row={number}, slug={slug!r}")
            continue
        seen.add(slug)
        levels: dict[str, SchoolLevelSource] = {}
        for level, column in LEVEL_COLUMN.items():
            cell = norm(row[column])
            state = source_state(cell)
            schools = split_school_source(cell)
            if state == "provided" and not schools:
                audit.error("source_token_empty", path, f"row={number}, level={level}, raw={cell!r}")
            if state != "provided" and schools:
                audit.error("source_state_tokens", path, f"row={number}, level={level}")
            expected_suffix = {"elementary": ("초", "초등학교"), "middle": ("중", "중학교"), "high": ("고", "고등학교")}[level]
            for school in schools:
                if not school.endswith(expected_suffix):
                    audit.error("source_school_suffix", path, f"row={number}, level={level}, school={school}")
            levels[level] = SchoolLevelSource(cell, state, schools)
            level_metrics[level][f"{state}_rows"] += 1
            level_metrics[level]["deduped"] += len(schools)
        result.append(
            SourceRow(
                slug=slug,
                source_locality=source_locality,
                locality=slug,
                region=norm(row["지역"]),
                city=norm(row["시or구"]),
                levels=levels,
            )
        )
    if len(result) != EXPECTED_ROWS:
        audit.error("source_count", path, f"rows={len(result)}, expected={EXPECTED_ROWS}")
    for level, expected in EXPECTED_LEVEL_SOURCE.items():
        got = level_metrics[level]
        actual = {
            "named_rows": got["provided_rows"],
            "missing": got["missing_rows"],
            "coverage": got["coverage_rows"],
            "deduped": got["deduped"],
        }
        if actual != expected:
            audit.error("source_level_metrics", path, f"level={level}, actual={actual}, expected={expected}")
    all_names = {school for row in result for src in row.levels.values() for school in src.schools}
    if "창원중앙여고" not in all_names or "창원중" in all_names or "앙여고" in all_names:
        audit.error("source_token_integrity", path, "창원중앙여고 token integrity failed")
    compacted = [row.source_locality for row in result if row.source_locality != row.locality]
    if len(compacted) != EXPECTED_COMPACTED_LOCALITIES:
        audit.error(
            "source_locality_mapping",
            path,
            f"compacted={len(compacted)}, expected={EXPECTED_COMPACTED_LOCALITIES}, values={compacted}",
        )
    audit.observations["source"] = {
        "sha256": sha256_bytes(raw_bytes),
        "rows": len(result),
        "level_metrics": {level: dict(values) for level, values in level_metrics.items()},
        "unique_school_names": len(all_names),
        "compacted_localities": len(compacted),
    }
    return result, sha256_bytes(raw_bytes)


def expected_paths(root: Path, rows: Sequence[SourceRow]) -> dict[str, tuple[str, SourceRow]]:
    result: dict[str, tuple[str, SourceRow]] = {}
    for category in CATEGORY_LEVELS:
        for row in rows:
            rel = (Path("과목별학원") / category / row.slug / "index.html").as_posix()
            result[rel] = (category, row)
    return result


def expected_url(category: str, slug: str) -> str:
    return BASE_URL + quote(f"/과목별학원/{category}/{slug}/", safe="/")


def iter_repo_files(root: Path) -> Iterator[Path]:
    for current, dirs, files in os.walk(root, topdown=True, followlinks=False):
        dirs[:] = [name for name in dirs if name not in PRUNE_DIRS]
        base = Path(current)
        for name in files:
            yield base / name


def repository_manifest(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): sha256_file(path)
        for path in sorted(iter_repo_files(root), key=lambda item: item.as_posix())
    }


def decode_html(value: bytes) -> str:
    if value.startswith(b"\xef\xbb\xbf"):
        return value[3:].decode("utf-8")
    return value.decode("utf-8")


def import_projection(path: Path, audit: Audit) -> ModuleType | None:
    if not path.is_file():
        audit.error("projection_missing", path, "projection script missing")
        return None
    spec = importlib.util.spec_from_file_location("_school_manuscript_projection", path)
    if spec is None or spec.loader is None:
        audit.error("projection_import", path, "cannot create import spec")
        return None
    module = importlib.util.module_from_spec(spec)
    old = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    except Exception as exc:  # noqa: BLE001 - report a foreign generator failure
        audit.error("projection_import", path, repr(exc))
        return None
    finally:
        sys.dont_write_bytecode = old
    return module


def plan_documents(plan: Any, audit: Audit, location: str) -> dict[str, str]:
    value = getattr(plan, "authorized_documents", None)
    if not isinstance(value, Mapping):
        audit.error("projection_contract", location, "plan.authorized_documents must be a mapping")
        return {}
    result: dict[str, str] = {}
    for raw_key, raw_value in value.items():
        key_path = Path(str(raw_key))
        if key_path.is_absolute():
            try:
                key = key_path.resolve().relative_to(ROOT.resolve()).as_posix()
            except ValueError:
                audit.error("projection_scope", location, f"outside path={raw_key}")
                continue
        else:
            key = key_path.as_posix().lstrip("./")
        if key in result:
            audit.error("projection_duplicate", location, key)
            continue
        if isinstance(raw_value, bytes):
            try:
                result[key] = decode_html(raw_value)
            except UnicodeError as exc:
                audit.error("projection_encoding", key, str(exc))
        elif isinstance(raw_value, str):
            result[key] = raw_value
        else:
            audit.error("projection_value", key, f"type={type(raw_value).__name__}")
    return result


def call_build_plan(module: ModuleType, root: Path, common: Path, overrides: Mapping[str, str] | None, audit: Audit) -> Any:
    build = getattr(module, "build_plan", None)
    if not callable(build):
        audit.error("projection_contract", "generator", "build_plan is missing")
        return None
    signature = inspect.signature(build)
    expected = {"root", "common_dir", "current_overrides"}
    if not {"root", "common_dir"}.issubset(signature.parameters):
        audit.error("projection_signature", "generator", f"signature={signature}")
        return None
    kwargs: dict[str, Any] = {"root": root, "common_dir": common}
    if "current_overrides" in signature.parameters:
        kwargs["current_overrides"] = overrides
    elif overrides is not None:
        audit.error("projection_signature", "generator", "current_overrides unsupported")
        return None
    try:
        return build(**kwargs)
    except Exception as exc:  # noqa: BLE001
        audit.error("projection_build", "generator", repr(exc))
        return None


def projected_sources(
    root: Path,
    common: Path,
    script: Path | None,
    expected: Mapping[str, tuple[str, SourceRow]],
    source_sha: str,
    audit: Audit,
) -> tuple[dict[str, str], dict[str, str], str | None]:
    before = {rel: decode_html((root / rel).read_bytes()) for rel in expected}
    before[SITEMAP] = decode_html((root / SITEMAP).read_bytes())
    if script is None:
        return before, before, None
    module = import_projection(script, audit)
    if module is None:
        return before, before, None
    script_sha = sha256_file(script)
    first = call_build_plan(module, root, common, None, audit)
    if first is None:
        return before, before, script_sha
    final = plan_documents(first, audit, "first-plan")
    expected_scope = set(expected) | {SITEMAP}
    if set(final) != expected_scope:
        audit.error(
            "projection_scope",
            script,
            f"missing={len(expected_scope-set(final))}, extra={len(set(final)-expected_scope)}, total={len(final)}",
        )
    if getattr(first, "source_sha256", source_sha) != source_sha:
        audit.error("projection_source_sha", script, f"plan={getattr(first, 'source_sha256', None)}, actual={source_sha}")
    diagnostics = getattr(first, "diagnostics", ())
    if isinstance(diagnostics, Mapping):
        if diagnostics.get("errors") or diagnostics.get("ok") is False:
            audit.error("projection_diagnostics", script, repr(diagnostics)[:1000])
    elif diagnostics:
        audit.error("projection_diagnostics", script, repr(diagnostics)[:1000])
    second_pass_changes = getattr(first, "second_pass_changes", ())
    if second_pass_changes:
        audit.error("projection_second_pass", script, repr(second_pass_changes)[:1000])

    second = call_build_plan(module, root, common, final, audit)
    if second is not None:
        final_second = plan_documents(second, audit, "second-plan")
        if final_second != final:
            changed = [key for key in expected_scope if final_second.get(key) != final.get(key)]
            audit.error("projection_idempotency", script, f"second output differs on {len(changed)} paths")
        changed_paths = getattr(second, "changed_paths", ())
        if changed_paths:
            audit.error("projection_idempotency", script, f"second changed_paths={len(changed_paths)}")
        if getattr(second, "second_pass_changes", ()):
            audit.error("projection_idempotency", script, "second plan reports second_pass_changes")
    audit.observations["projection"] = {
        "script": str(script),
        "sha256": script_sha,
        "documents": len(final),
        "changed_paths": len(getattr(first, "changed_paths", ())),
        "before_manifest_sha256": mapping_manifest_sha(getattr(first, "before_manifest", None)),
        "after_manifest_sha256": mapping_manifest_sha(getattr(first, "after_manifest", None)),
        "diagnostics": diagnostics,
    }
    return before, final, script_sha


@dataclass
class Node:
    tag: str
    attrs: dict[str, str]
    children: list[Node | str] = field(default_factory=list)
    parent: Node | None = None


class TreeParser(HTMLParser):
    VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = Node("#document", {})
        self.stack = [self.root]

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        node = Node(tag.lower(), {key.lower(): value or "" for key, value in attrs}, parent=self.stack[-1])
        self.stack[-1].children.append(node)
        if tag.lower() not in self.VOID:
            self.stack.append(node)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag.lower() not in self.VOID:
            self.stack.pop()

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index].tag == tag:
                del self.stack[index:]
                return

    def handle_data(self, data: str) -> None:
        self.stack[-1].children.append(data)


def parse_tree(source: str, audit: Audit, location: str) -> Node:
    parser = TreeParser()
    try:
        parser.feed(source)
        parser.close()
    except Exception as exc:  # noqa: BLE001
        audit.error("html_parse", location, repr(exc))
    return parser.root


def descendants(node: Node) -> Iterator[Node]:
    for child in node.children:
        if isinstance(child, Node):
            yield child
            yield from descendants(child)


def node_text(node: Node) -> str:
    parts: list[str] = []
    for child in node.children:
        if isinstance(child, str):
            parts.append(child)
        else:
            parts.append(node_text(child))
    return norm(" ".join(parts))


def has_ancestor(node: Node, predicate: Any, stop: Node | None = None) -> bool:
    current = node.parent
    while current is not None and current is not stop:
        if predicate(current):
            return True
        current = current.parent
    return False


def visible_text_nodes(source: str, exclude_school: bool, audit: Audit, location: str) -> tuple[str, ...]:
    root = parse_tree(source, audit, location)
    result: list[str] = []

    def walk(node: Node, skipped: bool = False) -> None:
        hidden = skipped or node.tag in SKIP_VISIBLE or "hidden" in node.attrs or node.attrs.get("aria-hidden", "").lower() == "true"
        hidden = hidden or bool(re.search(r"(?:^|;)\s*display\s*:\s*none\b", node.attrs.get("style", ""), re.I))
        if exclude_school and "data-school-reference" in node.attrs:
            hidden = True
        if hidden:
            return
        for child in node.children:
            if isinstance(child, str):
                if value := norm(child):
                    result.append(value)
            else:
                walk(child, hidden)

    walk(root)
    return tuple(result)


def tag_texts(source: str, tag: str) -> tuple[str, ...]:
    return tuple(
        norm(re.sub(r"<[^>]+>", " ", match.group(1)))
        for match in re.finditer(rf"<{tag}\b[^>]*>(.*?)</{tag}\s*>", source, re.I | re.S)
    )


def attr_map(raw: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for match in re.finditer(r"([^\s=/>]+)(?:\s*=\s*(?:\"([^\"]*)\"|'([^']*)'|([^\s>]+)))?", raw, re.S):
        result[match.group(1).lower()] = html.unescape(next((x for x in match.groups()[1:] if x is not None), ""))
    return result


def canonical(source: str) -> tuple[str, ...]:
    result: list[str] = []
    for match in re.finditer(r"<link\b([^>]*)>", source, re.I | re.S):
        attrs = attr_map(match.group(1))
        if "canonical" in attrs.get("rel", "").lower().split():
            result.append(attrs.get("href", ""))
    return tuple(result)


def meta_content(source: str, key: str, expected: str) -> tuple[str, ...]:
    values: list[str] = []
    for match in re.finditer(r"<meta\b([^>]*)>", source, re.I | re.S):
        attrs = attr_map(match.group(1))
        if attrs.get(key, "").lower() == expected.lower():
            values.append(attrs.get("content", ""))
    return tuple(values)


def jsonld_nodes(source: str, audit: Audit, location: str) -> list[dict[str, Any]]:
    blocks = re.findall(
        r"<script\b[^>]*type\s*=\s*['\"]application/ld\+json['\"][^>]*>(.*?)</script\s*>",
        source,
        re.I | re.S,
    )
    result: list[dict[str, Any]] = []
    for index, block in enumerate(blocks):
        try:
            value = json.loads(block)
        except json.JSONDecodeError as exc:
            audit.error("jsonld_parse", location, f"block={index}: {exc}")
            continue
        if isinstance(value, dict) and isinstance(value.get("@graph"), list):
            result.extend(node for node in value["@graph"] if isinstance(node, dict))
        elif isinstance(value, list):
            result.extend(node for node in value if isinstance(node, dict))
        elif isinstance(value, dict):
            result.append(value)
    return result


def type_has(node: Mapping[str, Any], wanted: str) -> bool:
    value = node.get("@type")
    return wanted in value if isinstance(value, list) else value == wanted


def one_type(nodes: Sequence[dict[str, Any]], wanted: str) -> list[dict[str, Any]]:
    return [node for node in nodes if type_has(node, wanted)]


def is_school_mention(value: Any, all_school_names: set[str]) -> bool:
    if not isinstance(value, dict):
        return False
    name = norm(value.get("name"))
    raw_type = value.get("@type")
    types = set(raw_type if isinstance(raw_type, list) else [raw_type])
    return name in all_school_names or bool(types & SCHOOL_TYPES)


def is_school_itemlist(node: Mapping[str, Any], all_school_names: set[str]) -> bool:
    if not type_has(node, "ItemList"):
        return False
    identifier = str(node.get("@id", ""))
    if identifier.endswith("#schools") or "#school-reference-" in identifier:
        return True
    elements = node.get("itemListElement", [])
    names = {
        norm(item.get("name"))
        for item in elements if isinstance(item, dict)
    } if isinstance(elements, list) else set()
    return bool(names & all_school_names)


def sanitized_schema(
    nodes: Sequence[dict[str, Any]],
    all_school_names: set[str],
    school_h2: str,
    canonical_url: str,
    category: str,
    row: SourceRow,
) -> str:
    """Remove only the explicitly authorized school/freshness projection.

    Any Service, organization, FAQ, offer, address, author, image or unrelated
    article semantic drift therefore remains visible to the exact comparison.
    """

    copied: list[dict[str, Any]] = json.loads(json.dumps(list(nodes), ensure_ascii=False))
    result: list[dict[str, Any]] = []
    for node in copied:
        if node.get("@id") == canonical_url + "#school-reference" and type_has(node, "WebPageElement"):
            continue
        if is_school_itemlist(node, all_school_names):
            continue
        mentions_any = node.get("mentions")
        if isinstance(mentions_any, list):
            node["mentions"] = [
                item for item in mentions_any
                if not (
                    isinstance(item, dict)
                    and (
                        norm(item.get("name")) == GENERIC_HIGH
                        or is_school_mention(item, all_school_names)
                    )
                )
            ]
        if type_has(node, "Article"):
            node.pop("dateModified", None)
            parts = node.get("hasPart")
            if isinstance(parts, list):
                node["hasPart"] = [
                    item for item in parts
                    if not (
                        isinstance(item, dict)
                        and (
                            item.get("@id") == canonical_url + "#school-reference"
                            or norm(item.get("name")) == school_h2
                        )
                    )
                ]
            sections = node.get("articleSection")
            if isinstance(sections, list):
                node["articleSection"] = [item for item in sections if norm(item) != school_h2]
            elif norm(sections) == school_h2:
                node.pop("articleSection", None)
        if type_has(node, "WebPage"):
            node.pop("dateModified", None)
            parts = node.get("hasPart")
            if isinstance(parts, list):
                node["hasPart"] = [
                    item for item in parts
                    if not (isinstance(item, dict) and item.get("@id") == canonical_url + "#school-reference")
                ]
        result.append(node)
    corrected = authorized_schema_copy(result, category, row)
    if not isinstance(corrected, list):
        corrected = result
    corrected.sort(key=lambda item: (str(item.get("@id", "")), str(item.get("@type", "")), str(item.get("name", ""))))
    return json.dumps(corrected, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def faq_visible(source: str) -> tuple[tuple[str, str], ...]:
    result: list[tuple[str, str]] = []
    for match in re.finditer(r"<details\b([^>]*)>(.*?)</details\s*>", source, re.I | re.S):
        attrs = attr_map(match.group(1))
        if "faq" not in attrs.get("class", "").lower():
            continue
        body = match.group(2)
        summary = re.search(r"<summary\b[^>]*>(.*?)</summary\s*>", body, re.I | re.S)
        if not summary:
            continue
        question = norm(re.sub(r"<[^>]+>", " ", summary.group(1)))
        question = re.sub(r"^(?:Q|질문)\s*[:.\-)]?\s*", "", question, flags=re.I)
        answer = norm(re.sub(r"<[^>]+>", " ", body[summary.end():]))
        answer = re.sub(r"^(?:A|답변)\s*[:.\-)]?\s*", "", answer, flags=re.I)
        result.append((question, answer))
    return tuple(result)


def faq_schema(nodes: Sequence[dict[str, Any]]) -> tuple[tuple[str, str], ...]:
    pages = one_type(nodes, "FAQPage")
    if len(pages) != 1:
        return ()
    result: list[tuple[str, str]] = []
    for question in pages[0].get("mainEntity", []):
        if not isinstance(question, dict):
            continue
        answer = question.get("acceptedAnswer")
        result.append((norm(question.get("name")), norm(answer.get("text")) if isinstance(answer, dict) else ""))
    return tuple(result)


def sentence_split(text: str) -> tuple[str, ...]:
    parts = re.split(r"(?<=[.!?。！？])\s+|[\r\n]+", norm(text))
    return tuple(part.strip() for part in parts if part.strip())


HEADING_CONCEPT_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("student", re.compile(r"학생")),
    ("school", re.compile(r"(?:재학\s*)?학교(?:명|별|\s*목록|\s*정보|\s*근거)?")),
    ("grade", re.compile(r"학년(?:별)?")),
    ("subject", re.compile(r"과목(?:별)?")),
    ("schedule", re.compile(r"(?:학생\s*)?일정|시간(?:표|대)?|요일")),
    ("range", re.compile(r"범위")),
    ("arrangement", re.compile(r"(?:반\s*)?편성")),
    ("opening", re.compile(r"개설|시작")),
    ("condition", re.compile(r"조건")),
    ("class", re.compile(r"수업")),
    ("available", re.compile(r"(?<!불)가능")),
    ("source", re.compile(r"원자료|근거")),
    ("state", re.compile(r"상태")),
    ("compare", re.compile(r"대조|비교")),
    ("check", re.compile(r"(?:재)?확인|점검|검토|살피")),
    ("record", re.compile(r"기록|메모")),
    ("prepare", re.compile(r"준비|마련")),
    ("organize", re.compile(r"정리|구분|분리")),
    ("consult", re.compile(r"상담|문의|질문")),
    ("communicate", re.compile(r"전달|알리")),
)

COVERAGE_NAMED_LIST_CUE = re.compile(
    r"(?:학교\s*(?:가능\s*)?목록|가능\s*학교\s*목록|학교명\s*목록)"
)
COVERAGE_NAMED_LIST_NEGATIVE = re.compile(
    r"(?:아니|없|미기재|열거하지|생성하지|제공되지|기재되지|목록이\s*아닌)"
)

REPEATED_CONTENT_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("school", re.compile(r"학교(?:명|별)?")),
    ("grade", re.compile(r"학년(?:별)?")),
    ("subject", re.compile(r"과목(?:별)?")),
    ("class", re.compile(r"수업")),
    ("student", re.compile(r"학생")),
    ("schedule", re.compile(r"일정")),
    ("time", re.compile(r"시간(?:표|대)?")),
    ("day", re.compile(r"요일")),
    ("range", re.compile(r"범위")),
    ("condition", re.compile(r"조건")),
    ("arrangement", re.compile(r"편성")),
    ("available", re.compile(r"(?<!불)가능")),
    ("check", re.compile(r"(?:재)?확인|점검|검토|살피")),
    ("compare", re.compile(r"대조|비교")),
    ("consult", re.compile(r"상담")),
    ("inquiry", re.compile(r"문의")),
    ("record", re.compile(r"기록")),
    ("source", re.compile(r"원자료")),
    ("list", re.compile(r"목록")),
)


def heading_concept_signature(value: str) -> frozenset[str]:
    return frozenset(
        name for name, pattern in HEADING_CONCEPT_PATTERNS if pattern.search(norm(value))
    )


def heading_semantic_collision(text: str) -> tuple[str, str, tuple[str, ...]] | None:
    """Return a redundant ``A부터 B까지`` H2 tail, including synonyms.

    The release renderer composes the colon tail from independent banks.  Exact
    string deduplication cannot catch pairs such as ``학생 일정 대조`` and
    ``학생 일정 비교``.  A deliberately small concept lexicon closes that gap
    without treating every shared word (for example ``학교``) as a collision.
    """

    match = re.search(r"[:：]\s*(.+?)부터\s+(.+?)까지\s*$", norm(text))
    if not match:
        return None
    left, right = (norm(match.group(1)), norm(match.group(2)))

    left_signature = heading_concept_signature(left)
    right_signature = heading_concept_signature(right)
    if not left_signature or not right_signature:
        return None
    shared = left_signature & right_signature
    action_families = {
        "compare", "check", "record", "prepare", "organize", "consult", "communicate"
    }
    # Equal concept signatures are always redundant.  A near-equal pair is
    # redundant only when it also repeats the same semantic action.
    union = left_signature | right_signature
    if left_signature == right_signature or (
        bool(shared & action_families) and len(shared) >= 2 and len(shared) / len(union) >= 0.75
    ):
        return left, right, tuple(sorted(shared))
    return None


def heading_subject_collisions(
    text: str, category: str, row: SourceRow
) -> tuple[dict[str, str], tuple[tuple[str, tuple[str, ...]], ...]] | None:
    """Parse the renderer H2 and compare the subject with all bank fragments."""

    normalized = norm(text)
    if ":" not in normalized and "：" not in normalized:
        return None
    lead, tail = re.split(r"[:：]", normalized, maxsplit=1)
    category_values = sorted(
        {value for value in CATEGORY_COPY_VALUES[category] if value.endswith("학원")},
        key=len,
        reverse=True,
    )
    body = ""
    for value in category_values:
        prefix = f"{row.locality} {value} "
        if lead.startswith(prefix):
            body = lead[len(prefix):]
            break
    subject_match = re.fullmatch(r"(.+?)와\s+(.+)", body)
    tail_match = re.fullmatch(r"(.+?)부터\s+(.+?)까지", norm(tail))
    if not subject_match or not tail_match:
        return None
    components = {
        "subject": norm(subject_match.group(1)),
        "focus": norm(subject_match.group(2)),
        "start": norm(tail_match.group(1)),
        "end": norm(tail_match.group(2)),
    }
    subject_signature = heading_concept_signature(components["subject"])
    collisions: list[tuple[str, tuple[str, ...]]] = []
    for label in ("focus", "start", "end"):
        shared = tuple(sorted(subject_signature & heading_concept_signature(components[label])))
        if shared:
            collisions.append((label, shared))
    return components, tuple(collisions)


def repeated_content_families(text: str) -> dict[str, int]:
    """Find repeated content concepts inside one authored sentence."""

    value = unicodedata.normalize("NFKC", norm(text))
    return {
        family: count
        for family, pattern in REPEATED_CONTENT_PATTERNS
        if (count := len(pattern.findall(value))) > 1
    }


ENDING_FAMILY_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("separate-check", re.compile(r"별도로(?:다시)?(?:재)?확인")),
    ("staff-answer-record", re.compile(r"담당자답변(?:을)?받아적")),
)

# Human-reviewed atomic subject→predicate pairs.  The subject and predicate
# must travel together; independently selecting either half produced phrases
# such as ``실제 시작 시점은 받은 문구를 ... 보관``.
COMPATIBLE_ENDING_CLAUSES: tuple[tuple[str, str], ...] = (
    ("ask", "반 배정 상태는 담당자에게 직접 물어보세요."),
    ("record", "운영 안내는 받은 문구 그대로 노트에 남기세요."),
    ("listen", "담당자의 배정 설명은 끝까지 들어 보세요."),
    ("mark", "회신받은 자리 상태는 빈칸에 분명하게 표시하세요."),
    ("align", "원자료 표기와 최신 안내가 일치하는지 대조해 보세요."),
    ("preserve", "안내 문구는 받은 날짜와 함께 보관하세요."),
    ("review", "받은 회신은 처음부터 다시 읽어 보세요."),
)

GUIDANCE_CONTEXT_PHRASES: tuple[str, ...] = (
    "희망 시작 시점도 함께 메모하고",
    "학생이 가능한 요일을 별도 표시하고",
    "현재 학습 범위를 한 문장으로 덧붙이고",
    "문의하려는 과목을 정확히 구분하고",
    "가능한 시간대를 두세 개 준비하고",
    "학교명과 학년을 다시 한 번 확인하고",
    "수업에서 필요한 도움을 짧게 설명하고",
    "등록 전 궁금한 조건을 순서대로 적고",
    "학생 일정과 이동 가능 시간을 정리하고",
    "현재 사용 중인 학습 자료 범위를 알리고",
    "희망 수업 횟수를 질문 항목에 넣고",
    "상담 답변을 기록할 자리를 마련하고",
    "학년과 과목을 서로 다른 칸에 적고",
    "학생의 우선 목표를 한 가지로 정리하고",
    "시작 가능 날짜를 참고 항목으로 두고",
    "학교 범위와 개인 조건을 구분하고",
    "현재 편성 질문을 마지막 항목에 넣고",
    "필요한 확인 사항을 짧게 묶어 두고",
    "상담 시점의 날짜를 함께 기록하고",
    "학생에게 맞는 시간 후보를 준비하고",
    "학교·학년·과목 순서로 메모하고",
    "현재 수업 조건을 확인할 질문을 만들고",
    "최종 답변과 원자료를 나란히 볼 수 있게 준비하고",
)

LEVEL_STATE_PREFIX: dict[str, str] = {
    "elementary": "초등 학습 단계 상담에서는 ",
    "middle": "중등 교과 단계 상담에서는 ",
    "high": "고등 학습 단계 상담에서는 ",
}

LEVEL_GUIDANCE_PREFIX: dict[str, str] = {
    "elementary": "초등 단계 기준으로 ",
    "middle": "중등 단계 기준으로 ",
    "high": "고등 단계 기준으로 ",
}


def guidance_context_counts(text: str) -> Counter[str]:
    """Count only the generator-owned, human-reviewed guidance contexts."""

    value = norm(text)
    return Counter(
        {
            phrase: value.count(phrase)
            for phrase in GUIDANCE_CONTEXT_PHRASES
            if phrase in value
        }
    )


def compatible_ending_family(text: str) -> str | None:
    value = norm(text)
    matches = [family for family, clause in COMPATIBLE_ENDING_CLAUSES if value.endswith(clause)]
    return matches[0] if len(matches) == 1 else None


def strip_compatible_ending(text: str) -> tuple[str, str] | None:
    """Return the reviewed family and the text before its inseparable clause."""

    value = norm(text)
    matches = [
        (family, clause)
        for family, clause in COMPATIBLE_ENDING_CLAUSES
        if value.endswith(clause)
    ]
    if len(matches) != 1:
        return None
    family, clause = matches[0]
    return family, norm(value[: -len(clause)])


def state_stem_signature(text: str, level: str) -> tuple[str, str] | None:
    """Remove only the owned level prefix and reviewed ending from state copy."""

    stripped = strip_compatible_ending(text)
    prefix = LEVEL_STATE_PREFIX.get(level)
    if stripped is None or prefix is None:
        return None
    family, body = stripped
    if not body.startswith(prefix):
        return None
    stem = norm(body[len(prefix) :])
    return (family, stem) if stem else None


def guidance_lead_signature(text: str, level: str) -> tuple[str, str, str] | None:
    """Prove one level-owned context between its prefix, lead, and ending."""

    stripped = strip_compatible_ending(text)
    prefix = LEVEL_GUIDANCE_PREFIX.get(level)
    if stripped is None or prefix is None:
        return None
    family, body = stripped
    if not body.startswith(prefix):
        return None
    body = norm(body[len(prefix) :])
    matches = [
        context
        for context in GUIDANCE_CONTEXT_PHRASES
        if body.endswith(context) and (body == context or body.endswith(" " + context))
    ]
    if len(matches) != 1:
        return None
    context = matches[0]
    lead = norm(body[: -len(context)])
    return (family, context, lead) if lead else None


def closing_context_signature(text: str) -> tuple[str, str, str] | None:
    """Return the renderer-owned context in the single closing paragraph."""

    stripped = strip_compatible_ending(text)
    if stripped is None:
        return None
    family, body = stripped
    matches = [
        context
        for context in GUIDANCE_CONTEXT_PHRASES
        if body.endswith(context) and (body == context or body.endswith(" " + context))
    ]
    if len(matches) != 1:
        return None
    context = matches[0]
    lead = norm(body[: -len(context)])
    return (family, context, lead) if lead else None


def ending_tokens(text: str) -> tuple[str, ...]:
    value = unicodedata.normalize("NFKC", norm(text)).lower()
    return tuple(re.findall(r"[0-9a-z가-힣]+", value))


def authored_ending_repeats(texts: Sequence[str]) -> dict[str, Any]:
    """Measure repeated endings across separate authored sentences on a page."""

    clauses: Counter[str] = Counter()
    suffixes: dict[int, Counter[str]] = {size: Counter() for size in (5, 6, 7)}
    families: Counter[str] = Counter()
    sentences: list[str] = []
    for block in texts:
        for sentence in sentence_split(block):
            sentences.append(sentence)
            parts = [part for part in re.split(r"[,，;；:：]\s*", sentence) if norm(part)]
            final_clause_tokens = ending_tokens(parts[-1] if parts else sentence)
            if len(final_clause_tokens) >= 2:
                clauses[" ".join(final_clause_tokens)] += 1
            tokens = ending_tokens(sentence)
            for size, counter in suffixes.items():
                if len(tokens) >= size:
                    counter[" ".join(tokens[-size:])] += 1
            compact = "".join(tokens)
            for family, pattern in ENDING_FAMILY_PATTERNS:
                if pattern.search(compact):
                    families[family] += 1
    return {
        "sentences": len(sentences),
        "final_clauses": {value: count for value, count in clauses.items() if count > 1},
        "suffixes": {
            str(size): {value: count for value, count in counter.items() if count > 1}
            for size, counter in suffixes.items()
            if any(count > 1 for count in counter.values())
        },
        "families": {value: count for value, count in families.items() if count > 1},
    }


def diversity_norm(text: str, category: str, row: SourceRow, all_schools: Sequence[str]) -> str:
    value = unicodedata.normalize("NFKC", norm(text)).lower()
    replacements = [
        row.locality,
        row.region,
        row.city,
        *CATEGORY_COPY_VALUES[category],
        *LEVEL_KOREAN.values(),
        "초등학교",
        "중학교",
        "고등학교",
        *all_schools,
    ]
    for item in sorted({norm(item) for item in replacements if norm(item)}, key=len, reverse=True):
        value = value.replace(item.lower(), " [값] ")
    value = re.sub(r"(?<![가-힣0-9])(?:초[1-6]|중[1-3]|고[1-3])(?![가-힣0-9])", " [학년] ", value)
    value = re.sub(r"[^0-9a-z가-힣]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def school_like_tokens(text: str) -> set[str]:
    result: set[str] = set()
    particles = ("으로는", "으로", "에서", "에게", "까지", "부터", "처럼", "보다", "은", "는", "이", "가", "을", "를", "와", "과", "의", "도", "에", "로")
    generic = {
        "초", "중", "고", "초등학교", "중학교", "고등학교", "학교", "재학중", "학년중",
        "인근고", "주변고", "지역고", "학교별", "여고생", "중고", "초중고",
    }
    for raw in re.findall(r"[가-힣A-Za-z0-9]{2,}", text):
        token = raw
        for particle in particles:
            if token.endswith(particle) and len(token) > len(particle) + 1:
                token = token[:-len(particle)]
                break
        if token in generic:
            continue
        # Bare ``초/중/고`` suffixes are unsafe in unrestricted prose: ordinary
        # Korean verb forms such as ``확인하고`` would be false positives.  Bare
        # abbreviated school names are still closed by the exact chip/schema
        # source gates and by the known-source reference scan below.
        if token.endswith(("초등학교", "중학교", "고등학교", "여고", "남고", "외고", "과학고", "예고", "체고", "상고", "공고")):
            result.add(token)
    return result


def known_school_references(text: str, all_names: Iterable[str]) -> set[str]:
    """Return exact school tokens without an O(pages × all-schools) regex scan."""

    names = set(all_names)
    result: set[str] = set()
    particles = ("에서는", "에서", "에게", "으로", "까지", "부터", "처럼", "보다", "은", "는", "이", "가", "을", "를", "와", "과", "의", "도", "에", "로")
    for token in re.findall(r"[가-힣A-Za-z0-9]+", text):
        if token in names:
            result.add(token)
            continue
        for particle in particles:
            if token.endswith(particle):
                candidate = token[: -len(particle)]
                if candidate in names:
                    result.add(candidate)
                    break
    return result


def authorized_existing_copy(value: str, category: str, row: SourceRow) -> str:
    """Canonicalize only the approved 15-page 창원중앙여고 correction.

    No other pre-existing prose correction is authorized by this release.
    """

    text = norm(value)
    if row.locality not in CHANGWON_LOCALITIES:
        return text
    if category in CHANGWON_HIGH_CATEGORIES:
        text = text.replace("창원중앙여고", "[SCHOOL_CORRECTION]").replace("앙여고", "[SCHOOL_CORRECTION]")
    elif category in CHANGWON_MIDDLE_CATEGORIES:
        text = STANDALONE_CHANGWON_MIDDLE.sub("", text)
    elif category == "영수학원":
        text = text.replace("창원중앙여고", "[SCHOOL_CORRECTION]").replace("앙여고", "[SCHOOL_CORRECTION]")
        text = STANDALONE_CHANGWON_MIDDLE.sub("", text)
    text = re.sub(r"\s*([,，./|·;])(?:\s*\1)*\s*", r"\1", text)
    text = re.sub(r"[,，./|·;]+(?=\[SCHOOL_CORRECTION\])", "", text)
    text = re.sub(r"[,，./|·;]+(?=(?:입니다|이며|이고|로서|$))", "", text)
    text = re.sub(r"(?:^|\s)[,，./|·;]+(?=\s|$)", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def authorized_schema_copy(value: Any, category: str, row: SourceRow) -> Any:
    if row.locality not in CHANGWON_LOCALITIES:
        return value
    if isinstance(value, str):
        return authorized_existing_copy(value, category, row)
    if isinstance(value, list):
        result: list[Any] = []
        for item in value:
            converted = authorized_schema_copy(item, category, row)
            if converted is not None:
                result.append(converted)
        return result
    if not isinstance(value, dict):
        return value
    name = norm(value.get("name"))
    if category in CHANGWON_MIDDLE_CATEGORIES | {"영수학원"} and name == "창원중":
        return None
    result = {key: authorized_schema_copy(item, category, row) for key, item in value.items()}
    if category in CHANGWON_HIGH_CATEGORIES | {"영수학원"} and name in {"앙여고", "창원중앙여고"}:
        result["name"] = "[SCHOOL_CORRECTION]"
    return result


def node_school_level(node: Node, outer: Node) -> str:
    current: Node | None = node
    while current is not None:
        if value := current.attrs.get("data-school-level"):
            return value
        if current is outer:
            break
        current = current.parent
    return ""


@dataclass
class ManuscriptMetrics:
    paragraphs: list[tuple[str, str, str]] = field(default_factory=list)
    sentences: list[tuple[str, str, str]] = field(default_factory=list)
    h2s: list[tuple[str, str, str]] = field(default_factory=list)
    group_states: Counter[str] = field(default_factory=Counter)
    school_occurrences: int = 0
    changwon_corrections: int = 0
    heading_semantic_collisions: int = 0
    heading_collision_samples: list[dict[str, Any]] = field(default_factory=list)
    heading_subject_collisions: int = 0
    heading_subject_collision_samples: list[dict[str, Any]] = field(default_factory=list)
    sentence_semantic_repeats: int = 0
    sentence_repeat_pages: set[str] = field(default_factory=set)
    sentence_repeat_families: Counter[str] = field(default_factory=Counter)
    sentence_repeat_samples: list[dict[str, Any]] = field(default_factory=list)
    coverage_named_list_claims: int = 0
    coverage_named_list_samples: list[dict[str, Any]] = field(default_factory=list)
    authored_ending_repeat_pages: int = 0
    authored_final_clause_repeats: int = 0
    authored_suffix_repeats: Counter[str] = field(default_factory=Counter)
    authored_ending_family_repeats: Counter[str] = field(default_factory=Counter)
    authored_ending_repeat_samples: list[dict[str, Any]] = field(default_factory=list)
    compatible_ending_families: Counter[str] = field(default_factory=Counter)
    incompatible_ending_sentences: int = 0
    incompatible_ending_samples: list[dict[str, Any]] = field(default_factory=list)
    guidance_context_occurrences: int = 0
    guidance_context_duplicate_pages: int = 0
    guidance_context_cardinality_pages: int = 0
    guidance_context_samples: list[dict[str, Any]] = field(default_factory=list)
    state_stem_repeat_pages: int = 0
    state_stem_boundary_pages: int = 0
    guidance_lead_repeat_pages: int = 0
    guidance_context_ownership_pages: int = 0
    ownership_samples: list[dict[str, Any]] = field(default_factory=list)


def audit_manuscript_page(
    rel: str,
    category: str,
    row: SourceRow,
    before: str,
    final: str,
    all_school_names: set[str],
    metrics: ManuscriptMetrics,
    audit: Audit,
) -> None:
    location = rel
    url = expected_url(category, row.slug)
    if final.count(START_MARKER) != 1 or final.count(END_MARKER) != 1 or final.find(START_MARKER) >= final.find(END_MARKER):
        audit.error("school_markers", location, "expected one ordered start/end marker pair")

    before_visible = visible_text_nodes(before, True, audit, location + ":before")
    final_visible = visible_text_nodes(final, True, audit, location + ":final")
    before_visible_copy = tuple(
        value for item in before_visible
        if (value := authorized_existing_copy(item, category, row))
    )
    final_visible_copy = tuple(
        value for item in final_visible
        if (value := authorized_existing_copy(item, category, row))
    )
    if before_visible_copy != final_visible_copy:
        audit.error("existing_visible_parity", location, "visible nodes outside school section changed")
    before_faq_copy = tuple(
        (authorized_existing_copy(q, category, row), authorized_existing_copy(a, category, row))
        for q, a in faq_visible(before)
    )
    final_faq_copy = tuple(
        (authorized_existing_copy(q, category, row), authorized_existing_copy(a, category, row))
        for q, a in faq_visible(final)
    )
    if before_faq_copy != final_faq_copy:
        audit.error("faq_visible_changed", location, "existing visible FAQ changed")
    if row.locality in CHANGWON_LOCALITIES and category in (
        CHANGWON_HIGH_CATEGORIES | CHANGWON_MIDDLE_CATEGORIES | {"영수학원"}
    ):
        metrics.changwon_corrections += 1
        outside_text = " ".join(final_visible)
        standalone_low = STANDALONE_CHANGWON_MIDDLE.search(outside_text)
        broken_high = STANDALONE_BROKEN_HIGH.search(outside_text)
        if standalone_low or broken_high:
            audit.error("changwon_school_fragment", location, f"창원중={bool(standalone_low)}, 앙여고={bool(broken_high)}")
        if category in CHANGWON_HIGH_CATEGORIES | {"영수학원"} and "창원중앙여고" not in outside_text:
            audit.error("changwon_school_missing", location, "corrected source school absent outside new section")

    expected_canonical = url
    if canonical(final) != (expected_canonical,):
        audit.error("canonical", location, repr(canonical(final)))
    if canonical(before) != canonical(final):
        audit.error("canonical_changed", location, "canonical changed")
    if meta_content(final, "property", "og:url") != (expected_canonical,):
        audit.error("og_url", location, repr(meta_content(final, "property", "og:url")))
    for label, extractor in (("title", lambda x: tag_texts(x, "title")), ("h1", lambda x: tag_texts(x, "h1"))):
        if extractor(before) != extractor(final):
            audit.error(f"{label}_changed", location, f"before={extractor(before)}, after={extractor(final)}")
    if meta_content(before, "name", "description") != meta_content(final, "name", "description"):
        audit.error("meta_description_changed", location, "description changed")

    tree = parse_tree(final, audit, location)
    outers = [node for node in descendants(tree) if "data-school-reference" in node.attrs]
    if len(outers) != 1:
        audit.error("school_section_count", location, f"sections={len(outers)}")
        return
    outer = outers[0]
    if outer.attrs.get("data-source-field") != "target-schools":
        audit.error("school_source_field", location, repr(outer.attrs.get("data-source-field")))
    level_nodes = [node for node in descendants(outer) if node.attrs.get("data-school-level") and not has_ancestor(node, lambda x: bool(x.attrs.get("data-school-level")), outer)]
    expected_levels = CATEGORY_LEVELS[category]
    got_levels = tuple(node.attrs.get("data-school-level", "") for node in level_nodes)
    if got_levels != expected_levels:
        audit.error("school_level_groups", location, f"actual={got_levels}, expected={expected_levels}")

    visible_school_names: list[str] = []
    level_headings: dict[str, str] = {}
    source_state_texts: list[str] = []
    source_fact_texts: list[str] = []
    source_state_authored: list[str] = []
    source_state_authored_by_level: dict[str, str] = {}
    guidance_by_level: dict[str, str] = {}
    for group in level_nodes:
        level = group.attrs.get("data-school-level", "")
        source = row.levels[level]
        state = group.attrs.get("data-source-state", "")
        if state != source.state:
            audit.error("school_source_state", location, f"level={level}, actual={state}, expected={source.state}")
        metrics.group_states[state] += 1
        group_h3s = [node_text(node) for node in descendants(group) if node.tag == "h3"]
        if len(group_h3s) != 1:
            audit.error("school_level_heading", location, f"level={level}, h3={group_h3s}")
            level_headings[level] = ""
        else:
            level_headings[level] = group_h3s[0]
        states = [node for node in descendants(group) if "data-school-source-state" in node.attrs]
        if len(states) != 1:
            audit.error("school_state_node", location, f"level={level}, count={len(states)}")
            state_text = ""
            fact_text = ""
        else:
            state_text = node_text(states[0])
            if "data-source-raw" in states[0].attrs:
                audit.error("school_source_raw_exposed", location, f"level={level}")
            fact_nodes = [node for node in descendants(states[0]) if "data-school-source-fact" in node.attrs]
            authored_nodes = [node for node in descendants(states[0]) if "data-school-authored-copy" in node.attrs]
            if len(fact_nodes) != 1 or len(authored_nodes) != 1:
                audit.error(
                    "school_state_boundaries",
                    location,
                    f"level={level}, fact={len(fact_nodes)}, authored={len(authored_nodes)}",
                )
                fact_text = state_text
            else:
                fact_text = node_text(fact_nodes[0])
                authored_text = node_text(authored_nodes[0])
                if not authored_text:
                    audit.error("school_state_boundaries", location, f"level={level}, empty authored copy")
                else:
                    source_state_authored.append(authored_text)
                    source_state_authored_by_level[level] = authored_text
        source_state_texts.append(state_text)
        source_fact_texts.append(fact_text)
        guidance_nodes = [
            node
            for node in descendants(group)
            if node.tag == "p"
            and "data-school-source-state" not in node.attrs
            and not has_ancestor(
                node,
                lambda parent: "data-school-source-state" in parent.attrs,
                group,
            )
        ]
        if len(guidance_nodes) != 1:
            audit.error(
                "school_guidance_node",
                location,
                f"level={level}, count={len(guidance_nodes)}",
            )
        else:
            guidance_by_level[level] = node_text(guidance_nodes[0])
        chips = [node for node in descendants(group) if "data-source-school" in node.attrs]
        chip_values: list[str] = []
        for chip in chips:
            attr_value = chip.attrs.get("data-source-school", "")
            text_value = node_text(chip)
            if attr_value != text_value:
                audit.error("school_chip_attr_text", location, f"level={level}, attr={attr_value!r}, text={text_value!r}")
            chip_values.append(text_value)
        if tuple(chip_values) != source.schools:
            audit.error("school_chip_source", location, f"level={level}, actual={chip_values}, expected={source.schools}")
        visible_school_names.extend(chip_values)
        metrics.school_occurrences += len(chip_values)
        coverage_positive = (
            source.state == "coverage"
            and GENERIC_HIGH in fact_text
            and "가능 범위" in fact_text
        )
        if source.state in {"provided", "coverage"} and not (
            POSITIVE_SCHOOL_CUE.search(fact_text) or coverage_positive
        ):
            audit.error("school_positive_meaning", location, f"level={level}, text={fact_text!r}")
        if source.state in {"provided", "coverage"} and WEAK_REFERENCE_CUE.search(fact_text):
            audit.error("school_meaning_weakened", location, f"level={level}, text={fact_text!r}")
        if source.state == "coverage" and GENERIC_HIGH not in fact_text:
            audit.error("school_coverage_exact", location, f"level={level}, text={fact_text!r}")
        if source.state == "missing":
            if not MISSING_CUE.search(fact_text):
                audit.error("school_missing_disclosure", location, f"level={level}, text={fact_text!r}")
            if POSITIVE_MISSING_SCHOOL.search(fact_text):
                audit.error("school_missing_positive", location, f"level={level}, text={fact_text!r}")

    h2_nodes = [node for node in descendants(outer) if node.tag == "h2"]
    if len(h2_nodes) != 1:
        audit.error("school_h2_count", location, f"h2={len(h2_nodes)}")
        h2_text = ""
    else:
        h2_text = node_text(h2_nodes[0])
        metrics.h2s.append((location, category, h2_text))
        if collision := heading_semantic_collision(h2_text):
            metrics.heading_semantic_collisions += 1
            if len(metrics.heading_collision_samples) < 20:
                metrics.heading_collision_samples.append(
                    {"path": location, "heading": h2_text, "left": collision[0], "right": collision[1], "shared": collision[2]}
                )
            audit.error(
                "school_h2_semantic_collision",
                location,
                f"left={collision[0]!r}, right={collision[1]!r}, shared={collision[2]!r}",
            )
        parsed_heading = heading_subject_collisions(h2_text, category, row)
        if parsed_heading is None:
            audit.error("school_h2_composition_shape", location, h2_text)
        elif parsed_heading[1]:
            components, collisions = parsed_heading
            metrics.heading_subject_collisions += 1
            if len(metrics.heading_subject_collision_samples) < 20:
                metrics.heading_subject_collision_samples.append(
                    {"path": location, "heading": h2_text, "components": components, "collisions": collisions}
                )
            audit.error(
                "school_h2_subject_collision",
                location,
                f"components={components!r}, collisions={collisions!r}",
            )

    state_stems: dict[str, str] = {}
    guidance_leads: dict[str, str] = {}
    owned_contexts: list[str] = []
    ownership_issues: list[dict[str, Any]] = []
    state_boundary_issues: list[dict[str, Any]] = []
    for level in expected_levels:
        state_text = source_state_authored_by_level.get(level, "")
        state_signature = state_stem_signature(state_text, level)
        if state_signature is None:
            state_boundary_issues.append(
                {"level": level, "kind": "state-boundary", "text": state_text}
            )
        else:
            state_stems[level] = state_signature[1]

        guidance_text = guidance_by_level.get(level, "")
        guidance_signature = guidance_lead_signature(guidance_text, level)
        if guidance_signature is None:
            ownership_issues.append(
                {"level": level, "kind": "guidance-boundary", "text": guidance_text}
            )
        else:
            _, context, lead = guidance_signature
            guidance_leads[level] = lead
            owned_contexts.append(context)

    if state_boundary_issues:
        metrics.state_stem_boundary_pages += 1
        audit.error("school_state_stem_boundary", location, repr(state_boundary_issues[:3]))
    if len(state_stems) != len(set(state_stems.values())):
        metrics.state_stem_repeat_pages += 1
        audit.error("school_state_stem_repeat", location, repr(state_stems))
    if len(guidance_leads) != len(set(guidance_leads.values())):
        metrics.guidance_lead_repeat_pages += 1
        audit.error("school_guidance_lead_repeat", location, repr(guidance_leads))

    answer_boxes = [
        node
        for node in descendants(outer)
        if "subject-answer-box" in node.attrs.get("class", "").split()
    ]
    if len(answer_boxes) != 1:
        ownership_issues.append(
            {"kind": "closing-container", "count": len(answer_boxes)}
        )
    else:
        closing_nodes = [node for node in descendants(answer_boxes[0]) if node.tag == "p"]
        if len(closing_nodes) != 1:
            ownership_issues.append(
                {"kind": "closing-paragraph", "count": len(closing_nodes)}
            )
        else:
            closing_text = node_text(closing_nodes[0])
            closing_signature = closing_context_signature(closing_text)
            if closing_signature is None:
                ownership_issues.append(
                    {"kind": "closing-boundary", "text": closing_text}
                )
            else:
                owned_contexts.append(closing_signature[1])

    excluded_attr = {"data-school-source-state", "data-source-school"}
    paragraphs = [
        node for node in descendants(outer)
        if node.tag == "p"
        and not any(key in node.attrs for key in excluded_attr)
        and not has_ancestor(node, lambda parent: any(key in parent.attrs for key in excluded_attr), outer)
        and not any(any(key in child.attrs for key in excluded_attr) for child in descendants(node))
    ]
    authored = [*source_state_authored, *[node_text(node) for node in paragraphs if node_text(node)]]
    if len(authored) < 2:
        audit.error("school_copy_thin", location, f"authored paragraphs={len(authored)}")
    if sum(len(re.sub(r"\s+", "", text)) for text in authored) < 100:
        audit.error("school_copy_thin", location, "authored copy under 100 non-space characters")
    page_sentence_repeats: list[tuple[str, dict[str, int]]] = []
    page_incompatible_endings: list[str] = []
    for paragraph in authored:
        metrics.paragraphs.append((location, category, paragraph))
        for sentence in sentence_split(paragraph):
            metrics.sentences.append((location, category, sentence))
            repeated = repeated_content_families(sentence)
            if repeated:
                metrics.sentence_semantic_repeats += 1
                metrics.sentence_repeat_pages.add(location)
                metrics.sentence_repeat_families.update(repeated)
                page_sentence_repeats.append((sentence, repeated))
                if len(metrics.sentence_repeat_samples) < 30:
                    metrics.sentence_repeat_samples.append(
                        {"path": location, "sentence": sentence, "families": repeated}
                    )
            ending_family = compatible_ending_family(sentence)
            if ending_family is None:
                metrics.incompatible_ending_sentences += 1
                page_incompatible_endings.append(sentence)
                if len(metrics.incompatible_ending_samples) < 30:
                    metrics.incompatible_ending_samples.append(
                        {"path": location, "sentence": sentence}
                    )
            else:
                metrics.compatible_ending_families[ending_family] += 1
    if page_sentence_repeats:
        audit.error(
            "school_sentence_semantic_repeat",
            location,
            repr(page_sentence_repeats[:3]),
        )
    if page_incompatible_endings:
        audit.error(
            "school_ending_subject_predicate",
            location,
            repr(page_incompatible_endings[:3]),
        )
    ending_repeats = authored_ending_repeats(authored)
    if ending_repeats["final_clauses"] or ending_repeats["suffixes"] or ending_repeats["families"]:
        metrics.authored_ending_repeat_pages += 1
        metrics.authored_final_clause_repeats += len(ending_repeats["final_clauses"])
        for size, values in ending_repeats["suffixes"].items():
            metrics.authored_suffix_repeats[size] += len(values)
        metrics.authored_ending_family_repeats.update(ending_repeats["families"])
        if len(metrics.authored_ending_repeat_samples) < 30:
            metrics.authored_ending_repeat_samples.append(
                {"path": location, **ending_repeats}
            )
        audit.error("school_authored_ending_repeat", location, repr(ending_repeats))
    coverage_only = bool(expected_levels) and all(
        row.levels[level].state == "coverage" for level in expected_levels
    )
    if coverage_only:
        for sentence in (item for paragraph in authored for item in sentence_split(paragraph)):
            if COVERAGE_NAMED_LIST_CUE.search(sentence) and not COVERAGE_NAMED_LIST_NEGATIVE.search(sentence):
                metrics.coverage_named_list_claims += 1
                if len(metrics.coverage_named_list_samples) < 20:
                    metrics.coverage_named_list_samples.append(
                        {"path": location, "sentence": sentence}
                    )
                audit.error("school_coverage_named_list_claim", location, sentence)

    page_school_names = tuple(dict.fromkeys(visible_school_names))
    section_text = node_text(outer)
    # Remove the exact authoritative tokens before looking for fabricated
    # schools.  Some source cells intentionally contain whitespace inside one
    # field token; whitespace alone is not an approved delimiter.
    fabrication_text = section_text
    for school in sorted(page_school_names, key=len, reverse=True):
        fabrication_text = fabrication_text.replace(school, " ")
    unexpected_names = school_like_tokens(fabrication_text)
    known_references = known_school_references(fabrication_text, all_school_names)
    unexpected_names |= known_references - set(page_school_names)
    if unexpected_names:
        audit.error("school_name_fabricated", location, f"unexpected={sorted(unexpected_names)}")
    if "창원중앙여고" in page_school_names:
        if "창원중" in visible_school_names or "앙여고" in visible_school_names:
            audit.error("school_name_split", location, "창원중앙여고 was split")
    authored_scope = norm(" ".join([h2_text, *authored]))
    context_counts = guidance_context_counts(authored_scope)
    context_total = sum(context_counts.values())
    expected_contexts = 4 if category == "영수학원" else 2
    context_duplicates = {phrase: count for phrase, count in context_counts.items() if count > 1}
    metrics.guidance_context_occurrences += context_total
    if context_total != expected_contexts:
        metrics.guidance_context_cardinality_pages += 1
        audit.error(
            "school_guidance_context_count",
            location,
            f"actual={context_total}, expected={expected_contexts}, values={dict(context_counts)!r}",
        )
    if context_duplicates:
        metrics.guidance_context_duplicate_pages += 1
        if len(metrics.guidance_context_samples) < 30:
            metrics.guidance_context_samples.append(
                {"path": location, "duplicates": context_duplicates, "values": dict(context_counts)}
            )
        audit.error("school_guidance_context_repeat", location, repr(context_duplicates))
    expected_owned_contexts = len(expected_levels) + 1
    owned_context_counts = Counter(owned_contexts)
    if len(owned_contexts) != expected_owned_contexts:
        ownership_issues.append(
            {
                "kind": "owned-context-count",
                "actual": len(owned_contexts),
                "expected": expected_owned_contexts,
            }
        )
    if len(owned_contexts) != len(set(owned_contexts)):
        ownership_issues.append(
            {"kind": "owned-context-repeat", "values": owned_contexts}
        )
    if owned_context_counts != context_counts:
        ownership_issues.append(
            {
                "kind": "owned-context-scope",
                "owned": dict(owned_context_counts),
                "authored": dict(context_counts),
            }
        )
    if ownership_issues:
        metrics.guidance_context_ownership_pages += 1
        if len(metrics.ownership_samples) < 30:
            metrics.ownership_samples.append(
                {"path": location, "issues": ownership_issues[:5]}
            )
        audit.error("school_guidance_context_ownership", location, repr(ownership_issues[:5]))
    for seed in AUTHORING_SEEDS:
        if seed.lower() in authored_scope.lower():
            audit.error("school_copy_seed", location, seed)
    if "\ufffd" in section_text or any(unicodedata.category(ch) == "Cc" and ch not in "\r\n\t" for ch in section_text):
        audit.error("school_copy_control", location, "replacement/control character")
    if UNSUPPORTED_OPERATION.search(section_text):
        audit.error("school_operation_claim", location, UNSUPPORTED_OPERATION.search(section_text).group(0))
    if match := OVERBROAD_SCHOOL_CLAIM.search(section_text):
        sentence = next((item for item in sentence_split(section_text) if match.group(0) in item), match.group(0))
        if not NEGATIVE_LIMIT_CUE.search(sentence):
            audit.error("school_overbroad_claim", location, sentence)
    for block in [h2_text, *level_headings.values(), *source_fact_texts, *authored]:
        if match := ADJACENT_WORD_REPEAT.search(block):
            audit.error("school_adjacent_repeat", location, match.group(0))
            break
    for left, right, label in (("“", "”", "curly-double"), ("‘", "’", "curly-single")):
        if section_text.count(left) != section_text.count(right):
            audit.error("school_quote_balance", location, f"{label}={section_text.count(left)}/{section_text.count(right)}")
    for block in [*source_state_texts, *authored]:
        for sentence in sentence_split(block):
            # A claim can be school-specific even when it says only ``학교별``
            # rather than repeating a named chip.  Any curriculum/schedule/
            # exam assertion therefore needs an explicit confirmation/evidence
            # boundary, not merely assertions that happen to name a school.
            if SENSITIVE_SCHOOL_TERMS.search(sentence) and not SAFE_EPISTEMIC_TERMS.search(sentence):
                audit.error("school_specific_claim", location, sentence)
    locality_count = authored_scope.count(row.locality)
    category_count = max(
        (authored_scope.count(value) for value in CATEGORY_COPY_VALUES[category] if value.endswith("학원")),
        default=0,
    )
    if locality_count > 5:
        audit.error("school_locality_repetition", location, f"count={locality_count}")
    if category_count > 3:
        audit.error("school_query_repetition", location, f"count={category_count}")

    nodes = jsonld_nodes(final, audit, location)
    before_nodes = jsonld_nodes(before, audit, location + ":before")
    before_schema_frozen = authorized_existing_copy(
        sanitized_schema(before_nodes, all_school_names, h2_text, url, category, row), category, row
    )
    final_schema_frozen = authorized_existing_copy(
        sanitized_schema(nodes, all_school_names, h2_text, url, category, row), category, row
    )
    if before_schema_frozen != final_schema_frozen:
        audit.error("schema_unrelated_changed", location, "schema outside school/freshness contract changed")
    articles = one_type(nodes, "Article")
    if len(articles) != 1:
        audit.error("article_count", location, f"count={len(articles)}")
        return
    article = articles[0]
    if article.get("dateModified") != MODIFIED_DATE:
        audit.error("article_date_modified", location, repr(article.get("dateModified")))
    before_articles = one_type(before_nodes, "Article")
    if len(before_articles) == 1 and before_articles[0].get("datePublished") != article.get("datePublished"):
        audit.error("article_date_published", location, "datePublished changed")
    webpages = one_type(nodes, "WebPage")
    if len(webpages) != 1 or webpages[0].get("dateModified") != MODIFIED_DATE:
        audit.error("webpage_date_modified", location, f"count={len(webpages)}, date={webpages[0].get('dateModified') if webpages else None}")
    elif not isinstance(webpages[0].get("hasPart"), list) or {"@id": url + "#school-reference"} not in webpages[0]["hasPart"]:
        audit.error("webpage_school_haspart", location, repr(webpages[0].get("hasPart")))
    if faq_schema(nodes) != faq_visible(final):
        audit.error("faq_schema_parity", location, f"visible={len(faq_visible(final))}, schema={len(faq_schema(nodes))}")

    mentions = article.get("mentions", [])
    school_mentions: list[dict[str, Any]] = []
    for mention in mentions if isinstance(mentions, list) else []:
        if not isinstance(mention, dict):
            continue
        name = norm(mention.get("name"))
        types = mention.get("@type")
        type_values = set(types if isinstance(types, list) else [types])
        if name in all_school_names or type_values & SCHOOL_TYPES:
            school_mentions.append(mention)
    mention_names = [norm(item.get("name")) for item in school_mentions]
    if mention_names != list(page_school_names):
        audit.error("school_mentions", location, f"actual={mention_names}, expected={list(page_school_names)}")
    for mention in school_mentions:
        if mention != {"@type": "EducationalOrganization", "name": norm(mention.get("name"))}:
            audit.error("school_mention_shape", location, repr(mention))
    for owner in nodes:
        owner_mentions = owner.get("mentions")
        if isinstance(owner_mentions, list) and any(
            isinstance(item, dict) and norm(item.get("name")) == GENERIC_HIGH
            for item in owner_mentions
        ):
            audit.error("school_coverage_mentions_forbidden", location, f"owner={owner.get('@type')}")
        if owner is article or not isinstance(owner.get("mentions"), list):
            continue
        owner_school_mentions = [
            item for item in owner["mentions"]
            if is_school_mention(item, all_school_names)
        ]
        if not owner_school_mentions:
            continue
        owner_names = [norm(item.get("name")) for item in owner_school_mentions]
        if owner_names != list(page_school_names):
            audit.error(
                "school_mentions_other_node",
                location,
                f"owner={owner.get('@type')}, actual={owner_names}, expected={list(page_school_names)}",
            )
        for mention in owner_school_mentions:
            if mention != {"@type": "EducationalOrganization", "name": norm(mention.get("name"))}:
                audit.error("school_mention_shape", location, f"owner={owner.get('@type')}, mention={mention!r}")

    school_part_id = url + "#school-reference"
    has_part = article.get("hasPart", [])
    part_refs = [item for item in has_part if isinstance(item, dict) and item.get("@id") == school_part_id] if isinstance(has_part, list) else []
    resolved_parts = [node for node in nodes if node.get("@id") == school_part_id]
    if len(part_refs) != 1 or part_refs[0] != {"@id": school_part_id}:
        audit.error("school_haspart", location, f"refs={part_refs!r}")
    if len(resolved_parts) != 1:
        audit.error("school_haspart_resolve", location, f"count={len(resolved_parts)}")
    elif resolved_parts[0].get("@type") != "WebPageElement" or norm(resolved_parts[0].get("name")) != h2_text:
        audit.error("school_haspart_shape", location, repr(resolved_parts[0]))
    else:
        part = resolved_parts[0]
        if part.get("isPartOf") != {"@id": url + "#webpage"}:
            audit.error("school_haspart_parent", location, repr(part.get("isPartOf")))
        if part.get("url") != school_part_id:
            audit.error("school_haspart_url", location, repr(part.get("url")))
        allowed_part_keys = {"@type", "@id", "name", "url", "isPartOf", "description", "additionalProperty", "hasPart"}
        if extra := set(part) - allowed_part_keys:
            audit.error("school_haspart_extra", location, repr(sorted(extra)))
        coverage_levels = [level for level in expected_levels if row.levels[level].state == "coverage"]
        if coverage_levels:
            if GENERIC_HIGH not in norm(part.get("description")):
                audit.error("school_coverage_description", location, repr(part.get("description")))
            additional = json.dumps(part.get("additionalProperty"), ensure_ascii=False)
            if GENERIC_HIGH not in additional:
                audit.error("school_coverage_property", location, additional)
        expected_child_refs = [
            {"@id": url + f"#school-reference-{level}"}
            for level in expected_levels if row.levels[level].state == "provided"
        ]
        if part.get("hasPart", []) != expected_child_refs:
            audit.error("school_haspart_children", location, f"actual={part.get('hasPart')!r}, expected={expected_child_refs!r}")
        properties = part.get("additionalProperty", [])
        if not isinstance(properties, list) or len(properties) != len(expected_levels):
            audit.error("school_state_properties", location, repr(properties))
        else:
            for level, prop in zip(expected_levels, properties):
                source = row.levels[level]
                if not isinstance(prop, dict):
                    audit.error("school_state_property_shape", location, f"level={level}, value={prop!r}")
                    continue
                if prop.get("@type") != "PropertyValue" or prop.get("name") != f"{level}SourceState" or prop.get("value") != source.state:
                    audit.error("school_state_property_shape", location, f"level={level}, value={prop!r}")
                description = norm(prop.get("description"))
                if source.state == "coverage" and description != GENERIC_HIGH:
                    audit.error("school_state_property_description", location, f"level={level}, value={description!r}")
                elif source.state == "provided" and not POSITIVE_SCHOOL_CUE.search(description):
                    audit.error("school_state_property_description", location, f"level={level}, value={description!r}")
                elif source.state == "missing" and not re.search(r"(?:미기재|미표시|없)", description):
                    audit.error("school_state_property_description", location, f"level={level}, value={description!r}")
    sections = article.get("articleSection", [])
    section_values = [norm(value) for value in sections] if isinstance(sections, list) else [norm(sections)]
    if section_values.count(h2_text) != 1:
        audit.error("school_article_section", location, f"h2={h2_text!r}, sections={section_values}")

    school_lists = {
        node.get("@id", "").removeprefix(url + "#school-reference-"): node
        for node in one_type(nodes, "ItemList")
        if isinstance(node.get("@id"), str) and node.get("@id", "").startswith(url + "#school-reference-")
    }
    other_school_lists = [
        node for node in one_type(nodes, "ItemList")
        if is_school_itemlist(node, all_school_names)
        and not str(node.get("@id", "")).startswith(url + "#school-reference-")
    ]
    if other_school_lists:
        audit.error("school_itemlist_legacy", location, f"count={len(other_school_lists)}")
    expected_list_levels = [level for level in expected_levels if row.levels[level].state == "provided"]
    if set(school_lists) != set(expected_list_levels):
        audit.error("school_itemlist_levels", location, f"actual={sorted(school_lists)}, expected={expected_list_levels}")
    for level in expected_list_levels:
        item_list = school_lists.get(level)
        if not item_list:
            continue
        elements = item_list.get("itemListElement", [])
        names: list[str] = []
        positions: list[Any] = []
        for element in elements if isinstance(elements, list) else []:
            if isinstance(element, dict):
                names.append(norm(element.get("name")))
                positions.append(element.get("position"))
        expected_names = list(row.levels[level].schools)
        if names != expected_names or positions != list(range(1, len(expected_names) + 1)):
            audit.error("school_itemlist_items", location, f"level={level}, names={names}, positions={positions}, expected={expected_names}")
        if item_list.get("numberOfItems") != len(expected_names):
            audit.error("school_itemlist_count", location, f"level={level}, numberOfItems={item_list.get('numberOfItems')}")
        if norm(item_list.get("name")) != level_headings.get(level, ""):
            audit.error("school_itemlist_name", location, f"level={level}, schema={item_list.get('name')!r}, visible={level_headings.get(level)!r}")
        if not POSITIVE_SCHOOL_CUE.search(norm(item_list.get("description"))):
            audit.error("school_itemlist_description", location, f"level={level}, description={item_list.get('description')!r}")
        expected_property = {"@type": "PropertyValue", "name": "schoolLevel", "value": level}
        if item_list.get("additionalProperty") != expected_property:
            audit.error("school_itemlist_property", location, f"level={level}, actual={item_list.get('additionalProperty')!r}")
        for index, element in enumerate(elements if isinstance(elements, list) else [], start=1):
            expected_shape = {"@type": "ListItem", "position": index, "name": expected_names[index - 1]} if index <= len(expected_names) else None
            if expected_shape is None or element != expected_shape:
                audit.error("school_itemlist_shape", location, f"level={level}, position={index}, item={element!r}")


def audit_diversity(metrics: ManuscriptMetrics, rows: Sequence[SourceRow], audit: Audit) -> None:
    path_to_row = {row.slug: row for row in rows}

    def examine(label: str, values: Sequence[tuple[str, str, str]], limit: int) -> None:
        normalized_by_page: dict[str, list[str]] = defaultdict(list)
        for location, category, text in values:
            slug = Path(location).parent.name
            row = path_to_row[slug]
            # Authored copy is independently forbidden from referencing any
            # non-source school.  Masking only this page's authoritative names
            # is therefore semantically exact and avoids millions of redundant
            # global string scans during the 2,968-page release audit.
            page_schools = sorted(
                {school for source in row.levels.values() for school in source.schools},
                key=len,
                reverse=True,
            )
            value = diversity_norm(text, category, row, page_schools)
            if value:
                normalized_by_page[location].append(value)
        within = {
            path: [value for value, count in Counter(items).items() if count > 1]
            for path, items in normalized_by_page.items()
            if any(count > 1 for count in Counter(items).values())
        }
        if within:
            for path, duplicates in list(within.items())[:20]:
                audit.error(f"{label}_duplicate_within", path, repr(duplicates[:3]))
        documents: Counter[str] = Counter()
        for items in normalized_by_page.values():
            documents.update(set(items))
        max_df = max(documents.values(), default=0)
        if max_df > limit:
            top = [(value, count) for value, count in documents.most_common(10) if count > limit]
            audit.error(f"{label}_cross_df", "all-details", f"max_df={max_df}, limit={limit}, top={top}")
        audit.observations[f"{label}_diversity"] = {
            "occurrences": sum(len(items) for items in normalized_by_page.values()),
            "unique_normalized": len(documents),
            "max_df": max_df,
            "limit": limit,
            "within_duplicate_pages": len(within),
        }

    examine("paragraph", metrics.paragraphs, MAX_PARAGRAPH_DF)
    examine("sentence", metrics.sentences, MAX_SENTENCE_DF)
    examine("h2", metrics.h2s, MAX_H2_DF)


def sitemap_rows(source: str, audit: Audit, location: str) -> list[dict[str, str]]:
    try:
        root = ET.fromstring(source)
    except ET.ParseError as exc:
        audit.error("sitemap_parse", location, str(exc))
        return []
    namespace = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    result: list[dict[str, str]] = []
    for node in root.findall("sm:url", namespace):
        row: dict[str, str] = {}
        for key in ("loc", "lastmod", "changefreq", "priority"):
            child = node.find(f"sm:{key}", namespace)
            row[key] = norm(child.text) if child is not None else ""
        result.append(row)
    return result


def audit_sitemap(before: str, final: str, target_urls: set[str], audit: Audit) -> None:
    old = sitemap_rows(before, audit, "sitemap:before")
    new = sitemap_rows(final, audit, "sitemap:final")
    if [row["loc"] for row in old] != [row["loc"] for row in new]:
        audit.error("sitemap_url_order", SITEMAP, "URL set/order changed")
        return
    if len(new) != EXPECTED_SITEMAP_URLS:
        audit.error("sitemap_count", SITEMAP, f"actual={len(new)}, expected={EXPECTED_SITEMAP_URLS}")
    seen = Counter(row["loc"] for row in new)
    if any(count != 1 for count in seen.values()):
        audit.error("sitemap_duplicates", SITEMAP, f"duplicate URLs={sum(count-1 for count in seen.values() if count>1)}")
    if not target_urls.issubset(seen):
        audit.error("sitemap_target_missing", SITEMAP, f"missing={len(target_urls-set(seen))}")
    for old_row, new_row in zip(old, new):
        url = new_row["loc"]
        if url in target_urls:
            if new_row["lastmod"] != MODIFIED_DATE:
                audit.error("sitemap_target_lastmod", SITEMAP, f"{url}: {new_row['lastmod']}")
            for key in ("loc", "changefreq", "priority"):
                if old_row[key] != new_row[key]:
                    audit.error("sitemap_target_contract", SITEMAP, f"{url}: {key} changed")
        elif old_row != new_row:
            audit.error("sitemap_nontarget_changed", SITEMAP, f"{url}: {old_row} -> {new_row}")
    audit.observations["sitemap"] = {"urls": len(new), "target_urls": len(target_urls), "target_lastmod": MODIFIED_DATE}


def manifest_of_sources(values: Mapping[str, str]) -> str:
    digest = hashlib.sha256()
    for path in sorted(values):
        raw_path = path.encode("utf-8")
        raw_value = values[path].encode("utf-8")
        digest.update(len(raw_path).to_bytes(8, "big"))
        digest.update(raw_path)
        digest.update(len(raw_value).to_bytes(8, "big"))
        digest.update(raw_value)
    return digest.hexdigest()


def mapping_manifest_sha(value: Any) -> str | None:
    if not isinstance(value, Mapping):
        return None
    payload = json.dumps(
        {str(key): str(item) for key, item in value.items()},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return sha256_bytes(payload)


def run(root: Path, common: Path, projection_script: Path | None) -> Audit:
    global ROOT
    ROOT = root.resolve()
    audit = Audit()
    pre_manifest = repository_manifest(root)
    rows, source_sha = load_source(common, audit)
    targets = expected_paths(root, rows)
    if len(targets) != EXPECTED_DETAILS:
        audit.error("target_count", root, f"targets={len(targets)}, expected={EXPECTED_DETAILS}")
    discovered = {
        path.relative_to(root).as_posix()
        for category in CATEGORY_LEVELS
        for path in (root / "과목별학원" / category).glob("*/index.html")
    }
    if discovered != set(targets):
        audit.error(
            "target_scope",
            root,
            f"missing={len(set(targets)-discovered)}, extra={len(discovered-set(targets))}",
        )
    missing_paths = [rel for rel in targets if not (root / rel).is_file()]
    if missing_paths:
        audit.error("target_missing", root, f"count={len(missing_paths)}, sample={missing_paths[:5]}")
    if not (root / SITEMAP).is_file():
        audit.error("sitemap_missing", root / SITEMAP, "missing")
    if missing_paths or not (root / SITEMAP).is_file():
        return audit
    before, final, _ = projected_sources(root, common, projection_script, targets, source_sha, audit)
    expected_scope = set(targets) | {SITEMAP}
    if set(final) != expected_scope:
        # In a broken projection, retain only safely available expected entries.
        final = {key: final.get(key, before[key]) for key in expected_scope}
    all_school_names = {school for row in rows for source in row.levels.values() for school in source.schools}
    metrics = ManuscriptMetrics()
    for rel, (category, row) in targets.items():
        audit_manuscript_page(rel, category, row, before[rel], final[rel], all_school_names, metrics, audit)
    if metrics.group_states != Counter({"provided": EXPECTED_PROVIDED_GROUPS, "coverage": EXPECTED_COVERAGE_GROUPS, "missing": EXPECTED_MISSING_GROUPS}):
        audit.error("school_group_totals", "all-details", f"actual={dict(metrics.group_states)}")
    if metrics.school_occurrences != EXPECTED_NAMED_OCCURRENCES:
        audit.error("school_occurrence_total", "all-details", f"actual={metrics.school_occurrences}, expected={EXPECTED_NAMED_OCCURRENCES}")
    if metrics.changwon_corrections != 15:
        audit.error("changwon_correction_scope", "all-details", f"actual={metrics.changwon_corrections}, expected=15")
    audit_diversity(metrics, rows, audit)
    audit.observations["naturality"] = {
        "heading_semantic_collisions": metrics.heading_semantic_collisions,
        "heading_collision_samples": metrics.heading_collision_samples,
        "heading_subject_collisions": metrics.heading_subject_collisions,
        "heading_subject_collision_samples": metrics.heading_subject_collision_samples,
        "sentence_semantic_repeats": metrics.sentence_semantic_repeats,
        "sentence_repeat_pages": len(metrics.sentence_repeat_pages),
        "sentence_repeat_families": dict(metrics.sentence_repeat_families.most_common()),
        "sentence_repeat_samples": metrics.sentence_repeat_samples,
        "coverage_named_list_claims": metrics.coverage_named_list_claims,
        "coverage_named_list_samples": metrics.coverage_named_list_samples,
        "authored_ending_repeat_pages": metrics.authored_ending_repeat_pages,
        "authored_final_clause_repeats": metrics.authored_final_clause_repeats,
        "authored_suffix_repeats": dict(metrics.authored_suffix_repeats),
        "authored_ending_family_repeats": dict(metrics.authored_ending_family_repeats),
        "authored_ending_repeat_samples": metrics.authored_ending_repeat_samples,
        "compatible_ending_families": dict(metrics.compatible_ending_families),
        "incompatible_ending_sentences": metrics.incompatible_ending_sentences,
        "incompatible_ending_samples": metrics.incompatible_ending_samples,
        "guidance_context_occurrences": metrics.guidance_context_occurrences,
        "guidance_context_duplicate_pages": metrics.guidance_context_duplicate_pages,
        "guidance_context_cardinality_pages": metrics.guidance_context_cardinality_pages,
        "guidance_context_samples": metrics.guidance_context_samples,
        "state_stem_repeat_pages": metrics.state_stem_repeat_pages,
        "state_stem_boundary_pages": metrics.state_stem_boundary_pages,
        "guidance_lead_repeat_pages": metrics.guidance_lead_repeat_pages,
        "guidance_context_ownership_pages": metrics.guidance_context_ownership_pages,
        "ownership_samples": metrics.ownership_samples,
    }
    target_urls = {expected_url(category, row.slug) for category, row in targets.values()}
    audit_sitemap(before[SITEMAP], final[SITEMAP], target_urls, audit)

    post_manifest = repository_manifest(root)
    post_source_sha = sha256_file(common / SOURCE_NAME)
    if pre_manifest != post_manifest:
        changed = sorted(set(pre_manifest) ^ set(post_manifest) | {key for key in set(pre_manifest) & set(post_manifest) if pre_manifest[key] != post_manifest[key]})
        audit.error("repository_write", root, f"manifest changed: {changed[:20]}")
    if post_source_sha != source_sha:
        audit.error("source_write", common / SOURCE_NAME, f"before={source_sha}, after={post_source_sha}")
    audit.observations.update(
        {
            "mode": "projected" if projection_script else "materialized",
            "details": len(targets),
            "groups": dict(metrics.group_states),
            "named_school_occurrences": metrics.school_occurrences,
            "input_target_manifest": manifest_of_sources(before),
            "final_target_manifest": manifest_of_sources(final),
            "repository_manifest_sha256": sha256_bytes(json.dumps(pre_manifest, sort_keys=True).encode()),
            "repository_files": len(pre_manifest),
            "pre_post_repository_equal": pre_manifest == post_manifest,
            "pre_post_source_equal": source_sha == post_source_sha,
        }
    )
    return audit


def self_test() -> None:
    assert split_school_source("창원중앙여고, 남고") == ("창원중앙여고", "남고")
    assert split_school_source("나곡중/보라중/상갈중") == ("나곡중", "보라중", "상갈중")
    assert split_school_source("쌍용초.미라초.") == ("쌍용초", "미라초")
    assert split_school_source("서현중, 경덕중, 서현중") == ("서현중", "경덕중")
    assert split_school_source(GENERIC_HIGH) == ()
    assert source_state("") == "missing"
    assert source_state(GENERIC_HIGH) == "coverage"
    assert source_state("명일고") == "provided"
    collision = heading_semantic_collision(
        "노형동 고등수학학원 실제 수업 가능 학교와 상담 기준: 학생 일정 대조부터 학생 일정 비교까지"
    )
    assert collision and {"student", "schedule", "compare"}.issubset(collision[2])
    assert heading_semantic_collision(
        "명일동 고등수학학원 실제 수업 가능 학교와 상담 기준: 재학 학교 확인부터 최신 편성 점검까지"
    ) is None
    heading_row = SourceRow("신월동", "신월동", "신월동", "경남", "창원시", {})
    subject_collision = heading_subject_collisions(
        "신월동 영수학원 실제 수업 가능 학교와 가능 학교 확인 방법: 상담 자료 준비부터 최신 편성 확인까지",
        "영수학원",
        heading_row,
    )
    assert subject_collision and subject_collision[1] == (("focus", ("available", "school")),)
    assert heading_subject_collisions(
        "신월동 영수학원 실제 수업 가능 학교와 상담 자료 준비법: 현재 학년 대조부터 최신 편성 확인까지",
        "영수학원",
        heading_row,
    ) == (
        {
            "subject": "실제 수업 가능 학교",
            "focus": "상담 자료 준비법",
            "start": "현재 학년 대조",
            "end": "최신 편성 확인",
        },
        (),
    )
    assert COVERAGE_NAMED_LIST_CUE.search("노형동의 학교 가능 목록은 수업 문의 근거로 사용합니다.")
    assert not COVERAGE_NAMED_LIST_NEGATIVE.search("노형동의 학교 가능 목록은 수업 문의 근거로 사용합니다.")
    assert COVERAGE_NAMED_LIST_NEGATIVE.search("개별 학교명 목록이 아니라 범위 상태입니다.")
    repeats = repeated_content_families(
        "학교와 학년을 확인하고 현재 학년 편성을 다시 확인하세요."
    )
    assert repeats.get("grade") == 2 and repeats.get("check") == 2
    assert repeated_content_families("학교를 확인한 뒤 편성을 점검하세요.").get("check") == 2
    assert "available" not in repeated_content_families("가능 여부를 불가능으로 단정하지 마세요.")
    assert repeated_content_families(
        "재학 학교와 현재 학년을 적고 희망 시간을 상담에서 확인하세요."
    ) == {}
    endings = authored_ending_repeats(
        (
            "현재 조건은 별도로 확인합니다.",
            "가능 학년은 별도로 확인합니다.",
            "첫 질문 뒤 담당자 답변을 받아 적으세요.",
            "상담 항목마다 담당자 답변을 받아 적으세요.",
            "첫 상담에서 학교 학년 과목 시간을 확인하세요.",
            "다음 상담에서 학교 학년 과목 시간을 확인하세요.",
        )
    )
    assert endings["final_clauses"].get("현재 조건은 별도로 확인합니다") is None
    assert endings["families"] == {"separate-check": 2, "staff-answer-record": 2}
    assert endings["suffixes"]["6"] == {"상담에서 학교 학년 과목 시간을 확인하세요": 2}
    assert authored_ending_repeats(("학교를 적으세요.", "학년을 확인하세요."))["families"] == {}
    for family, clause in COMPATIBLE_ENDING_CLAUSES:
        assert compatible_ending_family(f"상담 준비를 마친 뒤, {clause}") == family
    for mismatch in (
        "실제 시작 시점은 받은 문구를 날짜와 나란히 보관하세요.",
        "최신 상담 답변은 응답 내용을 처음부터 다시 읽어 보세요.",
        "최종 과목 범위는 최신 설명을 끝까지 천천히 들어 보세요.",
        "현재 반 편성은 받은 문구를 날짜와 나란히 보관하세요.",
        "최종 과목 범위는 회신 내용을 빈칸에 분명하게 표시하세요.",
        "서로 다른 두 안내의 내용이 맞는지 견주어 보세요.",
    ):
        assert compatible_ending_family(mismatch) is None
    assert len(GUIDANCE_CONTEXT_PHRASES) == 23
    assert len(set(GUIDANCE_CONTEXT_PHRASES)) == len(GUIDANCE_CONTEXT_PHRASES)
    guidance_two = guidance_context_counts(
        "희망 시작 시점도 함께 메모하고 반 배정 상태는 담당자에게 직접 물어보세요. "
        "학생이 가능한 요일을 별도 표시하고 운영 안내는 받은 문구 그대로 노트에 남기세요."
    )
    assert sum(guidance_two.values()) == 2 and max(guidance_two.values()) == 1
    guidance_repeat = guidance_context_counts(
        "희망 시작 시점도 함께 메모하고 질문합니다. 희망 시작 시점도 함께 메모하고 기록합니다."
    )
    assert guidance_repeat == {"희망 시작 시점도 함께 메모하고": 2}
    assert state_stem_signature(
        "초등 학습 단계 상담에서는 재학 학교를 먼저 적고 "
        "반 배정 상태는 담당자에게 직접 물어보세요.",
        "elementary",
    ) == ("ask", "재학 학교를 먼저 적고")
    assert state_stem_signature(
        "중등 교과 단계 상담에서는 재학 학교를 먼저 적고 "
        "반 배정 상태는 담당자에게 직접 물어보세요.",
        "elementary",
    ) is None
    assert guidance_lead_signature(
        "초등 단계 기준으로 상담을 시작할 때는 재학 학교와 희망 학년을 먼저 적고 "
        "희망 시작 시점도 함께 메모하고 반 배정 상태는 담당자에게 직접 물어보세요.",
        "elementary",
    ) == (
        "ask",
        "희망 시작 시점도 함께 메모하고",
        "상담을 시작할 때는 재학 학교와 희망 학년을 먼저 적고",
    )
    assert guidance_lead_signature(
        "중등 단계 기준으로 상담을 시작할 때는 재학 학교와 희망 학년을 먼저 적고 "
        "희망 시작 시점도 함께 메모하고 반 배정 상태는 담당자에게 직접 물어보세요.",
        "elementary",
    ) is None
    assert closing_context_signature(
        "상담 내용을 정리하고, 마지막에는 학생이 가능한 요일을 별도 표시하고 "
        "운영 안내는 받은 문구 그대로 노트에 남기세요."
    ) == (
        "record",
        "학생이 가능한 요일을 별도 표시하고",
        "상담 내용을 정리하고, 마지막에는",
    )
    assert SENSITIVE_SCHOOL_TERMS.search("명일고 시험 범위는 학교 공지에서 확인합니다")
    assert SAFE_EPISTEMIC_TERMS.search("명일고 시험 범위는 학교 공지에서 확인합니다")
    assert SAFE_EPISTEMIC_TERMS.search("현재 반 편성은 최신 설명을 끝까지 들어 보세요")
    assert SENSITIVE_SCHOOL_TERMS.search("명일고 시험 범위를 반영해 수업합니다")
    assert not SAFE_EPISTEMIC_TERMS.search("명일고 시험 범위를 반영해 수업합니다")
    assert MISSING_CUE.search("공통 원자료에는 개별 학교명이 없습니다")
    assert MISSING_CUE.search("원자료에 개별 학교명이 기재되지 않았습니다")
    assert "창원중앙여고" in school_like_tokens("창원중앙여고 자료를 확인합니다")
    assert "고등학교" not in school_like_tokens("고등학교 자료를 확인합니다")
    assert known_school_references(
        "창원중앙여고와 명일고에서 확인합니다",
        {"창원중", "창원중앙여고", "명일고"},
    ) == {"창원중앙여고", "명일고"}
    empty_levels = {level: SchoolLevelSource("", "missing", ()) for level in LEVEL_COLUMN}
    changwon = SourceRow("사파동", "사파동", "사파동", "경남", "창원시", empty_levels)
    assert authorized_existing_copy("상남중·창원중입니다.", "중등수학학원", changwon) == authorized_existing_copy("상남중입니다.", "중등수학학원", changwon)
    assert authorized_existing_copy("창원중·앙여고", "영수학원", changwon) == authorized_existing_copy("창원중앙여고", "영수학원", changwon)


def report(audit: Audit) -> dict[str, Any]:
    counts = Counter(item.code for item in audit.errors)
    return {
        "ok": not audit.errors,
        "errors": len(audit.errors),
        "error_counts": dict(sorted(counts.items())),
        "samples": [item.__dict__ for item in audit.errors[:100]],
        "observations": audit.observations,
    }


def main(argv: Sequence[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--common-dir", type=Path, default=DEFAULT_COMMON)
    parser.add_argument("--projected-content-script", type=Path)
    parser.add_argument("--soft", action="store_true", help="print failures but return zero")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)
    if args.self_test:
        self_test()
    audit = run(args.root.resolve(), args.common_dir.resolve(), args.projected_content_script.resolve() if args.projected_content_script else None)
    print(json.dumps(report(audit), ensure_ascii=False, indent=2))
    return 0 if args.soft or not audit.errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
