from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def write_if_changed(path: Path, text: str) -> None:
    previous = path.read_text(encoding="utf-8")
    if previous != text:
        path.write_text(text, encoding="utf-8", newline="\n")


for path in ROOT.rglob("index.html"):
    if ".vercel" in path.parts:
        continue
    html = path.read_text(encoding="utf-8")
    nav_match = re.search(r'<div class="nav-links">(.*?)</div>', html, re.DOTALL)
    if not nav_match or ">과목별학원</a>" in nav_match.group(1):
        continue

    nationwide = re.search(
        r'(<a\b[^>]*href="(?P<prefix>[^"]*)전국학원/"[^>]*>\s*전국학원\s*</a>)',
        nav_match.group(1),
        re.DOTALL,
    )
    if not nationwide:
        raise RuntimeError(f"전국학원 메뉴를 찾을 수 없습니다: {path}")

    subject_link = f'<a href="{nationwide.group("prefix")}과목별학원/">과목별학원</a>'
    new_nav = (
        nav_match.group(1)[:nationwide.end()]
        + subject_link
        + nav_match.group(1)[nationwide.end():]
    )
    updated = html[:nav_match.start(1)] + new_nav + html[nav_match.end(1):]
    updated = "\n".join(line.rstrip() for line in updated.splitlines()) + "\n"
    write_if_changed(path, updated)
