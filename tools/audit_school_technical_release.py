from __future__ import annotations

import argparse
import hashlib
import html
import importlib.util
import inspect
import json
import os
import re
import shutil
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from collections import Counter
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Mapping, Sequence
from urllib.parse import quote, unquote, urljoin, urlsplit


sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[1]
DOMAIN = "https://xn--ru4bi8s1tac0p.kr"
HOST = "xn--ru4bi8s1tac0p.kr"
PARENT = "과목별학원"
TARGET_CATEGORIES = (
    "고등수학학원",
    "고등영어학원",
    "고등학생학원",
    "영수학원",
    "중등수학학원",
    "중등영어학원",
    "중학생학원",
    "초등학생학원",
)
CATEGORY_LEVELS = {
    "고등수학학원": ("high",),
    "고등영어학원": ("high",),
    "고등학생학원": ("high",),
    "중등수학학원": ("middle",),
    "중등영어학원": ("middle",),
    "중학생학원": ("middle",),
    "초등학생학원": ("elementary",),
    "영수학원": ("elementary", "middle", "high"),
}
LEVEL_IDS = {
    "elementary": "#school-reference-elementary",
    "middle": "#school-reference-middle",
    "high": "#school-reference-high",
}
COVERAGE_RAW = "지역내 모든 고등학교 가능"

BASELINE_COMMIT = "fdf8ddfae63652cd709784ed2781d95ef41ec39c"
BASELINE_TARGET_MANIFEST = "b72909afb27a4a9939e276d9337693bc05a05406d580299ea33450acb72f063f"
BASELINE_ASSET_MANIFEST = "6d4ae230a7a00dbcb4f44b9a7b1f55aba4a6099d2331663a7a45b2caa07b5861"
BASELINE_SITEMAP_SHA256 = "193d8c1a7e2fac4ea32b52141ccf189a0bbc20c93726adf075f85330f8595177"
BASELINE_ROBOTS_SHA256 = "85e823e81c1ecd6468c3265d701dc37a6d9f0dea5596ff142bcfa7363a138c91"
RELEASE_DATE = "2026-08-26"
DETAILS_PER_CATEGORY = 371
TARGET_HTML_COUNT = 2968
AUTHORIZED_DOCUMENT_COUNT = 2969
SITEMAP_URL_COUNT = 4743
SCHOOL_START = "<!-- school-reference:start -->"
SCHOOL_END = "<!-- school-reference:end -->"
SCHOOL_SECTION_ATTR = "data-school-reference"

# These pins are replaced exactly once after the content and fact owners declare
# their final no-edit freeze.  An unpinned release cannot pass.
APPROVED_GENERATOR_RELATIVE = "tools/add_school_manuscripts.py"
APPROVED_GENERATOR_SHA256 = "c4b5f9e25abf5d9cda2e32bc5bb1131534768eee9785869867d5548ada03a3a8"
APPROVED_SOURCE_SHA256 = "08c73da41d47ed76bdfa318ff30c238cc12ba92a73b40e0ca2feacec9610ac0f"
APPROVED_PROJECTED_DOCUMENT_MANIFEST = "8a6cedfe0ff050c8bc0a38c49f50d5441352dc25b39bb52eccf02d9b6da0e0d1"
APPROVED_FACT_AUDITOR_RELATIVE = "tools/audit_school_manuscripts_release.py"
APPROVED_FACT_AUDITOR_SHA256 = "3a42c38b1502941447908f9fa2ced2acc3030cd2d33c1e006062e506a0d95669"
APPROVED_RELEASE_RELATIVE = "tools/audit_school_technical_release.py"

KNOWN_BASELINE_DEBT_PATH = f"{PARENT}/와와학습코칭센터/광장점/index.html"
KNOWN_BASELINE_DEBT_URL = "https://wawa-center.com/wp-content/uploads/2026/06/M370.jpg"
KNOWN_BASELINE_DEBT_OCCURRENCES = 5

CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
TRAILING_RE = re.compile(r"(?m)[\t ]+$")
LD_SCRIPT_RE = re.compile(
    r"<script\b(?=[^>]*\btype=[\"']application/ld\+json[\"'])[^>]*>.*?</script\s*>",
    re.I | re.S,
)
SCHOOL_SECTION_START_RE = re.compile(
    rf"<section\b(?=[^>]*\b{re.escape(SCHOOL_SECTION_ATTR)}(?:\s*=|\s|>))[^>]*>",
    re.I,
)
DANGEROUS_FRAGMENT_RE = re.compile(
    r"<(?:script|style|iframe|object|embed|form|base|link|meta|template)\b|"
    r"\b(?:on[a-z]+|style)\s*=|"
    r"(?:href|src|action)\s*=\s*[\"']?\s*javascript:",
    re.I,
)
SECRET_PATTERNS = (
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\bBearer\s+[A-Za-z0-9._~+/-]{20,}", re.I),
)
PRUNED_DIRS = {
    ".git",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    "node_modules",
    "tmp",
}
IGNORED_SCHEMES = ("tel:", "sms:", "mailto:", "javascript:", "data:")
BROWSER_WIDTHS = (320, 390, 1440)
BROWSER_MISSING_CUE_PATTERN = r"미기재|기재되어 있지 않|확인되지 않|원자료에 없|이름이 없|적혀 있지 않|비어 있"


def sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def clean(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(value)).strip()


def strip_tags(value: str) -> str:
    return clean(re.sub(r"<[^>]*>", " ", value))


def relpath(root: Path, path: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def route_for_relative(relative: str) -> str:
    value = PurePosixPath(relative)
    if value.name != "index.html":
        raise ValueError(f"not an index page: {relative}")
    if str(value.parent) == ".":
        return "/"
    return "/" + "/".join(quote(part, safe="") for part in value.parent.parts) + "/"


def normalize_route(value: str, *, base_route: str | None = None) -> str | None:
    value = html.unescape(value.strip())
    if not value or value.startswith(("#", *IGNORED_SCHEMES)):
        return None
    if base_route is not None:
        value = urljoin(f"{DOMAIN}{base_route}", value)
    parts = urlsplit(value)
    if parts.scheme and parts.scheme not in {"http", "https"}:
        return None
    if parts.netloc and parts.netloc.lower() != HOST:
        return None
    path = unquote(parts.path or "/").replace("\\", "/")
    path = re.sub(r"/{2,}", "/", path)
    if path == "/index.html":
        path = "/"
    elif path.endswith("/index.html"):
        path = path[: -len("index.html")]
    if not path.startswith("/"):
        path = "/" + path
    if path != "/" and not path.endswith("/"):
        path += "/"
    return "/" + "/".join(quote(piece, safe="") for piece in path.strip("/").split("/")) + ("/" if path != "/" else "")


@dataclass
class Audit:
    errors: list[dict[str, Any]] = field(default_factory=list)
    observations: dict[str, Any] = field(default_factory=dict)

    def hard(self, condition: bool, code: str, detail: Any = None) -> None:
        if not condition:
            self.errors.append({"code": code, "detail": detail})

    def extend(self, code: str, values: Iterable[Any]) -> None:
        for value in values:
            self.errors.append({"code": code, "detail": value})


class PageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title: list[str] = []
        self.h1: list[list[str]] = []
        self.h2: list[list[str]] = []
        self._title = False
        self._h1_depth = 0
        self._h2_depth = 0
        self.metas: list[dict[str, str | None]] = []
        self.links: list[dict[str, str | None]] = []
        self.anchors: list[dict[str, str | None]] = []
        self.images: list[dict[str, str | None]] = []
        self.starts: list[tuple[str, dict[str, str | None]]] = []
        self.ld_scripts: list[str] = []
        self._script: list[str] | None = None
        self._script_ld = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        data = dict(attrs)
        self.starts.append((tag, data))
        if tag == "title":
            self._title = True
        if tag == "h1":
            self._h1_depth = 1
            self.h1.append([])
        elif self._h1_depth:
            self._h1_depth += 1
        if tag == "h2":
            self._h2_depth = 1
            self.h2.append([])
        elif self._h2_depth:
            self._h2_depth += 1
        if tag == "meta":
            self.metas.append(data)
        elif tag == "link":
            self.links.append(data)
        elif tag == "a":
            self.anchors.append(data)
        elif tag == "img":
            self.images.append(data)
        elif tag == "script":
            self._script = []
            self._script_ld = (data.get("type") or "").lower() == "application/ld+json"

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._title = False
        if self._h1_depth:
            self._h1_depth -= 1
        if self._h2_depth:
            self._h2_depth -= 1
        if tag == "script" and self._script is not None:
            if self._script_ld:
                self.ld_scripts.append("".join(self._script))
            self._script = None
            self._script_ld = False

    def handle_data(self, data: str) -> None:
        if self._title:
            self.title.append(data)
        if self._h1_depth and self.h1:
            self.h1[-1].append(data)
        if self._h2_depth and self.h2:
            self.h2[-1].append(data)
        if self._script is not None:
            self._script.append(data)


@dataclass
class Page:
    relative: str
    route: str
    raw: bytes
    text: str
    parser: PageParser
    schema: list[Any]

    @classmethod
    def parse(cls, relative: str, raw: bytes) -> "Page":
        text = raw.decode("utf-8")
        parser = PageParser()
        parser.feed(text)
        schema: list[Any] = []
        for index, source in enumerate(parser.ld_scripts):
            try:
                schema.append(json.loads(source))
            except Exception as exc:
                schema.append({"__invalid__": f"{index}: {type(exc).__name__}: {exc}"})
        return cls(relative, route_for_relative(relative), raw, text, parser, schema)

    def meta(self, *, name: str | None = None, prop: str | None = None) -> list[str]:
        result: list[str] = []
        for item in self.parser.metas:
            if name is not None and (item.get("name") or "").lower() != name.lower():
                continue
            if prop is not None and (item.get("property") or "").lower() != prop.lower():
                continue
            result.append(item.get("content") or "")
        return result

    def canonical(self) -> list[str]:
        return [
            item.get("href") or ""
            for item in self.parser.links
            if "canonical" in (item.get("rel") or "").lower().split()
        ]

    def title(self) -> str:
        return clean("".join(self.parser.title))

    def h1(self) -> list[str]:
        return [clean("".join(value)) for value in self.parser.h1]


def schema_nodes(values: Sequence[Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for value in values:
        if not isinstance(value, dict):
            continue
        graph = value.get("@graph")
        if isinstance(graph, list):
            result.extend(item for item in graph if isinstance(item, dict))
        elif "@type" in value:
            result.append(value)
    return result


def node_types(node: Mapping[str, Any]) -> set[str]:
    value = node.get("@type")
    if isinstance(value, str):
        return {value}
    if isinstance(value, list):
        return {item for item in value if isinstance(item, str)}
    return set()


def is_school_node(node: Mapping[str, Any]) -> bool:
    identifier = str(node.get("@id", ""))
    if (
        identifier.endswith("#schools")
        or identifier.endswith("#service-schools")
        or any(identifier.endswith(value) for value in LEVEL_IDS.values())
    ):
        return True
    return identifier.endswith("#school-reference") and "WebPageElement" in node_types(node)


def is_school_mention(value: Any) -> bool:
    return (
        isinstance(value, dict)
        and (
            (
                "EducationalOrganization" in node_types(value)
                and not value.get("@id")
                and isinstance(value.get("name"), str)
            )
            or value.get("name") == COVERAGE_RAW
        )
    )


def sanitize_schema(value: Any) -> Any:
    if isinstance(value, list):
        return [sanitize_schema(item) for item in value if not (isinstance(item, dict) and is_school_node(item))]
    if not isinstance(value, dict):
        return value
    if is_school_node(value):
        return None
    types = node_types(value)
    result: dict[str, Any] = {}
    for key, item in value.items():
        if types & {"Article", "WebPage"} and key == "mentions":
            source = item if isinstance(item, list) else [item]
            kept = [part for part in source if not is_school_mention(part)]
            result[key] = sanitize_schema(kept)
            continue
        if types & {"Article", "WebPage"} and key in {"hasPart", "articleSection", "dateModified"}:
            continue
        if "Service" in types and key == "mentions":
            source = item if isinstance(item, list) else [item]
            kept = [part for part in source if not is_school_mention(part)]
            result[key] = sanitize_schema(kept)
            continue
        result[key] = sanitize_schema(item)
    if isinstance(result.get("@graph"), list):
        result["@graph"] = [item for item in result["@graph"] if item is not None]
    return result


def schema_index(page: Page) -> dict[tuple[str, tuple[str, ...]], dict[str, Any]]:
    result: dict[tuple[str, tuple[str, ...]], dict[str, Any]] = {}
    for index, node in enumerate(schema_nodes(page.schema)):
        identifier = str(node.get("@id", f"__index_{index}"))
        result[(identifier, tuple(sorted(node_types(node))))] = node
    return result


def masked_head(text: str) -> str:
    match = re.search(r"<head\b[^>]*>(.*?)</head\s*>", text, re.I | re.S)
    if not match:
        return ""
    def preserve_tag(source: re.Match[str]) -> str:
        value = source.group(0)
        opening_end = value.find(">") + 1
        closing_start = value.lower().rfind("</script")
        if opening_end <= 0 or closing_start < opening_end:
            return value
        return value[:opening_end] + "__JSON_LD__" + value[closing_start:]

    return LD_SCRIPT_RE.sub(preserve_tag, match.group(0))


def body_text(text: str) -> str:
    match = re.search(r"<body\b[^>]*>.*?</body\s*>", text, re.I | re.S)
    return match.group(0) if match else ""


def school_fragment(text: str) -> tuple[str | None, list[str]]:
    errors: list[str] = []
    if text.count(SCHOOL_START) != 1:
        errors.append(f"start marker count={text.count(SCHOOL_START)}")
    if text.count(SCHOOL_END) != 1:
        errors.append(f"end marker count={text.count(SCHOOL_END)}")
    if errors:
        return None, errors
    start = text.index(SCHOOL_START)
    end = text.index(SCHOOL_END, start) + len(SCHOOL_END)
    value = text[start:end]
    if len(SCHOOL_SECTION_START_RE.findall(value)) != 1:
        errors.append(f"section[{SCHOOL_SECTION_ATTR}] count={len(SCHOOL_SECTION_START_RE.findall(value))}")
    return value, errors


def remove_school_fragment(final_body: str, baseline_body: str) -> tuple[bool, str]:
    if final_body.count(SCHOOL_START) != 1 or final_body.count(SCHOOL_END) != 1:
        return False, final_body
    start = final_body.index(SCHOOL_START)
    end = final_body.index(SCHOOL_END, start) + len(SCHOOL_END)
    starts = {start}
    ends = {end}
    for separator in ("\n", "\r\n"):
        if final_body[max(0, start - len(separator)):start] == separator:
            starts.add(start - len(separator))
        if final_body[end:end + len(separator)] == separator:
            ends.add(end + len(separator))
    for left in sorted(starts):
        for right in sorted(ends):
            candidate = final_body[:left] + final_body[right:]
            if candidate == baseline_body:
                return True, candidate
    return False, final_body[:start] + final_body[end:]


def target_relatives(root: Path) -> list[str]:
    result: list[str] = []
    for category in TARGET_CATEGORIES:
        directory = root / PARENT / category
        result.extend(relpath(root, path) for path in sorted(directory.glob("*/index.html")))
    return sorted(result)


def expected_document_paths(root: Path) -> set[str]:
    return {*target_relatives(root), "sitemap.xml"}


def git_blobs(root: Path, commit: str, relatives: Sequence[str]) -> dict[str, bytes]:
    process = subprocess.Popen(
        ["git", "cat-file", "--batch"],
        cwd=root,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert process.stdin is not None and process.stdout is not None
    result: dict[str, bytes] = {}
    try:
        for relative in relatives:
            process.stdin.write(f"{commit}:{relative}\n".encode("utf-8"))
            process.stdin.flush()
            header = process.stdout.readline().decode("utf-8", "replace").rstrip("\n")
            if header.endswith(" missing"):
                raise RuntimeError(f"missing baseline blob: {relative}")
            fields = header.split()
            if len(fields) != 3 or fields[1] != "blob":
                raise RuntimeError(f"bad cat-file header for {relative}: {header}")
            size = int(fields[2])
            value = process.stdout.read(size)
            newline = process.stdout.read(1)
            if len(value) != size or newline != b"\n":
                raise RuntimeError(f"short cat-file read for {relative}")
            result[relative] = value
    finally:
        if process.stdin:
            process.stdin.close()
        process.wait(timeout=30)
    if process.returncode:
        stderr = process.stderr.read().decode("utf-8", "replace") if process.stderr else ""
        raise RuntimeError(f"git cat-file failed: {stderr}")
    return result


def iter_repo_files(root: Path) -> Iterable[Path]:
    for directory, names, files in os.walk(root, topdown=True):
        names[:] = sorted(name for name in names if name not in PRUNED_DIRS and not name.startswith(".school-reference-"))
        base = Path(directory)
        for name in sorted(files):
            if name in {".school-reference.lock", ".school-reference-transaction.json"}:
                continue
            yield base / name


def tree_snapshot(root: Path) -> tuple[str, dict[str, str]]:
    items: dict[str, str] = {}
    digest = hashlib.sha256()
    for path in sorted(iter_repo_files(root), key=lambda value: value.as_posix()):
        relative = relpath(root, path)
        value = sha256(path.read_bytes())
        items[relative] = value
        digest.update(relative.encode("utf-8") + b"\0" + value.encode("ascii") + b"\n")
    return digest.hexdigest(), items


def git_status_bytes(root: Path) -> bytes:
    result = subprocess.run(
        ["git", "-c", "core.quotePath=false", "status", "--porcelain=v1", "-z", "--untracked-files=all"],
        cwd=root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    return result.stdout if result.returncode == 0 else b"ERROR:" + result.stderr


def parse_porcelain_v1_z(raw: bytes) -> tuple[set[str], list[str]]:
    paths: set[str] = set()
    statuses: list[str] = []
    fields = raw.split(b"\0")
    index = 0
    while index < len(fields):
        record = fields[index]
        index += 1
        if not record:
            continue
        if len(record) < 4 or record[2:3] != b" ":
            raise ValueError(f"invalid porcelain v1 -z record: {record[:80]!r}")
        status = record[:2].decode("ascii", "strict")
        path = record[3:].decode("utf-8", "strict").replace("\\", "/")
        statuses.append(status)
        paths.add(path)
        if "R" in status or "C" in status:
            if index >= len(fields) or not fields[index]:
                raise ValueError(f"missing source path for porcelain status {status!r}")
            paths.add(fields[index].decode("utf-8", "strict").replace("\\", "/"))
            index += 1
    return paths, statuses


def git_status(root: Path) -> str:
    return git_status_bytes(root).decode("utf-8", "replace")


def manifest(values: Mapping[str, bytes]) -> str:
    digest = hashlib.sha256()
    for relative in sorted(values):
        value = values[relative]
        digest.update(relative.encode("utf-8") + b"\0" + str(len(value)).encode("ascii") + b"\0" + bytes.fromhex(sha256(value)) + b"\n")
    return digest.hexdigest()


def load_module(path: Path) -> Any:
    name = f"school_release_projection_{time.time_ns()}"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    sys.path.insert(0, str(path.parent))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.remove(str(path.parent))
    return module


def normalize_authorized_documents(root: Path, plan: Any) -> tuple[dict[str, bytes], list[str]]:
    source = getattr(plan, "authorized_documents", None)
    if not isinstance(source, dict):
        return {}, ["BuildPlan.authorized_documents is not dict"]
    result: dict[str, bytes] = {}
    errors: list[str] = []
    for key, value in source.items():
        if not isinstance(key, (str, Path)):
            errors.append(f"non-path document key: {key!r}")
            continue
        path = Path(key)
        try:
            relative = relpath(root, path if path.is_absolute() else root / path)
        except Exception:
            errors.append(f"document outside root: {key!r}")
            continue
        if relative in result:
            errors.append(f"duplicate document path: {relative}")
            continue
        if isinstance(value, str):
            raw = value.encode("utf-8")
        elif isinstance(value, bytes):
            raw = value
        else:
            errors.append(f"document value is not str/bytes: {relative}")
            continue
        result[relative] = raw
    return result, errors


def normalize_declared_paths(root: Path, values: Iterable[Any]) -> tuple[set[str], list[str]]:
    result: set[str] = set()
    errors: list[str] = []
    for value in values:
        if not isinstance(value, (str, Path)):
            errors.append(f"non-path declared value: {value!r}")
            continue
        path = Path(value)
        try:
            relative = relpath(root, path if path.is_absolute() else root / path)
        except Exception:
            errors.append(f"declared path outside root: {value!r}")
            continue
        if relative in result:
            errors.append(f"duplicate declared path: {relative}")
        result.add(relative)
    return result, errors


def discover_common_dir(root: Path, supplied: Path | None) -> Path:
    candidates = [
        supplied,
        root.parent / "참고자료" / "공통자료",
        root.parent.parent / "참고자료" / "공통자료",
    ]
    for value in candidates:
        if value is not None and value.is_dir():
            return value.resolve()
    raise RuntimeError("common_dir not found; pass --common-dir")


@dataclass
class Projection:
    documents: dict[str, bytes]
    changed_paths: set[str]
    source_sha256: str
    before_manifest: str
    after_manifest: str
    second_pass_changes: int
    generator_sha256: str


def validate_plan_manifest(value: Any, expected_paths: set[str], code: str, audit: Audit) -> tuple[dict[str, str], str]:
    if not isinstance(value, dict):
        audit.hard(False, code, f"expected dict, got {type(value).__name__}")
        return {}, ""
    normalized = {str(key).replace("\\", "/"): str(digest) for key, digest in value.items()}
    audit.hard(set(normalized) == expected_paths, code + "_paths", {"missing": sorted(expected_paths - set(normalized))[:10], "extra": sorted(set(normalized) - expected_paths)[:10]})
    bad = {key: digest for key, digest in normalized.items() if not re.fullmatch(r"[0-9a-f]{64}", digest)}
    audit.hard(not bad, code + "_hashes", list(bad.items())[:10])
    digest = sha256("\n".join(f"{key}\0{normalized[key]}" for key in sorted(normalized)).encode("utf-8")) if normalized else ""
    return normalized, digest


def run_projection(root: Path, generator: Path, common_dir: Path, audit: Audit) -> Projection | None:
    relative = relpath(root, generator)
    digest = sha256(generator.read_bytes())
    audit.hard(
        relative == APPROVED_GENERATOR_RELATIVE and digest == APPROVED_GENERATOR_SHA256,
        "approved_generator_pin",
        {"expected_path": APPROVED_GENERATOR_RELATIVE, "actual_path": relative, "expected_sha256": APPROVED_GENERATOR_SHA256, "actual_sha256": digest},
    )
    if relative != APPROVED_GENERATOR_RELATIVE or digest != APPROVED_GENERATOR_SHA256:
        return None
    repo_before = tree_snapshot(root)
    common_before = tree_snapshot(common_dir)
    status_before = git_status(root)
    try:
        module = load_module(generator)
        build_plan = getattr(module, "build_plan", None)
        audit.hard(callable(build_plan), "projection_api", "missing callable build_plan")
        if not callable(build_plan):
            return None
        signature = inspect.signature(build_plan)
        required = {"root", "common_dir", "current_overrides"}
        audit.hard(required <= set(signature.parameters), "projection_signature", str(signature))
        if not required <= set(signature.parameters):
            return None
        plan = build_plan(root=root, common_dir=common_dir, current_overrides=None)
        documents, errors = normalize_authorized_documents(root, plan)
        audit.extend("projection_document_contract", errors)
        expected = expected_document_paths(root)
        audit.hard(len(documents) == AUTHORIZED_DOCUMENT_COUNT, "projection_document_count", {"expected": AUTHORIZED_DOCUMENT_COUNT, "actual": len(documents)})
        audit.hard(set(documents) == expected, "projection_scope", {"missing": sorted(expected - set(documents))[:10], "extra": sorted(set(documents) - expected)[:10]})
        document_manifest = manifest(documents)
        audit.hard(APPROVED_PROJECTED_DOCUMENT_MANIFEST != "PENDING" and document_manifest == APPROVED_PROJECTED_DOCUMENT_MANIFEST, "approved_projected_manifest", {"expected": APPROVED_PROJECTED_DOCUMENT_MANIFEST, "actual": document_manifest})
        diagnostics_value = getattr(plan, "diagnostics", None)
        audit.hard(isinstance(diagnostics_value, dict), "projection_diagnostics_type", type(diagnostics_value).__name__)
        diagnostic_errors = diagnostics_value.get("errors", ()) if isinstance(diagnostics_value, dict) else ("invalid diagnostics",)
        diagnostic_detail = list(diagnostic_errors)[:20] if isinstance(diagnostic_errors, (list, tuple, set)) else diagnostic_errors
        audit.hard(not diagnostic_errors, "projection_diagnostics_errors", diagnostic_detail)
        declared_changed, declared_errors = normalize_declared_paths(root, getattr(plan, "changed_paths", ()) or ())
        audit.extend("projection_declared_changed_contract", declared_errors)
        actual_changed = {relative for relative, value in documents.items() if not (root / relative).exists() or (root / relative).read_bytes() != value}
        audit.hard(declared_changed == actual_changed, "projection_changed_paths", {"declared_only": sorted(declared_changed - actual_changed)[:10], "actual_only": sorted(actual_changed - declared_changed)[:10]})
        audit.hard(len(actual_changed) in {0, AUTHORIZED_DOCUMENT_COUNT}, "projection_partial_materialization", {"expected": [0, AUTHORIZED_DOCUMENT_COUNT], "actual": len(actual_changed)})

        repeat = build_plan(root=root, common_dir=common_dir, current_overrides=None)
        repeated, repeat_errors = normalize_authorized_documents(root, repeat)
        audit.extend("projection_repeat_contract", repeat_errors)
        audit.hard(repeated == documents, "projection_deterministic", {"first": manifest(documents), "second": manifest(repeated)})

        overrides = {relative: value.decode("utf-8") for relative, value in documents.items()}
        second = build_plan(root=root, common_dir=common_dir, current_overrides=overrides)
        second_documents, second_errors = normalize_authorized_documents(root, second)
        audit.extend("projection_second_contract", second_errors)
        audit.hard(second_documents == documents, "projection_second_pass_bytes", {"first": manifest(documents), "second": manifest(second_documents)})
        second_before_values, _ = validate_plan_manifest(getattr(second, "before_manifest", None), expected, "projection_second_before_manifest", audit)
        second_after_values, _ = validate_plan_manifest(getattr(second, "after_manifest", None), expected, "projection_second_after_manifest", audit)
        expected_final_hashes = {relative: sha256(value) for relative, value in documents.items()}
        audit.hard(second_before_values == expected_final_hashes, "projection_second_before_values", "second pass did not consume first-pass output")
        audit.hard(second_after_values == expected_final_hashes, "projection_second_after_values", "second pass changed final bytes")
        second_changed, second_path_errors = normalize_declared_paths(root, getattr(second, "changed_paths", ()) or ())
        audit.extend("projection_second_changed_contract", second_path_errors)
        audit.hard(not second_changed, "projection_second_changed_paths", sorted(second_changed)[:20])
        first_second_count = int(getattr(plan, "second_pass_changes", 0) or 0)
        audit.hard(first_second_count == 0, "projection_declared_second_pass_changes", first_second_count)
        declared_second_count = int(getattr(second, "second_pass_changes", 0) or 0)
        audit.hard(declared_second_count == 0, "projection_second_pass_changes", declared_second_count)

        source_sha = str(getattr(plan, "source_sha256", ""))
        before_values, before_manifest = validate_plan_manifest(getattr(plan, "before_manifest", None), expected, "projection_before_manifest", audit)
        after_values, after_manifest = validate_plan_manifest(getattr(plan, "after_manifest", None), expected, "projection_after_manifest", audit)
        audit.hard(bool(re.fullmatch(r"[0-9a-f]{64}", source_sha)), "projection_source_sha256", source_sha)
        audit.hard(APPROVED_SOURCE_SHA256 != "PENDING" and source_sha == APPROVED_SOURCE_SHA256, "approved_source_pin", {"expected": APPROVED_SOURCE_SHA256, "actual": source_sha})
        actual_before = {relative: sha256((root / relative).read_bytes()) for relative in expected}
        actual_after = {relative: sha256(value) for relative, value in documents.items()}
        audit.hard(before_values == actual_before, "projection_before_manifest_values", {"declared": before_manifest, "actual": sha256("\n".join(f"{key}\0{actual_before[key]}" for key in sorted(actual_before)).encode())})
        audit.hard(after_values == actual_after, "projection_after_manifest_values", {"declared": after_manifest, "actual": sha256("\n".join(f"{key}\0{actual_after[key]}" for key in sorted(actual_after)).encode())})
        projection = Projection(documents, actual_changed, source_sha, before_manifest, after_manifest, declared_second_count, digest)
        audit.observations["projection"] = {
            "documents": len(documents),
            "changed": len(actual_changed),
            "manifest": document_manifest,
            "source_sha256": source_sha,
            "before_manifest": before_manifest,
            "after_manifest": after_manifest,
            "second_pass_changes": declared_second_count,
        }
        return projection
    finally:
        repo_after = tree_snapshot(root)
        common_after = tree_snapshot(common_dir)
        status_after = git_status(root)
        audit.hard(repo_before == repo_after, "projection_repo_freeze", {"before": repo_before[0], "after": repo_after[0]})
        audit.hard(common_before == common_after, "projection_common_freeze", {"before": common_before[0], "after": common_after[0]})
        audit.hard(status_before == status_after, "projection_git_freeze", {"before": status_before, "after": status_after})
        audit.observations["freeze"] = {"repo_before": repo_before[0], "repo_after": repo_after[0], "common_before": common_before[0], "common_after": common_after[0]}


def alias_allowlist_kind(relative: str) -> str | None:
    parts = PurePosixPath(relative).parts
    if len(parts) != 4 or parts[0] != PARENT or parts[3] != "index.html":
        return None
    category, locality = parts[1], parts[2]
    if locality not in {"상남동", "신월동", "사파동"}:
        return None
    if category in {"고등수학학원", "고등영어학원"}:
        return "high"
    if category in {"중등수학학원", "중등영어학원"}:
        return "middle"
    if category == "영수학원":
        return "combined"
    return None


def apply_alias_body_fix(relative: str, baseline_body: str) -> str:
    kind = alias_allowlist_kind(relative)
    if kind == "high":
        return re.sub(r"(?<!창원중)앙여고", "창원중앙여고", baseline_body)
    if kind == "middle":
        return baseline_body.replace("·창원중", "").replace("창원중·", "").replace("<span>창원중</span>", "")
    if kind == "combined":
        return (
            baseline_body
            .replace("<span>창원중</span><span>앙여고</span>", "<span>창원중앙여고</span>")
            .replace("창원중·앙여고", "창원중앙여고")
        )
    return baseline_body


def canonical_alias_value(relative: str, value: Any) -> Any:
    kind = alias_allowlist_kind(relative)
    if isinstance(value, str):
        if kind == "high":
            return re.sub(r"(?<!창원중)앙여고", "창원중앙여고", value)
        if kind == "middle":
            return value.replace("·창원중", "").replace("창원중·", "")
        if kind == "combined":
            return value.replace("창원중·앙여고", "창원중앙여고")
        return value
    if isinstance(value, dict):
        return {key: canonical_alias_value(relative, item) for key, item in value.items()}
    if not isinstance(value, list):
        return value
    source = list(value)
    output: list[Any] = []
    index = 0
    while index < len(source):
        item = source[index]
        name = item.get("name") if isinstance(item, dict) else None
        item_types = node_types(item) if isinstance(item, dict) else set()
        is_school_org = isinstance(item, dict) and "EducationalOrganization" in item_types and not item.get("@id") and isinstance(name, str)
        if kind == "middle" and name == "창원중" and (is_school_org or "ListItem" in item_types):
            index += 1
            continue
        if kind == "combined" and name == "창원중" and index + 1 < len(source):
            next_item = source[index + 1]
            next_name = next_item.get("name") if isinstance(next_item, dict) else None
            if next_name == "앙여고" and isinstance(item, dict) and isinstance(next_item, dict):
                merged = json.loads(json.dumps(item, ensure_ascii=False))
                merged["name"] = "창원중앙여고"
                if isinstance(merged.get("item"), dict):
                    merged["item"]["name"] = "창원중앙여고"
                output.append(canonical_alias_value(relative, merged))
                index += 2
                continue
        output.append(canonical_alias_value(relative, item))
        index += 1
    if output and all(isinstance(item, dict) and "ListItem" in node_types(item) for item in output):
        for position, item in enumerate(output, 1):
            item["position"] = position
    return output


def meta_contract(page: Page) -> dict[str, Any]:
    return {
        "title": page.title(),
        "h1": page.h1(),
        "description": page.meta(name="description"),
        "robots": page.meta(name="robots"),
        "canonical": page.canonical(),
        "og_title": page.meta(prop="og:title"),
        "og_description": page.meta(prop="og:description"),
        "og_url": page.meta(prop="og:url"),
        "og_image": page.meta(prop="og:image"),
        "hrefs": [item.get("href") or "" for item in page.parser.anchors],
        "images": [tuple(sorted((key, value or "") for key, value in item.items())) for item in page.parser.images],
        "head_non_json": masked_head(page.text),
    }


def section_status(fragment: str) -> str:
    group_states = [value.lower() for value in re.findall(r"\bdata-source-state\s*=\s*[\"']([^\"']+)[\"']", fragment, re.I)]
    if group_states:
        if "provided" in group_states:
            return "provided"
        if "coverage" in group_states:
            return "coverage"
        if all(value == "missing" for value in group_states):
            return "missing"
    start = SCHOOL_SECTION_START_RE.search(fragment)
    if not start:
        return "unknown"
    tag = start.group(0)
    matches = re.findall(r"\bdata-(?:school-)?source-status\s*=\s*[\"']([^\"']+)[\"']", tag, re.I)
    if matches:
        value = matches[0].lower()
        if any(token in value for token in ("missing", "blank", "empty", "unconfirmed")):
            return "missing"
        return "provided"
    rendered = strip_tags(fragment)
    if re.search(r"미기재|기재되어 있지 않|확인되지 않|원자료에 없", rendered):
        return "missing"
    return "provided"


def validate_page(relative: str, baseline_raw: bytes, final_raw: bytes, audit: Audit) -> dict[str, Any]:
    errors: list[str] = []
    try:
        baseline = Page.parse(relative, baseline_raw)
        final = Page.parse(relative, final_raw)
    except Exception as exc:
        audit.hard(False, "page_decode_parse", {"path": relative, "error": f"{type(exc).__name__}: {exc}"})
        return {"status": "unknown", "h2": ""}
    expected_absolute = DOMAIN + final.route
    if meta_contract(baseline) != meta_contract(final):
        base = meta_contract(baseline)
        after = meta_contract(final)
        for key in base:
            if base[key] != after[key]:
                errors.append(f"stable meta/link/image field changed: {key}")
    if final.canonical() != [expected_absolute]:
        errors.append(f"canonical expected {expected_absolute!r} got {final.canonical()!r}")
    if final.meta(prop="og:url") != [expected_absolute]:
        errors.append(f"og:url expected {expected_absolute!r} got {final.meta(prop='og:url')!r}")
    if len(final.h1()) != 1 or not final.h1()[0] or not final.title():
        errors.append(f"title/H1 cardinality title={final.title()!r} h1={final.h1()!r}")
    if any("noindex" in value.lower() for value in final.meta(name="robots")):
        errors.append("noindex introduced")
    if any("index.html" in (item.get("href") or "").lower() for item in final.parser.anchors):
        errors.append("internal index.html href remains")
    ids = [attrs.get("id") or "" for _, attrs in final.parser.starts if attrs.get("id")]
    duplicate_ids = sorted(value for value, count in Counter(ids).items() if count > 1)
    if duplicate_ids:
        errors.append(f"duplicate HTML ids={duplicate_ids[:10]}")
    if CONTROL_RE.search(final.text):
        errors.append("forbidden control character")
    if TRAILING_RE.search(final.text):
        errors.append("trailing whitespace")

    alias_kind = alias_allowlist_kind(relative)
    if alias_kind == "high":
        if baseline.text.count("앙여고") != 8 or baseline.text.count("창원중") != 0:
            errors.append("high alias baseline occurrence contract differs expected 8/0")
        if final.text.count("창원중앙여고") < 8 or re.search(r"(?<!창원중)앙여고", final.text):
            errors.append("high alias correction occurrence contract failed")
    elif alias_kind == "middle":
        if baseline.text.count("창원중") != 8 or baseline.text.count("앙여고") != 0:
            errors.append("middle alias baseline occurrence contract differs expected 8/0")
        if re.search(r"창원중(?!앙여고)", final.text):
            errors.append("middle stray 창원중 correction contract failed")
    elif alias_kind == "combined":
        if baseline.text.count("창원중") != 8 or baseline.text.count("앙여고") != 8:
            errors.append("combined alias baseline occurrence contract differs expected 8/8")
        if final.text.count("창원중앙여고") < 8 or re.search(r"창원중(?!앙여고)|(?<!창원중)앙여고", final.text):
            errors.append("combined alias merge occurrence contract failed")

    fragment, fragment_errors = school_fragment(final.text)
    errors.extend(fragment_errors)
    status = "unknown"
    h2 = ""
    group_states: list[str] = []
    if fragment is not None:
        status = section_status(fragment)
        group_states = [
            value.lower()
            for value in re.findall(r"\bdata-source-state\s*=\s*[\"']([^\"']+)[\"']", fragment, re.I)
        ]
        expected_group_count = len(CATEGORY_LEVELS[PurePosixPath(relative).parts[1]])
        if len(group_states) != expected_group_count or any(value not in {"provided", "coverage", "missing"} for value in group_states):
            errors.append(f"source group states expected={expected_group_count} actual={group_states}")
        if DANGEROUS_FRAGMENT_RE.search(fragment):
            errors.append("dangerous HTML in school fragment")
        section_open = SCHOOL_SECTION_START_RE.search(fragment)
        if section_open and (
            re.search(r"\shidden(?:\s|=|>)", section_open.group(0), re.I)
            or re.search(r"\baria-hidden\s*=\s*[\"']?true", section_open.group(0), re.I)
        ):
            errors.append("school section is explicitly hidden")
        if re.search(r"\b(?:href|src|action)\s*=", fragment, re.I):
            errors.append("school fragment introduced URL-bearing attribute")
        headings = re.findall(r"<h2\b[^>]*>(.*?)</h2\s*>", fragment, re.I | re.S)
        if len(headings) != 1:
            errors.append(f"school H2 count={len(headings)}")
        else:
            h2 = strip_tags(headings[0])

    baseline_body = apply_alias_body_fix(relative, body_text(baseline.text))
    body_ok, stripped = remove_school_fragment(body_text(final.text), baseline_body)
    if not body_ok:
        errors.append(f"body excluding school block differs baseline expected={sha256(baseline_body.encode())} actual={sha256(stripped.encode())}")

    if any(isinstance(value, dict) and "__invalid__" in value for value in final.schema):
        errors.append("invalid JSON-LD")
    base_schema = canonical_alias_value(relative, sanitize_schema(baseline.schema))
    final_schema = sanitize_schema(final.schema)
    if base_schema != final_schema:
        errors.append("schema changed outside school allowlist/dateModified")
    base_nodes = schema_index(baseline)
    final_nodes = schema_index(final)
    dated_counts: Counter[str] = Counter()
    for key, base_node in base_nodes.items():
        types = node_types(base_node)
        relevant_types = types & {"Article", "WebPage"}
        if not relevant_types:
            continue
        node = final_nodes.get(key)
        if node is None:
            errors.append(f"dated schema node disappeared: {key}")
            continue
        if ("datePublished" in node, node.get("datePublished")) != ("datePublished" in base_node, base_node.get("datePublished")):
            errors.append(f"datePublished changed: {key}")
        if "dateModified" not in node or node.get("dateModified") != RELEASE_DATE:
            errors.append(f"dateModified not raw-exact {RELEASE_DATE}: {key}")
        else:
            dated_counts.update(relevant_types)
    baseline_type_counts = Counter(
        expected_type
        for node in base_nodes.values()
        for expected_type in ("Article", "WebPage")
        if expected_type in node_types(node)
    )
    if dated_counts != baseline_type_counts or any(baseline_type_counts[value] != 1 for value in ("Article", "WebPage")):
        errors.append(f"Article/WebPage dateModified coverage differs baseline expected={dict(baseline_type_counts)} actual={dict(dated_counts)}")

    nodes = schema_nodes(final.schema)
    page_school_id = expected_absolute + "#school-reference"
    web_elements = [node for node in nodes if "WebPageElement" in node_types(node) and node.get("@id") == page_school_id]
    schema_text = json.dumps(final.schema, ensure_ascii=False, separators=(",", ":"))
    if len(web_elements) != 1:
        errors.append(f"#school-reference WebPageElement count={len(web_elements)}")
    else:
        element = web_elements[0]
        if element.get("name") != h2:
            errors.append("#school-reference WebPageElement name differs H2")
        if element.get("url") != page_school_id:
            errors.append("#school-reference WebPageElement url differs canonical fragment")
        webpages = [node for node in nodes if "WebPage" in node_types(node)]
        expected_parent_id = webpages[0].get("@id") if len(webpages) == 1 else None
        if not isinstance(element.get("isPartOf"), dict) or element["isPartOf"].get("@id") != expected_parent_id:
            errors.append("#school-reference WebPageElement isPartOf differs WebPage")
    for expected_type in ("WebPage", "Article"):
        base_typed = [node for node in schema_nodes(baseline.schema) if expected_type in node_types(node)]
        typed = [node for node in nodes if expected_type in node_types(node)]
        if len(base_typed) != 1 or len(typed) != 1:
            errors.append(f"{expected_type} node cardinality baseline/final={len(base_typed)}/{len(typed)}")
        references = 0
        for node in typed:
            has_part = node.get("hasPart", [])
            if not isinstance(has_part, list):
                has_part = [has_part]
            references += sum(isinstance(item, dict) and item.get("@id") == page_school_id for item in has_part)
        if references != 1:
            errors.append(f"{expected_type}.hasPart #school-reference count={references}")
        if len(base_typed) == 1 and len(typed) == 1:
            baseline_parts = base_typed[0].get("hasPart", [])
            if not isinstance(baseline_parts, list):
                baseline_parts = [baseline_parts] if baseline_parts else []
            expected_parts = [
                canonical_alias_value(relative, item)
                for item in baseline_parts
                if not (
                    isinstance(item, dict)
                    and isinstance(item.get("@id"), str)
                    and item["@id"].endswith("#school-reference")
                )
            ] + [{"@id": page_school_id}]
            actual_parts = typed[0].get("hasPart", [])
            if not isinstance(actual_parts, list):
                actual_parts = [actual_parts] if actual_parts else []
            if actual_parts != expected_parts:
                errors.append(f"{expected_type}.hasPart changed outside owned school reference")
            if expected_type == "Article":
                locality = PurePosixPath(relative).parts[2]
                baseline_sections = base_typed[0].get("articleSection", [])
                if not isinstance(baseline_sections, list):
                    baseline_sections = [baseline_sections] if baseline_sections else []
                expected_sections = [
                    canonical_alias_value(relative, item)
                    for item in baseline_sections
                    if not (isinstance(item, str) and locality in item and "수업 가능 학교" in item)
                ] + [h2]
                actual_sections = typed[0].get("articleSection", [])
                if actual_sections != expected_sections:
                    errors.append("Article.articleSection changed outside school heading reconciliation")
    if h2 and schema_text.count(h2) < 1:
        errors.append("school H2 absent from schema")

    allowed_level_ids = {expected_absolute + LEVEL_IDS[level] for level in CATEGORY_LEVELS[PurePosixPath(relative).parts[1]]}
    itemlists = [node for node in nodes if "ItemList" in node_types(node) and str(node.get("@id", "")).startswith(expected_absolute + "#school-reference-")]
    actual_level_ids = {str(node.get("@id")) for node in itemlists}
    if len(itemlists) != len(actual_level_ids):
        errors.append("duplicate school ItemList @id")
    if not actual_level_ids <= allowed_level_ids:
        errors.append(f"unexpected school ItemList ids={sorted(actual_level_ids - allowed_level_ids)}")
    for node in itemlists:
        elements = node.get("itemListElement")
        if not isinstance(elements, list) or not elements:
            errors.append(f"empty named school ItemList {node.get('@id')}")

    audit.extend("page_contract", ({"path": relative, "error": error} for error in errors))
    resources: list[str] = []
    for tag, attrs in final.parser.starts:
        if tag in {"img", "source", "script"}:
            if attrs.get("src"):
                resources.append(attrs["src"] or "")
            if attrs.get("srcset"):
                resources.extend(part.strip().split()[0] for part in (attrs["srcset"] or "").split(",") if part.strip())
    return {
        "status": status,
        "group_states": group_states,
        "h2": h2,
        "route": final.route,
        "relative": relative,
        "category": PurePosixPath(relative).parts[1],
        "hrefs": [item.get("href") or "" for item in final.parser.anchors],
        "resources": resources,
    }


def local_destination(root: Path, base_route: str, value: str) -> Path | None:
    value = html.unescape(value.strip())
    if not value or value.startswith(("#", *IGNORED_SCHEMES)):
        return None
    absolute = urlsplit(urljoin(DOMAIN + base_route, value))
    if absolute.netloc and absolute.netloc.lower() != HOST:
        return None
    path = unquote(absolute.path or "/")
    relative = path.lstrip("/")
    if not relative:
        return root / "index.html"
    candidate = root / relative
    if path.endswith("/"):
        candidate = candidate / "index.html"
    elif not candidate.suffix:
        candidate = candidate / "index.html"
    try:
        candidate.resolve().relative_to(root.resolve())
    except ValueError:
        return root / ".invalid-outside-root-reference"
    return candidate


def parse_sitemap(raw: bytes) -> list[dict[str, str]]:
    root = ET.fromstring(raw.decode("utf-8"))
    namespace = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
    result: list[dict[str, str]] = []
    for node in list(root):
        if node.tag != namespace + "url":
            raise ValueError(f"unexpected sitemap child {node.tag}")
        row: dict[str, str] = {}
        counts: Counter[str] = Counter()
        for child in list(node):
            key = child.tag.removeprefix(namespace)
            counts[key] += 1
            row[key] = (child.text or "").strip()
        if counts["loc"] != 1 or counts["lastmod"] != 1:
            raise ValueError(f"sitemap loc/lastmod cardinality {counts}")
        route = normalize_route(row["loc"])
        if route is None:
            raise ValueError(f"invalid sitemap loc {row['loc']!r}")
        row["route"] = route
        result.append(row)
    return result


def validate_sitemap(baseline_raw: bytes, final_raw: bytes, target_routes: set[str], audit: Audit) -> None:
    try:
        baseline = parse_sitemap(baseline_raw)
        final = parse_sitemap(final_raw)
    except Exception as exc:
        audit.hard(False, "sitemap_parse", f"{type(exc).__name__}: {exc}")
        return
    audit.hard(len(final) == SITEMAP_URL_COUNT, "sitemap_url_count", {"expected": SITEMAP_URL_COUNT, "actual": len(final)})
    baseline_routes = [row["route"] for row in baseline]
    final_routes = [row["route"] for row in final]
    audit.hard(final_routes == baseline_routes, "sitemap_url_order", {"baseline": sha256("\n".join(baseline_routes).encode()), "final": sha256("\n".join(final_routes).encode())})
    audit.hard(len(final_routes) == len(set(final_routes)), "sitemap_unique", len(final_routes) - len(set(final_routes)))
    audit.hard(target_routes <= set(final_routes), "sitemap_target_coverage", len(target_routes - set(final_routes)))
    errors: list[Any] = []
    changed_lastmod = 0
    for before, after in zip(baseline, final):
        route = before["route"]
        if route in target_routes:
            if after.get("lastmod") != RELEASE_DATE:
                errors.append({"route": route, "lastmod": after.get("lastmod")})
            if before.get("lastmod") != after.get("lastmod"):
                changed_lastmod += 1
            for key in set(before) | set(after):
                if key not in {"lastmod"} and before.get(key) != after.get(key):
                    errors.append({"route": route, "field": key, "before": before.get(key), "after": after.get(key)})
        elif before != after:
            errors.append({"route": route, "non_target_changed": True})
    audit.extend("sitemap_contract", errors)
    audit.hard(changed_lastmod == len(target_routes), "sitemap_target_lastmod_change_count", {"expected": len(target_routes), "actual": changed_lastmod})
    try:
        baseline_text = baseline_raw.decode("utf-8")
        expected_blocks: list[str] = []
        cursor = 0
        pieces: list[str] = []
        for match in re.finditer(r"<url>(.*?)</url>", baseline_text, re.S):
            pieces.append(baseline_text[cursor:match.start()])
            block = match.group(0)
            loc_match = re.search(r"<loc>(.*?)</loc>", block, re.S)
            route = normalize_route(html.unescape(loc_match.group(1)).strip()) if loc_match else None
            if route in target_routes:
                block, replacements = re.subn(r"(<lastmod>).*?(</lastmod>)", rf"\g<1>{RELEASE_DATE}\g<2>", block, count=1, flags=re.S)
                if replacements != 1:
                    raise ValueError(f"target sitemap block has no unique lastmod: {route}")
            pieces.append(block)
            cursor = match.end()
        pieces.append(baseline_text[cursor:])
        expected_raw = "".join(pieces).encode("utf-8")
        audit.hard(final_raw == expected_raw, "sitemap_only_target_lastmod_bytes", {"expected": sha256(expected_raw), "actual": sha256(final_raw)})
    except Exception as exc:
        audit.hard(False, "sitemap_exact_projection", f"{type(exc).__name__}: {exc}")
    audit.observations["sitemap"] = {"urls": len(final), "target_urls": len(target_routes), "target_lastmod_changed": changed_lastmod, "url_order_sha256": sha256("\n".join(final_routes).encode())}


def git_changed_paths(root: Path) -> tuple[set[str], list[str], str]:
    paths, statuses = parse_porcelain_v1_z(git_status_bytes(root))
    summary = subprocess.run(["git", "diff", "--summary", BASELINE_COMMIT, "--"], cwd=root, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False).stdout.decode("utf-8", "replace")
    return paths, statuses, summary


def validate_git_scope(root: Path, expected_documents: set[str], audit: Audit) -> None:
    changed, statuses, summary = git_changed_paths(root)
    allowed = {
        *expected_documents,
        APPROVED_GENERATOR_RELATIVE,
        APPROVED_FACT_AUDITOR_RELATIVE,
        APPROVED_RELEASE_RELATIVE,
    }
    audit.hard(changed <= allowed, "git_scope", {"changed": len(changed), "extra": sorted(changed - allowed)[:20]})
    audit.hard(not any(status.startswith(("D", "R", "C", "T")) for status in statuses), "git_destructive_status", statuses)
    audit.hard(not re.search(r"mode change|create mode 120000|delete mode", summary), "git_mode_or_symlink", summary)
    unsafe_paths = [relative for relative in sorted(changed) if (root / relative).exists() and (root / relative).is_symlink()]
    audit.hard(not unsafe_paths, "git_symlink_scope", unsafe_paths[:20])
    diff_check = subprocess.run(
        ["git", "diff", "--check", BASELINE_COMMIT, "--"],
        cwd=root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    audit.hard(
        diff_check.returncode == 0 and not diff_check.stdout and not diff_check.stderr,
        "git_diff_check",
        (diff_check.stdout + diff_check.stderr).decode("utf-8", "replace")[:4000],
    )
    residue = [
        relpath(root, path) for path in iter_repo_files(root)
        if (
            any(part.startswith(".school-manuscripts-txn-") for part in path.relative_to(root).parts)
            or re.search(r"(?:transaction|staging|\.after$|\.before$|\.lock$)", path.name, re.I)
        )
        and path.name not in {"package-lock.json"}
    ]
    audit.hard(not residue, "transaction_residue", residue[:20])
    secret_hits: list[str] = []
    text_hygiene_hits: list[str] = []
    for relative in sorted(changed):
        path = root / relative
        if not path.is_file():
            continue
        if path.stat().st_size > 5_000_000:
            text_hygiene_hits.append(f"oversized changed file not text-audited: {relative}")
            continue
        raw = path.read_bytes()
        if b"\0" in raw:
            secret_hits.append(f"binary/NUL {relative}")
            continue
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            text_hygiene_hits.append(f"invalid UTF-8 {relative}: {exc}")
            continue
        if CONTROL_RE.search(text):
            text_hygiene_hits.append(f"control character {relative}")
        if TRAILING_RE.search(text):
            text_hygiene_hits.append(f"trailing whitespace {relative}")
        if raw and not raw.endswith(b"\n"):
            text_hygiene_hits.append(f"missing final newline {relative}")
        for pattern in SECRET_PATTERNS:
            if pattern.search(text):
                secret_hits.append(f"{relative}: {pattern.pattern}")
    audit.hard(not secret_hits, "secret_or_binary_scan", secret_hits[:20])
    audit.hard(not text_hygiene_hits, "changed_text_hygiene", text_hygiene_hits[:20])
    audit.observations["git_scope"] = {"changed": len(changed), "allowed": len(allowed), "extra": len(changed - allowed)}


def validate_known_debt(root: Path, baseline: Mapping[str, bytes], audit: Audit) -> None:
    baseline_raw = baseline.get(KNOWN_BASELINE_DEBT_PATH)
    actual_path = root / KNOWN_BASELINE_DEBT_PATH
    if baseline_raw is None:
        try:
            baseline_raw = git_blobs(root, BASELINE_COMMIT, [KNOWN_BASELINE_DEBT_PATH])[KNOWN_BASELINE_DEBT_PATH]
        except Exception as exc:
            audit.hard(False, "known_debt_baseline", str(exc))
            return
    actual_raw = actual_path.read_bytes()
    audit.hard(actual_raw == baseline_raw, "known_debt_regression", {"path": KNOWN_BASELINE_DEBT_PATH, "baseline": sha256(baseline_raw), "actual": sha256(actual_raw)})
    count = actual_raw.count(KNOWN_BASELINE_DEBT_URL.encode("utf-8"))
    audit.hard(count == KNOWN_BASELINE_DEBT_OCCURRENCES, "known_debt_occurrence_drift", count)
    audit.observations["known_baseline_debt"] = {"path": KNOWN_BASELINE_DEBT_PATH, "url": KNOWN_BASELINE_DEBT_URL, "occurrences": count, "hard_error": False}


def audit_static(root: Path, documents: Mapping[str, bytes], audit: Audit) -> list[dict[str, Any]]:
    targets = target_relatives(root)
    audit.hard(len(targets) == TARGET_HTML_COUNT, "target_html_count", {"expected": TARGET_HTML_COUNT, "actual": len(targets)})
    counts = {category: sum(PurePosixPath(value).parts[1] == category for value in targets) for category in TARGET_CATEGORIES}
    audit.hard(all(value == DETAILS_PER_CATEGORY for value in counts.values()), "category_detail_counts", counts)
    baseline = git_blobs(root, BASELINE_COMMIT, [*targets, "sitemap.xml", KNOWN_BASELINE_DEBT_PATH])
    reports: list[dict[str, Any]] = []
    for relative in targets:
        final_raw = documents.get(relative, (root / relative).read_bytes())
        reports.append(validate_page(relative, baseline[relative], final_raw, audit))
    broken_links: list[dict[str, str]] = []
    broken_resources: list[dict[str, str]] = []
    href_count = 0
    resource_count = 0
    for report in reports:
        for value in report.get("hrefs", []):
            href_count += 1
            target = local_destination(root, str(report["route"]), str(value))
            if target is not None and not target.is_file():
                broken_links.append({"path": str(report["relative"]), "href": str(value)})
        for value in report.get("resources", []):
            resource_count += 1
            target = local_destination(root, str(report["route"]), str(value))
            if target is not None and not target.is_file():
                broken_resources.append({"path": str(report["relative"]), "resource": str(value)})
    audit.hard(not broken_links, "internal_broken_links", broken_links[:20])
    audit.hard(not broken_resources, "internal_broken_resources", broken_resources[:20])
    target_routes = {route_for_relative(relative) for relative in targets}
    final_sitemap = documents.get("sitemap.xml", (root / "sitemap.xml").read_bytes())
    validate_sitemap(baseline["sitemap.xml"], final_sitemap, target_routes, audit)
    validate_known_debt(root, baseline, audit)
    status_counts = Counter(report["status"] for report in reports)
    alias_counts = Counter(alias_allowlist_kind(relative) or "none" for relative in targets)
    audit.hard(status_counts.get("unknown", 0) == 0 and sum(status_counts.values()) == TARGET_HTML_COUNT, "school_source_status_coverage", dict(status_counts))
    audit.hard(
        alias_counts == Counter({"high": 6, "middle": 6, "combined": 3, "none": TARGET_HTML_COUNT - 15}),
        "alias_allowlist_exact15",
        dict(alias_counts),
    )
    audit.observations["static"] = {
        "target_html": len(targets),
        "categories": counts,
        "source_status": dict(status_counts),
        "alias_allowlist": dict(alias_counts),
        "internal_hrefs": href_count,
        "internal_broken": len(broken_links),
        "resource_references": resource_count,
        "internal_broken_resources": len(broken_resources),
        "target_manifest": manifest({relative: documents.get(relative, (root / relative).read_bytes()) for relative in targets}),
    }
    return reports


def validate_frozen_inputs(root: Path, audit: Audit) -> None:
    for relative, expected, code in (
        (APPROVED_FACT_AUDITOR_RELATIVE, APPROVED_FACT_AUDITOR_SHA256, "approved_fact_auditor_pin"),
    ):
        path = root / relative
        actual = sha256(path.read_bytes()) if path.is_file() else "MISSING"
        audit.hard(expected != "PENDING" and actual == expected, code, {"path": relative, "expected": expected, "actual": actual})


def validate_baseline(root: Path, audit: Audit) -> None:
    targets = target_relatives(root)
    target_values = {relative: (root / relative).read_bytes() for relative in targets}
    assets = {
        relpath(root, path): path.read_bytes()
        for path in (root / "assets").rglob("*")
        if path.is_file()
    }
    current_target = manifest(target_values)
    current_assets = manifest(assets)
    sitemap = sha256((root / "sitemap.xml").read_bytes())
    robots = sha256((root / "robots.txt").read_bytes())
    audit.hard(len(targets) == TARGET_HTML_COUNT, "baseline_target_count", len(targets))
    audit.hard(current_target == BASELINE_TARGET_MANIFEST, "baseline_target_manifest", {"expected": BASELINE_TARGET_MANIFEST, "actual": current_target})
    audit.hard(current_assets == BASELINE_ASSET_MANIFEST, "baseline_asset_manifest", {"expected": BASELINE_ASSET_MANIFEST, "actual": current_assets})
    audit.hard(sitemap == BASELINE_SITEMAP_SHA256, "baseline_sitemap_sha256", {"expected": BASELINE_SITEMAP_SHA256, "actual": sitemap})
    audit.hard(robots == BASELINE_ROBOTS_SHA256, "baseline_robots_sha256", {"expected": BASELINE_ROBOTS_SHA256, "actual": robots})
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False).stdout.decode().strip()
    main = subprocess.run(["git", "rev-parse", "main"], cwd=root, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False).stdout.decode().strip()
    remote = subprocess.run(["git", "rev-parse", "origin/main"], cwd=root, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False).stdout.decode().strip()
    audit.hard(head == main == remote == BASELINE_COMMIT, "baseline_git", {"head": head, "main": main, "origin_main": remote, "expected": BASELINE_COMMIT})
    audit.observations["baseline"] = {
        "commit": head,
        "target_count": len(targets),
        "target_manifest": current_target,
        "asset_count": len(assets),
        "asset_manifest": current_assets,
        "sitemap_sha256": sitemap,
        "robots_sha256": robots,
        "production_deployment": "dpl_3ZAauVhzAGpG13n7YMYRg6pk1PiK",
        "production_immutable": "academy-site-2-aztz6qok2-1992kjb.vercel.app",
    }


def select_browser_cases(reports: Sequence[Mapping[str, Any]], audit: Audit) -> list[dict[str, str]]:
    cases: list[dict[str, str]] = []
    for category in TARGET_CATEGORIES:
        values = sorted((item for item in reports if item.get("category") == category), key=lambda item: str(item.get("route")))
        selected_routes: set[str] = set()
        for status in ("provided", "missing"):
            candidates = [item for item in values if status in item.get("group_states", [])]
            distinct = [item for item in candidates if str(item.get("route")) not in selected_routes]
            if distinct:
                candidates = distinct
            audit.hard(bool(candidates), "browser_boundary_case", {"category": category, "source_group_state": status})
            if candidates:
                chosen = candidates[0]
                selected_routes.add(str(chosen["route"]))
                cases.append({
                    "category": category,
                    "status": status,
                    "route": str(chosen["route"]),
                    "h2": str(chosen["h2"]),
                    "group_count": str(len(CATEGORY_LEVELS[category])),
                })
    audit.hard(len(cases) == len(TARGET_CATEGORIES) * 2, "browser_case_count", {"expected": 16, "actual": len(cases)})
    audit.observations["browser_cases"] = cases
    return cases


def find_playwright_node_path() -> str | None:
    candidates: list[Path] = []
    configured = os.environ.get("NODE_PATH")
    if configured:
        for value in configured.split(os.pathsep):
            if (Path(value) / "playwright" / "package.json").is_file():
                candidates.append(Path(value))
    local = Path(os.environ.get("LOCALAPPDATA", "")) / "npm-cache" / "_npx"
    if local.is_dir():
        candidates.extend(path.parent.parent for path in local.glob("*/node_modules/playwright/package.json"))
    npm = shutil.which("npm") or shutil.which("npm.cmd")
    if npm:
        global_root = subprocess.run([npm, "root", "-g"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
        if global_root.returncode == 0:
            value = Path(global_root.stdout.decode("utf-8", "replace").strip())
            if (value / "playwright" / "package.json").is_file():
                candidates.append(value)
    if not candidates:
        return None
    def version(path: Path) -> tuple[int, ...]:
        try:
            raw = json.loads((path / "playwright" / "package.json").read_text(encoding="utf-8"))
            return tuple(int(part) for part in re.findall(r"\d+", str(raw.get("version", "0")))[:3])
        except Exception:
            return (0,)
    return str(max(set(candidates), key=version))


def find_node_executable() -> str | None:
    direct = shutil.which("node")
    if direct:
        return direct
    local = Path(os.environ.get("LOCALAPPDATA", ""))
    candidates = [
        *local.glob("Microsoft/WinGet/Packages/OpenJS.NodeJS*/node-*-win-x64/node.exe"),
        Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "nodejs" / "node.exe",
    ]
    existing = [path for path in candidates if path.is_file()]
    if not existing:
        return None
    return str(max(existing, key=lambda path: path.stat().st_mtime_ns))


def run_browser(base: str, cases: Sequence[Mapping[str, str]], timeout: int) -> dict[str, Any]:
    node_path = find_playwright_node_path()
    node_executable = find_node_executable()
    if node_path is None or node_executable is None:
        return {"tests": 0, "failures": 1, "error": "playwright package or node executable not found"}
    import base64
    payload = base64.b64encode(json.dumps({"base": base.rstrip("/"), "domain": DOMAIN, "cases": list(cases), "widths": BROWSER_WIDTHS}, ensure_ascii=False).encode("utf-8")).decode("ascii")
    script = r'''
const {chromium}=require('playwright');
const cfg=JSON.parse(Buffer.from(process.argv[1],'base64').toString('utf8'));
(async()=>{
 const browser=await chromium.launch({headless:true}); const rows=[];
 for(const item of cfg.cases){ for(const width of cfg.widths){
  const context=await browser.newContext({viewport:{width,height:900},locale:'ko-KR'});
  const page=await context.newPage(); const consoleErrors=[],pageErrors=[],network=[];
  page.on('console',m=>{if(m.type()==='error')consoleErrors.push(m.text())});
  page.on('pageerror',e=>pageErrors.push(String(e)));
  page.on('requestfailed',r=>network.push('FAIL '+r.url()));
  page.on('response',r=>{if(r.status()>=400)network.push(r.status()+' '+r.url())});
  let status=0,nav=''; try{const response=await page.goto(cfg.base+item.route,{waitUntil:'networkidle',timeout:30000});status=response?response.status():0}catch(e){nav=String(e)}
  const section=page.locator('section[data-school-reference]');
  if(await section.count()===1){try{await section.scrollIntoViewIfNeeded({timeout:3000});await page.waitForTimeout(100)}catch{}}
  const state=await page.evaluate(({expectedRoute,expectedH2,expectedStatus,domain})=>{
   const sections=[...document.querySelectorAll('section[data-school-reference]')]; const section=sections[0];
   const tagStatus=section?(section.getAttribute('data-school-source-status')||section.getAttribute('data-source-status')||'').toLowerCase():'';
   const groups=section?[...section.querySelectorAll('[data-source-state]')].map(x=>({state:(x.getAttribute('data-source-state')||'').toLowerCase(),schoolCount:x.querySelectorAll('[data-source-school]').length,text:(x.innerText||'').replace(/\s+/g,' ').trim()})):[];
   const groupStates=groups.map(x=>x.state);
   let inferred='provided'; if(groupStates.includes('provided'))inferred='provided';else if(groupStates.includes('coverage'))inferred='coverage';else if(groupStates.length&&groupStates.every(x=>x==='missing'))inferred='missing';else if(/missing|blank|empty|unconfirmed/.test(tagStatus))inferred='missing';else if(tagStatus)inferred='provided';else if(section&&/__BROWSER_MISSING_CUE__/.test(section.innerText))inferred='missing';
   const rect=section?section.getBoundingClientRect():null; const style=section?getComputedStyle(section):null;
   const canonical=[...document.querySelectorAll('link[rel~="canonical"]')].map(x=>x.href);
   const robots=[...document.querySelectorAll('meta[name="robots" i]')].map(x=>x.content);
   return {sectionCount:sections.length,visible:!!section&&style.display!=='none'&&style.visibility!=='hidden'&&rect.width>0&&rect.height>0,sectionOverflow:!!rect&&rect.right>innerWidth+1,h2:section?(section.querySelector('h2')?.innerText||'').replace(/\s+/g,' ').trim():'',status:inferred,text:section?(section.innerText||'').replace(/\s+/g,' ').trim():'',groups,groupStates,schoolCount:section?section.querySelectorAll('[data-source-school]').length:0,canonical,h1:document.querySelectorAll('h1').length,noindex:robots.some(x=>/noindex/i.test(x)),overflow:document.documentElement.scrollWidth>innerWidth+1,indexHref:[...document.querySelectorAll('a[href]')].filter(x=>/index\.html(?:[?#]|$)/i.test(x.getAttribute('href'))).length,expectedCanonical:domain+expectedRoute,expectedH2,expectedStatus};
  },{expectedRoute:item.route,expectedH2:item.h2,expectedStatus:item.status,domain:cfg.domain});
  const allowedNetwork=network.filter(x=>!x.includes('https://wawa-center.com/wp-content/uploads/2026/06/M370.jpg'));
  const failures=[];
  if(status!==200)failures.push('status'); if(nav)failures.push('navigation'); if(consoleErrors.length)failures.push('console'); if(pageErrors.length)failures.push('pageerror'); if(allowedNetwork.length)failures.push('network');
  if(state.sectionCount!==1||!state.visible||state.sectionOverflow)failures.push('section'); if(state.h2!==item.h2)failures.push('h2');
  if(state.groupStates.length!==Number(item.group_count)||state.groupStates.some(x=>!['provided','coverage','missing'].includes(x)))failures.push('source-groups');
  if(state.canonical.length!==1||state.canonical[0]!==state.expectedCanonical)failures.push('canonical'); if(state.h1!==1||state.noindex||state.overflow||state.indexHref)failures.push('document');
  const matchingGroups=state.groups.filter(x=>x.state===item.status);
  if(item.status==='missing'&&(!matchingGroups.length||matchingGroups.some(x=>x.schoolCount!==0)||!matchingGroups.some(x=>/__BROWSER_MISSING_CUE__/.test(x.text))))failures.push('missing-state');
  if(item.status==='provided'&&(!matchingGroups.length||!matchingGroups.some(x=>x.schoolCount>0&&x.text.length>=20)))failures.push('provided-content');
  rows.push({route:item.route,category:item.category,expectedStatus:item.status,width,status,nav,consoleErrors,pageErrors,network,allowedNetwork,state,failures});
  await context.close();
 }} await browser.close();
 const failed=rows.filter(x=>x.failures.length); console.log(JSON.stringify({tests:rows.length,failures:failed.length,failureRows:failed.slice(0,20),rows}));
})().catch(e=>{console.error(e);process.exit(1)});
'''
    script = script.replace("__BROWSER_MISSING_CUE__", BROWSER_MISSING_CUE_PATTERN)
    env = dict(os.environ)
    env["NODE_PATH"] = node_path
    try:
        result = subprocess.run([node_executable, "-e", script, payload], stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env, timeout=timeout, check=False)
    except subprocess.TimeoutExpired:
        return {"tests": 0, "failures": 1, "error": "browser timeout"}
    if result.returncode:
        return {"tests": 0, "failures": 1, "error": result.stderr.decode("utf-8", "replace")[-2000:]}
    try:
        return json.loads(result.stdout.decode("utf-8"))
    except Exception as exc:
        return {"tests": 0, "failures": 1, "error": f"invalid browser output: {exc}: {result.stdout[-1000:]!r}"}


def self_test(audit: Audit) -> None:
    baseline = '<body><main><p>before</p><p>after</p></main></body>'
    final = '<body><main><p>before</p>\n<!-- school-reference:start --><section data-school-reference data-school-source-status="provided"><h2>학교 참고</h2></section><!-- school-reference:end -->\n<p>after</p></main></body>'
    ok, _ = remove_school_fragment(final, baseline)
    audit.hard(ok, "selftest_marker_removal")
    fragment, errors = school_fragment(final)
    audit.hard(fragment is not None and not errors and section_status(fragment) == "provided", "selftest_fragment", errors)
    missing = '<!-- school-reference:start --><section data-school-reference data-school-source-status="missing"><h2>학교 참고</h2><p>원자료 미기재</p></section><!-- school-reference:end -->'
    audit.hard(section_status(missing) == "missing", "selftest_missing")
    high = f"{PARENT}/고등수학학원/상남동/index.html"
    middle = f"{PARENT}/중등수학학원/상남동/index.html"
    combined = f"{PARENT}/영수학원/상남동/index.html"
    audit.hard(apply_alias_body_fix(high, "앙여고") == "창원중앙여고", "selftest_alias_high")
    audit.hard(apply_alias_body_fix(middle, "A·창원중") == "A", "selftest_alias_middle")
    audit.hard(apply_alias_body_fix(combined, "창원중·앙여고") == "창원중앙여고", "selftest_alias_combined")
    porcelain = (
        b" M path with space.html\0"
        + "?? 과목별학원/한글 경로/index.html\0".encode("utf-8")
        + b"R  renamed new.html\0renamed old.html\0"
        + "C  복사 새.html\0복사 옛.html\0".encode("utf-8")
    )
    try:
        paths, statuses = parse_porcelain_v1_z(porcelain)
        audit.hard(
            paths
            == {
                "path with space.html",
                "과목별학원/한글 경로/index.html",
                "renamed new.html",
                "renamed old.html",
                "복사 새.html",
                "복사 옛.html",
            },
            "selftest_porcelain_paths",
            sorted(paths),
        )
        audit.hard(statuses == [" M", "??", "R ", "C "], "selftest_porcelain_statuses", statuses)
    except Exception as exc:
        audit.hard(False, "selftest_porcelain_exception", f"{type(exc).__name__}: {exc}")
    missing_positive = (
        "원자료의 고등학교 목록에는 이름이 없습니다.",
        "특정 중학교 이름이 별도로 적혀 있지 않습니다.",
        "원자료의 중학교 항목은 비어 있습니다.",
        "원자료에 적혀 있지 않습니다.",
    )
    missing_negative = (
        "학교 목록의 이름을 확인합니다.",
        "중학교 이름을 별도로 적습니다.",
        "원자료의 중학교 항목을 비교합니다.",
        "원자료에 학교 이름이 있습니다.",
    )
    audit.hard(
        all(re.search(BROWSER_MISSING_CUE_PATTERN, value) for value in missing_positive),
        "selftest_browser_missing_positive",
        missing_positive,
    )
    audit.hard(
        not any(re.search(BROWSER_MISSING_CUE_PATTERN, value) for value in missing_negative),
        "selftest_browser_missing_negative",
        missing_negative,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Read-only technical release gate for school-reference sections")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--common-dir", type=Path)
    parser.add_argument("--generator", type=Path, default=Path(APPROVED_GENERATOR_RELATIVE))
    parser.add_argument("--browser-base")
    parser.add_argument("--browser-timeout", type=int, default=300_000)
    parser.add_argument("--baseline-only", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = args.root.resolve()
    audit = Audit()
    started = time.time()
    if args.self_test:
        self_test(audit)
        report = {"ok": not audit.errors, "mode": "self-test", "errors": audit.errors, "observations": audit.observations, "elapsed_seconds": round(time.time() - started, 3)}
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if not audit.errors else 1
    if args.baseline_only:
        validate_baseline(root, audit)
        validate_known_debt(root, {}, audit)
        report = {"ok": not audit.errors, "mode": "baseline", "errors": audit.errors, "observations": audit.observations, "elapsed_seconds": round(time.time() - started, 3)}
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if not audit.errors else 1

    release_repo_before = tree_snapshot(root)
    release_status_before = git_status(root)
    generator = args.generator if args.generator.is_absolute() else root / args.generator
    audit.hard(generator.is_file(), "generator_missing", str(generator))
    common_dir: Path | None = None
    projection: Projection | None = None
    if generator.is_file():
        try:
            common_dir = discover_common_dir(root, args.common_dir)
            projection = run_projection(root, generator.resolve(), common_dir, audit)
        except Exception as exc:
            audit.hard(False, "projection_exception", f"{type(exc).__name__}: {exc}")
    validate_frozen_inputs(root, audit)
    expected = expected_document_paths(root)
    validate_git_scope(root, expected, audit)
    reports: list[dict[str, Any]] = []
    browser: dict[str, Any] | None = None
    mode = "projection-failed"
    if projection is not None:
        mode = "projected" if projection.changed_paths else "actual"
        reports = audit_static(root, projection.documents, audit)
        cases = select_browser_cases(reports, audit)
        if mode == "actual":
            audit.hard(bool(args.browser_base), "actual_browser_required", "materialized release requires --browser-base")
        if args.browser_base:
            audit.hard(mode == "actual", "browser_requires_materialized_release", mode)
            if mode == "actual":
                if audit.errors:
                    audit.hard(False, "browser_skipped_due_static_hold", {"pre_browser_errors": len(audit.errors)})
                else:
                    browser = run_browser(args.browser_base, cases, args.browser_timeout)
                    audit.hard(browser.get("tests") == 48, "browser_test_count", {"expected": 48, "actual": browser.get("tests")})
                    audit.hard(browser.get("failures") == 0, "browser_contract", {key: value for key, value in browser.items() if key != "rows"})
    validate_frozen_inputs(root, audit)
    if projection is not None:
        current_generator_hash = sha256(generator.read_bytes()) if generator.is_file() else "MISSING"
        audit.hard(
            current_generator_hash == projection.generator_sha256,
            "generator_post_audit_freeze",
            {"before": projection.generator_sha256, "after": current_generator_hash},
        )
    release_repo_after = tree_snapshot(root)
    release_status_after = git_status(root)
    audit.hard(
        release_repo_before == release_repo_after,
        "release_repo_pre_post_freeze",
        {"before": release_repo_before[0], "after": release_repo_after[0]},
    )
    audit.hard(
        release_status_before == release_status_after,
        "release_git_pre_post_freeze",
        {"before": release_status_before, "after": release_status_after},
    )
    audit.observations["release_freeze"] = {
        "repo_before": release_repo_before[0],
        "repo_after": release_repo_after[0],
        "git_status_equal": release_status_before == release_status_after,
    }
    report = {
        "ok": not audit.errors,
        "mode": mode,
        "error_count": len(audit.errors),
        "errors": audit.errors[:200],
        "observations": audit.observations,
        "browser": browser,
        "release_auditor_sha256": sha256(Path(__file__).read_bytes()),
        "elapsed_seconds": round(time.time() - started, 3),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if not audit.errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
