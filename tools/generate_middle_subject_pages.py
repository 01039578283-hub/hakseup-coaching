from __future__ import annotations

import argparse
import json
import re
from dataclasses import replace
from pathlib import Path
from types import ModuleType

import generate_yeongsu_subject_pages as base
from source_copy_utils import distribute_source_paragraphs, source_paragraphs, source_theme


ROOT = Path(__file__).resolve().parents[1]
DESKTOP = Path.home() / "Desktop"
MIDDLE_GRADES = tuple(base.GRADE_ORDER[6:9])
MIDDLE_PUBLISHED_DATE = "2026-08-13"


def _source_theme(record: base.Record) -> str:
    """Return the short, locality-specific angle authored in the source sheet."""

    source = re.sub(r"\s+", " ", record.source_text).strip()
    inverted = re.match(
        rf"LOCAL ACADEMY GUIDE\s+(.{{3,40}}?)\s+{re.escape(record.locality)}\s*중등\s*영어학원(?:\s|,)",
        source,
    )
    if inverted:
        theme = inverted.group(1).strip(" ,·:-")
        if theme:
            return theme
    match = re.match(
        rf"LOCAL ACADEMY GUIDE\s+{re.escape(record.locality)}\s*중등\s*영어학원,?\s*"
        rf"(.{{3,48}}?)(?=\s+(?:중등\s+(?:영어|시기)|중학교|초등\s+영어|영어(?:를|\s+(?:시험|유형|문법|문제|공부|수업|진도|단어|개념|문장))|"
        rf"새\s+학기|중[123]\s+학생|학년이|객관식|중학생|진도는|문법\s+문제|기말고사|"
        rf"시험(?:이|을|에서|이\s+끝난)|학원에|영어\s+학원을|단어를|답지를|공부(?:를|\s+시간)|문제의|중간고사|방학\s+동안|와와학습)|[.!?])",
        source,
    )
    if not match:
        return record.english_focus
    theme = match.group(1).strip(" ,·:-")
    if any(token in theme for token in ("LOCAL", "수업 진행방식", "핵심 키워드")):
        return record.english_focus
    return theme


def _source_sentences(record: base.Record) -> list[str]:
    """Recover useful prose from the sheet without exposing flattened headings.

    The workbook cells contain authored copy as plain text.  We treat that copy as
    content only, remove its document labels, and select sentences later by topic.
    """

    source = re.sub(r"\s+", " ", record.source_text).strip()
    source = source.replace("LOCAL ACADEMY GUIDE", " ")
    for marker in (
        "수업 진행방식",
        "선생님 특징",
        "핵심 포인트",
        "학생별 학습 목표 점검",
    ):
        source = source.replace(marker, ". ")
    source = re.sub(r"중등 영어 [^.!?]{0,45}? 로드맵", ". ", source)
    source = re.sub(r"\s+[1-4]\.\s+", ". ", source)

    forbidden = re.compile(
        r"LOCAL ACADEMY GUIDE|핵심 키워드|(?<![가-힣])원고(?![가-힣])|"
        r"수업 진행방식|실시간\s*수업|온라인\s*수업|입시합격|합격전략|"
        r"실제 후기|성적이 향상|점수가 올랐",
        re.I,
    )
    unrelated = ("초등", "고등", "고교", "여고", "수학", "국어")
    useful = ("영어", "어휘", "문법", "문장", "독해", "서술형", "오답", "복습", "학교", "시험", "학습", "상담")
    theme = _source_theme(record)
    title_prefixes = (
        f"{record.locality} 중등 영어학원, {theme}",
        f"{record.locality} 중등 영어학원 {theme}",
        f"{theme} {record.locality} 중등 영어학원",
    )
    leading_labels = tuple(sorted((
        "개념 정리와 유형 학습",
        "오답 관리와 학습 피드백",
        "학생의 설명을 바탕으로 확인하는 상담",
        "목표에 맞춘 학습 방향 상담",
        "현재 수준 확인",
        "문법과 문장 구조",
        "문법 개념과 적용",
        "독해와 서술형 대비",
        "독해와 학교 시험 대비",
        "학교 시험 학습 점검",
        "학교 시험 학습 관리",
        "학교 시험 준비",
        "학교 공부와 기본기 연결",
        "학교생활과 학습 목표",
        "어휘와 문장 구조",
        "어휘 기반 다지기",
        "꾸준함을 만드는 학습 코칭",
        "반복보다 학습 과정 점검",
    ), key=len, reverse=True))
    non_middle_schools = tuple(
        school for school in record.schools
        if not (school.endswith("중") or school.endswith("중학교"))
    )
    sentences: list[str] = []
    seen: set[str] = set()
    for raw in re.split(r"(?<=[.!?])\s+", source):
        sentence = re.sub(r"\s+", " ", raw).strip(" .")
        for prefix in title_prefixes:
            if sentence.startswith(prefix + " "):
                sentence = sentence[len(prefix):].strip()
                break
        for label in leading_labels:
            if sentence.startswith(label + " "):
                sentence = sentence[len(label):].strip()
                break
        sentence = re.sub(r"^(?:학습 과목과 목표를 함께 고려|현재 목표에 맞춘 상담|이해하는 공부를 중심으로 안내)\s+", "", sentence)
        if not 45 <= len(sentence) <= 230:
            continue
        if forbidden.search(sentence) or any(token in sentence for token in unrelated):
            continue
        if any(school in sentence for school in non_middle_schools):
            continue
        if not any(token in sentence for token in useful):
            continue
        normalized = re.sub(r"\W+", "", sentence)
        if normalized in seen:
            continue
        seen.add(normalized)
        sentences.append(sentence + ("" if sentence.endswith((".", "!", "?")) else "."))
    return sentences


def _take_source_sentences(
    record: base.Record,
    sentences: list[str],
    used: set[str],
    keywords: tuple[str, ...],
    count: int,
    salt: str,
) -> list[str]:
    ranked = sorted(
        (sentence for sentence in sentences if sentence not in used),
        key=lambda sentence: (
            -sum(sentence.count(keyword) for keyword in keywords),
            base.stable_number(record.key, f"{salt}|{sentence}"),
        ),
    )
    selected = ranked[:count]
    used.update(selected)
    return selected


def _subject_values(subject: str) -> dict[str, object]:
    if subject == "math":
        return {
            "module": "generate_high_math_subject_pages",
            "workbook": DESKTOP / "구글시트로 뽑은거" / "중등 수학학원.xlsx",
            "category": "중등수학학원",
            "label": "중등 수학학원",
            "subject_label": "수학",
            "grade_attr": "math_grades",
            "focus_attr": "math_focus",
            "evidence_attr": "math_evidence",
            "seed": "middle-math",
        }
    if subject == "english":
        return {
            "module": "generate_high_english_subject_pages",
            "workbook": DESKTOP / "구글시트로 뽑은거" / "중등 영어학원.xlsx",
            "category": "중등영어학원",
            "label": "중등 영어학원",
            "subject_label": "영어",
            "grade_attr": "english_grades",
            "focus_attr": "english_focus",
            "evidence_attr": "english_evidence",
            "seed": "middle-english",
        }
    raise ValueError(f"지원하지 않는 과목: {subject}")


def _protect_and_replace(text: str, records: list[base.Record] | tuple[base.Record, ...]) -> str:
    protected: dict[str, str] = {}
    values: set[str] = set()
    for record in records:
        values.update(
            value for value in (
                record.locality,
                record.service_region,
                record.service_city,
                record.center_name,
                record.address,
                record.legal_name,
                record.registration,
                record.location_note,
                *record.schools,
            ) if value
        )
    for index, value in enumerate(sorted(values, key=len, reverse=True)):
        token = f"@@FACT_{index:05d}@@"
        if value in text:
            text = text.replace(value, token)
            protected[token] = value
    text = text.replace("HIGH SCHOOL", "MIDDLE SCHOOL").replace("HIGH GRADE", "MIDDLE GRADE").replace("고등", "중등")
    text = text.replace("모의고사", "학기별 평가").replace("고1·고2·고3", "중1·중2·중3")
    for token, value in protected.items():
        text = text.replace(token, value)
    return text


def _deep_middle(value: object, records: list[base.Record]) -> object:
    if isinstance(value, str):
        return _protect_and_replace(value, records)
    if isinstance(value, list):
        return [_deep_middle(item, records) for item in value]
    if isinstance(value, dict):
        return {key: _deep_middle(item, records) for key, item in value.items()}
    return value


def configure(subject: str) -> ModuleType:
    cfg = _subject_values(subject)
    module = __import__(str(cfg["module"]))
    category = str(cfg["category"])
    label = str(cfg["label"])
    subject_label = str(cfg["subject_label"])
    grade_attr = str(cfg["grade_attr"])
    focus_attr = str(cfg["focus_attr"])
    evidence_attr = str(cfg["evidence_attr"])
    seed = str(cfg["seed"])

    original_schema_graph = module.schema_graph
    original_render_facts = module.render_facts
    original_render_local_page = module.render_local_page
    original_render_hub = module.render_hub

    module.DEFAULT_WORKBOOK = Path(cfg["workbook"])
    module.CATEGORY = category
    module.CATEGORY_LABEL = label
    module.TARGET_ROOT = ROOT / "과목별학원" / category
    module.HIGH_GRADES = MIDDLE_GRADES

    def title(record: base.Record) -> str:
        return f"{record.locality} {label}"

    def page_url(record: base.Record) -> str:
        return base.absolute_url("과목별학원", category, record.slug)

    def middle_grades(record: base.Record) -> tuple[str, ...]:
        return tuple(grade for grade in getattr(record, grade_attr) if grade in MIDDLE_GRADES)

    def middle_schools(record: base.Record) -> tuple[str, ...]:
        corrections = {"상남동", "신월동", "사파동"}
        return tuple(
            school for school in record.schools
            if school.endswith("중") or school.endswith("중학교")
            if not (record.locality in corrections and school == "창원중")
        )

    def build_persona(record: base.Record, grade: str) -> str:
        learner = f"{base.GRADE_EXPANDED[grade]} 학생" if grade else "학년별 수업 가능 여부부터 상담에서 확인해야 하는 학생"
        if subject == "math":
            frames = (
                f"개념은 기억하지만 유형이 바뀌면 첫 식을 정하기 어려운 {learner}",
                f"학교 문제는 풀어도 서술형에서 조건과 풀이 근거를 빠뜨리는 {learner}",
                f"계산 실수와 개념 누락을 구분하지 않아 같은 오답을 반복하는 {learner}",
                f"단원별 문제는 풀지만 두 개념을 연결하는 문항에서 멈추는 {learner}",
                f"숙제는 마쳐도 틀린 문제를 다시 푸는 날짜가 정해지지 않은 {learner}",
                f"풀이 속도보다 문제 조건을 읽고 순서를 세우는 연습이 필요한 {learner}",
                f"중학교 내신 범위와 누적 개념 복습을 함께 계획해야 하는 {learner}",
                f"답은 맞혀도 왜 그 식을 세웠는지 말로 설명하기 어려운 {learner}",
            )
        else:
            frames = (
                f"단어 뜻은 외웠지만 문장 안에서 의미를 고르기 어려운 {learner}",
                f"문법 문제는 풀어도 실제 문장에서 적용 근거를 설명하지 못하는 {learner}",
                f"독해 지문을 끝까지 읽지만 답의 근거 문장을 표시하지 않는 {learner}",
                f"학교 본문은 암기해도 낯선 글의 구조를 스스로 나누기 어려운 {learner}",
                f"서술형 답안을 쓰면서 핵심 표현과 문법 조건을 빠뜨리는 {learner}",
                f"어휘·문법·독해를 따로 공부해 한 지문에서 연결하지 못하는 {learner}",
                f"시험 직전 문제 수만 늘리고 틀린 선택지의 이유를 남기지 않는 {learner}",
                f"중학교 내신과 누적 어휘 복습을 한 주 계획에 넣어야 하는 {learner}",
                f"본문 해석은 가능하지만 핵심 문장을 한글이나 영어로 요약하기 어려운 {learner}",
                f"문법 개념을 기억해도 서술형 답안에서 어순과 시제를 함께 점검하지 못하는 {learner}",
                f"긴 문장을 만날 때 주어·동사보다 모르는 단어부터 찾느라 구조를 놓치는 {learner}",
                f"오답을 고친 뒤 같은 근거로 새 선택지를 판단할 수 있는지 확인이 필요한 {learner}",
                f"학교 본문과 누적 독해의 복습 날짜가 겹쳐 시험 직전 계획이 흔들리는 {learner}",
                f"듣기에서 놓친 표현을 대본과 음원으로 다시 확인하는 습관이 필요한 {learner}",
                f"단어장을 외운 날과 실제 지문에서 어휘를 다시 사용한 날을 구분하지 않는 {learner}",
                f"정답은 고르지만 오답 선택지의 문법·내용상 오류를 설명하기 어려운 {learner}",
                f"학교 범위는 따라가도 이전 학년 어휘와 문장 구조의 빈틈이 남아 있는 {learner}",
                f"서술형에서 요구한 조건을 찾고도 답안에 모두 반영했는지 점검하지 않는 {learner}",
                f"복습 시간은 확보했지만 어휘·문법·독해의 완료 기준이 분명하지 않은 {learner}",
                f"한 지문을 푼 뒤 근거 표시와 짧은 요약까지 이어 가는 연습이 필요한 {learner}",
            )
        return base.choose(record.key, frames, f"{seed}-persona")

    def make_records(workbook: Path) -> list[base.Record]:
        records = base.make_records(workbook)
        prepared: list[base.Record] = []
        for record in records:
            grades = middle_grades(record)
            selected = grades[base.stable_number(record.key, f"{seed}-grade") % len(grades)] if grades else ""
            prepared.append(replace(
                record,
                common_grades=grades,
                selected_grade=selected,
                persona=build_persona(record, selected),
            ))
        return prepared

    def meta_description(record: base.Record) -> str:
        if subject == "math":
            values = (
                f"{record.locality} 중등 수학학원 상담 전 개념 연결, 학교 시험, 서술형 풀이, 오답 재풀이와 가능 학년·센터 확인 기준을 정리했습니다.",
                f"{record.locality} 중등 수학학원 선택에 필요한 현재 진단, 교재와 시험 자료, 풀이 기록, 주간 복습과 상담 전 센터 확인 질문을 안내합니다.",
                f"{record.locality} 중등 수학학원을 알아보는 학부모를 위해 가능 학년, 개념·유형·계산 진단, 학교 자료와 첫 주 계획을 담았습니다.",
            )
        else:
            grades = middle_grades(record)
            grade_text = "·".join(grades) if grades else "중등 가능 학년"
            focus = getattr(record, focus_attr)
            values = (
                f"{record.locality} 중등 영어학원 상담 전 어휘 누적, 문법 적용, 독해 근거, 서술형 답안과 가능 학년·센터 확인 기준을 정리했습니다.",
                f"{record.locality} 중등 영어학원 선택에 필요한 현재 진단, 학교 시험 자료, 답안 기록, 주간 복습과 상담 전 센터 확인 질문을 안내합니다.",
                f"{record.locality} 중등 영어학원을 알아보는 학부모를 위해 가능 학년, 어휘·문법·독해 진단, 학교 자료와 첫 주 계획을 담았습니다.",
                f"{record.locality} 중등 영어학원에서 확인할 {grade_text} 수업 범위, {focus}, 학교 영어 자료와 14일 복습 계획을 안내합니다.",
                f"{record.locality} 중등 영어학원 비교 전 최근 시험지로 {base.with_josa(focus, '을', '를')} 점검하고, 가능 학년·중학교 자료·상담 질문을 확인하세요.",
                f"{record.locality} 중등 영어학원 선택 기준을 {grade_text}, 학교 내신 자료, 오답 기록과 어휘·문법·독해 복습 순서로 나누어 정리했습니다.",
                f"{record.locality} 중학생 영어 상담을 준비한다면 가능 학년과 학교 범위, {focus}, 답안 재확인 기준을 먼저 살펴보세요.",
                f"{record.locality} 중등 영어학원 안내입니다. {grade_text} 가능 범위와 학교 참고 정보, {focus} 진단 및 상담 체크리스트를 확인하세요.",
            )
        value = base.choose(record.key, values, f"{seed}-meta")
        if not 65 <= len(value) <= 105:
            raise ValueError(f"{record.locality} 메타 설명 길이 오류: {len(value)}")
        return value

    def grade_sentence(record: base.Record) -> str:
        grades = middle_grades(record)
        if grades:
            return (
                f"확인된 센터 정보상 {subject_label} 수업 가능 중등 학년은 {'·'.join(grades)}입니다. "
                "현재 개설 시간과 학생의 학교 진도는 상담에서 다시 확인해야 합니다."
            )
        return (
            f"확인된 센터 정보에 {subject_label} 수업 가능 중등 학년이 따로 표시되지 않았습니다. "
            "학년을 추정하지 말고 현재 개설 범위부터 상담에서 확인하세요."
        )

    def school_sentence(record: base.Record) -> str:
        schools = middle_schools(record)
        if schools:
            shown = "·".join(schools[:5])
            return (
                f"확인된 중학교 참고 정보는 {shown}{' 등' if len(schools) > 5 else ''}입니다. "
                "학교별 시험 범위와 교재는 최신 자료로 다시 대조해야 합니다."
            )
        return (
            "확인된 중학교 정보가 없습니다. "
            "최근 시험 범위표와 교재를 준비해 학교 자료의 반영 방법을 문의하세요."
        )

    def english_content_sections(record: base.Record) -> tuple[str, list[dict[str, object]]]:
        focus = record.english_focus
        evidence = record.english_evidence
        focus_obj = base.with_josa(focus, "을", "를")
        evidence_obj = base.with_josa(evidence, "을", "를")
        theme = _source_theme(record)
        grades = middle_grades(record)
        schools = middle_schools(record)
        selected_label = base.GRADE_EXPANDED.get(record.selected_grade, "중학생")
        school_anchor = schools[0] if schools else "재학 중학교"
        source_sentences = _source_sentences(record)
        used_source: set[str] = set()

        def sourced(keywords: tuple[str, ...], count: int, salt: str) -> list[str]:
            return _take_source_sentences(
                record, source_sentences, used_source, keywords, count, f"{seed}-{salt}"
            )

        profile = {
            "듣기 핵심어와 문장 이해": (
                "음원에서 놓친 구간과 대본에서 이해하지 못한 문장을 따로 표시합니다",
                "다시 들은 뒤 핵심어를 적고 한 문장으로 내용을 요약할 수 있어야 합니다",
            ),
            "문법 개념의 문장 적용": (
                "맞힌 문항도 선택한 문법 규칙을 실제 문장에 대입해 설명합니다",
                "형태만 고치는 데서 끝내지 않고 어순·시제·수일치 근거를 함께 남깁니다",
            ),
            "서술형 답안의 근거와 표현": (
                "문제에서 요구한 조건과 답안에 사용한 핵심 표현을 나란히 확인합니다",
                "틀린 문장을 고친 뒤 같은 조건으로 한 문장을 새로 써 봅니다",
            ),
            "어휘 누적과 문장 적용": (
                "뜻을 맞힌 단어도 지문 속 의미와 함께 다시 분류합니다",
                "암기 확인 뒤 예문을 바꾸어 쓰고 이틀 뒤 같은 어휘를 다시 확인합니다",
            ),
            "독해 근거 표시와 문장 구조": (
                "정답 문장뿐 아니라 오답 선택지가 틀린 근거도 지문에 표시합니다",
                "주어·동사·수식 관계를 나눈 뒤 문단의 역할을 짧게 요약합니다",
            ),
            "어휘·문법·독해의 연결": (
                "어휘 뜻, 문장 구조, 선택지 판단이 어느 지점에서 끊겼는지 나눕니다",
                "한 지문에서 찾은 오류를 어휘·문법·독해 복습으로 다시 연결합니다",
            ),
        }.get(
            focus,
            (
                "첫 답안과 고친 답안 사이에서 설명이 끊긴 지점을 표시합니다",
                "같은 기준을 새 문장에 적용하고 다음 확인 날짜를 남깁니다",
            ),
        )

        answer_bank = (
            f"{record.locality} 중등 영어학원은 교재 수보다 학생의 답안 근거로 비교하세요. {focus}에서 막힌 지점과 다음 확인 날짜가 계획에 함께 있어야 합니다.",
            f"{record.locality} 중등 영어 상담에서는 {selected_label}의 최근 시험지를 어휘·문법·독해로 나눠 보세요. {evidence_obj} 확인하면 첫 복습 순서를 정하기 쉽습니다.",
            f"{record.locality}에서 중등 영어학원을 찾는다면 {school_anchor} 시험 범위와 실제 답안을 함께 준비하세요. 학교 진도와 누적 복습의 완료 기준을 따로 물어보는 것이 좋습니다.",
            f"{record.locality} 중등 영어학원 선택의 핵심은 {focus_obj} 학생이 혼자 재현할 수 있는지입니다. 정답을 고친 이유와 이틀 뒤 다시 쓴 결과까지 비교하세요.",
            f"{record.locality} 중학생 영어는 본문 암기만으로 판단하기 어렵습니다. 근거 표시, 문장 구조 설명, 서술형 재작성으로 현재 수준을 확인하세요.",
            f"{record.locality} 중등 영어 상담 전에는 최근 시험지·현재 교재·학교 범위표를 한꺼번에 준비하세요. 자료마다 무엇을 확인할지 정해야 상담 결과가 주간 계획으로 이어집니다.",
            f"{record.locality} 중등 영어학원 비교표에는 가능 학년, 학교 자료 반영 방법, {focus}, 오답 재확인 날짜를 함께 적으세요.",
            f"{record.locality}에서 영어 공부의 우선순위를 정할 때는 점수보다 처음 설명이 끊긴 단계를 찾으세요. {evidence_obj} 기준으로 일주일 뒤 다시 확인하면 됩니다.",
            f"{record.locality} 중등 영어는 어휘·문법·독해를 따로 늘리기보다 한 지문에서 연결하는 과정이 중요합니다. 첫 답안과 고친 답안을 함께 확인하세요.",
            f"{record.locality} 중등 영어학원을 알아볼 때는 {base.with_josa(theme, '을', '를')} 상담 주제로 삼아 보세요. 학생이 직접 남긴 기록과 실행 가능한 복습 간격으로 답변을 비교할 수 있습니다.",
        )
        answer = base.choose(record.key, answer_bank, f"{seed}-answer-expanded")

        intro_source = sourced(("현재", "목표", "방향", "상담", "상태"), 3, "source-intro")
        focus_source = sourced(("어휘", "문법", "문장", "독해", "서술형", "오답"), 3, "source-focus")
        school_source = sourced(("학교", "시험", "내신", "학년", "범위"), 2, "source-school")
        plan_source = sourced(("복습", "오답", "계획", "관리", "꾸준", "피드백"), 2, "source-plan")

        intro_paragraphs = [
            f"{record.locality}의 이번 안내는 {base.with_josa(theme, '을', '를')} 중심으로 구성했습니다. {record.persona}이라면 점수만 전달하기보다 최근 답안에서 혼자 설명할 수 있는 부분과 막힌 부분을 먼저 나누는 것이 좋습니다.",
            *intro_source,
        ]
        while len(intro_paragraphs) < 3:
            intro_paragraphs.append(base.choose(record.key, (
                f"{record.center_name} 상담에서는 현재 교재와 최근 시험지를 함께 놓고 학생의 목표에 맞는 시작 범위를 확인하세요.",
                f"{record.locality}에서 학습 방향을 비교할 때는 학교 진도와 누적 영어 실력을 한 기준으로 섞지 말고 각각의 완료 조건을 적어 두세요.",
                f"첫 상담의 결과는 교재 이름보다 학생이 이번 주에 바꿀 행동과 다시 확인할 날짜로 설명되어야 합니다.",
            ), f"{seed}-intro-fallback-{len(intro_paragraphs)}"))

        focus_paragraphs = [
            *focus_source,
            f"이 페이지에서 우선 확인할 영역은 {focus}입니다. 진단할 때는 ‘{profile[0]}’. 이어서 ‘{profile[1]}’라는 두 기준으로 첫 답안과 수정 답안을 비교하세요.",
            f"확인 기록은 {evidence}입니다. 한 번 고친 결과만 보지 말고 같은 유형을 다시 만났을 때 학생이 근거를 재현하는지 살펴봐야 복습 완료 여부를 판단할 수 있습니다.",
        ]
        while len(focus_paragraphs) < 3:
            focus_paragraphs.insert(0, f"{focus_obj} 점수표의 한 항목으로만 보지 말고 실제 문장과 선택지 판단 과정에서 확인하세요.")

        grade_variants = {
            "중1": (
                "초등 영어에서 중학교 평가로 넘어갈 때 어휘 암기와 문장 구조 설명이 함께 되는지 확인",
                "짧은 문장의 주어·동사 찾기와 교과서 핵심 어휘의 문장 속 의미를 우선 점검",
                "학교 본문을 외우기 전에 기본 문장 구조와 질문에 맞는 답의 형태를 확인",
                "첫 시험 전에는 문제 수보다 범위표 읽기, 어휘 재사용, 근거 표시 습관을 만들기",
            ),
            "중2": (
                "문법 단원이 늘어나는 시기에 규칙 암기와 실제 문장 적용의 차이를 답안으로 확인",
                "길어진 지문에서 문장 구조와 문단의 핵심 근거를 연결해 설명하는 연습을 점검",
                "누적 어휘 복습과 학교 본문 준비를 다른 날짜에 배치해 밀림 여부를 확인",
                "서술형 조건을 찾고 어순·시제·수일치를 답안에 반영했는지 다시 대조",
            ),
            "중3": (
                "현재 학교 범위와 고교 영어에 필요한 누적 어휘·독해 빈틈을 따로 진단",
                "익숙한 본문 암기와 낯선 지문에서 근거를 찾는 능력을 분리해 확인",
                "서술형 재작성과 문단 요약을 통해 문법·독해를 한 답안에서 연결",
                "진도 선행보다 중학교 오답을 혼자 설명하고 다시 해결하는 재현 기준을 점검",
            ),
        }
        grade_items = [
            f"{grade}: {base.choose(record.key, grade_variants[grade], f'{seed}-grade-item-{grade}')}"
            for grade in grades
        ] or ["현재 중등 가능 학년 표기가 없어 학년과 개설 범위를 상담에서 먼저 대조"]
        grade_paragraphs = [
            grade_sentence(record),
            f"학년 이름만 같아도 필요한 시작점은 다를 수 있습니다. {selected_label}을 기준으로 최근 학교 범위, 이전 학기 오답, 집에서 확보할 수 있는 복습 시간을 함께 놓고 아래 항목을 대조하세요.",
        ]

        school_items = [
            f"{school}: {base.choose(record.key, (
                '최근 영어 시험 범위표와 현재 교재의 단원 순서를 함께 확인',
                '학생이 직접 쓴 서술형 답안과 감점된 조건을 상담 자료로 준비',
                '본문 암기 범위와 누적 어휘·독해 복습 범위를 나누어 질문',
                '시험이 끝난 뒤 다시 볼 대표 오답과 재확인 날짜를 정리',
            ), f'{seed}-school-item-{position}-{school}')}"
            for position, school in enumerate(schools[:5], 1)
        ]
        if not school_items:
            school_items = ["재학 중학교: 최신 영어 범위표·교재·학생 답안을 직접 준비해 반영 방법을 문의"]
        school_paragraphs = [school_sentence(record), *school_source]
        school_paragraphs.append(
            "학교명은 수업 가능 범위를 확인하는 참고 정보이고, 학교별 출제 방식이나 현재 시험 범위를 단정하는 자료는 아닙니다. 최신 범위표와 학생 답안을 기준으로 실제 준비 내용을 다시 확인하세요."
        )

        plan_items = [
            f"1~2일 · {base.choose(record.key, ('최근 시험지에서 처음 막힌 문장 표시', '정답을 가리고 답의 근거 다시 설명', '어휘·문법·독해 오답을 원인별로 분류'), f'{seed}-plan-1')}",
            f"3~5일 · {base.choose(record.key, ('현재 교재에서 같은 개념의 짧은 문장 재적용', '오답 선택지가 틀린 이유를 한 줄로 기록', '학교 본문과 누적 어휘 복습 시간을 분리'), f'{seed}-plan-2')}",
            f"6~9일 · {base.choose(record.key, ('낯선 문장에 같은 문법 기준 적용', '지문 근거 표시 뒤 두 문장으로 요약', '서술형 조건을 바꾸어 새 답안 작성'), f'{seed}-plan-3')}",
            f"10~14일 · {base.choose(record.key, ('첫 답안과 다시 쓴 답안을 나란히 비교', '같은 오류가 남으면 분량보다 복습 간격 조정', '학생이 혼자 재현한 범위로 다음 계획 결정'), f'{seed}-plan-4')}",
        ]
        plan_paragraphs = [
            *plan_source,
            f"14일 계획은 진도를 보장하는 시간표가 아니라 {evidence_obj} 같은 기준으로 두 번 확인하기 위한 예시입니다. 학교 일정과 실제 공부 가능 시간에 맞춰 분량을 줄이거나 날짜를 옮기세요.",
        ]
        while len(plan_paragraphs) < 3:
            plan_paragraphs.insert(0, "첫 주에는 새 문제집을 늘리기보다 진단에 사용한 답안을 같은 기준으로 다시 확인하는 편이 좋습니다.")

        checklist = [
            f"{record.center_name}의 현재 {('·'.join(grades) if grades else '중등')} 영어 개설 시간 재확인",
            f"최근 시험지에서 {focus} 관련 문항 세 개 표시",
            f"{school_anchor} 최신 영어 범위표와 현재 교재 준비",
            f"첫 주에 남길 기록을 ‘{evidence}’로 정할 수 있는지 질문",
            "학교 내신 준비와 누적 어휘·독해 복습의 날짜를 따로 확인",
            "결석·과제 미완료가 생겼을 때 분량과 재확인 날짜를 조정하는 기준 질문",
            "교습비와 실제 반 편성은 공개 자료 및 최신 상담 답변으로 재확인",
        ]
        closing_source = sourced(
            ("학생", "영어", "학습", "상담", "이해", "과정"),
            2,
            "source-closing",
        )
        consultation_paragraphs = [
            *closing_source,
            f"상담에는 최근 시험지, 현재 교재, 학교 범위표, 학생이 직접 쓴 답안을 준비하세요. {record.locality}에서 확인할 주소는 {record.address}이며, 이동 시간과 실제 가능한 요일도 함께 적어 두는 편이 좋습니다.",
            f"확인된 사실과 상담에서 새로 확인할 조건을 구분해야 합니다. 센터명·주소·등록 정보·가능 학년은 페이지의 센터 정보와 대조하고, 시간표·교습비·학생별 시작 범위는 최신 답변을 따로 기록하세요.",
        ]

        core_sections = [
            {"heading": f"{focus_obj} 답안에서 확인하는 기준", "paragraphs": focus_paragraphs},
            {"heading": f"{record.locality} 중1·중2·중3 영어 점검 순서", "paragraphs": grade_paragraphs, "items": grade_items},
            {"heading": f"{record.locality} 학교 영어 자료를 상담에 쓰는 법", "paragraphs": school_paragraphs, "items": school_items},
            {"heading": f"{record.locality} 중등 영어 14일 재확인 계획", "paragraphs": plan_paragraphs, "items": plan_items},
        ]
        rotation = base.stable_number(record.key, f"{seed}-section-rotation") % len(core_sections)
        core_sections = core_sections[rotation:] + core_sections[:rotation]
        sections: list[dict[str, object]] = [
            {"heading": f"{record.locality} 중등 영어, {theme}", "paragraphs": intro_paragraphs},
            *core_sections,
            {"heading": f"{record.locality} 중등 영어 상담 전 최종 체크", "paragraphs": consultation_paragraphs, "items": checklist},
        ]
        return answer, sections

    def content_sections(record: base.Record) -> tuple[str, list[dict[str, object]]]:
        if subject == "english":
            return english_content_sections(record)
        focus = getattr(record, focus_attr)
        evidence = getattr(record, evidence_attr)
        obj_focus = base.with_josa(focus, "을", "를")
        obj_evidence = base.with_josa(evidence, "을", "를")
        if subject == "math":
            answer_bank = (
                f"{record.locality} 중등 수학학원을 고를 때는 진도보다 풀이 설명을 먼저 확인하세요. {focus}에서 멈춘 지점을 찾고 다음 재풀이 날짜까지 정해야 합니다.",
                f"{record.locality} 중등 수학 상담에서는 최근 시험지에서 개념·조건·계산 중 무엇이 흔들렸는지 나누어야 합니다. 진단 결과가 학교 일정과 주간 행동으로 이어지는지 살펴보세요.",
                f"{record.locality}에서 중등 수학학원을 비교한다면 최근 시험지와 학생이 쓴 풀이를 준비하세요. 첫 식의 이유와 틀린 문제를 혼자 다시 푼 결과가 선택 기준입니다.",
                f"{record.locality} 중등 수학학원 선택의 핵심은 문제 수가 아니라 개념을 다른 유형에 적용하는 과정입니다. 답을 고친 근거까지 말할 수 있는지 확인하세요.",
            )
            headings = (
                f"{record.locality} 중등 수학의 출발점을 찾는 진단",
                f"{obj_focus} 기록에서 구분하는 방법",
                "중등 가능 학년과 학교 시험 자료 확인",
                "개념·유형·오답을 한 주 계획에 배치하는 순서",
                "고교 수학 전환 전에 확인할 설명과 재풀이",
                f"{record.locality} 중등 수학 상담 전 체크리스트",
            )
            paragraph_banks = (
                (
                    f"{record.persona}이라면 새 문제집보다 최근에 틀린 세 문항이 더 유용합니다. 정답을 가리고 문제 조건과 첫 식을 다시 설명하게 해 보세요.",
                    f"진단은 단원 이름을 묻는 데서 끝나지 않습니다. {obj_focus} 학생이 자기 말로 설명하고 비슷한 문항에 적용할 수 있는지 확인해야 합니다.",
                ),
                (
                    f"수학 오답은 개념 누락, 조건 해석, 계산 실수, 풀이 순서로 나누어 기록할 수 있습니다. {obj_evidence} 첫 답안과 나란히 놓으면 원인이 선명해집니다.",
                    "정답만 다시 적으면 오답 원인이 남지 않습니다. 첫 식을 세운 이유, 중간 계산, 검산 결과를 짧게 남겨 다음 복습에서도 같은 기준을 사용하세요.",
                ),
                (grade_sentence(record), school_sentence(record)),
                (
                    "학교 숙제와 누적 복습을 한날에 몰지 말고 개념 설명, 대표 유형, 재풀이를 서로 다른 날에 배치하세요. 완료 기준은 문제 수보다 혼자 설명할 수 있는지로 정하는 편이 좋습니다.",
                    f"{obj_evidence} 주간 계획에 넣을 때는 다시 볼 날짜를 함께 적으세요. 같은 오류가 반복되면 분량을 늘리기보다 확인 간격을 조정해야 합니다.",
                ),
                (
                    "중학교 수학에서 고교 과정으로 이어질 때는 빠른 선행보다 식을 세운 이유와 단원 사이의 연결을 설명하는 힘이 중요합니다. 누적 빈틈이 남아 있다면 현재 학년 개념부터 정리하세요.",
                    "고교 전환 준비는 어려운 문제를 미리 푸는 일이 아닙니다. 학교 시험이 끝난 뒤에도 대표 오답을 다시 풀고 풀이를 재현할 수 있는지를 확인하는 과정입니다.",
                ),
                (
                    "상담에서는 최근 시험지, 현재 교재, 학교 범위표, 학생이 직접 쓴 풀이를 함께 준비하세요. 첫 주에 바꿀 행동과 재확인 날짜가 답변에 포함되어야 합니다.",
                    "센터 정보는 주소·등록 정보·가능 학년·학교 참고 자료처럼 확인 가능한 사실과 대조하세요. 개설 시간과 교습비는 최신 상담 자료로 다시 확인해야 합니다.",
                ),
            )
            checklist = (
                "최근 시험지에서 처음 막힌 문항과 이유 표시",
                "현재 교재의 진도와 혼자 다시 풀 수 있는 범위 확인",
                "학교 시험 일정과 주간 복습 가능 시간 정리",
                "첫 주 학습 행동과 오답 재확인 날짜 질문",
            )
        else:
            answer_bank = (
                f"{record.locality} 중등 영어학원을 고를 때는 암기량보다 답의 근거를 먼저 확인하세요. {focus}에서 막힌 지점을 찾고 다음 복습 날짜까지 정해야 합니다.",
                f"{record.locality} 중등 영어 상담에서는 어휘·문법·독해 중 어느 단계에서 설명이 끊기는지 나누어야 합니다. 진단 결과가 학교 일정과 주간 행동으로 이어져야 합니다.",
                f"{record.locality}에서 중등 영어학원을 비교한다면 최근 시험지와 학생 답안을 준비하세요. 근거 문장, 틀린 선택지의 이유, 혼자 다시 쓴 결과를 확인하면 됩니다.",
                f"{record.locality} 중등 영어학원 선택의 핵심은 진도 속도가 아니라 문장을 이해하고 답의 근거를 설명하는 과정입니다. 암기한 표현을 새 문장에 적용할 수 있는지 살펴보세요.",
            )
            headings = (
                f"{record.locality} 중등 영어의 출발점을 찾는 진단",
                f"{obj_focus} 답안 기록에서 구분하는 방법",
                "중등 가능 학년과 학교 영어 자료 확인",
                "어휘·문법·독해를 한 주 계획에 배치하는 순서",
                "고교 영어 전환 전에 확인할 독해와 서술형",
                f"{record.locality} 중등 영어 상담 전 체크리스트",
            )
            paragraph_banks = (
                (
                    f"{record.persona}이라면 새 문제집보다 최근에 틀린 세 문장이 더 유용합니다. 정답을 가리고 근거 문장과 다른 선택지가 틀린 이유를 다시 설명하게 해 보세요.",
                    f"진단은 영역 이름을 묻는 데서 끝나지 않습니다. {obj_focus} 학생이 자기 말로 설명하고 다른 문장에 적용할 수 있는지 확인해야 합니다.",
                ),
                (
                    f"영어 오답은 어휘 누락, 문법 적용, 문장 구조, 근거 표시로 나누어 기록할 수 있습니다. {obj_evidence} 첫 답안과 나란히 놓으면 원인이 선명해집니다.",
                    "정답만 다시 적으면 학습 과정이 남지 않습니다. 근거 문장, 선택지 판단, 문법 적용, 다시 쓴 표현을 짧게 남겨 다음 복습에서도 같은 기준을 사용하세요.",
                ),
                (grade_sentence(record), school_sentence(record)),
                (
                    "학교 본문 암기와 누적 어휘·독해 복습을 한날에 몰지 마세요. 어휘 재사용, 문법 적용, 독해 근거, 서술형 표현을 서로 다른 날에 배치하는 편이 좋습니다.",
                    f"{obj_evidence} 주간 계획에 넣을 때는 다시 확인할 날짜를 함께 적으세요. 같은 오류가 반복되면 분량보다 복습 간격을 조정해야 합니다.",
                ),
                (
                    "중학교 영어에서 고교 과정으로 이어질 때는 본문 암기만으로 부족합니다. 낯선 문장의 구조를 나누고 근거를 표시한 뒤 자신의 표현으로 요약할 수 있어야 합니다.",
                    "고교 전환 준비는 어려운 지문을 미리 푸는 일이 아닙니다. 누적 어휘와 문법을 실제 문장에 적용하고 독해 근거를 재현할 수 있는지 확인하는 과정입니다.",
                ),
                (
                    "상담에서는 최근 시험지, 현재 교재, 학교 범위표, 학생이 직접 쓴 답안을 함께 준비하세요. 첫 주에 바꿀 행동과 재확인 날짜가 답변에 포함되어야 합니다.",
                    "센터 정보는 주소·등록 정보·가능 학년·학교 참고 자료처럼 확인 가능한 사실과 대조하세요. 개설 시간과 교습비는 최신 상담 자료로 다시 확인해야 합니다.",
                ),
            )
            checklist = (
                "최근 시험지에서 근거를 놓친 문장과 이유 표시",
                "현재 교재의 진도와 혼자 다시 설명할 수 있는 범위 확인",
                "학교 시험 일정과 어휘·독해 복습 가능 시간 정리",
                "첫 주 학습 행동과 답안 재확인 날짜 질문",
            )
        answer = base.choose(record.key, answer_bank, f"{seed}-answer")
        openers = (
            "먼저 최근 기록을 같은 기준으로 나누어 보세요.",
            "상담 전에는 학생이 혼자 남긴 흔적부터 살펴보는 편이 좋습니다.",
            "학교 시험 전후의 답안을 비교하면 시작점이 더 분명해집니다.",
            "가정 복습 시간을 정하기 전에 현재 자료부터 확인하세요.",
            "새 교재를 고르기보다 지금 막힌 과정을 먼저 설명해 보세요.",
            "학생의 말과 실제 기록을 함께 보면 추측을 줄일 수 있습니다.",
            "한 번의 점수보다 여러 날의 학습 흔적을 대조해 보세요.",
            "진도표와 학생의 설명이 일치하는지 먼저 확인해야 합니다.",
            "상담 질문은 막연한 평가보다 확인 가능한 행동으로 준비하세요.",
            "학교 일정과 집에서 가능한 시간을 함께 놓고 판단하세요.",
            "첫 주에 바꿀 한 가지 행동을 정한 뒤 범위를 넓히는 편이 좋습니다.",
            "정답을 가린 상태에서 학생이 다시 설명할 수 있는지 살펴보세요.",
        )
        closers = (
            "이 결과를 다음 확인 날짜와 함께 남기세요.",
            "답변은 첫 주의 구체적인 행동으로 이어져야 합니다.",
            "같은 기준으로 일주일 뒤 다시 확인할 수 있어야 합니다.",
            "학생이 혼자 재현한 결과까지 비교 기준에 포함하세요.",
            "분량보다 완료 기준이 분명한지를 물어보는 것이 중요합니다.",
            "학교 일정이 바뀌어도 유지할 수 있는 계획인지 확인하세요.",
            "상담 뒤에는 학생과 보호자가 같은 기준을 공유해야 합니다.",
            "기록이 남아야 다음 범위를 늘릴 근거도 생깁니다.",
            "실행하기 어려운 계획은 시간과 분량을 다시 조정하세요.",
            "다음 상담에서는 변화보다 재현 가능한 과정을 확인하세요.",
            "확인 결과가 교재와 복습 간격에 반영되는지도 살펴보세요.",
            "학생의 학교 자료가 바뀌면 계획도 함께 대조해야 합니다.",
        )
        styled_banks: list[tuple[str, ...]] = []
        opener_order = sorted(
            range(len(openers)),
            key=lambda index: base.stable_number(record.key, f"{seed}-opener-order-{index}"),
        )
        closer_order = sorted(
            range(len(closers)),
            key=lambda index: base.stable_number(record.key, f"{seed}-closer-order-{index}"),
        )
        slot = 0
        for paragraphs in paragraph_banks:
            styled: list[str] = []
            for paragraph in paragraphs:
                opener_index = opener_order[slot % len(opener_order)]
                closer_index = closer_order[slot % len(closer_order)]
                opener = openers[opener_index]
                closer = closers[closer_index]
                styled.append(f"{opener} {paragraph} {closer}")
                slot += 1
            styled_banks.append(tuple(styled))
        paragraph_banks = tuple(styled_banks)
        sections = [
            {"heading": heading, "paragraphs": list(paragraphs)}
            for heading, paragraphs in zip(headings[:5], paragraph_banks[:5])
        ]
        sections.append({"heading": headings[5], "paragraphs": list(paragraph_banks[5]), "items": list(checklist)})
        if subject == "math":
            theme = source_theme(
                record.source_html,
                record.locality,
                "중등 수학학원",
                record.math_focus,
            )
            sections[0]["heading"] = f"{record.locality} 중등 수학, {theme}"
            excluded_schools = tuple(
                school for school in record.schools
                if not (school.endswith("중") or school.endswith("중학교"))
            )
            authored = source_paragraphs(
                record.source_html,
                useful_terms=("수학", "개념", "문제", "풀이", "학습", "학생", "오답", "시험", "상담"),
                blocked_terms=("영어", "국어", "초등", "고등", "고교"),
                excluded_school_names=excluded_schools,
                limit=8,
            )
            distribute_source_paragraphs(sections, authored)
        return answer, sections

    def build_faqs(record: base.Record) -> list[tuple[str, str]]:
        grades = "·".join(middle_grades(record))
        schools = middle_schools(record)
        focus = getattr(record, focus_attr)
        evidence = getattr(record, evidence_attr)
        grade_answer = (
            f"{record.locality}에서 확인된 {subject_label} 수업 가능 중등 학년은 {grades}입니다. 학생 진도와 현재 개설 시간은 상담에서 다시 대조해야 합니다."
            if grades else
            f"{record.locality}의 확인된 센터 정보에는 {subject_label} 수업 가능 중등 학년이 표시되지 않았습니다. 현재 개설 범위를 상담에서 먼저 확인하세요."
        )
        school_answer = (
            f"{record.locality}에서 확인된 중학교 정보는 {'·'.join(schools[:4])}{' 등' if len(schools) > 4 else ''}입니다. 최신 시험 범위표와 교재를 준비해 실제 반영 범위를 확인하세요."
            if schools else
            f"{record.locality}의 확인된 중학교 정보가 없습니다. 자녀 학교의 최근 시험 범위표와 교재를 상담 자료로 준비하세요."
        )
        if subject == "english":
            theme = _source_theme(record)
            school_anchor = schools[0] if schools else "재학 중학교"
            required = [
                (
                    f"{record.locality} 중등 영어 수업 가능 학년은 어떻게 확인하나요?",
                    grade_answer,
                ),
                (
                    f"{record.locality} 학교별 영어 자료는 중등 영어 상담에 어떻게 쓰나요?",
                    school_answer,
                ),
            ]
            optional = [
                (
                    f"{record.locality} 중등 영어학원에서는 첫 진단을 어떻게 하나요?",
                    f"최근 시험지와 현재 교재를 함께 보고 어휘·문법·독해 중 설명이 처음 끊긴 지점을 찾습니다. {base.with_josa(evidence, '을', '를')} 남긴 뒤 같은 기준으로 다시 확인할 날짜를 정하세요.",
                ),
                (
                    f"{record.locality}에서 {base.with_josa(focus, '은', '는')} 어떻게 확인하나요?",
                    f"정답률만 보지 말고 첫 답안과 고친 답안을 나란히 놓으세요. 학생이 근거를 말하고 새 문장에 다시 적용할 수 있어야 {focus}의 복습이 끝났다고 판단할 수 있습니다.",
                ),
                (
                    f"{record.locality} 중등 영어 14일 계획은 모든 학생에게 같나요?",
                    "아닙니다. 14일은 진단·재적용·재확인의 순서를 보여 주는 예시입니다. 학교 일정, 현재 학년, 실제 공부 가능 시간에 따라 분량과 날짜를 조정해야 합니다.",
                ),
                (
                    f"{record.locality} 중등 영어학원 상담 전에 무엇을 준비하나요?",
                    f"{school_anchor}의 최신 영어 범위표, 최근 시험지, 현재 교재, 학생이 직접 쓴 답안을 준비하세요. 센터 시간표와 이동 가능한 요일도 함께 적으면 실행 가능한 계획인지 비교하기 쉽습니다.",
                ),
                (
                    f"{record.locality} 중등 영어학원을 비교할 때 교재보다 먼저 볼 것은 무엇인가요?",
                    f"이 페이지의 상담 주제인 {base.with_josa(theme, '이', '가')} 학생의 실제 기록에 어떻게 반영되는지 보세요. 교재 이름보다 첫 주 행동, 완료 기준, 다음 확인 날짜가 구체적인지가 중요합니다.",
                ),
                (
                    f"{record.locality} 중3 영어에서 고교 전환은 무엇부터 준비하나요?",
                    "어려운 지문 선행보다 누적 어휘, 문장 구조, 독해 근거, 서술형 재작성을 먼저 확인하세요. 중학교 오답을 학생이 혼자 설명하고 새 문장에 적용할 수 있는지가 출발점입니다.",
                ),
                (
                    f"{record.locality} 중등 영어 복습이 자주 밀리면 무엇을 바꿔야 하나요?",
                    f"{base.with_josa(evidence, '을', '를')} 한 번에 많이 만들기보다 재확인할 문장 수를 줄이고 날짜를 먼저 고정하세요. 같은 오류가 남으면 새 분량을 늘리기 전에 복습 간격을 조정해야 합니다.",
                ),
            ]
            optional = sorted(
                optional,
                key=lambda pair: base.stable_number(record.key, f"{seed}-faq-{pair[0]}"),
            )[:3]
            faqs = [
                (
                    question,
                    answer
                    if record.locality in answer
                    else f"{record.locality}에서 확인할 때, {answer}",
                )
                for question, answer in required + optional
            ]
            rotation = base.stable_number(record.key, f"{seed}-faq-rotation") % len(faqs)
            return faqs[rotation:] + faqs[:rotation]
        return [
            (f"{record.locality} 중등 {subject_label}학원에서는 무엇부터 진단하나요?", f"{record.locality}에서는 최근 시험지와 교재를 보고 {focus}에서 막힌 지점을 먼저 찾습니다. {base.with_josa(evidence, '을', '를')} 바탕으로 첫 주의 복습 행동과 확인 날짜를 정해야 합니다."),
            (f"{record.locality} 중등 {subject_label} 수업 가능 학년은 어떻게 확인하나요?", grade_answer),
            (f"{record.locality} 학교별 내신 자료는 중등 {subject_label} 상담에 어떻게 쓰나요?", school_answer),
            (f"{record.locality} 중등 {subject_label} 상담 전에 어떤 자료를 준비하면 좋나요?", f"{record.locality}에서는 최근 시험지, 현재 교재, 학교 범위표와 학생이 직접 남긴 {base.with_josa('풀이' if subject == 'math' else '답안', '을', '를')} 준비하세요. 정답보다 막힌 지점과 다시 확인할 날짜가 중요합니다."),
            (f"{record.locality} 중등 {subject_label}학원 선택 시 가장 중요한 질문은 무엇인가요?", f"{record.locality} 상담에서는 진단 결과가 교재 진도와 주간 복습 계획에 어떻게 반영되는지 물어보세요. 학생이 혼자 설명하고 다시 {'풀' if subject == 'math' else '쓸'} 수 있는 완료 기준도 확인해야 합니다."),
        ]

    def review_scenario(record: base.Record) -> str:
        focus = getattr(record, focus_attr)
        evidence = getattr(record, evidence_attr)
        noun = "풀이" if subject == "math" else "답안"
        if subject == "english":
            schools = middle_schools(record)
            school_anchor = schools[0] if schools else "학교"
            return base.choose(record.key, (
                f"상담 전 최근 시험지 세 장에서 {focus}과 관련된 문장을 표시했습니다. 정답을 가리고 아이가 근거를 다시 말하는지 보니 첫 주에 확인할 답안과 날짜를 구체적으로 질문할 수 있었습니다.",
                f"{school_anchor} 범위표와 현재 교재를 함께 준비했습니다. 학교 본문 진도와 누적 어휘·독해 복습을 따로 설명해 달라고 요청하니 집에서 확인할 항목도 나누어 적을 수 있었습니다.",
                f"문제집을 더 늘릴지 묻기보다 {base.with_josa(evidence, '을', '를')} 보여 주었습니다. 같은 오류를 언제 다시 확인하는지 질문하니 수업 계획의 완료 기준을 비교하기 쉬웠습니다.",
                f"{record.persona}의 상황을 한 문장으로 정리해 상담에 가져갔습니다. 점수와 교재명 대신 처음 설명이 끊기는 단계와 학생이 혼자 다시 해 볼 범위를 확인했습니다.",
                f"어휘·문법·독해를 모두 부족하다고 말하지 않고 첫 답안의 오류를 세 종류로 나눴습니다. 우선순위와 14일 뒤의 재확인 방법을 물어보니 실제 가능한 계획인지 판단하기 쉬웠습니다.",
                f"학교 시험 준비와 누적 실력 보완을 같은 시간표로 묶지 않았습니다. {record.locality} 상담에서 각각의 자료, 날짜, 완료 조건을 따로 물어보니 계획이 더 선명해졌습니다.",
                f"아이에게 답을 다시 고치게 한 뒤 왜 그렇게 바꿨는지 설명해 보게 했습니다. {focus}에서 말이 끊긴 지점을 표시해 가져가니 첫 수업의 시작 범위를 구체적으로 확인할 수 있었습니다.",
                f"상담 뒤에는 들은 내용을 가능 학년, 학교 자료, 첫 주 행동, 재확인 날짜로 나누어 적었습니다. 확인된 센터 정보와 새로 답변받은 조건을 구분하니 다른 학원과 비교하기도 수월했습니다.",
            ), f"{seed}-review-expanded")
        return base.choose(record.key, (
            f"상담 전에 최근 시험지와 교재를 정리하고 {focus}에서 막힌 부분을 표시했습니다. 설명을 들은 뒤 첫 주에 다시 확인할 {noun}과 날짜를 나누어 메모하니 비교 기준이 선명해졌습니다.",
            f"문제집을 더 늘릴지 묻기보다 {base.with_josa(evidence, '을', '를')} 보여 주고 원인을 확인했습니다. 학교 과제와 누적 복습 시간을 나누어 적으니 실제로 실행할 계획인지 판단하기 쉬웠습니다.",
            f"{record.persona}의 상황을 상담 질문으로 준비했습니다. 학교 시험 범위와 누적 복습을 따로 묻고 혼자 설명할 수 있는 범위를 확인하니 시작점을 정리하기 수월했습니다.",
            f"정답률만 전달하지 않고 {focus}에서 놓친 기록을 구분했습니다. 각각의 복습 기준과 다음 확인 날짜를 물어보니 수업 계획을 구체적으로 비교할 수 있었습니다.",
        ), f"{seed}-review")

    def related_links(record: base.Record, records: list[base.Record], index: int) -> list[tuple[str, str, str]]:
        previous = records[(index - 1) % len(records)]
        following = records[(index + 1) % len(records)]
        sibling = "중등영어학원" if subject == "math" else "중등수학학원"
        sibling_label = "중등 영어학원" if subject == "math" else "중등 수학학원"
        high = "고등수학학원" if subject == "math" else "고등영어학원"
        high_label = "고교 수학학원" if subject == "math" else "고교 영어학원"
        return [
            ("CATEGORY", f"{label} 전체 지역", base.absolute_url("과목별학원", category)),
            ("LOCAL", f"{record.locality} 전국학원 종합 안내", record.source_url),
            ("GRADE", f"{record.locality} 중학생학원", base.absolute_url("과목별학원", "중학생학원", record.slug)),
            ("SUBJECT", f"{record.locality} {sibling_label}", base.absolute_url("과목별학원", sibling, record.slug)),
            ("COMBINED", f"{record.locality} 영수학원", base.absolute_url("과목별학원", "영수학원", record.slug)),
            ("NEXT", f"{record.locality} {high_label}", base.absolute_url("과목별학원", high, record.slug)),
            ("NEARBY", title(previous), page_url(previous)),
            ("NEARBY", title(following), page_url(following)),
            ("GUIDE", "학습가이드", base.absolute_url("학습가이드")),
            ("CONTACT", "상담 준비하기", base.absolute_url("상담문의")),
        ]

    def hub_faqs() -> list[tuple[str, str]]:
        if subject == "math":
            return [
                ("중등 수학학원은 학교 내신과 누적 개념을 어떻게 함께 준비하나요?", "학교 시험 범위는 일정에 맞춰 준비하되, 이전 단원의 개념과 오답은 별도의 재풀이 날짜를 정해야 합니다. 두 계획의 완료 기준을 구분하는 편이 좋습니다."),
                ("지역별 중등 수학 가능 학년은 어떤 자료를 기준으로 하나요?", "확인된 센터 정보의 수학 가능 학년 중 중1·중2·중3만 안내합니다. 중등 학년 정보가 없으면 현재 개설 범위를 상담에서 확인하도록 안내합니다."),
                ("중등 수학 상담 전에 어떤 자료를 준비하면 좋나요?", "최근 시험지, 현재 교재, 학교 시험 범위, 학생이 직접 쓴 풀이와 실제 공부 가능 시간을 준비하세요. 정답보다 첫 식과 오답 원인을 확인해야 합니다."),
            ]
        return [
            ("중등 영어학원은 학교 내신과 누적 어휘·독해를 어떻게 함께 준비하나요?", "학교 본문과 시험 범위는 일정에 맞춰 준비하되, 누적 어휘와 독해 근거는 별도의 복습 날짜를 정해야 합니다. 두 계획의 완료 기준을 구분하는 편이 좋습니다."),
            ("지역별 중등 영어 가능 학년은 어떤 자료를 기준으로 하나요?", "확인된 센터 정보의 영어 가능 학년 중 중1·중2·중3만 안내합니다. 중등 학년 정보가 없으면 현재 개설 범위를 상담에서 확인하도록 안내합니다."),
            ("중등 영어 상담 전에 어떤 자료를 준비하면 좋나요?", "최근 시험지, 현재 교재, 학교 시험 범위, 학생이 직접 쓴 답안과 실제 공부 가능 시간을 준비하세요. 정답보다 근거 문장과 오답 원인을 확인해야 합니다."),
        ]

    def schema_graph(record: base.Record, meta: str, answer: str, sections: list[dict[str, object]], faqs: list[tuple[str, str]], related: list[tuple[str, str, str]]) -> dict:
        graph = original_schema_graph(record, meta, answer, sections, faqs, related)
        graph = _deep_middle(graph, [record])
        if isinstance(graph, dict):
            for node in graph.get("@graph", []):
                if isinstance(node, dict) and node.get("@type") == "Article":
                    node["datePublished"] = MIDDLE_PUBLISHED_DATE
        return graph  # type: ignore[return-value]

    def render_facts(record: base.Record) -> str:
        return _protect_and_replace(original_render_facts(record), [record])

    def render_local_page(record: base.Record, records: list[base.Record], index: int) -> str:
        return _protect_and_replace(original_render_local_page(record, records, index), [record])

    def render_hub(records: list[base.Record]) -> str:
        return _protect_and_replace(original_render_hub(records), records)

    module.title = title
    module.page_url = page_url
    module.high_grades = middle_grades
    module.high_schools = middle_schools
    module.build_persona = build_persona
    module.make_records = make_records
    module.meta_description = meta_description
    module.grade_sentence = grade_sentence
    module.school_sentence = school_sentence
    module.content_sections = content_sections
    module.build_faqs = build_faqs
    module.review_scenario = review_scenario
    module.related_links = related_links
    module.hub_faqs = hub_faqs
    module.schema_graph = schema_graph
    module.render_facts = render_facts
    module.render_local_page = render_local_page
    module.render_hub = render_hub
    return module


def run(subject: str) -> None:
    module = configure(subject)
    parser = argparse.ArgumentParser(description=f"학습코칭.kr {module.CATEGORY_LABEL} 371개 지역 페이지 생성")
    parser.add_argument("--workbook", type=Path, default=module.DEFAULT_WORKBOOK)
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()
    records = module.make_records(args.workbook)
    module.preflight(records)
    if not args.check_only:
        module.write_site(records)
    print(json.dumps({
        "category": module.CATEGORY,
        "records": len(records),
        "unique_centers": len({record.center_name for record in records}),
        "missing_middle_grades": sum(not module.high_grades(record) for record in records),
        "missing_tuition_links": sum(not record.tuition_url for record in records),
        "written": not args.check_only,
        "target": str(module.TARGET_ROOT),
    }, ensure_ascii=False))
