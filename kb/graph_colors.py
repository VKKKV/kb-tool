"""Generate an Obsidian Graph View color snippet."""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from pathlib import Path
from typing import TypedDict, cast

DEFAULT_COLORS = {
    "dark_node": "#7aa2f7", "light_node": "#2457a6",
    "dark_line": "#414868", "light_line": "#9aa5b1",
    "dark_text": "#c0caf5", "light_text": "#334155",
    "dark_unresolved": "#f7768e", "light_unresolved": "#b42318",
    "dark_tag": "#bb9af7", "light_tag": "#6941c6",
    "dark_attachment": "#73daca", "light_attachment": "#087f5b",
    "dark_highlight": "#e0af68", "light_highlight": "#b54708",
}

THEMES = {
    "default": DEFAULT_COLORS,
    "nord": {
        **DEFAULT_COLORS, "dark_node": "#88c0d0", "light_node": "#2e3440",
        "dark_line": "#4c566a", "light_line": "#d8dee9", "dark_text": "#eceff4",
        "light_text": "#2e3440", "dark_unresolved": "#bf616a", "light_unresolved": "#a94442",
        "dark_tag": "#b48ead", "light_tag": "#815b7b",
    },
    "catppuccin": {
        **DEFAULT_COLORS, "dark_node": "#89b4fa", "light_node": "#1e66f5",
        "dark_line": "#585b70", "light_line": "#9ca0b0", "dark_text": "#cdd6f4",
        "light_text": "#4c4f69", "dark_unresolved": "#f38ba8", "light_unresolved": "#d20f39",
        "dark_tag": "#cba6f7", "light_tag": "#8839ef",
    },
}
THEME_NAMES: tuple[str, ...] = tuple(THEMES)
HEX_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")
CHECK_COLOR_KEYS = (
    "dark_text", "light_text", "dark_node", "light_node",
    "dark_unresolved", "light_unresolved",
)
REPORT_COLOR_KEYS = CHECK_COLOR_KEYS + (
    "dark_tag", "dark_attachment", "light_tag", "light_attachment",
)


class ContrastCheck(TypedDict):
    """One pairwise contrast check in a theme report."""

    first: str
    second: str
    ratio: float
    ok: bool


class ThemeReport(TypedDict):
    """Machine-readable result of validating one graph color theme."""

    minimum_contrast: int | float
    ok: bool
    checks: list[ContrastCheck]
    conflicts: list[ContrastCheck]


class GraphPalette(TypedDict):
    """Complete flat palette used by the Graph View snippet."""

    dark_node: str
    light_node: str
    dark_line: str
    light_line: str
    dark_text: str
    light_text: str
    dark_unresolved: str
    light_unresolved: str
    dark_tag: str
    light_tag: str
    dark_attachment: str
    light_attachment: str
    dark_highlight: str
    light_highlight: str


class GroupPalette(TypedDict):
    """Dark-mode colors assigned to suggested Graph View groups."""

    path: str
    tag: str
    type: str
    status: str
    health: str


def get_theme(name: str = "default") -> GraphPalette:
    """Return a copy of a named theme, or raise a user-facing error."""
    try:
        colors = THEMES[name]
    except KeyError as exc:
        raise ValueError(f"unknown graph color theme: {name}") from exc
    return _complete_theme(colors)


def get_graph_palette(name: str = "default") -> GraphPalette:
    """Return a named flat Graph View palette."""
    return get_theme(name)


def get_group_palette(name: str = "default") -> GroupPalette:
    """Return the dark-theme colors used for suggested Graph View groups."""
    colors = get_theme(name)
    return {
        "path": colors["dark_node"],
        "tag": colors["dark_tag"],
        "type": colors["dark_attachment"],
        "status": colors["dark_highlight"],
        "health": colors["dark_unresolved"],
    }


def validate_colors(colors: Mapping[str, object]) -> None:
    """Reject unknown keys and malformed six-digit hex colors."""
    unknown = set(colors) - set(DEFAULT_COLORS)
    if unknown:
        raise ValueError(f"unknown graph color(s): {', '.join(sorted(unknown))}")
    invalid = {
        key for key, value in colors.items()
        if not isinstance(value, str) or not HEX_COLOR.fullmatch(value)
    }
    if invalid:
        raise ValueError("colors must use #RRGGBB: " + ", ".join(sorted(invalid)))


def _complete_theme(colors: Mapping[str, object]) -> GraphPalette:
    """Validate and copy a complete named theme."""
    validate_colors(colors)
    missing = set(DEFAULT_COLORS) - set(colors)
    if missing:
        raise ValueError("missing graph color(s): " + ", ".join(sorted(missing)))
    return cast(GraphPalette, dict(colors))


def _require_colors(colors: Mapping[str, object], keys: tuple[str, ...]) -> None:
    """Validate a partial color mapping required by a specific report."""
    validate_colors(colors)
    missing = set(keys) - set(colors)
    if missing:
        raise ValueError("missing graph color(s): " + ", ".join(sorted(missing)))


def _luminance(value: str) -> float:
    rgb = [int(value[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    linear = [channel / 12.92 if channel <= 0.03928
              else ((channel + 0.055) / 1.055) ** 2.4 for channel in rgb]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def contrast_ratio(first: str, second: str) -> float:
    """Return WCAG relative contrast ratio for two hex colors."""
    if not HEX_COLOR.fullmatch(first) or not HEX_COLOR.fullmatch(second):
        raise ValueError("colors must use #RRGGBB")
    light, dark = sorted((_luminance(first), _luminance(second)), reverse=True)
    return round((light + 0.05) / (dark + 0.05), 2)


def _contrast_check(colors: Mapping[str, object], first: str, second: str,
                    minimum: int | float) -> ContrastCheck:
    first_color = colors[first]
    second_color = colors[second]
    if not isinstance(first_color, str) or not isinstance(second_color, str):
        raise ValueError("colors must use #RRGGBB")
    ratio = contrast_ratio(first_color, second_color)
    return {"first": first, "second": second, "ratio": ratio, "ok": ratio >= minimum}


def validate_theme(
    colors: Mapping[str, object], minimum: int | float = 2.0
) -> list[ContrastCheck]:
    """Report low-contrast text/node and node/unresolved color pairs."""
    finite = isinstance(minimum, (int, float)) and not isinstance(minimum, bool)
    if isinstance(minimum, float):
        finite = finite and math.isfinite(minimum)
    if not finite or minimum < 1.0:
        raise ValueError("minimum contrast must be a finite number >= 1.0")
    _require_colors(colors, CHECK_COLOR_KEYS)
    checks = [("dark_text", "dark_node"), ("light_text", "light_node"),
              ("dark_node", "dark_unresolved"), ("light_node", "light_unresolved")]
    return [_contrast_check(colors, first, second, minimum) for first, second in checks]


def theme_report(
    colors: Mapping[str, object], minimum: int | float = 2.0
) -> ThemeReport:
    """Return a structured contrast report for a graph color theme."""
    _require_colors(colors, REPORT_COLOR_KEYS)
    checks = validate_theme(colors, minimum)
    conflicts: list[ContrastCheck] = []
    for first, second in (("dark_node", "dark_tag"), ("dark_node", "dark_attachment"),
                          ("light_node", "light_tag"), ("light_node", "light_attachment")):
        conflicts.append(_contrast_check(colors, first, second, minimum))
    return {"minimum_contrast": minimum, "ok": all(row["ok"] for row in checks + conflicts),
            "checks": checks, "conflicts": conflicts}


def render_css(colors: Mapping[str, object] | None = None) -> str:
    """Render CSS classes supported by Obsidian's Graph View plugin."""
    validate_colors(colors or {})
    v = {**DEFAULT_COLORS, **(colors or {})}
    return f"""/* Generated by kb-tool graph-colors. Enable as an Obsidian CSS snippet. */
.theme-dark .graph-view.color-fill {{ color: {v['dark_node']}; }}
.theme-light .graph-view.color-fill {{ color: {v['light_node']}; }}
.theme-dark .graph-view.color-line {{ color: {v['dark_line']}; }}
.theme-light .graph-view.color-line {{ color: {v['light_line']}; }}
.theme-dark .graph-view.color-text {{ color: {v['dark_text']}; }}
.theme-light .graph-view.color-text {{ color: {v['light_text']}; }}
.theme-dark .graph-view.color-fill-unresolved {{ color: {v['dark_unresolved']}; }}
.theme-light .graph-view.color-fill-unresolved {{ color: {v['light_unresolved']}; }}
.theme-dark .graph-view.color-fill-tag {{ color: {v['dark_tag']}; }}
.theme-light .graph-view.color-fill-tag {{ color: {v['light_tag']}; }}
.theme-dark .graph-view.color-fill-attachment {{ color: {v['dark_attachment']}; }}
.theme-light .graph-view.color-fill-attachment {{ color: {v['light_attachment']}; }}
.theme-dark .graph-view.color-fill-highlight,
.theme-dark .graph-view.color-line-highlight {{ color: {v['dark_highlight']}; }}
.theme-light .graph-view.color-fill-highlight,
.theme-light .graph-view.color-line-highlight {{ color: {v['light_highlight']}; }}
"""


def write_css(path: Path, colors: Mapping[str, object] | None = None) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_css(colors), encoding="utf-8")
    return path
