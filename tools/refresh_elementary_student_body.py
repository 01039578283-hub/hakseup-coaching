from __future__ import annotations

"""Differentiate repeated prose in 371 elementary-student locality pages.

The command is a validated dry run by default. ``--apply`` updates only the
visible ``subject-copy-flow`` content and the WebPage/Article modification
date. Existing headings, factual school/address copy, FAQ, review, title,
canonical URL, media, center details, and internal-link blocks are preserved.
"""

import argparse
import hashlib
import html
import itertools
import json
import re
import statistics
from dataclasses import dataclass
from pathlib import Path


DEFAULT_ROOT = Path(__file__).resolve().parents[1]
CATEGORY = "초등학생학원"
RELEASE_DATE = "2026-08-28"
MARKER = "<!-- elementary-body-differentiation:2026-08-28 -->"
FLOW_RE = re.compile(
    r'(<div\s+class="subject-copy-flow">)(.*?)(</div>\s*</article>)', re.I | re.S
)
JSONLD_RE = re.compile(
    r'(<script\b[^>]*type=["\']application/ld\+json["\'][^>]*>)(.*?)(</script>)',
    re.I | re.S,
)
SCHOOL_RE = re.compile(
    r"<!-- school-reference:start -->.*?<!-- school-reference:end -->", re.I | re.S
)
NETWORK_RE = re.compile(
    r"<!-- local-study-network:start -->.*?<!-- local-study-network:end -->",
    re.I | re.S,
)
FAQ_RE = re.compile(
    r'<section\b[^>]*class="subject-faq-section".*?</section>', re.I | re.S
)
ANSWER_RE = re.compile(
    r'<div\b[^>]*class="subject-answer-box".*?</div>', re.I | re.S
)
REVIEW_RE = re.compile(
    r'<section\b[^>]*class="subject-review-section".*?</section>', re.I | re.S
)
SCRIPT_STYLE_RE = re.compile(
    r"<(?:script|style|header|footer|nav|noscript|svg)\b.*?</(?:script|style|header|footer|nav|noscript|svg)>",
    re.I | re.S,
)
TAG_RE = re.compile(r"<[^>]+>")


@dataclass(frozen=True)
class Context:
    path: Path
    ordinal: int
    before: str
    title: str
    locality: str
    area: str
    persona: str
    keyword: str


@dataclass(frozen=True)
class Plan:
    context: Context
    after: str
    replacements: int
    particle_fixes: int


def clean(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(TAG_RE.sub(" ", value or ""))).strip()


def first(pattern: str, source: str, flags: int = re.I | re.S) -> str:
    match = re.search(pattern, source, flags)
    return clean(match.group(1)) if match else ""


def stable_number(value: str, salt: str) -> int:
    digest = hashlib.sha256(f"{value}|{salt}".encode("utf-8")).hexdigest()
    return int(digest[:14], 16)


def choose(context: Context, salt: str, values: tuple[str, ...]) -> str:
    if not values:
        raise ValueError(f"empty choice pool: {salt}")
    return values[stable_number(context.title, salt) % len(values)]


def has_batchim(value: str) -> bool:
    last = next((char for char in reversed(value) if "가" <= char <= "힣"), "")
    return bool(last) and (ord(last) - ord("가")) % 28 != 0


def corrected_separate_phrase(context: Context) -> tuple[str, str]:
    before = f"{context.keyword}와 별개로"
    particle = "과" if has_batchim(context.keyword) else "와"
    return before, f"{context.keyword}{particle} 별개로"


def extract_keyword(source: str) -> str:
    service_phrase = re.search(r"([가-힣A-Za-z0-9]+)(?:와|과) 별개로", source)
    if service_phrase:
        return service_phrase.group(1).strip()
    patterns = (
        r"<h2>([^<]{2,32}) 관련 질문을 구체적으로 바꾸는 방법</h2>",
        r"<h2>([^<]{2,32})(?:을|를) 물을 때 빠뜨리지 말아야 할 항목</h2>",
        r"<h2>([^<]{2,32})(?:을|를) 수업 적합성과 연결해 보는 법</h2>",
        r"<summary><span>Q</span>([^<]{2,32})(?:은|는|을|를)\?",
    )
    for pattern in patterns:
        match = re.search(pattern, source)
        if match:
            return match.group(1).strip(" ‘’.:—")
    return "학습관리"


def extract_context(path: Path, ordinal: int) -> Context:
    source = path.read_text(encoding="utf-8", errors="strict")
    title = first(r"<h1\b[^>]*>(.*?)</h1>", source)
    suffix = f" {CATEGORY}"
    locality = title[: -len(suffix)].strip() if title.endswith(suffix) else ""
    area = first(r"ELEMENTARY SCHOOL COACHING\s*·\s*([^<]+)</p>", source)
    flow = FLOW_RE.search(source)
    flow_text = clean(flow.group(2)) if flow else ""
    persona_match = re.search(r"([1-6]학년\s+[가-힣·]+형\s+학생)", flow_text)
    persona = persona_match.group(1) if persona_match else "초등학생"
    keyword = extract_keyword(source)
    missing = [
        name
        for name, value in (
            ("title", title),
            ("locality", locality),
            ("area", area),
            ("flow", flow_text),
        )
        if not value
    ]
    if missing:
        raise ValueError(f"{path}: context missing {missing}")
    return Context(path, ordinal, source, title, locality, area, persona, keyword)


def replace_literal(value: str, before: str, after: str) -> tuple[str, int]:
    if before not in value:
        return value, 0
    return value.replace(before, after, 1), 1


def replace_pattern(
    value: str, pattern: str, replacement: str, flags: int = 0
) -> tuple[str, int]:
    return re.subn(pattern, lambda _: replacement, value, count=1, flags=flags)


def rewrite_flow(flow: str, context: Context) -> tuple[str, int]:
    if MARKER in flow:
        return flow, 0

    locality = context.locality
    persona = context.persona
    area = context.area
    keyword = context.keyword
    replacements = 0

    def literal(before: str, after: str) -> None:
        nonlocal flow, replacements
        flow, count = replace_literal(flow, before, after)
        replacements += count

    literal(
        "첫 상담에서 현재 몇 학년 교재를 푸는지만 묻기보다, 어느 순간에 풀이가 멈추는지를 확인해야 합니다.",
        choose(
            context,
            "diagnostic-start",
            (
                "상담에서는 교재 표지보다 최근에 혼자 풀다 멈춘 문제를 먼저 펼쳐 두고, 생각이 끊긴 지점을 찾아야 합니다.",
                "현재 진도만 말하기보다 마지막으로 스스로 해결한 문제와 도움을 요청한 문제를 나누어 보여 주세요.",
                "학년과 교재 난도를 확인한 다음에는 문제를 읽고 첫 행동을 정하는 과정에서 어디가 막히는지 살펴야 합니다.",
                "첫 상담 자료는 진도표 한 장보다 최근 과제와 오답이 유용합니다. 시작·풀이·확인 중 멈춘 단계를 표시해 가세요.",
                "아이에게 어려운 단원을 묻는 데서 끝내지 말고, 실제 문제 앞에서 혼자 할 수 있는 마지막 단계까지 확인해야 합니다.",
                "교재 수준을 올릴지 결정하기 전에 최근 답안에서 설명 없이 넘어간 부분과 도움을 받은 시점을 구분해 보세요.",
                "상담 전 최근 문제 세 개를 골라 풀이를 다시 말하게 하면 현재 진도보다 구체적인 시작점을 찾을 수 있습니다.",
                "학생이 알고 있다고 말한 내용과 답안에 남은 흔적을 대조해, 혼자 재현하지 못하는 첫 단계를 확인하세요.",
                "현재 몇 학년 과정을 배우는지와 별개로, 지시문 이해부터 검산까지 어느 순서에서 멈추는지를 먼저 기록해야 합니다.",
                "진단에서는 맞힌 개수보다 문제를 읽고 계획하고 다시 확인하는 과정 중 빠진 부분을 찾는 것이 우선입니다.",
                "최근 과제를 시간 순서대로 살펴보며 시작이 늦어진 문제, 설명이 필요한 문제, 스스로 고친 문제를 나누어 보세요.",
                "첫 면담에는 최근 교재와 오답을 함께 가져가 아이가 혼자 설명할 수 있는 범위부터 확인하는 편이 좋습니다.",
            ),
        ),
    )
    literal(
        f"{locality} 진단 뒤에는 진도·복습 비율과 재풀이 날짜까지 정해지는지 확인하세요.",
        choose(
            context,
            "diagnostic-close",
            (
                f"{locality} 상담을 마칠 때는 새 진도와 복습의 비율, 같은 문제를 다시 확인할 날짜가 남아 있는지 살펴보세요.",
                f"진단 결과가 {locality} 학생의 첫 주 분량과 재풀이 일정으로 이어지는지 마지막에 확인해야 합니다.",
                f"{locality}에서 받은 진단 설명은 우선 단원, 주간 분량, 다음 확인일의 세 항목으로 다시 적어 보세요.",
                f"상담 후에는 {locality} 학생이 먼저 보완할 내용과 혼자 다시 풀 시점이 구체적으로 정해졌는지 확인하세요.",
                f"{locality} 진단이 실제 계획으로 연결되려면 진도 조정 기준과 복습 날짜가 함께 제시되어야 합니다.",
                f"마지막에는 {locality} 학생의 새 학습량과 누적 복습량을 나누고 재확인 시점을 달력에 표시하세요.",
                f"{locality} 상담 기록에는 시작 교재보다 먼저 보완할 개념과 다음 재풀이 날짜를 남기는 편이 실용적입니다.",
                f"설명을 들은 뒤 {locality} 가정에서 확인할 행동 한 가지와 학원에서 다시 볼 날짜 한 가지를 정해 보세요.",
            ),
        ),
    )
    literal(
        f"{persona}에게 설명만 길게 제공하면 수업 중에는 이해한 듯 보여도 집에서 다시 시작할 단서가 남지 않을 수 있습니다.",
        choose(
            context,
            "independent-recall",
            (
                f"{persona}에게는 설명을 들은 직후보다 집에서 첫 단계를 혼자 다시 꺼낼 수 있는지가 더 중요한 확인 항목입니다.",
                f"{persona}이 수업 중 고개를 끄덕였더라도 다음 날 같은 순서를 말하지 못한다면 복습 단서가 부족한 상태일 수 있습니다.",
                f"설명 시간이 길어질수록 {persona}이 직접 해 보는 구간이 줄 수 있으므로, 짧은 재현 과정을 반드시 남겨야 합니다.",
                f"{persona}은 이해했다는 반응보다 책을 덮은 뒤 핵심 순서를 다시 말하거나 써 보는 과정으로 확인하는 편이 좋습니다.",
                f"수업 안에서만 해결되는 도움은 {persona}의 독립 학습으로 이어지기 어렵습니다. 혼자 시작할 작은 단서를 정해 주세요.",
                f"{persona}에게 필요한 것은 추가 설명의 양보다 다음 학습 때 스스로 꺼내 쓸 수 있는 표시와 재확인 순서입니다.",
                f"{persona}이 집에서도 같은 방법을 시작하려면 수업 말미에 첫 행동과 확인 기준을 자신의 말로 정리해 보아야 합니다.",
                f"설명을 바로 이해한 것과 혼자 다시 수행하는 것은 다릅니다. {persona}에게는 시간차를 둔 재확인이 필요합니다.",
            ),
        ),
    )
    literal(
        f"{locality}의 과제는 양보다 목적과 피드백 시점이 중요합니다.",
        choose(
            context,
            "homework-purpose",
            (
                f"{locality} 초등 과제는 몇 쪽을 끝냈는지보다 왜 풀고 언제 확인받는지가 분명해야 합니다.",
                f"{locality} 가정에서는 과제량을 늘리기 전에 새 연습과 오답 재확인의 목적을 구분해 보세요.",
                f"과제를 비교할 때 {locality} 학부모가 먼저 볼 항목은 분량이 아니라 완료 기준과 피드백 날짜입니다.",
                f"{locality} 학생의 숙제는 같은 양이라도 확인 시점과 다시 풀 조건에 따라 학습 효과가 달라질 수 있습니다.",
                f"{locality}에서 과제 계획을 들을 때는 문제 수보다 수업 내용과 어떤 방식으로 이어지는지 질문하세요.",
                f"숙제가 많은지를 묻기 전에 {locality} 학생이 혼자 할 부분과 도움을 받을 부분이 나뉘는지 확인해야 합니다.",
                f"{locality} 초등 학습의 과제 기준은 양이 아니라 목적·난도·회수 시점이 한 흐름으로 설명되는가에 있습니다.",
                f"매일 같은 분량을 주는지보다 {locality} 학생의 오답에 따라 과제 목적이 조정되는지 살펴보는 편이 좋습니다.",
            ),
        ),
    )
    literal(
        f"{locality} 초등학생학원을 검토할 때 새 문제, 수업 중 틀린 문제, 며칠 뒤 다시 풀 문제를 구분하는지 묻고, {locality} 상담에서는 미완료 과제를 늘리는지, 난도·분량·집중 시간을 조정하는지도 확인해야 합니다.",
        choose(
            context,
            "homework-check",
            (
                f"{locality} 상담에서는 처음 푸는 문제와 수업 오답, 시간차 재풀이를 따로 표시하는지 물어보세요. 미완료가 생겼을 때 분량·난도·집중 시간을 무엇부터 바꾸는지도 함께 확인합니다.",
                f"과제표에 새 학습과 오답, 재확인 날짜가 구분되는지 확인한 뒤 {locality} 학생이 끝내지 못했을 때의 조정 순서를 질문하세요.",
                f"{locality} 초등학생학원을 비교한다면 과제를 더 주는 기준뿐 아니라 줄이거나 나누는 기준도 들어 보아야 합니다. 새 문제와 재풀이의 비중도 따로 기록하세요.",
                f"상담 답변은 새 문제·수업 오답·며칠 뒤 재풀이의 세 칸으로 적고, {locality} 학생의 미완료 원인에 따라 어떤 칸을 조정하는지 확인하세요.",
                f"{locality} 학부모는 과제 개수보다 문제의 역할을 구분해 질문할 수 있습니다. 수업 뒤 바로 고칠 문제와 일정 후 다시 볼 문제가 나뉘는지 살펴보세요.",
                f"미완료 과제를 무조건 다음 날로 넘기는지, {locality} 학생의 집중 시간과 난도를 다시 계산하는지 확인하고 재풀이 일정도 별도로 받아 두세요.",
                f"{locality} 상담에서는 숙제를 새 진도, 당일 수정, 누적 재학습으로 나누어 설명해 달라고 요청하세요. 각 분량이 달라지는 조건도 함께 기록합니다.",
                f"새 문제를 많이 푸는 것만으로 복습을 판단하기 어렵습니다. {locality} 학생이 틀린 이유를 고친 뒤 며칠 후 다시 확인하는 절차가 있는지 물어보세요.",
            ),
        ),
    )
    literal(
        f"{locality}에서 초등학생학원을 선택할 때 소수, 개별, 맞춤이라는 이름만으로 수업 밀도를 판단하면 부족합니다.",
        choose(
            context,
            "class-density",
            (
                f"{locality}에서 소수·개별·맞춤 수업이라는 명칭만 보고 학생별 관찰 시간이 충분하다고 단정하기는 어렵습니다.",
                f"수업 인원이 적다는 설명과 {locality} 학생에게 실제로 돌아오는 질문·피드백 시간은 구분해서 확인해야 합니다.",
                f"{locality} 초등학생학원을 비교할 때는 반 이름보다 교사가 한 학생의 풀이를 보는 과정이 구체적인지 살펴보세요.",
                f"개별 관리라는 표현이 있어도 {locality} 학생이 직접 풀고 설명하는 시간이 확보되는지는 별도로 물어야 합니다.",
                f"{locality} 학부모는 소수 수업 여부와 함께 기다리는 시간, 질문 순서, 과제 확인 방식을 나누어 확인하는 편이 좋습니다.",
                f"한 반의 인원수만으로 {locality} 수업의 밀도를 알기는 어렵습니다. 학생별 관찰과 수정 기회가 어떻게 배분되는지 물어보세요.",
                f"맞춤이라는 이름보다 {locality} 학생의 교재 조정과 풀이 확인이 실제로 언제 이루어지는지 확인해야 합니다.",
                f"소수 정원은 비교 항목 중 하나입니다. {locality} 학생이 혼자 시도하고 피드백받는 흐름까지 보아야 수업 방식을 판단할 수 있습니다.",
            ),
        ),
    )
    literal(
        f"{locality} 초등학생학원은 인원수보다 아이가 직접 시도하고 수정한 흔적으로 비교하세요.",
        choose(
            context,
            "class-density-close",
            (
                f"{locality} 수업은 정원 숫자와 함께 학생의 풀이·수정 기록이 실제로 남는지로 비교하는 편이 정확합니다.",
                f"최종 비교표에는 {locality} 학생이 혼자 시도한 시간과 피드백 뒤 고친 흔적을 함께 적어 보세요.",
                f"{locality} 학원 선택에서는 학생 수보다 아이의 첫 답안과 수정 답안을 확인할 수 있는지가 더 구체적인 기준입니다.",
                f"인원 정보를 확인한 다음 {locality} 학생에게 남는 질문, 풀이, 재확인 기록까지 살펴보세요.",
                f"{locality} 초등 수업의 밀도는 아이가 설명을 듣는 시간보다 직접 해 보고 고치는 과정에서 드러납니다.",
                f"정원 안내를 받은 뒤에는 {locality} 학생의 시도와 수정 과정을 어떤 기록으로 확인하는지 추가로 질문하세요.",
                f"{locality}에서 여러 학원을 볼 때 같은 문제의 첫 풀이와 수정 결과가 남는지를 공통 기준으로 사용해 보세요.",
                f"수업 방식의 이름보다 {locality} 학생이 스스로 풀고 피드백을 반영한 흔적을 비교 자료로 삼는 것이 좋습니다.",
            ),
        ),
    )
    literal(
        f"{locality} 초등학생학원 방문을 검토할 때는 실제 종료 시간대에 집·학교 중 출발 지점을 정해 이동과 귀가 방법을 확인하세요.",
        choose(
            context,
            "travel",
            (
                f"{locality} 방문 전에는 평소 출발지를 집과 학교 중 하나로 정하고, 수업 종료 시각 기준의 귀가 동선을 직접 확인하세요.",
                f"주소를 확인한 다음 {locality} 학생이 실제 이동할 요일과 시간대에 걸리는 시간, 귀가 방법을 따로 계산해 보세요.",
                f"{locality} 센터까지의 거리는 지도 숫자만 보지 말고 방과 후 출발 시각과 수업 뒤 귀가 경로를 기준으로 살펴야 합니다.",
                f"상담 일정보다 먼저 {locality} 학생의 학교 종료 시각, 이동 시간, 귀가 동행 여부를 한 줄 일정표로 정리해 보세요.",
                f"{locality} 위치가 생활권에 맞는지는 실제 등원 요일의 출발지와 종료 뒤 이동 방법을 함께 보아야 판단할 수 있습니다.",
                f"방문 가능 여부는 주소만으로 결정하지 말고 {locality} 학생의 방과 후 일정과 수업 종료 뒤 귀가 시간을 대조하세요.",
                f"{locality} 상담을 예약할 때에는 학교 또는 집에서 센터까지의 시간과 늦은 시간 귀가 방법을 각각 확인하는 편이 좋습니다.",
                f"실제 등원 계획을 세우려면 {locality} 주소와 함께 출발 시각, 이동 수단, 수업 후 귀가 동선을 순서대로 점검하세요.",
            ),
        ),
    )
    literal(
        f"{locality} 초등학생학원에 등록한 뒤에는 첫 일주일의 반응만으로 적합성을 단정하지 말고 약 4주 동안 같은 지표를 반복해 보는 것이 좋습니다.",
        choose(
            context,
            "four-week-baseline",
            (
                f"{locality} 수업의 적합성은 첫날의 만족도보다 4주 동안 같은 항목을 기록했을 때 더 구체적으로 판단할 수 있습니다.",
                f"등록 직후의 반응은 일시적일 수 있으므로 {locality} 학생의 시작·수행·복습 기록을 약 한 달간 같은 기준으로 살펴보세요.",
                f"{locality} 초등학생학원을 시작했다면 첫 주와 넷째 주를 비교할 수 있도록 관찰 항목을 중간에 바꾸지 않는 편이 좋습니다.",
                f"한두 번의 수업만으로 결론을 내리기보다 {locality} 학생에게 정한 지표를 4주 동안 주간 단위로 남겨 보세요.",
                f"{locality} 학부모는 등록 전 기대와 실제 한 달 기록을 분리해 두면 수업 유지 여부를 더 차분하게 판단할 수 있습니다.",
                f"첫 주의 낯섦이 줄어든 뒤를 보기 위해 {locality} 학생의 동일한 행동 지표를 약 4주간 반복 확인하세요.",
                f"{locality} 수업을 평가할 때는 점수 변화만 기다리지 말고 시작 시간과 독립 수행, 재확인 행동을 한 달 동안 기록해야 합니다.",
                f"등록 후 4주 동안 {locality} 학생의 과제량이 아니라 같은 학습 행동이 얼마나 안정적으로 반복되는지 살펴보는 편이 좋습니다.",
            ),
        ),
    )
    literal(
        f"{locality}에서는 점수가 바로 움직이지 않더라도 시작이 빨라지고 질문이 구체화되며 같은 실수의 간격이 길어지는 변화를 함께 봐야 합니다.",
        choose(
            context,
            "four-week-positive",
            (
                f"{locality} 학생의 변화는 점수 외에도 시작까지 걸리는 시간, 질문의 구체성, 같은 오답이 다시 나타나는 간격으로 확인할 수 있습니다.",
                f"성적표가 그대로여도 {locality} 학생이 스스로 시작하고 막힌 이유를 정확히 말하며 반복 실수를 줄이는지는 따로 살펴야 합니다.",
                f"{locality}에서는 정답 수와 함께 독립 수행 시간이 늘었는지, 질문이 구체해졌는지, 오답 재발 주기가 달라졌는지를 봅니다.",
                f"점수 변화가 늦더라도 {locality} 학생의 시작 행동과 설명 수준, 같은 실수 사이의 간격이 좋아지는지 기록해 보세요.",
                f"{locality} 한 달 점검에서는 결과 점수뿐 아니라 도움 요청 시점과 질문 내용, 반복 오류의 빈도까지 함께 비교하는 편이 좋습니다.",
                f"학습 변화는 한 번의 평가로만 보이지 않습니다. {locality} 학생의 시작 속도와 독립 풀이, 오류 수정 과정도 나란히 확인하세요.",
                f"{locality} 학생이 이전보다 빨리 시작하고 질문을 구체적으로 만들며 같은 오류를 덜 반복한다면 과정 지표가 달라진 것입니다.",
                f"한 달 기록에는 {locality} 학생의 점수와 별도로 첫 문제 시작, 질문 정리, 시간차 재풀이의 변화를 표시해 보세요.",
            ),
        ),
    )
    negative_pattern = (
        rf"반대로 과제 부담만 커지거나 답을 베끼는 행동이 늘면 {re.escape(area)} "
        rf"{re.escape(locality)}의 생활 리듬과 현재 학년 수준을 기준으로 진도·난도·과제량을 "
        rf"다시 조정해야 하며, {re.escape(keyword)}만으로 유지 여부를 결정해서는 안 됩니다\."
    )
    flow, count = replace_pattern(
        flow,
        negative_pattern,
        choose(
            context,
            "four-week-adjust",
            (
                f"반면 과제를 버티기 위해 답을 옮겨 적거나 피로가 누적된다면 {locality} 일정을 다시 보고 진도·난도·분량을 조정해야 합니다. {keyword} 안내만으로 계속 다닐지를 정하지 마세요.",
                f"{locality} 학생에게 미완료와 베끼기가 늘면 의지 문제로 단정하지 말고 수업 진도, 과제 난도, 생활 시간을 다시 맞춰야 합니다. {keyword} 조건은 그다음에 판단합니다.",
                f"과제 부담이 커지고 독립 풀이가 줄어드는 경우에는 {locality} 학생의 가능한 학습 시간부터 재계산하세요. {keyword}이라는 명칭보다 실제 조정 절차가 중요합니다.",
                f"{locality} 생활 리듬과 맞지 않아 피로·미완료·베끼기가 늘었다면 진도와 분량을 낮춰 원인을 확인해야 합니다. {keyword}만 보고 유지 여부를 결정하기는 어렵습니다.",
                f"반복 과제가 늘수록 {locality} 학생이 스스로 하는 시간이 줄어든다면 난도와 과제 구성을 다시 상담하세요. {keyword} 안내는 실제 변경 가능 여부와 함께 봅니다.",
                f"{locality} 학생의 과제 수행이 악화되면 학년 수준과 주간 일정을 기준으로 진도·난도·분량을 재조정해야 합니다. {keyword} 조건 하나가 결정 기준이 되어서는 안 됩니다.",
                f"답을 베끼거나 시작을 피하는 행동이 늘 때에는 {locality} 학생의 피로와 학습량을 먼저 점검하세요. {keyword}보다 수정 가능한 계획이 제시되는지가 중요합니다.",
                f"한 달 뒤 부담만 커졌다면 {locality} 학생의 생활 시간, 현재 수준, 과제 목적을 다시 맞춰 보세요. {keyword} 설명과 실제 운영 조정은 구분해 판단해야 합니다.",
            ),
        ),
    )
    replacements += count

    phrase_pools = (
        (
            f"{persona}이 수동적으로 따라갈 가능성을 줄일 수 있습니다.",
            "operation-persona",
            (
                f"{persona}이 설명을 기다리기만 하는 시간을 줄일 수 있습니다.",
                f"{persona}에게 필요한 독립 풀이 시간을 확보했는지 판단할 수 있습니다.",
                f"{persona}이 직접 시도할 기회가 충분한지 비교할 수 있습니다.",
                f"{persona}의 질문과 수정 과정이 수업 안에 포함되는지 알 수 있습니다.",
                f"{persona}이 수동적으로 진도만 따라가는 상황을 예방하는 데 도움이 됩니다.",
                f"{persona}에게 맞는 관찰과 개입의 간격인지 확인할 수 있습니다.",
                f"{persona}이 혼자 해결하는 구간이 실제로 남는지 판단하기 쉽습니다.",
                f"{persona}의 참여 방식이 설명 중심으로 치우치는지 살펴볼 수 있습니다.",
            ),
        ),
        (
            "답변이 달라질 수 있는 조건까지 적어 두면 비교가 쉬워집니다.",
            "consult-condition",
            (
                "적용되는 경우와 예외까지 같은 표에 적으면 답변을 비교하기 수월합니다.",
                "조건이 달라질 때의 처리 방식도 기록해야 상담 내용을 정확히 대조할 수 있습니다.",
                "학생 상황에 따라 달라지는 항목을 따로 표시하면 홍보 문구와 실제 운영을 나누어 볼 수 있습니다.",
                "현재 가능한 범위와 변경될 수 있는 조건을 구분해 메모하는 편이 좋습니다.",
                "답변의 적용 대상·시점·예외를 함께 적어 두어야 학원별 차이가 분명해집니다.",
                "한 문장 답변보다 적용 기준과 조정 절차를 받아 두면 비교표를 만들기 쉽습니다.",
                "예외 상황에서 무엇이 바뀌는지도 물어야 같은 질문으로 여러 답변을 비교할 수 있습니다.",
                "확인 날짜와 적용 조건을 함께 남기면 상담 뒤에도 판단 근거가 흐려지지 않습니다.",
            ),
        ),
        (
            "말로만 좋은 안내와 실제 운영 절차를 구분할 수 있습니다.",
            "consult-proof",
            (
                "설명 문구와 실제로 확인할 수 있는 관리 과정을 나누어 볼 수 있습니다.",
                "좋아 보이는 표현이 학생의 주간 계획으로 이어지는지 판단할 수 있습니다.",
                "홍보 표현과 실제 적용 절차 사이의 차이를 확인하기 쉽습니다.",
                "상담 답변이 구체적인 실행 기준을 갖고 있는지 비교할 수 있습니다.",
                "안내된 장점이 학생 기록에 어떻게 남는지를 판단할 수 있습니다.",
                "운영 설명이 실제 행동과 점검 시점으로 이어지는지 살펴볼 수 있습니다.",
                "추상적인 장점과 확인 가능한 수업 과정을 분리할 수 있습니다.",
                "상담 문구를 그대로 믿기보다 실행 방식으로 검토할 수 있습니다.",
            ),
        ),
        (
            "작은 변화도 확인하기 쉽습니다.",
            "metric-small-change",
            (
                "점수에 앞서 나타나는 과정 변화를 놓치지 않을 수 있습니다.",
                "한 주의 우연과 반복되는 변화를 구분하기 쉬워집니다.",
                "처음에는 작아 보이는 학습 행동의 차이도 비교할 수 있습니다.",
                "학생의 변화가 어느 지점에서 시작됐는지 확인할 수 있습니다.",
                "막연한 느낌 대신 주간 기록으로 변화를 설명할 수 있습니다.",
                "한 달 동안 유지된 변화와 일시적인 반응을 나누어 볼 수 있습니다.",
                "다음 계획을 유지할지 조정할지 판단할 근거가 생깁니다.",
                "학생과 보호자가 같은 기준으로 진행 상황을 확인할 수 있습니다.",
            ),
        ),
        (
            f"{locality} 학부모가 살펴볼 실용적인 지표입니다.",
            "metric-parent",
            (
                f"{locality} 가정에서 매주 같은 방식으로 확인하기 좋은 항목입니다.",
                f"{locality} 학부모가 수업 전후를 비교할 때 활용할 수 있는 관찰 기준입니다.",
                f"{locality} 학생의 변화가 실제 생활에도 이어지는지 보여 주는 지표입니다.",
                f"{locality} 가정에서 별도 도구 없이 기록할 수 있는 현실적인 확인 항목입니다.",
                f"{locality} 학부모가 다음 상담에 가져가기 좋은 과정 자료가 됩니다.",
                f"{locality} 학생의 주간 흐름을 점수와 별도로 살펴볼 수 있는 기준입니다.",
                f"{locality} 가정이 수업 적합성을 판단하는 데 사용할 수 있는 기록입니다.",
                f"{locality} 학부모가 계획 조정 시점을 정할 때 참고할 수 있는 항목입니다.",
            ),
        ),
    )
    for before, salt, pool in phrase_pools:
        literal(before, choose(context, salt, pool))

    if replacements < 15:
        raise ValueError(
            f"{context.path}: expected at least 15 repeated-copy replacements, got {replacements}"
        )
    return MARKER + "\n" + flow, replacements


def update_jsonld_dates(source: str, path: Path) -> str:
    updated = False

    def replace(match: re.Match[str]) -> str:
        nonlocal updated
        if updated:
            return match.group(0)
        payload = json.loads(match.group(2))
        graph = payload.get("@graph", []) if isinstance(payload, dict) else []
        page_nodes = article_nodes = 0
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
            raise ValueError(f"{path}: WebPage/Article={page_nodes}/{article_nodes}")
        updated = True
        packed = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        return match.group(1) + packed + match.group(3)

    result = JSONLD_RE.sub(replace, source, count=1)
    if not updated:
        raise ValueError(f"{path}: JSON-LD not updated")
    return result


def transform(context: Context) -> Plan:
    match = FLOW_RE.search(context.before)
    if not match:
        raise ValueError(f"{context.path}: subject-copy-flow missing")
    rewritten, replacements = rewrite_flow(match.group(2), context)
    after = (
        context.before[: match.start(2)]
        + rewritten
        + context.before[match.end(2) :]
    )
    wrong_particle, correct_particle = corrected_separate_phrase(context)
    particle_fixes = 0
    if wrong_particle != correct_particle:
        particle_fixes = after.count(wrong_particle)
        after = after.replace(wrong_particle, correct_particle)
    after = update_jsonld_dates(after, context.path)
    return Plan(context, after, replacements, particle_fixes)


def unchanged(pattern: re.Pattern[str], before: str, after: str) -> bool:
    left = pattern.search(before)
    right = pattern.search(after)
    return bool(left and right and left.group(0) == right.group(0))


def jsonld_without_dates(source: str) -> object:
    match = JSONLD_RE.search(source)
    if not match:
        return None
    payload = json.loads(match.group(2))
    graph = payload.get("@graph", []) if isinstance(payload, dict) else []
    for node in graph:
        if not isinstance(node, dict):
            continue
        node_type = node.get("@type", [])
        types = set(node_type if isinstance(node_type, list) else [node_type])
        if {"WebPage", "Article"} & types:
            node.pop("dateModified", None)
    return payload


def validate(plans: list[Plan], root: Path) -> list[str]:
    errors: list[str] = []
    if len(plans) != 371:
        errors.append(f"pages={len(plans)}/371")
    for plan in plans:
        before = plan.context.before
        after = plan.after
        wrong_particle, correct_particle = corrected_separate_phrase(plan.context)
        normalized_before = before.replace(wrong_particle, correct_particle)
        relative = plan.context.path.relative_to(root).as_posix()
        for label, pattern in (
            ("school", SCHOOL_RE),
            ("FAQ", FAQ_RE),
            ("review", REVIEW_RE),
            ("network", NETWORK_RE),
        ):
            if not unchanged(pattern, before, after):
                errors.append(f"{relative}: {label} changed")
        old_answer = ANSWER_RE.search(normalized_before)
        new_answer = ANSWER_RE.search(after)
        if not old_answer or not new_answer or old_answer.group(0) != new_answer.group(0):
            errors.append(f"{relative}: answer changed beyond particle correction")
        for pattern, label in (
            (r"<title>(.*?)</title>", "title"),
            (r"<h1\b[^>]*>(.*?)</h1>", "H1"),
            (r'<link\b(?=[^>]*\brel="canonical")[^>]*\bhref="([^"]+)"', "canonical"),
            (r'<meta\s+name="description"\s+content="([^"]+)"', "description"),
        ):
            left = re.search(pattern, before, re.I | re.S)
            right = re.search(pattern, after, re.I | re.S)
            if not left or not right or left.group(0) != right.group(0):
                errors.append(f"{relative}: {label} changed")
        old_flow = FLOW_RE.search(before)
        new_flow = FLOW_RE.search(after)
        old_headings = re.findall(
            r'<section\s+class="subject-copy-section"><h2>(.*?)</h2>',
            old_flow.group(2) if old_flow else "",
            re.I | re.S,
        )
        new_headings = re.findall(
            r'<section\s+class="subject-copy-section"><h2>(.*?)</h2>',
            new_flow.group(2) if new_flow else "",
            re.I | re.S,
        )
        if old_headings != new_headings or len(new_headings) != 6:
            errors.append(f"{relative}: headings changed/count={len(new_headings)}")
        old_paragraphs = re.findall(r"<p\b[^>]*>.*?</p>", old_flow.group(2) if old_flow else "", re.I | re.S)
        new_paragraphs = re.findall(r"<p\b[^>]*>.*?</p>", new_flow.group(2) if new_flow else "", re.I | re.S)
        if len(old_paragraphs) != 12 or len(new_paragraphs) != 12:
            errors.append(
                f"{relative}: paragraph count={len(old_paragraphs)}/{len(new_paragraphs)}"
            )
        old_assets = re.findall(r'\b(?:href|src|srcset)="([^"]+)"', before, re.I)
        new_assets = re.findall(r'\b(?:href|src|srcset)="([^"]+)"', after, re.I)
        if old_assets != new_assets:
            errors.append(f"{relative}: href/src changed")
        if MARKER not in (new_flow.group(2) if new_flow else ""):
            errors.append(f"{relative}: marker missing")
        if jsonld_without_dates(normalized_before) != jsonld_without_dates(after):
            errors.append(f"{relative}: JSON-LD changed beyond dateModified")
        if wrong_particle != correct_particle and wrong_particle in after:
            errors.append(f"{relative}: wrong particle remains")
        try:
            payload_match = JSONLD_RE.search(after)
            payload = json.loads(payload_match.group(2)) if payload_match else {}
            dates = set()
            for node in payload.get("@graph", []):
                node_type = node.get("@type", []) if isinstance(node, dict) else []
                types = set(node_type if isinstance(node_type, list) else [node_type])
                if {"WebPage", "Article"} & types:
                    dates.add(node.get("dateModified"))
            if dates != {RELEASE_DATE}:
                errors.append(f"{relative}: dates={sorted(map(str, dates))}")
        except Exception as exc:
            errors.append(f"{relative}: JSON-LD {type(exc).__name__}: {exc}")
    return errors


def visible_text(source: str) -> str:
    match = re.search(r"<main\b.*?</main>", source, re.I | re.S)
    return clean(SCRIPT_STYLE_RE.sub(" ", match.group(0) if match else source))


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
        if left or right
    ]
    ordered = sorted(scores)
    return {
        "average": round(statistics.mean(scores), 4),
        "p90": round(ordered[int(len(ordered) * 0.9)], 4),
        "max": round(max(scores), 4),
    }


def atomic_write(path: Path, value: str) -> None:
    temporary = path.with_name(path.name + ".elementary-diff.tmp")
    temporary.write_text(value, encoding="utf-8", newline="\n")
    temporary.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    root = args.root.resolve()
    target = root / "과목별학원" / CATEGORY
    paths = sorted(target.glob("*/index.html"))
    contexts = [extract_context(path, index) for index, path in enumerate(paths)]
    plans = [transform(context) for context in contexts]
    errors = validate(plans, root)
    before_articles = [article_text(plan.context.before) for plan in plans]
    after_articles = [article_text(plan.after) for plan in plans]
    before_full = [visible_text(plan.context.before) for plan in plans]
    after_full = [visible_text(plan.after) for plan in plans]
    report = {
        "mode": "APPLY" if args.apply else "DRY-RUN",
        "pages": len(plans),
        "changed": sum(plan.context.before != plan.after for plan in plans),
        "replacements": {
            "total": sum(plan.replacements for plan in plans),
            "min": min((plan.replacements for plan in plans), default=0),
            "average": round(statistics.mean(plan.replacements for plan in plans), 2),
            "max": max((plan.replacements for plan in plans), default=0),
        },
        "particle_fixes": {
            "pages": sum(plan.particle_fixes > 0 for plan in plans),
            "total": sum(plan.particle_fixes for plan in plans),
        },
        "visible_chars_average": {
            "before": round(statistics.mean(map(len, before_full)), 1),
            "after": round(statistics.mean(map(len, after_full)), 1),
        },
        "article_similarity": {
            "before": similarity(before_articles),
            "after": similarity(after_articles),
        },
        "full_page_similarity": {
            "before": similarity(before_full),
            "after": similarity(after_full),
        },
        "unique_articles": len(set(after_articles)),
        "errors": len(errors),
        "samples": errors[:30],
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
