"""Generate read-only Obsidian Graph View group suggestions."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

from .graph import build_graph


def _frontmatter(text: str) -> dict[str, Any]:
    if not text.startswith("---\n") or "\n---\n" not in text[4:]:
        return {}
    end = text.find("\n---\n", 4)
    value = yaml.safe_load(text[4:end])
    return value if isinstance(value, dict) else {}


def _add(groups: dict[str, set[str]], name: str, path: str) -> None:
    groups.setdefault(name, set()).add(path)


def suggest_groups(index: Any, limit: int = 50) -> list[dict[str, Any]]:
    """Return deterministic groups based on paths, metadata, and graph health."""
    if limit < 1:
        raise ValueError("limit must be >= 1")
    groups: dict[str, set[str]] = {}
    for path in sorted(index.md_files):
        _add(groups, f"path:{Path(path).parent.as_posix()}", path)
        metadata = _frontmatter((index.repo / path).read_text(encoding="utf-8", errors="ignore"))
        for tag in metadata.get("tags", []) if isinstance(metadata.get("tags"), list) else []:
            _add(groups, f"tag:{str(tag).lstrip('#')}", path)
        for field in ("type", "status"):
            value = metadata.get(field)
            if value is not None and not isinstance(value, (dict, list)):
                _add(groups, f"{field}:{value}", path)

    graph = build_graph(index)
    for path in graph.nodes:
        if graph.in_degree(path) + graph.out_degree(path) == 0:
            _add(groups, "health:orphan", path)
        if graph.in_degree(path) + graph.out_degree(path) >= 10:
            _add(groups, "health:hub", path)
    for path in index.md_files:
        text = (index.repo / path).read_text(encoding="utf-8", errors="ignore")
        if any(index.resolve_wikilink_status(path, match.group(1))[0] != "resolved"
               for match in re.finditer(r"(?<!`)\[\[([^\]\n]+)\]\]", text)):
            _add(groups, "health:broken-link", path)

    rows = []
    for name, paths in groups.items():
        if not paths:
            continue
        kind, _, value = name.partition(":")
        rows.append({"name": name, "kind": kind, "value": value,
                     "query": name, "count": len(paths), "paths": sorted(paths)})
    rows.sort(key=lambda row: (-row["count"], row["name"]))
    return rows[:limit]
