"""Orphan/isolation analyzer.

Merges: obsidian-orphan-analyzer.py
"""

from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path

from .core import FileIndex, WIKI_RE


def analyze_orphans(index: FileIndex) -> dict:
    """Classify all MD files by link connectivity.

    Returns dict with stats and classified file lists.
    """
    outgoing = index.wikilink_targets()

    # build incoming
    incoming: dict[str, set[str]] = defaultdict(set)
    for src, tgts in outgoing.items():
        for t in tgts:
            incoming[t].add(src)

    zero_both, only_out, only_in, connected = [], [], [], []
    for fp in sorted(index.md_files):
        has_out = fp in outgoing
        in_count = len(incoming.get(fp, set()))
        if not has_out and in_count == 0:
            # check if it has ANY wikilinks (all broken)
            content = (index.repo / fp).read_text(encoding="utf-8", errors="ignore")
            has_any = bool(WIKI_RE.search(content))
            zero_both.append((fp, "broken" if has_any else "none"))
        elif has_out and in_count == 0:
            only_out.append(fp)
        elif not has_out and in_count > 0:
            only_in.append(fp)
        else:
            connected.append(fp)

    total = len(index.md_files)

    # directory clusters for zero-both
    dir_counts: dict[str, int] = defaultdict(int)
    none_dirs: dict[str, int] = defaultdict(int)
    broken_dirs: dict[str, int] = defaultdict(int)
    for fp, typ in zero_both:
        d = str(Path(fp).parent) or "."
        dir_counts[d] += 1
        (none_dirs if typ == "none" else broken_dirs)[d] += 1

    total_links = sum(len(v) for v in outgoing.values())

    return {
        "total": total,
        "total_links": total_links,
        "connected": connected,
        "only_outgoing": only_out,
        "only_incoming": only_in,
        "zero_both": zero_both,
        "dir_counts": dir_counts,
        "none_dirs": none_dirs,
        "broken_dirs": broken_dirs,
    }


def cmd_orphan(index: FileIndex, limit: int, by_dir: bool):
    """CLI handler for 'kb orphan'."""
    result = analyze_orphans(index)
    total = result["total"]

    print(f"文件总数: {total}")
    print(f"wikilink 总数: {result['total_links']}")
    print()
    print(f"connected:     {len(result['connected']):5d}  ({100*len(result['connected'])/total:.1f}%)")
    print(f"only outgoing: {len(result['only_outgoing']):5d}  ({100*len(result['only_outgoing'])/total:.1f}%)")
    print(f"only incoming: {len(result['only_incoming']):5d}  ({100*len(result['only_incoming'])/total:.1f}%)")
    print(f"zero both:     {len(result['zero_both']):5d}  ({100*len(result['zero_both'])/total:.1f}%)")

    none_count = sum(1 for _, t in result["zero_both"] if t == "none")
    broken_count = sum(1 for _, t in result["zero_both"] if t == "broken")
    print(f"  no links:    {none_count:5d}")
    print(f"  all broken:  {broken_count:5d}")

    if by_dir:
        print()
        print("零连接文件按目录 (>=5):")
        for d, c in sorted(result["dir_counts"].items(), key=lambda x: -x[1]):
            if c >= 5:
                print(f"  {d}/: {c:3d}  (none={result['none_dirs'].get(d,0)}, "
                      f"broken={result['broken_dirs'].get(d,0)})")

    if limit > 0:
        print()
        print(f"零连接文件 (前 {limit}):")
        for fp, typ in result["zero_both"][:limit]:
            print(f"  [{typ:6s}] {fp}")
