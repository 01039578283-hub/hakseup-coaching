from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE_SCRIPT = ROOT / "tmp" / "generate_middle_student_subject_pages.py"


def load_base():
    spec = importlib.util.spec_from_file_location("subject_page_base", BASE_SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load {BASE_SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


base = load_base()
base.ZIP_PATH = Path.home() / "Desktop" / "학습코칭.kr 추가 원고" / "초등학생학원.zip"
base.CATEGORY = "초등학생학원"
base.TARGET_ROOT = base.SUBJECT_ROOT / base.CATEGORY


def elementary_meta(title: str, source: dict, index: int) -> str:
    area = base.compact(f"{source['region']} {source['city']}")
    variants = [
        f"{title} 선택 전 확인할 안내입니다. {area} 학생의 현재 교재와 기초 이해도, 공부 습관을 살펴 학습 계획과 복습 기준을 정리했습니다.",
        f"{area}에서 {title}을 찾을 때 확인할 교과 기초, 학습 습관, 계획 실천과 틀린 문제 복습 기준을 학부모 관점에서 안내합니다.",
        f"{title} 상담 전에 살펴볼 내용을 모았습니다. {area} 초등학생의 현재 학습 상태와 교재, 주간 계획, 중등 과정 준비 기준을 확인하세요.",
        f"{area} {title} 안내입니다. 학생이 어려워하는 단원과 공부 습관을 진단하고 작은 계획부터 복습까지 연결하는 관리 기준을 설명합니다.",
        f"{title}을 비교하는 학부모를 위해 {area} 수업 가능 학교, 기초 진단, 자기주도 습관과 오답 재학습 기준을 간결하게 정리했습니다.",
        f"{area}에서 초등 학습 관리를 준비할 때 필요한 현재 교재 확인, 개념 진단, 주간 실행과 복습 기준을 {title} 페이지에서 안내합니다.",
        f"{title}은 수업량보다 학습 습관과 기초 이해도를 함께 봐야 합니다. {area} 학생의 계획 실천과 반복 학습 기준을 확인할 수 있습니다.",
        f"{area} 학부모가 {title} 상담에서 물어볼 기초 학습, 숙제 습관, 교재 진도와 중등 준비 기준을 학생 상황에 맞춰 정리했습니다.",
    ]
    meta = base.compact(variants[index % len(variants)])
    if len(meta) < 70:
        meta = base.compact(meta + " 상담 전 확인할 학습 기준도 함께 안내합니다.")
    if len(meta) > 100:
        meta = meta[:97].rstrip(" ,·") + "…"
    return meta


def elementary_review_note(locality: str, title: str, index: int) -> str:
    variants = [
        f"※ {locality} 학부모가 초등 학습 상담의 확인 기준을 이해하도록 구성한 가상 사례이며, 실제 수강생의 발언이나 성적 결과가 아닙니다.",
        f"※ 이 문구는 {title} 상담에서 살펴볼 관점을 설명하기 위한 예시입니다. 실제 후기 또는 학습 결과를 보장하는 사례가 아닙니다.",
        f"※ {locality} 초등학생의 학습 상황을 가정해 정리한 상담 예시로, 특정 이용자의 경험이나 결과를 재현한 내용이 아닙니다.",
        f"※ 아래 사례는 {title} 선택 기준을 이해하기 위한 설명용 구성입니다. 실제 수강 후기와 구분해 읽어 주세요.",
        f"※ {locality} 상담 과정에서 살펴볼 기초와 습관 항목을 보여 주는 가상 문구이며, 개인의 성적 향상을 보장하지 않습니다.",
        f"※ 학부모의 이해를 돕기 위해 {title} 상담 상황을 재구성한 예시입니다. 실제 학생의 발언이나 결과가 아닙니다.",
        f"※ 이 사례는 {locality} 초등 학습 상담의 확인 순서를 설명하려고 작성했으며, 실제 이용 후기로 제시한 내용이 아닙니다.",
        f"※ {title} 페이지의 상담 메모는 정보 제공을 위한 가상 사례입니다. 특정 학생의 경험이나 성과를 뜻하지 않습니다.",
        f"※ 아래 내용은 {locality} 학생에게 필요한 상담 질문을 보여 주기 위한 예시이며, 실제 후기나 결과 보장 표현이 아닙니다.",
        f"※ {title} 상담 시 확인할 학습 조건을 이해하기 쉽게 구성한 사례형 문구입니다. 실제 수강생 사례와는 다릅니다.",
        f"※ {locality} 학부모가 준비 항목을 살펴볼 수 있도록 만든 설명용 사례이며, 실제 성적 변화나 이용 경험을 나타내지 않습니다.",
        f"※ 다음 문구는 {title}의 초등 상담 흐름을 설명하기 위해 가정한 내용입니다. 실제 학생 후기 또는 성과 자료가 아닙니다.",
    ]
    return variants[index % len(variants)]


def rewrite_schema_value(value):
    if isinstance(value, str):
        exact = {
            "중학생 내신 및 고등 과정 학습관리": "초등학생 교과 및 중등 과정 학습관리",
            "중학생 내신·고등 과정 학습관리": "초등학생 교과·중등 과정 학습관리",
            "내신 대비": "교과 학습 및 중등 준비",
            "middle school": "primary school",
        }
        value = exact.get(value, value)
        return value.replace("중학생학원", "초등학생학원").replace("중학생", "초등학생").replace("중등 학습", "초등 학습")
    if isinstance(value, list):
        return [rewrite_schema_value(item) for item in value]
    if isinstance(value, dict):
        return {key: rewrite_schema_value(item) for key, item in value.items()}
    return value


original_make_graph = base.make_graph


def elementary_graph(**kwargs):
    related = kwargs["related"]
    locality = kwargs["locality"]
    slug = kwargs["slug"]
    middle = (f"{locality} 중학생학원", base.absolute_url("과목별학원", "중학생학원", slug))
    if middle not in related:
        related.insert(3, middle)
    graph = rewrite_schema_value(original_make_graph(**kwargs))
    middle_path = base.quote("/과목별학원/중학생학원/", safe="/")
    for node in graph.get("@graph", []):
        if node.get("@type") != "ItemList":
            continue
        for item in node.get("itemListElement", []):
            if middle_path in item.get("url", ""):
                item["name"] = f"{locality} 중학생학원"
    return graph


def individualized_faq(value: str, locality: str, title: str, source: dict, index: int) -> str:
    pairs = base.parse_faq(value)
    area = base.compact(f"{source['region']} {source['city']} {locality}")
    grade_match = re.search(r"([1-6]학년)", pairs[0][0] if pairs else "")
    grade = grade_match.group(1) if grade_match else "초등학생"
    opening_questions = [
        f"{locality}에서 {grade} 자녀의 학원을 고를 때 가장 먼저 확인할 점은 무엇인가요?",
        f"{title}을 알아보는 {grade} 학부모는 상담에서 무엇부터 물어봐야 하나요?",
        f"{area} {grade} 학생에게 맞는 학원인지 어떤 기준으로 판단하나요?",
        f"{locality} {grade} 학생의 현재 학습 상태는 상담에서 어떻게 확인하나요?",
        f"{title} 선택 전에 {grade} 자녀의 어떤 공부 기록을 살펴봐야 하나요?",
        f"{area}에서 {grade} 학습 관리를 시작할 때 우선 확인할 항목은 무엇인가요?",
        f"{locality} {grade} 자녀에게 필요한 수업과 관리를 어떻게 구분하나요?",
        f"{title} 상담에서 {grade} 학생의 막힌 지점을 어떻게 찾을 수 있나요?",
        f"{area} {grade} 학원 선택은 성적 외에 무엇을 함께 봐야 하나요?",
        f"{locality}에서 {grade} 자녀에게 맞는 학습 계획인지 어떻게 확인하나요?",
        f"{title}을 비교할 때 {grade} 학생의 공부 습관은 왜 중요한가요?",
        f"{area} {grade} 학생의 교재와 오답은 상담에서 어떻게 활용하나요?",
        f"{locality} {grade} 학원 상담 전에 준비하면 좋은 자료는 무엇인가요?",
        f"{title}이 {grade} 자녀에게 맞는지 첫 상담에서 무엇으로 살펴보나요?",
        f"{area}에서 {grade} 학생의 기초와 학습 습관을 함께 보는 방법은 무엇인가요?",
        f"{locality} {grade} 자녀의 학원 선택 기준을 어떤 순서로 정하면 좋나요?",
    ]
    question_variants = [
        f"{area}에서 학교 진도를 초등 학습 계획에 어떻게 반영해야 하나요?",
        f"{locality} 학생의 학교 진도와 학원 계획은 어떤 순서로 맞추면 좋나요?",
        f"{title} 상담에서 학교 자료는 어디까지 참고해야 하나요?",
        f"{area} 초등학생의 교과 진도를 계획에 그대로 적용해도 되나요?",
        f"{locality}에서 학교별 진도 차이는 상담 때 어떻게 확인하나요?",
        f"{title} 학습 계획을 세울 때 학교명보다 먼저 볼 자료가 있나요?",
        f"{area} 학생의 최근 과제와 평가 자료는 학원 상담에 왜 필요한가요?",
        f"{locality} 초등 학습 계획에 학교 수업 내용을 어떻게 연결하나요?",
        f"{title} 상담 전에 학교 진도와 과제는 어떻게 정리해 가면 좋나요?",
        f"{area}에서 학교 정보만으로 교재 진도를 정해도 괜찮을까요?",
        f"{locality} 학생의 실제 학습 범위는 무엇으로 확인해야 하나요?",
        f"{title} 계획을 학교 일정과 맞출 때 주의할 점은 무엇인가요?",
    ]
    answer_variants = [
        f"{locality}에서는 학교명만 보고 진도를 정하기보다 현재 교재, 최근 과제와 평가 자료를 함께 확인해야 합니다. 확인된 학습 범위 안에서 어려운 단원과 복습 순서를 정하고, 학교별 운영 방식은 임의로 가정하지 않는 편이 안전합니다.",
        f"상담에는 {locality} 학생이 실제로 공부한 교재와 과제, 최근 평가 결과를 가져가세요. 학교 정보는 참고 자료로 활용하되, 계획은 아이가 수행한 범위와 틀린 문제를 기준으로 조정하는 것이 좋습니다.",
        f"{area}의 학교 정보만으로 학생의 현재 수준을 단정하기는 어렵습니다. 최근 진도와 과제량, 평가 자료를 먼저 대조한 뒤 기초 보완과 다음 단원 준비의 비중을 나눠야 합니다.",
        f"{locality} 초등학생의 계획은 학교명보다 실제 학습 기록에서 시작합니다. 현재 교재와 배부 자료, 최근 틀린 문제를 확인하고 검증되지 않은 학교별 수업 방식은 계획의 근거로 삼지 않습니다.",
        f"학교 진도는 {title} 상담의 출발점일 뿐입니다. {locality} 학생이 받은 과제와 평가 자료, 집에서 복습한 범위를 함께 살펴 주간 학습량을 현실적으로 정하는 편이 좋습니다.",
        f"{area}에서 같은 학교를 다녀도 학생마다 이해한 범위와 공부 습관이 다를 수 있습니다. 최근 교재와 과제, 평가 결과를 기준으로 먼저 보완할 내용을 가리고 확인되지 않은 정보는 제외하세요.",
        f"{locality} 상담에서는 학교 이름보다 아이가 최근 어디까지 공부했고 어떤 문제에서 막혔는지를 구체적으로 알려 주세요. 그 자료를 바탕으로 교과 진도와 복습 계획을 연결해야 합니다.",
        f"학교 자료는 {locality} 학생의 학습 범위를 확인하는 데 활용합니다. 다만 계획은 최근 과제 수행, 평가 결과와 현재 교재를 함께 보고 세워야 하며 학교별 운영을 추측해서는 안 됩니다.",
        f"{title} 계획을 세울 때에는 학교 진도를 그대로 따라가기보다 학생이 이해하지 못한 단원부터 확인해야 합니다. {area}의 최근 과제와 평가 자료를 근거로 다음 학습 순서를 조정하세요.",
        f"{locality} 학생이 실제로 받은 교과 자료와 최근 평가 내용을 상담에서 확인하면 필요한 복습 범위가 분명해집니다. 제공되지 않은 학교별 세부 운영은 단정하지 않고 확인된 자료만 반영합니다.",
        f"{area}의 학교 일정은 참고하되, 현재 교재와 과제 수행 정도, 반복되는 오답을 함께 봐야 합니다. {title} 상담에서는 이 자료를 기준으로 주간 분량과 중등 준비 시점을 나눕니다.",
        f"학교명이 같아도 {locality} 학생마다 필요한 계획은 다릅니다. 최근 진도·과제·평가 자료를 가져가 현재 이해도를 먼저 확인하고, 확인되지 않은 정보 대신 실제 학습 기록으로 계획을 세우세요.",
        f"{title}에서는 학교 정보를 학생의 생활 범위를 이해하는 참고 자료로 봅니다. 실제 수업 계획은 {locality} 학생의 교재 진도, 과제와 평가 기록을 확인한 뒤 구체화하는 것이 적절합니다.",
        f"{locality} 초등 학습은 학교 진도와 개인의 이해 속도를 함께 맞춰야 합니다. 최근 교재와 과제 결과를 확인해 복습이 필요한 부분을 먼저 정하고 학교별 운영은 사실 확인 없이 가정하지 않습니다.",
        f"상담 전 {area} 학생의 현재 교재, 최근 과제와 평가 자료를 순서대로 준비하세요. 학교명 자체보다 실제로 학습한 범위와 어려워한 문제를 기준으로 계획을 조정하는 데 도움이 됩니다.",
        f"{locality}에서 학교별 진도 차이를 반영하려면 제공된 자료부터 확인해야 합니다. 최근 학습 범위와 과제, 평가 기록을 바탕으로 계획을 세우고 확인되지 않은 세부 정보는 판단 근거에서 제외합니다.",
    ]
    revised: list[tuple[str, str]] = []
    for position, (question, answer) in enumerate(pairs):
        if position == 0:
            question = opening_questions[index % len(opening_questions)]
        if "학교" in question and ("진도" in question or "계획" in question):
            question = question_variants[index % len(question_variants)]
            answer = answer_variants[index % len(answer_variants)]
        revised.append((question, answer))
    return "\n\n".join(f"Q{pos}. {question}\nA{pos}. {answer}" for pos, (question, answer) in enumerate(revised, 1))


def individualized_body(value: str, locality: str, index: int) -> str:
    repeated = f"{locality} 페이지에는 특정 수업 학교명이 제시되지 않았으므로, 상담에서는 현재 다니는 학교의 교과 진도와 과제량을 직접 알려 주고 그 범위 안에서 계획을 세우는 편이 안전합니다."
    variants = [
        f"{locality} 페이지에 수업 학교명이 따로 제시되지 않은 경우에는 현재 학교의 교과 진도와 과제량을 상담에서 직접 확인하고, 실제 학습 범위 안에서 계획을 세우는 것이 안전합니다.",
        f"수업 학교 정보가 없는 {locality} 안내에서는 학생이 현재 배우는 단원과 과제량을 먼저 알려 주세요. 확인된 교과 범위를 기준으로 계획을 조정해야 합니다.",
        f"{locality}의 특정 학교명이 제공되지 않았다면 학교를 추측하지 않고, 학생의 실제 교재 진도와 과제를 상담 자료로 삼아 학습 순서를 정합니다.",
        f"학교명이 별도로 안내되지 않은 {locality} 학생은 현재 교과 진도와 최근 과제를 준비하는 편이 좋습니다. 계획은 확인 가능한 학습 자료 안에서 구체화합니다.",
        f"{locality} 페이지에 학교 정보가 없을 때에는 현재 다니는 학교의 진도와 과제 범위를 상담에서 확인합니다. 제공된 자료를 넘어 학교별 상황을 임의로 가정하지 않습니다.",
        f"특정 수업 학교가 제시되지 않은 {locality} 안내에서는 학생이 실제로 학습한 교과 범위와 과제량을 중심으로 필요한 복습과 다음 진도를 나눕니다.",
        f"{locality} 학생의 학교명이 자료에 없다면 상담 시 현재 진도와 과제, 최근 평가 범위를 직접 알려 주세요. 그 범위 안에서 실행 가능한 계획을 세우는 것이 적절합니다.",
        f"학교 정보가 빠진 {locality} 페이지에서는 확인되지 않은 내용을 보태지 않습니다. 현재 교재와 학교 과제량을 기준으로 학생별 계획을 정합니다.",
    ]
    return value.replace(repeated, variants[index % len(variants)])


def elementary_records() -> list[dict]:
    if not base.ZIP_PATH.exists():
        raise FileNotFoundError(base.ZIP_PATH)
    sources = base.extract_source_pages()
    required = {"페이지타이틀", "메타설명", "본문", "FAQ", "학부모후기", "JSON-LD 요약"}
    records: list[dict] = []
    with base.ZipFile(base.ZIP_PATH) as archive:
        for name in archive.namelist():
            if not name.lower().endswith(".txt"):
                continue
            sections = base.parse_sections(base.decode_text(archive.read(name)))
            missing = required - set(sections)
            if missing:
                raise ValueError(f"Missing sections in {name}: {sorted(missing)}")
            title = base.compact(sections["페이지타이틀"])
            locality = re.sub(r"\s*초등학생학원\s*$", "", title).strip()
            slug = base.normalize_slug(locality)
            source = sources.get(slug)
            if not source:
                raise KeyError(f"No source center for {title} ({slug})")
            records.append({"sections": sections, "locality": locality, "slug": slug, "source": source})
    records.sort(key=lambda item: (item["source"]["region"], item["source"]["city"], item["locality"]))
    if len(records) != 371 or len({item["slug"] for item in records}) != 371:
        raise ValueError(f"Expected 371 unique records, got {len(records)}")
    return records


def elementary_page(record: dict, records: list[dict], index: int) -> str:
    local_record = dict(record)
    local_record["sections"] = dict(record["sections"])
    local_record["sections"]["FAQ"] = individualized_faq(
        local_record["sections"]["FAQ"], local_record["locality"],
        local_record["sections"]["페이지타이틀"], local_record["source"], index,
    )
    local_record["sections"]["본문"] = individualized_body(
        local_record["sections"]["본문"], local_record["locality"], index,
    )
    page = original_render_local(local_record, records, index)
    replacements = {
        "MIDDLE SCHOOL COACHING": "ELEMENTARY SCHOOL COACHING",
        "LOCAL MIDDLE SCHOOL GUIDE": "LOCAL ELEMENTARY SCHOOL GUIDE",
        "<span>중학생</span>": "<span>초등학생</span>",
        "인접한 중학생학원 페이지": "같은 동네의 학년별 학원 페이지",
    }
    for old, new in replacements.items():
        page = page.replace(old, new)
    return page


def elementary_hub(records: list[dict]) -> str:
    page = original_render_hub(records)
    replacements = {
        "MIDDLE SCHOOL ACADEMY DIRECTORY": "ELEMENTARY SCHOOL ACADEMY DIRECTORY",
        "지역명으로 중학생학원 찾기": "지역명으로 초등학생학원 찾기",
        "중학생 학원은 수업 전후의 관리 흐름까지 확인하세요": "초등학생 학원은 기초와 공부 습관의 연결을 확인하세요",
        "내신·고등 과정 계획": "교과 학습·중등 과정 준비",
        "최근 시험지와 교재, 오답 패턴을 기준으로 우선순위를 정합니다.": "현재 교재와 학습 기록, 어려워하는 단원을 기준으로 우선순위를 정합니다.",
        "학교 일정과 목표를 함께 보고 주간 학습량을 조정합니다.": "학교 진도와 학생의 학습 습관을 함께 보고 주간 학습량을 조정합니다.",
        "중학생학원": "초등학생학원",
        "중학생": "초등학생",
    }
    for old, new in replacements.items():
        page = page.replace(old, new)
    return page


def update_llms() -> None:
    path = ROOT / "llms.txt"
    if not path.exists():
        return
    text = path.read_text(encoding="utf-8")
    line = f"- [초등학생학원 371개 지역 안내]({base.absolute_url('과목별학원', base.CATEGORY)})"
    if line not in text:
        marker = "## 과목별학원"
        position = text.find("\n## ", text.find(marker) + len(marker))
        if position == -1:
            text = text.rstrip() + "\n" + line + "\n"
        else:
            text = text[:position].rstrip() + "\n" + line + "\n\n" + text[position + 1:].lstrip("\n")
        path.write_text(text, encoding="utf-8", newline="\n")


base.build_middle_meta = elementary_meta
base.varied_review_note = elementary_review_note
base.make_graph = elementary_graph
base.load_records = elementary_records
original_render_local = base.render_local_page
original_render_hub = base.render_hub
base.render_local_page = elementary_page
base.render_hub = elementary_hub
base.update_llms = update_llms


if __name__ == "__main__":
    base.main()
