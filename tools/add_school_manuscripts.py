from __future__ import annotations

"""Add source-bound, locality-specific school manuscripts to subject pages.

The default command is deliberately read-only.  ``--apply`` additionally needs the
literal ``--go APPLY-GO`` and frozen source/before hashes.  The public
``build_plan`` API is intended for release auditors and returns every authorized
target document in memory without touching the working tree.

Owned output:
* 2,968 locality detail pages under the eight configured subject categories.
* ``sitemap.xml`` (only the matching detail-page ``lastmod`` values).

The common ``타깃학교.csv`` file is the sole authority for school availability.
Named schools mean that students of those schools can actually receive a lesson;
the source does not, by itself, promise every grade, subject, time, curriculum or
exam scope.  A blank field means "not listed in this source", never "unavailable".
"""

import argparse
import contextlib
import copy
import csv
import functools
import hashlib
import html
import io
import json
import os
import re
import shutil
import stat
import sys
import tempfile
import uuid
from collections import Counter
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Iterable, Mapping, Sequence
from urllib.parse import unquote

try:
    from source_copy_utils import VERIFIED_SCHOOL_SOURCE_CORRECTIONS
except ModuleNotFoundError:  # package import, e.g. tools.add_school_manuscripts
    from .source_copy_utils import VERIFIED_SCHOOL_SOURCE_CORRECTIONS


RELEASE_DATE = "2026-08-27"
SCHOOL_CSV_NAME = "타깃학교.csv"
SUBJECT_ROOT_NAME = "과목별학원"
SITEMAP_NAME = "sitemap.xml"
BASE_URL = "https://xn--ru4bi8s1tac0p.kr"

START_MARKER = "<!-- school-reference:start -->"
END_MARKER = "<!-- school-reference:end -->"
OUTER_ID = "school-reference"
TITLE_ID = "school-reference-title"
SOURCE_FIELD = "target-schools"
COVERAGE_RAW = "지역내 모든 고등학교 가능"

LEVEL_ORDER = ("elementary", "middle", "high")
LEVEL_LABEL = {
    "elementary": "초등학교",
    "middle": "중학교",
    "high": "고등학교",
}
LEVEL_SHORT = {
    "elementary": "초등",
    "middle": "중등",
    "high": "고등",
}
LEVEL_HEADER_HINT = {
    "elementary": "(초)",
    "middle": "(중)",
    "high": "(고)",
}

# Fixed release gates supplied by the source audit.  They intentionally fail if
# the authoritative file changes between freeze and apply.
EXPECTED_SOURCE_ROWS = 371
EXPECTED_LEVEL_STATS = {
    "elementary": {
        "provided_rows": 297,
        "missing_rows": 74,
        "coverage_rows": 0,
        "raw_names": 640,
        "deduped_names": 640,
    },
    "middle": {
        "provided_rows": 318,
        "missing_rows": 53,
        "coverage_rows": 0,
        "raw_names": 857,
        "deduped_names": 854,
    },
    "high": {
        "provided_rows": 306,
        "missing_rows": 63,
        "coverage_rows": 2,
        "raw_names": 943,
        "deduped_names": 941,
    },
}
EXPECTED_PAGE_COUNT = 2_968
EXPECTED_GROUP_COUNT = 3_710
EXPECTED_GROUP_STATES = {
    "provided": 3_090,
    "coverage": 8,
    "missing": 612,
}
EXPECTED_NAMED_CHIPS = 8_460

JSON_RE = re.compile(
    r'(<script\b[^>]*type=["\']application/ld\+json["\'][^>]*>)(.*?)(</script>)',
    re.I | re.S,
)
CANONICAL_RE = re.compile(r'<link\s+rel="canonical"\s+href="([^"]+)"\s*/?>', re.I)
H1_RE = re.compile(r'<h1\b[^>]*>(.*?)</h1>', re.I | re.S)
TITLE_RE = re.compile(r'<title>(.*?)</title>', re.I | re.S)
META_DESCRIPTION_RE = re.compile(
    r'<meta\s+name="description"\s+content="([^"]*)"\s*/?>', re.I
)
OG_URL_RE = re.compile(
    r'<meta\s+property="og:url"\s+content="([^"]*)"\s*/?>', re.I
)
FAQ_VISIBLE_RE = re.compile(
    r'<section\b[^>]*class="[^"]*subject-faq-section[^"]*".*?</section>',
    re.I | re.S,
)
MANUSCRIPT_OPEN = '<article class="subject-manuscript wrap"'
SCHOOL_BLOCK_RE = re.compile(
    re.escape(START_MARKER) + r"(?:\r\n|\n|\r).*?" + re.escape(END_MARKER)
    + r"(?:\r\n|\n|\r)",
    re.S,
)
SCHOOL_SPLIT_RE = re.compile(r"\s*[,/.]+\s*")
SITEMAP_URL_RE = re.compile(r"<url>.*?</url>", re.S)
SITEMAP_LOC_RE = re.compile(r"<loc>(.*?)</loc>", re.S)
SITEMAP_LASTMOD_RE = re.compile(r"(<lastmod>)(.*?)(</lastmod>)", re.S)
TAG_RE = re.compile(r"<[^>]+>")
SENTENCE_RE = re.compile(r"(?<=[.!?。！？])\s+")
SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
TRANSACTION_NAME_RE = re.compile(r"\.school-manuscripts-txn-([0-9a-f]{32})\Z")
PREP_NAME_RE = re.compile(r"\.school-manuscripts-prep-([0-9a-f]{32})\Z")
JOURNAL_VERSION = 2
JOURNAL_KEYS = frozenset(
    {
        "version",
        "transaction_id",
        "status",
        "source_sha256",
        "entries",
        "before_manifest",
        "after_manifest",
    }
)
JOURNAL_ENTRY_KEYS = frozenset(
    {"path", "before_sha256", "after_sha256", "backup_sha256", "stage_sha256"}
)
JOURNAL_STATES = frozenset({"prepared", "committing", "committed"})

# Naturalness is a release invariant, not a best-effort style check.  These
# families intentionally match the independent release auditor.  The few extra
# families at the end catch the same sort of noun/action echo before it becomes
# visible copy (for example, "메모 ... 메모" or "정리 ... 구분").
AUTHORED_REPEAT_PATTERNS: dict[str, re.Pattern[str]] = {
    "school": re.compile(r"학교(?:명|별)?"),
    "grade": re.compile(r"학년(?:별)?"),
    "subject": re.compile(r"과목(?:별)?"),
    "class": re.compile(r"수업"),
    "student": re.compile(r"학생"),
    "schedule": re.compile(r"일정"),
    "time": re.compile(r"시간(?:표|대)?"),
    "day": re.compile(r"요일"),
    "range": re.compile(r"범위"),
    "condition": re.compile(r"조건"),
    "arrangement": re.compile(r"편성"),
    "available": re.compile(r"(?<!불)가능"),
    "check": re.compile(r"(?:재)?확인|점검|검토|살피"),
    "compare": re.compile(r"대조|비교"),
    "consult": re.compile(r"상담"),
    "inquiry": re.compile(r"문의"),
    "record": re.compile(r"기록"),
    "source": re.compile(r"원자료"),
    "list": re.compile(r"목록"),
    # Stricter generator-only safeguards.
    "current": re.compile(r"현재"),
    "answer": re.compile(r"답변|응답"),
    "information": re.compile(r"정보"),
    "hope": re.compile(r"희망"),
    "opening": re.compile(r"개설|시작"),
    "registration": re.compile(r"등록"),
    "prepare": re.compile(r"준비|마련"),
    "organize": re.compile(r"정리|구분|분리"),
    "communicate": re.compile(r"전달|알리"),
    "note": re.compile(r"메모"),
    "basis": re.compile(r"기준"),
    "last": re.compile(r"마지막"),
    "final": re.compile(r"최종"),
    "learning": re.compile(r"학습"),
    "question": re.compile(r"질문"),
    "item": re.compile(r"항목"),
    "point": re.compile(r"시점"),
    "actual": re.compile(r"실제"),
    "separate": re.compile(r"별도"),
    "whether": re.compile(r"여부"),
    "together": re.compile(r"함께"),
    "material": re.compile(r"자료"),
    "brief": re.compile(r"짧게"),
    "date": re.compile(r"날짜"),
}

HEADING_SEMANTIC_PATTERNS: dict[str, re.Pattern[str]] = {
    "student": re.compile(r"학생"),
    "school": re.compile(r"(?:재학\s*)?학교(?:명|별|\s*목록|\s*정보|\s*근거)?"),
    "grade": re.compile(r"학년"),
    "subject": re.compile(r"과목"),
    "schedule": re.compile(r"(?:학생\s*)?일정|시간(?:표|대)?|요일"),
    "range": re.compile(r"범위"),
    "arrangement": re.compile(r"(?:반\s*)?편성"),
    "opening": re.compile(r"개설|시작"),
    "condition": re.compile(r"조건"),
    "compare": re.compile(r"대조|비교"),
    "check": re.compile(r"(?:재)?확인|점검|검토|살피"),
    "record": re.compile(r"기록|메모"),
    "prepare": re.compile(r"준비|마련"),
    "organize": re.compile(r"정리|구분|분리"),
    "consult": re.compile(r"상담|문의|질문"),
    "communicate": re.compile(r"전달|알리"),
}
HEADING_ACTION_FAMILIES = frozenset(
    {"compare", "check", "record", "prepare", "organize", "consult", "communicate"}
)
HEADING_NATURALNESS_EXTRA_PATTERNS: dict[str, re.Pattern[str]] = {
    "hope": re.compile(r"희망"),
    "lesson": re.compile(r"수업"),
    "available": re.compile(r"(?<!불)가능"),
    "information": re.compile(r"정보"),
    "learning": re.compile(r"학습"),
    "registration": re.compile(r"등록"),
    "source": re.compile(r"원자료"),
    "actual": re.compile(r"실제"),
}


class PlanError(RuntimeError):
    """Raised when a source, parity or release gate fails."""


@dataclass(frozen=True)
class CategoryConfig:
    directory: str
    label: str
    service: str
    levels: tuple[str, ...]


CATEGORIES: tuple[CategoryConfig, ...] = (
    CategoryConfig("초등학생학원", "초등학생학원", "초등 과정", ("elementary",)),
    CategoryConfig("중학생학원", "중학생학원", "중학생 과정", ("middle",)),
    CategoryConfig("중등수학학원", "중등 수학학원", "중등 수학", ("middle",)),
    CategoryConfig("중등영어학원", "중등 영어학원", "중등 영어", ("middle",)),
    CategoryConfig("고등학생학원", "고등학생학원", "고등학생 과정", ("high",)),
    CategoryConfig("고등수학학원", "고등 수학학원", "고등 수학", ("high",)),
    CategoryConfig("고등영어학원", "고등 영어학원", "고등 영어", ("high",)),
    CategoryConfig(
        "영수학원",
        "영수학원",
        "영어 또는 수학",
        ("elementary", "middle", "high"),
    ),
)
CATEGORY_BY_DIR = {config.directory: config for config in CATEGORIES}


@dataclass(frozen=True)
class LevelSource:
    level: str
    raw: str
    state: str
    names: tuple[str, ...]
    raw_name_count: int


@dataclass(frozen=True)
class SchoolSourceRow:
    locality: str
    source_locality: str
    region: str
    district: str
    center: str
    levels: Mapping[str, LevelSource]


@dataclass(frozen=True)
class BuildPlan:
    """Complete in-memory release plan.

    Keys are root-relative POSIX paths.  Values are final raw Unicode text; a
    leading BOM and the original EOL style, when present, remain in the string.
    """

    authorized_documents: dict[str, str]
    changed_paths: tuple[str, ...]
    diagnostics: dict
    source_sha256: str
    before_manifest: dict[str, str]
    after_manifest: dict[str, str]
    second_pass_changes: tuple[str, ...]

    @property
    def documents(self) -> dict[str, str]:
        return self.authorized_documents


@dataclass(frozen=True)
class JournalEntry:
    path: str
    before_sha256: str
    after_sha256: str
    backup_sha256: str
    stage_sha256: str


@dataclass(frozen=True)
class ValidatedJournal:
    transaction_id: str
    status: str
    source_sha256: str
    entries: tuple[JournalEntry, ...]
    before_manifest: dict[str, str]
    after_manifest: dict[str, str]


HEADING_FOCUSES = (
    "상담 범위 확인 기준",
    "학년·시간 대조 순서",
    "등록 전 확인 항목",
    "현재 편성 확인 방법",
    "상담 메모 준비법",
    "학교 목록 읽는 기준",
    "첫 상담 질문 순서",
    "수업 범위 점검 방법",
    "희망 과목 확인 순서",
    "재학 학교 대조 기준",
    "상담 자료 준비 순서",
    "가능 범위 확인 절차",
    "학년별 문의 준비법",
    "현재 수업 확인 기준",
    "상담 전 기록 항목",
    "학교별 문의 정리법",
    "반 편성 확인 순서",
    "수업 시간 확인 방법",
    "과목 범위 대조 기준",
    "첫 문의 준비 항목",
    "학습 상황 전달 순서",
    "수업 조건 확인 절차",
    "상담 범위 정리 방법",
    "학년·과목 확인 기준",
    "학교 정보 활용 순서",
    "현재 개설 문의 방법",
    "상담 전 대조 항목",
    "학생 정보 준비 순서",
    "실제 수업 확인 기준",
    "가능 학교 확인 방법",
    "학교·학년 상담 절차",
)

HEADING_STARTS = (
    "재학 학교 확인",
    "현재 학년 대조",
    "희망 과목 정리",
    "가능 시간 기록",
    "상담 자료 준비",
    "학교 범위 확인",
    "학생 정보 전달",
    "현재 편성 문의",
    "수업 조건 분리",
    "학년 범위 점검",
    "첫 문의 메모",
    "학교 목록 대조",
    "상담 순서 설계",
    "개설 조건 확인",
    "재학 정보 준비",
    "희망 요일 정리",
    "학생 일정 대조",
    "수업 범위 기록",
    "학교 근거 확인",
)

HEADING_ENDS = (
    "최신 편성 확인",
    "학년별 문의",
    "과목 범위 대조",
    "수업 시간 확인",
    "상담 답변 기록",
    "현재 조건 점검",
    "학생 일정 비교",
    "등록 전 재확인",
    "학교 정보 활용",
    "반 편성 문의",
    "희망 수업 확인",
    "상담 범위 결정",
    "가능 조건 구분",
    "학년·시간 점검",
    "시작 조건 확인",
    "최종 상담 대조",
    "수업 여부 확인",
)

# These fragments are deliberately combined in the same sentence.  Their
# cross-product gives natural page-level variation without inventing school facts.
STATE_SUBJECTS = (
    "재학 학교를",
    "학생 학년을",
    "희망 과목을",
    "가능 요일을",
    "상담 목적을",
    "현재 학습 범위를",
    "희망 시작 시점을",
    "학생 일정을",
    "문의 과목을",
    "학교·학년 정보를",
    "상담 우선순위를",
    "필요 수업 범위를",
    "가능 시간대를",
    "학생의 현재 조건을",
    "등록 전 질문을",
    "수업 희망 조건을",
    "재학 정보를",
    "학년별 문의를",
    "상담 메모를",
)

STATE_ACTIONS = (
    "첫 항목으로 적고",
    "원자료와 맞춘 뒤",
    "서로 나누어 정리하고",
    "상담 순서에 맞춰 기록한 뒤",
    "한 줄씩 구분해 전달하고",
    "현재 정보로 대조한 다음",
    "먼저 확인 항목에 넣고",
    "상담 전에 정확히 적은 뒤",
    "학교 범위와 함께 살피고",
    "빠짐없이 메모한 다음",
    "학생 기준으로 정리하고",
    "질문 순서대로 준비한 뒤",
    "학교명과 구분해 적고",
    "현재 상태대로 전달한 다음",
    "첫 질문으로 확인하고",
    "상담 기록에 남긴 뒤",
    "가능 학교와 대조하고",
)

# A page has three authored sentences for a single-level category and seven for
# 영수학원 (state + guidance per level, then the closing).  A stable rotation of
# these seven human-reviewed atomic subject/predicate clauses prevents both
# template-looking repetition and semantically invalid subject/action cross
# products.  The renderer must use the complete clause; it never combines the
# subject from one row with the predicate from another.
ENDING_STYLE_PARTS = (
    ("ask", "반 배정 상태는", "담당자에게 직접 물어보세요."),
    ("record", "운영 안내는", "받은 문구 그대로 노트에 남기세요."),
    ("listen", "담당자의 배정 설명은", "끝까지 들어 보세요."),
    ("mark", "회신받은 자리 상태는", "빈칸에 분명하게 표시하세요."),
    (
        "align",
        "원자료 표기와 최신 안내가",
        "일치하는지 대조해 보세요.",
    ),
    ("preserve", "안내 문구는", "받은 날짜와 함께 보관하세요."),
    ("review", "받은 회신은", "처음부터 다시 읽어 보세요."),
)
ENDING_STYLES = tuple(
    (family, f"{subject} {predicate}")
    for family, subject, predicate in ENDING_STYLE_PARTS
)
LEGACY_INCOMPATIBLE_ENDING_PATTERNS: dict[str, re.Pattern[str]] = {
    "boundary-preserve": re.compile(
        r"(?:실제 시작 시점|현재 반 편성)(?:은|는).*받은 문구.*보관"
    ),
    "answer-review": re.compile(
        r"최신 상담 답변(?:은|는).*응답 내용.*읽어"
    ),
    "schedule-listen": re.compile(
        r"(?:최종 과목 범위|가능한 수업 시간)(?:은|는).*최신 설명.*들어"
    ),
    "range-mark": re.compile(
        r"최종 과목 범위(?:은|는).*회신 내용.*표시"
    ),
}
STATE_ENDING_SLOT = {"elementary": 0, "middle": 2, "high": 4}
GUIDANCE_ENDING_SLOT = {"elementary": 1, "middle": 3, "high": 5}
CLOSING_ENDING_SLOT = 6

GUIDANCE_CONTEXTS = (
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

LEVEL_STAGE_PHRASE = {
    "elementary": "초등 학습 단계",
    "middle": "중등 교과 단계",
    "high": "고등 학습 단계",
}

PROVIDED_STATE_TEMPLATES = (
    "{locality}에서 {service} 수업이 실제 가능한 {level_label}로 원자료에 확인된 학교는 {schools}입니다.",
    "원자료 기준 {locality}의 {level_label} 가운데 {service} 실제 수업 가능 학교는 {schools}입니다.",
    "{locality} {category} 상담에 연결된 {level_label} 실제 수업 가능 학교 목록은 {schools}입니다.",
    "{locality}의 {service} 실제 수업 가능 범위를 학교명으로 대조한 원자료 기재 내용은 {schools}입니다.",
    "공통 원자료에서 {locality} {service} 실제 수업 가능 학교로 명시한 {level_label}는 {schools}입니다.",
    "{locality} 페이지에 적용되는 {level_label} 실제 수업 가능 목록은 {schools}이며, {service} 상담의 학교 근거로 사용합니다.",
    "{locality}의 {level_label} 가운데 원자료가 {service} 실제 수업 가능 대상으로 확인한 곳은 {schools}입니다.",
    "학교 기준으로 살펴본 {locality} {service} 실제 수업 가능 범위의 원자료 확인 결과는 {schools}입니다.",
    "{locality}에서 재학 학교를 먼저 대조할 때 사용할 {level_label} 실제 수업 가능 목록은 {schools}입니다.",
    "{locality} {category}의 {level_label} 범위는 원자료상 {schools}이며, 모두 실제 수업 가능 학교입니다.",
    "원자료에 적힌 {locality} {level_label} 실제 수업 가능 학교는 {schools}이며, {service} 상담에서 확인할 학교 범위입니다.",
    "{locality}의 실제 수업 가능 학교 정보를 {level_label} 기준으로 정리하면 {schools}이며, {service} 상담의 근거로 사용합니다.",
    "{locality}에서 {service} 실제 수업이 가능한 {level_label} 대상은 원자료의 {schools}입니다.",
    "{locality}에서 {service} 실제 수업 가능 학교 범위를 {level_label} 기준으로 정리한 원자료 내용은 {schools}입니다.",
    "{locality} 실제 수업 가능 학교 원자료에서 {level_label} 항목에 기재된 곳은 {schools}입니다.",
    "{locality} {category}의 {level_label} 실제 수업 가능 기재 내용은 {schools}입니다.",
    "{locality}의 {service} 상담과 연결되는 {level_label} 실제 수업 가능 학교는 원자료의 {schools}입니다.",
)

PROVIDED_GUIDANCE_LEADS = (
    "상담을 시작할 때는 재학 학교와 희망 학년을 먼저 적고",
    "첫 문의에서는 학생의 재학 학교를 목록과 대조하고 현재 학년을 따로 적은 뒤",
    "등록 가능 범위를 확인하려면 재학 학교를 먼저 밝히고",
    "수업 조건을 빠르게 맞추려면 학교명과 현재 학년을 전한 다음",
    "상담 메모에는 재학 학교와 학년을 첫 줄에 두고",
    "현재 가능한 반을 확인할 때는 학교와 학년을 먼저 대조하고",
    "학교 목록을 확인한 뒤에는 학생의 학년과 희망 과목을 나누어 적고",
    "첫 상담 전에 재학 학교·학년·희망 과목을 구분해 준비하고",
    "수업 범위를 오해하지 않으려면 학교 가능 여부를 먼저 확인한 뒤",
    "상담 순서를 학교 확인부터 시작하고 학생의 현재 학년을 이어서 알린 뒤",
    "페이지의 학교명 중 재학 학교를 찾은 다음 학년 정보를 덧붙이고",
    "학교 범위를 확인한 상태에서 학생의 학년과 문의 과목을 별도로 전하고",
    "실제 편성을 대조할 때 학교명과 학년을 한 항목으로 정리한 뒤",
    "상담 자료에 학교·학년을 정확히 적은 다음",
    "학생이 다니는 학교가 목록에 있음을 확인하고 현재 학년을 함께 전한 뒤",
    "학교 기준이 맞는지 확인한 다음 학년별 문의 범위를 정리하고",
    "재학 학교를 원자료 목록과 맞춘 뒤 학생의 희망 수업을 설명하고",
    "상담 전에 학교와 학년을 서로 다른 항목으로 기록하고",
    "학교 정보 확인을 마치면 학생의 현재 학습 상황을 짧게 덧붙이고",
)

PROVIDED_GUIDANCE_TAILS = (
    "현재 반 편성·수업 시간·학년별 가능 범위를 상담 시점에 다시 확인하세요.",
    "원하는 요일과 시간을 현재 개설 범위와 상담에서 대조하세요.",
    "학년별 수업 여부와 가능한 시간을 최신 상담 내용으로 확인하세요.",
    "지금 개설된 학년·시간이 학생 일정과 맞는지 따로 문의하세요.",
    "희망 과목의 현재 학년 편성과 수업 시간을 마지막에 확인하세요.",
    "수업 시작 가능 시점과 학년별 편성을 상담 답변으로 다시 맞추세요.",
    "학교명만으로 반을 단정하지 말고 학년과 시간 조건을 함께 확인하세요.",
    "현재 운영 중인 학년 범위와 학생이 가능한 시간을 각각 질문하세요.",
    "학교 가능 사실과 별개로 희망 학년·요일의 현재 자리를 확인하세요.",
    "수업 가능 학교 목록을 시간표 전체 가능으로 넓혀 해석하지 말고 현재 편성을 물어보세요.",
    "학년과 수업 시간은 고정 정보로 추정하지 말고 상담일 기준으로 대조하세요.",
    "희망 학년과 과목이 현재 어느 시간에 편성되는지 별도로 확인하세요.",
    "학교 범위가 맞더라도 학생 학년과 가능한 요일을 현재 상담에서 다시 점검하세요.",
    "반 편성은 달라질 수 있으므로 학년·과목·시간을 각각 나누어 확인하세요.",
    "현재 수업 가능 시간과 학년 범위를 상담 기록에 명확히 남기세요.",
    "실제 시작 전에는 학년별 가능 여부와 수업 시간을 다시 대조하세요.",
    "학교 목록과 함께 현재 학년 편성 및 상담 가능한 시간을 확인하세요.",
    "과목별 개설 여부와 학생 학년의 가능한 시간을 한 번 더 물어보세요.",
    "재학 학교가 확인돼도 모든 학년·시간이 열린다는 뜻은 아니므로 현재 조건을 확인하세요.",
)

MISSING_STATE_TEMPLATES = (
    "{locality} {category}에 연결된 공통 원자료의 {level_label} 타깃학교 칸에는 학교명이 기재되어 있지 않습니다.",
    "공통 원자료를 확인한 결과 {locality}의 {level_label} 목록은 현재 미기재 상태입니다.",
    "{locality} {service} 페이지의 원자료에는 특정 {level_label} 이름이 별도로 적혀 있지 않습니다.",
    "{locality}에 적용되는 공통 원자료에서 {level_label} 타깃학교 항목은 빈칸으로 확인됩니다.",
    "원자료상 {locality} {category}의 {level_label} 이름 목록은 제공되지 않았습니다.",
    "{locality}의 {level_label} 실제 수업 가능 학교는 공통 원자료 칸에 개별 학교명으로 기재되지 않았습니다.",
    "학교 단위로 {locality} {service} 범위를 확인했지만 원자료의 {level_label} 목록에는 이름이 없습니다.",
    "{locality} 페이지와 연결된 {level_label} 타깃학교 원자료는 학교명 미기재 상태입니다.",
    "학교 원자료의 {locality} 행에서 {level_label} 칸은 특정 학교명을 제시하지 않습니다.",
    "{locality} {category}의 {level_label} 실제 학교 목록은 이번 원자료에 따로 기록되지 않았습니다.",
    "{locality}에서 {service} 학교 범위를 대조할 원자료의 {level_label} 항목은 비어 있습니다.",
    "원자료의 {locality} {level_label} 타깃학교 셀에는 확인 가능한 개별 학교명이 없습니다.",
    "{locality} {category}에 사용할 {level_label} 이름은 공통 원자료에서 미기재로 확인됩니다.",
    "공통 원자료 기준 {locality}의 {level_label} 수업 가능 학교명은 별도 목록으로 제공되지 않았습니다.",
    "{locality} {service} 상담과 연결할 {level_label} 이름은 원자료에 적혀 있지 않습니다.",
    "{locality}의 {level_label} 타깃학교 항목을 확인했으나 공통 원자료에는 개별 학교명이 없습니다.",
)

MISSING_GUIDANCE_TEMPLATES = (
    "원자료의 학교 칸이 비어 있어 재학 정보를 직접 알려야 합니다.",
    "학교 이름이 없는 원자료 상태는 가능 여부를 단정하지 않습니다.",
    "기재된 이름이 없으므로 학생 정보를 바탕으로 문의해야 합니다.",
    "빈 칸만으로 실제 수업 조건을 판단하지 않습니다.",
    "특정 학교를 임의로 보태지 않고 학생 정보를 먼저 전해야 합니다.",
    "이 상태는 수업 불가를 뜻하지 않으므로 학교를 추정해 넣지 않고, 재학 학교와 학년을 상담에서 직접 확인합니다.",
    "원자료 미기재를 불가로 해석하지 않으며, 특정 학교를 임의로 추가하지 않고 현재 학교·학년부터 문의합니다.",
    "학교명이 없다는 이유로 가능 여부를 단정하지 말고, 학생의 재학 학교와 희망 수업을 상담에서 대조하세요.",
    "목록 밖 학교를 임의 생성하지 않았으며, 실제 가능 여부는 학교명·학년·희망 시간을 전해 확인해야 합니다.",
    "미기재 상태만으로 수업 여부를 판단할 수 없으므로 재학 학교를 밝히고 현재 편성을 문의하세요.",
    "특정 학교명을 추정하는 대신 상담 시 학교와 학년을 정확히 전달해 실제 가능 범위를 확인하세요.",
    "빈 원자료 칸은 불가 표시가 아니며, 학교명·학년·문의 과목을 기준으로 현재 수업 여부를 확인합니다.",
    "학교 목록을 만들어 채우지 않았으므로 재학 학교 정보를 상담 담당자와 직접 대조해야 합니다.",
    "원자료에 없는 학교를 가능하다고 단정하지 않고, 학생 학교와 현재 학년을 먼저 확인하는 것이 안전합니다.",
    "학교명 미기재와 수업 불가는 같은 뜻이 아니므로 실제 학교 정보를 알려 주고 현재 조건을 문의하세요.",
    "임의 학교를 보충하지 않은 상태이며, 학교·학년·희망 과목의 최신 가능 여부는 상담에서 확인합니다.",
    "목록이 비어 있어도 가능성을 배제하지 말고 재학 학교와 가능한 시간을 함께 전해 확인하세요.",
    "원자료 범위를 넘어 학교를 제시하지 않으며, 실제 학생 정보를 바탕으로 상담에서 가능 여부를 대조합니다.",
    "학교명을 추측하지 않은 대신 재학 학교와 학년을 정확히 준비해 최신 편성을 확인하도록 안내합니다.",
    "미기재 학교 범위는 상담 확인 대상으로 남기고, 특정 학교가 가능하다는 문구를 임의로 만들지 않습니다.",
    "현재 목록이 없으므로 학생의 학교·학년을 기준으로 상담 답변을 받아 수업 가능 여부를 확인하세요.",
)

COVERAGE_STATE_TEMPLATES = (
    "{locality}의 {level_label} 수업 가능 범위는 원자료에 ‘{coverage}’으로 기재되어 있으며, 실제 수업 가능 학교 범위를 뜻합니다.",
    "공통 원자료는 {locality} {level_label} 항목을 ‘{coverage}’으로 명시해 실제 학교 수업 가능 범위를 제시합니다.",
    "{locality} {category}에 적용되는 {level_label} 원자료 상태는 ‘{coverage}’이며, 수업 가능 학교 범위에 관한 사실입니다.",
    "원자료 기준 {locality}의 {level_label} 실제 수업 가능 범위는 ‘{coverage}’으로 확인됩니다.",
    "{locality} {service} 상담에 연결된 {level_label} 범위는 원자료의 ‘{coverage}’ 문구로 확인합니다.",
    "{locality}의 {level_label} 타깃학교 칸에는 개별 학교명 대신 ‘{coverage}’이라는 실제 수업 가능 범위가 적혀 있습니다.",
    "학교별 이름을 열거하지 않은 {locality} {level_label} 원자료는 ‘{coverage}’으로 가능 범위를 명시합니다.",
    "{locality} {category}의 {level_label} 근거는 원자료상 ‘{coverage}’으로, 실제 수업 가능 상태를 나타냅니다.",
    "학교 원자료의 {locality} 행은 {level_label} 실제 수업 가능 학교를 ‘{coverage}’ 범위로 제시합니다.",
    "{locality}에서 {service} 수업 가능 학교를 확인하면 {level_label} 항목은 ‘{coverage}’으로 기록되어 있습니다.",
    "원자료가 제시한 {locality} {level_label} 수업 가능 상태는 ‘{coverage}’입니다.",
    "{locality}의 {level_label} 범위에는 원자료의 ‘{coverage}’ 수업 가능 표시가 적용됩니다.",
)

COVERAGE_GUIDANCE_TEMPLATES = (
    "이 범위는 모든 학년·시간·과목이 동시에 편성된다는 뜻이 아니므로 학생의 학교와 학년, 희망 수업을 상담에서 각각 확인하세요.",
    "학교 범위가 넓더라도 현재 반 편성 전체를 보장하지 않으므로 학년·과목·시간을 나누어 문의하세요.",
    "개별 학교 칩을 임의 생성하지 않았으며, 실제 시작 전에는 학교·학년·희망 시간을 현재 상담과 대조해야 합니다.",
    "원자료 범위와 별개로 학년별 개설 및 가능한 시간은 달라질 수 있으니 상담 시점에 다시 확인하세요.",
    "학교 가능 사실을 모든 조건의 보장으로 넓히지 말고 학생 학년과 문의 과목의 현재 편성을 확인하세요.",
    "개별 학교명 목록이 아니라 범위 상태이므로 재학 학교를 알려 주고 현재 학년·시간 가능 여부를 물어보세요.",
    "실제 수업 가능 학교 범위는 확인됐지만 희망 학년과 시간의 최신 자리는 별도 상담이 필요합니다.",
    "이 문구만으로 과목별 시간표를 단정할 수 없으므로 학생 학교·학년·희망 과목을 함께 전달하세요.",
    "수업 가능 학교 범위와 현재 개설 반은 다른 정보이므로 상담일 기준 편성을 다시 맞추세요.",
    "모든 학교 범위 표시는 실제 가능 학교를 뜻하지만 모든 학년·시간의 동시 개설까지 뜻하지는 않습니다.",
    "학교명 대신 범위가 제공된 경우에도 실제 학생의 학년과 가능한 요일은 최신 상담에서 확인해야 합니다.",
    "범위 표시를 학교별 시험·교재 정보로 확대하지 않고, 현재 수업 조건만 상담에서 대조합니다.",
)

CLOSING_TEMPLATES = (
    "{locality} 상담에서는 학교 가능 사실을 출발점으로 삼고, 학생의 학년·희망 과목·가능 시간을 차례로 확인하세요.",
    "{locality}의 학교 목록을 확인한 다음에는 현재 학년과 원하는 수업 시간을 상담 메모에 따로 남기세요.",
    "{locality} {category} 문의 시 학교명만 전달하지 말고 학년과 희망 과목, 가능한 요일도 함께 준비하세요.",
    "{locality} 실제 수업 가능 학교 정보는 상담 시작점이며, 최종 편성은 학년·과목·시간 확인으로 마무리합니다.",
    "{locality}에서 수업을 문의할 때 학교 범위와 현재 반 편성을 구분해 확인하면 오해를 줄일 수 있습니다.",
    "{locality} 학교 정보에 학생 학년과 현재 학습 상황을 더해 전달하면 상담 범위를 정확히 맞추기 쉽습니다.",
    "{locality} {service} 상담은 학교 확인 뒤 학년·시간 순서로 질문해 현재 가능한 조건을 정리하세요.",
    "{locality}의 실제 가능 학교 근거와 학생의 희망 조건을 나누어 기록한 뒤 상담 답변을 대조하세요.",
    "{locality} 페이지의 학교 정보는 사실 범위만 사용하고, 시간표와 학년 편성은 최신 상담으로 확인합니다.",
    "{locality}에서 등록을 검토한다면 학교·학년·과목·시간을 각각 확인해 한 조건을 다른 조건으로 확대하지 마세요.",
    "{locality} 학교 범위를 본 뒤 학생이 원하는 학년과 시간의 현재 가능 여부를 별도 질문으로 남기세요.",
    "{locality} {category} 상담 전 학교명과 학년을 정확히 적고 최신 편성 답변을 함께 보관하세요.",
    "{locality}의 수업 가능 학교 목록은 문의 근거로 사용하고, 학생별 시작 조건은 상담에서 다시 맞춥니다.",
    "{locality} 실제 수업 가능 학교를 확인했더라도 구체적인 학년과 과목, 시간은 각각 대조해야 합니다.",
    "{locality} 상담 기록에는 학교 가능 여부와 현재 반 편성 답변을 서로 다른 항목으로 적어 두세요.",
    "{locality}에서 학교 정보를 활용할 때는 재학 학교 확인과 수업 시간 문의를 순서대로 진행하세요.",
    "{locality}의 학교 근거를 확인한 후 학년별 가능 범위와 희망 시간을 상담일 기준으로 점검하세요.",
    "{locality} {service} 실제 수업 가능 학교와 현재 가능한 수업 조건을 구분해 문의하는 것이 핵심입니다.",
    "{locality} 문의에서는 학교 목록을 먼저 대조하고 학생 학년과 가능한 시간을 최신 답변으로 확인하세요.",
    "{locality}의 학교 정보가 맞는지 본 뒤 희망 과목과 반 편성을 별도로 확인해 상담을 마무리하세요.",
    "{locality} 학교 범위는 원자료대로 사용하고, 학생에게 맞는 학년·시간은 상담을 통해 결정하세요.",
    "{locality} {category}의 학교 정보와 학생 개인의 수업 조건을 섞지 말고 차례로 검토하세요.",
    "{locality}에서 실제 수업을 시작하기 전 학교·학년·희망 과목·시간을 한 번 더 확인하세요.",
    "{locality}에서 안내한 수업 가능 학교를 확인한 뒤 현재 개설 조건을 별도 기록하면 상담 결과를 명확히 비교할 수 있습니다.",
)

MISSING_CLOSING_TEMPLATES = (
    "{locality}의 원자료 미기재 상태만으로 수업 여부를 판단하지 말고 재학 학교를 상담에서 전달하세요.",
    "{locality}에서는 학교명이 원자료에 없다는 사실과 현재 가능 여부를 구분해 문의하세요.",
    "{locality}의 빈 학교 항목은 불가 표시가 아니므로 학생 정보를 준비하세요.",
    "{locality} 페이지는 학교명을 추정하지 않으므로 재학 정보를 상담 기록에 남기세요.",
    "{locality}의 미기재 사실은 불가 판정과 다르므로 현재 조건을 직접 문의하세요.",
    "{locality}에서는 원자료에 없는 이름을 만들지 않고 학생의 재학 정보를 전달하세요.",
    "{locality}의 비어 있는 학교 칸은 상담 확인 대상이므로 현재 학년을 준비하세요.",
    "{locality} 문의에서는 원자료 상태와 학생이 알려 주는 재학 사실을 나누어 기록하세요.",
    "{locality}의 학교 미기재 상태를 그대로 두고 등록 조건은 최신 상담으로 점검하세요.",
    "{locality}에서는 목록 공백을 학교 불가로 바꾸지 말고 실제 조건을 확인하세요.",
)

COVERAGE_CLOSING_TEMPLATES = (
    "{locality}의 범위형 원자료는 지역 내 고교 수업 가능 상태를 뜻하므로 개별 이름을 덧붙이지 마세요.",
    "{locality}에서는 지역 단위 수업 가능 사실과 현재 편성 조건을 나누어 문의하세요.",
    "{locality}의 범위 표시는 특정 학교 목록이 아니므로 재학 정보를 상담에서 전달하세요.",
    "{locality} 페이지는 지역 내 고교 가능 범위를 유지하되 개별 이름은 추정하지 않습니다.",
    "{locality}의 원자료 문구를 학교별 보장으로 넓히지 말고 학생 조건을 확인하세요.",
    "{locality}에서는 범위 근거와 학년별 개설 상태를 서로 다른 질문으로 남기세요.",
    "{locality}의 지역 단위 학교 범위는 사실 그대로 사용하고 현재 수업 조건은 상담에서 확인하세요.",
    "{locality}의 고교 대상 범위를 개별 학생 일정과 분리해 기록하세요.",
    "{locality} 상담에서는 범위형 근거를 먼저 밝히고 희망 과목을 따로 문의하세요.",
    "{locality}의 지역 전체 문구는 시간표 보장이 아니므로 최신 편성을 확인하세요.",
)

MIXED_CLOSING_TEMPLATES = (
    "{locality}에서는 초·중·고 원자료 상태를 각각 읽고 학생 조건을 별도로 문의하세요.",
    "{locality}의 학제별 안내는 학교명과 원자료 상태를 구분해 상담하세요.",
    "{locality} 페이지는 학제마다 다른 원자료 상태를 유지하되 과목 조건은 별도로 확인하세요.",
    "{locality}의 초·중·고 학교 근거를 한 범위로 합치지 말고 학생 정보를 따로 전달하세요.",
    "{locality}에서는 학제별 사실을 먼저 살핀 뒤 현재 편성 조건을 문의하세요.",
    "{locality} 영수학원 문의에서는 학제별 근거와 학생의 희망 시간을 나누어 준비하세요.",
    "{locality}의 원자료는 학제별 상태를 보존하므로 재학 정보를 상담에서 대조하세요.",
)


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_text(value: str) -> str:
    return _sha256_bytes(value.encode("utf-8"))


def _stable_number(key: str, salt: str) -> int:
    digest = hashlib.sha256(f"{key}|{salt}".encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big")


def _choose(key: str, salt: str, values: Sequence[str]) -> str:
    return values[_stable_number(key, salt) % len(values)]


def _ending_style_for_slot(key: str, slot: int) -> tuple[str, str]:
    if not 0 <= slot < len(ENDING_STYLES):
        raise PlanError(f"페이지 종결문 slot 범위 오류: {slot}")
    offset = _stable_number(key, "school-page-ending-rotation") % len(
        ENDING_STYLES
    )
    return ENDING_STYLES[(offset + slot) % len(ENDING_STYLES)]


def _ending_phrase(family: str) -> str:
    matches = [phrase for name, phrase in ENDING_STYLES if name == family]
    if len(matches) != 1:
        raise PlanError(f"알 수 없거나 중복된 종결문 family: {family}")
    return matches[0]


def _guidance_context_order(key: str) -> tuple[str, ...]:
    offset = _stable_number(key, "school-page-guidance-context-rotation") % len(
        GUIDANCE_CONTEXTS
    )
    return GUIDANCE_CONTEXTS[offset:] + GUIDANCE_CONTEXTS[:offset]


def _compatible_atomic_ending_families(sentence: str) -> tuple[str, ...]:
    """Return only exact, reviewed subject/predicate pairs owned by the renderer."""

    return tuple(
        family
        for family, subject, predicate in ENDING_STYLE_PARTS
        if sentence.endswith(f"{subject} {predicate}")
    )


def _eol(source: str) -> str:
    if "\r\n" in source:
        return "\r\n"
    if "\n" in source:
        return "\n"
    if "\r" in source:
        return "\r"
    return os.linesep


def _decode_document(raw: bytes, path: str) -> str:
    try:
        # Deliberately do not use utf-8-sig: a BOM is part of the raw text contract.
        return raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise PlanError(f"UTF-8 문서가 아닙니다: {path}: {exc}") from exc


def _read_document(path: Path, rel: str) -> str:
    if not path.is_file():
        raise PlanError(f"필수 문서가 없습니다: {rel}")
    return _decode_document(path.read_bytes(), rel)


def _source_header(headers: Iterable[str | None], hint: str) -> str:
    matches = [
        header
        for header in headers
        if header and header.replace("\r", "").replace("\n", "").startswith("타깃학교")
        and hint in header
    ]
    if len(matches) != 1:
        raise PlanError(f"타깃학교 헤더를 하나로 찾지 못했습니다: {hint}: {matches}")
    return matches[0]


def _split_school_field(raw: str) -> tuple[tuple[str, ...], int]:
    # Never infer school boundaries from whitespace.  Only the six source
    # literals independently confirmed across twelve high-school rows are
    # corrected.
    if raw.strip() in VERIFIED_SCHOOL_SOURCE_CORRECTIONS:
        names = VERIFIED_SCHOOL_SOURCE_CORRECTIONS[raw.strip()]
        return names, len(names)
    tokens = tuple(token.strip() for token in SCHOOL_SPLIT_RE.split(raw.strip()) if token.strip())
    names = tuple(dict.fromkeys(tokens))
    return names, len(tokens)


def _parse_level(level: str, raw_value: str | None) -> LevelSource:
    raw = str(raw_value or "").strip()
    if not raw:
        return LevelSource(level, raw, "missing", (), 0)
    if raw == COVERAGE_RAW:
        if level != "high":
            raise PlanError(f"고등 외 학제에 coverage 문구가 있습니다: {level}: {raw}")
        return LevelSource(level, raw, "coverage", (), 0)
    names, raw_count = _split_school_field(raw)
    if not names:
        raise PlanError(f"학교 필드가 비어 있지 않지만 이름을 분리하지 못했습니다: {level}: {raw}")
    if any(name == COVERAGE_RAW for name in names):
        raise PlanError(f"coverage 문구와 학교명이 한 셀에 혼재합니다: {level}: {raw}")
    return LevelSource(level, raw, "provided", names, raw_count)


def _load_sources(common_dir: Path) -> tuple[dict[str, SchoolSourceRow], bytes, dict]:
    source_path = common_dir / SCHOOL_CSV_NAME
    if not source_path.is_file():
        candidates = []
        for candidate in common_dir.glob("*.csv"):
            raw = candidate.read_bytes()
            if b"\xed\x83\x80\xea\xb9\x83\xed\x95\x99\xea\xb5\x90" in raw:
                candidates.append(candidate)
        if len(candidates) != 1:
            raise PlanError(f"{SCHOOL_CSV_NAME}을 찾지 못했습니다: {common_dir}")
        source_path = candidates[0]

    source_bytes = source_path.read_bytes()
    try:
        decoded = source_bytes.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise PlanError(f"타깃학교 원자료는 UTF-8 CSV여야 합니다: {source_path}") from exc

    reader = csv.DictReader(io.StringIO(decoded, newline=""))
    if not reader.fieldnames:
        raise PlanError("타깃학교 CSV 헤더가 없습니다.")
    locality_header = next(
        (header for header in reader.fieldnames if header and "수업가능 동네" in header),
        None,
    )
    if not locality_header:
        raise PlanError("근처 수업가능 동네 헤더가 없습니다.")
    level_headers = {
        level: _source_header(reader.fieldnames, LEVEL_HEADER_HINT[level])
        for level in LEVEL_ORDER
    }

    rows: dict[str, SchoolSourceRow] = {}
    source_stats = {
        level: {
            "provided_rows": 0,
            "missing_rows": 0,
            "coverage_rows": 0,
            "raw_names": 0,
            "deduped_names": 0,
        }
        for level in LEVEL_ORDER
    }
    duplicate_cells: list[dict] = []
    special_separator_cells: list[dict] = []

    for row_number, raw_row in enumerate(reader, start=2):
        source_locality = str(raw_row.get(locality_header) or "").strip()
        if not source_locality:
            raise PlanError(f"타깃학교 CSV {row_number}행 동네가 비었습니다.")
        # Existing routes compact the 14 disambiguated source labels (for
        # example ``부천 상동`` -> ``부천상동``).  Whitespace removal is the
        # audited route mapping; it never touches school-name tokens.
        locality = re.sub(r"\s+", "", source_locality)
        if locality in rows:
            raise PlanError(f"타깃학교 CSV 동네 중복: {locality}")
        levels = {
            level: _parse_level(level, raw_row.get(level_headers[level]))
            for level in LEVEL_ORDER
        }
        for level, source in levels.items():
            source_stats[level][f"{source.state}_rows"] += 1
            source_stats[level]["raw_names"] += source.raw_name_count
            source_stats[level]["deduped_names"] += len(source.names)
            if source.raw_name_count != len(source.names):
                duplicate_cells.append(
                    {
                        "locality": locality,
                        "level": level,
                        "raw": source.raw,
                        "raw_count": source.raw_name_count,
                        "deduped_count": len(source.names),
                    }
                )
            if source.raw and re.search(r"[/.]", source.raw):
                special_separator_cells.append(
                    {"locality": locality, "level": level, "raw": source.raw}
                )
        rows[locality] = SchoolSourceRow(
            locality=locality,
            source_locality=source_locality,
            region=str(raw_row.get("지역") or "").strip(),
            district=str(raw_row.get("시or구") or "").strip(),
            center=str(raw_row.get("센터명") or "").strip(),
            levels=levels,
        )

    if len(rows) != EXPECTED_SOURCE_ROWS:
        raise PlanError(f"타깃학교 행 수 오류: {len(rows)} != {EXPECTED_SOURCE_ROWS}")
    if source_stats != EXPECTED_LEVEL_STATS:
        raise PlanError(
            "타깃학교 원자료 cardinality가 release gate와 다릅니다: "
            + json.dumps(source_stats, ensure_ascii=False, sort_keys=True)
        )
    return rows, source_bytes, {
        "path": str(source_path),
        "rows": len(rows),
        "levels": source_stats,
        "duplicate_cells": duplicate_cells,
        "special_separator_cells": special_separator_cells,
    }


def _relative_target_paths(root: Path) -> tuple[str, ...]:
    paths: list[str] = []
    subject_root = root / SUBJECT_ROOT_NAME
    for config in CATEGORIES:
        category_root = subject_root / config.directory
        if not category_root.is_dir():
            raise PlanError(f"카테고리 폴더가 없습니다: {category_root}")
        category_paths = sorted(
            (
                path.relative_to(root).as_posix()
                for path in category_root.glob("*/index.html")
                if path.is_file()
            ),
            key=lambda value: value.encode("utf-8"),
        )
        if len(category_paths) != EXPECTED_SOURCE_ROWS:
            raise PlanError(
                f"{config.directory} 상세 페이지 수 오류: "
                f"{len(category_paths)} != {EXPECTED_SOURCE_ROWS}"
            )
        paths.extend(category_paths)
    if len(paths) != EXPECTED_PAGE_COUNT or len(set(paths)) != len(paths):
        raise PlanError(f"대상 페이지 cardinality 오류: {len(paths)}")
    return tuple(paths)


def _normalize_override_key(root: Path, key: str | Path) -> str:
    raw = str(key)
    candidate = Path(raw)
    if candidate.is_absolute():
        try:
            rel = candidate.resolve().relative_to(root.resolve())
        except ValueError as exc:
            raise PlanError(f"override가 root 밖을 가리킵니다: {key}") from exc
        return rel.as_posix()
    # Accept POSIX and Windows relative keys regardless of the caller platform.
    normalized = PurePosixPath(raw.replace("\\", "/"))
    if normalized.is_absolute() or ".." in normalized.parts:
        raise PlanError(f"안전하지 않은 override key: {key}")
    return normalized.as_posix()


def _prepare_overrides(
    root: Path,
    current_overrides: Mapping[str | Path, str | bytes] | None,
    authorized: set[str],
) -> dict[str, str]:
    prepared: dict[str, str] = {}
    if not current_overrides:
        return prepared
    for key, value in current_overrides.items():
        rel = _normalize_override_key(root, key)
        if rel not in authorized:
            raise PlanError(f"대상 문서가 아닌 override는 허용하지 않습니다: {rel}")
        if rel in prepared:
            raise PlanError(f"override key가 중복됩니다: {rel}")
        if isinstance(value, bytes):
            prepared[rel] = _decode_document(value, rel)
        elif isinstance(value, str):
            prepared[rel] = value
        else:
            raise PlanError(f"override value는 str/bytes여야 합니다: {rel}")
    return prepared


def _canonical(source: str, rel: str) -> str:
    matches = CANONICAL_RE.findall(source)
    if len(matches) != 1:
        raise PlanError(f"canonical이 정확히 1개가 아닙니다: {rel}: {len(matches)}")
    return html.unescape(matches[0])


def _json_document(source: str, rel: str) -> tuple[re.Match[str], dict]:
    matches = list(JSON_RE.finditer(source))
    if len(matches) != 1:
        raise PlanError(f"JSON-LD script가 정확히 1개가 아닙니다: {rel}: {len(matches)}")
    try:
        parsed = json.loads(matches[0].group(2))
    except json.JSONDecodeError as exc:
        raise PlanError(f"JSON-LD parse 오류: {rel}: {exc}") from exc
    if not isinstance(parsed, dict) or not isinstance(parsed.get("@graph"), list):
        raise PlanError(f"JSON-LD @graph 형식 오류: {rel}")
    return matches[0], parsed


def _schema_types(node: Mapping) -> set[str]:
    value = node.get("@type", [])
    if isinstance(value, str):
        return {value}
    if isinstance(value, list):
        return {item for item in value if isinstance(item, str)}
    return set()


def _graph_nodes(document: Mapping, expected_type: str) -> list[dict]:
    return [
        node
        for node in document.get("@graph", [])
        if isinstance(node, dict) and expected_type in _schema_types(node)
    ]


def _is_school_organization(value: object) -> bool:
    return (
        isinstance(value, dict)
        and "EducationalOrganization" in _schema_types(value)
        and not value.get("@id")
        and isinstance(value.get("name"), str)
    )


def _fix_natural_school_string(value: str, mode: str) -> str:
    if mode == "high":
        return re.sub(r"(?<!창원중)앙여고", "창원중앙여고", value)
    if mode == "middle":
        value = value.replace("·창원중", "").replace("창원중·", "")
        return value
    if mode == "yeongsu":
        return value.replace("창원중·앙여고", "창원중앙여고")
    return value


def _correct_schema_value(value: object, mode: str) -> object:
    if isinstance(value, str):
        return _fix_natural_school_string(value, mode)
    if isinstance(value, dict):
        return {key: _correct_schema_value(item, mode) for key, item in value.items()}
    if not isinstance(value, list):
        return value

    source = list(value)
    output: list[object] = []
    index = 0
    while index < len(source):
        item = source[index]
        name = item.get("name") if isinstance(item, dict) else None
        if mode == "middle" and name == "창원중" and (
            _is_school_organization(item) or "ListItem" in _schema_types(item)
        ):
            index += 1
            continue
        if mode == "yeongsu" and name == "창원중" and index + 1 < len(source):
            next_item = source[index + 1]
            next_name = next_item.get("name") if isinstance(next_item, dict) else None
            if next_name == "앙여고" and isinstance(item, dict) and isinstance(next_item, dict):
                merged = copy.deepcopy(item)
                merged["name"] = "창원중앙여고"
                if isinstance(merged.get("item"), dict):
                    merged["item"]["name"] = "창원중앙여고"
                output.append(_correct_schema_value(merged, mode))
                index += 2
                continue
        output.append(_correct_schema_value(item, mode))
        index += 1

    # Positions/counts in a soon-to-be-reconciled legacy school ItemList should
    # still remain internally sane during the structured correction.
    if output and all(isinstance(item, dict) and "ListItem" in _schema_types(item) for item in output):
        for position, item in enumerate(output, 1):
            item["position"] = position
    return output


CORRECTION_LOCALITIES = frozenset(("상남동", "신월동", "사파동"))


def _correction_mode(config: CategoryConfig, locality: str) -> str:
    if locality not in CORRECTION_LOCALITIES:
        return ""
    if config.directory in {"고등수학학원", "고등영어학원"}:
        return "high"
    if config.directory in {"중등수학학원", "중등영어학원"}:
        return "middle"
    if config.directory == "영수학원":
        return "yeongsu"
    return ""


def _correct_visible_non_json(source: str, mode: str) -> str:
    if not mode:
        return source
    match = JSON_RE.search(source)
    if not match:
        return source
    before, script, after = source[: match.start()], source[match.start() : match.end()], source[match.end() :]
    visible = before + "\0JSONLD\0" + after
    if mode == "high":
        visible = re.sub(r"(?<!창원중)앙여고", "창원중앙여고", visible)
    elif mode == "middle":
        visible = visible.replace("·창원중", "").replace("창원중·", "")
        visible = visible.replace("<span>창원중</span>", "")
    elif mode == "yeongsu":
        visible = visible.replace("창원중·앙여고", "창원중앙여고")
        visible = visible.replace(
            "<span>창원중</span><span>앙여고</span>",
            "<span>창원중앙여고</span>",
        )
    return visible.replace("\0JSONLD\0", script, 1)


def _correct_schema(document: dict, mode: str) -> dict:
    if not mode:
        return document
    corrected = _correct_schema_value(document, mode)
    if not isinstance(corrected, dict):
        raise AssertionError("corrected schema must remain a dict")
    return corrected


def _school_names_for_levels(row: SchoolSourceRow, levels: Sequence[str]) -> tuple[str, ...]:
    values: list[str] = []
    for level in levels:
        values.extend(row.levels[level].names)
    return tuple(dict.fromkeys(values))


def _school_mentions(row: SchoolSourceRow, levels: Sequence[str]) -> list[dict]:
    return [
        {"@type": "EducationalOrganization", "name": name}
        for name in _school_names_for_levels(row, levels)
    ]


def _replace_school_mentions(node: dict, new_school_mentions: Sequence[dict]) -> None:
    existing = node.get("mentions", [])
    if existing is None:
        existing = []
    if not isinstance(existing, list):
        existing = [existing]
    kept = [
        item
        for item in existing
        if not _is_school_organization(item)
        and not (isinstance(item, dict) and item.get("name") == COVERAGE_RAW)
    ]
    node["mentions"] = kept + copy.deepcopy(list(new_school_mentions))


def _owned_schema_id(value: object, canonical: str) -> bool:
    if not isinstance(value, str):
        return False
    return value in {
        canonical + "#schools",
        canonical + "#service-schools",
        canonical + "#school-reference",
        *(canonical + f"#school-reference-{level}" for level in LEVEL_ORDER),
    } or value.endswith("#schools")


def _heading_signature(value: str) -> frozenset[str]:
    return frozenset(
        family
        for family, pattern in HEADING_SEMANTIC_PATTERNS.items()
        if pattern.search(value)
    )


def _heading_natural_signature(value: str) -> frozenset[str]:
    signature = set(_heading_signature(value))
    signature.update(
        family
        for family, pattern in HEADING_NATURALNESS_EXTRA_PATTERNS.items()
        if pattern.search(value)
    )
    return frozenset(signature)


def _heading_semantic_collision(start: str, end: str) -> bool:
    """Reject equivalent A/B steps in ``A부터 B까지`` headings."""

    start_signature = _heading_signature(start)
    end_signature = _heading_signature(end)
    shared = start_signature & end_signature
    union = start_signature | end_signature
    if start_signature == end_signature:
        return True
    return bool(
        shared & HEADING_ACTION_FAMILIES
        and len(shared) >= 2
        and union
        and len(shared) / len(union) >= 0.75
    )


def _heading_subject(states: set[str]) -> str:
    if states == {"missing"}:
        return "원자료상 학교 목록 미기재 상태"
    if states == {"coverage"}:
        return "원자료상 지역 내 고등학교 수업 가능 범위"
    if "missing" in states or "coverage" in states:
        return "학제별 학교 원자료 상태"
    return "실제 수업 가능 학교"


@functools.lru_cache(maxsize=None)
def _valid_heading_combinations(subject: str) -> tuple[tuple[str, str, str], ...]:
    subject_signature = _heading_natural_signature(subject)
    combinations: list[tuple[str, str, str]] = []
    for focus in HEADING_FOCUSES:
        focus_signature = _heading_natural_signature(focus)
        if subject_signature & focus_signature:
            continue
        for start in HEADING_STARTS:
            start_signature = _heading_natural_signature(start)
            if start_signature & (subject_signature | focus_signature):
                continue
            for end in HEADING_ENDS:
                end_signature = _heading_natural_signature(end)
                if end_signature & (
                    subject_signature | focus_signature | start_signature
                ):
                    continue
                if _heading_semantic_collision(start, end):
                    continue
                combinations.append((focus, start, end))
    if not combinations:
        raise PlanError(f"의미 family가 겹치지 않는 H2 조합이 없습니다: {subject}")
    return tuple(combinations)


def _choose_heading_parts(key: str, subject: str) -> tuple[str, str, str]:
    return _choose(
        key,
        f"school-heading-combination-{subject}",
        _valid_heading_combinations(subject),
    )


def _heading(config: CategoryConfig, row: SchoolSourceRow) -> str:
    locality = row.locality
    key = f"{config.directory}|{locality}"
    states = {row.levels[level].state for level in config.levels}
    subject = _heading_subject(states)
    focus, start, end = _choose_heading_parts(key, subject)
    return (
        f"{locality} {config.label} {subject}와 {focus}: "
        f"{start}부터 {end}까지"
    )


def _state_with_boundary(
    state: str,
    key: str,
    level: str,
    source_state: str,
    used_stems: set[str],
) -> tuple[str, str]:
    """Return the source fact and a separately attributable authored sentence."""

    ending_family, _ = _ending_style_for_slot(key, STATE_ENDING_SLOT[level])
    candidates = _state_sentence_candidates(level, source_state, ending_family)
    available = [
        sentence
        for sentence in candidates
        if _state_sentence_stem(sentence, level, ending_family) not in used_stems
    ]
    if not available:
        raise PlanError(f"페이지 내부 고유 state stem 후보가 없습니다: {key}/{level}")
    authored = _choose(
        key,
        f"{source_state}-natural-state-{level}-{ending_family}",
        available,
    )
    used_stems.add(_state_sentence_stem(authored, level, ending_family))
    return state, authored


def _state_sentence_stem(
    sentence: str, level: str, ending_family: str
) -> str:
    prefix = f"{LEVEL_STAGE_PHRASE[level]} 상담에서는 "
    ending = _ending_phrase(ending_family)
    if not sentence.startswith(prefix) or not sentence.endswith(ending):
        raise PlanError(f"state 작성 문장 소유 경계 오류: {sentence}")
    return sentence[len(prefix) : -len(ending)].strip()


def _as_connective(sentence: str) -> str:
    """Convert the finite ending of an authored sentence to a natural clause."""

    value = sentence.rstrip().rstrip(".")
    replacements = (
        ("대조해야 합니다", "대조한 뒤"),
        ("확인해야 합니다", "확인한 뒤"),
        ("뜻하지는 않습니다", "뜻하지 않으므로"),
        ("뜻하지 않습니다", "뜻하지 않으므로"),
        ("마무리하세요", "마무리한 뒤"),
        ("결정하세요", "결정한 뒤"),
        ("검토하세요", "검토한 뒤"),
        ("점검하세요", "점검한 뒤"),
        ("진행하세요", "진행하고"),
        ("상담하세요", "상담하고"),
        ("기록하세요", "기록하고"),
        ("구분하세요", "구분하고"),
        ("보관하세요", "보관하고"),
        ("준비하세요", "준비하고"),
        ("정리하세요", "정리하고"),
        ("문의하세요", "문의하고"),
        ("물어보세요", "물어보고"),
        ("전달하세요", "전달하고"),
        ("맞추세요", "맞춘 뒤"),
        ("확인하세요", "확인하고"),
        ("대조하세요", "대조하고"),
        ("남기세요", "남기고"),
        ("두세요", "두고"),
        ("마세요", "말고"),
        ("쉽습니다", "쉬우며"),
        ("안전합니다", "안전하므로"),
        ("필요합니다", "필요하므로"),
        ("핵심입니다", "핵심이므로"),
        ("않습니다", "않고"),
        ("있습니다", "있고"),
        ("맞춥니다", "맞춘 뒤"),
        ("합니다", "하며"),
    )
    for ending, replacement in replacements:
        if value.endswith(ending):
            return value[: -len(ending)] + replacement
    raise PlanError(f"연결형으로 바꿀 수 없는 작성 문장입니다: {sentence}")


def _authored_repeat_counts(sentence: str) -> dict[str, int]:
    return {
        family: count
        for family, pattern in AUTHORED_REPEAT_PATTERNS.items()
        if (count := len(pattern.findall(sentence))) > 1
    }


def _natural_sentence_pool(
    label: str,
    candidates: Iterable[str],
    *,
    allow_empty: bool = False,
) -> tuple[str, ...]:
    kept = tuple(
        sentence for sentence in candidates if not _authored_repeat_counts(sentence)
    )
    if not kept and not allow_empty:
        raise PlanError(f"반복 없는 작성 문장 후보가 없습니다: {label}")
    if len(kept) != len(set(kept)):
        raise PlanError(f"작성 문장 후보 자체가 중복됩니다: {label}")
    return kept


@functools.lru_cache(maxsize=None)
def _state_sentence_candidates(
    level: str, source_state: str, ending_family: str
) -> tuple[str, ...]:
    if level not in LEVEL_STAGE_PHRASE:
        raise PlanError(f"알 수 없는 학제 작성 문장 요청: {level}")
    if source_state not in {"provided", "missing", "coverage"}:
        raise PlanError(f"알 수 없는 학교 원자료 상태: {source_state}")
    stage = LEVEL_STAGE_PHRASE[level]
    ending = _ending_phrase(ending_family)

    def compatible_pairs() -> Iterable[tuple[str, str]]:
        source_compare_actions = {"원자료와 맞춘 뒤", "가능 학교와 대조하고"}
        for subject in STATE_SUBJECTS:
            for action in STATE_ACTIONS:
                if action in source_compare_actions and not (
                    source_state == "provided" and subject == "재학 학교를"
                ):
                    continue
                if action == "학교 범위와 함께 살피고" and source_state == "missing":
                    continue
                yield subject, action

    return _natural_sentence_pool(
        f"state-{source_state}-{level}-{ending_family}",
        (
            f"{stage} 상담에서는 {subject} {action} {ending}"
            for subject, action in compatible_pairs()
        ),
    )


@functools.lru_cache(maxsize=None)
def _guidance_sentence_candidates(
    state: str,
    level: str,
    ending_family: str,
    selected_context: str | None = None,
) -> tuple[str, ...]:
    if level not in LEVEL_SHORT:
        raise PlanError(f"알 수 없는 guidance level: {level}")
    if state == "provided":
        leads: Sequence[str] = PROVIDED_GUIDANCE_LEADS
        connective = False
    elif state == "missing":
        leads = MISSING_GUIDANCE_TEMPLATES
        connective = True
    elif state == "coverage":
        leads = COVERAGE_GUIDANCE_TEMPLATES
        connective = True
    else:
        raise PlanError(f"알 수 없는 guidance state: {state}")
    ending = _ending_phrase(ending_family)
    if selected_context is not None and selected_context not in GUIDANCE_CONTEXTS:
        raise PlanError(f"알 수 없는 guidance context: {selected_context}")
    contexts = (
        (selected_context,) if selected_context is not None else GUIDANCE_CONTEXTS
    )

    def sentences() -> Iterable[str]:
        for lead in leads:
            opening = _as_connective(lead) + "," if connective else lead
            for context in contexts:
                yield (
                    f"{LEVEL_SHORT[level]} 단계 기준으로 {opening} "
                    f"{context} {ending}"
                )

    return _natural_sentence_pool(
        f"guidance-{state}-{level}-{ending_family}",
        sentences(),
        allow_empty=selected_context is not None,
    )


def _guidance_lead_signature(
    sentence: str,
    level: str,
    selected_context: str,
    ending_family: str,
) -> str:
    prefix = f"{LEVEL_SHORT[level]} 단계 기준으로 "
    suffix = f" {selected_context} {_ending_phrase(ending_family)}"
    if not sentence.startswith(prefix) or not sentence.endswith(suffix):
        raise PlanError(f"guidance 작성 문장 소유 경계 오류: {sentence}")
    return sentence[len(prefix) : -len(suffix)].strip()


@functools.lru_cache(maxsize=None)
def _closing_sentence_candidates(
    category_directory: str,
    source_scope: str,
    ending_family: str,
    selected_context: str | None = None,
) -> tuple[str, ...]:
    config = CATEGORY_BY_DIR.get(category_directory)
    if not config:
        raise PlanError(f"알 수 없는 closing category: {category_directory}")
    templates_by_scope = {
        "provided": CLOSING_TEMPLATES,
        "missing": MISSING_CLOSING_TEMPLATES,
        "coverage": COVERAGE_CLOSING_TEMPLATES,
        "mixed": MIXED_CLOSING_TEMPLATES,
    }
    templates = templates_by_scope.get(source_scope)
    if templates is None:
        raise PlanError(f"알 수 없는 closing source scope: {source_scope}")
    ending = _ending_phrase(ending_family)
    if selected_context is not None and selected_context not in GUIDANCE_CONTEXTS:
        raise PlanError(f"알 수 없는 closing context: {selected_context}")
    contexts = (
        (selected_context,) if selected_context is not None else GUIDANCE_CONTEXTS
    )

    def sentences() -> Iterable[str]:
        for template in templates:
            opening = _as_connective(
                template.format(
                    locality="{locality}",
                    category=config.label,
                    service=config.service,
                )
            )
            for context in contexts:
                yield f"{opening}, 마지막에는 {context} {ending}"

    return _natural_sentence_pool(
        f"closing-{category_directory}-{source_scope}-{ending_family}",
        sentences(),
        allow_empty=selected_context is not None,
    )


def _source_scope_from_states(states: set[str]) -> str:
    if states == {"provided"}:
        return "provided"
    if states == {"missing"}:
        return "missing"
    if states == {"coverage"}:
        return "coverage"
    return "mixed"


def _page_source_scope(config: CategoryConfig, row: SchoolSourceRow) -> str:
    return _source_scope_from_states(
        {row.levels[level].state for level in config.levels}
    )


def _rotated_candidates(
    key: str, salt: str, values: Sequence[str]
) -> tuple[str, ...]:
    if not values:
        return ()
    start = _stable_number(key, salt) % len(values)
    return tuple(values[start:]) + tuple(values[:start])


def _page_guidance_plan(
    key: str,
    config: CategoryConfig,
    state_by_level: Mapping[str, str],
) -> tuple[dict[str, str], dict[str, str], str]:
    """Jointly choose unique contexts and visible guidance leads for a page."""

    if set(state_by_level) != set(config.levels):
        raise PlanError(f"페이지 학제/context 상태 불일치: {config.directory}")
    order = _guidance_context_order(key)
    closing_family, _ = _ending_style_for_slot(key, CLOSING_ENDING_SLOT)
    source_scope = _source_scope_from_states(set(state_by_level.values()))

    def search(
        index: int,
        used_contexts: set[str],
        used_leads: set[str],
    ) -> tuple[dict[str, str], dict[str, str], str] | None:
        if index == len(config.levels):
            for context in order:
                if context in used_contexts:
                    continue
                if _closing_sentence_candidates(
                    config.directory,
                    source_scope,
                    closing_family,
                    context,
                ):
                    return {}, {}, context
            return None

        level = config.levels[index]
        state = state_by_level[level]
        ending_family, _ = _ending_style_for_slot(
            key, GUIDANCE_ENDING_SLOT[level]
        )
        for context in order:
            if context in used_contexts:
                continue
            candidates = _guidance_sentence_candidates(
                state, level, ending_family, context
            )
            ordered_candidates = _rotated_candidates(
                key,
                f"page-guidance-plan-{level}-{state}-{ending_family}-{context}",
                candidates,
            )
            seen_leads: set[str] = set()
            for sentence in ordered_candidates:
                lead = _guidance_lead_signature(
                    sentence, level, context, ending_family
                )
                if lead in used_leads or lead in seen_leads:
                    continue
                seen_leads.add(lead)
                remainder = search(
                    index + 1,
                    used_contexts | {context},
                    used_leads | {lead},
                )
                if remainder is None:
                    continue
                contexts, sentences, closing_context = remainder
                return (
                    {level: context, **contexts},
                    {level: sentence, **sentences},
                    closing_context,
                )
        return None

    result = search(0, set(), set())
    if result is None:
        raise PlanError(f"페이지 guidance/context 공동 후보가 없습니다: {key}")
    return result


def _state_description(config: CategoryConfig, row: SchoolSourceRow) -> str:
    chunks: list[str] = []
    for level in config.levels:
        source = row.levels[level]
        if source.state == "provided":
            chunks.append(
                f"{LEVEL_SHORT[level]} 실제 수업 가능 학교 {len(source.names)}곳이 원자료에 기재되어 있습니다."
            )
        elif source.state == "coverage":
            chunks.append(
                f"{LEVEL_SHORT[level]} 원자료 상태는 ‘{COVERAGE_RAW}’입니다."
            )
        else:
            chunks.append(
                f"{LEVEL_SHORT[level]} 타깃학교 이름은 원자료에 미기재되어 있습니다."
            )
    return " ".join(chunks)


def _visible_source_note(config: CategoryConfig, row: SchoolSourceRow) -> str:
    states = {row.levels[level].state for level in config.levels}
    if states == {"provided"}:
        return "공통 타깃학교 원자료에 실제 수업 가능으로 기재된 학교만 사용했습니다."
    if states == {"missing"}:
        return "공통 원자료에 학교명이 미기재된 상태를 그대로 표시하고 임의 학교를 추가하지 않았습니다."
    if states == {"coverage"}:
        return "공통 원자료의 실제 수업 가능 범위 문구를 그대로 안내하며 개별 학교명은 임의 생성하지 않았습니다."
    labels: list[str] = []
    if "provided" in states:
        labels.append("실제 수업 가능 학교명")
    if "missing" in states:
        labels.append("학교명 미기재 상태")
    if "coverage" in states:
        labels.append("지역 단위 가능 범위")
    return (
        "학제별 원자료의 " + "·".join(labels) + " 항목을 서로 구분해 표시했습니다."
    )


def _schema_item_list(canonical: str, row: SchoolSourceRow, level: str) -> dict:
    source = row.levels[level]
    if source.state != "provided" or not source.names:
        raise AssertionError("ItemList is only valid for named, provided source groups")
    return {
        "@type": "ItemList",
        "@id": canonical + f"#school-reference-{level}",
        "name": f"{LEVEL_LABEL[level]} 실제 수업 가능 학교",
        "description": (
            f"공통 타깃학교 원자료에 실제 수업 가능으로 기재된 "
            f"{row.locality} {LEVEL_LABEL[level]} 목록입니다."
        ),
        "numberOfItems": len(source.names),
        "itemListElement": [
            {
                "@type": "ListItem",
                "position": position,
                "name": name,
            }
            for position, name in enumerate(source.names, 1)
        ],
        "additionalProperty": {
            "@type": "PropertyValue",
            "name": "schoolLevel",
            "value": level,
        },
    }


def _schema_webpage_element(
    canonical: str,
    webpage_id: str,
    config: CategoryConfig,
    row: SchoolSourceRow,
    heading: str,
) -> dict:
    properties: list[dict] = []
    child_lists: list[dict] = []
    for level in config.levels:
        source = row.levels[level]
        prop: dict = {
            "@type": "PropertyValue",
            "name": f"{level}SourceState",
            "value": source.state,
        }
        if source.state == "provided":
            prop["description"] = f"실제 수업 가능 학교 {len(source.names)}곳"
            child_lists.append({"@id": canonical + f"#school-reference-{level}"})
        elif source.state == "coverage":
            prop["description"] = COVERAGE_RAW
        else:
            prop["description"] = "타깃학교 원자료 목록 미기재"
        properties.append(prop)
    node: dict = {
        "@type": "WebPageElement",
        "@id": canonical + "#school-reference",
        "name": heading,
        "url": canonical + "#school-reference",
        "description": _state_description(config, row),
        "isPartOf": {"@id": webpage_id},
        "additionalProperty": properties,
    }
    if child_lists:
        node["hasPart"] = child_lists
    return node


def _replace_owned_has_part(node: dict, element_id: str) -> None:
    existing = node.get("hasPart", [])
    if existing is None:
        existing = []
    if not isinstance(existing, list):
        existing = [existing]
    kept = [
        item
        for item in existing
        if not (
            isinstance(item, dict)
            and isinstance(item.get("@id"), str)
            and item["@id"].endswith("#school-reference")
        )
    ]
    node["hasPart"] = kept + [{"@id": element_id}]


def _transform_schema(
    document: dict,
    canonical: str,
    config: CategoryConfig,
    row: SchoolSourceRow,
    heading: str,
) -> dict:
    transformed = copy.deepcopy(document)
    graph = transformed["@graph"]
    owned_section_names = {
        node.get("name")
        for node in graph
        if isinstance(node, dict)
        and _owned_schema_id(node.get("@id"), canonical)
        and node.get("@id") == canonical + "#school-reference"
        and isinstance(node.get("name"), str)
    }
    graph[:] = [
        node
        for node in graph
        if not (
            isinstance(node, dict)
            and _owned_schema_id(node.get("@id"), canonical)
        )
    ]

    webpages = _graph_nodes(transformed, "WebPage")
    articles = _graph_nodes(transformed, "Article")
    services = _graph_nodes(transformed, "Service")
    if len(webpages) != 1 or len(articles) != 1:
        raise PlanError(
            f"WebPage/Article node cardinality 오류: {canonical}: "
            f"{len(webpages)}/{len(articles)}"
        )
    webpage = webpages[0]
    article = articles[0]
    webpage_id = str(webpage.get("@id") or canonical + "#webpage")
    element_id = canonical + "#school-reference"
    mentions = _school_mentions(row, config.levels)

    for node in [webpage, article, *services]:
        _replace_school_mentions(node, mentions)
    _replace_owned_has_part(webpage, element_id)
    _replace_owned_has_part(article, element_id)

    sections = article.get("articleSection", [])
    if not isinstance(sections, list):
        sections = [sections] if sections else []
    sections = [
        section
        for section in sections
        if section not in owned_section_names
    ]
    article["articleSection"] = sections + [heading]
    # Never move a page's modification date backwards when verified school
    # references are re-applied after a newer category regeneration.
    modified_candidates = [
        str(value)
        for value in (
            RELEASE_DATE,
            webpage.get("dateModified"),
            article.get("dateModified"),
        )
        if value and re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(value))
    ]
    effective_modified = max(modified_candidates)
    webpage["dateModified"] = effective_modified
    article["dateModified"] = effective_modified

    graph.append(
        _schema_webpage_element(canonical, webpage_id, config, row, heading)
    )
    for level in config.levels:
        if row.levels[level].state == "provided":
            graph.append(_schema_item_list(canonical, row, level))
    return transformed


def _school_text(names: Sequence[str]) -> str:
    return "·".join(names)


def _render_group(
    config: CategoryConfig,
    row: SchoolSourceRow,
    level: str,
    key: str,
    guidance_sentence: str,
    used_state_stems: set[str],
    eol: str,
) -> str:
    source = row.levels[level]
    level_label = LEVEL_LABEL[level]
    class_name = f"wawa-school-card is-{level}"
    heading = f"{level_label} 실제 수업 가능 학교"
    common = {
        "locality": row.locality,
        "category": config.label,
        "service": config.service,
        "level_label": level_label,
        "coverage": COVERAGE_RAW,
    }
    lines = [
        (
            f'<section class="{class_name}" data-school-level="{level}" '
            f'data-source-state="{source.state}">'
        ),
        f"  <h3>{html.escape(heading)}</h3>",
    ]
    if source.state == "provided":
        schools = _school_text(source.names)
        template = _choose(key, f"state-{level}", PROVIDED_STATE_TEMPLATES)
        state, state_guidance = _state_with_boundary(
            template.format(**common, schools=schools),
            key,
            level,
            "provided",
            used_state_stems,
        )
        guidance = guidance_sentence
        lines.append(
            '  <p data-school-source-state>'
            f'<span data-school-source-fact>{html.escape(state)}</span> '
            f'<span data-school-authored-copy>{html.escape(state_guidance)}</span></p>'
        )
        lines.append('  <div class="wawa-pills" aria-label="실제 수업 가능 학교 목록">')
        for name in source.names:
            escaped = html.escape(name, quote=True)
            lines.append(
                f'    <span class="wawa-pill is-{level}" data-source-school="{escaped}">{escaped}</span>'
            )
        lines.append("  </div>")
        lines.append(f"  <p>{html.escape(guidance)}</p>")
    elif source.state == "coverage":
        template = _choose(key, f"coverage-state-{level}", COVERAGE_STATE_TEMPLATES)
        state, state_guidance = _state_with_boundary(
            template.format(**common),
            key,
            level,
            "coverage",
            used_state_stems,
        )
        guidance = guidance_sentence
        lines.append(
            '  <p data-school-source-state>'
            f'<span data-school-source-fact>{html.escape(state)}</span> '
            f'<span data-school-authored-copy>{html.escape(state_guidance)}</span></p>'
        )
        lines.append(f"  <p>{html.escape(guidance)}</p>")
    else:
        template = _choose(key, f"missing-state-{level}", MISSING_STATE_TEMPLATES)
        state_text = template.format(**common)
        if config.directory == "중등영어학원":
            state_text = state_text.replace("공통자료", "확인 자료")
        state, state_guidance = _state_with_boundary(
            state_text,
            key,
            level,
            "missing",
            used_state_stems,
        )
        guidance = guidance_sentence
        lines.append(
            '  <p data-school-source-state>'
            f'<span data-school-source-fact>{html.escape(state)}</span> '
            f'<span data-school-authored-copy>{html.escape(state_guidance)}</span></p>'
        )
        lines.append(f"  <p>{html.escape(guidance)}</p>")
    lines.append("</section>")
    return eol.join(lines)


def _render_school_block(
    config: CategoryConfig,
    row: SchoolSourceRow,
    heading: str,
    eol: str,
) -> str:
    key = f"{config.directory}|{row.locality}"
    guidance_contexts, guidance_sentences, closing_context = _page_guidance_plan(
        key,
        config,
        {level: row.levels[level].state for level in config.levels},
    )
    used_state_stems: set[str] = set()
    groups = [
        _render_group(
            config,
            row,
            level,
            key,
            guidance_sentences[level],
            used_state_stems,
            eol,
        )
        for level in config.levels
    ]
    closing_ending_family, _ = _ending_style_for_slot(key, CLOSING_ENDING_SLOT)
    closing = _choose(
        key,
        f"natural-closing-{closing_ending_family}-{closing_context}",
        _closing_sentence_candidates(
            config.directory,
            _page_source_scope(config, row),
            closing_ending_family,
            closing_context,
        ),
    ).format(locality=row.locality)
    source_note = _visible_source_note(config, row)
    lines = [
        START_MARKER,
        (
            f'<section class="center-profile-school" id="{OUTER_ID}" '
            f'data-school-reference data-source-field="{SOURCE_FIELD}" '
            f'aria-labelledby="{TITLE_ID}">'
        ),
        '  <div class="wrap subject-narrow">',
        '    <div class="subject-section-head">',
        '      <div class="subject-kicker">SOURCE-VERIFIED SCHOOL RANGE</div>',
        f'      <h2 id="{TITLE_ID}">{html.escape(heading)}</h2>',
        f"      <span>{html.escape(source_note)}</span>",
        "    </div>",
        '    <div class="subject-copy-flow">',
    ]
    for group in groups:
        lines.extend("      " + line if line else line for line in group.split(eol))
    lines.extend(
        [
            "    </div>",
            '    <div class="subject-answer-box">',
            "      <span>확인</span>",
            f"      <p>{html.escape(closing)}</p>",
            "    </div>",
            "  </div>",
            "</section>",
            END_MARKER,
        ]
    )
    return eol.join(lines) + eol


def _remove_school_block(source: str, rel: str) -> str:
    matches = list(SCHOOL_BLOCK_RE.finditer(source))
    if not matches:
        return source
    if len(matches) != 1:
        raise PlanError(f"school marker block이 정확히 1개가 아닙니다: {rel}")
    return source[: matches[0].start()] + source[matches[0].end() :]


def _insert_school_block(source: str, block: str, rel: str) -> str:
    open_index = source.find(MANUSCRIPT_OPEN)
    if open_index < 0:
        raise PlanError(f"기존 원고 article을 찾지 못했습니다: {rel}")
    close_index = source.find("</article>", open_index)
    if close_index < 0:
        raise PlanError(f"기존 원고 article 닫힘을 찾지 못했습니다: {rel}")
    insertion = close_index + len("</article>")
    eol = _eol(source)
    if not source.startswith(eol, insertion):
        raise PlanError(f"원고 article 뒤 EOL 경계가 예상과 다릅니다: {rel}")
    insertion += len(eol)
    return source[:insertion] + block + source[insertion:]


def _replace_json(source: str, document: dict, rel: str) -> str:
    match, _ = _json_document(source, rel)
    raw = json.dumps(document, ensure_ascii=False, separators=(",", ":"))
    return source[: match.start(2)] + raw + source[match.end(2) :]


def _critical_signature(source: str, rel: str) -> tuple:
    values = []
    for label, pattern in (
        ("title", TITLE_RE),
        ("description", META_DESCRIPTION_RE),
        ("canonical", CANONICAL_RE),
        ("og:url", OG_URL_RE),
        ("h1", H1_RE),
    ):
        matches = pattern.findall(source)
        if len(matches) != 1:
            raise PlanError(f"{label} cardinality 오류: {rel}: {len(matches)}")
        values.append(matches[0])
    return tuple(values)


def _faq_visible(source: str) -> str:
    match = FAQ_VISIBLE_RE.search(source)
    return match.group(0) if match else ""


def _schema_faq(document: Mapping) -> list[dict]:
    return copy.deepcopy(_graph_nodes(document, "FAQPage"))


def _schema_without_owned(document: dict, canonical: str) -> dict:
    value = copy.deepcopy(document)
    graph = value.get("@graph", [])
    graph[:] = [
        node
        for node in graph
        if not (
            isinstance(node, dict)
            and _owned_schema_id(node.get("@id"), canonical)
        )
    ]
    for node in graph:
        if not isinstance(node, dict):
            continue
        types = _schema_types(node)
        if "WebPage" in types:
            for key in ("mentions", "hasPart", "dateModified"):
                node.pop(key, None)
        if "Article" in types:
            for key in ("mentions", "hasPart", "articleSection", "dateModified"):
                node.pop(key, None)
        if "Service" in types:
            node.pop("mentions", None)
    return value


def _assert_unique_html_ids(source: str, rel: str) -> None:
    ids = re.findall(r'\bid=["\']([^"\']+)["\']', source, re.I)
    duplicates = sorted(name for name, count in Counter(ids).items() if count > 1)
    if duplicates:
        raise PlanError(f"중복 HTML id: {rel}: {duplicates}")


def _assert_unique_graph_ids(document: Mapping, rel: str) -> None:
    ids = [
        node.get("@id")
        for node in document.get("@graph", [])
        if isinstance(node, dict) and isinstance(node.get("@id"), str)
    ]
    duplicates = sorted(name for name, count in Counter(ids).items() if count > 1)
    if duplicates:
        raise PlanError(f"중복 top-level JSON-LD @id: {rel}: {duplicates}")


def _expected_chips(row: SchoolSourceRow, levels: Sequence[str]) -> list[str]:
    return [name for level in levels for name in row.levels[level].names]


def _extract_block(source: str, rel: str) -> str:
    matches = list(SCHOOL_BLOCK_RE.finditer(source))
    if len(matches) != 1:
        raise PlanError(f"school block cardinality 오류: {rel}: {len(matches)}")
    return matches[0].group(0)


def _extract_chip_names(block: str) -> list[str]:
    return [
        html.unescape(value)
        for value in re.findall(r'data-source-school="([^"]+)"', block)
    ]


def _extract_group_states(block: str) -> list[tuple[str, str]]:
    return re.findall(
        r'<section\b[^>]*data-school-level="(elementary|middle|high)"[^>]*'
        r'data-source-state="(provided|missing|coverage)"[^>]*>',
        block,
    )


def _transform_page(
    source: str,
    rel: str,
    config: CategoryConfig,
    row: SchoolSourceRow,
) -> tuple[str, dict]:
    # The two high-student coverage pages received a later, deliberately
    # cautious clarification: the broad source phrase is retained, but the
    # page does not turn it into a current per-school availability claim.
    # Preserve that audited refinement instead of letting this school-block
    # projector overwrite it during an unrelated source correction.
    if (
        config.directory == "고등학생학원"
        and row.levels["high"].state == "coverage"
        and "현재 연결된 센터 정보에는 개별 고등학교명" in source
    ):
        canonical = _canonical(source, rel)
        _, schema = _json_document(source, rel)
        block = _extract_block(source, rel)
        expected_states = [
            (level, row.levels[level].state) for level in config.levels
        ]
        if _extract_group_states(block) != expected_states:
            raise PlanError(f"보존 coverage state mismatch: {rel}")
        expected_chips = _expected_chips(row, config.levels)
        if _extract_chip_names(block) != expected_chips:
            raise PlanError(f"보존 coverage chip mismatch: {rel}")
        _assert_unique_html_ids(source, rel)
        _assert_unique_graph_ids(schema, rel)
        return source, {
            "canonical": canonical,
            "groups": expected_states,
            "chips": len(expected_chips),
            "correction_mode": _correction_mode(config, row.locality),
            "heading": _heading(config, row),
        }

    baseline = _remove_school_block(source, rel)
    if baseline.count(START_MARKER) or baseline.count(END_MARKER):
        raise PlanError(f"orphan school marker가 있습니다: {rel}")
    if f'id="{OUTER_ID}"' in baseline or f'id="{TITLE_ID}"' in baseline:
        raise PlanError(f"신규 school id가 기존 문서와 충돌합니다: {rel}")

    mode = _correction_mode(config, row.locality)
    corrected_visible = _correct_visible_non_json(baseline, mode)
    canonical = _canonical(corrected_visible, rel)
    json_match, json_before = _json_document(corrected_visible, rel)
    corrected_schema = _correct_schema(json_before, mode)
    heading = _heading(config, row)
    transformed_schema = _transform_schema(
        corrected_schema, canonical, config, row, heading
    )
    with_json = (
        corrected_visible[: json_match.start(2)]
        + json.dumps(transformed_schema, ensure_ascii=False, separators=(",", ":"))
        + corrected_visible[json_match.end(2) :]
    )
    block = _render_school_block(config, row, heading, _eol(with_json))
    output = _insert_school_block(with_json, block, rel)

    # Raw head and existing-copy parity.  The only visible-copy exception is the
    # fixed 15-page school-token correction declared above.
    if _critical_signature(baseline, rel) != _critical_signature(output, rel):
        raise PlanError(f"title/meta/canonical/og:url/H1 변형: {rel}")
    stripped = _remove_school_block(output, rel)
    before_non_json = JSON_RE.sub(r"\1\0JSONLD\0\3", corrected_visible, count=1)
    after_non_json = JSON_RE.sub(r"\1\0JSONLD\0\3", stripped, count=1)
    if before_non_json != after_non_json:
        raise PlanError(f"신규 block 외 visible raw parity 실패: {rel}")

    _, json_after = _json_document(output, rel)
    if _schema_without_owned(corrected_schema, canonical) != _schema_without_owned(
        json_after, canonical
    ):
        raise PlanError(f"allowlist 밖 JSON-LD 변경: {rel}")
    if _schema_faq(corrected_schema) != _schema_faq(json_after):
        raise PlanError(f"FAQPage JSON-LD 변경: {rel}")
    expected_faq_visible = _faq_visible(corrected_visible)
    if expected_faq_visible != _faq_visible(output):
        raise PlanError(f"기존 visible FAQ 변경: {rel}")

    _assert_unique_html_ids(output, rel)
    _assert_unique_graph_ids(json_after, rel)
    if output.count(START_MARKER) != 1 or output.count(END_MARKER) != 1:
        raise PlanError(f"school marker cardinality 오류: {rel}")
    if len(re.findall(r"<section\b[^>]*\bdata-school-reference\b", output)) != 1:
        raise PlanError(f"section[data-school-reference] cardinality 오류: {rel}")
    block_after = _extract_block(output, rel)
    expected_states = [
        (level, row.levels[level].state) for level in config.levels
    ]
    if _extract_group_states(block_after) != expected_states:
        raise PlanError(
            f"학제별 state mismatch: {rel}: "
            f"{_extract_group_states(block_after)} != {expected_states}"
        )
    if block_after.count("data-school-source-state") != len(config.levels):
        raise PlanError(f"source state node cardinality 오류: {rel}")
    expected_chips = _expected_chips(row, config.levels)
    if _extract_chip_names(block_after) != expected_chips:
        raise PlanError(f"학교 chip source/order mismatch: {rel}")
    if "창원중앙여고" in expected_chips and (
        'data-source-school="창원중"' in block_after
        or 'data-source-school="앙여고"' in block_after
    ):
        raise PlanError(f"창원중앙여고 atomicity 실패: {rel}")

    stats = {
        "canonical": canonical,
        "groups": expected_states,
        "chips": len(expected_chips),
        "correction_mode": mode,
        "heading": heading,
    }
    return output, stats


def _transform_sitemap(
    source: str,
    target_urls: set[str],
    rel: str = SITEMAP_NAME,
) -> tuple[str, dict]:
    seen: set[str] = set()
    changed = 0

    def replace_block(match: re.Match[str]) -> str:
        nonlocal changed
        block = match.group(0)
        loc_match = SITEMAP_LOC_RE.search(block)
        if not loc_match:
            raise PlanError(f"sitemap url block에 loc가 없습니다: {rel}")
        loc = html.unescape(loc_match.group(1).strip())
        if loc not in target_urls:
            return block
        if loc in seen:
            raise PlanError(f"sitemap 대상 loc 중복: {loc}")
        seen.add(loc)
        lastmods = list(SITEMAP_LASTMOD_RE.finditer(block))
        if len(lastmods) != 1:
            raise PlanError(f"sitemap 대상 lastmod cardinality 오류: {loc}: {len(lastmods)}")
        current_lastmod = lastmods[0].group(2).strip()
        effective_lastmod = RELEASE_DATE
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", current_lastmod):
            effective_lastmod = max(RELEASE_DATE, current_lastmod)
        new_block = SITEMAP_LASTMOD_RE.sub(
            lambda item: item.group(1) + effective_lastmod + item.group(3),
            block,
            count=1,
        )
        if new_block != block:
            changed += 1
        return new_block

    output = SITEMAP_URL_RE.sub(replace_block, source)
    missing = target_urls - seen
    if missing:
        examples = sorted(missing)[:5]
        raise PlanError(f"sitemap에 대상 URL이 없습니다: {len(missing)}: {examples}")
    if len(seen) != EXPECTED_PAGE_COUNT:
        raise PlanError(f"sitemap 대상 loc 수 오류: {len(seen)}")

    # Prove that every non-target <url> block is raw exact.
    before_blocks = SITEMAP_URL_RE.findall(source)
    after_blocks = SITEMAP_URL_RE.findall(output)
    if len(before_blocks) != len(after_blocks):
        raise PlanError("sitemap url block 수가 변경되었습니다.")
    non_target_changes = 0
    for before, after in zip(before_blocks, after_blocks):
        loc_match = SITEMAP_LOC_RE.search(before)
        loc = html.unescape(loc_match.group(1).strip()) if loc_match else ""
        if loc not in target_urls and before != after:
            non_target_changes += 1
    if non_target_changes:
        raise PlanError(f"sitemap 비대상 block 변경: {non_target_changes}")
    return output, {"matched": len(seen), "lastmod_changed": changed}


def _strip_tags(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(TAG_RE.sub(" ", value))).strip()


def _normalized_copy(value: str, variable_tokens: Sequence[str]) -> str:
    result = value
    for token in sorted(set(variable_tokens), key=len, reverse=True):
        if token:
            result = result.replace(token, "{VAR}")
    result = re.sub(r"\d+", "{N}", result)
    result = re.sub(r"\{VAR\}(?:·\{VAR\})+", "{SCHOOLS}", result)
    result = re.sub(r"\s+", " ", result).strip()
    return result


def _duplicate_ratio(values: Sequence[str]) -> float:
    if not values:
        return 0.0
    counts = Counter(values)
    duplicate_instances = sum(count for count in counts.values() if count > 1)
    return round(100.0 * duplicate_instances / len(values), 3)


def _frequency_report(families: Mapping[str, set[str]], limit: int = 8) -> dict:
    ranked = sorted(
        ((len(paths), value) for value, paths in families.items()),
        key=lambda item: (-item[0], item[1]),
    )
    return {
        "max_document_frequency": ranked[0][0] if ranked else 0,
        "distinct_families": len(ranked),
        "top_families": [
            {"document_frequency": frequency, "normalized_text": value}
            for frequency, value in ranked[:limit]
        ],
    }


def _copy_duplication_metrics(
    page_outputs: Mapping[str, str],
    sources: Mapping[str, SchoolSourceRow],
) -> dict:
    paragraphs: list[str] = []
    sentences: list[str] = []
    headings: list[str] = []
    paragraph_docs: dict[str, set[str]] = {}
    sentence_docs: dict[str, set[str]] = {}
    heading_docs: dict[str, set[str]] = {}
    within_duplicates = 0
    for rel, source in page_outputs.items():
        block = _extract_block(source, rel)
        parts = PurePosixPath(rel).parts
        config = CATEGORY_BY_DIR[parts[1]]
        locality = parts[2]
        row = sources[locality]
        variables = [
            locality,
            row.region,
            row.district,
            row.center,
            config.directory,
            config.label,
            config.service,
            COVERAGE_RAW,
            *LEVEL_LABEL.values(),
            *_school_names_for_levels(row, config.levels),
        ]
        page_paragraphs: list[str] = []
        source_state_prefixes_excluded = 0
        for match in re.finditer(r"<p\b([^>]*)>(.*?)</p>", block, re.S | re.I):
            inner = match.group(2)
            value = _strip_tags(inner)
            if "data-school-source-state" in match.group(1):
                # The source-fact span directly renders locality, source-state
                # and exact school names.  It is not authored SEO copy.  The
                # sibling authored-copy span remains inside every diversity gate.
                authored = re.findall(
                    r'<span\b[^>]*data-school-authored-copy[^>]*>(.*?)</span>',
                    inner,
                    re.S | re.I,
                )
                facts = re.findall(
                    r'<span\b[^>]*data-school-source-fact[^>]*>(.*?)</span>',
                    inner,
                    re.S | re.I,
                )
                if len(authored) != 1 or len(facts) != 1:
                    raise PlanError(f"source/authored span boundary 오류: {rel}")
                value = _strip_tags(authored[0])
                source_state_prefixes_excluded += 1
            page_paragraphs.append(value)
        if source_state_prefixes_excluded != len(config.levels):
            raise PlanError(f"source-state exclude cardinality 오류: {rel}")
        page_headings = [
            _strip_tags(item)
            for item in re.findall(r"<h2\b[^>]*>(.*?)</h2>", block, re.S | re.I)
        ]
        page_sentences = [
            sentence.strip()
            for paragraph in page_paragraphs
            for sentence in SENTENCE_RE.split(paragraph)
            if sentence.strip()
        ]
        normalized_page = {
            "p": [_normalized_copy(item, variables) for item in page_paragraphs],
            "s": [_normalized_copy(item, variables) for item in page_sentences],
            "h2": [_normalized_copy(item, variables) for item in page_headings],
        }
        within_duplicates += sum(
            len(values) - len(set(values)) for values in normalized_page.values()
        )
        for value in set(normalized_page["p"]):
            paragraph_docs.setdefault(value, set()).add(rel)
        for value in set(normalized_page["s"]):
            sentence_docs.setdefault(value, set()).add(rel)
        for value in set(normalized_page["h2"]):
            heading_docs.setdefault(value, set()).add(rel)
        paragraphs.extend(normalized_page["p"])
        sentences.extend(normalized_page["s"])
        headings.extend(normalized_page["h2"])
    p_report = _frequency_report(paragraph_docs)
    s_report = _frequency_report(sentence_docs)
    h2_report = _frequency_report(heading_docs)
    result = {
        "hard_ceiling_document_frequency": {
            "paragraph": 34,
            "sentence": 34,
            "h2": 40,
        },
        "paragraph": p_report,
        "sentence": s_report,
        "h2": h2_report,
        "normalized_paragraph_duplicate_pct": _duplicate_ratio(paragraphs),
        "normalized_sentence_duplicate_pct": _duplicate_ratio(sentences),
        "normalized_h2_duplicate_pct": _duplicate_ratio(headings),
        "within_page_normalized_duplicates": within_duplicates,
        "instances": {
            "paragraphs": len(paragraphs),
            "sentences": len(sentences),
            "h2": len(headings),
        },
        "source_aware_exclusions": {
            "excluded": (
                "각 [data-school-source-state] 문단의 [data-school-source-fact] "
                "locality/source-state/exact-school 사실과 data-source-school chip"
            ),
            "included": (
                "같은 문단의 [data-school-authored-copy] 상담 문구, 일반 안내 문단, "
                "마무리 문단, H2 전체"
            ),
        },
    }
    if p_report["max_document_frequency"] > 34:
        raise PlanError(f"신규 paragraph 정규화 document-frequency gate 실패: {result}")
    if s_report["max_document_frequency"] > 34:
        raise PlanError(f"신규 sentence 정규화 document-frequency gate 실패: {result}")
    if h2_report["max_document_frequency"] > 40:
        raise PlanError(f"신규 H2 정규화 document-frequency gate 실패: {result}")
    if within_duplicates:
        raise PlanError(f"신규 원고 page 내부 정규화 중복 gate 실패: {result}")
    return result


def _naturalness_metrics(page_outputs: Mapping[str, str]) -> dict:
    heading_initial_collisions = 0
    heading_final_collisions = 0
    heading_initial_dynamic_overlap = 0
    heading_final_dynamic_overlap = 0
    authored_paragraphs = 0
    sentences_checked = 0
    repeat_sentences = 0
    repeat_families: Counter[str] = Counter()
    repeat_pages: dict[str, set[str]] = {}
    source_scope_violations: list[dict[str, str]] = []
    provided_facts_checked = 0
    school_adjacent_repeat_pages: set[str] = set()
    provided_positive_meaning_pages: set[str] = set()
    ending_family_repeat_pages = 0
    ending_clause_repeat_pages = 0
    ending_suffix_repeat_pages: Counter[int] = Counter()
    fixed_ending_family_repeat_pages: Counter[str] = Counter()
    ending_subject_predicate_incompatibility_pages: set[str] = set()
    legacy_incompatible_ending_pages: set[str] = set()
    legacy_incompatible_ending_families: Counter[str] = Counter()
    compatible_atomic_endings_checked = 0
    guidance_context_repeat_pages: set[str] = set()
    guidance_context_ownership_violations: list[dict] = []
    state_stem_repeat_pages: set[str] = set()
    guidance_lead_repeat_pages: set[str] = set()
    ending_violations: list[dict] = []
    samples: list[dict] = []

    for rel, source in page_outputs.items():
        parts = PurePosixPath(rel).parts
        config = CATEGORY_BY_DIR[parts[1]]
        locality = parts[2]
        key = f"{config.directory}|{locality}"
        block = _extract_block(source, rel)
        states = set(
            re.findall(
                r'data-source-state="(provided|missing|coverage)"', block
            )
        )
        if not states:
            raise PlanError(f"H2 상태를 판정할 수 없습니다: {rel}")
        subject = _heading_subject(states)
        initial_focus = _choose(key, "school-heading", HEADING_FOCUSES)
        initial_start = _choose(key, "school-heading-start", HEADING_STARTS)
        initial_end = _choose(key, "school-heading-end", HEADING_ENDS)
        final_focus, final_start, final_end = _choose_heading_parts(key, subject)
        if _heading_semantic_collision(initial_start, initial_end):
            heading_initial_collisions += 1
        if _heading_semantic_collision(final_start, final_end):
            heading_final_collisions += 1
            if len(samples) < 12:
                samples.append(
                    {
                        "kind": "heading",
                        "path": rel,
                        "start": final_start,
                        "end": final_end,
                    }
                )
        initial_signatures = [
            _heading_natural_signature(value)
            for value in (subject, initial_focus, initial_start, initial_end)
        ]
        final_signatures = [
            _heading_natural_signature(value)
            for value in (subject, final_focus, final_start, final_end)
        ]
        if any(
            left & right
            for index, left in enumerate(initial_signatures)
            for right in initial_signatures[index + 1 :]
        ):
            heading_initial_dynamic_overlap += 1
        if any(
            left & right
            for index, left in enumerate(final_signatures)
            for right in final_signatures[index + 1 :]
        ):
            heading_final_dynamic_overlap += 1

        group_records = re.findall(
            r'<section\b[^>]*data-school-level="([^"]+)"[^>]*'
            r'data-source-state="([^"]+)"[^>]*>(.*?)</section>',
            block,
            re.S | re.I,
        )
        state_by_level: dict[str, str] = {}
        state_authored_by_level: dict[str, str] = {}
        guidance_by_level: dict[str, str] = {}
        for level, source_state, group in group_records:
            state_by_level[level] = source_state
            fact_match = re.search(
                r'<span\b[^>]*data-school-source-fact[^>]*>(.*?)</span>',
                group,
                re.S | re.I,
            )
            if not fact_match:
                raise PlanError(f"원자료 사실 경계를 찾지 못했습니다: {rel}/{level}")
            fact_text = _strip_tags(fact_match.group(1))
            if re.search(r"학교\s+학교", fact_text):
                school_adjacent_repeat_pages.add(rel)
                source_scope_violations.append(
                    {
                        "path": rel,
                        "kind": "school-adjacent-repeat",
                        "text": fact_text,
                    }
                )
            if source_state == "provided":
                provided_facts_checked += 1
                if not re.search(
                    r"(?:실제\s*수업(?:이)?\s*가능|수업이\s*실제\s*가능)",
                    fact_text,
                ):
                    provided_positive_meaning_pages.add(rel)
                    source_scope_violations.append(
                        {
                            "path": rel,
                            "kind": "provided-positive-meaning",
                            "text": fact_text,
                        }
                    )
            authored_match = re.search(
                r'<span\b[^>]*data-school-authored-copy[^>]*>(.*?)</span>',
                group,
                re.S | re.I,
            )
            if not authored_match:
                raise PlanError(f"작성 문장 경계를 찾지 못했습니다: {rel}/{level}")
            authored_text = _strip_tags(authored_match.group(1))
            state_authored_by_level[level] = authored_text
            group_without_source_state = re.sub(
                r'<p\b[^>]*data-school-source-state[^>]*>.*?</p>',
                "",
                group,
                flags=re.S | re.I,
            )
            guidance_matches = re.findall(
                r"<p\b[^>]*>(.*?)</p>",
                group_without_source_state,
                re.S | re.I,
            )
            if len(guidance_matches) != 1:
                raise PlanError(f"guidance 문장 경계 오류: {rel}/{level}")
            guidance_by_level[level] = _strip_tags(guidance_matches[0])
            source_compare = (
                "원자료와 맞춘" in authored_text
                or "가능 학교와 대조" in authored_text
            )
            if source_compare and not (
                source_state == "provided" and "재학 학교를" in authored_text
            ):
                source_scope_violations.append(
                    {
                        "path": rel,
                        "kind": "source-compare",
                        "text": authored_text,
                    }
                )
            if (
                source_state == "missing"
                and "학교 범위와 함께" in authored_text
            ):
                source_scope_violations.append(
                    {
                        "path": rel,
                        "kind": "missing-range",
                        "text": authored_text,
                    }
                )

        if states == {"coverage"}:
            visible = _strip_tags(block)
            for positive_list_claim in (
                "학교 가능 목록",
                "가능 학교 목록",
                "학교명 목록",
            ):
                if positive_list_claim in visible:
                    source_scope_violations.append(
                        {
                            "path": rel,
                            "kind": "coverage-positive-list",
                            "text": positive_list_claim,
                        }
                    )

        paragraphs = [
            _strip_tags(value)
            for value in re.findall(
                r'<span\b[^>]*data-school-authored-copy[^>]*>(.*?)</span>',
                block,
                re.S | re.I,
            )
        ]
        without_source_facts = re.sub(
            r'<p\b[^>]*data-school-source-state[^>]*>.*?</p>',
            "",
            block,
            flags=re.S | re.I,
        )
        paragraphs.extend(
            _strip_tags(value)
            for value in re.findall(
                r"<p\b[^>]*>(.*?)</p>",
                without_source_facts,
                re.S | re.I,
            )
        )

        (
            expected_guidance_contexts,
            expected_guidance_sentences,
            expected_closing_context,
        ) = (
            _page_guidance_plan(key, config, state_by_level)
        )
        expected_contexts = [
            expected_guidance_contexts[level] for level in config.levels
        ] + [expected_closing_context]
        if guidance_by_level != expected_guidance_sentences:
            violation = {
                "path": rel,
                "kind": "guidance-render-plan-mismatch",
            }
            guidance_context_ownership_violations.append(violation)
            ending_violations.append(violation)
        state_stems: list[str] = []
        guidance_leads: list[str] = []
        for level in config.levels:
            state_text = state_authored_by_level[level]
            state_families = _compatible_atomic_ending_families(state_text)
            guidance_text = guidance_by_level[level]
            guidance_families = _compatible_atomic_ending_families(guidance_text)
            if len(state_families) == 1:
                state_stems.append(
                    _state_sentence_stem(state_text, level, state_families[0])
                )
            if len(guidance_families) == 1:
                guidance_leads.append(
                    _guidance_lead_signature(
                        guidance_text,
                        level,
                        expected_guidance_contexts[level],
                        guidance_families[0],
                    )
                )
        if len(state_stems) != len(set(state_stems)):
            state_stem_repeat_pages.add(rel)
            ending_violations.append(
                {
                    "path": rel,
                    "kind": "state-stem-repeat",
                    "stems": state_stems,
                }
            )
        if len(guidance_leads) != len(set(guidance_leads)):
            guidance_lead_repeat_pages.add(rel)
            ending_violations.append(
                {
                    "path": rel,
                    "kind": "guidance-lead-repeat",
                    "leads": guidance_leads,
                }
            )
        context_occurrences = {
            context: sum(paragraph.count(context) for paragraph in paragraphs)
            for context in GUIDANCE_CONTEXTS
        }
        actual_contexts = [
            context
            for context, count in context_occurrences.items()
            for _ in range(count)
        ]
        if len(actual_contexts) != len(set(actual_contexts)):
            guidance_context_repeat_pages.add(rel)
        if (
            len(expected_contexts) != len(set(expected_contexts))
            or sorted(actual_contexts) != sorted(expected_contexts)
        ):
            violation = {
                "path": rel,
                "kind": "guidance-context-ownership",
                "expected": expected_contexts,
                "actual": actual_contexts,
            }
            guidance_context_ownership_violations.append(violation)
            ending_violations.append(violation)

        page_ending_families: list[str] = []
        page_final_clauses: list[str] = []
        page_suffixes: dict[int, list[str]] = {5: [], 6: [], 7: []}
        compact_paragraphs = [re.sub(r"\s+", "", value) for value in paragraphs]
        for paragraph in paragraphs:
            matches = list(_compatible_atomic_ending_families(paragraph))
            if len(matches) != 1:
                ending_subject_predicate_incompatibility_pages.add(rel)
                ending_violations.append(
                    {
                        "path": rel,
                        "kind": "incompatible-or-unowned-atomic-ending",
                        "text": paragraph,
                    }
                )
            else:
                compatible_atomic_endings_checked += 1
                page_ending_families.append(matches[0])
            for family, pattern in LEGACY_INCOMPATIBLE_ENDING_PATTERNS.items():
                if pattern.search(paragraph):
                    legacy_incompatible_ending_pages.add(rel)
                    legacy_incompatible_ending_families[family] += 1
                    ending_violations.append(
                        {
                            "path": rel,
                            "kind": f"legacy-incompatible-ending-{family}",
                            "text": paragraph,
                        }
                    )
            clause = re.split(r"[,;:，；：]", paragraph)[-1]
            normalized_clause = " ".join(
                re.findall(r"[가-힣A-Za-z0-9]+", clause.casefold())
            )
            page_final_clauses.append(normalized_clause)
            tokens = re.findall(r"[가-힣A-Za-z0-9]+", paragraph.casefold())
            for width in page_suffixes:
                if len(tokens) < width:
                    ending_violations.append(
                        {
                            "path": rel,
                            "kind": f"short-{width}-token-suffix",
                            "text": paragraph,
                        }
                    )
                else:
                    page_suffixes[width].append(" ".join(tokens[-width:]))

        if len(page_ending_families) != len(set(page_ending_families)):
            ending_family_repeat_pages += 1
            ending_violations.append(
                {
                    "path": rel,
                    "kind": "ending-family-repeat",
                    "families": page_ending_families,
                }
            )
        if len(page_final_clauses) != len(set(page_final_clauses)):
            ending_clause_repeat_pages += 1
            ending_violations.append(
                {
                    "path": rel,
                    "kind": "final-clause-repeat",
                    "clauses": page_final_clauses,
                }
            )
        for width, suffixes in page_suffixes.items():
            if len(suffixes) != len(set(suffixes)):
                ending_suffix_repeat_pages[width] += 1
                ending_violations.append(
                    {
                        "path": rel,
                        "kind": f"suffix-{width}-repeat",
                        "suffixes": suffixes,
                    }
                )

        fixed_patterns = {
            "separate-check": re.compile(r"별도로(?:다시)?(?:재)?확인"),
            "staff-answer-write": re.compile(r"담당자답변(?:을)?받아적"),
        }
        for family, pattern in fixed_patterns.items():
            occurrences = sum(
                len(pattern.findall(value)) for value in compact_paragraphs
            )
            if occurrences > 1:
                fixed_ending_family_repeat_pages[family] += 1
                ending_violations.append(
                    {
                        "path": rel,
                        "kind": f"fixed-{family}-repeat",
                        "occurrences": occurrences,
                    }
                )

        authored_paragraphs += len(paragraphs)
        for paragraph in paragraphs:
            for sentence in SENTENCE_RE.split(paragraph):
                sentence = sentence.strip()
                if not sentence:
                    continue
                sentences_checked += 1
                repeats = _authored_repeat_counts(sentence)
                if not repeats:
                    continue
                repeat_sentences += 1
                for family, count in repeats.items():
                    repeat_families[family] += 1
                    repeat_pages.setdefault(family, set()).add(rel)
                    if len(samples) < 12:
                        samples.append(
                            {
                                "kind": "sentence",
                                "path": rel,
                                "family": family,
                                "count": count,
                                "sentence": sentence,
                            }
                        )

    # Synthetic sentinels prove that the exact patterns behind the reported
    # real-page zeroes still reject the regressions that prompted this gate.
    if not _heading_semantic_collision("학생 일정 대조", "학생 일정 비교"):
        raise AssertionError("H2 일정 대조/비교 synthetic이 충돌을 잡지 못했습니다.")
    cited = (
        "학교명과 학년을 다시 한 번 확인하고 희망 과목의 현재 학년 편성과 "
        "수업 시간을 마지막에 확인하세요."
    )
    cited_repeats = _authored_repeat_counts(cited)
    if cited_repeats.get("grade", 0) < 2 or cited_repeats.get("check", 0) < 2:
        raise AssertionError("학년/확인 반복 synthetic이 회귀를 잡지 못했습니다.")

    ending_families = tuple(family for family, _ in ENDING_STYLES)

    def candidate_size_range(values: Iterable[int]) -> dict[str, int]:
        sizes = tuple(values)
        return {"min": min(sizes), "max": max(sizes)}

    if len({family for family, _ in ENDING_STYLES}) != len(ENDING_STYLES):
        raise AssertionError("종결문 family 중복 synthetic 실패")
    if len({family for family, _, _ in ENDING_STYLE_PARTS}) != len(
        ENDING_STYLE_PARTS
    ):
        raise AssertionError("atomic 종결문 family 중복 synthetic 실패")
    if any(
        _ending_phrase(family) != f"{subject} {predicate}"
        for family, subject, predicate in ENDING_STYLE_PARTS
    ):
        raise AssertionError("atomic 종결문 subject/predicate 소유권 synthetic 실패")
    mismatched_atomic = (
        f"{ENDING_STYLE_PARTS[0][1]} {ENDING_STYLE_PARTS[1][2]}"
    )
    if _compatible_atomic_ending_families(mismatched_atomic):
        raise AssertionError("교차 결합 종결문 synthetic을 거부하지 못했습니다.")
    if not all(
        _compatible_atomic_ending_families(_ending_phrase(family)) == (family,)
        for family, _, _ in ENDING_STYLE_PARTS
    ):
        raise AssertionError("정상 atomic 종결문 synthetic을 인식하지 못했습니다.")
    synthetic_families = [ENDING_STYLES[0][0], ENDING_STYLES[0][0]]
    if len(synthetic_families) == len(set(synthetic_families)):
        raise AssertionError("페이지 종결 family 반복 감지 synthetic 실패")
    repeated_ending = ENDING_STYLES[0][1]
    repeated_suffix = " ".join(
        re.findall(r"[가-힣A-Za-z0-9]+", repeated_ending)[-6:]
    )
    synthetic_suffixes = [repeated_suffix, repeated_suffix]
    if len(synthetic_suffixes) == len(set(synthetic_suffixes)):
        raise AssertionError("6-token suffix 중복 synthetic 실패")
    synthetic_contexts = [GUIDANCE_CONTEXTS[0], GUIDANCE_CONTEXTS[0]]
    if len(synthetic_contexts) == len(set(synthetic_contexts)):
        raise AssertionError("페이지 안내 문맥 반복 감지 synthetic 실패")
    if not re.search(
        r"별도로(?:다시)?(?:재)?확인",
        "별도로재확인",
    ) or not re.search(
        r"담당자답변(?:을)?받아적",
        "담당자답변을받아적으세요",
    ):
        raise AssertionError("고정 종결 family synthetic 실패")
    positive_school_pattern = re.compile(
        r"(?:실제\s*수업(?:이)?\s*가능|수업이\s*실제\s*가능)"
    )
    if not re.search(r"학교\s+학교", "고등학교 학교로"):
        raise AssertionError("학교 인접 반복 synthetic 실패")
    if not positive_school_pattern.search("실제 수업이 가능한 고등학교"):
        raise AssertionError("실제 수업 가능 의미 synthetic 실패")
    if positive_school_pattern.search("수업을 문의할 수 있는 고등학교"):
        raise AssertionError("문의 가능 의미 약화 synthetic 실패")

    result = {
        "heading_semantic_collision": {
            "initial_selection_pages": heading_initial_collisions,
            "final_pages": heading_final_collisions,
            "stricter_dynamic_phrase_overlap_initial_pages": (
                heading_initial_dynamic_overlap
            ),
            "stricter_dynamic_phrase_overlap_final_pages": (
                heading_final_dynamic_overlap
            ),
        },
        "authored_copy": {
            "paragraphs_checked": authored_paragraphs,
            "sentences_checked": sentences_checked,
            "repeat_sentences": repeat_sentences,
            "repeat_family_sentence_counts": dict(sorted(repeat_families.items())),
            "repeat_family_page_counts": {
                family: len(paths)
                for family, paths in sorted(repeat_pages.items())
            },
            "source_aware_exclusion": (
                "data-school-source-fact와 data-source-school chip은 제외; "
                "data-school-authored-copy, 일반 guidance, closing의 모든 문장은 포함"
            ),
        },
        "source_scope_semantics": {
            "violations": len(source_scope_violations),
            "provided_facts_checked": provided_facts_checked,
            "school_adjacent_repeat_pages": len(
                school_adjacent_repeat_pages
            ),
            "provided_positive_meaning_pages": len(
                provided_positive_meaning_pages
            ),
            "checks": (
                "원자료/가능학교 대조는 provided 재학학교에만 허용; "
                "missing 학교범위 결합 금지; coverage-only 긍정 학교목록 주장 금지; "
                "학교 학교 인접 반복 금지; provided 사실은 실제 수업 가능 의미 필수"
            ),
            "samples": source_scope_violations[:12],
        },
        "page_internal_endings": {
            "pages_checked": len(page_outputs),
            "authored_paragraphs_checked": authored_paragraphs,
            "compatible_atomic_endings_checked": compatible_atomic_endings_checked,
            "subject_predicate_incompatibility_pages": len(
                ending_subject_predicate_incompatibility_pages
            ),
            "legacy_incompatible_cited_pages": len(
                legacy_incompatible_ending_pages
            ),
            "legacy_incompatible_family_counts": dict(
                sorted(legacy_incompatible_ending_families.items())
            ),
            "guidance_context_repeat_pages": len(
                guidance_context_repeat_pages
            ),
            "guidance_context_ownership_violations": len(
                guidance_context_ownership_violations
            ),
            "state_stem_repeat_pages": len(state_stem_repeat_pages),
            "guidance_lead_repeat_pages": len(guidance_lead_repeat_pages),
            "ending_family_repeat_pages": ending_family_repeat_pages,
            "normalized_final_clause_repeat_pages": ending_clause_repeat_pages,
            "normalized_suffix_repeat_pages": {
                str(width): ending_suffix_repeat_pages[width]
                for width in (5, 6, 7)
            },
            "fixed_family_repeat_pages": {
                family: fixed_ending_family_repeat_pages[family]
                for family in ("separate-check", "staff-answer-write")
            },
            "ending_families": [family for family, _ in ENDING_STYLES],
            "violations": len(ending_violations),
            "samples": ending_violations[:12],
        },
        "candidate_pool_sizes": {
            "state": {
                f"{source_state}-{level}": candidate_size_range(
                    len(
                        _state_sentence_candidates(
                            level, source_state, ending_family
                        )
                    )
                    for ending_family in ending_families
                )
                for source_state in ("provided", "missing", "coverage")
                for level in LEVEL_ORDER
            },
            "guidance": {
                f"{state}-{level}": candidate_size_range(
                    len(
                        _guidance_sentence_candidates(
                            state, level, ending_family
                        )
                    )
                    for ending_family in ending_families
                )
                for state in ("provided", "missing", "coverage")
                for level in LEVEL_ORDER
            },
            "closing": {
                f"{config.directory}-{source_scope}": candidate_size_range(
                    len(
                        _closing_sentence_candidates(
                            config.directory,
                            source_scope,
                            ending_family,
                        )
                    )
                    for ending_family in ending_families
                )
                for config in CATEGORIES
                for source_scope in (
                    "provided",
                    "missing",
                    "coverage",
                    "mixed",
                )
            },
        },
        "synthetics": {
            "heading_schedule_compare_collision": True,
            "grade_and_check_repeat": True,
            "ending_family_repeat": True,
            "six_token_suffix_repeat": True,
            "fixed_ending_families": True,
            "atomic_subject_predicate_compatibility": True,
            "legacy_incompatible_cited_endings": True,
            "guidance_context_repeat": True,
            "state_stem_and_guidance_lead_repeat": True,
            "school_adjacent_repeat": True,
            "provided_positive_meaning": True,
        },
        "samples": samples,
    }
    if (
        heading_final_collisions
        or heading_final_dynamic_overlap
        or repeat_sentences
        or source_scope_violations
        or ending_violations
    ):
        raise PlanError(f"신규 원고 자연성 반복 gate 실패: {result}")
    return result


def _build_red_team_paths(
    page_paths: Sequence[str],
    sources: Mapping[str, SchoolSourceRow],
) -> tuple[str, ...]:
    selected: list[str] = []
    available = set(page_paths)

    def add(rel: str) -> None:
        if rel in available and rel not in selected:
            selected.append(rel)

    # All malformed-token correction boundaries.
    for locality in sorted(CORRECTION_LOCALITIES):
        for category in (
            "고등수학학원",
            "고등영어학원",
            "중등수학학원",
            "중등영어학원",
            "영수학원",
        ):
            add(f"{SUBJECT_ROOT_NAME}/{category}/{locality}/index.html")

    # Every category for coverage source rows.
    coverage_localities = [
        locality
        for locality, row in sources.items()
        if row.levels["high"].state == "coverage"
    ]
    for locality in coverage_localities:
        for config in CATEGORIES:
            add(f"{SUBJECT_ROOT_NAME}/{config.directory}/{locality}/index.html")

    # Separator and first-seen-dedupe source cells in every relevant category.
    special_localities = {
        locality
        for locality, row in sources.items()
        for level in LEVEL_ORDER
        if re.search(r"[/.]", row.levels[level].raw)
        or row.levels[level].raw_name_count != len(row.levels[level].names)
    }
    for locality in sorted(special_localities):
        for config in CATEGORIES:
            if any(
                sources[locality].levels[level].raw
                and (
                    re.search(r"[/.]", sources[locality].levels[level].raw)
                    or sources[locality].levels[level].raw_name_count
                    != len(sources[locality].levels[level].names)
                )
                for level in config.levels
            ):
                add(f"{SUBJECT_ROOT_NAME}/{config.directory}/{locality}/index.html")

    # Boundary and state examples, then deterministic fill to at least 64.
    for config in CATEGORIES:
        category_paths = sorted(
            (rel for rel in page_paths if f"/{config.directory}/" in rel),
            key=lambda value: value.encode("utf-8"),
        )
        add(category_paths[0])
        add(category_paths[-1])
        for state in ("provided", "missing", "coverage"):
            match = next(
                (
                    rel
                    for rel in category_paths
                    if any(
                        sources[PurePosixPath(rel).parts[2]].levels[level].state
                        == state
                        for level in config.levels
                    )
                ),
                None,
            )
            if match:
                add(match)
    for rel in sorted(
        page_paths,
        key=lambda value: _stable_number(value, "red-team-fill"),
    ):
        if len(selected) >= 72:
            break
        add(rel)
    if len(selected) < 64:
        raise PlanError(f"red-team 표본이 64개 미만입니다: {len(selected)}")
    return tuple(selected)


def _validate_red_team(
    paths: Sequence[str],
    outputs: Mapping[str, str],
    sources: Mapping[str, SchoolSourceRow],
) -> dict:
    state_counts: Counter[str] = Counter()
    correction_count = 0
    for rel in paths:
        source = outputs[rel]
        block = _extract_block(source, rel)
        parts = PurePosixPath(rel).parts
        config = CATEGORY_BY_DIR[parts[1]]
        row = sources[parts[2]]
        expected = _expected_chips(row, config.levels)
        if _extract_chip_names(block) != expected:
            raise PlanError(f"red-team chip mismatch: {rel}")
        for _, state in _extract_group_states(block):
            state_counts[state] += 1
        mode = _correction_mode(config, row.locality)
        if mode:
            correction_count += 1
            if mode == "high" and (
                '>앙여고<' in source
                or '"name":"앙여고"' in source
                or "·앙여고" in source
            ):
                raise PlanError(f"red-team high correction 잔존: {rel}")
            if mode == "middle" and "창원중" in source:
                raise PlanError(f"red-team middle correction 잔존: {rel}")
            if mode == "yeongsu" and ("창원중·앙여고" in source or ">앙여고<" in source):
                raise PlanError(f"red-team yeongsu correction 잔존: {rel}")
    return {
        "sample_size": len(paths),
        "states": dict(sorted(state_counts.items())),
        "correction_pages": correction_count,
        "paths": list(paths),
    }


def _core_build(
    root: Path,
    sources: Mapping[str, SchoolSourceRow],
    page_paths: Sequence[str],
    inputs: Mapping[str, str],
) -> tuple[dict[str, str], dict]:
    outputs: dict[str, str] = {}
    page_stats: dict[str, dict] = {}
    target_urls: set[str] = set()
    group_states: Counter[str] = Counter()
    chips = 0
    correction_modes: Counter[str] = Counter()

    source_localities = set(sources)
    seen_localities_by_category: dict[str, set[str]] = {}
    for rel in page_paths:
        parts = PurePosixPath(rel).parts
        if len(parts) != 4 or parts[0] != SUBJECT_ROOT_NAME or parts[-1] != "index.html":
            raise PlanError(f"대상 경로 형식 오류: {rel}")
        config = CATEGORY_BY_DIR.get(parts[1])
        if not config:
            raise PlanError(f"미승인 카테고리 경로: {rel}")
        locality = parts[2]
        if locality not in sources:
            raise PlanError(f"페이지 동네가 타깃학교 CSV에 없습니다: {rel}")
        seen_localities_by_category.setdefault(config.directory, set()).add(locality)
        output, stats = _transform_page(inputs[rel], rel, config, sources[locality])
        outputs[rel] = output
        page_stats[rel] = stats
        if stats["canonical"] in target_urls:
            raise PlanError(f"대상 canonical 중복: {stats['canonical']}")
        target_urls.add(stats["canonical"])
        chips += stats["chips"]
        for _, state in stats["groups"]:
            group_states[state] += 1
        if stats["correction_mode"]:
            correction_modes[stats["correction_mode"]] += 1

    for config in CATEGORIES:
        seen = seen_localities_by_category.get(config.directory, set())
        if seen != source_localities:
            raise PlanError(
                f"{config.directory} route/source 불일치: "
                f"missing={sorted(source_localities-seen)[:5]} "
                f"extra={sorted(seen-source_localities)[:5]}"
            )

    total_groups = sum(group_states.values())
    if total_groups != EXPECTED_GROUP_COUNT:
        raise PlanError(f"학제 group 수 오류: {total_groups}")
    if dict(group_states) != EXPECTED_GROUP_STATES:
        raise PlanError(f"학제 state cardinality 오류: {dict(group_states)}")
    if chips != EXPECTED_NAMED_CHIPS:
        raise PlanError(f"deduped named chip 수 오류: {chips}")
    if dict(correction_modes) != {"high": 6, "middle": 6, "yeongsu": 3}:
        raise PlanError(f"malformed school correction path 수 오류: {dict(correction_modes)}")

    sitemap_output, sitemap_stats = _transform_sitemap(
        inputs[SITEMAP_NAME], target_urls
    )
    outputs[SITEMAP_NAME] = sitemap_output
    red_team_paths = _build_red_team_paths(page_paths, sources)
    red_team = _validate_red_team(red_team_paths, outputs, sources)
    naturalness = _naturalness_metrics(
        {rel: outputs[rel] for rel in page_paths}
    )
    duplication = _copy_duplication_metrics(
        {rel: outputs[rel] for rel in page_paths}, sources
    )
    return outputs, {
        "pages": len(page_paths),
        "groups": total_groups,
        "group_states": dict(sorted(group_states.items())),
        "named_chips": chips,
        "corrections": dict(sorted(correction_modes.items())),
        "sitemap": sitemap_stats,
        "naturalness": naturalness,
        "duplication": duplication,
        "red_team": red_team,
    }


def build_plan(
    root: str | Path,
    common_dir: str | Path,
    current_overrides: Mapping[str | Path, str | bytes] | None = None,
) -> BuildPlan:
    """Build and fully validate an in-memory release plan.

    ``current_overrides`` may contain relative or absolute Path/string keys and
    string/bytes values, but only for the 2,968 HTML targets or sitemap.xml.
    """

    root_path = Path(root).resolve()
    common_path = Path(common_dir).resolve()
    if not root_path.is_dir():
        raise PlanError(f"root 폴더가 없습니다: {root_path}")
    if not common_path.is_dir():
        raise PlanError(f"common_dir 폴더가 없습니다: {common_path}")

    sources, source_bytes, source_diagnostics = _load_sources(common_path)
    page_paths = _relative_target_paths(root_path)
    authorized_paths = tuple(page_paths) + (SITEMAP_NAME,)
    authorized_set = set(authorized_paths)
    overrides = _prepare_overrides(
        root_path, current_overrides, authorized_set
    )
    inputs = {
        rel: overrides[rel]
        if rel in overrides
        else _read_document(root_path / Path(rel), rel)
        for rel in authorized_paths
    }
    before_manifest = {rel: _sha256_text(inputs[rel]) for rel in authorized_paths}

    outputs, diagnostics = _core_build(root_path, sources, page_paths, inputs)
    if set(outputs) != authorized_set:
        raise PlanError(
            f"authorized document set 불일치: {len(outputs)} != {len(authorized_set)}"
        )
    after_manifest = {rel: _sha256_text(outputs[rel]) for rel in authorized_paths}
    changed_paths = tuple(
        rel for rel in authorized_paths if inputs[rel] != outputs[rel]
    )
    # Mandatory in-process second pass.  Inputs are the first-pass outputs; exact
    # equality proves both HTML/JSON-LD replacement and sitemap idempotence.
    second_outputs, second_diagnostics = _core_build(
        root_path, sources, page_paths, outputs
    )
    second_pass_changes = tuple(
        rel for rel in authorized_paths if outputs[rel] != second_outputs[rel]
    )
    if second_pass_changes:
        raise PlanError(
            f"2-pass idempotence 실패: {len(second_pass_changes)}: "
            f"{list(second_pass_changes[:5])}"
        )
    # Sitemap's ``lastmod_changed`` is expected to move from 2,968 on a fresh
    # baseline to zero on the projected second pass.  Document equality is the
    # authoritative idempotence gate; all semantic cardinalities are rechecked
    # inside ``_core_build`` on both passes.

    diagnostics = {
        **diagnostics,
        "source": source_diagnostics,
        "authorized_documents": len(outputs),
        "changed_documents": len(changed_paths),
        "second_pass_changes": 0,
        "release_date": RELEASE_DATE,
        "source_sha256": _sha256_bytes(source_bytes),
    }
    return BuildPlan(
        authorized_documents={rel: outputs[rel] for rel in authorized_paths},
        changed_paths=changed_paths,
        diagnostics=diagnostics,
        source_sha256=_sha256_bytes(source_bytes),
        before_manifest=before_manifest,
        after_manifest=after_manifest,
        second_pass_changes=second_pass_changes,
    )


def _fsync_directory(path: Path) -> None:
    """Persist a directory entry update where the platform supports it."""

    if os.name == "nt":
        return
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _atomic_write_bytes(path: Path, value: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(
        prefix=path.name + ".", suffix=".tmp", dir=path.parent
    )
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(value)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
        _fsync_directory(path.parent)
    except BaseException:
        temp_path.unlink(missing_ok=True)
        raise


def _atomic_write_text(path: Path, value: str) -> None:
    _atomic_write_bytes(path, value.encode("utf-8"))


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _valid_sha256(value: object) -> bool:
    return isinstance(value, str) and SHA256_RE.fullmatch(value) is not None


def _is_link_like(path: Path, info: os.stat_result | None = None) -> bool:
    details = info or path.lstat()
    if stat.S_ISLNK(details.st_mode):
        return True
    if hasattr(path, "is_junction") and path.is_junction():
        return True
    attributes = getattr(details, "st_file_attributes", 0)
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    return bool(reparse_flag and attributes & reparse_flag)


def _validate_authorized_rel(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise PlanError("transaction path는 비어 있지 않은 문자열이어야 합니다.")
    if "\\" in value or "\0" in value or any(ord(char) < 32 for char in value):
        raise PlanError(f"transaction path에 금지 문자가 있습니다: {value!r}")
    pure = PurePosixPath(value)
    if pure.is_absolute() or value != pure.as_posix() or ".." in pure.parts:
        raise PlanError(f"transaction path는 정규화된 상대 경로여야 합니다: {value!r}")
    if value == SITEMAP_NAME:
        return value
    parts = pure.parts
    if (
        len(parts) != 4
        or parts[0] != SUBJECT_ROOT_NAME
        or parts[1] not in CATEGORY_BY_DIR
        or not parts[2]
        or parts[2] in {".", ".."}
        or ":" in parts[2]
        or parts[3] != "index.html"
    ):
        raise PlanError(f"승인된 school detail 경로 형식이 아닙니다: {value!r}")
    return value


def _safe_join(base: Path, rel: str) -> Path:
    rel = _validate_authorized_rel(rel)
    if base.exists() and _is_link_like(base):
        raise PlanError(f"승인된 base가 symlink입니다: {base}")
    base_resolved = base.resolve()
    candidate = base.joinpath(*PurePosixPath(rel).parts)
    try:
        candidate.resolve(strict=False).relative_to(base_resolved)
    except ValueError as exc:
        raise PlanError(f"경로가 승인된 base 밖으로 이탈합니다: {rel}") from exc
    current = base
    for part in PurePosixPath(rel).parts:
        current = current / part
        if current.exists() and _is_link_like(current):
            raise PlanError(f"transaction 경로에 symlink가 있습니다: {current}")
    return candidate


def _require_regular_file(path: Path, label: str) -> None:
    try:
        info = path.lstat()
    except FileNotFoundError as exc:
        raise PlanError(f"{label} 파일이 없습니다: {path}") from exc
    if _is_link_like(path, info) or not stat.S_ISREG(info.st_mode):
        raise PlanError(f"{label}은 symlink가 아닌 일반 파일이어야 합니다: {path}")


def _transaction_allowlist(root: Path) -> set[str]:
    allowed = set(_relative_target_paths(root))
    sitemap = root / SITEMAP_NAME
    _require_regular_file(sitemap, "authorized sitemap")
    allowed.add(SITEMAP_NAME)
    if len(allowed) != EXPECTED_PAGE_COUNT + 1:
        raise PlanError(f"transaction allowlist cardinality 오류: {len(allowed)}")
    return allowed


def _validate_manifest(
    value: object, label: str, allowed_paths: set[str] | None = None
) -> dict[str, str]:
    if not isinstance(value, dict):
        raise PlanError(f"{label}는 object여야 합니다.")
    result: dict[str, str] = {}
    for raw_path, raw_hash in value.items():
        rel = _validate_authorized_rel(raw_path)
        if allowed_paths is not None and rel not in allowed_paths:
            raise PlanError(f"{label} path가 discovered allowlist 밖입니다: {rel}")
        if rel in result:
            raise PlanError(f"{label} path 중복: {rel}")
        if not _valid_sha256(raw_hash):
            raise PlanError(f"{label} SHA-256 형식 오류: {rel}")
        result[rel] = raw_hash
    if not result:
        raise PlanError(f"{label}가 비었습니다.")
    return result


def _validate_transaction_directory(root: Path, transaction_dir: Path) -> str:
    match = TRANSACTION_NAME_RE.fullmatch(transaction_dir.name)
    if not match:
        raise PlanError(f"transaction 폴더 이름 오류: {transaction_dir.name}")
    try:
        info = transaction_dir.lstat()
    except FileNotFoundError as exc:
        raise PlanError(f"transaction 폴더가 없습니다: {transaction_dir}") from exc
    if _is_link_like(transaction_dir, info) or not stat.S_ISDIR(info.st_mode):
        raise PlanError(f"transaction은 symlink가 아닌 폴더여야 합니다: {transaction_dir}")
    try:
        transaction_dir.resolve().relative_to(root.resolve())
    except ValueError as exc:
        raise PlanError(f"transaction 폴더가 root 밖입니다: {transaction_dir}") from exc
    return match.group(1)


def _validate_journal(
    root: Path,
    transaction_dir: Path,
    allowed_paths: set[str] | None = None,
) -> ValidatedJournal:
    transaction_id = _validate_transaction_directory(root, transaction_dir)
    journal_path = transaction_dir / "journal.json"
    _require_regular_file(journal_path, "transaction journal")
    raw = journal_path.read_bytes()
    if len(raw) > 10 * 1024 * 1024:
        raise PlanError(f"transaction journal이 비정상적으로 큽니다: {len(raw)}")
    def reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict:
        result: dict = {}
        for key, value in pairs:
            if key in result:
                raise PlanError(f"transaction journal JSON key 중복: {key}")
            result[key] = value
        return result

    try:
        data = json.loads(
            raw.decode("utf-8"), object_pairs_hook=reject_duplicate_keys
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PlanError(f"transaction journal parse 오류: {journal_path}") from exc
    if not isinstance(data, dict) or set(data) != JOURNAL_KEYS:
        raise PlanError(f"transaction journal key 오류: {journal_path}")
    if type(data["version"]) is not int or data["version"] != JOURNAL_VERSION:
        raise PlanError(f"transaction journal version 오류: {data['version']!r}")
    if data["transaction_id"] != transaction_id:
        raise PlanError("transaction journal id가 폴더 이름과 다릅니다.")
    status = data["status"]
    if not isinstance(status, str) or status not in JOURNAL_STATES:
        raise PlanError(f"transaction journal status 오류: {status!r}")
    if not _valid_sha256(data["source_sha256"]):
        raise PlanError("transaction source SHA-256 형식 오류")
    allowed = allowed_paths if allowed_paths is not None else _transaction_allowlist(root)
    before_manifest = _validate_manifest(
        data["before_manifest"], "before_manifest", allowed
    )
    after_manifest = _validate_manifest(
        data["after_manifest"], "after_manifest", allowed
    )
    if set(before_manifest) != set(after_manifest):
        raise PlanError("transaction before/after manifest key set 불일치")

    raw_entries = data["entries"]
    if not isinstance(raw_entries, list) or not raw_entries:
        raise PlanError("transaction entries는 비어 있지 않은 array여야 합니다.")
    entries: list[JournalEntry] = []
    seen: set[str] = set()
    for raw_entry in raw_entries:
        if not isinstance(raw_entry, dict) or set(raw_entry) != JOURNAL_ENTRY_KEYS:
            raise PlanError("transaction entry key/type 오류")
        rel = _validate_authorized_rel(raw_entry["path"])
        if rel not in allowed:
            raise PlanError(f"transaction entry가 discovered allowlist 밖입니다: {rel}")
        if rel in seen:
            raise PlanError(f"transaction entry path 중복: {rel}")
        seen.add(rel)
        hashes = [
            raw_entry["before_sha256"],
            raw_entry["after_sha256"],
            raw_entry["backup_sha256"],
            raw_entry["stage_sha256"],
        ]
        if not all(_valid_sha256(value) for value in hashes):
            raise PlanError(f"transaction entry SHA-256 형식 오류: {rel}")
        entry = JournalEntry(
            path=rel,
            before_sha256=raw_entry["before_sha256"],
            after_sha256=raw_entry["after_sha256"],
            backup_sha256=raw_entry["backup_sha256"],
            stage_sha256=raw_entry["stage_sha256"],
        )
        if entry.before_sha256 == entry.after_sha256:
            raise PlanError(f"transaction entry before/after가 같습니다: {rel}")
        if entry.backup_sha256 != entry.before_sha256:
            raise PlanError(f"transaction backup SHA가 before와 다릅니다: {rel}")
        if entry.stage_sha256 != entry.after_sha256:
            raise PlanError(f"transaction stage SHA가 after와 다릅니다: {rel}")
        if before_manifest.get(rel) != entry.before_sha256:
            raise PlanError(f"transaction before manifest/entry 불일치: {rel}")
        if after_manifest.get(rel) != entry.after_sha256:
            raise PlanError(f"transaction after manifest/entry 불일치: {rel}")
        entries.append(entry)
    if seen != set(before_manifest):
        raise PlanError("transaction entries/manifest path set 불일치")
    path_parts = [(entry.path, PurePosixPath(entry.path).parts) for entry in entries]
    for index, (left_name, left_parts) in enumerate(path_parts):
        for right_name, right_parts in path_parts[index + 1 :]:
            width = min(len(left_parts), len(right_parts))
            if left_parts[:width] == right_parts[:width]:
                raise PlanError(
                    f"transaction entry path ancestor/overlap: {left_name} / {right_name}"
                )
    return ValidatedJournal(
        transaction_id=transaction_id,
        status=status,
        source_sha256=data["source_sha256"],
        entries=tuple(entries),
        before_manifest=before_manifest,
        after_manifest=after_manifest,
    )


def _validate_transaction_state(
    root: Path, transaction_dir: Path, journal: ValidatedJournal
) -> dict[str, str]:
    """Validate every file/hash before recovery is allowed to mutate anything."""

    classifications: dict[str, str] = {}
    stage_root = transaction_dir / "stage"
    backup_root = transaction_dir / "backup"
    for entry in journal.entries:
        target = _safe_join(root, entry.path)
        backup = _safe_join(backup_root, entry.path)
        stage = _safe_join(stage_root, entry.path)
        _require_regular_file(target, "transaction target")
        _require_regular_file(backup, "transaction backup")
        if _sha256_file(backup) != entry.backup_sha256:
            raise PlanError(f"transaction backup hash mismatch: {entry.path}")
        target_hash = _sha256_file(target)
        stage_exists = stage.exists()
        if stage_exists:
            _require_regular_file(stage, "transaction stage")
            if _sha256_file(stage) != entry.stage_sha256:
                raise PlanError(f"transaction stage hash mismatch: {entry.path}")

        if journal.status == "prepared":
            if target_hash != entry.before_sha256 or not stage_exists:
                raise PlanError(f"prepared transaction state mismatch: {entry.path}")
            classifications[entry.path] = "before"
        elif journal.status == "committing":
            if target_hash == entry.before_sha256 and stage_exists:
                classifications[entry.path] = "before"
            elif target_hash == entry.after_sha256 and not stage_exists:
                classifications[entry.path] = "after"
            else:
                raise PlanError(f"committing transaction state mismatch: {entry.path}")
        else:
            if target_hash != entry.after_sha256 or stage_exists:
                raise PlanError(f"committed transaction state mismatch: {entry.path}")
            classifications[entry.path] = "after"
    return classifications


def _journal_payload(
    transaction_id: str,
    status: str,
    source_sha256: str,
    entries: Sequence[JournalEntry],
) -> dict:
    before = {entry.path: entry.before_sha256 for entry in entries}
    after = {entry.path: entry.after_sha256 for entry in entries}
    return {
        "version": JOURNAL_VERSION,
        "transaction_id": transaction_id,
        "status": status,
        "source_sha256": source_sha256,
        "entries": [
            {
                "path": entry.path,
                "before_sha256": entry.before_sha256,
                "after_sha256": entry.after_sha256,
                "backup_sha256": entry.backup_sha256,
                "stage_sha256": entry.stage_sha256,
            }
            for entry in entries
        ],
        "before_manifest": before,
        "after_manifest": after,
    }


def _write_journal(
    transaction_dir: Path,
    transaction_id: str,
    status: str,
    source_sha256: str,
    entries: Sequence[JournalEntry],
) -> None:
    if status not in JOURNAL_STATES:
        raise PlanError(f"journal status 쓰기 거부: {status}")
    payload = _journal_payload(
        transaction_id, status, source_sha256, entries
    )
    _atomic_write_text(
        transaction_dir / "journal.json",
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )


@contextlib.contextmanager
def _repo_apply_lock(root: Path):
    lock_key = hashlib.sha256(str(root.resolve()).casefold().encode("utf-8")).hexdigest()[:24]
    lock_path = Path(tempfile.gettempdir()) / f"hakseup-school-apply-{lock_key}.lock"
    if lock_path.exists() and _is_link_like(lock_path):
        raise PlanError(f"apply lock이 symlink입니다: {lock_path}")
    flags = os.O_CREAT | os.O_RDWR
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(lock_path, flags, 0o600)
    handle = os.fdopen(descriptor, "r+b", buffering=0)
    acquired = False
    try:
        info = os.fstat(handle.fileno())
        if not stat.S_ISREG(info.st_mode):
            raise PlanError(f"apply lock이 일반 파일이 아닙니다: {lock_path}")
        if info.st_size == 0:
            handle.write(b"0")
            handle.flush()
            os.fsync(handle.fileno())
        handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            acquired = True
        except (OSError, BlockingIOError) as exc:
            raise PlanError("다른 school manuscript apply/recovery가 실행 중입니다.") from exc
        yield
    finally:
        if acquired:
            handle.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        handle.close()


def _remove_transaction_dir(root: Path, transaction_dir: Path) -> None:
    _validate_transaction_directory(root, transaction_dir)
    shutil.rmtree(transaction_dir)
    _fsync_directory(root)


def _recover_one_transaction_locked(
    root: Path,
    transaction_dir: Path,
    allowed_paths: set[str] | None = None,
) -> str:
    journal = _validate_journal(root, transaction_dir, allowed_paths)
    classifications = _validate_transaction_state(root, transaction_dir, journal)
    if journal.status == "committing":
        backup_root = transaction_dir / "backup"
        # All paths/hashes were validated above.  Recheck each input immediately
        # before its atomic restore to narrow the TOCTOU window.
        for entry in journal.entries:
            target = _safe_join(root, entry.path)
            backup = _safe_join(backup_root, entry.path)
            if _sha256_file(backup) != entry.before_sha256:
                raise PlanError(f"rollback 직전 backup 변경: {entry.path}")
            current_hash = _sha256_file(target)
            if current_hash not in {entry.before_sha256, entry.after_sha256}:
                raise PlanError(f"rollback 직전 target 변경: {entry.path}")
            if classifications[entry.path] == "after":
                _atomic_write_bytes(target, backup.read_bytes())
        for entry in journal.entries:
            target = _safe_join(root, entry.path)
            if _sha256_file(target) != entry.before_sha256:
                raise PlanError(f"rollback 결과 hash mismatch: {entry.path}")
    _remove_transaction_dir(root, transaction_dir)
    return transaction_dir.name


def _validate_abandoned_preps_locked(root: Path) -> list[Path]:
    validated: list[Path] = []
    for prep in sorted(root.glob(".school-manuscripts-prep-*")):
        if not PREP_NAME_RE.fullmatch(prep.name):
            raise PlanError(f"유효하지 않은 prep 폴더 이름: {prep.name}")
        info = prep.lstat()
        if _is_link_like(prep, info) or not stat.S_ISDIR(info.st_mode):
            raise PlanError(f"prep은 symlink가 아닌 폴더여야 합니다: {prep}")
        validated.append(prep)
    return validated


def _remove_validated_preps_locked(root: Path, preps: Sequence[Path]) -> list[str]:
    removed: list[str] = []
    for prep in preps:
        # Repeat the top-level check immediately before deletion.
        info = prep.lstat()
        if _is_link_like(prep, info) or not PREP_NAME_RE.fullmatch(prep.name):
            raise PlanError(f"prep 삭제 직전 검증 오류: {prep}")
        shutil.rmtree(prep)
        removed.append(prep.name)
    if removed:
        _fsync_directory(root)
    return removed


def _recover_pending_transactions_locked(root: Path) -> list[str]:
    preps = _validate_abandoned_preps_locked(root)
    candidates = sorted(root.glob(".school-manuscripts-txn-*"))
    if len(candidates) > 1:
        raise PlanError(
            f"동시에 둘 이상의 pending transaction은 복구하지 않습니다: "
            f"{[path.name for path in candidates]}"
        )
    allowed = _transaction_allowlist(root)
    # Validate every journal and every referenced file before the first recovery
    # mutation.  A corrupt journal therefore cannot even delete an abandoned prep.
    for transaction_dir in candidates:
        journal = _validate_journal(root, transaction_dir, allowed)
        _validate_transaction_state(root, transaction_dir, journal)
    recovered = _remove_validated_preps_locked(root, preps)
    for transaction_dir in candidates:
        recovered.append(
            _recover_one_transaction_locked(root, transaction_dir, allowed)
        )
    return recovered


def recover_pending_transactions(root: str | Path) -> list[str]:
    """Strictly validate, then recover interrupted generator transactions."""

    root_path = Path(root).resolve()
    if not root_path.is_dir():
        raise PlanError(f"recovery root 폴더가 없습니다: {root_path}")
    with _repo_apply_lock(root_path):
        return _recover_pending_transactions_locked(root_path)


def _verify_manifest_on_disk(root: Path, manifest: Mapping[str, str], label: str) -> None:
    for raw_rel, expected_hash in manifest.items():
        rel = _validate_authorized_rel(raw_rel)
        if not _valid_sha256(expected_hash):
            raise PlanError(f"{label} manifest SHA 형식 오류: {rel}")
        target = _safe_join(root, rel)
        _require_regular_file(target, f"{label} target")
        if _sha256_file(target) != expected_hash:
            raise PlanError(f"{label} manifest mismatch: {rel}")


def apply_plan(
    plan: BuildPlan,
    root: str | Path,
    *,
    expected_source_sha256: str,
    expected_before_manifest: Mapping[str, str],
) -> None:
    """Apply exactly a frozen plan under an exclusive, recoverable transaction."""

    root_path = Path(root).resolve()
    if expected_source_sha256 != plan.source_sha256 or not _valid_sha256(
        expected_source_sha256
    ):
        raise PlanError("APPLY source SHA가 dry-run freeze와 다릅니다.")
    if dict(expected_before_manifest) != plan.before_manifest:
        raise PlanError("APPLY before manifest가 dry-run freeze와 다릅니다.")
    if plan.second_pass_changes:
        raise PlanError("idempotence 실패 plan은 적용할 수 없습니다.")
    authorized = set(plan.authorized_documents)
    if authorized != set(plan.before_manifest) or authorized != set(plan.after_manifest):
        raise PlanError("plan authorized/before/after set 불일치")
    changed = tuple(plan.changed_paths)
    if len(changed) != len(set(changed)) or not set(changed).issubset(authorized):
        raise PlanError("plan changed_paths 중복/범위 오류")
    for rel in authorized:
        _validate_authorized_rel(rel)
        if not _valid_sha256(plan.before_manifest[rel]) or not _valid_sha256(
            plan.after_manifest[rel]
        ):
            raise PlanError(f"plan manifest SHA 형식 오류: {rel}")
        if _sha256_text(plan.authorized_documents[rel]) != plan.after_manifest[rel]:
            raise PlanError(f"plan document/after manifest 불일치: {rel}")

    with _repo_apply_lock(root_path):
        allowed = _transaction_allowlist(root_path)
        if authorized != allowed:
            raise PlanError(
                "plan authorized set이 discovered 2,968 detail+sitemap allowlist와 다릅니다."
            )
        _recover_pending_transactions_locked(root_path)
        _verify_manifest_on_disk(root_path, plan.before_manifest, "freeze-before")
        if not changed:
            return

        transaction_id = uuid.uuid4().hex
        prep_dir = root_path / f".school-manuscripts-prep-{transaction_id}"
        transaction_dir = root_path / f".school-manuscripts-txn-{transaction_id}"
        prep_dir.mkdir(parents=False)
        _fsync_directory(root_path)
        entries: list[JournalEntry] = []
        renamed = False
        try:
            stage_root = prep_dir / "stage"
            backup_root = prep_dir / "backup"
            for rel in changed:
                target = _safe_join(root_path, rel)
                _require_regular_file(target, "apply target")
                before_hash = plan.before_manifest[rel]
                after_hash = plan.after_manifest[rel]
                if before_hash == after_hash:
                    raise PlanError(f"changed path의 before/after가 같습니다: {rel}")
                if _sha256_file(target) != before_hash:
                    raise PlanError(f"stage 직전 target 변경: {rel}")
                stage = _safe_join(stage_root, rel)
                backup = _safe_join(backup_root, rel)
                _atomic_write_bytes(stage, plan.authorized_documents[rel].encode("utf-8"))
                _atomic_write_bytes(backup, target.read_bytes())
                entry = JournalEntry(
                    path=rel,
                    before_sha256=before_hash,
                    after_sha256=after_hash,
                    backup_sha256=before_hash,
                    stage_sha256=after_hash,
                )
                if _sha256_file(stage) != after_hash or _sha256_file(backup) != before_hash:
                    raise PlanError(f"stage/backup 생성 hash mismatch: {rel}")
                entries.append(entry)
            _write_journal(
                prep_dir,
                transaction_id,
                "prepared",
                plan.source_sha256,
                entries,
            )
            os.replace(prep_dir, transaction_dir)
            renamed = True
            _fsync_directory(root_path)
            prepared = _validate_journal(root_path, transaction_dir, allowed)
            _validate_transaction_state(root_path, transaction_dir, prepared)

            # Recheck the complete freeze immediately before the first swap.
            _verify_manifest_on_disk(root_path, plan.before_manifest, "commit-before")
            _write_journal(
                transaction_dir,
                transaction_id,
                "committing",
                plan.source_sha256,
                entries,
            )
            for entry in entries:
                target = _safe_join(root_path, entry.path)
                stage = _safe_join(transaction_dir / "stage", entry.path)
                _require_regular_file(target, "commit target")
                _require_regular_file(stage, "commit stage")
                if _sha256_file(target) != entry.before_sha256:
                    raise PlanError(f"swap 직전 target 변경: {entry.path}")
                if _sha256_file(stage) != entry.after_sha256:
                    raise PlanError(f"swap 직전 stage 변경: {entry.path}")
                os.replace(stage, target)
                _fsync_directory(target.parent)

            _verify_manifest_on_disk(root_path, plan.after_manifest, "commit-after")
            _write_journal(
                transaction_dir,
                transaction_id,
                "committed",
                plan.source_sha256,
                entries,
            )
            committed = _validate_journal(root_path, transaction_dir, allowed)
            _validate_transaction_state(root_path, transaction_dir, committed)
            _remove_transaction_dir(root_path, transaction_dir)
        except BaseException as original:
            try:
                if renamed and transaction_dir.exists():
                    _recover_one_transaction_locked(
                        root_path, transaction_dir, allowed
                    )
                elif prep_dir.exists():
                    info = prep_dir.lstat()
                    if _is_link_like(prep_dir, info) or not PREP_NAME_RE.fullmatch(prep_dir.name):
                        raise PlanError("실패한 prep 경로 검증 오류")
                    shutil.rmtree(prep_dir)
                    _fsync_directory(root_path)
            except BaseException as recovery_error:
                raise PlanError(
                    f"APPLY 실패 후 자동 복구도 실패했습니다; transaction을 보존합니다: "
                    f"{transaction_dir}: original={original!r}"
                ) from recovery_error
            raise


def _manifest_digest(manifest: Mapping[str, str]) -> str:
    packed = "".join(f"{key}\0{manifest[key]}\n" for key in sorted(manifest))
    return _sha256_text(packed)


def _summary(plan: BuildPlan) -> dict:
    return {
        "source_sha256": plan.source_sha256,
        "before_manifest_sha256": _manifest_digest(plan.before_manifest),
        "after_manifest_sha256": _manifest_digest(plan.after_manifest),
        "authorized_documents": len(plan.authorized_documents),
        "changed_paths": len(plan.changed_paths),
        "second_pass_changes": len(plan.second_pass_changes),
        "diagnostics": plan.diagnostics,
    }


def _default_common_dir(root: Path) -> Path:
    return root.parent / "참고자료" / "공통자료"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--common-dir", type=Path)
    parser.add_argument("--apply", action="store_true", help="frozen plan을 실제 적용")
    parser.add_argument("--go", default="", help="apply safety token; literal APPLY-GO")
    parser.add_argument("--expected-source-sha256", default="")
    parser.add_argument(
        "--freeze-file",
        type=Path,
        help="apply 시 full before_manifest를 읽을 JSON; dry-run은 summary만 출력",
    )
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args(argv)
    root = args.root.resolve()
    common_dir = (args.common_dir or _default_common_dir(root)).resolve()
    plan = build_plan(root, common_dir)
    if args.apply:
        if args.go != "APPLY-GO":
            raise PlanError("실제 적용에는 --go APPLY-GO가 필요합니다.")
        if not args.expected_source_sha256 or not args.freeze_file:
            raise PlanError(
                "실제 적용에는 --expected-source-sha256와 --freeze-file이 필요합니다."
            )
        freeze = json.loads(args.freeze_file.read_text(encoding="utf-8"))
        apply_plan(
            plan,
            root,
            expected_source_sha256=args.expected_source_sha256,
            expected_before_manifest=freeze["before_manifest"],
        )
    print(
        json.dumps(
            _summary(plan),
            ensure_ascii=False,
            indent=2 if args.pretty else None,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except PlanError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
