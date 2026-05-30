"""
vault_graph.py — Wikilink graph analysis for the vault.

Commands exposed via vault_intelligence.py:
  graph-analyze [--scope Memory|vault] [--top N]
"""

import os
import re
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

from ai_provider import ask_ai

load_dotenv()

VAULT_PATH: str = os.environ.get("VAULT_PATH", "")

_NEVER_SCAN: list[str] = [
    "/grok/",
    "/00_Inbox/grok",
    "/venv/",
    "/node_modules/",
    "/.git/",
    "/dist/",
    "/build/",
    "/target/",
    "/__pycache__/",
    "VocalCoach",
    "youtube_system",
]

_WIKILINK_RE = re.compile(r'\[\[([^\]|\n#]+?)(?:\|[^\]]*)?(?:#[^\]]*)?\]\]')


def _should_skip_path(p: Path, vault: Path) -> bool:
    try:
        rel = str(p.relative_to(vault)).lower()
    except ValueError:
        rel = str(p).lower()
    return any(bad.lower() in rel for bad in _NEVER_SCAN)


def _build_link_graph(
    scan_root: Path, vault: Path
) -> tuple[dict[str, set[str]], dict[str, str]]:
    """
    Return (graph, slug_map) where:
      graph    = {rel_path: set_of_linked_rel_paths}
      slug_map = {lowercase_stem: rel_path}  for all notes
    """
    graph: dict[str, set[str]] = {}
    slug_map: dict[str, str] = {}

    for md in scan_root.rglob("*.md"):
        if _should_skip_path(md, vault):
            continue
        rel = str(md.relative_to(vault).with_suffix(""))
        graph[rel] = set()
        slug_map[md.stem.lower()] = rel

    for md in scan_root.rglob("*.md"):
        if _should_skip_path(md, vault):
            continue
        rel = str(md.relative_to(vault).with_suffix(""))
        try:
            text = md.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        for m in _WIKILINK_RE.finditer(text):
            raw = m.group(1).strip()
            target_stem = Path(raw).name.lower()
            target_rel = slug_map.get(target_stem)
            if target_rel and target_rel != rel:
                graph[rel].add(target_rel)

    return graph, slug_map


def _compute_graph_stats(graph: dict[str, set[str]]) -> dict:
    in_degree: dict[str, int] = {n: 0 for n in graph}
    out_degree: dict[str, int] = {n: len(links) for n, links in graph.items()}

    for links in graph.values():
        for target in links:
            if target in in_degree:
                in_degree[target] += 1

    total_degree = {n: in_degree[n] + out_degree[n] for n in graph}
    orphans = sorted(n for n, d in total_degree.items() if d == 0)

    undirected: dict[str, set[str]] = {n: set() for n in graph}
    for node, links in graph.items():
        for t in links:
            if t in undirected:
                undirected[node].add(t)
                undirected[t].add(node)

    visited: set[str] = set()
    components: list[set[str]] = []
    for node in undirected:
        if node not in visited:
            component: set[str] = set()
            queue = [node]
            while queue:
                curr = queue.pop()
                if curr in visited:
                    continue
                visited.add(curr)
                component.add(curr)
                queue.extend(undirected[curr] - visited)
            components.append(component)

    components.sort(key=len, reverse=True)

    return {
        "total_degree": total_degree,
        "in_degree": in_degree,
        "out_degree": out_degree,
        "orphans": orphans,
        "components": components,
    }


def run_graph_analyze(scope: str = "vault", top_n: int = 15) -> None:
    """Build the wikilink graph and write a hub/orphan/cluster report."""
    vault = Path(VAULT_PATH)

    if scope.lower() in {"memory", "core"}:
        scan_root = vault / "Memory"
        scope_label = "Memory/"
    else:
        scan_root = vault
        scope_label = "vault"

    print(f"Building wikilink graph ({scope_label})…")
    graph, _ = _build_link_graph(scan_root, vault)
    stats = _compute_graph_stats(graph)

    n_nodes = len(graph)
    n_edges = sum(len(v) for v in graph.values())
    n_orphans = len(stats["orphans"])
    n_components = len(stats["components"])
    date_str = datetime.now().strftime("%Y-%m-%d")

    print(f"  {n_nodes} notes · {n_edges} links · {n_orphans} orphans · {n_components} clusters")

    hubs = sorted(stats["total_degree"].items(), key=lambda x: x[1], reverse=True)[:top_n]
    hubs_lines = [
        f"- [[{node}]] — {deg} connections "
        f"(in: {stats['in_degree'].get(node, 0)}, out: {stats['out_degree'].get(node, 0)})"
        for node, deg in hubs
        if deg > 0
    ]

    orphans_sample = stats["orphans"][:40]
    orphans_lines = [f"- [[{o}]]" for o in orphans_sample]
    orphans_note = f"*{n_orphans} total — showing first {len(orphans_sample)}*\n\n" if n_orphans > 40 else ""

    cluster_lines: list[str] = []
    for i, comp in enumerate(stats["components"][:6], 1):
        sample = sorted(comp)[:6]
        cluster_lines.append(f"### Cluster {i} ({len(comp)} notes)")
        cluster_lines.extend(f"- [[{n}]]" for n in sample)
        if len(comp) > 6:
            cluster_lines.append(f"- *…and {len(comp) - 6} more*")
        cluster_lines.append("")

    bridge_md = ""
    big = [c for c in stats["components"] if len(c) > 3]
    if len(big) >= 2:
        sample_a = sorted(big[0])[:6]
        sample_b = sorted(big[1])[:6]
        print("Asking AI for bridge note between the two largest clusters…")
        bridge_content = ask_ai(
            "Two clusters of notes in a personal knowledge vault have no wikilink connections.\n"
            "Find the strongest conceptual bridge — the insight or practice that naturally links them.\n"
            "Write it as an Obsidian permanent note: ≤150 words, plain prose, include [[wikilinks]] "
            "to at least one note from each cluster. Start with a clear central claim.\n\n"
            f"CLUSTER A ({len(big[0])} notes — sample):\n"
            + "\n".join(f"  {n}" for n in sample_a)
            + f"\n\nCLUSTER B ({len(big[1])} notes — sample):\n"
            + "\n".join(f"  {n}" for n in sample_b)
        )
        bridge_slug = f"bridge-cluster-1-2-{date_str}"
        bridge_md = (
            f"## AI Bridge Note Suggestion\n\n"
            f"*Gap between Cluster 1 ({len(big[0])} notes) and Cluster 2 ({len(big[1])} notes):*\n\n"
            f"{bridge_content}\n\n"
            f"To save this as a permanent note:\n"
            f"```\n"
            f"# create Memory/Permanent/{bridge_slug}.md\n"
            f"# paste the content above, then link both clusters\n"
            f"```\n\n"
        )

    report = (
        f"# Vault Graph Report — {date_str}\n\n"
        f"> Scope: `{scope_label}` · {n_nodes} notes · {n_edges} links · "
        f"{n_orphans} orphans · {n_components} clusters\n\n"
        f"## Hub Notes (top {len(hubs_lines)} by connections)\n\n"
        + ("\n".join(hubs_lines) if hubs_lines else "*No connected notes found.*")
        + f"\n\n## Orphaned Notes (no connections)\n\n"
        + orphans_note
        + ("\n".join(orphans_lines) if orphans_lines else "*None — great!*")
        + f"\n\n## Cluster Breakdown\n\n"
        f"*{n_components} disconnected islands — ideally this should shrink over time.*\n\n"
        + "\n".join(cluster_lines)
        + (f"\n{bridge_md}" if bridge_md else "")
    )

    out_path = vault / "Memory" / f"Graph-Report-{date_str}.md"
    out_path.write_text(report, encoding="utf-8")
    print(f"Graph report written: {out_path}")
    if hubs_lines:
        print(f"Top hub: {hubs[0][0]} ({hubs[0][1]} connections)")
    print(f"Orphans to review: {n_orphans}")
