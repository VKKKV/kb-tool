"""Tests for strict optional kb-tool configuration loading."""

from pathlib import Path

import pytest

from kb.config import ConfigError, ConfigPathError, load_config


def test_missing_auto_config_is_optional(tmp_path: Path) -> None:
    assert load_config(kb_root=tmp_path) == {}


def test_empty_and_partial_config_are_valid(tmp_path: Path) -> None:
    config = tmp_path / ".kb-tool.yaml"
    config.write_text("graph:\n  theme: nord\n", encoding="utf-8")

    assert load_config(kb_root=tmp_path) == {"graph": {"theme": "nord"}}


def test_explicit_config_replaces_auto_discovery(tmp_path: Path) -> None:
    (tmp_path / ".kb-tool.yaml").write_text("graph:\n  theme: nord\n", encoding="utf-8")
    explicit = tmp_path / "custom.yaml"
    explicit.write_text("graph_groups:\n  limit: 3\n", encoding="utf-8")

    assert load_config(kb_root=tmp_path, explicit_path=explicit) == {
        "graph_groups": {"limit": 3}
    }


@pytest.mark.parametrize(
    ("content", "fragment"),
    [
        ("[]\n", "root: must be a mapping"),
        ("graph: []\n", "graph: must be a mapping"),
        ("wrong: true\n", "wrong: unknown key"),
        ("graph:\n  wrong: true\n", "graph.wrong: unknown key"),
        ("graph:\n  theme: missing\n", "graph.theme: unknown graph color theme"),
        ("graph:\n  min_contrast: .nan\n", "graph.min_contrast: must be a finite"),
        ("graph_groups:\n  limit: true\n", "graph_groups.limit: must be an integer"),
        ("graph_groups:\n  min_count: 0\n", "graph_groups.min_count: must be an integer >= 1"),
    ],
)
def test_invalid_config_reports_path_and_dotted_key(
    tmp_path: Path, content: str, fragment: str
) -> None:
    config = tmp_path / "bad.yaml"
    config.write_text(content, encoding="utf-8")

    with pytest.raises(ConfigError, match=fragment) as raised:
        load_config(kb_root=tmp_path, explicit_path=config)
    assert str(config) in str(raised.value)


def test_malformed_yaml_reports_path(tmp_path: Path) -> None:
    config = tmp_path / "bad.yaml"
    config.write_text("graph: [\n", encoding="utf-8")

    with pytest.raises(ConfigError, match="invalid YAML") as raised:
        load_config(kb_root=tmp_path, explicit_path=config)
    assert str(config) in str(raised.value)


def test_explicit_missing_and_directory_paths_fail(tmp_path: Path) -> None:
    with pytest.raises(ConfigPathError, match="file not found"):
        load_config(kb_root=tmp_path, explicit_path=tmp_path / "missing.yaml")

    directory = tmp_path / "directory.yaml"
    directory.mkdir()
    with pytest.raises(ConfigPathError, match="not a regular file"):
        load_config(kb_root=tmp_path, explicit_path=directory)


def test_auto_discovered_directory_is_an_error(tmp_path: Path) -> None:
    (tmp_path / ".kb-tool.yaml").mkdir()

    with pytest.raises(ConfigPathError, match="not a regular file"):
        load_config(kb_root=tmp_path)


def test_non_string_yaml_keys_are_rejected(tmp_path: Path) -> None:
    config = tmp_path / "bad.yaml"
    config.write_text("? [nested]\n: value\n", encoding="utf-8")

    with pytest.raises(ConfigError, match="invalid YAML"):
        load_config(kb_root=tmp_path, explicit_path=config)
