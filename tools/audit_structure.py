from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CENTER_ROOT = ROOT / "전국학원"

REQUIRED_TYPES = [
    "EducationalOrganization",
    "LocalBusiness",
    "WebPage",
    "BreadcrumbList",
    "Article",
    "Service",
    "FAQPage",
    "ItemList",
]


def type_names(node) -> list[str]:
    t = node.get("@type")
    if isinstance(t, list):
        return t
    return [t] if t else []


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
    issues = {
        "no_canonical": [],
        "no_og_url": [],
        "multi_h1": [],
        "no_h1": [],
        "bad_title_format": [],
        "jsonld_parse_error": [],
        "missing_types": [],
        "missing_fields": [],
    }

    for f in files:
        text = f.read_text(encoding="utf-8", errors="ignore")

        if not re.search(r'<link rel="canonical"', text):
            issues["no_canonical"].append(str(f))
        if not re.search(r'<meta property="og:url"', text):
            issues["no_og_url"].append(str(f))

        h1s = re.findall(r"<h1\b[^>]*>.*?</h1>", text, re.S)
        if len(h1s) == 0:
            issues["no_h1"].append(str(f))
        elif len(h1s) > 1:
            issues["multi_h1"].append(str(f))

        title_m = re.search(r"<title>(.*?)</title>", text, re.S)
        if not title_m or " | " not in title_m.group(1):
            issues["bad_title_format"].append(str(f))

        m = re.search(r'<script type="application/ld\+json">(.*?)</script>', text, re.S)
        if not m:
            issues["jsonld_parse_error"].append(str(f) + " (no script tag)")
            continue
        try:
            data = json.loads(m.group(1))
        except Exception as exc:  # noqa: BLE001
            issues["jsonld_parse_error"].append(f"{f}: {exc}")
            continue

        graph = data.get("@graph", [])
        present_types = set()
        for node in graph:
            if isinstance(node, dict):
                present_types.update(type_names(node))
        missing = [t for t in REQUIRED_TYPES if t not in present_types]
        if missing:
            issues["missing_types"].append(f"{f}: missing {missing}")

        # field-level checks on key nodes
        def find(type_name):
            for node in graph:
                if isinstance(node, dict) and type_name in type_names(node):
                    return node
            return None

        webpage = find("WebPage")
        article = find("Article")
        service = find("Service")
        org = find("EducationalOrganization")

        field_gaps = []
        if webpage:
            if not webpage.get("about"):
                field_gaps.append("WebPage.about")
            if not webpage.get("mentions"):
                field_gaps.append("WebPage.mentions")
            if not webpage.get("hasPart"):
                field_gaps.append("WebPage.hasPart")
        if article and not article.get("articleSection"):
            field_gaps.append("Article.articleSection")
        if org and not org.get("makesOffer"):
            field_gaps.append("Organization.makesOffer")
        if service and not service.get("makesOffer"):
            field_gaps.append("Service.makesOffer")
        if field_gaps:
            issues["missing_fields"].append(f"{f}: {field_gaps}")

    print(f"total_files={len(files)}")
    for key, vals in issues.items():
        print(f"{key}={len(vals)}")
        for v in vals[:5]:
            print(f"  - {v}")


if __name__ == "__main__":
    main()
