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
    review_mismatch = 0
    rating_bad = 0

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
        visible_reviews = re.findall(r'parent-review-card">.*?<p>(.*?)</p>', text, re.S)
        jsonld_reviews = [r["reviewBody"] for r in org_node["review"]]
        if visible_reviews != jsonld_reviews:
            review_mismatch += 1
            print("REVIEW MISMATCH", f)

        visible_ratings = re.findall(r'aria-label="(\d)점 후기"', text)
        five_count = visible_ratings.count("5")
        four_count = visible_ratings.count("4")
        if not (five_count == 5 and four_count == 1 and len(visible_ratings) == 6):
            rating_bad += 1
            print("RATING RATIO BAD", f, visible_ratings)

    print(f"total={len(files)} faq_mismatch={faq_mismatch} review_mismatch={review_mismatch} rating_bad={rating_bad}")


if __name__ == "__main__":
    main()
