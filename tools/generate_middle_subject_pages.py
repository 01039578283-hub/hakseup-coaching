from __future__ import annotations

import argparse
import json
import re
from dataclasses import replace
from pathlib import Path
from types import ModuleType

import generate_yeongsu_subject_pages as base


ROOT = Path(__file__).resolve().parents[1]
DESKTOP = Path.home() / "Desktop"
MIDDLE_GRADES = tuple(base.GRADE_ORDER[6:9])


def _subject_values(subject: str) -> dict[str, object]:
    if subject == "math":
        return {
            "module": "generate_high_math_subject_pages",
            "workbook": DESKTOP / "중등 수학학원.xlsx",
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
            "workbook": DESKTOP / "중등 영어학원.xlsx",
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
    text = text.replace("HIGH SCHOOL", "MIDDLE SCHOOL").replace("고등", "중등")
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
        return tuple(
            school for school in record.schools
            if school.endswith("중") or school.endswith("중학교")
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
            values = (
                f"{record.locality} 중등 영어학원 상담 전 어휘 누적, 문법 적용, 독해 근거, 서술형 답안과 가능 학년·센터 확인 기준을 정리했습니다.",
                f"{record.locality} 중등 영어학원 선택에 필요한 현재 진단, 학교 시험 자료, 답안 기록, 주간 복습과 상담 전 센터 확인 질문을 안내합니다.",
                f"{record.locality} 중등 영어학원을 알아보는 학부모를 위해 가능 학년, 어휘·문법·독해 진단, 학교 자료와 첫 주 계획을 담았습니다.",
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

    def content_sections(record: base.Record) -> tuple[str, list[dict[str, object]]]:
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
        return _deep_middle(graph, [record])  # type: ignore[return-value]

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
