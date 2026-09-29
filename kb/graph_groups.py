"""Generate read-only Obsidian Graph View group suggestions."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, TypedDict

import yaml

from .graph import build_graph
from .graph_colors import get_group_palette

GROUP_COLORS = get_group_palette("default")


class GroupSuggestion(TypedDict):
    """One deterministic Obsidian Graph View group suggestion."""

    name: str
    kind: str
    value: str
    query: str
    obsidian_query: str
    property_query: str | None
    color: str
    requires_kb_tool: bool
    kb_command: str | None
    count: int
    paths: list[str]


class GroupReport(TypedDict):
    """Structured metadata and rows for a graph-groups JSON report."""

    theme: str
    limit: int
    min_count: int
    groups: list[GroupSuggestion]


def _obsidian_query(kind: str, value: str) -> str:
    if kind == "tag":
        return f"tag:#{value}"
    if kind == "path":
        return f"path:{value}" if value != "." else "path:/"
    if kind in {"type", "status"}:
        return f"[{kind}:{value}]"
    return ""


def _property_query(kind: str, value: str) -> str | None:
    return f"{kind}:{value}" if kind in {"type", "status"} else None


def _kb_command(kind: str) -> str | None:
    return {"orphan": "kb orphan", "hub": "kb graph -m hubs",
            "broken-link": "kb scan"}.get(kind.removeprefix("health:"))


def _frontmatter(text: str) -> dict[str, Any]:
    if not text.startswith("---\n") or "\n---\n" not in text[4:]:
        return {}
    end = text.find("\n---\n", 4)
    value = yaml.safe_load(text[4:end])
    return value if isinstance(value, dict) else {}


def _add(groups: dict[str, set[str]], name: str, path: str) -> None:
    groups.setdefault(name, set()).add(path)


def _metadata_tags(metadata: dict[str, Any]) -> list[str]:
    """Normalize scalar/list tags and the singular tag frontmatter key."""
    values = metadata.get("tags", metadata.get("tag", []))
    if isinstance(values, (str, int, float)):
        values = [values]
    if not isinstance(values, list):
        return []
    return [str(value).lstrip("#").strip() for value in values if str(value).strip()]


def suggest_groups(index: Any, limit: int = 50, theme: str = "default",
                   min_count: int = 1) -> list[GroupSuggestion]:
    """Return deterministic groups based on paths, metadata, and graph health."""
    if limit < 1:
        raise ValueError("limit must be >= 1")
    if min_count < 1:
        raise ValueError("min_count must be >= 1")
    group_colors = get_group_palette(theme)
    groups: dict[str, set[str]] = {}
    for path in sorted(index.md_files):
        _add(groups, f"path:{Path(path).parent.as_posix()}", path)
        metadata = _frontmatter((index.repo / path).read_text(encoding="utf-8", errors="ignore"))
        for tag in _metadata_tags(metadata):
            _add(groups, f"tag:{tag}", path)
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

    rows: list[GroupSuggestion] = []
    for name, paths in groups.items():
        if not paths:
            continue
        kind, _, value = name.partition(":")
        if len(paths) < min_count:
            continue
        rows.append({"name": name, "kind": kind, "value": value,
                     "query": name, "obsidian_query": _obsidian_query(kind, value),
                     "property_query": _property_query(kind, value),
                     "color": group_colors.get(kind, group_colors["path"]),
                     "requires_kb_tool": kind == "health",
                     "kb_command": _kb_command(value) if kind == "health" else None,
                     "count": len(paths),
                     "paths": sorted(paths)})
    rows.sort(key=lambda row: (-row["count"], row["name"]))
    return rows[:limit]
