from __future__ import annotations

"""Read-only release audit for the locality-level internal link network."""

import html
import json
import re
import statistics
from collections import Counter
from pathlib import Path
from urllib.parse import unquote, urljoin, urlsplit
from xml.etree import ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
START_MARKER = "<!-- local-study-network:start -->"
END_MARKER = "<!-- local-study-network:end -->"
NETWORK_RE = re.compile(
    re.escape(START_MARKER) + r"(.*?)" + re.escape(END_MARKER), re.S
)
CANONICAL_RE = re.compile(
    r'<link\b(?=[^>]*\brel=["\']canonical["\'])[^>]*\bhref=["\'](.*?)["\']',
    re.I | re.S,
)
HREF_RE = re.compile(r'<a\b[^>]*\bhref=["\'](.*?)["\']', re.I | re.S)
NETWORK_HREF_RE = re.compile(
    r'<a\b[^>]*class="[^"]*local-study-network-card[^"]*"[^>]*href="(.*?)"',
    re.I | re.S,
)
JSONLD_RE = re.compile(
    r'<script\b[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
    re.I | re.S,
)


def key(value: str) -> str:
    route = unquote(urlsplit(html.unescape(value)).path).replace("\\", "/")
    route = re.sub(r"/index\.html/?$", "/", route, flags=re.I)
    route = "/" + route.strip("/")
    return "/" if route == "/" else route + "/"


def canonical(source: str) -> str:
    match = CANONICAL_RE.search(source)
    if not match:
        raise ValueError("canonical 없음")
    return html.unescape(match.group(1)).rstrip("/") + "/"


def is_indexable(source: str) -> bool:
    head = re.search(r"<head\b.*?</head>", source, re.I | re.S)
    return not (head and re.search(r"\bnoindex\b", head.group(0), re.I))


def public_sources() -> dict[Path, str]:
    return {
        path: path.read_text(encoding="utf-8", errors="strict")
        for path in ROOT.rglob("index.html")
        if ".vercel" not in path.parts and "tmp" not in path.parts
    }


def network_schema_urls(source: str, current_url: str) -> list[str]:
    node_id = current_url + "#local-study-network"
    found: list[dict] = []
    for payload in JSONLD_RE.findall(source):
        data = json.loads(payload)
        graph = data.get("@graph", []) if isinstance(data, dict) else []
        if not isinstance(graph, list):
            continue
        found.extend(
            node
            for node in graph
            if isinstance(node, dict) and node.get("@id") == node_id
        )
    if len(found) != 1:
        raise ValueError(f"network ItemList={len(found)}")
    node = found[0]
    items = node.get("itemListElement")
    if not isinstance(items, list) or node.get("numberOfItems") != len(items):
        raise ValueError("network ItemList 개수 불일치")
    return [item.get("url", "") for item in items if isinstance(item, dict)]


def is_cluster_page(route: str) -> bool:
    parts = tuple(part for part in route.strip("/").split("/") if part)
    if len(parts) == 3 and parts[0] == "과목별학원":
        return parts[1] != "와와학습코칭센터"
    return parts[0:1] == ("전국학원",) and len(parts) in (4, 5)


def percentile(values: list[int], ratio: float) -> int:
    return values[int((len(values) - 1) * ratio)]


def main() -> int:
    sources = public_sources()
    pages: dict[str, tuple[str, str, Path]] = {}
    errors: list[str] = []
    for path, source in sources.items():
        try:
            url = canonical(source)
        except ValueError as exc:
            errors.append(f"{path.relative_to(ROOT)}: {exc}")
            continue
        if not is_indexable(source):
            continue
        route = key(url)
        if route in pages:
            errors.append(f"canonical 중복: {route}")
            continue
        pages[route] = (url, source, path)

    sitemap = {
        key(node.text or "")
        for node in ET.parse(ROOT / "sitemap.xml").findall(".//{*}loc")
    }
    if sitemap != set(pages):
        errors.append(
            f"sitemap/page 차이={len(sitemap - set(pages))}/{len(set(pages) - sitemap)}"
        )

    inbound: Counter[str] = Counter()
    network_counts: list[int] = []
    cluster_routes: list[str] = []
    broken: set[tuple[str, str]] = set()
    network_pages = 0
    schema_mismatch = 0

    for route, (url, source, path) in pages.items():
        targets: set[str] = set()
        for href in HREF_RE.findall(source):
            href = html.unescape(href.strip())
            if not href or href.startswith(
                ("#", "tel:", "sms:", "mailto:", "javascript:", "data:")
            ):
                continue
            absolute = urljoin(url, href)
            parsed = urlsplit(absolute)
            if parsed.netloc not in ("xn--ru4bi8s1tac0p.kr", "학습코칭.kr"):
                continue
            target = key(absolute)
            if target in pages:
                targets.add(target)
            elif not re.search(r"\.[A-Za-z0-9]{2,5}/?$", parsed.path):
                broken.add((route, target))
        for target in targets:
            inbound[target] += 1

        if not is_cluster_page(route):
            continue
        cluster_routes.append(route)
        matches = NETWORK_RE.findall(source)
        if len(matches) != 1:
            errors.append(f"{path.relative_to(ROOT)}: network marker={len(matches)}")
            continue
        network_pages += 1
        block = matches[0]
        visible_urls = [html.unescape(value) for value in NETWORK_HREF_RE.findall(block)]
        network_counts.append(len(visible_urls))
        if len(visible_urls) not in (11, 12) or len(visible_urls) != len(set(visible_urls)):
            errors.append(
                f"{path.relative_to(ROOT)}: network links={len(visible_urls)}/{len(set(visible_urls))}"
            )
        if url in visible_urls:
            errors.append(f"{path.relative_to(ROOT)}: 자기 자신 링크")
        try:
            schema_urls = network_schema_urls(source, url)
            if schema_urls != visible_urls:
                schema_mismatch += 1
        except (ValueError, json.JSONDecodeError) as exc:
            errors.append(f"{path.relative_to(ROOT)}: {exc}")

    all_inbound = sorted(inbound[route] for route in sitemap)
    cluster_inbound = sorted(inbound[route] for route in cluster_routes)
    if broken:
        errors.append(f"broken internal targets={len(broken)}")
    if len(cluster_routes) != 4452 or network_pages != 4452:
        errors.append(f"cluster/network pages={len(cluster_routes)}/{network_pages}")
    if network_counts and min(network_counts) < 11:
        errors.append(f"network min links={min(network_counts)}")
    if cluster_inbound and min(cluster_inbound) < 11:
        errors.append(f"cluster inbound min={min(cluster_inbound)}")
    if schema_mismatch:
        errors.append(f"visible/schema network mismatch={schema_mismatch}")

    report = {
        "ok": not errors,
        "sitemap_pages": len(sitemap),
        "cluster_pages": len(cluster_routes),
        "network_pages": network_pages,
        "links_per_network_page_min": min(network_counts),
        "links_per_network_page_median": statistics.median(network_counts),
        "cluster_inbound_min": min(cluster_inbound),
        "cluster_inbound_p10": percentile(cluster_inbound, 0.1),
        "cluster_inbound_median": statistics.median(cluster_inbound),
        "site_inbound_p10": percentile(all_inbound, 0.1),
        "site_inbound_median": statistics.median(all_inbound),
        "broken_internal_targets": len(broken),
        "visible_schema_mismatch": schema_mismatch,
        "errors": len(errors),
        "samples": errors[:20],
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
