from __future__ import annotations

"""Add source-grounded search-intent guidance to 742 middle subject pages.

The default mode is a validated dry run.  ``--apply`` writes only the 371
middle-English and 371 middle-math detail pages.  Existing authored copy,
school-source disclosures, FAQ, local link network, and canonical URLs are
preserved byte-for-byte outside this script's marked block and JSON-LD node.
"""

import argparse
import hashlib
import html
import itertools
import json
import re
import statistics
from collections import Counter
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RELEASE_DATE = "2026-08-27"
START_MARKER = "<!-- priority-search-intent:start -->"
END_MARKER = "<!-- priority-search-intent:end -->"
CATEGORIES = {
    "중등영어학원": "영어",
    "중등수학학원": "수학",
}

BLOCK_RE = re.compile(
    re.escape(START_MARKER) + r".*?" + re.escape(END_MARKER), re.I | re.S
)
QUICK_ANSWER_RE = re.compile(
    r'<section\b[^>]*class="[^"]*subject-quick-answer[^"]*"[^>]*>.*?</section>',
    re.I | re.S,
)
SCHOOL_RE = re.compile(
    r"<!-- school-reference:start -->.*?<!-- school-reference:end -->", re.I | re.S
)
JSONLD_RE = re.compile(
    r'(<script\b[^>]*type=["\']application/ld\+json["\'][^>]*>)(.*?)(</script>)',
    re.I | re.S,
)
DATE_RE = re.compile(
    r'("dateModified"\s*:\s*")[0-9]{4}-[0-9]{2}-[0-9]{2}(")'
)
TAG_RE = re.compile(r"<[^>]+>")
SCRIPT_STYLE_RE = re.compile(
    r"<(?:script|style|header|footer|nav|noscript|svg)\b.*?</(?:script|style|header|footer|nav|noscript|svg)>",
    re.I | re.S,
)


@dataclass(frozen=True)
class Context:
    path: Path
    before: str
    category: str
    subject: str
    ordinal: int
    canonical: str
    title: str
    locality: str
    center: str
    address: str
    grades: str
    schools: tuple[str, ...]
    school_state: str
    school_fact: str
    focus: str
    theme: str


@dataclass(frozen=True)
class Card:
    label: str
    heading: str
    body: str
    items: tuple[str, ...]


@dataclass(frozen=True)
class Plan:
    context: Context
    after: str
    cards: tuple[Card, ...]


def clean(value: str) -> str:
    return re.sub(
        r"\s+", " ", html.unescape(TAG_RE.sub(" ", value or ""))
    ).strip()


def attr(source: str, name: str) -> str:
    match = re.search(rf'\b{re.escape(name)}="([^"]*)"', source, re.I)
    return html.unescape(match.group(1)) if match else ""


def first(pattern: str, source: str, flags: int = re.I | re.S) -> str:
    match = re.search(pattern, source, flags)
    return clean(match.group(1)) if match else ""


def stable_number(value: str, salt: str) -> int:
    return int(
        hashlib.sha256(f"{value}|{salt}".encode("utf-8")).hexdigest()[:12], 16
    )


def choose(context: Context, salt: str, values: tuple[str, ...]) -> str:
    if not values:
        raise ValueError(f"빈 문장 후보: {salt}")
    multipliers = (1, 3, 5, 7, 9, 11, 13, 15)
    multiplier = multipliers[stable_number(context.category, salt) % len(multipliers)]
    offset = stable_number(context.category, salt + "|offset") % len(values)
    return values[(context.ordinal * multiplier + offset) % len(values)]


def with_particle(value: str, consonant: str, vowel: str) -> str:
    """Attach the correct Korean particle to the final Hangul syllable."""
    last = next((char for char in reversed(value) if "가" <= char <= "힣"), "")
    has_batchim = bool(last) and (ord(last) - ord("가")) % 28 != 0
    return value + (consonant if has_batchim else vowel)


def extract_context(
    path: Path, category: str, subject: str, ordinal: int
) -> Context:
    source = path.read_text(encoding="utf-8", errors="strict")
    title = first(r"<h1\b[^>]*>(.*?)</h1>", source)
    locality = re.sub(rf"\s*중등\s*{subject}학원\s*$", "", title).strip()
    canonical = first(
        r'<link\b(?=[^>]*\brel="canonical")[^>]*\bhref="([^"]+)"', source
    )
    center = first(r"<dt>센터 기준</dt>\s*<dd>(.*?)</dd>", source)
    address = first(r"<dt>확인된 주소</dt>\s*<dd>(.*?)</dd>", source)
    grades = first(
        rf"<dt>{subject}\s*가능\s*중등\s*학년</dt>\s*<dd>(.*?)</dd>", source
    )
    school_block = SCHOOL_RE.search(source)
    school_html = school_block.group(0) if school_block else ""
    schools = tuple(
        dict.fromkeys(
            html.unescape(value)
            for value in re.findall(r'data-source-school="([^"]+)"', school_html)
        )
    )
    card_match = re.search(
        r'(<section\b[^>]*class="[^"]*wawa-school-card[^"]*"[^>]*>)',
        school_html,
        re.I,
    )
    card_tag = card_match.group(1) if card_match else ""
    school_state = attr(card_tag, "data-source-state") or "unknown"
    school_fact = first(
        r"<span\b[^>]*data-school-source-fact[^>]*>(.*?)</span>", school_html
    )
    focus = first(r"우선\s*확인할\s*영역은\s*(.*?)입니다", source)
    if not focus:
        focus = "어휘·문법·독해의 연결" if subject == "영어" else "개념·유형·풀이의 연결"
    headings = [
        clean(value)
        for value in re.findall(
            r'<section\b[^>]*class="subject-copy-section"[^>]*>\s*<h2>(.*?)</h2>',
            source,
            re.I | re.S,
        )
    ]
    theme = next(
        (
            re.sub(rf"^{re.escape(locality)}\s+", "", heading).strip()
            for heading in headings
            if subject in heading and "최종 체크" not in heading and "점검 순서" not in heading
        ),
        f"중등 {subject} 현재 상태 확인",
    )
    required = {
        "title": title,
        "locality": locality,
        "canonical": canonical,
        "center": center,
        "address": address,
        "school block": school_html,
        "school fact": school_fact,
    }
    missing = [name for name, value in required.items() if not value]
    if missing:
        raise ValueError(f"{path.relative_to(ROOT)}: 추출 실패 {missing}")
    return Context(
        path=path,
        before=source,
        category=category,
        subject=subject,
        ordinal=ordinal,
        canonical=canonical,
        title=title,
        locality=locality,
        center=center,
        address=address,
        grades=grades or "중등 가능 학년 상담 확인",
        schools=schools,
        school_state=school_state,
        school_fact=school_fact,
        focus=focus,
        theme=theme,
    )


def contexts() -> list[Context]:
    result: list[Context] = []
    for category, subject in CATEGORIES.items():
        paths = sorted((ROOT / "과목별학원" / category).glob("*/index.html"))
        if len(paths) != 371:
            raise ValueError(f"{category}: 상세 페이지 {len(paths)}/371")
        result.extend(
            extract_context(path, category, subject, ordinal)
            for ordinal, path in enumerate(paths)
        )
    return result


def school_summary(context: Context) -> str:
    if context.schools:
        shown = "·".join(context.schools[:4])
        suffix = f" 등 {len(context.schools)}곳" if len(context.schools) > 4 else ""
        return f"원자료에 기재된 중학교는 {shown}{suffix}입니다."
    if context.school_state == "coverage":
        return "원자료는 개별 학교명 대신 지역 단위 가능 범위를 제시합니다."
    return "원자료에는 개별 중학교명이 기재되어 있지 않습니다."


def intro_copy(context: Context) -> str:
    s = context.subject
    options = (
        f"{context.locality}에서 중등 {s}학원을 비교할 때는 광고 문구보다 최근 답안, 학교 범위, 집에서 가능한 복습 시간을 같은 순서로 확인해야 합니다.",
        f"{context.title} 상담의 출발점은 학생이 이미 아는 내용과 혼자 재현하지 못하는 내용을 답안에서 나누는 일입니다.",
        f"{context.theme}라는 학습 초점을 실제 상담 질문과 선택 기준으로 바꾸어 정리했습니다.",
        f"{context.locality} 중학생의 {s} 학습은 학년만 같다고 시작점이 같지 않습니다. 최근 두 번의 평가 기록을 먼저 대조하세요.",
        f"센터 위치와 가능 학년을 확인한 뒤에는 학생의 학교 일정과 {context.focus} 기록이 계획에 어떻게 반영되는지 물어보세요.",
        f"{context.title}를 알아보는 학부모가 서로 다른 답변을 비교할 수 있도록 진단·내신·복습·상담 기록의 네 기준을 제시합니다.",
        f"새 교재를 선택하기 전에 현재 교재와 시험지에서 {with_particle(context.focus, '이', '가')} 실제로 막힌 지점을 표시해 보세요.",
        f"{context.locality} 중등 {s} 상담은 점수 하나가 아니라 풀이·답안 흔적, 학교 자료, 재확인 날짜를 함께 보아야 구체적입니다.",
        f"페이지에 확인된 사실과 상담에서 새로 확인할 조건을 분리하면 {context.title}의 현재 운영과 학생의 필요를 혼동하지 않습니다.",
        f"중등 {s}학원 선택 전에 ‘무엇을 배우나’와 ‘어떻게 확인하나’를 나누어 질문하면 답변을 실제 주간 계획으로 비교할 수 있습니다.",
        f"{context.locality} 학교 시험 준비와 누적 {s} 실력을 같은 계획으로 묶기 전에 각각의 완료 조건부터 확인하세요.",
        f"{context.title} 페이지의 학년·학교 근거를 학생의 최근 기록과 연결해 첫 2주의 확인 항목을 구체화했습니다.",
        f"상담에서 교재명만 메모하지 말고 {context.focus}, 학교 범위 반영 방법, 오답 재확인 시점을 같은 표에 적어 보세요.",
        f"{context.locality} 중학생에게 필요한 {s} 수업을 찾으려면 현재 오류, 시험 일정, 복습 가능 시간의 순서로 질문을 준비하는 편이 좋습니다.",
        f"{context.center}의 확인된 정보에 학생별 진단 질문을 더하면 비교 기준을 구체적으로 정할 수 있습니다.",
        f"{context.title} 상담 전에는 최근 자료 세 가지와 학생이 바꾸고 싶은 학습 행동 한 가지를 함께 준비하세요.",
    )
    return choose(context, "intro", options)


def subject_actions(context: Context) -> dict[str, tuple[str, ...]]:
    if context.subject == "영어":
        return {
            "diagnosis": (
                "정답을 가린 뒤 어휘 뜻, 문장 구조, 선택 근거를 학생이 어느 단계까지 혼자 설명하는지 확인하세요.",
                "최근 시험지의 오류를 어휘·문법·독해·서술형으로 나누고 처음 설명이 끊긴 칸에 표시하세요.",
                "맞힌 문제도 근거 문장을 찾지 못했다면 완료로 보지 말고 같은 기준으로 낯선 지문을 다시 확인하세요.",
                "본문 암기와 낯선 지문 독해를 분리해 각각 근거 표시와 한 문장 요약이 가능한지 살펴보세요.",
                "서술형 답안에서 요구 조건, 핵심 표현, 어순·시제를 차례로 대조해 빠진 항목을 기록하세요.",
                "단어를 외운 날과 실제 문장에서 의미를 고른 날을 구분해 누적 어휘의 재사용 여부를 확인하세요.",
                "긴 문장은 모르는 단어부터 찾기 전에 주어·동사와 수식 관계를 먼저 표시하게 해 보세요.",
                "오답 선택지가 왜 틀렸는지 문법 근거와 내용 근거로 나누어 설명할 수 있는지 확인하세요.",
                "듣기에서 놓친 구간은 대본 확인, 다시 듣기, 핵심어 기록의 순서가 남아 있는지 살펴보세요.",
                "첫 답안과 수정 답안을 나란히 놓고 학생이 바꾼 이유를 말할 수 있는 문장 수를 세어 보세요.",
                "학교 본문 해석과 누적 독해에서 같은 문장 구조 오류가 반복되는지 두 자료를 함께 비교하세요.",
                "문법 규칙 이름을 아는 것과 새 문장에 적용하는 것을 분리해 짧은 재작성으로 확인하세요.",
                "시험 직전 문제 수보다 오답 근거를 다시 설명한 횟수와 날짜가 기록되어 있는지 확인하세요.",
                "어휘·문법·독해를 따로 평가한 뒤 한 지문에서 세 영역을 연결할 수 있는지 다시 살펴보세요.",
                "정답률이 비슷한 두 시험에서 빈 문제와 근거 없이 고른 문제의 비율이 어떻게 달라졌는지 확인하세요.",
                "학생이 어려웠다고 말한 문장과 실제로 풀이가 멈춘 문장이 같은지 답안 흔적으로 대조하세요.",
            ),
            "exam": (
                "학교 본문 진도와 누적 어휘 복습을 다른 날짜에 배치하고 밀린 항목을 별도로 표시하세요.",
                "범위표의 단원마다 어휘·문법·서술형 준비 자료를 한 줄씩 연결해 누락을 확인하세요.",
                "학교별 시험 범위는 학생이 받은 최신 공지를 기준으로 하고 페이지의 학교명은 대조용으로만 사용하세요.",
                "본문 암기 여부와 변형 문장 적용 여부를 구분해 학교 시험 준비가 한쪽에 치우치지 않게 하세요.",
                "수행평가와 지필평가 일정을 먼저 고정한 뒤 누적 독해 시간을 남겨 둘 수 있는지 확인하세요.",
                "교과서 문장만 반복하지 말고 같은 문법과 어휘가 쓰인 새 문장으로 적용 여부를 대조하세요.",
                "최근 학교 시험에서 감점된 서술형 조건을 목록으로 만들고 다음 답안에 모두 반영됐는지 확인하세요.",
                "시험 범위의 어휘를 뜻 암기·문장 재사용·오답 재확인의 세 칸으로 나누어 완료 기준을 정하세요.",
                "학교 일정이 바뀌었을 때 유지할 누적 복습과 이동할 시험 준비를 구분해 계획을 조정하세요.",
                "중1·중2·중3의 같은 단원도 평가 방식이 다를 수 있으므로 학생의 실제 범위표를 먼저 준비하세요.",
                "학교 본문 질문과 낯선 지문 질문을 섞어 풀어 암기와 독해 근거를 함께 확인하세요.",
                "시험 후에는 틀린 문항보다 근거를 설명하지 못한 문항을 따로 남겨 누적 복습으로 넘기세요.",
                "영어 범위표와 현재 교재 목차가 어긋나는 지점을 표시해 상담에서 반영 순서를 질문하세요.",
                "학교 자료에 없는 예상 범위를 임의로 넓히지 말고 확인된 단원과 누적 빈틈을 구분하세요.",
                "서술형 대비는 모범답안 암기보다 조건을 바꾸어 다시 쓰는 과정이 계획에 있는지 확인하세요.",
                "학교별 일정·본문·문법 단원을 한 표에 놓고 각 항목의 마지막 재확인 날짜를 정하세요.",
            ),
            "plan": (
                "첫 2주는 어휘 재사용, 문법 적용, 독해 근거 가운데 가장 약한 한 항목을 매일 짧게 확인하세요.",
                "새 분량과 재확인 분량을 다른 칸에 적고 같은 오류가 남으면 새 문제 수를 늘리지 마세요.",
                "월·수·금에는 학교 범위, 화·목에는 누적 어휘와 독해처럼 목적이 다른 학습을 분리해 보세요.",
                "완료 기준을 ‘공부함’이 아니라 근거 표시, 한 문장 요약, 서술형 재작성처럼 관찰 가능한 행동으로 적으세요.",
                "학생이 혼자 해낸 문장 수를 기준으로 다음 주 분량을 조정하고 미완료 이유를 한 줄 남기세요.",
                "당일 복습과 사흘 뒤 재확인을 함께 배치해 외운 답이 아니라 재현 가능한지 살펴보세요.",
                "학교 시험이 가까우면 누적 학습을 없애지 말고 짧은 유지 분량으로 조정해 연결을 지키세요.",
                "어휘·문법·독해의 시작 날짜보다 마지막 확인 날짜를 정해 복습이 뒤로 밀리지 않게 하세요.",
                "답안을 고친 날과 같은 기준의 새 문장을 푼 날을 분리해 적용 여부를 기록하세요.",
                "한 주 필수 항목과 여유 항목을 나누어 학교 일정이 바뀌어도 핵심 복습이 남도록 하세요.",
                "학생이 선택한 학습 순서와 실제 완료 순서를 비교해 자주 미뤄지는 영역을 먼저 조정하세요.",
                "긴 지문 한 개보다 짧은 문장 여러 개로 구조 설명을 확인한 뒤 지문으로 연결하세요.",
                "오답 노트의 양을 늘리기보다 다음 주에 다시 설명할 문장을 정하고 날짜를 고정하세요.",
                "첫 주에는 진단 자료를 만들고 둘째 주에는 같은 기준을 새 문제에 적용해 변화보다 재현을 확인하세요.",
                "학교 범위와 누적 빈틈을 한 계획에 적되 색이나 칸을 달리해 완료 조건을 혼동하지 마세요.",
                "실제 가능한 공부 시간을 먼저 계산하고 어휘·문법·독해의 최소 유지 분량을 배치하세요.",
            ),
        }
    return {
        "diagnosis": (
            "정답을 보기 전에 문제 조건, 필요한 개념, 풀이 첫 줄을 학생이 어느 단계까지 혼자 정하는지 확인하세요.",
            "최근 시험지의 오답을 개념 누락·조건 해석·계산 실수·시간 부족으로 나누어 표시하세요.",
            "맞힌 문제도 풀이 근거를 설명하지 못했다면 같은 개념의 변형 문제로 다시 확인하세요.",
            "단원별 문제와 두 개념을 연결한 문제를 분리해 어디에서 식 세우기가 막히는지 살펴보세요.",
            "서술형 답안에서 조건, 사용한 개념, 계산 과정, 결론이 모두 남아 있는지 대조하세요.",
            "계산 실수라고 말하기 전에 부호·분수·식 변형·검산 가운데 실제 오류 위치를 기록하세요.",
            "공식을 외운 것과 문제 조건에서 필요한 공식을 고르는 것을 다른 문항으로 확인하세요.",
            "오답을 고친 뒤 숫자와 조건이 바뀐 문제에서도 같은 풀이 순서를 재현하는지 살펴보세요.",
            "첫 줄을 쓰지 못한 문제와 중간 계산에서 틀린 문제를 구분해 필요한 설명을 다르게 정하세요.",
            "최근 두 시험에서 반복된 단원보다 반복된 오류 원인이 무엇인지 답안 흔적으로 비교하세요.",
            "학생이 어려웠다고 말한 유형과 실제로 풀이가 멈춘 단계가 같은지 확인하세요.",
            "개념 설명, 예제 재현, 유형 적용, 서술형 설명의 네 단계 중 처음 막힌 곳을 표시하세요.",
            "시간 안에 푼 문제와 시간이 충분할 때만 푼 문제를 구분해 속도보다 풀이 안정성을 확인하세요.",
            "정답률이 비슷해도 빈 문제와 실수 문항의 비율이 다른지 살펴 학습 순서를 정하세요.",
            "문제 조건에 밑줄을 긋고 식으로 옮긴 흔적이 있는지 확인해 독해와 계산 오류를 분리하세요.",
            "학생이 풀이를 말로 설명한 뒤 같은 구조의 새 문제에서 혼자 풀이 첫 줄을 쓰는지 확인하세요.",
        ),
        "exam": (
            "학교 범위의 현재 단원과 이전 학년에서 연결되는 개념을 다른 칸에 적어 함께 준비하세요.",
            "범위표마다 개념 확인·유형 적용·서술형·오답 재풀이의 완료 날짜를 정하세요.",
            "학교별 시험 범위는 학생이 받은 최신 공지를 기준으로 하고 페이지 학교명은 대조용으로만 사용하세요.",
            "교과서 예제와 학교 프린트의 변형 정도를 비교해 필요한 적용 연습을 질문하세요.",
            "수행평가와 지필평가 일정을 먼저 고정한 뒤 누적 개념 복습 시간을 남겨 두세요.",
            "문제 수보다 학교 시험에서 자주 감점된 풀이 누락과 계산 오류를 따로 정리하세요.",
            "서술형 답안은 정답뿐 아니라 사용한 조건과 식의 근거가 모두 적혔는지 확인하세요.",
            "시험 범위의 단원마다 바로 풀 문제와 시간차를 두고 다시 풀 문제를 구분하세요.",
            "학교 일정이 바뀌면 유지할 누적 복습과 이동할 시험 대비 분량을 나누어 조정하세요.",
            "중1·중2·중3의 같은 개념도 문제 연결 방식이 다를 수 있어 실제 범위 자료가 필요합니다.",
            "학교 문제와 낯선 변형 문제를 섞어 풀이 순서를 암기한 것인지 이해한 것인지 확인하세요.",
            "시험 후에는 틀린 번호보다 다시 설명하지 못한 개념과 풀이를 누적 목록으로 넘기세요.",
            "수학 범위표와 현재 교재 목차가 어긋나는 지점을 표시해 상담에서 반영 순서를 질문하세요.",
            "확인되지 않은 예상 범위를 임의로 늘리지 말고 학교 자료와 누적 빈틈을 구분하세요.",
            "고난도 문제보다 기본 유형의 식 세우기와 검산이 안정적인지 먼저 확인해 계획을 정하세요.",
            "학교별 단원·프린트·서술형 조건을 한 표에 놓고 마지막 재풀이 날짜를 기록하세요.",
        ),
        "plan": (
            "첫 2주는 개념 설명, 식 세우기, 계산 검산 가운데 가장 약한 한 단계를 매일 짧게 확인하세요.",
            "새 문제와 오답 재풀이를 다른 칸에 적고 같은 원인이 남으면 새 분량을 늘리지 마세요.",
            "학교 범위 학습과 누적 개념 복습을 요일별로 나누어 미완료 원인을 확인하세요.",
            "완료 기준을 ‘수학 공부’가 아니라 단원·문제 수·풀이 첫 줄·검산 여부로 적으세요.",
            "학생이 혼자 완성한 풀이 수를 기준으로 다음 주 분량을 조정하세요.",
            "당일 재풀이와 사흘 뒤 조건이 바뀐 문제를 함께 배치해 적용 여부를 살펴보세요.",
            "시험이 가까워도 이전 개념 복습을 없애지 말고 짧은 유지 분량을 남겨 두세요.",
            "개념·유형·서술형의 시작 날짜보다 마지막 재확인 날짜를 먼저 정하세요.",
            "답안을 고친 날과 유사 문제를 혼자 푼 날을 분리해 변화 과정을 기록하세요.",
            "한 주 필수 항목과 여유 항목을 나누어 학교 일정 변화에 대비하세요.",
            "학생이 계획한 풀이 순서와 실제 완료 순서를 비교해 자주 밀리는 단계를 조정하세요.",
            "고난도 한 문제보다 기본 연결 문제 여러 개에서 식을 안정적으로 세우는지 확인하세요.",
            "오답 노트의 양을 늘리기보다 다음 주에 다시 풀 문제와 날짜를 고정하세요.",
            "첫 주에는 오류 원인을 나누고 둘째 주에는 같은 기준을 변형 문제에 적용하세요.",
            "학교 범위와 누적 빈틈을 한 계획에 적되 색이나 칸을 달리해 구분하세요.",
            "실제 공부 가능 시간을 먼저 계산하고 개념·유형·오답의 최소 유지 분량을 배치하세요.",
        ),
    }


def build_cards(context: Context) -> tuple[Card, ...]:
    actions = subject_actions(context)
    diagnostic = choose(context, "diagnosis", actions["diagnosis"])
    exam = choose(context, "exam", actions["exam"])
    plan = choose(context, "plan", actions["plan"])
    school = school_summary(context)
    decision_options = (
        f"{context.grades} 표시는 확인된 자료이고 현재 개설 시간은 상담에서 새로 확인할 조건입니다. 두 정보를 같은 칸에 섞지 마세요.",
        f"{context.center}의 주소는 {context.address}입니다. 이동 가능한 요일과 시간을 함께 적어 실제 계획이 가능한지 확인하세요.",
        f"상담 답변은 가능 학년, 학교 자료 반영, 첫 주 행동, 재확인 날짜의 네 칸으로 나누어 기록하세요.",
        f"교재 이름보다 {with_particle(context.focus, '을', '를')} 어떤 자료로 확인하고 다음 확인 시점을 언제 잡는지 물어보세요.",
        f"페이지에서 확인한 센터·주소·학년 정보와 상담에서 들은 시간표·반 편성·교습비를 서로 다른 출처로 표시하세요.",
        f"{context.locality}에서 비교한 학원마다 진단 자료, 완료 기준, 학교 범위 반영 방식이 구체적인지 같은 질문을 사용하세요.",
        f"첫 상담 뒤에는 학생이 바꿀 행동 한 가지와 보호자가 확인할 날짜 한 가지가 남아 있어야 합니다.",
        f"‘관리합니다’라는 답보다 무엇을, 어떤 기록으로, 언제 다시 확인하는지 세부 기준을 요청하세요.",
        f"가능 학년이 같아도 학생의 현재 진도와 희망 시간이 다르므로 실제 시작 범위를 별도 메모하세요.",
        f"학교 시험 계획과 누적 {context.subject} 계획을 분리해 각각의 자료와 완료 조건을 확인하세요.",
        f"상담 전 질문과 상담 후 답변을 같은 표에 적으면 확인된 사실과 아직 남은 조건을 구분하기 쉽습니다.",
        f"{context.title}의 최종 비교표에는 학생이 혼자 재현할 기준과 다음 재확인 날짜가 반드시 포함되어야 합니다.",
        f"센터 위치가 적합해도 학년·시간·학교 범위가 맞지 않을 수 있으므로 조건별로 확인 결과를 남기세요.",
        f"상담에서 들은 내용은 날짜를 함께 적고 페이지 원자료와 다른 항목은 최신 답변으로 별도 표시하세요.",
        f"학생의 최근 답안이 첫 계획에 어떻게 반영되는지 설명을 요청하고 집에서 확인할 항목을 함께 정하세요.",
        f"{context.theme}라는 상담 주제가 실제 주간 행동과 재확인 기록으로 이어지는지 최종적으로 비교하세요.",
    )
    decision = (
        f"중등 {context.subject} 선택 기록: "
        + choose(context, "decision", decision_options)
    )
    base_items = {
        "diagnosis": (
            f"최근 {context.subject} 시험지에서 막힌 문항 3개 표시",
            f"{context.focus}의 첫 답안과 수정 답안 비교",
            "학생이 혼자 설명하거나 다시 푼 날짜 기록",
            "맞힌 문제 중 근거가 불분명한 문항 분리",
            "현재 교재 목차에 완료·미완료 단원 표시",
            "일주일 공부 시간과 실제 완료량 함께 준비",
        ),
        "exam": (
            "학교에서 받은 최신 시험 범위표 준비",
            f"{context.subject} 교재 진도와 학교 범위 차이 표시",
            "수행평가와 지필평가 일정 분리",
            "시험 후 누적 복습으로 넘길 항목 기록",
            "학교 자료와 추정 범위를 구분",
            "서술형·변형 문제의 감점 조건 확인",
        ),
        "plan": (
            "새 학습과 재확인 분량을 다른 칸에 기록",
            "완료 기준을 문제 수와 행동으로 구체화",
            "사흘 뒤 다시 확인할 날짜 고정",
            "미완료 이유를 시간·난도·이해로 구분",
            "필수 항목과 여유 항목 분리",
            "다음 주 분량은 실제 완료 결과로 조정",
        ),
        "decision": (
            "현재 개설 학년·시간표 최신 확인",
            "학교 자료 반영 방법과 범위 질문",
            "첫 주 행동과 완료 기준 기록",
            "오답 재확인 날짜와 방법 확인",
            "센터 정보와 상담 답변의 출처 구분",
            "교습비·반 편성·희망 요일 별도 확인",
        ),
    }

    def pick_items(salt: str) -> tuple[str, ...]:
        values = base_items[salt]
        start = stable_number(context.title, salt) % len(values)
        return tuple(values[(start + step * 2 + context.ordinal) % len(values)] for step in range(3))

    school_heading = (
        f"{context.schools[0]} 등 학교 시험 자료를 어떻게 반영하나"
        if context.schools
        else "학교명이 미기재된 경우 무엇을 준비하나"
    )
    return (
        Card("01 · 현재 진단", f"{with_particle(context.focus, '은', '는')} 어디에서 막히나", diagnostic, pick_items("diagnosis")),
        Card("02 · 학교 내신", school_heading, f"{school} {exam}", pick_items("exam")),
        Card("03 · 첫 2주", f"{context.subject} 복습을 어떤 간격으로 확인하나", plan, pick_items("plan")),
        Card("04 · 상담 결정", "확인된 사실과 최신 답변을 어떻게 나누나", decision, pick_items("decision")),
    )


def render_block(context: Context, cards: tuple[Card, ...]) -> str:
    cards_html = "".join(
        '<article class="priority-intent-card">'
        f'<span>{html.escape(card.label)}</span>'
        f'<h3>{html.escape(card.heading)}</h3>'
        f'<p>{html.escape(card.body)}</p>'
        '<ul>'
        + "".join(f"<li>{html.escape(item)}</li>" for item in card.items)
        + "</ul></article>"
        for card in cards
    )
    return (
        f"{START_MARKER}\n"
        '<section class="priority-intent-section" aria-labelledby="priority-intent-title">'
        '<div class="wrap"><div class="priority-intent-head">'
        f'<p>SEARCH INTENT · MIDDLE {"ENGLISH" if context.subject == "영어" else "MATH"}</p>'
        f'<h2 id="priority-intent-title">{html.escape(context.locality)} 중등 {html.escape(context.subject)}학원, 등록 전에 답할 네 가지 질문</h2>'
        f'<span>{html.escape(intro_copy(context))}</span>'
        '</div><div class="priority-intent-grid">'
        f"{cards_html}</div>"
        '<aside class="priority-intent-source"><strong>페이지 근거</strong>'
        f'<p>{html.escape(context.school_fact)} 가능 학년은 {html.escape(context.grades)}로 표시되어 있습니다. '
        '현재 개설 시간·반 편성·교습비는 상담 시점에 다시 확인하세요.</p></aside>'
        f"</div></section>\n{END_MARKER}"
    )


def update_jsonld(
    source: str, context: Context, cards: tuple[Card, ...]
) -> str:
    node_id = context.canonical + "#priority-search-intent"
    updated = False

    def replace(match: re.Match[str]) -> str:
        nonlocal updated
        if updated:
            return match.group(0)
        try:
            data = json.loads(match.group(2))
        except json.JSONDecodeError:
            return match.group(0)
        if not isinstance(data, dict) or not isinstance(data.get("@graph"), list):
            return match.group(0)
        graph = data["@graph"]
        if not any(
            isinstance(node, dict)
            and node.get("@id") == context.canonical + "#webpage"
            for node in graph
        ):
            return match.group(0)
        graph[:] = [
            node
            for node in graph
            if not (isinstance(node, dict) and node.get("@id") == node_id)
        ]
        node = {
            "@type": "ItemList",
            "@id": node_id,
            "name": f"{context.locality} 중등 {context.subject}학원 선택 질문",
            "numberOfItems": len(cards),
            "itemListElement": [
                {
                    "@type": "ListItem",
                    "position": index,
                    "name": card.heading,
                    "description": card.body,
                }
                for index, card in enumerate(cards, 1)
            ],
        }
        insert_at = next(
            (
                index
                for index, item in enumerate(graph)
                if isinstance(item, dict)
                and str(item.get("@id", "")).endswith("#school-reference")
            ),
            len(graph),
        )
        graph.insert(insert_at, node)
        for item in graph:
            if not isinstance(item, dict):
                continue
            item_type = item.get("@type")
            types = item_type if isinstance(item_type, list) else [item_type]
            if not ({"WebPage", "Article"} & set(types)):
                continue
            if item.get("@id") not in {
                context.canonical + "#webpage",
                context.canonical + "#article",
            }:
                continue
            parts = item.get("hasPart")
            if not isinstance(parts, list):
                parts = []
            parts = [
                part
                for part in parts
                if not (isinstance(part, dict) and part.get("@id") == node_id)
            ]
            part_at = next(
                (
                    index
                    for index, part in enumerate(parts)
                    if isinstance(part, dict)
                    and str(part.get("@id", "")).endswith("#school-reference")
                ),
                len(parts),
            )
            parts.insert(part_at, {"@id": node_id})
            item["hasPart"] = parts
        updated = True
        payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
        return match.group(1) + payload + match.group(3)

    result = JSONLD_RE.sub(replace, source)
    if not updated:
        raise ValueError(f"{context.path.relative_to(ROOT)}: WebPage JSON-LD 없음")
    return result


def transform(context: Context) -> tuple[str, tuple[Card, ...]]:
    cards = build_cards(context)
    block = render_block(context, cards)
    source = context.before
    if BLOCK_RE.search(source):
        source = BLOCK_RE.sub(block, source, count=1)
    else:
        quick = QUICK_ANSWER_RE.search(source)
        if not quick:
            raise ValueError(f"{context.path.relative_to(ROOT)}: quick answer 없음")
        source = source[: quick.end()] + "\n" + block + source[quick.end() :]
    source = update_jsonld(source, context, cards)
    source = DATE_RE.sub(rf"\g<1>{RELEASE_DATE}\g<2>", source)
    return source, cards


def normalized_visible(source: str, context: Context) -> str:
    main = first(r"(<main\b.*?</main>)", source)
    value = clean(SCRIPT_STYLE_RE.sub(" ", main))
    facts = [
        context.title,
        context.locality,
        context.center,
        context.address,
        context.grades,
        context.school_fact,
        context.focus,
        context.theme,
        *context.schools,
    ]
    for fact in sorted({item for item in facts if item}, key=len, reverse=True):
        value = value.replace(fact, " VAR ")
    return re.sub(r"\s+", " ", value).strip()


def shingle_set(value: str, size: int = 4) -> set[tuple[str, ...]]:
    words = re.findall(r"[가-힣A-Za-z0-9]+", value.lower())
    return {
        tuple(words[index : index + size])
        for index in range(max(0, len(words) - size + 1))
    }


def similarity_metrics(
    pairs: list[tuple[Context, str]], sample_size: int = 90
) -> dict[str, float]:
    if len(pairs) > sample_size:
        indices = [
            round(index * (len(pairs) - 1) / (sample_size - 1))
            for index in range(sample_size)
        ]
        pairs = [pairs[index] for index in indices]
    sets = [shingle_set(normalized_visible(source, context)) for context, source in pairs]
    similarities = [
        len(left & right) / len(left | right)
        for left, right in itertools.combinations(sets, 2)
    ]
    ordered = sorted(similarities)
    return {
        "average": round(statistics.mean(similarities), 4),
        "p90": round(ordered[int(len(ordered) * 0.9)], 4),
        "max": round(max(similarities), 4),
    }


def validate(plans: list[Plan]) -> list[str]:
    errors: list[str] = []
    if len(plans) != 742:
        errors.append(f"pages={len(plans)}/742")
    paragraph_counts: Counter[str] = Counter()
    for plan in plans:
        context = plan.context
        relative = context.path.relative_to(ROOT).as_posix()
        if plan.after.count(START_MARKER) != 1 or plan.after.count(END_MARKER) != 1:
            errors.append(f"{relative}: marker 수 오류")
        if context.before.count("<h1") != plan.after.count("<h1"):
            errors.append(f"{relative}: H1 수 변경")
        before_school = SCHOOL_RE.search(context.before)
        after_school = SCHOOL_RE.search(plan.after)
        if not before_school or not after_school or before_school.group(0) != after_school.group(0):
            errors.append(f"{relative}: 학교 원자료 블록 변경")
        if context.canonical not in plan.after:
            errors.append(f"{relative}: canonical 손실")
        block = BLOCK_RE.search(plan.after)
        if not block or block.group(0).count('class="priority-intent-card"') != 4:
            errors.append(f"{relative}: 선택 질문 카드 수 오류")
            continue
        for card in plan.cards:
            paragraph = card.body
            for fact in sorted(
                {
                    context.locality,
                    context.center,
                    context.address,
                    context.grades,
                    context.school_fact,
                    context.focus,
                    context.theme,
                    *context.schools,
                },
                key=len,
                reverse=True,
            ):
                if fact:
                    paragraph = paragraph.replace(fact, " VAR ")
            paragraph_counts[re.sub(r"\s+", " ", paragraph).strip()] += 1
        match = JSONLD_RE.search(plan.after)
        if not match:
            errors.append(f"{relative}: JSON-LD 없음")
            continue
        try:
            data = json.loads(match.group(2))
        except json.JSONDecodeError:
            errors.append(f"{relative}: JSON-LD parse 오류")
            continue
        node_id = context.canonical + "#priority-search-intent"
        nodes = [
            node
            for node in data.get("@graph", [])
            if isinstance(node, dict) and node.get("@id") == node_id
        ]
        if len(nodes) != 1:
            errors.append(f"{relative}: intent schema node={len(nodes)}")
        else:
            schema_cards = [
                (item.get("name"), item.get("description"))
                for item in nodes[0].get("itemListElement", [])
            ]
            visible_cards = [(card.heading, card.body) for card in plan.cards]
            if schema_cards != visible_cards:
                errors.append(f"{relative}: 화면/schema 카드 불일치")
    if paragraph_counts and max(paragraph_counts.values()) > 30:
        errors.append(
            f"intent normalized paragraph max_df={max(paragraph_counts.values())}/30"
        )
    return errors


def atomic_write(path: Path, value: str) -> None:
    temporary = path.with_name(path.name + ".intent.tmp")
    temporary.write_text(value, encoding="utf-8", newline="\n")
    temporary.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    page_contexts = contexts()
    plans: list[Plan] = []
    for context in page_contexts:
        after, cards = transform(context)
        plans.append(Plan(context, after, cards))
    errors = validate(plans)
    categories: dict[str, dict[str, object]] = {}
    for category in CATEGORIES:
        selected = [plan for plan in plans if plan.context.category == category]
        before_pairs = [(plan.context, plan.context.before) for plan in selected]
        after_pairs = [(plan.context, plan.after) for plan in selected]
        categories[category] = {
            "pages": len(selected),
            "visible_chars_before_avg": round(
                statistics.mean(
                    len(clean(SCRIPT_STYLE_RE.sub(" ", first(r"(<main\b.*?</main>)", source))))
                    for _, source in before_pairs
                ),
                1,
            ),
            "visible_chars_after_avg": round(
                statistics.mean(
                    len(clean(SCRIPT_STYLE_RE.sub(" ", first(r"(<main\b.*?</main>)", source))))
                    for _, source in after_pairs
                ),
                1,
            ),
            "similarity_before": similarity_metrics(before_pairs),
            "similarity_after": similarity_metrics(after_pairs),
        }
    report = {
        "mode": "APPLY" if args.apply else "DRY-RUN",
        "pages": len(plans),
        "changed": sum(plan.context.before != plan.after for plan in plans),
        "categories": categories,
        "errors": len(errors),
        "samples": errors[:20],
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if errors:
        return 1
    if args.apply:
        for plan in plans:
            if plan.context.before != plan.after:
                atomic_write(plan.context.path, plan.after)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
