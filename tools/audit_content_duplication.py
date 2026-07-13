from __future__ import annotations

import re
from collections import Counter
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


def main() -> None:
    files = target_files()
    faq_counter: Counter[str] = Counter()
    review_counter: Counter[str] = Counter()
    review_sets: Counter[frozenset] = Counter()

    for f in files:
        text = f.read_text(encoding="utf-8", errors="ignore")
        faqs = re.findall(r'<p class="parent-faq-answer">(.*?)</p>', text)
        for a in faqs:
            faq_counter[a] += 1
        reviews = re.findall(r'parent-review-card">.*?<p>(.*?)</p>', text, re.S)
        for r in reviews:
            review_counter[r] += 1
        if reviews:
            review_sets[frozenset(reviews)] += 1

    dup_review_sets = sum(1 for cnt in review_sets.values() if cnt > 1)

    print(f"total_pages={len(files)}")
    print(f"distinct_faq_answers={len(faq_counter)} total_faq_instances={sum(faq_counter.values())}")
    print("top repeated FAQ answers:")
    for text, cnt in faq_counter.most_common(5):
        print(f"  {cnt}x  {text[:60]}")
    print()
    print(f"distinct_review_bodies={len(review_counter)} total_review_instances={sum(review_counter.values())}")
    print("top repeated review bodies:")
    for text, cnt in review_counter.most_common(5):
        print(f"  {cnt}x  {text[:60]}")
    print()
    print(f"distinct_review_sets={len(review_sets)} pages_with_reviews={sum(review_sets.values())}")
    print(f"review_sets_used_more_than_once={dup_review_sets}")


if __name__ == "__main__":
    main()
