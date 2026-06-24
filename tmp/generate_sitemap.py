from __future__ import annotations

from datetime import date
from pathlib import Path
from urllib.parse import quote
from xml.sax.saxutils import escape


ROOT = Path(__file__).resolve().parents[1]
BASE_URL = "https://학습코칭.kr"
EXCLUDED_DIRS = {".git", ".vercel", "__pycache__"}


def is_public_html(path: Path) -> bool:
    parts = set(path.relative_to(ROOT).parts)
    return path.suffix.lower() == ".html" and not parts.intersection(EXCLUDED_DIRS)


def public_url(path: Path) -> str:
    rel = path.relative_to(ROOT).as_posix()
    if rel == "index.html":
        page_path = "/"
    elif rel.endswith("/index.html"):
        page_path = "/" + rel[: -len("index.html")]
    else:
        page_path = "/" + rel
    return BASE_URL + quote(page_path, safe="/")


def main() -> None:
    urls = sorted({public_url(path) for path in ROOT.rglob("*.html") if is_public_html(path)})
    today = date.today().isoformat()
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
    ]
    for url in urls:
        lines.extend(
            [
                "  <url>",
                f"    <loc>{escape(url)}</loc>",
                f"    <lastmod>{today}</lastmod>",
                "  </url>",
            ]
        )
    lines.append("</urlset>")
    (ROOT / "sitemap.xml").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Generated sitemap.xml with {len(urls)} URLs")


if __name__ == "__main__":
    main()
