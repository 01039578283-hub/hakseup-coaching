from __future__ import annotations

import re
import subprocess
from datetime import date
from pathlib import Path
from urllib.parse import quote
from xml.sax.saxutils import escape


ROOT = Path(__file__).resolve().parents[1]
BASE_URL = "https://xn--ru4bi8s1tac0p.kr"
EXCLUDED_DIRS = {".git", ".vercel", "__pycache__", "tmp"}


def is_public_html(path: Path) -> bool:
    relative = path.relative_to(ROOT)
    if any(part in EXCLUDED_DIRS for part in relative.parts):
        return False
    source = path.read_text(encoding="utf-8", errors="ignore")
    return not bool(
        re.search(
            r'<meta\s+name=["\']robots["\']\s+content=["\'][^"\']*noindex',
            source,
            re.I,
        )
    )


def public_url(path: Path) -> str:
    relative = path.relative_to(ROOT).as_posix()
    if relative == "index.html":
        route = "/"
    elif relative.endswith("/index.html"):
        route = "/" + relative[: -len("index.html")]
    else:
        route = "/" + relative
    return BASE_URL + quote(route, safe="/")


def git_dates() -> dict[str, str]:
    command = [
        "git",
        "-c",
        "core.quotepath=false",
        "log",
        "--name-only",
        "--format=@@DATE:%ad",
        "--date=short",
        "--diff-filter=AM",
        "--",
        "*.html",
    ]
    completed = subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=True,
    )
    result: dict[str, str] = {}
    current_date = ""
    for raw_line in completed.stdout.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("@@DATE:"):
            current_date = line.split(":", 1)[1].strip()
            continue
        normalized = line.replace("\\", "/")
        if current_date and normalized not in result:
            result[normalized] = current_date
    return result


def working_tree_paths() -> set[str]:
    completed = subprocess.run(
        ["git", "-c", "core.quotepath=false", "status", "--porcelain", "-z"],
        cwd=ROOT,
        capture_output=True,
        check=True,
    )
    decoded = completed.stdout.decode("utf-8", errors="replace")
    result: set[str] = set()
    for entry in decoded.split("\0"):
        if len(entry) < 4:
            continue
        path = entry[3:]
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        result.add(path.replace("\\", "/"))
    return result


def modified_date(
    path: Path,
    history: dict[str, str],
    working: set[str],
    today: str,
) -> str:
    relative = path.relative_to(ROOT).as_posix()
    if relative in working:
        return today
    if relative in history:
        return history[relative]
    return date.fromtimestamp(path.stat().st_mtime).isoformat()


def main() -> None:
    pages = [
        path
        for path in ROOT.rglob("*.html")
        if is_public_html(path)
    ]
    history = git_dates()
    working = working_tree_paths()
    today = date.today().isoformat()

    records = sorted(
        (
            public_url(path),
            modified_date(path, history, working, today),
        )
        for path in pages
    )
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
    ]
    for url, lastmod in records:
        lines.extend(
            [
                "  <url>",
                f"    <loc>{escape(url)}</loc>",
                f"    <lastmod>{lastmod}</lastmod>",
                "  </url>",
            ]
        )
    lines.append("</urlset>")
    (ROOT / "sitemap.xml").write_text(
        "\n".join(lines) + "\n", encoding="utf-8", newline="\n"
    )

    unique_dates = sorted({lastmod for _, lastmod in records})
    print(f"urls={len(records)}")
    print(f"unique_lastmod_dates={len(unique_dates)}")
    print(f"oldest={unique_dates[0] if unique_dates else ''}")
    print(f"newest={unique_dates[-1] if unique_dates else ''}")


if __name__ == "__main__":
    main()
