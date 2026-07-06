from __future__ import annotations

import json
import re
from pathlib import Path

SITE = Path(__file__).resolve().parents[1]
ROOT_ORG_ID = "https://학습코칭.kr/#organization"

ORG_NAME_PATTERN = re.compile(
    r'("@type":\["EducationalOrganization","LocalBusiness"\],"@id":"[^"]*#organization","name":")'
    r'([^"]*)'
    r'(","url":)'
)
BRANCH_PATTERN = re.compile(r'aria-label="와와학습코칭센터\s+(.+?)\s+센터 안내"')


def enhance_root(index_file: Path) -> bool:
    text = index_file.read_text(encoding="utf-8")
    if "alternateName" in text:
        return False
    old = (
        '      "name": "학습코칭 연구소",\n'
        '      "url": "https://학습코칭.kr/",\n'
        '      "logo":'
    )
    new = (
        '      "name": "학습코칭 연구소",\n'
        '      "alternateName": ["와와학습코칭센터", "와와학습코칭학원", "와와학원"],\n'
        '      "url": "https://학습코칭.kr/",\n'
        '      "logo":'
    )
    if old not in text:
        print(f"WARN root anchor not found: {index_file}")
        return False
    index_file.write_text(text.replace(old, new, 1), encoding="utf-8")
    return True


def enhance_local(index_file: Path) -> bool:
    text = index_file.read_text(encoding="utf-8")
    if "alternateName" in text:
        return False

    org_match = ORG_NAME_PATTERN.search(text)
    branch_match = BRANCH_PATTERN.search(text)
    if not org_match or not branch_match:
        print(f"WARN anchor not found: {index_file}")
        return False

    branch = branch_match.group(1)
    alt_names = [
        f"와와학습코칭학원 {branch}",
        f"와와학습코칭센터 {branch}",
        "와와학습코칭학원",
        "와와학습코칭센터",
        "와와학원",
    ]
    alt_json = json.dumps(alt_names, ensure_ascii=False)
    replacement = (
        f'{org_match.group(1)}{org_match.group(2)}",'
        f'"alternateName":{alt_json},'
        f'"branchOf":{{"@id":"{ROOT_ORG_ID}"}},'
        f'"url":'
    )
    new_text = text[: org_match.start()] + replacement + text[org_match.end():]
    index_file.write_text(new_text, encoding="utf-8")
    return True


def validate_jsonld(index_file: Path) -> None:
    text = index_file.read_text(encoding="utf-8")
    for m in re.finditer(r'<script type="application/ld\+json">(.*?)</script>', text, re.S):
        json.loads(m.group(1))


def main() -> None:
    root_index = SITE / "index.html"
    root_changed = enhance_root(root_index)
    validate_jsonld(root_index)

    changed = 0
    skipped = 0
    warned = 0
    for f in sorted(SITE.glob("전국학원/**/index.html")):
        if not ORG_NAME_PATTERN.search(f.read_text(encoding="utf-8")):
            continue  # hub pages without a LocalBusiness node
        try:
            ok = enhance_local(f)
        except Exception as exc:  # noqa: BLE001
            print(f"ERROR {f}: {exc}")
            warned += 1
            continue
        if ok:
            changed += 1
            try:
                validate_jsonld(f)
            except Exception as exc:  # noqa: BLE001
                print(f"JSON-LD BROKEN after edit: {f}: {exc}")
                warned += 1
        else:
            skipped += 1

    print(f"root_changed={root_changed}")
    print(f"local_changed={changed} skipped={skipped} warned={warned}")


if __name__ == "__main__":
    main()
