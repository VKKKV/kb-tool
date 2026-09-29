"""Load and validate optional kb-tool command configuration."""

from __future__ import annotations

import math
from collections.abc import Mapping
from pathlib import Path
from typing import Any, TypedDict, cast

import yaml

from .graph_colors import get_theme

CONFIG_FILENAME = ".kb-tool.yaml"


class GraphConfig(TypedDict, total=False):
    """Optional settings for the graph-colors command."""

    theme: str
    min_contrast: float


class GraphGroupsConfig(TypedDict, total=False):
    """Optional settings for the graph-groups command."""

    theme: str
    min_count: int
    limit: int


class ToolConfig(TypedDict, total=False):
    """Validated top-level kb-tool configuration."""

    graph: GraphConfig
    graph_groups: GraphGroupsConfig


class ConfigError(ValueError):
    """A configuration file exists but is invalid or cannot be read."""

    def __init__(self, message: str, *, path: Path) -> None:
        self.path = path
        super().__init__(f"config {path}: {message}")


class ConfigPathError(ConfigError):
    """An explicit or discovered config path is missing or not a regular file."""

    def __init__(self, message: str, *, path: Path, explicit: bool) -> None:
        self.explicit = explicit
        super().__init__(message, path=path)


_ALLOWED_TOP_LEVEL = {"graph", "graph_groups"}
_ALLOWED_GRAPH = {"theme", "min_contrast"}
_ALLOWED_GRAPH_GROUPS = {"theme", "min_count", "limit"}
_MAX_CONFIG_INTEGER_BITS = 1024


class _UniqueKeyLoader(yaml.SafeLoader):
    """Safe YAML loader that rejects duplicate mapping keys."""


def _construct_unique_mapping(loader: _UniqueKeyLoader, node: yaml.MappingNode) -> dict[Any, Any]:
    mapping: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node)
        if key in mapping:
            raise ValueError(f"duplicate key: {key}")
        mapping[key] = loader.construct_object(value_node)
    return mapping


_UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_unique_mapping
)


def _key_error(path: Path, key: str, message: str) -> ConfigError:
    return ConfigError(f"{key}: {message}", path=path)


def _mapping(value: Any, *, path: Path, key: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise _key_error(path, key, "must be a mapping")
    if any(not isinstance(item, str) for item in value):
        raise _key_error(path, key, "must use string keys")
    return value


def _reject_unknown(
    mapping: Mapping[str, Any], allowed: set[str], *, path: Path, prefix: str
) -> None:
    unknown = [key for key in mapping if not isinstance(key, str) or key not in allowed]
    if unknown:
        key = str(sorted(unknown, key=str)[0])
        dotted = f"{prefix}.{key}" if prefix else key
        raise _key_error(path, dotted, "unknown key")


def _theme(value: Any, *, path: Path, key: str) -> str:
    if not isinstance(value, str):
        raise _key_error(path, key, "must be a string")
    try:
        get_theme(value)
    except ValueError as exc:
        raise _key_error(path, key, str(exc)) from exc
    return value


def _finite_minimum(value: Any, *, path: Path, key: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise _key_error(path, key, "must be a number")
    if isinstance(value, int):
        if value < 1:
            raise _key_error(path, key, "must be a finite number >= 1.0")
        if value.bit_length() > _MAX_CONFIG_INTEGER_BITS:
            raise _key_error(path, key, "integer is too large")
        try:
            normalized = float(value)
        except OverflowError:
            raise _key_error(path, key, "integer is too large") from None
        if not math.isfinite(normalized):
            raise _key_error(path, key, "integer is too large")
        return normalized
    try:
        finite = math.isfinite(value)
    except (OverflowError, TypeError, ValueError):
        finite = False
    if not finite or value < 1.0:
        raise _key_error(path, key, "must be a finite number >= 1.0")
    return value


def _positive_int(value: Any, *, path: Path, key: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise _key_error(path, key, "must be an integer")
    if value < 1:
        raise _key_error(path, key, "must be an integer >= 1")
    if value.bit_length() > _MAX_CONFIG_INTEGER_BITS:
        raise _key_error(path, key, "integer is too large")
    return value


def _validate(raw: Any, *, path: Path) -> ToolConfig:
    if raw is None:
        return {}
    top = _mapping(raw, path=path, key="root")
    _reject_unknown(top, _ALLOWED_TOP_LEVEL, path=path, prefix="")
    result: ToolConfig = {}

    if "graph" in top:
        graph = _mapping(top["graph"], path=path, key="graph")
        _reject_unknown(graph, _ALLOWED_GRAPH, path=path, prefix="graph")
        graph_result: GraphConfig = {}
        if "theme" in graph:
            graph_result["theme"] = _theme(graph["theme"], path=path, key="graph.theme")
        if "min_contrast" in graph:
            graph_result["min_contrast"] = _finite_minimum(
                graph["min_contrast"], path=path, key="graph.min_contrast"
            )
        result["graph"] = graph_result

    if "graph_groups" in top:
        groups = _mapping(top["graph_groups"], path=path, key="graph_groups")
        _reject_unknown(groups, _ALLOWED_GRAPH_GROUPS, path=path, prefix="graph_groups")
        groups_result: GraphGroupsConfig = {}
        if "theme" in groups:
            groups_result["theme"] = _theme(
                groups["theme"], path=path, key="graph_groups.theme"
            )
        if "min_count" in groups:
            groups_result["min_count"] = _positive_int(
                groups["min_count"], path=path, key="graph_groups.min_count"
            )
        if "limit" in groups:
            groups_result["limit"] = _positive_int(
                groups["limit"], path=path, key="graph_groups.limit"
            )
        result["graph_groups"] = groups_result

    return result


def _config_path(kb_root: Path, explicit: Path | None) -> tuple[Path, bool]:
    path = explicit if explicit is not None else kb_root / CONFIG_FILENAME
    return path.expanduser(), explicit is not None


def load_config(*, kb_root: Path, explicit_path: Path | None = None) -> ToolConfig:
    """Load optional config from an explicit path or the effective KB root."""
    path, explicit = _config_path(kb_root, explicit_path)
    if not path.exists():
        if explicit:
            raise ConfigPathError("file not found", path=path, explicit=True)
        return {}
    if not path.is_file():
        raise ConfigPathError("path is not a regular file", path=path, explicit=explicit)

    try:
        text = path.read_text(encoding="utf-8")
        raw = yaml.load(text, Loader=_UniqueKeyLoader)
    except (yaml.YAMLError, TypeError, ValueError, OverflowError, MemoryError) as exc:
        raise ConfigError(f"invalid YAML: {exc}", path=path) from exc
    except (OSError, UnicodeError) as exc:
        raise ConfigError(f"cannot read file: {exc}", path=path) from exc
    return _validate(raw, path=path)


def section(config: ToolConfig, name: str) -> Mapping[str, Any]:
    """Return a validated section without exposing mutable TypedDict internals."""
    value = config.get(name)
    if value is None:
        return {}
    return cast(Mapping[str, Any], value)
