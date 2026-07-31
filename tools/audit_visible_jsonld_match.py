from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CENTER_ROOT = ROOT / "전국학원"


def target_files() -> list[Path]:
    result = []
    for index in CENTER_ROOT.rglob("index.html"):
        rel = index.parent.relative_to(CENTER_ROOT)
        if str(rel) == ".":
            continue
        if len(rel.parts) in {3, 4}:
            result.append(index)
    return sorted(result)


def type_names(node) -> list[str]:
    t = node.get("@type")
    if isinstance(t, list):
        return t
    return [t] if t else []


def find(graph, type_name):
    for node in graph:
        if isinstance(node, dict) and type_name in type_names(node):
            return node
    return None


def main() -> None:
    files = target_files()
    faq_mismatch = 0
    unsupported_review_schema = 0
    visible_star_ratings = 0
    evidence_card_bad = 0

    for f in files:
        text = f.read_text(encoding="utf-8", errors="ignore")
        m = re.search(r'<script type="application/ld\+json">(.*?)</script>', text, re.S)
        data = json.loads(m.group(1))
        graph = data["@graph"]

        faq_node = find(graph, "FAQPage")
        visible_q = re.findall(r'<span class="parent-faq-q">Q</span>([^<]*)</summary>', text)
        jsonld_q = [q["name"] for q in faq_node["mainEntity"]]
        if visible_q != jsonld_q:
            faq_mismatch += 1
            print("FAQ MISMATCH", f)

        org_node = find(graph, "EducationalOrganization")
        if "review" in org_node or "aggregateRating" in org_node:
            unsupported_review_schema += 1
            print("UNSUPPORTED REVIEW SCHEMA", f)

        visible_ratings = re.findall(r'aria-label="(\d)점 후기"', text)
        if visible_ratings:
            visible_star_ratings += 1
            print("VISIBLE STAR RATING", f, visible_ratings)

        evidence_cards = re.findall(r'parent-review-card">.*?<p>(.*?)</p>', text, re.S)
        if len(evidence_cards) != 4 or "학습관리 확인 정보" not in text:
            evidence_card_bad += 1
            print("EVIDENCE CARD BAD", f)

    print(
        f"total={len(files)} faq_mismatch={faq_mismatch} "
        f"unsupported_review_schema={unsupported_review_schema} "
        f"visible_star_ratings={visible_star_ratings} "
        f"evidence_card_bad={evidence_card_bad}"
    )


if __name__ == "__main__":
    main()
