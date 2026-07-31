# -*- coding: utf-8 -*-
"""학습코칭.kr 전국학원 동네·자식페이지의 답변 영역을 개별화한다.

이 스크립트가 다루는 범위
------------------------
* 전국학원/{광역}/{시군구}/{동네}/index.html
* 전국학원/{광역}/{시군구}/{동네}/{자식}/index.html

안전 원칙
---------
* 기본 실행은 dry-run이며 파일을 쓰지 않는다.
* ``--apply``를 명시해야만 전체 파일을 수정한다.
* 기존 주소·학교·센터·등록 정보와 본문, FAQ, 후기, 평점은 바꾸지 않는다.
* 페이지에 이미 적혀 있는 사실만 새 요약 영역에 재사용한다.
* 임의의 학교명, 주소, 후기, 평점, 성과를 만들지 않는다.
* 모든 결과를 메모리에서 먼저 검증한 뒤 오류가 없을 때만 일괄 기록한다.
* 경로 기반 SHA-256 선택을 사용하므로 같은 입력에는 같은 결과가 나온다.

사용 예
-------
두 페이지의 변경 예시와 전체 검증 결과만 확인::

    python tmp/improve_national_content_v2.py --dry-run --samples 2

특정 두 페이지를 샘플로 확인::

    python tmp/improve_national_content_v2.py --dry-run ^
      --sample-page "전국학원/서울/강동구/명일동/index.html" ^
      --sample-page "전국학원/충청/천안시/불당동/중등영수학원/index.html"

전체 검증을 통과한 결과를 실제 파일에 반영::

    python tmp/improve_national_content_v2.py --apply

HTML 원문까지 샘플에 출력::

    python tmp/improve_national_content_v2.py --dry-run --samples 2 --show-html
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import html
import json
import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Sequence


ROOT = Path(__file__).resolve().parents[1]
NATIONAL_ROOT = ROOT / "전국학원"
EXPECTED_TARGET_COUNT = 1_484

SEO_START = "<!-- seo-geo-enhancement:start -->"
SEO_END = "<!-- seo-geo-enhancement:end -->"

OLD_PRODUCER_LABELS = (
    "SEARCH INTENT ANSWER",
    "SEO · AEO · GEO SUMMARY",
    "SEO · GEO SUMMARY",
    "ANSWER READY",
    "CONSULTING CHECKLIST",
)

PARENT_FACING_LABELS = {
    "answer": "학원 선택 핵심 안내",
    "checklist": "상담 준비 자료",
}

GRADE_ORDER = {
    **{f"초{i}": i for i in range(1, 7)},
    **{f"중{i}": 10 + i for i in range(1, 4)},
    **{f"고{i}": 20 + i for i in range(1, 4)},
}


SCENARIOS: dict[str, tuple[str, ...]] = {
    "전체": (
        "과목마다 이해도 차이가 커서 무엇부터 보완할지 정해야 하는 학생",
        "계획표는 작성하지만 실행 기록이 남지 않아 학습 습관부터 살펴봐야 하는 학생",
        "시험 후 오답을 확인해도 다음 단원에서 비슷한 실수를 반복하는 학생",
        "영어와 수학의 학습 속도가 달라 한 과목에 공부 시간이 치우치는 학생",
        "새 학기 진도와 이전 학년의 기초 공백을 함께 점검해야 하는 학생",
        "숙제는 끝내지만 풀이 이유를 설명하거나 복습하는 단계가 부족한 학생",
        "시험 준비를 늦게 시작해 범위별 계획과 마감 기준이 필요한 학생",
        "공부 시간은 확보했지만 교재 난이도가 현재 수준과 맞는지 확인이 필요한 학생",
        "혼자 공부할 때 막힌 단원을 오래 미루어 주간 확인이 필요한 학생",
        "과목별 오답 원인이 달라 진단 후 관리 순서를 세워야 하는 학생",
        "점수보다 먼저 수업 준비·숙제·복습 루틴을 안정시키려는 학생",
        "학년이 바뀌며 학습량과 시험 방식 변화에 맞춘 계획이 필요한 학생",
    ),
    "초등": (
        "연산이나 어휘는 연습하지만 문제를 읽고 풀이 순서를 정하는 데 시간이 필요한 학생",
        "숙제를 시작하는 시간과 마치는 시간이 일정하지 않아 기본 루틴부터 잡아야 하는 학생",
        "배운 개념을 말로 설명하거나 다른 문제에 적용하는 단계가 아직 낯선 학생",
        "영어 어휘와 수학 연산을 함께 챙기느라 주간 분량 조절이 필요한 학생",
        "틀린 문제를 지우고 다시 쓰는 데 그쳐 오답 이유를 남기는 연습이 필요한 학생",
        "학년 진도보다 앞서가기 전에 읽기·계산의 기초 공백을 확인해야 하는 학생",
        "문제를 오래 붙잡거나 바로 답을 확인해 스스로 시도하는 시간을 조절해야 하는 학생",
        "교재는 여러 권이지만 끝낸 범위와 이해한 범위가 구분되지 않는 학생",
        "수업 날에는 공부하지만 수업 사이 복습 간격이 길어지는 학생",
        "단원평가 전 무엇을 다시 볼지 혼자 정하기 어려운 학생",
        "문장제와 서술형에서 풀이 과정을 순서대로 표현하는 연습이 필요한 학생",
        "학습량보다 집중 가능한 시간과 작은 완료 경험을 먼저 확인해야 하는 학생",
    ),
    "중등": (
        "학교 진도는 따라가지만 시험 범위가 넓어지면 복습 순서를 놓치는 학생",
        "개념 문제는 풀어도 서술형과 변형 문제에서 풀이 근거가 흔들리는 학생",
        "영어 본문·문법과 수학 단원 학습의 주간 균형을 맞추기 어려운 학생",
        "시험 직전에 공부가 몰려 평소 과제와 누적 복습을 나눌 필요가 있는 학생",
        "오답 원인이 개념 부족인지 시간 부족인지 구분하지 못하는 학생",
        "수행평가와 지필평가 일정을 함께 관리할 계획이 필요한 학생",
        "숙제는 제출하지만 채점 뒤 틀린 문제를 다시 확인하는 과정이 약한 학생",
        "중학교 첫 시험이나 학년 전환을 앞두고 공부량을 조절해야 하는 학생",
        "학교별 시험 범위와 현재 교재 진도가 어긋나 우선순위 확인이 필요한 학생",
        "풀이 속도를 높이기 전에 정확한 해석과 계산 습관을 점검해야 하는 학생",
        "과목별 점수 차이보다 공부 방법의 차이를 먼저 찾아야 하는 학생",
        "주말 계획이 자주 밀려 다음 주 학습까지 영향을 받는 학생",
    ),
    "고등": (
        "내신 범위와 모의고사 오답을 따로 관리하지 못해 우선순위가 흔들리는 학생",
        "학습 시간은 길지만 과목별 완료 기준이 없어 계획이 자주 밀리는 학생",
        "개념은 알고 있어도 제한 시간 안에 풀이를 완성하기 어려운 학생",
        "영어 독해·어휘와 수학 유형 복습의 주간 비중을 조정해야 하는 학생",
        "시험 결과를 단순 점수로만 보고 취약 단원과 실수 원인을 나누지 못하는 학생",
        "학교 시험과 모의고사 준비 시기가 겹칠 때 공부 순서를 정하기 어려운 학생",
        "고난도 문제보다 기본·중간 난도 문항의 실수를 먼저 줄여야 하는 학생",
        "계획한 진도와 실제 완료한 진도의 차이를 매주 확인할 필요가 있는 학생",
        "수업에서 이해한 내용을 혼자 재현하는 복습 단계가 부족한 학생",
        "여러 교재를 병행하면서 오답과 미완료 범위가 흩어지는 학생",
        "학년 전환이나 시험 일정 변화에 맞춰 공부 시간을 다시 배분해야 하는 학생",
        "문제별 소요 시간과 풀이 선택을 기록하며 시험 운영을 점검해야 하는 학생",
    ),
}


LEARNING_FOCUS: dict[str, tuple[str, ...]] = {
    "전체": (
        "현재 교재와 최근 평가 자료를 함께 보고 과목별 시작점을 나누는 것",
        "주간 계획의 분량보다 실제 완료 여부와 미완료 원인을 확인하는 것",
        "오답을 개념·계산·해석·시간 관리로 구분해 다음 학습에 연결하는 것",
        "영어와 수학의 부족한 영역을 같은 기준으로 보지 않고 따로 진단하는 것",
        "새 진도를 시작하기 전 이전 단원의 공백과 복습 간격을 확인하는 것",
        "학생이 스스로 설명할 수 있는 범위와 도움을 받아 푸는 범위를 구분하는 것",
        "시험일까지 남은 시간을 범위·복습·오답 점검으로 나누는 것",
        "교재 수보다 현재 수준에 맞는 문제 난이도와 완료 기준을 정하는 것",
        "공부를 미룬 이유를 시간·난이도·집중 환경으로 나누어 보는 것",
        "과목별 취약점과 학습 습관 중 먼저 바꿀 한 가지를 정하는 것",
        "수업 준비부터 숙제 확인, 복습까지 이어지는 한 주의 흐름을 살피는 것",
        "학년 변화에 맞춰 공부량·시험 방식·피드백 주기를 다시 맞추는 것",
    ),
    "초등": (
        "읽기와 계산의 기초를 확인한 뒤 학생이 끝낼 수 있는 분량부터 정하는 것",
        "숙제 시작 시간과 복습 간격을 짧고 일정하게 만드는 것",
        "배운 개념을 말로 설명하고 비슷한 문제에 적용할 수 있는지 확인하는 것",
        "영어 어휘와 수학 연산의 주간 분량을 무리 없이 나누는 것",
        "틀린 답만 고치지 않고 문제를 잘못 읽은 지점까지 돌아보는 것",
        "선행 범위보다 현재 학년의 읽기·계산 공백을 먼저 찾는 것",
        "혼자 시도하는 시간과 질문이 필요한 시점을 구분하는 것",
        "사용 교재마다 끝낸 범위와 다시 볼 범위를 표시하는 것",
        "수업 사이에 짧은 복습이 이어지는지 확인하는 것",
        "단원평가 전에 개념·기본 문제·오답 순서로 복습하는 것",
        "문장제와 서술형에서 풀이 과정을 한 단계씩 적는 것",
        "집중 가능한 시간을 기준으로 작은 완료 목표를 세우는 것",
    ),
    "중등": (
        "학교 진도와 시험 범위를 맞추고 누적 복습 시점을 앞당기는 것",
        "개념 이해와 서술형 풀이 근거를 각각 확인하는 것",
        "영어 본문·문법과 수학 단원 복습의 주간 비중을 나누는 것",
        "시험 직전 몰아보지 않도록 과제·복습·오답 일정을 분산하는 것",
        "오답을 개념 부족·풀이 실수·시간 부족으로 나누는 것",
        "수행평가와 지필평가 일정을 한 계획표에서 함께 확인하는 것",
        "채점 뒤 재풀이와 유사 문제 확인까지 완료 기준에 넣는 것",
        "학년 전환에 맞춰 과목별 공부량과 시험 준비 시점을 조정하는 것",
        "학교 진도와 현재 교재가 다른 경우 먼저 볼 범위를 정하는 것",
        "풀이 속도보다 문제 해석과 계산의 정확성을 먼저 안정시키는 것",
        "과목별 점수 차이를 공부 방법과 오답 유형으로 다시 살펴보는 것",
        "주말 미완료 학습이 다음 주로 누적되지 않게 마감 기준을 세우는 것",
    ),
    "고등": (
        "내신 범위와 모의고사 오답을 분리해 학습 우선순위를 정하는 것",
        "공부 시간보다 과목별 완료 범위와 실제 수행 기록을 확인하는 것",
        "시간 제한 안에서 개념을 꺼내 풀이로 연결할 수 있는지 보는 것",
        "영어 독해·어휘와 수학 유형 복습의 주간 비중을 조절하는 것",
        "시험 결과를 취약 단원·실수·시간 배분으로 나누어 해석하는 것",
        "학교 시험과 모의고사 일정이 겹칠 때 먼저 끝낼 범위를 정하는 것",
        "고난도보다 기본·중간 난도 문항의 실수부터 줄이는 것",
        "계획 진도와 실제 완료 진도의 차이를 매주 기록하는 것",
        "수업에서 이해한 내용을 혼자 다시 풀어낼 수 있는지 확인하는 것",
        "여러 교재의 오답과 미완료 범위를 한곳에 모아 관리하는 것",
        "학년과 시험 일정 변화에 맞춰 과목별 시간을 다시 배분하는 것",
        "문항별 소요 시간과 풀이 선택을 기록해 시험 운영을 점검하는 것",
    ),
}


DECISION_CRITERIA = (
    "진단 결과가 주간 계획과 오답 점검으로 실제 이어지는지 확인하세요.",
    "학생이 할 수 있는 분량과 선생님이 확인할 완료 기준이 분명한지 살펴보세요.",
    "수업 설명뿐 아니라 수업 사이 복습을 어떻게 확인하는지도 물어보세요.",
    "최근 시험지에서 찾은 약점이 다음 교재와 과제에 반영되는지 확인하세요.",
    "과목마다 다른 오답 원인을 같은 방식으로 처리하지 않는지 살펴보세요.",
    "시험 전 계획을 언제 세우고 중간에 어떻게 조정하는지 확인하세요.",
    "숙제 미완료를 양으로만 보지 않고 원인까지 확인하는지 물어보세요.",
    "학생이 이해한 내용을 스스로 설명하고 재현하는 단계가 있는지 살펴보세요.",
    "학년이 바뀔 때 진도와 학습량을 다시 진단하는지 확인하세요.",
    "학부모에게 전달되는 피드백에 다음 학습 계획이 포함되는지 물어보세요.",
    "교재를 추가하기 전에 기존 교재의 미완료와 오답을 정리하는지 살펴보세요.",
    "상담에서 제시한 목표가 주간 단위의 확인 항목으로 구체화되는지 확인하세요.",
)


CONSULT_QUESTIONS: dict[str, tuple[str, ...]] = {
    "전체": (
        "현재 가장 먼저 점검해야 할 과목과 단원은 무엇인가요?",
        "주간 계획에서 학생이 반드시 끝내야 할 기준은 어떻게 정하나요?",
        "반복되는 오답을 어떤 기준으로 분류하고 다시 확인하나요?",
        "영어와 수학의 공부 비중은 어떤 자료를 보고 조정하나요?",
        "이전 학년의 공백과 현재 진도는 어떤 순서로 연결하나요?",
        "수업에서 이해한 내용을 혼자 복습했는지 어떻게 확인하나요?",
        "시험일까지 학습 범위와 오답 점검을 어떻게 나누나요?",
        "현재 교재 난이도가 학생에게 맞는지는 어떻게 판단하나요?",
        "계획이 밀렸을 때 분량과 순서를 어떤 방식으로 다시 조정하나요?",
        "학부모 피드백에는 어떤 학습 기록이 포함되나요?",
        "숙제·복습 습관을 확인하는 주기는 어떻게 되나요?",
        "학년이 바뀌면 진단과 계획도 다시 진행하나요?",
    ),
    "초등": (
        "읽기와 계산 기초 중 먼저 확인할 부분은 무엇인가요?",
        "집에서 이어갈 수 있는 짧은 복습 분량은 어떻게 정하나요?",
        "개념을 이해했는지 학생의 설명으로도 확인하나요?",
        "영어 어휘와 수학 연산의 주간 분량은 어떻게 나누나요?",
        "오답 이유를 학생이 직접 남기도록 어떤 방식으로 돕나요?",
        "선행 전에 현재 학년의 기초 공백을 어떻게 확인하나요?",
        "혼자 풀어보는 시간과 질문하는 시점을 어떻게 정하나요?",
        "여러 교재 중 어떤 교재를 먼저 마무리할지 어떻게 판단하나요?",
        "수업이 없는 날의 복습도 확인할 수 있나요?",
        "단원평가 전 복습 순서는 어떻게 잡나요?",
        "문장제와 서술형 풀이 과정을 어떻게 점검하나요?",
        "집중 시간에 맞춘 완료 목표는 어떻게 정하나요?",
    ),
    "중등": (
        "학교 시험 범위와 현재 교재 진도를 어떻게 맞추나요?",
        "서술형에서 풀이 근거가 약한 부분은 어떻게 확인하나요?",
        "영어와 수학의 시험 준비 비중을 어떻게 조정하나요?",
        "시험 직전 학습이 몰리지 않도록 언제부터 계획하나요?",
        "개념 부족과 시간 부족형 오답을 어떻게 구분하나요?",
        "수행평가 일정도 주간 계획에 함께 반영하나요?",
        "숙제 채점 뒤 재풀이까지 어떻게 확인하나요?",
        "학년 전환기에 공부량을 어떤 기준으로 늘리나요?",
        "학교 진도와 교재가 다를 때 무엇을 먼저 공부하나요?",
        "풀이 속도와 정확성 중 현재 우선순위는 어떻게 정하나요?",
        "과목별 공부 방법의 차이는 어떤 자료로 확인하나요?",
        "주말에 끝내지 못한 계획은 어떻게 다시 배치하나요?",
    ),
    "고등": (
        "내신과 모의고사 오답은 어떻게 나누어 관리하나요?",
        "과목별 공부 시간보다 완료 범위를 어떻게 확인하나요?",
        "시간 제한 안에서 풀이를 완성하는 연습은 어떻게 진행하나요?",
        "영어와 수학의 주간 학습 비중을 어떤 기준으로 정하나요?",
        "시험 결과에서 취약 단원과 실수를 어떻게 구분하나요?",
        "내신과 모의고사 일정이 겹칠 때 무엇부터 준비하나요?",
        "기본 문항 실수를 줄이기 위한 확인 과정이 있나요?",
        "계획 진도와 실제 진도의 차이를 어떻게 기록하나요?",
        "수업 내용을 혼자 다시 풀어내는 단계도 확인하나요?",
        "여러 교재의 오답과 미완료는 어디에 모아 관리하나요?",
        "학년과 시험 일정이 바뀌면 시간 배분도 조정하나요?",
        "문항별 소요 시간과 풀이 선택을 어떻게 점검하나요?",
    ),
}


META_PATTERNS = (
    "{title}에서 {scenario_short}을 위한 점검 기준을 정리했습니다. {focus_short}과 상담 준비 자료를 확인하세요.",
    "{region_line}의 {grade_subject} 안내입니다. {focus_short}을 중심으로 학생 상황과 상담 전 확인사항을 담았습니다.",
    "{title} 선택 전, {scenario_short}인지 살펴보세요. {focus_short}과 지역 센터 참고 정보를 함께 확인할 수 있습니다.",
    "{region_line}에서 {grade_subject} 관리를 알아볼 때 필요한 내용입니다. {focus_short}과 상담 질문을 간결하게 정리했습니다.",
    "{title} 상담을 준비한다면 현재 교재·평가 자료와 함께 {focus_short}을 확인하세요. 지역 수업 정보도 함께 담았습니다.",
    "{title} 페이지입니다. {scenario_short}에게 필요한 {focus_short}과 상담 체크 항목을 지역 기준으로 정리했습니다.",
    "{region_line} 학생을 위한 {grade_subject} 확인 기준입니다. {focus_short}과 수업 전 준비 자료를 살펴보세요.",
    "{title}의 학년·과목 범위와 상담 기준을 정리했습니다. {scenario_short}이라면 {focus_short}부터 확인하세요.",
    "{title}을 비교할 때 필요한 학생 상황, 학습 범위, 상담 자료를 담았습니다. 핵심은 {focus_short}입니다.",
    "{region_line} 기준 {grade_subject} 페이지입니다. {focus_short}을 살펴보고 현재 학습 상황에 맞는지 판단해 보세요.",
    "{title} 상담 전 확인할 내용입니다. {scenario_short}을 기준으로 교재·오답·주간 계획을 어떻게 볼지 정리했습니다.",
    "{title}에서 다루는 지역·학년·과목 정보와 상담 질문을 모았습니다. {focus_short}이 필요한 학생에게 참고가 됩니다.",
)


INTENT_INTROS = (
    "{region_line}에서 {topic}을 비교하고 있다면 먼저 학생이 {scenario}인지 살펴보세요. 상담에서는 {focus}부터 확인하는 편이 좋습니다.",
    "{title}을 알아볼 때 수업 횟수보다 앞서 볼 것은 학생의 현재 학습 흐름입니다. {scenario}이라면 {focus}을 상담의 첫 기준으로 삼을 수 있습니다.",
    "{region_line}의 학원 정보를 찾는 학부모라면 교재 이름만 비교하기보다 학생 상황을 구체화할 필요가 있습니다. {scenario}에게는 {focus}이 우선입니다.",
    "{title} 선택은 점수 한 번만으로 결정하기 어렵습니다. 현재 모습이 {scenario}에 가깝다면 {focus}을 먼저 확인해 보세요.",
    "{region_line}에서 {grade_subject} 수업을 알아보는 경우, 아이가 실제로 막히는 지점을 상담 전에 정리하면 비교가 쉬워집니다. 특히 {scenario}에게는 {focus}이 중요합니다.",
    "{title} 상담의 출발점은 많은 문제를 푸는지가 아니라 무엇이 아직 연결되지 않았는지 찾는 일입니다. {scenario}이라면 {focus}을 질문해 보세요.",
    "{region_line} 학원 선택 전에는 학생의 공부 시간과 결과 사이의 차이를 살펴볼 필요가 있습니다. {scenario}에게 필요한 확인 항목은 {focus}입니다.",
    "{title} 페이지에서는 지역 정보와 함께 학생 상황에 맞는 상담 기준을 제시합니다. {scenario}이라면 {focus}이 실제 관리에 포함되는지 확인하세요.",
    "{region_line}에서 학원을 찾을 때 가까운 거리만큼 중요한 것이 현재 학습 문제와 관리 방식의 일치입니다. {scenario}에게는 {focus}이 핵심 확인점입니다.",
    "{title}을 비교하기 전 최근 교재와 평가 자료에서 반복되는 모습을 찾아보세요. {scenario}에 해당한다면 {focus}을 우선 상담하는 것이 좋습니다.",
    "{region_line}의 {grade_subject} 안내를 살펴보는 단계라면 목표를 막연히 정하기보다 현재 문제를 먼저 좁혀야 합니다. {scenario}에게는 {focus}이 필요합니다.",
    "{title} 상담에서는 학생에게 필요한 관리가 진도인지, 복습인지, 습관인지부터 구분해야 합니다. {scenario}이라면 {focus}을 중심으로 질문해 보세요.",
)


SUMMARY_INTROS = (
    "{title}의 지역·학년·과목 정보를 바탕으로 상담에서 확인할 학습 범위를 정리했습니다. 페이지에 등록된 센터 정보도 함께 확인할 수 있습니다.",
    "{region_line} 기준으로 {grade_subject} 학습 범위와 센터 참고 정보를 한눈에 볼 수 있도록 묶었습니다. 없는 지역 사실은 임의로 덧붙이지 않았습니다.",
    "{title}에서 확인 가능한 수업 대상과 학습 초점을 요약했습니다. 학교·주소·등록 정보는 현재 페이지에 표시된 내용만 사용했습니다.",
    "{region_line}에서 {topic}을 알아보는 학부모를 위해 학년 범위, 관리 과목, 센터 정보를 구분해 정리했습니다.",
    "{title} 상담에 필요한 기본 정보를 지역과 학생 단계에 맞춰 요약했습니다. 아래 내용은 페이지에 확인된 자료를 기준으로 합니다.",
    "{grade_subject} 학습에서 먼저 볼 부분과 {region_line} 센터 참고 정보를 나누어 확인할 수 있습니다. 실제 페이지에 없는 사실은 포함하지 않았습니다.",
    "{title}의 핵심은 지역명 반복이 아니라 학생 단계와 과목별 확인 기준을 분명히 하는 데 있습니다. 확인된 센터 정보도 함께 표시합니다.",
    "{region_line} 페이지에 등록된 자료를 토대로 학습 대상, 과목 범위, 상담 기준을 짧게 정리했습니다.",
    "{title}을 찾는 과정에서 필요한 학년·과목·센터 정보를 한곳에 모았습니다. 학생 상황에 따라 달라질 부분은 상담 질문으로 남겼습니다.",
    "{region_line}의 {grade_subject} 안내를 학생 상황, 학습 초점, 센터 참고 정보로 나누었습니다. 현재 페이지의 사실 정보만 반영했습니다.",
    "{title} 페이지에서 길게 흩어진 정보를 학부모가 비교하기 쉬운 기준으로 다시 정리했습니다. 지역 센터 자료도 함께 확인하세요.",
    "{region_line}의 수업 정보를 학년과 과목 중심으로 요약했습니다. 학교와 센터 관련 내용은 등록된 범위 안에서만 안내합니다.",
)


ANSWER_INTROS = (
    "상담에서는 “현재 가장 먼저 바꿀 한 가지가 무엇인지”부터 물어보세요. {question}라는 질문으로 계획과 관리 방식을 구체적으로 확인할 수 있습니다.",
    "학생에게 맞는지 판단하려면 설명을 듣는 것에서 끝내지 말고 확인 방법을 질문해야 합니다. 첫 질문은 “{question}”가 좋습니다.",
    "최근 교재와 평가 자료를 준비한 뒤 상담 목표를 한 문장으로 정리해 보세요. 이어서 “{question}”라고 물으면 관리 기준을 비교하기 쉽습니다.",
    "상담 답변은 구체적인 자료와 확인 주기가 있을수록 판단하기 쉽습니다. “{question}”라는 질문을 중심으로 들어보세요.",
    "우리 아이에게 필요한 수업인지 보려면 현재 문제와 다음 행동이 연결되어야 합니다. “{question}”라는 질문으로 그 흐름을 확인하세요.",
    "수업 방식보다 학생의 변화 과정을 어떻게 기록하는지 확인해 보세요. 상담에서 “{question}”라고 물으면 구체적인 답을 들을 수 있습니다.",
    "학습 목표를 점수 하나로만 두지 말고 완료할 행동으로 바꾸어 질문하는 것이 좋습니다. 예를 들어 “{question}”라고 확인해 보세요.",
    "학원 비교 시에는 같은 질문을 여러 곳에 해보면 차이가 분명해집니다. 이 페이지에서는 “{question}”를 첫 질문으로 제안합니다.",
    "학생의 현재 자료를 기준으로 답할 수 있는지를 살펴보세요. “{question}”라는 질문에 대한 설명이 구체적인지 확인하면 됩니다.",
    "상담 후 무엇을 집에서 확인해야 하는지도 함께 물어보는 것이 좋습니다. 먼저 “{question}”라는 질문으로 관리 범위를 좁혀보세요.",
    "진도, 복습, 습관 중 무엇을 우선할지 정한 다음 관리 방법을 비교하세요. “{question}”라고 물으면 판단 기준을 세우기 쉽습니다.",
    "상담에서 제시하는 계획이 학생의 현재 자료와 연결되는지 확인해야 합니다. “{question}”라는 질문으로 시작해 보세요.",
)


@dataclass(frozen=True)
class ChecklistItem:
    label: str
    text: str

    @property
    def schema_name(self) -> str:
        return f"{self.label}: {self.text}"


@dataclass
class PageFacts:
    path: Path
    relative: str
    region: str
    district: str
    neighborhood: str
    child_slug: str
    title: str
    grade: str
    subjects: str
    topic: str
    address: str = ""
    center_name: str = ""
    registration_name: str = ""
    registration_number: str = ""
    tuition_url: str = ""
    schools: dict[str, list[str]] = field(default_factory=dict)
    available_grades: dict[str, list[str]] = field(default_factory=dict)
    article_sentences: list[str] = field(default_factory=list)

    @property
    def is_child(self) -> bool:
        return bool(self.child_slug)

    @property
    def region_line(self) -> str:
        return f"{self.region} {self.district} {self.neighborhood}"

    @property
    def grade_subject(self) -> str:
        grade = f"{self.grade} " if self.grade != "전체" else "초등·중등·고등 "
        return f"{grade}{self.subjects}".strip()

    @property
    def relevant_school_level(self) -> str:
        return {
            "초등": "초등",
            "중등": "중등",
            "고등": "고등",
        }.get(self.grade, "")

    def relevant_schools(self) -> list[str]:
        if self.relevant_school_level:
            return self.schools.get(self.relevant_school_level, [])
        all_schools: list[str] = []
        for level in ("초등", "중등", "고등"):
            all_schools.extend(self.schools.get(level, []))
        return unique_preserving_order(all_schools)


@dataclass
class PagePlan:
    facts: PageFacts
    old_source: str
    new_source: str
    old_description: str
    new_description: str
    block_html: str
    checklist: list[ChecklistItem]
    scenario: str
    focus: str
    issues: list[str] = field(default_factory=list)

    @property
    def changed(self) -> bool:
        return self.old_source != self.new_source


def stable_index(key: str, salt: str, size: int) -> int:
    if size <= 0:
        raise ValueError("선택할 항목이 없습니다.")
    digest = hashlib.sha256(f"{salt}\0{key}".encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") % size


def stable_pick(items: Sequence[str], key: str, salt: str) -> str:
    return items[stable_index(key, salt, len(items))]


def stable_rotated(items: Sequence[ChecklistItem], key: str, salt: str) -> list[ChecklistItem]:
    if not items:
        return []
    start = stable_index(key, salt, len(items))
    return list(items[start:]) + list(items[:start])


def clean_text(value: str) -> str:
    value = re.sub(r"<script\b.*?</script>", " ", value or "", flags=re.I | re.S)
    value = re.sub(r"<style\b.*?</style>", " ", value, flags=re.I | re.S)
    value = re.sub(r"<[^>]+>", " ", value, flags=re.S)
    return re.sub(r"\s+", " ", html.unescape(value)).strip()


def unique_preserving_order(values: Iterable[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        value = re.sub(r"\s+", " ", value).strip()
        if value and value not in seen:
            result.append(value)
            seen.add(value)
    return result


def first_match(source: str, pattern: str, default: str = "") -> str:
    match = re.search(pattern, source, flags=re.I | re.S)
    return clean_text(match.group(1)) if match else default


def page_targets(root: Path) -> list[Path]:
    national_root = root / "전국학원"
    targets: list[Path] = []
    for path in national_root.rglob("index.html"):
        parts = path.relative_to(national_root).parts[:-1]
        if len(parts) in {3, 4}:
            targets.append(path)
    return sorted(targets, key=lambda p: p.relative_to(root).as_posix())


def grade_from_title(title: str) -> str:
    if "고등" in title:
        return "고등"
    if "중등" in title:
        return "중등"
    if "초등" in title:
        return "초등"
    return "전체"


def subjects_from_title(title: str, is_child: bool) -> str:
    if "영수" in title:
        return "영어·수학"
    found = [subject for subject in ("국어", "영어", "수학") if subject in title]
    if found:
        return "·".join(found)
    return "영어·수학" if is_child else "국어·영어·수학"


def topic_from_title(title: str, neighborhood: str) -> str:
    topic = title
    if topic.startswith(neighborhood):
        topic = topic[len(neighborhood) :].strip()
    return topic or "학원"


def extract_school_groups(source: str) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {"초등": [], "중등": [], "고등": []}
    card_pattern = re.compile(
        r'<article\b[^>]*class=["\'][^"\']*\bwawa-school-card\b[^"\']*["\'][^>]*>'
        r"(.*?)</article>",
        flags=re.I | re.S,
    )
    for card_match in card_pattern.finditer(source):
        card = card_match.group(1)
        heading = first_match(card, r"<h3\b[^>]*>(.*?)</h3>")
        level = next((value for value in ("초등", "중등", "고등") if value in heading), "")
        if not level:
            continue
        pills = re.findall(
            r'<span\b[^>]*class=["\'][^"\']*\bwawa-pill\b[^"\']*["\'][^>]*>(.*?)</span>',
            card,
            flags=re.I | re.S,
        )
        values = [
            clean_text(value)
            for value in pills
            if clean_text(value) and "정보 준비중" not in clean_text(value)
        ]
        result[level] = unique_preserving_order(values)
    return result


def extract_available_grades(source: str) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    starts = list(
        re.finditer(
            r'<div\b[^>]*class=["\'][^"\']*\bwawa-grade-row\b[^"\']*["\'][^>]*>',
            source,
            flags=re.I,
        )
    )
    for index, match in enumerate(starts):
        end = starts[index + 1].start() if index + 1 < len(starts) else source.find("</section>", match.end())
        if end == -1:
            end = min(len(source), match.end() + 4_000)
        chunk = source[match.start() : end]
        subject = first_match(
            chunk,
            r'<div\b[^>]*class=["\'][^"\']*\bwawa-grade-subject\b[^"\']*["\'][^>]*>(.*?)</div>',
        )
        if not subject:
            continue
        grades = [
            clean_text(value)
            for value in re.findall(
                r'<span\b[^>]*class=["\'][^"\']*\bwawa-pill\b[^"\']*["\'][^>]*>(.*?)</span>',
                chunk,
                flags=re.I | re.S,
            )
        ]
        grades = [grade for grade in grades if grade in GRADE_ORDER]
        if grades:
            result[subject] = unique_preserving_order(grades)
    return result


def extract_article_sentences(source: str) -> list[str]:
    start = source.find('<section class="article-main">')
    end = source.find('<section class="generated-support-section"', start)
    if start == -1:
        return []
    if end == -1:
        end = source.find(SEO_START, start)
    if end == -1:
        end = min(len(source), start + 30_000)
    article = source[start:end]
    values: list[str] = []
    for value in re.findall(r"<(?:p|li)\b[^>]*>(.*?)</(?:p|li)>", article, flags=re.I | re.S):
        text = clean_text(value)
        if 24 <= len(text) <= 180 and "정보 준비중" not in text:
            values.append(text)
    return unique_preserving_order(values)


def extract_facts(path: Path, root: Path, source: str) -> PageFacts:
    relative_parts = path.relative_to(root / "전국학원").parts[:-1]
    if len(relative_parts) not in {3, 4}:
        raise ValueError(f"대상 깊이가 아닙니다: {path}")
    region, district, neighborhood = relative_parts[:3]
    child_slug = relative_parts[3] if len(relative_parts) == 4 else ""
    title = first_match(source, r"<h1\b[^>]*>(.*?)</h1>")
    if not title:
        title = f"{neighborhood} {child_slug or '학원'}".strip()

    address = first_match(
        source,
        r'<span\b[^>]*class=["\'][^"\']*\bwawa-label\b[^"\']*["\'][^>]*>\s*주소\s*</span>'
        r'\s*<p\b[^>]*class=["\'][^"\']*\bwawa-text\b[^"\']*["\'][^>]*>(.*?)</p>',
    )
    center_name = first_match(
        source,
        r'<section\b[^>]*class=["\'][^"\']*\bwawa-center-snippet\b[^"\']*["\'][^>]*'
        r'aria-label=["\'](.*?)\s+센터 안내["\']',
    )
    registration_name = first_match(
        source,
        r'<p\b[^>]*class=["\'][^"\']*\bwawa-register-line\b[^"\']*["\'][^>]*>'
        r"\s*<strong>\s*교육지원청\s*</strong>\s*:\s*(.*?)</p>",
    )
    registration_number = first_match(
        source,
        r'<p\b[^>]*class=["\'][^"\']*\bwawa-register-line\b[^"\']*["\'][^>]*>'
        r"\s*<strong>\s*등록번호\s*</strong>\s*:\s*(.*?)</p>",
    )
    tuition_url_match = re.search(
        r'<a\b[^>]*class=["\'][^"\']*\bwawa-tuition-link\b[^"\']*["\'][^>]*'
        r'href=["\']([^"\']+)["\']',
        source,
        flags=re.I | re.S,
    )
    tuition_url = html.unescape(tuition_url_match.group(1)).strip() if tuition_url_match else ""

    return PageFacts(
        path=path,
        relative=path.relative_to(root).as_posix(),
        region=region,
        district=district,
        neighborhood=neighborhood,
        child_slug=child_slug,
        title=title,
        grade=grade_from_title(title),
        subjects=subjects_from_title(title, bool(child_slug)),
        topic=topic_from_title(title, neighborhood),
        address=address if "정보 준비중" not in address else "",
        center_name=center_name if "정보 준비중" not in center_name else "",
        registration_name=registration_name if "정보 준비중" not in registration_name else "",
        registration_number=registration_number if "정보 준비중" not in registration_number else "",
        tuition_url=tuition_url,
        schools=extract_school_groups(source),
        available_grades=extract_available_grades(source),
        article_sentences=extract_article_sentences(source),
    )


def grade_pool(facts: PageFacts, source: dict[str, tuple[str, ...]]) -> tuple[str, ...]:
    return source.get(facts.grade, source["전체"])


def shorten_phrase(value: str, max_chars: int = 42) -> str:
    value = value.strip().rstrip(".")
    if len(value) <= max_chars:
        return value
    pieces = re.split(r"[,·]|(?:하고|하며|해서|하여|해야)\s", value)
    for piece in pieces:
        piece = piece.strip()
        if 12 <= len(piece) <= max_chars:
            return piece
    return value[: max_chars - 1].rstrip() + "…"


def grade_span(grades: Sequence[str]) -> str:
    ordered = sorted(unique_preserving_order(grades), key=lambda value: GRADE_ORDER.get(value, 999))
    if not ordered:
        return ""
    if len(ordered) == 1:
        return ordered[0]
    positions = [GRADE_ORDER[value] for value in ordered if value in GRADE_ORDER]
    contiguous = all(
        (right - left == 1) or (left in {6, 13} and right in {11, 21})
        for left, right in zip(positions, positions[1:])
    )
    if contiguous:
        return f"{ordered[0]}~{ordered[-1]}"
    return "·".join(ordered[:6]) + (" 등" if len(ordered) > 6 else "")


def relevant_grade_fact(facts: PageFacts) -> str:
    subject_names = [name for name in ("국어", "영어", "수학") if name in facts.subjects]
    if not subject_names:
        subject_names = [name for name in ("영어", "수학") if name in facts.available_grades]
    fragments: list[str] = []
    for subject in subject_names:
        grades = facts.available_grades.get(subject, [])
        if grades:
            fragments.append(f"{subject} {grade_span(grades)}")
    return ", ".join(fragments[:3])


def actual_fact_text(facts: PageFacts, key: str) -> tuple[str, str]:
    schools = facts.relevant_schools()
    if schools:
        shown = "·".join(schools[:3])
        return (
            "학교 참고",
            f"페이지의 {facts.relevant_school_level or '학년별'} 학교 정보에는 {shown}"
            f"{' 등이' if len(schools) > 3 else '이'} 표시되어 있습니다.",
        )
    grades = relevant_grade_fact(facts)
    if grades:
        return ("수강 학년", f"{facts.title} 페이지에는 수강 가능 학년이 {grades}로 안내되어 있습니다.")
    if facts.registration_number:
        return ("등록 정보", f"페이지에 안내된 등록번호는 {facts.registration_number}입니다.")
    if facts.address:
        return ("센터 위치", f"방문 위치는 {facts.address}로 안내되어 있습니다.")
    if facts.center_name:
        return ("센터 안내", f"{facts.center_name} 관련 수업 정보를 기준으로 확인합니다.")
    return (
        "지역 상담",
        f"{facts.region_line} 학생의 현재 학교·교재·진도는 상담에서 개별 확인합니다.",
    )


def local_summary_text(facts: PageFacts, key: str) -> str:
    schools = facts.relevant_schools()
    variants: list[str] = []
    if schools:
        shown = "·".join(schools[:2])
        variants.append(f"{facts.relevant_school_level or '학년별'} 학교 참고 정보에 {shown}이 포함되어 있습니다.")
    if facts.address:
        variants.append(f"센터 위치는 {facts.address}로 안내되어 있습니다.")
    if facts.registration_number:
        variants.append(f"등록번호 {facts.registration_number}가 페이지에 표시되어 있습니다.")
    grades = relevant_grade_fact(facts)
    if grades:
        variants.append(f"수강 가능 학년 정보에는 {grades}가 표시되어 있습니다.")
    if facts.tuition_url:
        variants.append("현재 페이지에서 센터 교습비 안내 링크를 확인할 수 있습니다.")
    if not variants:
        variants.append(f"{facts.region_line}의 학교·교재·진도는 상담에서 학생별로 확인합니다.")
    return stable_pick(tuple(variants), key, "local-summary")


def center_detail_text(facts: PageFacts) -> str:
    """페이지에 실제로 적힌 센터 사실만 짧게 연결한다."""
    fragments: list[str] = []
    if facts.center_name:
        fragments.append(f"센터명은 {facts.center_name}으로 안내되어 있습니다")
    if facts.address:
        fragments.append(f"주소는 {facts.address}입니다")
    if facts.registration_number:
        fragments.append(f"등록번호는 {facts.registration_number}로 표시되어 있습니다")
    if facts.tuition_url:
        fragments.append("교습비 안내 링크도 페이지에서 확인할 수 있습니다")
    if not fragments:
        return f"{facts.region_line}의 방문 위치와 등록 정보는 상담 전에 개별 확인해 주세요."
    return ". ".join(fragments[:3]).rstrip(".") + "."


def school_and_grade_text(facts: PageFacts) -> str:
    """타깃학교와 가능 학년이 있으면 그대로 쓰고, 없으면 확인 필요성을 명시한다."""
    fragments: list[str] = []
    schools = facts.relevant_schools()
    if schools:
        shown = "·".join(schools[:3])
        suffix = " 등이" if len(schools) > 3 else "이"
        fragments.append(
            f"{facts.relevant_school_level or '학년별'} 학교 참고 정보에는 {shown}{suffix} 포함되어 있습니다"
        )
    grades = relevant_grade_fact(facts)
    if grades:
        fragments.append(f"{facts.title}의 수강 가능 학년은 {grades}로 표시되어 있습니다")
    if not fragments:
        return (
            "구체 학교나 가능 학년이 페이지에 등록되지 않은 경우에는 "
            "현재 학교·학년·진도를 상담에서 먼저 확인합니다."
        )
    return ". ".join(fragments).rstrip(".") + "."


def build_description(facts: PageFacts, scenario: str, focus: str, key: str) -> str:
    values = {
        "title": facts.title,
        "region_line": facts.region_line,
        "grade_subject": facts.grade_subject,
        # 현재 문구 뱅크의 학생 상황은 최대 46자, 학습 초점은 최대 41자다.
        # 이를 중간에서 자르면 “학생…이라면”처럼 부자연스러운 메타 설명이
        # 생기므로 각각 완결된 문장 성분을 그대로 사용한다.
        "scenario_short": shorten_phrase(scenario, 50),
        "focus_short": shorten_phrase(focus, 45),
    }
    start = stable_index(key, "meta-pattern", len(META_PATTERNS))
    candidates = list(META_PATTERNS[start:]) + list(META_PATTERNS[:start])
    descriptions = [pattern.format(**values) for pattern in candidates]
    selected = next((value for value in descriptions if 70 <= len(value) <= 120), "")
    if not selected:
        selected = min(descriptions, key=lambda value: abs(len(value) - 95))
    return re.sub(r"\s+", " ", selected).strip()


def build_checklist(facts: PageFacts, scenario: str, focus: str, key: str) -> list[ChecklistItem]:
    grade_specific = {
        "초등": ChecklistItem(
            "기초 확인",
            f"{facts.title} 상담을 위해 최근 단원평가나 학습지에서 읽기·계산이 막힌 지점을 표시합니다.",
        ),
        "중등": ChecklistItem(
            "학교 시험",
            f"{facts.title} 상담 전에 최근 시험지와 시험 범위를 준비해 개념·서술형·시간 부족 오답을 나눕니다.",
        ),
        "고등": ChecklistItem(
            "내신·모의",
            f"{facts.title} 상담 자료로 최근 내신 시험지와 모의고사에서 취약 단원과 시간 부족 문항을 구분합니다.",
        ),
        "전체": ChecklistItem(
            "최근 평가",
            f"{facts.title} 상담에 활용할 시험지나 단원평가에서 반복 오답과 어려운 단원을 확인합니다.",
        ),
    }[facts.grade]

    subject_item = (
        ChecklistItem(
            "과목 균형",
            f"{facts.title}의 {facts.subjects} 관리 기준을 잡기 위해 최근 일주일의 과목별 공부 시간을 살펴봅니다.",
        )
        if "·" in facts.subjects
        else ChecklistItem(
            "과목 자료",
            f"{facts.title} 상담 전에 {facts.subjects} 교재의 현재 진도와 다시 풀어야 할 문제를 표시합니다.",
        )
    )
    generic = [
        grade_specific,
        subject_item,
        ChecklistItem("현재 교재", f"사용 중인 교재에서 {shorten_phrase(focus, 48)}과 관련된 범위를 표시합니다."),
        ChecklistItem(
            "공부 기록",
            f"{facts.title} 상담에서 실행 습관을 설명할 수 있도록 평일·주말의 시작 시간과 미완료 이유를 적습니다.",
        ),
        ChecklistItem(
            "숙제 흐름",
            f"{facts.title}의 관리 방향을 정하기 위해 숙제 완료와 채점·재풀이 완료를 구분해 기록합니다.",
        ),
        ChecklistItem("상담 목표", f"{shorten_phrase(scenario, 50)} 상황에서 가장 먼저 바꿀 한 가지를 정합니다."),
        ChecklistItem(
            "질문 준비",
            f"{facts.title} 상담 질문으로 "
            f"{stable_pick(grade_pool(facts, CONSULT_QUESTIONS), key, 'checklist-question')}",
        ),
        ChecklistItem(
            "복습 간격",
            f"{facts.title} 상담 자료에 수업 내용을 다시 본 날짜와 혼자 풀리지 않은 문제를 표시합니다.",
        ),
    ]

    actual: list[ChecklistItem] = []
    schools = facts.relevant_schools()
    if schools:
        shown = "·".join(schools[:3])
        actual.append(
            ChecklistItem(
                "학교 자료",
                f"{shown}{' 등' if len(schools) > 3 else ''}의 현재 진도나 시험 자료가 있다면 함께 준비합니다.",
            )
        )
    grades = relevant_grade_fact(facts)
    if grades:
        actual.append(
            ChecklistItem(
                "가능 학년",
                f"{facts.title} 페이지에 표시된 {grades} 범위와 학생의 현재 학년을 대조합니다.",
            )
        )
    if facts.address:
        actual.append(ChecklistItem("방문 동선", f"상담 전 센터 주소({facts.address})와 이동 시간을 확인합니다."))
    if facts.tuition_url:
        actual.append(
            ChecklistItem(
                "교습비 확인",
                f"{facts.title} 페이지의 교습비 안내 링크에서 횟수별 기준을 확인하고 상담 내용과 비교합니다.",
            )
        )
    if facts.registration_number:
        actual.append(ChecklistItem("등록 정보", f"페이지에 표시된 등록번호({facts.registration_number})를 확인합니다."))

    selected: list[ChecklistItem] = []
    if actual:
        selected.append(stable_pick_checklist(actual, key, "checklist-actual"))
    for item in stable_rotated(generic, key, "checklist-generic"):
        if item.label not in {existing.label for existing in selected}:
            selected.append(item)
        if len(selected) == 4:
            break
    return selected


def stable_pick_checklist(items: Sequence[ChecklistItem], key: str, salt: str) -> ChecklistItem:
    return items[stable_index(key, salt, len(items))]


def build_block(
    facts: PageFacts,
    scenario: str,
    focus: str,
    checklist: list[ChecklistItem],
    key: str,
) -> str:
    base_question = stable_pick(grade_pool(facts, CONSULT_QUESTIONS), key, "consult-question")
    question = f"{facts.title} 상담에서는 {base_question[0].lower() + base_question[1:]}"
    values = {
        "title": facts.title,
        "topic": facts.topic,
        "region_line": facts.region_line,
        "grade_subject": facts.grade_subject,
        "scenario": scenario,
        "focus": focus,
        "question": question,
    }
    intent_intro = stable_pick(INTENT_INTROS, key, "intent-intro").format(**values)
    answer_intro = stable_pick(ANSWER_INTROS, key, "answer-intro").format(**values)
    center_detail = center_detail_text(facts)
    school_grade_detail = school_and_grade_text(facts)

    checklist_html = "\n".join(
        f'    <li><b>{html.escape(item.label)}</b><span>{html.escape(item.text)}</span></li>'
        for item in checklist
    )
    checklist_lead = stable_pick(
        (
            f"{facts.title} 상담에서는 전부 준비하기보다 현재 어려움을 설명할 자료부터 골라 확인하세요.",
            f"{facts.region_line}에서 상담을 준비할 때는 아래 자료 중 학생의 최근 학습 흐름을 보여주는 항목을 우선하면 됩니다.",
            f"{facts.grade_subject} 학습 상태를 정확히 설명할 수 있는 자료부터 준비하면 {facts.title} 상담을 구체적으로 진행하기 좋습니다.",
            f"아래 항목은 {facts.title} 상담에 활용할 수 있는 자료입니다. 학생에게 해당하는 내용만 선택해도 충분합니다.",
            f"{facts.neighborhood} 학생의 현재 진도와 습관을 보여주는 기록을 중심으로 준비하고, 없는 자료를 새로 만들 필요는 없습니다.",
            f"{facts.title} 상담 전에는 최근 교재·평가·공부 기록 가운데 실제 학습 상태를 잘 보여주는 자료를 선택하세요.",
        ),
        key,
        "checklist-lead",
    )

    return f"""{SEO_START}
<section class="seo-answer-section" aria-labelledby="seo-intent-title">
  <div class="seo-answer-copy">
    <p class="parent-faq-eyebrow">{PARENT_FACING_LABELS['answer']}</p>
    <h2 id="seo-intent-title">{html.escape(facts.title)}, 학생 상황과 센터 정보를 함께 확인하세요</h2>
    <p>{html.escape(intent_intro)} {html.escape(answer_intro)}</p>
  </div>
  <div class="seo-answer-list">
    <article><b>학생 상황</b><p>{html.escape(scenario)}</p></article>
    <article><b>학년·과목</b><p>{html.escape(facts.grade_subject)} 기준으로 {html.escape(focus)}</p></article>
    <article><b>학교·가능 학년</b><p>{html.escape(school_grade_detail)}</p></article>
    <article><b>센터 확인</b><p>{html.escape(center_detail)}</p></article>
    <article><b>첫 질문</b><p>{html.escape(question)}</p></article>
  </div>
</section>

<section class="seo-checklist-section" aria-labelledby="seo-checklist-title">
  <div class="seo-geo-head">
    <p class="parent-faq-eyebrow">{PARENT_FACING_LABELS['checklist']}</p>
    <h2 id="seo-checklist-title">{html.escape(facts.title)} 상담 전에 준비할 자료</h2>
    <p>{html.escape(checklist_lead)}</p>
  </div>
  <ol class="seo-checklist">
{checklist_html}
  </ol>
</section>
{SEO_END}"""


def extract_meta_content(source: str, attr_name: str, attr_value: str) -> str:
    for match in re.finditer(r"<meta\b[^>]*>", source, flags=re.I | re.S):
        tag = match.group(0)
        attrs = {
            key.lower(): html.unescape(value)
            for key, _, value in re.findall(
                r'([:\w-]+)\s*=\s*(["\'])(.*?)\2',
                tag,
                flags=re.I | re.S,
            )
        }
        if attrs.get(attr_name.lower(), "").lower() == attr_value.lower():
            return attrs.get("content", "")
    return ""


def replace_meta_content(source: str, attr_name: str, attr_value: str, content: str) -> tuple[str, bool]:
    escaped = html.escape(content, quote=True)
    changed = False

    def replace_tag(match: re.Match[str]) -> str:
        nonlocal changed
        tag = match.group(0)
        attrs = {
            key.lower(): html.unescape(value)
            for key, _, value in re.findall(
                r'([:\w-]+)\s*=\s*(["\'])(.*?)\2',
                tag,
                flags=re.I | re.S,
            )
        }
        if attrs.get(attr_name.lower(), "").lower() != attr_value.lower():
            return tag
        content_pattern = re.compile(r'(content\s*=\s*)(["\'])(.*?)\2', flags=re.I | re.S)
        if not content_pattern.search(tag):
            return tag
        changed = True
        return content_pattern.sub(lambda m: f"{m.group(1)}{m.group(2)}{escaped}{m.group(2)}", tag, count=1)

    return re.sub(r"<meta\b[^>]*>", replace_tag, source, flags=re.I | re.S), changed


def replace_enhancement_block(source: str, block: str) -> tuple[str, bool]:
    pattern = re.compile(re.escape(SEO_START) + r".*?" + re.escape(SEO_END), flags=re.S)
    matches = list(pattern.finditer(source))
    if len(matches) != 1:
        return source, False
    return pattern.sub(lambda _match: block, source, count=1), True


def node_has_type(node: dict[str, Any], wanted: str) -> bool:
    value = node.get("@type")
    return wanted in value if isinstance(value, list) else value == wanted


def graph_nodes(data: Any) -> list[dict[str, Any]]:
    if not isinstance(data, dict):
        return []
    graph = data.get("@graph")
    if isinstance(graph, list):
        return [node for node in graph if isinstance(node, dict)]
    return [data]


def updated_article_sections(existing: Any) -> list[str]:
    replacements = {
        "검색의도 요약": "학원 선택 핵심 안내",
        "핵심 요약": "학원 선택 핵심 안내",
        "지역·학년·추천학생": "학원 선택 핵심 안내",
        "지역·학년·추천학생 안내": "학원 선택 핵심 안내",
        "답변형 학습 안내": "학원 선택 핵심 안내",
        "상담 전 체크리스트": "상담 준비 자료",
        "학원 선택 전 첫 확인": "학원 선택 핵심 안내",
        "한눈에 보는 수업 정보": "학원 선택 핵심 안내",
        "학생 상황과 수업 범위": "학원 선택 핵심 안내",
        "상담에서 확인할 내용": "학원 선택 핵심 안내",
        "상담 준비": "상담 준비 자료",
    }
    values = existing if isinstance(existing, list) else [existing] if isinstance(existing, str) else []
    result = [replacements.get(value, value) for value in values if isinstance(value, str)]
    required = [
        "학원 선택 핵심 안내",
        "상담 준비 자료",
    ]
    return unique_preserving_order([*required, *result])


def update_has_part(existing: Any) -> Any:
    if not isinstance(existing, list):
        return existing
    replacements = {
        "검색의도 요약": "학원 선택 핵심 안내",
        "핵심 요약": "학원 선택 핵심 안내",
        "답변형 학습 안내": "학원 선택 핵심 안내",
        "지역·학년·추천학생 안내": "학원 선택 핵심 안내",
        "학원 선택 전 첫 확인": "학원 선택 핵심 안내",
        "한눈에 보는 수업 정보": "학원 선택 핵심 안내",
        "학생 상황과 수업 범위": "학원 선택 핵심 안내",
        "상담에서 확인할 내용": "학원 선택 핵심 안내",
        "상담 전 체크리스트": "상담 준비 자료",
        "상담 준비": "상담 준비 자료",
    }
    result = copy.deepcopy(existing)
    for item in result:
        if isinstance(item, dict) and isinstance(item.get("name"), str):
            item["name"] = replacements.get(item["name"], item["name"])
    deduplicated: list[Any] = []
    seen_names: set[str] = set()
    for item in result:
        if isinstance(item, dict) and isinstance(item.get("name"), str):
            name = item["name"]
            if name in seen_names:
                continue
            seen_names.add(name)
        deduplicated.append(item)
    return deduplicated


def update_jsonld(
    source: str,
    facts: PageFacts,
    description: str,
    checklist: list[ChecklistItem],
) -> tuple[str, int, list[str]]:
    errors: list[str] = []
    changed_scripts = 0
    script_pattern = re.compile(
        r'(<script\b[^>]*type=["\']application/ld\+json["\'][^>]*>)(.*?)(</script>)',
        flags=re.I | re.S,
    )

    def replace_script(match: re.Match[str]) -> str:
        nonlocal changed_scripts
        try:
            data = json.loads(match.group(2))
        except json.JSONDecodeError as exc:
            errors.append(f"JSON-LD 파싱 오류: {exc}")
            return match.group(0)

        touched = False
        for node in graph_nodes(data):
            if node_has_type(node, "WebPage"):
                node["description"] = description
                if "hasPart" in node:
                    node["hasPart"] = update_has_part(node["hasPart"])
                touched = True
            if node_has_type(node, "Article"):
                node["description"] = description
                node["articleSection"] = updated_article_sections(node.get("articleSection"))
                if "hasPart" in node:
                    node["hasPart"] = update_has_part(node["hasPart"])
                touched = True
            if node_has_type(node, "Service"):
                node["description"] = (
                    f"{facts.region_line} 학생을 위한 {facts.grade_subject} 학습 상담 안내입니다. "
                    f"{shorten_phrase(stable_pick(grade_pool(facts, LEARNING_FOCUS), facts.relative, 'service-focus'), 55)}"
                    "을 중심으로 현재 교재와 학습 흐름을 확인합니다."
                )
                touched = True
            if node_has_type(node, "ItemList") and (
                "#checklist" in str(node.get("@id", ""))
                or "체크리스트" in str(node.get("name", ""))
                or "상담 전 준비" in str(node.get("name", ""))
            ):
                node["name"] = f"{facts.title} 상담 전 준비할 내용"
                node["itemListElement"] = [
                    {
                        "@type": "ListItem",
                        "position": position,
                        "name": item.schema_name,
                    }
                    for position, item in enumerate(checklist, start=1)
                ]
                touched = True
        if not touched:
            return match.group(0)
        changed_scripts += 1
        serialized = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
        return f"{match.group(1)}{serialized}{match.group(3)}"

    return script_pattern.sub(replace_script, source), changed_scripts, errors


def structured_fingerprint(source: str, keys: set[str]) -> str:
    collected: list[Any] = []
    pattern = re.compile(
        r'<script\b[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        flags=re.I | re.S,
    )

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                if key in keys:
                    collected.append({key: child})
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    for match in pattern.finditer(source):
        try:
            walk(json.loads(match.group(1)))
        except json.JSONDecodeError:
            collected.append({"invalid_json": match.group(1)})
    payload = json.dumps(collected, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def visible_section_fingerprint(source: str, class_name: str) -> str:
    marker = re.search(
        rf'<section\b[^>]*class=["\'][^"\']*\b{re.escape(class_name)}\b[^"\']*["\'][^>]*>',
        source,
        flags=re.I,
    )
    if not marker:
        return hashlib.sha256(b"").hexdigest()
    next_section = source.find("<section", marker.end())
    end = next_section if next_section != -1 else len(source)
    payload = source[marker.start() : end]
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def stable_head_fingerprint(source: str) -> str:
    values = {
        "title": first_match(source, r"<title\b[^>]*>(.*?)</title>"),
        "h1": first_match(source, r"<h1\b[^>]*>(.*?)</h1>"),
        "canonical": extract_link_href(source, "canonical"),
        "og_url": extract_meta_content(source, "property", "og:url"),
    }
    return hashlib.sha256(
        json.dumps(values, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


def extract_link_href(source: str, rel_value: str) -> str:
    for match in re.finditer(r"<link\b[^>]*>", source, flags=re.I | re.S):
        tag = match.group(0)
        attrs = {
            key.lower(): html.unescape(value)
            for key, _, value in re.findall(
                r'([:\w-]+)\s*=\s*(["\'])(.*?)\2',
                tag,
                flags=re.I | re.S,
            )
        }
        if attrs.get("rel", "").lower() == rel_value.lower():
            return attrs.get("href", "")
    return ""


def facts_fingerprint(facts: PageFacts) -> str:
    payload = {
        "address": facts.address,
        "center_name": facts.center_name,
        "registration_name": facts.registration_name,
        "registration_number": facts.registration_number,
        "tuition_url": facts.tuition_url,
        "schools": facts.schools,
        "available_grades": facts.available_grades,
    }
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


def all_jsonld_valid(source: str) -> bool:
    matches = re.findall(
        r'<script\b[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        source,
        flags=re.I | re.S,
    )
    if not matches:
        return False
    try:
        for value in matches:
            json.loads(value)
    except json.JSONDecodeError:
        return False
    return True


def visible_checklist_names(source: str) -> list[str]:
    block_match = re.search(
        re.escape(SEO_START) + r"(.*?)" + re.escape(SEO_END),
        source,
        flags=re.S,
    )
    if not block_match:
        return []
    return [
        f"{clean_text(label)}: {clean_text(text)}"
        for label, text in re.findall(
            r"<li\b[^>]*>\s*<b\b[^>]*>(.*?)</b>\s*<span\b[^>]*>(.*?)</span>\s*</li>",
            block_match.group(1),
            flags=re.I | re.S,
        )
    ]


def schema_checklist_names(source: str) -> list[str]:
    for match in re.finditer(
        r'<script\b[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        source,
        flags=re.I | re.S,
    ):
        try:
            data = json.loads(match.group(1))
        except json.JSONDecodeError:
            continue
        for node in graph_nodes(data):
            if node_has_type(node, "ItemList") and (
                "#checklist" in str(node.get("@id", ""))
                or "상담 전 준비" in str(node.get("name", ""))
                or "체크리스트" in str(node.get("name", ""))
            ):
                return [
                    str(item.get("name", ""))
                    for item in node.get("itemListElement", [])
                    if isinstance(item, dict)
                ]
    return []


def transform_page(path: Path, root: Path) -> PagePlan:
    old_source = path.read_text(encoding="utf-8", errors="strict")
    facts = extract_facts(path, root, old_source)
    key = facts.relative
    scenario = stable_pick(grade_pool(facts, SCENARIOS), key, "scenario")
    focus = stable_pick(grade_pool(facts, LEARNING_FOCUS), key, "focus")
    checklist = build_checklist(facts, scenario, focus, key)
    description = build_description(facts, scenario, focus, key)
    block = build_block(facts, scenario, focus, checklist, key)

    issues: list[str] = []
    if old_source.count(SEO_START) != 1 or old_source.count(SEO_END) != 1:
        issues.append(
            f"개선 블록 마커 개수 오류(start={old_source.count(SEO_START)}, end={old_source.count(SEO_END)})"
        )

    new_source, replaced = replace_enhancement_block(old_source, block)
    if not replaced:
        issues.append("기존 개선 블록을 유일하게 찾지 못함")

    new_source, meta_found = replace_meta_content(new_source, "name", "description", description)
    if not meta_found:
        issues.append("meta description을 찾지 못함")
    new_source, og_found = replace_meta_content(new_source, "property", "og:description", description)
    if not og_found:
        issues.append("og:description을 찾지 못함")

    new_source, changed_scripts, jsonld_errors = update_jsonld(
        new_source,
        facts,
        description,
        checklist,
    )
    issues.extend(jsonld_errors)
    if changed_scripts == 0:
        issues.append("수정 가능한 JSON-LD 그래프를 찾지 못함")

    proposed_facts = extract_facts(path, root, new_source)
    if facts_fingerprint(facts) != facts_fingerprint(proposed_facts):
        issues.append("주소·학교·센터·등록 정보가 달라짐")
    if stable_head_fingerprint(old_source) != stable_head_fingerprint(new_source):
        issues.append("title/H1/canonical/og:url 중 하나가 달라짐")
    if visible_section_fingerprint(old_source, "parent-faq-section") != visible_section_fingerprint(
        new_source, "parent-faq-section"
    ):
        issues.append("화면 FAQ가 달라짐")
    if visible_section_fingerprint(old_source, "parent-review-section") != visible_section_fingerprint(
        new_source, "parent-review-section"
    ):
        issues.append("화면 후기가 달라짐")
    if structured_fingerprint(old_source, {"review", "aggregateRating"}) != structured_fingerprint(
        new_source, {"review", "aggregateRating"}
    ):
        issues.append("JSON-LD 후기 또는 평점이 달라짐")
    if structured_fingerprint(old_source, {"mainEntity"}) != structured_fingerprint(
        new_source, {"mainEntity"}
    ):
        # WebPage.mainEntity도 mainEntity 키를 사용하므로 전체 지문은 FAQ 보존 검사에 부적합하다.
        # 아래 FAQ 전용 지문이 실제 질문·답변 변경 여부를 판정한다.
        if faq_fingerprint(old_source) != faq_fingerprint(new_source):
            issues.append("JSON-LD FAQ가 달라짐")
    if not all_jsonld_valid(new_source):
        issues.append("수정 후 JSON-LD가 유효하지 않음")
    if any(label in block for label in OLD_PRODUCER_LABELS):
        issues.append("제작자용 영어 라벨이 새 블록에 남음")
    if len(re.findall(r"<section\b", block, flags=re.I)) != 2:
        issues.append("개선 블록이 핵심 안내 1개와 체크리스트 1개로 통합되지 않음")
    for fact_name, fact_value in (
        ("센터명", facts.center_name),
        ("주소", facts.address),
        ("타깃학교", facts.relevant_schools()[0] if facts.relevant_schools() else ""),
        ("가능학년", relevant_grade_fact(facts)),
    ):
        if fact_value and html.escape(fact_value) not in block:
            issues.append(f"확인된 {fact_name} 정보가 핵심 안내에서 누락됨")
    if visible_checklist_names(new_source) != schema_checklist_names(new_source):
        issues.append("화면 체크리스트와 ItemList가 일치하지 않음")
    if not 60 <= len(description) <= 130:
        issues.append(f"메타 설명 길이 범위 이탈({len(description)}자)")

    return PagePlan(
        facts=facts,
        old_source=old_source,
        new_source=new_source,
        old_description=extract_meta_content(old_source, "name", "description"),
        new_description=description,
        block_html=block,
        checklist=checklist,
        scenario=scenario,
        focus=focus,
        issues=issues,
    )


def faq_fingerprint(source: str) -> str:
    entities: list[Any] = []
    for match in re.finditer(
        r'<script\b[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        source,
        flags=re.I | re.S,
    ):
        try:
            data = json.loads(match.group(1))
        except json.JSONDecodeError:
            continue
        for node in graph_nodes(data):
            if node_has_type(node, "FAQPage"):
                entities.append(node.get("mainEntity", []))
    return hashlib.sha256(
        json.dumps(entities, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


def normalized_pattern(value: str, facts: PageFacts) -> str:
    replacements = [
        facts.title,
        facts.region_line,
        facts.neighborhood,
        facts.district,
        facts.region,
        facts.address,
        facts.center_name,
        facts.registration_name,
        facts.registration_number,
        *facts.relevant_schools(),
    ]
    result = value
    for replacement in sorted({item for item in replacements if item}, key=len, reverse=True):
        result = result.replace(replacement, "{FACT}")
    result = re.sub(r"\b(?:초|중|고)\d(?:~(?:초|중|고)\d)?\b", "{GRADE}", result)
    return re.sub(r"\s+", " ", result).strip()


def block_sentences(block: str) -> list[str]:
    values = []
    for value in re.findall(r"<(?:p|span)\b[^>]*>(.*?)</(?:p|span)>", block, flags=re.I | re.S):
        text = clean_text(value)
        if len(text) >= 24:
            values.append(text)
    return values


def print_sample(plan: PagePlan, index: int, show_html: bool) -> None:
    facts = plan.facts
    print(f"\n[샘플 {index}] {facts.relative}")
    print(f"  제목       : {facts.title}")
    print(f"  지역/대상  : {facts.region_line} / {facts.grade_subject}")
    print(f"  기존 설명  : {plan.old_description}")
    print(f"  변경 설명  : {plan.new_description}")
    print(f"  학생 상황  : {plan.scenario}")
    print(f"  학습 초점  : {plan.focus}")
    if facts.address:
        print(f"  확인 주소  : {facts.address}")
    schools = facts.relevant_schools()
    print(f"  확인 학교  : {', '.join(schools[:5]) if schools else '(페이지에 구체 학교 없음)'}")
    print("  체크리스트:")
    for item in plan.checklist:
        print(f"    - {item.label}: {item.text}")
    if show_html:
        print("\n----- 제안 HTML 시작 -----")
        print(plan.block_html)
        print("----- 제안 HTML 끝 -----")


def choose_samples(
    plans: list[PagePlan],
    root: Path,
    requested: list[str],
    count: int,
) -> list[PagePlan]:
    by_relative = {plan.facts.relative: plan for plan in plans}
    selected: list[PagePlan] = []
    for raw in requested:
        value = raw.replace("\\", "/").lstrip("./")
        if value.startswith("전국학원/"):
            relative = value
        else:
            relative = f"전국학원/{value}"
        if not relative.endswith("index.html"):
            relative = relative.rstrip("/") + "/index.html"
        plan = by_relative.get(relative)
        if not plan:
            raise ValueError(f"샘플 페이지를 찾지 못했습니다: {raw}")
        if plan not in selected:
            selected.append(plan)
    if selected:
        return selected[:count]

    preferred = (
        "전국학원/서울/강동구/명일동/index.html",
        "전국학원/충청/천안시/불당동/중등영수학원/index.html",
    )
    for relative in preferred:
        plan = by_relative.get(relative)
        if plan and plan not in selected:
            selected.append(plan)
    if len(selected) < count:
        parent = next((plan for plan in plans if not plan.facts.is_child and plan not in selected), None)
        child = next((plan for plan in plans if plan.facts.is_child and plan not in selected), None)
        for plan in (parent, child):
            if plan and plan not in selected:
                selected.append(plan)
            if len(selected) >= count:
                break
    for plan in plans:
        if plan not in selected:
            selected.append(plan)
        if len(selected) >= count:
            break
    return selected[:count]


def validate_collection(plans: list[PagePlan], expected_count: int) -> tuple[list[str], dict[str, Any]]:
    errors: list[str] = []
    page_errors = [(plan.facts.relative, issue) for plan in plans for issue in plan.issues]
    if len(plans) != expected_count:
        errors.append(f"대상 페이지 수가 예상과 다름: {len(plans):,} / {expected_count:,}")
    if page_errors:
        errors.append(f"페이지 검증 오류 {len(page_errors):,}건")

    descriptions = [plan.new_description for plan in plans]
    exact_description_count = len(set(descriptions))
    normalized_descriptions = [
        normalized_pattern(plan.new_description, plan.facts)
        for plan in plans
    ]
    blocks = [plan.block_html for plan in plans]
    exact_block_count = len(set(blocks))
    normalized_blocks = [normalized_pattern(plan.block_html, plan.facts) for plan in plans]

    sentence_counter: Counter[str] = Counter()
    for plan in plans:
        sentence_counter.update(block_sentences(plan.block_html))
    max_sentence_repeat = max(sentence_counter.values(), default=0)
    top_repeated_sentences = [
        (sentence, count)
        for sentence, count in sentence_counter.most_common(5)
        if count > 1
    ]

    old_labels_remaining = sum(
        1
        for plan in plans
        if any(label in plan.block_html for label in OLD_PRODUCER_LABELS)
    )
    review_changed = sum(
        1
        for plan in plans
        if structured_fingerprint(plan.old_source, {"review", "aggregateRating"})
        != structured_fingerprint(plan.new_source, {"review", "aggregateRating"})
    )
    faq_changed = sum(
        1
        for plan in plans
        if faq_fingerprint(plan.old_source) != faq_fingerprint(plan.new_source)
    )

    if exact_description_count != len(plans):
        errors.append(
            f"메타 설명 완전 중복: 고유 {exact_description_count:,} / 전체 {len(plans):,}"
        )
    if exact_block_count != len(plans):
        errors.append(f"개선 블록 완전 중복: 고유 {exact_block_count:,} / 전체 {len(plans):,}")
    if old_labels_remaining:
        errors.append(f"제작자용 영어 라벨 잔존 페이지: {old_labels_remaining:,}")
    if review_changed:
        errors.append(f"후기/평점이 달라진 페이지: {review_changed:,}")
    if faq_changed:
        errors.append(f"FAQ가 달라진 페이지: {faq_changed:,}")

    summary = {
        "target_pages": len(plans),
        "changed_pages": sum(plan.changed for plan in plans),
        "page_validation_errors": len(page_errors),
        "exact_unique_descriptions": exact_description_count,
        "normalized_description_patterns": len(set(normalized_descriptions)),
        "description_length_min": min(map(len, descriptions), default=0),
        "description_length_median": (
            sorted(map(len, descriptions))[len(descriptions) // 2] if descriptions else 0
        ),
        "description_length_max": max(map(len, descriptions), default=0),
        "exact_unique_blocks": exact_block_count,
        "normalized_block_patterns": len(set(normalized_blocks)),
        "max_exact_sentence_repeat": max_sentence_repeat,
        "top_repeated_sentences": top_repeated_sentences,
        "old_labels_remaining": old_labels_remaining,
        "review_or_rating_changed": review_changed,
        "faq_changed": faq_changed,
        "pages_with_address": sum(bool(plan.facts.address) for plan in plans),
        "pages_with_specific_schools": sum(bool(plan.facts.relevant_schools()) for plan in plans),
        "pages_with_grade_data": sum(bool(relevant_grade_fact(plan.facts)) for plan in plans),
        "pages_with_registration": sum(bool(plan.facts.registration_number) for plan in plans),
    }
    if page_errors:
        summary["first_page_errors"] = page_errors[:20]
    return errors, summary


def print_summary(summary: dict[str, Any], errors: list[str], mode: str) -> None:
    print("\n=== 전체 검증 요약 ===")
    print(f"실행 모드                         : {mode}")
    print(f"대상 페이지                       : {summary['target_pages']:,}")
    print(f"변경 예정/완료 페이지             : {summary['changed_pages']:,}")
    print(f"페이지 단위 검증 오류             : {summary['page_validation_errors']:,}")
    print(
        "메타 설명 완전 고유               : "
        f"{summary['exact_unique_descriptions']:,} / {summary['target_pages']:,}"
    )
    print(f"지역 사실 치환 후 설명 패턴       : {summary['normalized_description_patterns']:,}")
    print(
        "메타 설명 길이(최소/중앙/최대)   : "
        f"{summary['description_length_min']} / "
        f"{summary['description_length_median']} / "
        f"{summary['description_length_max']}자"
    )
    print(
        "개선 블록 완전 고유               : "
        f"{summary['exact_unique_blocks']:,} / {summary['target_pages']:,}"
    )
    print(f"지역 사실 치환 후 블록 패턴       : {summary['normalized_block_patterns']:,}")
    print(f"새 블록 문장 최대 반복 횟수       : {summary['max_exact_sentence_repeat']:,}")
    print(f"제작자용 영어 라벨 잔존           : {summary['old_labels_remaining']:,}")
    print(f"후기/평점 변경                    : {summary['review_or_rating_changed']:,}")
    print(f"FAQ 변경                          : {summary['faq_changed']:,}")
    print(f"주소 활용 가능 페이지             : {summary['pages_with_address']:,}")
    print(f"구체 학교 활용 가능 페이지        : {summary['pages_with_specific_schools']:,}")
    print(f"수강 가능 학년 활용 가능 페이지   : {summary['pages_with_grade_data']:,}")
    print(f"등록번호 활용 가능 페이지         : {summary['pages_with_registration']:,}")

    repeated = summary.get("top_repeated_sentences", [])
    if repeated:
        print("\n새 블록 반복 문장 상위:")
        for sentence, count in repeated:
            print(f"  - {count:>4}회 | {sentence}")

    if summary.get("first_page_errors"):
        print("\n페이지 오류 예시:")
        for relative, issue in summary["first_page_errors"]:
            print(f"  - {relative}: {issue}")

    if errors:
        print("\n검증 실패:")
        for error in errors:
            print(f"  - {error}")
    else:
        print("\n검증 결과: 통과")


def atomic_write(path: Path, content: str) -> None:
    temporary = path.with_name(path.name + ".content-v2.tmp")
    temporary.write_text(content, encoding="utf-8", newline="\n")
    temporary.replace(path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="전국학원 동네·자식페이지의 메타/답변/요약/체크리스트를 실제 페이지 정보로 개별화합니다."
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--apply",
        action="store_true",
        help="전체 검증 통과 후 실제 HTML 파일에 반영합니다.",
    )
    mode.add_argument(
        "--dry-run",
        action="store_true",
        help="파일을 쓰지 않고 변경 예시와 전체 검증 요약만 표시합니다(기본값).",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=ROOT,
        help="사이트 루트 경로(기본: 스크립트 상위 사이트 폴더)",
    )
    parser.add_argument(
        "--samples",
        type=int,
        default=2,
        help="dry-run에서 출력할 샘플 페이지 수(기본 2)",
    )
    parser.add_argument(
        "--sample-page",
        action="append",
        default=[],
        help="샘플로 볼 상대 경로. 여러 번 지정할 수 있습니다.",
    )
    parser.add_argument(
        "--show-html",
        action="store_true",
        help="샘플의 새 개선 블록 HTML 전체를 출력합니다.",
    )
    parser.add_argument(
        "--expected-count",
        type=int,
        default=EXPECTED_TARGET_COUNT,
        help=f"안전 검증용 예상 페이지 수(기본 {EXPECTED_TARGET_COUNT})",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = args.root.resolve()
    national_root = root / "전국학원"
    if not national_root.is_dir():
        print(f"오류: 전국학원 폴더를 찾을 수 없습니다: {national_root}", file=sys.stderr)
        return 2
    if args.samples < 0:
        print("오류: --samples는 0 이상이어야 합니다.", file=sys.stderr)
        return 2

    targets = page_targets(root)
    plans: list[PagePlan] = []
    for index, path in enumerate(targets, start=1):
        try:
            plans.append(transform_page(path, root))
        except Exception as exc:  # 한 페이지 오류로 나머지 검사를 잃지 않도록 경로와 함께 보고한다.
            print(f"변환 준비 실패 [{path.relative_to(root).as_posix()}]: {exc}", file=sys.stderr)
            return 2
        if index % 250 == 0:
            print(f"검사 준비: {index:,} / {len(targets):,}", file=sys.stderr)

    errors, summary = validate_collection(plans, args.expected_count)
    mode = "APPLY" if args.apply else "DRY-RUN"

    if not args.apply and args.samples:
        try:
            samples = choose_samples(plans, root, args.sample_page, args.samples)
        except ValueError as exc:
            print(f"오류: {exc}", file=sys.stderr)
            return 2
        for index, plan in enumerate(samples, start=1):
            print_sample(plan, index, args.show_html)

    print_summary(summary, errors, mode)
    if errors:
        print("\n파일은 수정하지 않았습니다.", file=sys.stderr)
        return 1

    if args.apply:
        for index, plan in enumerate(plans, start=1):
            if plan.changed:
                atomic_write(plan.facts.path, plan.new_source)
            if index % 250 == 0:
                print(f"반영 완료: {index:,} / {len(plans):,}", file=sys.stderr)
        print(f"\n총 {summary['changed_pages']:,}개 페이지에 반영했습니다.")
    else:
        print("\nDRY-RUN이므로 파일을 수정하지 않았습니다. 실제 반영은 --apply를 사용하세요.")
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):
        pass
    raise SystemExit(main())
