from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
from collections import defaultdict
from dataclasses import replace
from pathlib import Path
from urllib.parse import quote

import generate_yeongsu_subject_pages as base
from source_copy_utils import distribute_source_paragraphs, source_paragraphs, source_theme


ROOT = Path(__file__).resolve().parents[1]
DESKTOP = Path.home() / "Desktop"
DEFAULT_WORKBOOK = DESKTOP / "구글시트로 뽑은거" / "고등 영어학원.xlsx"
CATEGORY = "고등영어학원"
CATEGORY_LABEL = "고등 영어학원"
TARGET_ROOT = ROOT / "과목별학원" / CATEGORY
HIGH_GRADES = tuple(base.GRADE_ORDER[-3:])
PUBLISHED_DATE = "2026-08-13"


def title(record: base.Record) -> str:
    return f"{record.locality} {CATEGORY_LABEL}"


def page_url(record: base.Record) -> str:
    return base.absolute_url("과목별학원", CATEGORY, record.slug)


def high_grades(record: base.Record) -> tuple[str, ...]:
    return tuple(grade for grade in record.english_grades if grade in HIGH_GRADES)


def high_schools(record: base.Record) -> tuple[str, ...]:
    return tuple(
        school for school in record.schools
        if school.endswith("고") or school.endswith("고등학교")
    )


def obj(value: str) -> str:
    return base.with_josa(value, "을", "를")


def topic(value: str) -> str:
    return base.with_josa(value, "은", "는")


def subj(value: str) -> str:
    return base.with_josa(value, "이", "가")


def conj(value: str) -> str:
    return base.with_josa(value, "과", "와")


def build_persona(record: base.Record, grade: str) -> str:
    learner = f"{base.GRADE_EXPANDED[grade]} 학생" if grade else "고등 영어 수업 가능 학년을 먼저 확인해야 하는 학생"
    frames = (
        f"문법 규칙은 기억하지만 실제 문장에 적용할 때 선택 근거를 설명하기 어려운 {learner}",
        f"내신 지문은 익숙해도 낯선 독해 문제에서 근거 문장을 찾지 못하는 {learner}",
        f"정답은 고르지만 다른 선택지가 틀린 이유를 설명하기 어려운 {learner}",
        f"어휘·문법·독해를 따로 공부해 한 지문 안에서 연결하지 못하는 {learner}",
        f"단어 뜻은 외워도 예문과 서술형 답안에서 다시 사용하기 어려운 {learner}",
        f"학교 진도는 따라가지만 누적 어휘와 독해 복습 날짜를 정하지 못한 {learner}",
        f"시험 직전 문제 수만 늘리고 오답 선택의 이유를 기록하지 않는 {learner}",
        f"수업에서는 이해하지만 이틀 뒤 혼자 같은 지문을 해석하기 어려운 {learner}",
        f"쉬운 문제의 실수가 반복되어 시간 배분과 근거 표시를 점검해야 하는 {learner}",
        f"고난도 문제보다 현재 지문에서 놓친 문장 구조를 먼저 찾아야 하는 {learner}",
        f"서술형 답안에서 근거 문장과 자신의 표현을 연결하지 못하는 {learner}",
        f"학습 시간은 충분하지만 교재별 완료 기준과 복습 간격이 분명하지 않은 {learner}",
    )
    return base.choose(record.key, frames, "high-english-persona")


def make_records(workbook: Path) -> list[base.Record]:
    # Reuse the already audited 371-row locality, center and media mapping.
    records = base.make_records(workbook)
    prepared: list[base.Record] = []
    for record in records:
        grades = high_grades(record)
        selected = grades[base.stable_number(record.key, "high-english-grade") % len(grades)] if grades else ""
        prepared.append(
            replace(
                record,
                common_grades=grades,
                selected_grade=selected,
                persona=build_persona(record, selected),
            )
        )
    return prepared


def meta_description(record: base.Record) -> str:
    values = (
        f"{record.locality} 고등 영어학원 상담 전 어휘·문법·독해 근거, 내신·모의고사, 서술형 답안, 가능 학년과 복습 기준을 정리했습니다.",
        f"{record.locality} 고등 영어학원 선택에 필요한 현재 진단, 학교 시험 자료, 답안 근거, 주간 복습과 상담 전 확인 항목을 안내합니다.",
        f"{record.locality} 고등 영어학원을 알아보는 학부모를 위해 가능 학년, 어휘·문법·독해 진단, 학교 자료와 첫 주 계획을 담았습니다.",
    )
    value = base.choose(record.key, values, "high-english-meta")
    if not 65 <= len(value) <= 105:
        raise ValueError(f"{record.locality} 메타 설명 길이 오류: {len(value)}")
    return value


def grade_sentence(record: base.Record) -> str:
    grades = high_grades(record)
    if grades:
        return (
            f"확인된 센터 정보상 영어 수업 가능 고등 학년은 {'·'.join(grades)}입니다. "
            "현재 개설 시간과 학생의 학교 진도는 상담에서 다시 확인해야 합니다."
        )
    return (
        "확인된 센터 정보에 영어 수업 가능 고등 학년이 따로 표시되지 않았습니다. "
        "학년을 추정하지 말고 현재 개설 범위부터 상담에서 확인하세요."
    )


def school_sentence(record: base.Record) -> str:
    schools = high_schools(record)
    if schools:
        shown = "·".join(schools[:5])
        return (
            f"확인된 고등학교 참고 정보는 {shown}{' 등' if len(schools) > 5 else ''}입니다. "
            "학교별 시험 범위와 교재는 최신 자료로 다시 대조해야 합니다."
        )
    return (
        "확인된 고등학교 정보가 없습니다. "
        "최근 시험 범위표와 교재를 준비해 내신 자료의 반영 방법을 문의하세요."
    )


def content_sections(record: base.Record) -> tuple[str, list[dict[str, object]]]:
    key = record.key
    answer = base.choose(
        key,
        (
            f"{record.locality} 고등 영어학원을 고를 때는 문제 수보다 답의 근거를 확인하세요. {record.english_focus}에서 막힌 지점을 찾고 다음 복습 날짜까지 정해야 합니다.",
            f"{record.locality} 고등 영어 상담의 핵심은 현재 점수보다 어휘·문법·독해 중 어디에서 근거를 놓치는지 구분하는 데 있습니다. 진단 결과가 학교 일정과 주간 행동으로 이어져야 합니다.",
            f"{record.locality}에서 고등 영어학원을 비교한다면 최근 시험지와 교재를 준비하세요. 정답의 근거, 틀린 선택지의 이유, 혼자 다시 해석한 결과를 확인하면 됩니다.",
            f"{record.locality} 고등 영어학원 선택의 직접적인 기준은 진도 속도가 아니라 답안 설명의 구체성입니다. 학생이 근거 문장을 찾고 자신의 표현으로 바꿀 수 있는지 살펴보세요.",
            f"{record.locality} 고등 영어학원을 알아볼 때는 내신 지문과 모의고사 문제를 한꺼번에 늘리기보다 현재 영역의 빈틈을 먼저 찾아야 합니다. 진단 결과를 교재와 복습 일정에 연결하세요.",
            f"{record.locality} 고등 영어 상담에서는 선행 범위보다 최근 답안이 우선입니다. {obj(record.english_evidence)} 바탕으로 첫 주에 바꿀 행동을 정하는지 확인하세요.",
        ),
        "high-english-answer",
    )

    first_heading = base.choose(
        key,
        (
            f"{record.locality} 고등 영어의 시작점을 찾는 진단",
            "최근 답안에서 어휘·문법·독해의 막힌 단계를 찾는 방법",
            f"{record.locality} 학생의 독해 근거와 문장 적용 점검",
            "점수보다 먼저 확인할 고등 영어 답안 기록",
            f"{obj(record.english_focus)} 진단의 출발점으로 삼기",
            "고등 영어 첫 상담에서 답해야 할 질문",
        ),
        "high-english-h2-1",
    )
    first_p1 = base.choose(
        key,
        (
            f"{topic(record.persona)} 최근 답안에서 처음 근거를 놓친 문장을 표시해 보세요. 어휘 부족인지 문장 구조인지 선택지 판단인지 구분하기 쉬워집니다.",
            f"{record.persona}이라면 새 문제집보다 최근에 틀린 세 문제가 더 유용합니다. 정답을 가리고 근거 문장과 다른 선택지가 틀린 이유를 다시 설명해 보세요.",
            f"{record.locality} 상담에서는 {record.persona}의 실제 답안을 먼저 살펴보는 편이 좋습니다. 맞힌 문제도 근거를 설명하지 못하면 낯선 지문에서 같은 빈틈이 드러날 수 있습니다.",
            f"진단은 영역 이름을 묻는 데서 끝나지 않습니다. {topic(record.persona)} 문장을 읽고 근거를 찾은 뒤 자신의 말로 요약할 수 있는지 확인해야 합니다.",
        ),
        "high-english-first-p1",
    )
    first_p2 = base.choose(
        key,
        (
            f"특히 {topic(record.english_focus)} 정답률만으로 판단하기 어렵습니다. {obj(record.english_evidence)} 남기면 첫 수업 범위와 재확인 시점을 구체적으로 정할 수 있습니다.",
            f"첫 진단에서는 {obj(record.english_evidence)} 최근 시험지와 나란히 놓아 보세요. 같은 오류가 두 번 이상 보이면 그 지점을 첫 주 복습 항목으로 삼는 편이 현실적입니다.",
            f"학생이 {obj(record.english_focus)} 자기 말로 설명하고 유사 문장에 다시 적용할 수 있어야 합니다. 설명이 끊기면 해당 영역부터 복습 범위를 좁히세요.",
            f"진단 결과는 막연한 평가보다 행동으로 남아야 합니다. {obj(record.english_evidence)} 기준으로 다음 수업 전까지 무엇을 다시 읽고 쓸지 정해 보세요.",
        ),
        "high-english-first-p2",
    )

    second_heading = base.choose(
        key,
        (
            f"{obj(record.english_focus)} 어휘·문법·독해로 나누어 보기",
            "고등 영어 오답을 어휘·구조·근거로 분류하기",
            "내신 지문과 모의고사 독해의 근거 비교",
            "정답 뒤에 남겨야 할 문장 근거와 설명",
            "낯선 지문에서도 답의 근거를 찾는 연습",
            "해석 속도보다 재현 가능한 독해 과정을 만드는 방법",
        ),
        "high-english-h2-2",
    )
    second_p1 = base.choose(
        key,
        (
            f"영어 오답은 어휘 누락, 문법 적용, 문장 구조, 근거 표시, 시간 배분으로 나누어 기록할 수 있습니다. {record.english_focus}에 해당하는 오류는 첫 답안과 수정한 답안을 비교해야 변화가 보입니다.",
            "내신은 학교 범위 안의 지문과 서술형 표현을, 모의고사는 낯선 글의 구조와 시간 배분을 함께 요구합니다. 두 시험의 점수보다 근거를 찾는 과정이 같은지 대조하세요.",
            "정답만 다시 적으면 오답 원인이 남지 않습니다. 근거 문장, 선택지 판단, 문법 적용, 다시 쓴 표현을 짧게 적어야 다음 복습에서도 같은 기준을 쓸 수 있습니다.",
            "지문이 길수록 모든 문장을 번역하기보다 중심 문장과 선택지에 필요한 근거를 표시하는 편이 유용합니다. 이 기록이 있어야 어휘와 구조 중 어디에서 멈췄는지 구분할 수 있습니다.",
        ),
        "high-english-second-p1",
    )
    second_p2 = base.choose(
        key,
        (
            f"상담에서는 {obj(record.english_evidence)} 보여 주고 같은 영역을 언제 다시 확인할지 물어보세요. 날짜와 완료 기준이 분명해야 오답 기록이 실제 복습으로 이어집니다.",
            f"{obj(record.english_evidence)} 주간 계획에 넣을 때는 문제 수보다 확인 목적을 적어 두세요. 어휘 재사용, 문법 적용, 독해 근거, 서술형 표현 중 하나를 고르면 재확인도 선명해집니다.",
            "틀린 문제를 모두 다시 보는 방식보다 대표 오류를 고르고 유사 문장에 적용하는 방식이 효율적입니다. 학생이 혼자 설명한 기록까지 남겨야 다음 범위를 늘릴 근거가 생깁니다.",
            "오답 재확인은 정답을 기억하는지 보는 시간이 아닙니다. 지문을 보지 않고 핵심 내용을 요약하거나 다른 문장에서 같은 문법을 적용할 수 있는지 살펴보아야 합니다.",
        ),
        "high-english-second-p2",
    )

    third_heading = base.choose(
        key,
        (
            f"{record.locality} 고등 가능 학년과 학교 자료 확인",
            "고등 학년 정보와 내신 범위를 함께 보는 방법",
            "학교 시험 범위·교재를 상담 자료로 준비하기",
            f"{record.locality} 지역 정보와 실제 수업 범위 대조",
            "고1·고2·고3 가능 여부를 사실대로 확인하기",
            "학교별 영어 자료를 현재 학습 영역과 연결하는 기준",
        ),
        "high-english-h2-3",
    )
    third_p1 = grade_sentence(record)
    third_p2 = school_sentence(record)

    fourth_heading = base.choose(
        key,
        (
            "고등 영어 복습을 한 주 일정에 배치하는 순서",
            "학교 진도와 누적 어휘·독해 복습의 시간 배분",
            "어휘·문법·독해 기록을 현실적인 계획으로 연결하기",
            "시험 전후에도 유지할 수 있는 영어 학습 루틴",
            f"{record.locality} 학생의 주간 영어 계획 점검",
            "완료 분량보다 다시 시작할 시간을 정하는 방법",
        ),
        "high-english-h2-4",
    )
    fourth_p1 = base.choose(
        key,
        (
            "주간 계획에는 학교 진도, 어휘 누적, 독해·문법 오답을 구분해 적어야 합니다. 세 항목을 같은 날 몰아넣지 말고 실제 공부할 수 있는 시간에 맞춰 우선순위를 정하세요.",
            "계획이 밀렸다면 의지 부족으로 단정하기보다 시작 시간과 지문 난도를 확인해야 합니다. 끝내지 못한 항목은 분량을 줄이고 다음 시작 시점을 구체적으로 남기세요.",
            "시험 기간에도 누적 어휘와 독해 복습을 완전히 멈추지 않도록 짧은 재확인 시간을 남겨 두세요. 학교 범위와 연결되는 문법·어휘를 고르면 내신 준비와 누적 복습을 함께 이어갈 수 있습니다.",
            "영어 공부 시간은 길이보다 구성으로 점검해야 합니다. 어휘, 문법 적용, 독해 근거, 서술형 표현을 서로 다른 칸에 배치하면 어느 단계가 자주 빠지는지 확인할 수 있습니다.",
        ),
        "high-english-fourth-p1",
    )
    fourth_p2 = base.choose(
        key,
        (
            f"{record.locality} 상담에서는 평일 등원 시간과 가정 복습 시간을 함께 알려 주세요. {obj(record.english_focus)} 확인할 날짜까지 정하면 첫 주 계획의 실행 가능성을 비교하기 쉽습니다.",
            f"{obj(record.english_evidence)} 일주일 뒤 다시 확인할 수 있도록 날짜를 남겨야 합니다. 완료 여부뿐 아니라 혼자 설명했는지, 힌트가 필요했는지도 함께 기록하세요.",
            f"첫 주에는 {conj(record.english_focus)} 학교 과제 중 우선할 항목을 하나씩 고르는 편이 안전합니다. 계획을 지킨 뒤에만 지문 수나 선행 범위를 늘려야 합니다.",
            f"학원 계획과 가정 계획이 따로 움직이면 같은 과제를 반복하거나 복습을 놓칠 수 있습니다. {obj(record.english_evidence)} 공통 확인 자료로 사용해 다음 행동을 맞추세요.",
        ),
        "high-english-fourth-p2",
    )

    fifth_heading = base.choose(
        key,
        (
            "내신과 모의고사 준비를 같은 기준으로 묶지 않기",
            "학교 시험 대비와 수능 영어 독해의 우선순위",
            "현재 지문과 누적 어휘를 함께 확인하는 방법",
            "서술형 표현과 독해 시간 배분을 시험 전후로 비교하기",
            "고등 영어 점수보다 먼저 살펴볼 학습 기록",
            "시험이 끝난 뒤 다음 범위로 넘어가기 전 점검",
        ),
        "high-english-h2-5",
    )
    fifth_p1 = base.choose(
        key,
        (
            "내신은 학교별 지문과 서술형 기준이 중요하고, 모의고사는 낯선 글의 구조와 시간 배분이 중요합니다. 두 준비를 한 계획에 넣더라도 문제 선택과 오답 분류 기준은 따로 두어야 합니다.",
            "시험 전에는 범위 안의 지문·문법·서술형 표현을 확인하고, 시험 뒤에는 어휘 부족과 근거 판단, 시간 부족을 나누어 보세요. 이 순서가 있어야 다음 계획이 문제 수 증가로 끝나지 않습니다.",
            "현재 범위의 정답률이 높아도 핵심 문장을 설명하지 못하면 새로운 지문에서 다시 막힐 수 있습니다. 새 범위를 시작하기 전에 연결되는 어휘와 문장 구조를 짧게 재확인하세요.",
            "고난도 문제는 많이 푸는 것보다 답의 근거를 설명하는 연습이 먼저입니다. 어떤 문장을 보고 선택지를 판단했는지 말로 정리하면 우연히 맞힌 문제를 구분할 수 있습니다.",
        ),
        "high-english-fifth-p1",
    )
    fifth_p2 = base.choose(
        key,
        (
            f"{record.persona}이라면 시험 전 문제집을 추가하기보다 최근 답안의 공통 오류를 먼저 고르세요. 그 오류가 줄어든 뒤에 난도와 범위를 조정하는 편이 안정적입니다.",
            f"{record.persona}의 경우 학교 시험지와 평소 독해 기록을 나란히 보면 실전에서만 생기는 문제를 찾기 쉽습니다. 시간 배분과 근거 표시를 별도 항목으로 남겨 보세요.",
            f"{topic(record.english_focus)} 한 번의 점수보다 두 차례의 재확인 결과로 판단하는 편이 좋습니다. 같은 기준을 다른 지문에 적용할 수 있을 때 다음 범위로 넘어가세요.",
            f"상담에서는 내신 범위와 모의고사 준비를 각각 언제 시작하는지 물어보세요. {obj(record.english_evidence)} 어떤 평가 기준으로 사용하는지도 함께 확인해야 합니다.",
        ),
        "high-english-fifth-p2",
    )

    sixth_heading = base.choose(
        key,
        (
            f"{record.locality} 고등 영어학원 상담 전 체크리스트",
            "등록을 결정하기 전에 확인할 고등 영어 질문",
            "첫 상담에서 놓치지 말아야 할 네 가지 기준",
            "학생의 답안 기록으로 수업 계획을 검증하는 방법",
            "고등 영어 첫 주 계획을 비교하는 상담 항목",
            "학부모가 상담 메모에 남길 확인 사항",
        ),
        "high-english-h2-6",
    )
    checklist_banks = (
        (
            "최근 시험지에서 처음 근거를 놓친 문제와 그 이유를 설명하는지",
            f"{obj(record.english_focus)} 어떤 기록으로 재확인하는지",
            "학교 진도·어휘·독해·서술형 시간을 따로 배치하는지",
            "첫 주 완료 기준과 다음 복습 날짜를 정하는지",
        ),
        (
            "고등 영어 가능 학년과 현재 개설 시간을 다시 확인했는지",
            "내신 지문과 모의고사 독해의 오답 기준을 구분하는지",
            f"{obj(record.english_evidence)} 학생이 혼자 설명하는지",
            "계획이 밀릴 때 분량과 우선순위를 조정하는지",
        ),
        (
            "최근 교재와 학교 시험 범위를 진단에 반영하는지",
            "어휘 누락·문법 적용·독해 근거를 따로 표시하는지",
            "서술형 답안에서 근거 문장과 표현까지 확인하는지",
            "상담 결과를 구체적인 일주일 행동으로 남기는지",
        ),
    )
    checklist = checklist_banks[base.stable_number(key, "high-english-checklist") % len(checklist_banks)]
    sixth_p = base.choose(
        key,
        (
            f"{record.locality} 고등 영어학원을 비교할 때 아래 항목을 같은 순서로 물어보면 설명의 차이를 확인하기 쉽습니다.",
            "상담 질문을 많이 준비하기보다 진단 근거와 다음 행동을 확인하는 네 가지 항목에 집중하세요.",
            "등록 전에는 홍보 문구보다 학생의 최근 답안이 실제 계획에 어떻게 반영되는지 아래 기준으로 살펴보세요.",
        ),
        "high-english-sixth-p",
    )

    sections = [
        {"heading": first_heading, "paragraphs": [first_p1, first_p2]},
        {"heading": second_heading, "paragraphs": [second_p1, second_p2]},
        {"heading": third_heading, "paragraphs": [third_p1, third_p2]},
        {"heading": fourth_heading, "paragraphs": [fourth_p1, fourth_p2]},
        {"heading": fifth_heading, "paragraphs": [fifth_p1, fifth_p2]},
        {"heading": sixth_heading, "paragraphs": [sixth_p], "items": list(checklist)},
    ]
    theme = source_theme(record.source_html, record.locality, CATEGORY_LABEL, record.english_focus)
    sections[0]["heading"] = f"{record.locality} 고등 영어, {theme}"
    excluded_schools = tuple(
        school for school in record.schools
        if not (school.endswith("고") or school.endswith("고등학교"))
    )
    authored = source_paragraphs(
        record.source_html,
        useful_terms=("영어", "어휘", "문법", "문장", "독해", "학습", "학생", "오답", "시험", "상담"),
        blocked_terms=("수학", "국어", "초등", "중등", "중학교"),
        excluded_school_names=excluded_schools,
        limit=8,
    )
    distribute_source_paragraphs(sections, authored)
    return answer, sections
def build_faqs(record: base.Record) -> list[tuple[str, str]]:
    grades = "·".join(high_grades(record))
    grade_answer = (
        f"{record.locality}에서 확인된 영어 수업 가능 고등 학년은 {grades}입니다. 학생 진도와 현재 개설 시간은 상담에서 다시 대조해야 합니다."
        if grades else
        f"{record.locality}의 확인된 센터 정보에는 영어 수업 가능 고등 학년이 표시되지 않았습니다. 현재 개설 범위를 상담에서 먼저 확인하세요."
    )
    schools = high_schools(record)
    school_answer = (
        f"{record.locality}에서 확인된 고등학교 정보는 {'·'.join(schools[:4])}{' 등' if len(schools) > 4 else ''}입니다. 최신 시험 범위표와 교재를 함께 준비해 실제 반영 범위를 확인하세요."
        if schools else
        f"{record.locality}의 확인된 고등학교 정보가 없습니다. 자녀 학교의 최근 시험 범위표와 교재를 상담 자료로 준비하세요."
    )
    return [
        (
            base.choose(record.key, (
                f"{record.locality} 고등 영어학원에서는 무엇부터 진단하나요?",
                f"{record.locality} 고등 영어 첫 상담에 어떤 답안을 가져가야 하나요?",
                f"{record.locality} 고등 영어의 시작 영역은 어떤 기록으로 정하나요?",
            ), "high-english-faq-q1"),
            f"{record.locality}에서는 최근 시험지와 교재에서 처음 근거를 놓친 문제를 찾고 어휘·문법·독해 중 원인을 나눕니다. 특히 {obj(record.english_evidence)} 확인해 첫 주 시작점과 복습 날짜를 정하는 편이 좋습니다.",
        ),
        (
            base.choose(record.key, (
                f"{record.locality} 고등 영어학원 가능 학년은 어떻게 확인하나요?",
                f"{record.locality} 고1·고2·고3 영어 수업 가능 여부는 어디에서 확인하나요?",
                f"{record.locality}에서 {record.center_name}의 고등 영어 가능 학년은 무엇인가요?",
            ), "high-english-faq-q2"),
            grade_answer,
        ),
        (
            base.choose(record.key, (
                f"{record.locality} 학교별 내신 범위는 영어 계획에 어떻게 반영하나요?",
                f"{record.locality} 고등학교 영어 자료는 상담에서 어떻게 활용하나요?",
                f"{record.locality} 학교 시험지와 교재를 준비해야 하는 이유는 무엇인가요?",
            ), "high-english-faq-q3"),
            school_answer,
        ),
        (
            base.choose(record.key, (
                f"{record.locality} 내신 영어와 모의고사 독해는 같은 방식으로 준비하나요?",
                f"{record.locality} 고등 영어 오답은 언제 다시 확인해야 하나요?",
                f"{record.locality}에서 {topic(record.english_focus)} 어떤 기준으로 재확인하나요?",
            ), "high-english-faq-q4"),
            f"{record.locality} 고등 영어에서는 내신의 학교 범위·서술형 기준과 모의고사의 낯선 지문·시간 배분을 따로 확인합니다. {obj(record.english_evidence)} 남기고 같은 기준을 다른 문장에 적용한 결과로 다음 범위를 정하세요.",
        ),
        (
            base.choose(record.key, (
                f"{record.locality} 고등 영어학원 등록 전에 꼭 물어볼 질문은 무엇인가요?",
                f"{record.locality} 학부모가 고등 영어 상담 메모에 남기면 좋은 항목은 무엇인가요?",
                f"{record.locality} 첫 주 영어 계획이 현실적인지 어떻게 확인하나요?",
            ), "high-english-faq-q5"),
            f"{record.locality} 상담 메모에는 진단 근거, 학교 진도, 주간 공부 가능 시간, 첫 주 완료 기준, 다음 복습 날짜를 적어 두세요. 학년과 시간표, 교습비는 현재 상담 내용과 연결 자료로 다시 확인해야 합니다.",
        ),
    ]


def review_scenario(record: base.Record) -> str:
    return base.choose(
        record.key,
        (
            f"상담 전에 최근 시험지와 교재를 정리하고 {record.english_focus}에서 막힌 문제를 표시했습니다. 설명을 들은 뒤 첫 주에 다시 확인할 지문과 날짜를 구분해 메모하니 비교 기준이 선명해졌습니다.",
            f"문제집을 더 늘릴지 묻기보다 {obj(record.english_evidence)} 보여 주고 오답 원인을 확인했습니다. 학교 과제와 누적 복습 시간을 나누어 적으니 실제로 실행할 계획인지 판단하기 쉬웠습니다.",
            f"{record.persona}의 상황을 상담 질문으로 준비했습니다. 내신 범위와 모의고사 준비를 따로 묻고 학생이 혼자 설명할 수 있는 범위를 확인하니 시작점을 정리하기 수월했습니다.",
            "정답률만 전달하지 않고 독해 근거를 놓친 문제와 문법 적용이 흔들린 문장을 구분했습니다. 각각의 복습 기준과 다음 확인 날짜를 물어보니 수업 계획을 구체적으로 비교할 수 있었습니다.",
        ),
        "high-english-review",
    )
def related_links(record: base.Record, records: list[base.Record], index: int) -> list[tuple[str, str, str]]:
    previous = records[(index - 1) % len(records)]
    following = records[(index + 1) % len(records)]
    return [
        ("CATEGORY", "고등 영어학원 전체 지역", base.absolute_url("과목별학원", CATEGORY)),
        ("LOCAL", f"{record.locality} 전국학원 종합 안내", record.source_url),
        ("GRADE", f"{record.locality} 고등학생학원", base.absolute_url("과목별학원", "고등학생학원", record.slug)),
        ("SUBJECT", f"{record.locality} 고등 수학학원", base.absolute_url("과목별학원", "고등수학학원", record.slug)),
        ("COMBINED", f"{record.locality} 영수학원", base.absolute_url("과목별학원", "영수학원", record.slug)),
        ("GRADE", f"{record.locality} 중학생학원", base.absolute_url("과목별학원", "중학생학원", record.slug)),
        ("NEARBY", title(previous), page_url(previous)),
        ("NEARBY", title(following), page_url(following)),
        ("GUIDE", "학습가이드", base.absolute_url("학습가이드")),
        ("CONTACT", "상담 준비하기", base.absolute_url("상담문의")),
    ]


def schema_graph(
    record: base.Record,
    meta: str,
    answer: str,
    sections: list[dict[str, object]],
    faqs: list[tuple[str, str]],
    related: list[tuple[str, str, str]],
) -> dict:
    url = page_url(record)
    hub = base.absolute_url("과목별학원", CATEGORY)
    parent = base.absolute_url("과목별학원")
    image_id = url + "#primaryimage"
    service_id = url + "#service"
    article_id = url + "#article"
    body_url = base.BASE_URL + f"/assets/centers/common/{record.body_file}"
    map_url = base.BASE_URL + f"/assets/maps/{record.map_file}"
    schools = high_schools(record)
    about = [
        {"@type": "Thing", "name": title(record)},
        {"@type": "Thing", "name": "고등 영어 학습 진단"},
        {"@type": "Thing", "name": "내신·모의고사 영어 학습"},
        {"@type": "Place", "name": record.locality},
        {"@type": "Place", "name": record.service_city},
        {"@type": "Place", "name": record.service_region},
    ]
    mentions = [
        {"@type": "Thing", "name": record.english_focus},
        {"@type": "Thing", "name": "문장 구조와 독해 근거"},
        {"@type": "Thing", "name": "서술형 답안"},
        {"@type": "Thing", "name": "오답 재해석·재작성"},
        *({"@type": "EducationalOrganization", "name": school} for school in schools),
    ]
    offer = {
        "@type": "Offer",
        "name": f"{record.locality} 고등 영어 학습 상담",
        "url": url,
        "itemOffered": {
            "@type": "Service",
            "name": f"{record.locality} 고등 영어 가능 범위 확인",
            "serviceType": "고등 영어 학습 상담",
        },
    }
    org: dict[str, object] = {
        "@type": ["EducationalOrganization", "LocalBusiness"],
        "@id": record.organization_id,
        "name": record.center_name,
        "legalName": record.legal_name,
        "url": record.source_url,
        "address": {
            "@type": "PostalAddress",
            "streetAddress": record.address,
            "addressRegion": record.physical_region,
            "addressLocality": record.physical_city,
            "addressCountry": "KR",
        },
        "areaServed": [
            {"@type": "Place", "name": record.locality},
            {"@type": "AdministrativeArea", "name": record.service_city},
        ],
        "knowsAbout": ["고등 영어", "영어 학습 진단", "내신", "모의고사", "오답 재학습"],
        "makesOffer": [offer],
        "identifier": {
            "@type": "PropertyValue",
            "propertyID": "교육지원청 등록 정보",
            "value": record.registration,
        },
        "image": record.representative,
    }
    if record.tuition_url:
        org["subjectOf"] = {
            "@type": "CreativeWork",
            "name": f"{record.center_name} 교습비 안내",
            "url": record.tuition_url,
        }
    part_names = [
        "핵심 답변", *[str(section["heading"]) for section in sections],
        "지역·학년·추천 학생", "검증된 센터 정보", "FAQ", "학부모 상담 메모", "관련 페이지",
    ]
    parts = [
        {"@type": "WebPageElement", "name": name, "isPartOf": {"@id": url + "#webpage"}}
        for name in part_names
    ]
    graph: list[dict[str, object]] = [
        {
            "@type": "WebSite", "@id": base.BASE_URL + "/#website", "url": base.BASE_URL + "/",
            "name": base.SITE_NAME, "inLanguage": "ko-KR", "publisher": {"@id": base.BASE_URL + "/#organization"},
        },
        org,
        {
            "@type": "WebPage", "@id": url + "#webpage", "url": url, "name": title(record),
            "description": meta, "inLanguage": "ko-KR", "isPartOf": {"@id": base.BASE_URL + "/#website"},
            "publisher": {"@id": record.organization_id}, "primaryImageOfPage": {"@id": image_id},
            "breadcrumb": {"@id": url + "#breadcrumb"}, "mainEntity": {"@id": service_id},
            "about": about, "mentions": mentions, "hasPart": parts, "dateModified": base.TODAY,
        },
        {
            "@type": "ImageObject", "@id": image_id, "url": record.representative,
            "contentUrl": record.representative, "caption": f"{title(record)} {base.SITE_NAME} 대표 이미지",
            "inLanguage": "ko-KR",
        },
        {
            "@type": "BreadcrumbList", "@id": url + "#breadcrumb", "itemListElement": [
                {"@type": "ListItem", "position": 1, "name": "홈", "item": base.BASE_URL + "/"},
                {"@type": "ListItem", "position": 2, "name": "과목별학원", "item": parent},
                {"@type": "ListItem", "position": 3, "name": CATEGORY_LABEL, "item": hub},
                {"@type": "ListItem", "position": 4, "name": title(record), "item": url},
            ],
        },
        {
            "@type": "Article", "@id": article_id, "headline": title(record), "description": meta,
            "abstract": answer, "inLanguage": "ko-KR", "mainEntityOfPage": {"@id": url + "#webpage"},
            "author": {"@id": record.organization_id}, "publisher": {"@id": record.organization_id},
            "datePublished": PUBLISHED_DATE, "dateModified": base.TODAY,
            "image": [record.representative, body_url, map_url],
            "articleSection": [CATEGORY_LABEL, record.service_region, record.service_city, record.locality, *[str(s["heading"]) for s in sections]],
            "about": about, "mentions": mentions, "hasPart": parts,
        },
        {
            "@type": "Service", "@id": service_id, "name": f"{title(record)} 학습 상담 안내",
            "serviceType": "고등 영어 학습 진단 및 계획 상담", "description": answer,
            "provider": {"@id": record.organization_id}, "areaServed": {"@type": "Place", "name": record.locality},
            "audience": {"@type": "EducationalAudience", "educationalRole": "student", "audienceType": "고등 영어 학습 상담 대상"},
            "about": about, "mentions": mentions, "makesOffer": [offer],
        },
        {
            "@type": "FAQPage", "@id": url + "#faq", "mainEntity": [
                {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}}
                for q, a in faqs
            ],
        },
        {
            "@type": "ItemList", "@id": url + "#related", "name": f"{record.locality} 관련 학원·학습 안내",
            "numberOfItems": len(related), "itemListElement": [
                {"@type": "ListItem", "position": position, "name": label, "url": link}
                for position, (_, label, link) in enumerate(related, 1)
            ],
        },
    ]
    if schools:
        graph.append({
            "@type": "ItemList", "@id": url + "#schools", "name": f"{record.locality} 고등학교 참고 정보",
            "numberOfItems": len(schools), "itemListElement": [
                {"@type": "ListItem", "position": position, "name": school}
                for position, school in enumerate(schools, 1)
            ],
        })
    return {"@context": "https://schema.org", "@graph": graph}


def render_facts(record: base.Record) -> str:
    grades = "·".join(high_grades(record)) if high_grades(record) else "상담 확인 필요"
    schools = high_schools(record)
    school_tags = "".join(f"<span>{base.esc(school)}</span>" for school in schools) if schools else "<span>고등학교 자료를 상담 시 확인</span>"
    tuition = (
        f'<dt>교습비 자료</dt><dd><a href="{base.esc(record.tuition_url)}" target="_blank" rel="noopener noreferrer">센터별 안내 확인 <span aria-hidden="true">↗</span></a></dd>'
        if record.tuition_url else "<dt>교습비 자료</dt><dd>상담 시 확인</dd>"
    )
    location = f"<dt>위치 참고</dt><dd>{base.esc(record.location_note)}</dd>" if record.location_note else ""
    return f'''<section class="center-profile-overview high-english-fit-section" aria-labelledby="fit-facts-title">
      <div class="wrap center-profile-overview-grid">
        <div><p class="subject-kicker">LOCAL · HIGH GRADE · STUDENT</p><h2 id="fit-facts-title">{base.esc(record.locality)} 지역·고등 학년·추천 학생</h2><p>{base.esc(record.persona)}을 구체적인 상담 대상으로 삼았습니다. 학년과 현재 개설 시간은 확인된 정보와 실제 상담 내용을 함께 보세요.</p></div>
        <dl class="center-profile-facts"><dt>센터 기준</dt><dd>{base.esc(record.center_name)}</dd><dt>확인된 주소</dt><dd>{base.esc(record.address)}</dd>{location}<dt>영어 가능 고등 학년</dt><dd>{base.esc(grades)}</dd><dt>등록 학원명</dt><dd>{base.esc(record.legal_name)}</dd><dt>등록 정보</dt><dd>{base.esc(record.registration)}</dd>{tuition}</dl>
      </div>
      <div class="wrap"><div class="center-profile-schools"><strong>고등학교 참고 정보</strong><div>{school_tags}</div></div></div>
    </section>'''


def render_local_page(record: base.Record, records: list[base.Record], index: int) -> str:
    meta = meta_description(record)
    answer, sections = content_sections(record)
    faqs = build_faqs(record)
    review = review_scenario(record)
    related = related_links(record, records, index)
    schema = json.dumps(schema_graph(record, meta, answer, sections, faqs, related), ensure_ascii=False, separators=(",", ":"))
    body_src = f"../../../assets/centers/common/{record.body_file}"
    body_mobile_src = f"../../../assets/centers/common/{record.body_mobile_file}"
    body_mobile_avif = "../../../assets/generated/yeongsu-seoul-mobile.avif" if record.body_file.startswith("seoul") else "../../../assets/generated/yeongsu-local-mobile.avif"
    map_src = f"../../../assets/maps/{record.map_file}"
    faq_html = "".join(
        f'<details class="subject-faq-item"{" open" if position == 1 else ""}><summary><span>Q</span>{base.esc(q)}</summary><div class="subject-faq-answer"><span>A</span><p>{base.esc(a)}</p></div></details>'
        for position, (q, a) in enumerate(faqs, 1)
    )
    related_html = "".join(
        f'<a class="subject-related-card" href="{base.esc(link)}"><span>{base.esc(kind)}</span><strong>{base.esc(label)}</strong><small>자세히 보기 →</small></a>'
        for kind, label, link in related
    )
    url = page_url(record)
    return f'''<!doctype html>
<html lang="ko"><head>
  <meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{base.esc(title(record))} | {base.SITE_NAME}</title>
  <meta name="description" content="{base.esc(meta)}"><meta name="robots" content="index, follow">
  <link rel="canonical" href="{url}">
  <meta property="og:locale" content="ko_KR"><meta property="og:site_name" content="{base.SITE_NAME}"><meta property="og:type" content="article"><meta property="og:title" content="{base.esc(title(record))} | {base.SITE_NAME}"><meta property="og:description" content="{base.esc(meta)}"><meta property="og:url" content="{url}"><meta property="og:image" content="{base.esc(record.representative)}"><meta property="og:image:alt" content="{base.esc(title(record))} 대표 이미지">
  <meta name="twitter:card" content="summary_large_image"><meta name="twitter:title" content="{base.esc(title(record))} | {base.SITE_NAME}"><meta name="twitter:description" content="{base.esc(meta)}"><meta name="twitter:image" content="{base.esc(record.representative)}">
  <link rel="alternate" type="application/rss+xml" title="{base.SITE_NAME} RSS" href="{base.BASE_URL}/rss.xml"><link rel="icon" type="image/png" href="../../../assets/favicon.png"><link rel="stylesheet" href="../../../assets/subject.css"><script type="application/ld+json">{schema}</script>
</head><body class="subject-academy-page high-english-subject-page"><a class="skip-link" href="#main">본문 바로가기</a>{base.root_nav("과목별학원")}<main id="main">
  <section class="subject-local-hero"><div class="wrap"><nav class="subject-breadcrumb" aria-label="현재 위치"><a href="/">홈</a><span>›</span><a href="/과목별학원/">과목별학원</a><span>›</span><a href="/과목별학원/{CATEGORY}/">{CATEGORY_LABEL}</a><span>›</span><strong>{base.esc(title(record))}</strong></nav><p class="subject-kicker">HIGH SCHOOL ENGLISH COACHING · {base.esc(record.service_region)} {base.esc(record.service_city)}</p><h1>{base.esc(title(record))}</h1><p class="subject-hero-answer">{base.esc(meta)}</p><div class="subject-hero-tags"><span>{base.esc(record.service_region)}</span><span>{base.esc(record.service_city)}</span><span>고등 영어</span><span>어휘·문법·독해·서술형</span></div></div></section>
  <section class="subject-quick-answer" aria-label="{base.esc(title(record))} 핵심 답변"><div class="wrap subject-narrow"><div class="subject-answer-box"><span>핵심 답변</span><p>{base.esc(answer)}</p></div></div></section>
  <section class="subject-media-section"><div class="wrap"><img class="subject-hidden-representative" data-role="representative-image" src="{base.esc(record.representative)}" alt="{base.esc(title(record))} {base.SITE_NAME} 대표 이미지" style="display:none;"><figure class="subject-body-card"><div class="subject-media-label"><span>01</span><strong>{base.esc(record.locality)} 고등 영어 학습 안내</strong></div><picture><source media="(max-width:720px)" type="image/avif" srcset="{body_mobile_avif}"><source media="(max-width:720px)" type="image/webp" srcset="{body_mobile_src}"><img src="{body_src}" alt="{base.esc(title(record))} 어휘·문법·독해 학습 안내 이미지" width="{record.body_width}" height="{record.body_height}" fetchpriority="high" decoding="async"></picture></figure><figure class="subject-map-card"><div class="subject-media-label"><span>02</span><strong>{base.esc(record.locality)} 위치 안내</strong></div><img src="{map_src}" alt="{base.esc(title(record))} 센터 위치 지도" width="{record.map_width}" height="{record.map_height}" loading="lazy" decoding="async"><figcaption>확인된 센터 주소는 {base.esc(record.address)}입니다. 방문 가능 시간은 상담 시 확인하세요.</figcaption></figure></div></section>
  <article class="subject-manuscript wrap" aria-labelledby="manuscript-title"><header class="subject-copy-head"><p>ANSWER-FIRST HIGH SCHOOL ENGLISH GUIDE</p><h2 id="manuscript-title">{base.esc(title(record))} 선택 전 확인할 학습 기준</h2></header><div class="subject-copy-flow">{base.render_sections(sections)}</div></article>
  {render_facts(record)}
  <section class="subject-faq-section"><div class="wrap subject-narrow"><div class="subject-section-head"><p>QUESTIONS &amp; ANSWERS</p><h2>{base.esc(title(record))} 자주 묻는 질문</h2><span>화면의 질문과 답변은 구조화 데이터와 동일합니다.</span></div><div class="subject-faq-list">{faq_html}</div></div></section>
  <section class="subject-review-section"><div class="wrap subject-narrow"><div class="subject-review-card"><p class="subject-review-label">PARENT VOICE GUIDE</p><h2>{base.esc(title(record))} 학부모 상담 메모</h2><blockquote>{base.esc(review)}</blockquote><p class="subject-review-note">특정 학부모의 이용 경험이나 성적 사례가 아니라, 대표적인 상담 준비 상황을 재구성한 예시입니다.</p></div></div></section>
  <section class="subject-related-section"><div class="wrap subject-narrow"><div class="subject-section-head"><p>RELATED PAGES</p><h2>{base.esc(record.locality)} 학원 정보 이어보기</h2><span>같은 동네의 학년별 안내와 인접한 고등 영어학원 페이지를 함께 확인할 수 있습니다.</span></div><div class="subject-related-grid">{related_html}</div></div></section>
  <section class="consult-strip"><div class="wrap consult-strip-inner"><div><p class="eyebrow">상담 전 체크</p><h2>{base.esc(record.locality)} 최근 영어 시험지와 답안 기록 준비</h2><p>어휘·문법·독해 근거 중 막힌 지점을 확인해야 첫 주의 학습 순서를 구체적으로 정할 수 있습니다.</p></div><a class="btn btn-primary" href="/상담문의/">상담 준비하기</a></div></section>
</main>{base.footer()}</body></html>'''


def hub_faqs() -> list[tuple[str, str]]:
    return [
        ("고등 영어학원은 내신과 모의고사를 같은 방식으로 준비하나요?", "내신은 학교별 지문과 서술형 기준을, 모의고사는 낯선 글의 구조와 시간 배분을 따로 확인해야 합니다. 두 준비를 한 계획에 넣더라도 오답 분류와 복습 기준은 구분하는 편이 좋습니다."),
        ("지역별 고등 영어 가능 학년은 어떤 자료를 기준으로 하나요?", "확인된 센터 정보의 영어 가능 학년 중 고1·고2·고3만 안내합니다. 고등 학년 정보가 없으면 현재 개설 범위를 상담에서 확인하도록 안내합니다."),
        ("고등 영어 상담 전에 어떤 자료를 준비하면 좋나요?", "최근 시험지, 현재 교재, 학교 시험 범위, 학생이 직접 쓴 답안과 실제 공부 가능 시간을 준비하세요. 정답보다 근거 문장과 오답 원인을 확인해야 상담 결과를 첫 주 계획으로 연결할 수 있습니다."),
    ]


def render_hub(records: list[base.Record]) -> str:
    hub_url = base.absolute_url("과목별학원", CATEGORY)
    parent_url = base.absolute_url("과목별학원")
    description = "전국 371개 동네별 고등 영어학원 안내입니다. 고등 가능 학년, 어휘·문법·독해·서술형 진단, 내신·모의고사 복습과 상담 기준을 지역별로 확인하세요."
    grouped: dict[str, dict[str, list[base.Record]]] = defaultdict(lambda: defaultdict(list))
    for record in records:
        grouped[record.service_region][record.service_city].append(record)
    region_html: list[str] = []
    region_keys = sorted(grouped, key=lambda value: (base.REGION_ORDER.index(value) if value in base.REGION_ORDER else 99, value))
    for region in region_keys:
        city_html: list[str] = []
        for city in sorted(grouped[region]):
            locals_ = sorted(grouped[region][city], key=lambda item: item.locality)
            buttons = "".join(
                f'<a class="subject-local-button" data-local-name="{base.esc(item.locality)}" data-search="{base.esc(" ".join([item.locality, item.service_city, item.center_name]))}" href="/과목별학원/{CATEGORY}/{quote(item.slug)}/"><strong>{base.esc(item.locality)}</strong><span>{CATEGORY_LABEL}</span></a>'
                for item in locals_
            )
            city_html.append(f'<section class="subject-city-group" data-city-group><h3>{base.esc(city)} <small>{len(locals_)}</small></h3><div class="subject-local-grid">{buttons}</div></section>')
        count = sum(len(items) for items in grouped[region].values())
        opened = " open" if region == "서울" else ""
        region_html.append(f'<details class="subject-region-group" data-region-group{opened}><summary><span>{base.esc(region)}</span><strong>{count}개 지역</strong></summary><div class="subject-region-content">{"".join(city_html)}</div></details>')
    faqs = hub_faqs()
    faq_html = "".join(
        f'<details class="subject-faq-item"{" open" if i == 1 else ""}><summary><span>Q</span>{base.esc(q)}</summary><div class="subject-faq-answer"><span>A</span><p>{base.esc(a)}</p></div></details>'
        for i, (q, a) in enumerate(faqs, 1)
    )
    graph = {"@context": "https://schema.org", "@graph": [
        {"@type": "CollectionPage", "@id": hub_url + "#webpage", "url": hub_url, "name": "고등 영어학원 지역 안내", "description": description, "inLanguage": "ko-KR", "about": [CATEGORY_LABEL, "고등 영어 학습 진단", "내신", "모의고사", "오답 재해석·재작성"], "breadcrumb": {"@id": hub_url + "#breadcrumb"}, "hasPart": [{"@id": hub_url + "#local-list"}, {"@id": hub_url + "#faq"}]},
        {"@type": "BreadcrumbList", "@id": hub_url + "#breadcrumb", "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "홈", "item": base.BASE_URL + "/"},
            {"@type": "ListItem", "position": 2, "name": "과목별학원", "item": parent_url},
            {"@type": "ListItem", "position": 3, "name": CATEGORY_LABEL, "item": hub_url},
        ]},
        {"@type": "ItemList", "@id": hub_url + "#local-list", "name": "전국 고등 영어학원 지역 페이지", "numberOfItems": len(records), "itemListElement": [
            {"@type": "ListItem", "position": i, "name": title(record), "url": page_url(record)} for i, record in enumerate(records, 1)
        ]},
        {"@type": "FAQPage", "@id": hub_url + "#faq", "mainEntity": [
            {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in faqs
        ]},
    ]}
    schema = json.dumps(graph, ensure_ascii=False, separators=(",", ":"))
    return f'''<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>고등 영어학원 지역 안내 | {base.SITE_NAME}</title><meta name="description" content="{base.esc(description)}"><meta name="robots" content="index, follow"><link rel="canonical" href="{hub_url}"><meta property="og:locale" content="ko_KR"><meta property="og:site_name" content="{base.SITE_NAME}"><meta property="og:type" content="website"><meta property="og:title" content="고등 영어학원 지역 안내 | {base.SITE_NAME}"><meta property="og:description" content="{base.esc(description)}"><meta property="og:url" content="{hub_url}"><link rel="alternate" type="application/rss+xml" title="{base.SITE_NAME} RSS" href="{base.BASE_URL}/rss.xml"><link rel="icon" type="image/png" href="../../assets/favicon.png"><link rel="stylesheet" href="../../assets/subject.css"><script type="application/ld+json">{schema}</script></head><body class="subject-hub-page high-english-hub-page"><a class="skip-link" href="#main">본문 바로가기</a>{base.root_nav("과목별학원")}<main id="main">
    <section class="subject-hub-hero"><div class="wrap"><nav class="subject-breadcrumb" aria-label="현재 위치"><a href="/">홈</a><span>›</span><a href="/과목별학원/">과목별학원</a><span>›</span><strong>{CATEGORY_LABEL}</strong></nav><p class="subject-kicker">HIGH SCHOOL ENGLISH ACADEMY DIRECTORY</p><h1>동네별 고등 영어학원 안내</h1><p>{base.esc(description)}</p><div class="subject-hub-stats"><span><strong>371</strong>지역 상세 안내</span><span><strong>검증</strong>고등 학년·학교·주소</span><span><strong>5</strong>페이지별 FAQ</span></div></div></section>
    <section class="subject-directory-section"><div class="wrap"><div class="subject-directory-head"><div><p>LOCAL DIRECTORY</p><h2>지역명으로 고등 영어학원 찾기</h2></div><label class="subject-search"><span class="sr-only">지역명 검색</span><input id="subject-local-search" type="search" placeholder="예: 명일동, 불당동" autocomplete="off"><button id="subject-search-reset" type="button" hidden>초기화</button></label></div><p id="subject-search-status" class="subject-search-status" aria-live="polite"></p><div id="subject-region-list">{"".join(region_html)}</div></div></section>
    <section class="subject-hub-guide"><div class="wrap"><div class="subject-section-head"><p>SELECTION GUIDE</p><h2>고등 영어는 답안 근거와 복습 결과를 함께 확인하세요</h2></div><div class="subject-guide-grid"><article><span>01</span><h3>현재 답안 진단</h3><p>어휘·문법·독해 중 처음 막힌 단계를 최근 답안에서 찾습니다.</p></article><article><span>02</span><h3>학교 자료와 학년 확인</h3><p>고등 가능 학년과 최신 시험 범위·교재를 함께 대조합니다.</p></article><article><span>03</span><h3>오답 복습 계획</h3><p>내신과 모의고사의 복습 기준을 나누고 다음 확인 날짜를 정합니다.</p></article></div></div></section>
    <section class="subject-faq-section"><div class="wrap subject-narrow"><div class="subject-section-head"><p>FAQ</p><h2>고등 영어학원 지역 안내 자주 묻는 질문</h2><span>지역 상세 페이지를 보기 전에 확인할 기준입니다.</span></div><div class="subject-faq-list">{faq_html}</div></div></section>
  </main>{base.footer()}<script>(()=>{{const input=document.getElementById('subject-local-search');const reset=document.getElementById('subject-search-reset');const status=document.getElementById('subject-search-status');const cards=[...document.querySelectorAll('[data-local-name]')];const cities=[...document.querySelectorAll('[data-city-group]')];const regions=[...document.querySelectorAll('[data-region-group]')];const normalize=value=>value.toLowerCase().replace(/\\s+/g,'');const update=()=>{{const query=normalize(input.value.trim());let count=0;cards.forEach(card=>{{const matched=!query||normalize(card.dataset.search||card.dataset.localName).includes(query);card.hidden=!matched;if(matched)count+=1;}});cities.forEach(city=>{{city.hidden=![...city.querySelectorAll('[data-local-name]')].some(card=>!card.hidden);}});regions.forEach(region=>{{region.hidden=![...region.querySelectorAll('[data-local-name]')].some(card=>!card.hidden);if(query&&!region.hidden)region.open=true;}});reset.hidden=!query;status.textContent=query?`${{count}}개 지역을 찾았습니다.`:'';}};input.addEventListener('input',update);reset.addEventListener('click',()=>{{input.value='';update();input.focus();}});}})();</script></body></html>'''


def preflight(records: list[base.Record]) -> None:
    if len(records) != 371:
        raise ValueError(f"상세 371개가 필요합니다: {len(records)}")
    if len({record.slug for record in records}) != 371 or len({record.representative for record in records}) != 371:
        raise ValueError("지역 slug 또는 대표 이미지 고유성 검사 실패")
    metas = [meta_description(record) for record in records]
    if len(set(metas)) != 371:
        raise ValueError("메타 설명 371개 고유성 검사 실패")
    forbidden = re.compile(
        r"LOCAL ACADEMY GUIDE|핵심 키워드|(?<![가-힣])원고(?![가-힣])|이 페이지는|이 안내는|수업 진행방식|공통자료|공통 센터자료|학교명을 임의로|"
        r"따라가며도|영수국|실시간 수업|온라인 수업|입시합격|합격전략|실제 후기|성적이 향상|점수가 올랐|"
        r"답안를|문제이|문제을|근거을|구조을|근거과|답안와|작성와|영어은|첫 식|영영어원|"
        r"적용와|적용를|기록를|기준를|기준는|과정를|계획를|학생 학생|상담 상담|확인 확인",
        re.I,
    )
    for index, record in enumerate(records):
        answer, sections = content_sections(record)
        faqs = build_faqs(record)
        public = " ".join(
            [answer, record.persona, review_scenario(record)]
            + [str(section["heading"]) for section in sections]
            + [str(value) for section in sections for value in section["paragraphs"]]
            + [str(value) for section in sections for value in section.get("items", [])]
            + [value for pair in faqs for value in pair]
        )
        match = forbidden.search(public)
        if match:
            raise ValueError(f"{record.locality} 공개 문구 금칙어: {match.group(0)}")
        graph = schema_graph(record, meta_description(record), answer, sections, faqs, related_links(record, records, index))
        types = {
            item for node in graph["@graph"]
            for item in (node.get("@type", []) if isinstance(node.get("@type"), list) else [node.get("@type")])
        }
        required = {"EducationalOrganization", "LocalBusiness", "WebPage", "ImageObject", "Article", "Service", "FAQPage", "BreadcrumbList", "ItemList"}
        if not required.issubset(types):
            raise ValueError(f"{record.locality} 스키마 누락: {sorted(required - types)}")


def write_site(records: list[base.Record]) -> None:
    resolved = TARGET_ROOT.resolve()
    subject = (ROOT / "과목별학원").resolve()
    if resolved.parent != subject:
        raise RuntimeError(f"안전하지 않은 대상 경로: {resolved}")
    TARGET_ROOT.mkdir(parents=True, exist_ok=True)
    expected = {record.slug for record in records}
    for child in TARGET_ROOT.iterdir():
        if child.is_dir() and child.name not in expected:
            if child.resolve().parent != resolved:
                raise RuntimeError(f"안전하지 않은 잔여 경로: {child}")
            shutil.rmtree(child)
    for index, record in enumerate(records):
        output = TARGET_ROOT / record.slug / "index.html"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(render_local_page(record, records, index).rstrip() + "\n", encoding="utf-8", newline="\n")
    (TARGET_ROOT / "index.html").write_text(render_hub(records).rstrip() + "\n", encoding="utf-8", newline="\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="학습코칭.kr 고등 영어학원 371개 지역 페이지 생성")
    parser.add_argument("--workbook", type=Path, default=DEFAULT_WORKBOOK)
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()
    records = make_records(args.workbook)
    preflight(records)
    if not args.check_only:
        write_site(records)
    print(json.dumps({
        "records": len(records),
        "unique_centers": len({record.center_name for record in records}),
        "missing_high_english_grades": sum(not high_grades(record) for record in records),
        "missing_tuition_links": sum(not record.tuition_url for record in records),
        "written": not args.check_only,
        "target": str(TARGET_ROOT),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
