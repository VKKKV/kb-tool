"""Entry-point discovery and execution for optional knowledge-base analyzers."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Callable
from importlib.metadata import EntryPoint, entry_points
from typing import Any

from .core import FileIndex

ANALYZER_ENTRY_POINT_GROUP = "kb_tool.analyzers"
Analyzer = Callable[[FileIndex], Any]


class AnalyzerPluginError(RuntimeError):
    """A plugin is invalid, fails to load, or cannot produce JSON output."""


def _analyzer_entry_points() -> list[EntryPoint]:
    try:
        points = sorted(
            entry_points(group=ANALYZER_ENTRY_POINT_GROUP),
            key=lambda point: (point.name, point.value),
        )
    except Exception as exc:
        raise AnalyzerPluginError(f"cannot discover analyzer plugins: {exc}") from exc

    duplicates = sorted(name for name, count in Counter(p.name for p in points).items()
                        if count > 1)
    if duplicates:
        raise AnalyzerPluginError(
            "duplicate analyzer plugin name(s): " + ", ".join(duplicates)
        )
    return points


def _load_entry_point(point: EntryPoint) -> Any:
    """Load one point through a patchable seam for deterministic testing."""
    return point.load()


def list_analyzers() -> list[dict[str, str]]:
    """Return installed analyzer names and targets without importing plugin code."""
    return [
        {"name": point.name, "value": point.value}
        for point in _analyzer_entry_points()
    ]


def run_analyzer(name: str, index: FileIndex) -> Any:
    """Load and run one installed analyzer; require JSON-serializable output."""
    points = _analyzer_entry_points()
    point = next((candidate for candidate in points if candidate.name == name), None)
    if point is None:
        available = ", ".join(candidate.name for candidate in points) or "none"
        raise AnalyzerPluginError(f"unknown analyzer plugin {name!r}; installed: {available}")

    try:
        analyzer = _load_entry_point(point)
    except Exception as exc:
        raise AnalyzerPluginError(f"cannot load analyzer plugin {name!r}: {exc}") from exc
    if not callable(analyzer):
        raise AnalyzerPluginError(f"analyzer plugin {name!r} must resolve to a callable")

    try:
        result = analyzer(index)
    except Exception as exc:
        raise AnalyzerPluginError(f"analyzer plugin {name!r} failed: {exc}") from exc

    try:
        json.dumps(result, ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError, OverflowError) as exc:
        raise AnalyzerPluginError(
            f"analyzer plugin {name!r} returned a non-JSON-serializable result: {exc}"
        ) from exc
    return result
