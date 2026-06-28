"""Graph queries: islands, centrality, hub detection.

Uses networkx for graph algorithms on the wikilink graph.
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

try:
    import networkx as nx
except ImportError:
    nx = None  # type: ignore

from .core import FileIndex


def build_graph(index: FileIndex) -> "nx.DiGraph":
    """Build directed graph from wikilinks. Nodes = files, edges = wikilinks."""
    if nx is None:
        raise ImportError("networkx required: pip install networkx")
    G = nx.DiGraph()
    for fp in index.md_files:
        G.add_node(fp)
    outgoing = index.wikilink_targets()
    for src, tgts in outgoing.items():
        for tgt in tgts:
            G.add_edge(src, tgt)
    return G


def find_islands(G: "nx.DiGraph", min_links: int = 0) -> list[tuple[str, int]]:
    """Find nodes with total degree <= min_links. Returns (node, degree) sorted by degree."""
    islands = []
    for node in G.nodes():
        deg = G.in_degree(node) + G.out_degree(node)
        if deg <= min_links:
            islands.append((node, deg))
    return sorted(islands, key=lambda x: x[1])


def find_hubs(G: "nx.DiGraph", top_n: int = 20) -> list[tuple[str, int, int]]:
    """Find hub nodes by total degree. Returns (node, in_degree, out_degree)."""
    hubs = []
    for node in G.nodes():
        in_d = G.in_degree(node)
        out_d = G.out_degree(node)
        hubs.append((node, in_d, out_d))
    hubs.sort(key=lambda x: x[1] + x[2], reverse=True)
    return hubs[:top_n]


def find_wanted(G: "nx.DiGraph", index: FileIndex) -> list[tuple[str, int]]:
    """Find wanted pages: targets referenced by wikilinks but not existing as files.

    Returns (target_name, reference_count) sorted by count.
    """
    wanted: dict[str, int] = defaultdict(int)
    existing = set(index.md_files)
    outgoing = index.wikilink_targets()
    for src, tgts in outgoing.items():
        for tgt in tgts:
            if tgt not in existing:
                wanted[tgt] += 1
    return sorted(wanted.items(), key=lambda x: -x[1])


def communities(G: "nx.DiGraph") -> dict[str, int]:
    """Detect communities using label propagation on undirected version."""
    if nx is None:
        raise ImportError("networkx required")
    UG = G.to_undirected()
    try:
        communities_gen = nx.community.label_propagation_communities(UG)
        result = {}
        for i, comm in enumerate(communities_gen):
            for node in comm:
                result[node] = i
        return result
    except Exception:
        return {}


def cmd_graph(index: FileIndex, mode: str, top_n: int, min_links: int, show_edges: bool):
    """CLI handler for 'kb graph'."""
    G = build_graph(index)
    nodes = G.number_of_nodes()
    edges = G.number_of_edges()
    print(f"图: {nodes} 节点, {edges} 边")

    if mode in ("islands", "all"):
        islands = find_islands(G, min_links=min_links)
        print(f"\n孤岛 (degree<={min_links}): {len(islands)}")
        for node, deg in islands[:top_n]:
            print(f"  [{deg}] {node}")

    if mode in ("hubs", "all"):
        hubs = find_hubs(G, top_n=top_n)
        print(f"\n枢纽 (top {top_n}):")
        for node, in_d, out_d in hubs:
            print(f"  in={in_d:3d} out={out_d:3d}  {node}")

    if mode in ("wanted", "all"):
        wanted = find_wanted(G, index)
        print(f"\n被引用但不存在: {len(wanted)}")
        for target, count in wanted[:top_n]:
            print(f"  [{count:3d}] {target}")

    if mode in ("communities", "all"):
        comms = communities(G)
        if comms:
            # group by community id
            groups: dict[int, list[str]] = defaultdict(list)
            for node, cid in comms.items():
                groups[cid].append(node)
            # sort by size
            sorted_groups = sorted(groups.items(), key=lambda x: -len(x[1]))
            print(f"\n社区: {len(sorted_groups)} 个")
            for cid, members in sorted_groups[:10]:
                print(f"  社区 {cid}: {len(members)} 文件")
                for m in members[:5]:
                    print(f"    {m}")
                if len(members) > 5:
                    print(f"    ... 另有 {len(members)-5}")

    if show_edges:
        print(f"\n边列表 (前 100):")
        for i, (u, v) in enumerate(list(G.edges())[:100]):
            print(f"  {u} → {v}")
        if edges > 100:
            print(f"  ... 另有 {edges-100} 条边")
