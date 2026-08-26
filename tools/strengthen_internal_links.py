from __future__ import annotations

"""Build a crawlable, locality-level link network across the core landing pages.

The default mode is a validated dry run.  ``--apply`` writes only the 4,452
locality detail pages that belong to the 371 twelve-page learning clusters.
"""

import argparse
import html
import json
import re
import statistics
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urljoin, urlsplit


ROOT = Path(__file__).resolve().parents[1]
BASE_URL = "https://xn--ru4bi8s1tac0p.kr"
RELEASE_DATE = "2026-08-27"
START_MARKER = "<!-- local-study-network:start -->"
END_MARKER = "<!-- local-study-network:end -->"

SUBJECT_CATEGORIES = (
    ("초등학생학원", "초등"),
    ("중학생학원", "중등"),
    ("고등학생학원", "고등"),
    ("중등영어학원", "중등 영어"),
    ("중등수학학원", "중등 수학"),
    ("고등영어학원", "고등 영어"),
    ("고등수학학원", "고등 수학"),
    ("영수학원", "영어·수학"),
)
NATIONAL_CHILD_ORDER = (
    ("초등영수학원", "초등 영어·수학"),
    ("중등영수학원", "중등 영어·수학"),
    ("고등영수학원", "고등 영어·수학"),
)
DISPLAY_ORDER = (
    "national-hub",
    "초등학생학원",
    "초등영수학원",
    "중학생학원",
    "중등영어학원",
    "중등수학학원",
    "중등영수학원",
    "고등학생학원",
    "고등영어학원",
    "고등수학학원",
    "고등영수학원",
    "영수학원",
)

CANONICAL_RE = re.compile(
    r'<link\b(?=[^>]*\brel=["\']canonical["\'])[^>]*\bhref=["\'](.*?)["\']',
    re.I | re.S,
)
H1_RE = re.compile(r"<h1\b[^>]*>(.*?)</h1>", re.I | re.S)
HREF_RE = re.compile(r'<a\b[^>]*\bhref=["\'](.*?)["\']', re.I | re.S)
JSONLD_RE = re.compile(
    r'(<script\b[^>]*type=["\']application/ld\+json["\'][^>]*>)(.*?)(</script>)',
    re.I | re.S,
)
NETWORK_RE = re.compile(
    re.escape(START_MARKER) + r".*?" + re.escape(END_MARKER), re.S
)
DATE_MODIFIED_RE = re.compile(
    r'("dateModified"\s*:\s*")[0-9]{4}-[0-9]{2}-[0-9]{2}(")'
)


@dataclass(frozen=True)
class Member:
    key: str
    kind: str
    label: str
    url: str
    path: Path


@dataclass(frozen=True)
class Cluster:
    locality: str
    members: tuple[Member, ...]


@dataclass(frozen=True)
class Plan:
    path: Path
    before: str
    after: str
    links: tuple[tuple[str, str, str], ...]


def clean_text(value: str) -> str:
    return re.sub(
        r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", value))
    ).strip()


def canonical_key(value: str) -> str:
    parsed = urlsplit(html.unescape(value))
    route = unquote(parsed.path).replace("\\", "/")
    route = re.sub(r"/index\.html/?$", "/", route, flags=re.I)
    route = "/" + route.strip("/")
    return "/" if route == "/" else route + "/"


def canonical_of(source: str) -> str:
    match = CANONICAL_RE.search(source)
    if not match:
        raise ValueError("canonical 없음")
    return html.unescape(match.group(1)).rstrip("/") + "/"


def h1_of(source: str) -> str:
    match = H1_RE.search(source)
    if not match:
        raise ValueError("H1 없음")
    return clean_text(match.group(1))


def public_pages() -> list[Path]:
    return [
        path
        for path in ROOT.rglob("index.html")
        if ".vercel" not in path.parts and "tmp" not in path.parts
    ]


def source_map() -> tuple[dict[Path, str], dict[str, Path]]:
    sources: dict[Path, str] = {}
    by_url: dict[str, Path] = {}
    for path in public_pages():
        source = path.read_text(encoding="utf-8", errors="strict")
        sources[path] = source
        url = canonical_of(source)
        if 'content="noindex' in source or "content='noindex" in source:
            continue
        key = canonical_key(url)
        if key in by_url:
            raise ValueError(f"canonical 중복: {key}")
        by_url[key] = path
    return sources, by_url


def national_hub_from_subject(
    subject_url: str, source: str, by_url: dict[str, Path]
) -> Path:
    candidates: list[Path] = []
    for href in HREF_RE.findall(source):
        absolute = urljoin(subject_url, html.unescape(href))
        key = canonical_key(absolute)
        parts = tuple(part for part in key.strip("/").split("/") if part)
        if len(parts) != 4 or parts[0] != "전국학원":
            continue
        target = by_url.get(key)
        if target is not None:
            candidates.append(target)
    unique = list(dict.fromkeys(candidates))
    if len(unique) != 1:
        raise ValueError(f"전국 지역 종합 링크={len(unique)}")
    return unique[0]


def member(
    key: str, kind: str, path: Path, sources: dict[Path, str]
) -> Member:
    source = sources[path]
    return Member(key, kind, h1_of(source), canonical_of(source), path)


def build_clusters(
    sources: dict[Path, str], by_url: dict[str, Path]
) -> list[Cluster]:
    category_members: dict[str, dict[str, Path]] = {}
    for category, _ in SUBJECT_CATEGORIES:
        directory = ROOT / "과목별학원" / category
        found = {
            path.parent.name: path
            for path in directory.glob("*/index.html")
            if path in sources
        }
        if len(found) != 371:
            raise ValueError(f"{category}: 상세 페이지 {len(found)}/371")
        category_members[category] = found

    slugs = sorted(category_members[SUBJECT_CATEGORIES[0][0]])
    clusters: list[Cluster] = []
    used_national_hubs: set[Path] = set()
    for slug in slugs:
        members_by_key: dict[str, Member] = {}
        for category, kind in SUBJECT_CATEGORIES:
            path = category_members[category].get(slug)
            if path is None:
                raise ValueError(f"{slug}: {category} 페이지 없음")
            members_by_key[category] = member(category, kind, path, sources)

        seed = members_by_key[SUBJECT_CATEGORIES[0][0]]
        hub_path = national_hub_from_subject(seed.url, sources[seed.path], by_url)
        if hub_path in used_national_hubs:
            raise ValueError(f"{slug}: 전국 지역 종합 중복 {hub_path}")
        used_national_hubs.add(hub_path)
        members_by_key["national-hub"] = member(
            "national-hub", "지역 종합", hub_path, sources
        )

        for child, kind in NATIONAL_CHILD_ORDER:
            child_path = hub_path.parent / child / "index.html"
            if child_path not in sources:
                raise ValueError(f"{slug}: {child} 페이지 없음")
            members_by_key[child] = member(child, kind, child_path, sources)

        ordered = tuple(members_by_key[key] for key in DISPLAY_ORDER)
        locality = h1_of(sources[hub_path]).removesuffix(" 학원")
        clusters.append(Cluster(locality, ordered))

    if len(clusters) != 371 or len(used_national_hubs) != 371:
        raise ValueError(
            f"클러스터/전국 지역 종합={len(clusters)}/{len(used_national_hubs)}"
        )
    return clusters


def graph_nodes(value: object) -> list[dict]:
    if isinstance(value, dict):
        graph = value.get("@graph")
        if isinstance(graph, list):
            return [node for node in graph if isinstance(node, dict)]
        return [value]
    return []


def center_link(source: str, by_url: dict[str, Path]) -> tuple[str, str] | None:
    for match in JSONLD_RE.finditer(source):
        try:
            data = json.loads(match.group(2))
        except json.JSONDecodeError:
            continue
        for node in graph_nodes(data):
            node_id = node.get("@id")
            name = node.get("name")
            if not isinstance(node_id, str) or not isinstance(name, str):
                continue
            key = canonical_key(node_id.split("#", 1)[0])
            if "와와학습코칭센터" not in key or key not in by_url:
                continue
            target_source = by_url[key].read_text(encoding="utf-8")
            return h1_of(target_source), canonical_of(target_source)
    return None


def render_block(
    cluster: Cluster,
    current: Member,
    center: tuple[str, str] | None,
) -> tuple[str, tuple[tuple[str, str, str], ...]]:
    cards: list[str] = []
    links: list[tuple[str, str, str]] = []
    for target in cluster.members:
        if target.url == current.url:
            cards.append(
                '<span class="local-study-network-card is-current" '
                'aria-current="page">'
                f'<small>{html.escape(target.kind)}</small>'
                f'<strong>{html.escape(target.label)}</strong></span>'
            )
            continue
        cards.append(
            f'<a class="local-study-network-card" href="{html.escape(target.url, quote=True)}">'
            f'<small>{html.escape(target.kind)}</small>'
            f'<strong>{html.escape(target.label)}</strong></a>'
        )
        links.append((target.kind, target.label, target.url))
    if center is not None:
        label, url = center
        if url != current.url and all(url != item[2] for item in links):
            cards.append(
                f'<a class="local-study-network-card is-center" href="{html.escape(url, quote=True)}">'
                f'<small>센터 정보</small><strong>{html.escape(label)}</strong></a>'
            )
            links.append(("센터 정보", label, url))

    block = (
        f"{START_MARKER}\n"
        '<section class="local-study-network" aria-labelledby="local-study-network-title">'
        '<div class="local-study-network-inner">'
        '<div class="local-study-network-head">'
        '<p>같은 지역에서 함께 확인하기</p>'
        f'<h2 id="local-study-network-title">{html.escape(cluster.locality)} 과목·학년별 학습 안내</h2>'
        '<span>현재 페이지와 같은 지역의 과정만 모아 비교할 수 있습니다.</span>'
        '</div><nav class="local-study-network-grid" aria-label="같은 지역 학습 페이지">'
        + "".join(cards)
        + f"</nav></div></section>\n{END_MARKER}"
    )
    return block, tuple(links)


def update_jsonld(
    source: str,
    current_url: str,
    locality: str,
    links: tuple[tuple[str, str, str], ...],
) -> str:
    node_id = current_url + "#local-study-network"
    updated = False

    def replace(match: re.Match[str]) -> str:
        nonlocal updated
        if updated:
            return match.group(0)
        try:
            data = json.loads(match.group(2))
        except json.JSONDecodeError:
            return match.group(0)
        if not isinstance(data, dict) or not isinstance(data.get("@graph"), list):
            return match.group(0)
        graph = data["@graph"]
        if not any(
            isinstance(node, dict)
            and (
                node.get("url") == current_url
                or node.get("@id") == current_url + "#webpage"
            )
            and "WebPage"
            in (
                node.get("@type")
                if isinstance(node.get("@type"), list)
                else [node.get("@type")]
            )
            for node in graph
        ):
            return match.group(0)

        graph[:] = [
            node
            for node in graph
            if not (isinstance(node, dict) and node.get("@id") == node_id)
        ]
        network_node = {
            "@type": "ItemList",
            "@id": node_id,
            "name": f"{locality} 과목·학년별 학습 안내",
            "numberOfItems": len(links),
            "itemListElement": [
                {
                    "@type": "ListItem",
                    "position": position,
                    "name": label,
                    "url": url,
                }
                for position, (_, label, url) in enumerate(links, 1)
            ],
        }
        anchor_index = next(
            (
                index
                for index, node in enumerate(graph)
                if isinstance(node, dict)
                and str(node.get("@id", "")).endswith(
                    ("#priority-search-intent", "#school-reference")
                )
            ),
            len(graph),
        )
        graph.insert(anchor_index, network_node)
        for node in graph:
            if not isinstance(node, dict):
                continue
            node_types = node.get("@type")
            node_types = node_types if isinstance(node_types, list) else [node_types]
            if "WebPage" not in node_types:
                continue
            if node.get("url") != current_url and node.get("@id") != current_url + "#webpage":
                continue
            has_part = node.get("hasPart")
            if not isinstance(has_part, list):
                has_part = []
            has_part = [
                item
                for item in has_part
                if not (isinstance(item, dict) and item.get("@id") == node_id)
            ]
            anchor_index = next(
                (
                    index
                    for index, item in enumerate(has_part)
                    if isinstance(item, dict)
                    and str(item.get("@id", "")).endswith(
                        ("#priority-search-intent", "#school-reference")
                    )
                ),
                len(has_part),
            )
            has_part.insert(anchor_index, {"@id": node_id})
            node["hasPart"] = has_part
            break
        updated = True
        payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
        return match.group(1) + payload + match.group(3)

    result = JSONLD_RE.sub(replace, source)
    if not updated:
        raise ValueError(f"WebPage JSON-LD 없음: {current_url}")
    return result


def transform(
    source: str,
    cluster: Cluster,
    current: Member,
    by_url: dict[str, Path],
) -> tuple[str, tuple[tuple[str, str, str], ...]]:
    block, links = render_block(cluster, current, center_link(source, by_url))
    source = update_jsonld(source, current.url, cluster.locality, links)
    source = DATE_MODIFIED_RE.sub(
        rf"\g<1>{RELEASE_DATE}\g<2>", source
    )
    if NETWORK_RE.search(source):
        source = NETWORK_RE.sub(block, source, count=1)
        return source, links
    closing = source.lower().rfind("</main>")
    if closing < 0:
        raise ValueError(f"main 닫힘 태그 없음: {current.path}")
    source = source[:closing] + block + "\n" + source[closing:]
    return source, links


def validate_plan(
    plans: list[Plan],
    by_url: dict[str, Path],
) -> list[str]:
    errors: list[str] = []
    if len(plans) != 4452:
        errors.append(f"network pages={len(plans)}/4452")
    counts: list[int] = []
    for plan in plans:
        relative = plan.path.relative_to(ROOT).as_posix()
        if plan.after.count(START_MARKER) != 1 or plan.after.count(END_MARKER) != 1:
            errors.append(f"{relative}: marker 수 오류")
        if plan.before.count("<h1") != plan.after.count("<h1"):
            errors.append(f"{relative}: H1 수 변경")
        current_url = canonical_of(plan.after)
        network = NETWORK_RE.search(plan.after)
        if not network:
            errors.append(f"{relative}: 네트워크 블록 없음")
            continue
        if network.group(0).count('aria-current="page"') != 1:
            errors.append(f"{relative}: 현재 페이지 표시 오류")
        hrefs = [
            html.unescape(value)
            for value in re.findall(
                r'<a\b[^>]*class="[^"]*local-study-network-card[^"]*"[^>]*href="(.*?)"',
                network.group(0),
                re.I | re.S,
            )
        ]
        counts.append(len(hrefs))
        if len(hrefs) not in (11, 12):
            errors.append(f"{relative}: 네트워크 링크={len(hrefs)}")
        if len(hrefs) != len(set(hrefs)):
            errors.append(f"{relative}: 네트워크 링크 중복")
        if current_url in hrefs:
            errors.append(f"{relative}: 자기 자신 링크")
        for href in hrefs:
            if canonical_key(href) not in by_url:
                errors.append(f"{relative}: 링크 대상 없음 {href}")
    if counts and (min(counts) < 11 or statistics.median(counts) < 11):
        errors.append(
            f"network links min/median={min(counts)}/{statistics.median(counts)}"
        )
    return errors


def atomic_write(path: Path, value: str) -> None:
    temporary = path.with_name(path.name + ".links.tmp")
    temporary.write_text(value, encoding="utf-8", newline="\n")
    temporary.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    sources, by_url = source_map()
    clusters = build_clusters(sources, by_url)
    plans: list[Plan] = []
    for cluster in clusters:
        for current in cluster.members:
            after, links = transform(
                sources[current.path], cluster, current, by_url
            )
            plans.append(Plan(current.path, sources[current.path], after, links))

    errors = validate_plan(plans, by_url)
    changed = sum(plan.before != plan.after for plan in plans)
    link_counts = [len(plan.links) for plan in plans]
    report = {
        "mode": "APPLY" if args.apply else "DRY-RUN",
        "clusters": len(clusters),
        "pages": len(plans),
        "changed": changed,
        "links_per_page_min": min(link_counts),
        "links_per_page_median": statistics.median(link_counts),
        "links_per_page_max": max(link_counts),
        "center_links": sum(len(plan.links) == 12 for plan in plans),
        "errors": len(errors),
        "samples": errors[:20],
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if errors:
        return 1
    if args.apply:
        for plan in plans:
            if plan.before != plan.after:
                atomic_write(plan.path, plan.after)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
