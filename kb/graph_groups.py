"""Generate read-only Obsidian Graph View group suggestions."""

from __future__ import annotations

import csv
import io
import json
import re
from pathlib import Path
from typing import Any, TypedDict, cast

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


GROUP_EXPORT_FIELDS = (
    "name", "kind", "value", "query", "obsidian_query", "property_query",
    "color", "requires_kb_tool", "kb_command", "count", "paths",
)


def render_groups_csv(rows: list[GroupSuggestion]) -> str:
    """Serialize group suggestions as CSV, encoding paths as a JSON array."""
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(GROUP_EXPORT_FIELDS)
    for row in rows:
        values: dict[str, str | bool | int] = {}
        for key, value in row.items():
            if isinstance(value, list):
                values[key] = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
            elif value is None:
                values[key] = ""
            elif isinstance(value, (str, bool, int)):
                values[key] = str(value).lower() if isinstance(value, bool) else str(value)
            else:
                values[key] = str(value)
        writer.writerow([values[key] for key in GROUP_EXPORT_FIELDS])
    return output.getvalue()


def render_groups_markdown(rows: list[GroupSuggestion]) -> str:
    """Render a Markdown table with escaped pipes and line breaks."""
    if not rows:
        return ""
    header = "| " + " | ".join(GROUP_EXPORT_FIELDS) + " |"
    separator = "| " + " | ".join("---" for _ in GROUP_EXPORT_FIELDS) + " |"
    lines = [header, separator]
    for row in rows:
        cells = []
        for key, value in row.items():
            if value is None:
                text = ""
            elif isinstance(value, list):
                text = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
            elif isinstance(value, bool):
                text = str(value).lower()
            else:
                text = str(value)
            text = text.replace("\\", "\\\\").replace("|", "\\|")
            text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "<br>")
            cells.append(text)
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n"


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
                     "color": cast(str, group_colors.get(kind, group_colors["path"])),
                     "requires_kb_tool": kind == "health",
                     "kb_command": _kb_command(value) if kind == "health" else None,
                     "count": len(paths),
                     "paths": sorted(paths)})
    rows.sort(key=lambda row: (-row["count"], row["name"]))
    return rows[:limit]
