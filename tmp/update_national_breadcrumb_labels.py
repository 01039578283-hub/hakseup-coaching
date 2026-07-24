from __future__ import annotations

import html
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
NATIONAL_ROOT = ROOT / "전국학원"

H1_PATTERN = re.compile(r"<h1(?:\s[^>]*)?>(.*?)</h1>", re.IGNORECASE | re.DOTALL)
BREADCRUMB_PATTERN = re.compile(
    r'(<div\s+class="breadcrumb"[^>]*>)(.*?)(</div>)',
    re.IGNORECASE | re.DOTALL,
)
JSON_LD_PATTERN = re.compile(
    r'(<script\s+type="application/ld\+json"[^>]*>)(.*?)(</script>)',
    re.IGNORECASE | re.DOTALL,
)


def clean_text(value: str) -> str:
    value = re.sub(r"<[^>]+>", "", value)
    return " ".join(html.unescape(value).split())


def page_title(source: str) -> str:
    match = H1_PATTERN.search(source)
    return clean_text(match.group(1)) if match else ""


def update_visible_breadcrumb(source: str, title: str) -> tuple[str, bool]:
    match = BREADCRUMB_PATTERN.search(source)
    if not match or "›" not in match.group(2):
        return source, False

    inner = match.group(2)
    prefix = inner.rsplit("›", 1)[0].rstrip() + " › "
    replacement = match.group(1) + prefix + html.escape(title) + match.group(3)
    if match.group(0) == replacement:
        return source, False
    return source[: match.start()] + replacement + source[match.end() :], True


def iter_graph_nodes(data: object):
    if not isinstance(data, dict):
        return
    graph = data.get("@graph")
    if isinstance(graph, list):
        yield from (node for node in graph if isinstance(node, dict))
    else:
        yield data


def update_json_breadcrumbs(source: str, title: str) -> tuple[str, int]:
    changed_nodes = 0

    def replace_script(match: re.Match[str]) -> str:
        nonlocal changed_nodes
        raw = match.group(2)
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return match.group(0)

        script_changed = False
        for node in iter_graph_nodes(data):
            node_type = node.get("@type")
            is_breadcrumb = node_type == "BreadcrumbList" or (
                isinstance(node_type, list) and "BreadcrumbList" in node_type
            )
            if not is_breadcrumb:
                continue
            items = node.get("itemListElement")
            if not isinstance(items, list) or not items or not isinstance(items[-1], dict):
                continue
            if items[-1].get("name") != title:
                items[-1]["name"] = title
                changed_nodes += 1
                script_changed = True

        if not script_changed:
            return match.group(0)
        encoded = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
        return match.group(1) + encoded + match.group(3)

    return JSON_LD_PATTERN.sub(replace_script, source), changed_nodes


def main() -> None:
    scanned = 0
    updated_files = 0
    visible_updates = 0
    json_updates = 0
    skipped: list[str] = []

    for path in sorted(NATIONAL_ROOT.rglob("index.html")):
        depth = len(path.relative_to(NATIONAL_ROOT).parts) - 1
        if depth < 3:
            continue

        scanned += 1
        source = path.read_text(encoding="utf-8")
        title = page_title(source)
        if not title:
            skipped.append(str(path.relative_to(ROOT)))
            continue

        updated, visible_changed = update_visible_breadcrumb(source, title)
        updated, json_changed = update_json_breadcrumbs(updated, title)
        if updated != source:
            path.write_text(updated, encoding="utf-8", newline="")
            updated_files += 1
        visible_updates += int(visible_changed)
        json_updates += json_changed

    print(f"scanned={scanned}")
    print(f"updated_files={updated_files}")
    print(f"visible_updates={visible_updates}")
    print(f"json_updates={json_updates}")
    print(f"skipped={len(skipped)}")
    for item in skipped[:20]:
        print(f"SKIP {item}")


if __name__ == "__main__":
    main()
