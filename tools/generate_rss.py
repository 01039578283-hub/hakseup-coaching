from __future__ import annotations

import html
import re
from datetime import datetime, timezone, timedelta
from email.utils import format_datetime
from pathlib import Path
from urllib.parse import quote, urljoin
from xml.etree import ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
BASE_URL = "https://xn--ru4bi8s1tac0p.kr"
FEED_URL = f"{BASE_URL}/rss.xml"
KST = timezone(timedelta(hours=9))
MAX_ITEMS = 50
CONTENT_NAMESPACE = "http://purl.org/rss/1.0/modules/content/"

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
    Path("과목별학원/고등영어학원/index.html"),
    Path("과목별학원/중등수학학원/index.html"),
    Path("과목별학원/중등영어학원/index.html"),
    Path("과목별학원/와와학습코칭센터/index.html"),
    Path("전국학원/index.html"),
)


def extract(pattern: str, source: str) -> str:
    match = re.search(pattern, source, re.I | re.S)
    return re.sub(r"\s+", " ", match.group(1)).strip() if match else ""


def extract_content(source: str, url: str) -> str:
    """Return the page's factual main content as feed-safe HTML.

    RSS readers receive the same headings, paragraphs, lists, tables and links that
    are visible on the canonical page. Scripts and other non-content resources are
    excluded, and relative links are expanded because the feed has a different base
    URL from each source document.
    """

    match = re.search(r"<main\b[^>]*>(.*?)</main>", source, re.I | re.S)
    if not match:
        raise ValueError(f"main content not found: {url}")

    content = match.group(1).strip()
    content = re.sub(r"<!--.*?-->", "", content, flags=re.S)
    content = re.sub(
        r"<(script|style|noscript|svg|iframe)\b[^>]*>.*?</\1\s*>",
        "",
        content,
        flags=re.I | re.S,
    )

    def absolutize(match: re.Match[str]) -> str:
        attribute, quote_mark, value = match.groups()
        decoded = html.unescape(value.strip())
        if decoded.lower().startswith(("data:", "javascript:")):
            absolute = decoded
        else:
            absolute = urljoin(url, decoded)
        escaped = html.escape(absolute, quote=True)
        return f"{attribute}{quote_mark}{escaped}{quote_mark}"

    content = re.sub(
        r"(\b(?:href|src)\s*=\s*)([\"'])(.*?)\2",
        absolutize,
        content,
        flags=re.I | re.S,
    )
    content = "\n".join(line.rstrip() for line in content.splitlines())
    return re.sub(r"\n{3,}", "\n\n", content).strip()


def content_text(content: str) -> str:
    plain = re.sub(r"<[^>]+>", " ", content)
    return re.sub(r"\s+", " ", html.unescape(plain)).strip()


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
    url = page_url(path)
    return {
        "path": path,
        "title": title,
        "description": description,
        "content": extract_content(source, url),
        "url": url,
        "modified": modified,
        "indexable": is_indexable(source),
    }


def national_depth(path: Path) -> int:
    national_root = ROOT / "전국학원"
    return len(path.relative_to(national_root).parts) - 1


def national_hub_candidates() -> list[Path]:
    """Prioritize all province hubs, then the broadest city/county hubs."""

    national_root = ROOT / "전국학원"
    candidates = [
        path
        for path in national_root.rglob("index.html")
        if national_depth(path) in {1, 2}
    ]

    def sort_key(path: Path) -> tuple[int, int, str]:
        depth = national_depth(path)
        direct_children = sum(
            1
            for child in path.parent.iterdir()
            if child.is_dir() and (child / "index.html").is_file()
        )
        return (depth, -direct_children, path.relative_to(ROOT).as_posix())

    return sorted(candidates, key=sort_key)


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

    for path in national_hub_candidates():
        if len(selected) >= MAX_ITEMS:
            break
        if path in used:
            continue
        data = page_data(path)
        if data["indexable"]:
            selected.append(data)
            used.add(path)

    # Keep a deterministic fallback for installations that do not yet have enough
    # national hubs. The current production tree fills all 50 slots before this.
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


def sitemap_urls() -> set[str]:
    sitemap = ET.parse(ROOT / "sitemap.xml").getroot()
    namespace = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    return {
        node.text.strip()
        for node in sitemap.findall("sm:url/sm:loc", namespace)
        if node.text and node.text.strip()
    }


def validate_items(items: list[dict[str, object]]) -> None:
    if len(items) != MAX_ITEMS:
        raise ValueError(f"expected {MAX_ITEMS} feed items, found {len(items)}")

    urls = [str(item["url"]) for item in items]
    if len(urls) != len(set(urls)):
        raise ValueError("feed item URLs must be unique")

    missing = sorted(set(urls) - sitemap_urls())
    if missing:
        raise ValueError(f"feed URLs missing from sitemap.xml: {missing}")

    empty_content = [
        str(item["url"])
        for item in items
        if len(content_text(str(item["content"]))) < 200
    ]
    if empty_content:
        raise ValueError(f"feed items missing substantive content: {empty_content}")


def build_feed(items: list[dict[str, object]]) -> ET.Element:
    ET.register_namespace("atom", "http://www.w3.org/2005/Atom")
    ET.register_namespace("content", CONTENT_NAMESPACE)
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
        ET.SubElement(item, f"{{{CONTENT_NAMESPACE}}}encoded").text = str(data["content"])
    return rss


def main() -> None:
    items = select_items()
    validate_items(items)
    root = build_feed(items)
    ET.indent(root, space="  ")
    xml = ET.tostring(root, encoding="unicode", xml_declaration=True)
    (ROOT / "rss.xml").write_text(xml + "\n", encoding="utf-8", newline="\n")
    national_items = sum("/%EC%A0%84%EA%B5%AD%ED%95%99%EC%9B%90/" in str(item["url"]) for item in items)
    print(
        f"Generated rss.xml with {len(items)} items "
        f"({national_items} nationwide academy pages)"
    )


if __name__ == "__main__":
    main()
