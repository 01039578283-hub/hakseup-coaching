from __future__ import annotations

import re
from datetime import datetime, timezone, timedelta
from email.utils import format_datetime
from pathlib import Path
from urllib.parse import quote
from xml.etree import ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
BASE_URL = "https://xn--ru4bi8s1tac0p.kr"
FEED_URL = f"{BASE_URL}/rss.xml"
KST = timezone(timedelta(hours=9))
MAX_ITEMS = 50

CORE_PATHS = (
    Path("index.html"),
    Path("진단상담/index.html"),
    Path("학습가이드/index.html"),
    Path("과목별학원/index.html"),
    Path("과목별학원/초등학생학원/index.html"),
    Path("과목별학원/중학생학원/index.html"),
    Path("과목별학원/고등학생학원/index.html"),
    Path("과목별학원/영수학원/index.html"),
    Path("과목별학원/고등수학학원/index.html"),
    Path("과목별학원/와와학습코칭센터/index.html"),
    Path("전국학원/index.html"),
)


def extract(pattern: str, source: str) -> str:
    match = re.search(pattern, source, re.I | re.S)
    return re.sub(r"\s+", " ", match.group(1)).strip() if match else ""


def is_indexable(source: str) -> bool:
    robots = extract(r'<meta\s+name=["\']robots["\']\s+content=["\']([^"\']+)', source)
    return "noindex" not in robots.lower()


def page_url(path: Path) -> str:
    relative = path.relative_to(ROOT)
    if relative == Path("index.html"):
        return f"{BASE_URL}/"
    route = relative.parent.as_posix().strip("/")
    return f"{BASE_URL}/{quote(route, safe='/')}/"


def page_data(path: Path) -> dict[str, object]:
    source = path.read_text(encoding="utf-8", errors="strict")
    title = extract(r"<title>(.*?)</title>", source) or path.parent.name
    description = extract(r'<meta\s+name=["\']description["\']\s+content=["\']([^"\']*)', source)
    modified = datetime.fromtimestamp(path.stat().st_mtime, tz=KST)
    return {
        "path": path,
        "title": title,
        "description": description,
        "url": page_url(path),
        "modified": modified,
        "indexable": is_indexable(source),
    }


def select_items() -> list[dict[str, object]]:
    selected: list[dict[str, object]] = []
    used: set[Path] = set()

    for relative in CORE_PATHS:
        path = ROOT / relative
        if not path.exists():
            continue
        data = page_data(path)
        if data["indexable"]:
            selected.append(data)
            used.add(path)

    recent_candidates: list[dict[str, object]] = []
    subject_root = ROOT / "과목별학원"
    for path in subject_root.glob("*/*/index.html"):
        if path in used:
            continue
        data = page_data(path)
        if data["indexable"]:
            recent_candidates.append(data)
    recent_candidates.sort(key=lambda item: (item["modified"], item["url"]), reverse=True)
    selected.extend(recent_candidates[: max(0, MAX_ITEMS - len(selected))])
    return selected[:MAX_ITEMS]


def build_feed(items: list[dict[str, object]]) -> ET.Element:
    ET.register_namespace("atom", "http://www.w3.org/2005/Atom")
    rss = ET.Element("rss", {"version": "2.0"})
    channel = ET.SubElement(rss, "channel")
    ET.SubElement(channel, "title").text = "학습코칭 연구소"
    ET.SubElement(channel, "link").text = f"{BASE_URL}/"
    ET.SubElement(channel, "description").text = (
        "학습 진단, 플래너 관리, 오답 재학습과 학년별·지역별 학원 선택 기준을 안내합니다."
    )
    ET.SubElement(channel, "language").text = "ko-KR"
    ET.SubElement(channel, "lastBuildDate").text = format_datetime(datetime.now(KST))
    ET.SubElement(
        channel,
        "{http://www.w3.org/2005/Atom}link",
        {"href": FEED_URL, "rel": "self", "type": "application/rss+xml"},
    )

    for data in items:
        item = ET.SubElement(channel, "item")
        ET.SubElement(item, "title").text = str(data["title"])
        ET.SubElement(item, "link").text = str(data["url"])
        ET.SubElement(item, "guid", {"isPermaLink": "true"}).text = str(data["url"])
        ET.SubElement(item, "pubDate").text = format_datetime(data["modified"])
        ET.SubElement(item, "description").text = str(data["description"])
    return rss


def main() -> None:
    items = select_items()
    root = build_feed(items)
    ET.indent(root, space="  ")
    xml = ET.tostring(root, encoding="unicode", xml_declaration=True)
    (ROOT / "rss.xml").write_text(xml + "\n", encoding="utf-8", newline="\n")
    print(f"Generated rss.xml with {len(items)} items")


if __name__ == "__main__":
    main()
