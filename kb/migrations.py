"""Explicit-path migrations for archived Markdown knowledge bases.

The migration functions intentionally keep the original script contracts small:
all input paths are supplied by the caller, writes are in-place by default, and
summary counts are returned for CLI/reporting layers.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


LINK_LINE = re.compile(r"^(- \d{4}-\d{2}-\d{2} )\[([^]]+)\]\(([^)]+)\)( — .*)$")
FRONTMATTER = re.compile(r"^---\n(.*?)\n---\n?", re.DOTALL)
MANAGED_FIELDS = {"source_file", "tags", "parent", "topic", "decision"}


def load_mapping(path: Path) -> dict[str, str]:
    """Load an old-link/new-wikilink mapping from a tab-separated file."""
    mapping: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        old, separator, new = line.partition("\t")
        if not separator:
            raise ValueError(f"mapping line has no tab: {line!r}")
        mapping[old] = new
    return mapping


def convert_links(
    index: Path,
    mapping: dict[str, str],
    *,
    dry_run: bool = False,
) -> tuple[int, int]:
    """Convert mapped dated Markdown links in ``index`` in place.

    Returns ``(converted, missing)``. Unmapped matching links remain unchanged,
    which preserves the legacy script's partial-migration behavior.
    """
    converted = missing = 0
    output: list[str] = []
    for line in index.read_text(encoding="utf-8").splitlines(keepends=True):
        match = LINK_LINE.match(line.rstrip("\n"))
        if not match:
            output.append(line)
            continue
        prefix, title, old_path, suffix = match.groups()
        new_path = mapping.get(old_path)
        if new_path is None:
            missing += 1
            output.append(line)
            continue
        output.append(f"{prefix}[[{new_path}|{title}]]{suffix}\n")
        converted += 1
    if not dry_run:
        index.write_text("".join(output), encoding="utf-8")
    return converted, missing


def yaml_scalar(value: Any) -> str:
    """Render the limited scalar values used by migration coverage metadata."""
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if value is True:
        return "true"
    if value is False:
        return "false"
    if value is None:
        return "null"
    return str(value)


def tidy_file(
    path: Path,
    year: str,
    coverage: dict[str, Any],
    *,
    dry_run: bool = False,
) -> bool:
    """Normalize one archived article and return whether its content changes."""
    original = path.read_text(encoding="utf-8")
    match = FRONTMATTER.match(original)
    if not match:
        raise ValueError("missing YAML frontmatter")

    fields: list[str] = []
    for line in match.group(1).splitlines():
        key = line.split(":", 1)[0].strip() if ":" in line else ""
        if key not in MANAGED_FIELDS:
            fields.append(line)
    fields.extend(("tags: [wechat-archive]", f"parent: [[index-{year}]]"))

    entry = coverage.get(f"articles/{year}/{path.name}") or {}
    if not isinstance(entry, dict):
        raise ValueError("coverage entry must be an object")
    if entry.get("topic"):
        fields.append(f"topic: {yaml_scalar(entry['topic'])}")
    if "decision" in entry:
        fields.append(f"decision: {yaml_scalar(entry['decision'])}")

    body = original[match.end() :]
    body = re.sub(r"^-\s*导入来源:.*(?:\n|$)", "", body, flags=re.MULTILINE)
    backlink = f"[[index-{year}|← 返回索引]]"
    body = body.replace(backlink, "")
    body = re.sub(r"\n{3,}", "\n\n", body).rstrip()
    output = "---\n" + "\n".join(fields) + f"\n---\n{body}\n\n{backlink}\n"
    changed = output != original
    if changed and not dry_run:
        path.write_text(output, encoding="utf-8")
    return changed


def load_coverage(path: Path) -> dict[str, Any]:
    """Load and validate the JSON coverage object used by ``tidy-wechat``."""
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("coverage must be a JSON object")
    return value


def tidy_wechat(
    articles: Path,
    year: str,
    coverage: dict[str, Any],
    *,
    dry_run: bool = False,
) -> tuple[int, int, list[tuple[Path, str]]]:
    """Normalize all top-level Markdown articles in a year directory.

    Returns ``(processed, changed, errors)``. Errors are returned rather than
    aborting the batch so one malformed article does not hide the rest.
    """
    files = sorted(articles.glob("*.md"))
    changed = 0
    errors: list[tuple[Path, str]] = []
    for path in files:
        try:
            changed += tidy_file(path, year, coverage, dry_run=dry_run)
        except (OSError, ValueError) as exc:
            errors.append((path, str(exc)))
    return len(files), changed, errors
