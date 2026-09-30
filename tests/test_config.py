"""Tests for strict optional kb-tool configuration loading."""

from pathlib import Path

import pytest

from kb.config import ConfigError, ConfigPathError, load_config
from kb.core import effective_kb_root


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


def test_duplicate_yaml_keys_are_rejected(tmp_path: Path) -> None:
    config = tmp_path / "duplicate.yaml"
    config.write_text("graph:\n  theme: nord\n  theme: default\n", encoding="utf-8")

    with pytest.raises(ConfigError, match="duplicate key"):
        load_config(kb_root=tmp_path, explicit_path=config)


def test_integer_min_contrast_is_normalized_to_float(tmp_path: Path) -> None:
    config = tmp_path / "numbers.yaml"
    config.write_text("graph:\n  min_contrast: 1\n", encoding="utf-8")

    loaded = load_config(kb_root=tmp_path, explicit_path=config)

    value = loaded.get("graph", {}).get("min_contrast")
    assert value == 1.0
    assert isinstance(value, float)


def test_oversized_config_integers_are_rejected(tmp_path: Path) -> None:
    config = tmp_path / "huge.yaml"
    value = "1" + ("0" * 400)
    config.write_text(
        f"graph:\n  min_contrast: {value}\ngraph_groups:\n  limit: {value}\n",
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="integer is too large"):
        load_config(kb_root=tmp_path, explicit_path=config)


def test_duplicate_top_level_keys_are_rejected(tmp_path: Path) -> None:
    config = tmp_path / "duplicate-top.yaml"
    config.write_text("graph: {}\ngraph: {}\n", encoding="utf-8")

    with pytest.raises(ConfigError, match="duplicate key"):
        load_config(kb_root=tmp_path, explicit_path=config)


def test_cli_reports_invalid_auto_config_without_traceback(tmp_path: Path) -> None:
    from click.testing import CliRunner

    from kb.cli import cli

    (tmp_path / ".kb-tool.yaml").write_text("graph:\n  unknown: true\n", encoding="utf-8")
    result = CliRunner().invoke(cli, ["--kb", str(tmp_path), "graph-colors"])

    assert result.exit_code == 1
    assert "graph.unknown" in result.output
    assert "Traceback" not in result.output


def test_kb_root_precedence_and_tilde_expansion(tmp_path: Path, monkeypatch) -> None:
    from click.testing import CliRunner

    from kb.cli import cli

    explicit_root = tmp_path / "explicit"
    env_root = tmp_path / "from-env"
    explicit_root.mkdir()
    env_root.mkdir()
    (explicit_root / ".kb-tool.yaml").write_text(
        "graph:\n  theme: nord\n", encoding="utf-8"
    )
    (env_root / ".kb-tool.yaml").write_text(
        "graph:\n  theme: catppuccin\n", encoding="utf-8"
    )

    runner = CliRunner()
    chosen = runner.invoke(
        cli,
        ["--kb", str(explicit_root), "graph-colors"],
        env={"KB_ROOT": str(env_root)},
    )
    assert chosen.exit_code == 0, chosen.output
    assert ".theme-dark .graph-view.color-fill { color: #88c0d0; }" in chosen.output

    from_env = runner.invoke(cli, ["graph-colors"], env={"KB_ROOT": str(env_root)})
    assert from_env.exit_code == 0, from_env.output
    assert ".theme-dark .graph-view.color-fill { color: #89b4fa; }" in from_env.output

    home = tmp_path / "home"
    tilde_root = home / "vault"
    tilde_root.mkdir(parents=True)
    (tilde_root / ".kb-tool.yaml").write_text(
        "graph:\n  theme: nord\n", encoding="utf-8"
    )
    monkeypatch.setenv("HOME", str(home))
    tilde = runner.invoke(cli, ["--kb", "~/vault", "graph-colors"])
    assert tilde.exit_code == 0, tilde.output
    assert ".theme-dark .graph-view.color-fill { color: #88c0d0; }" in tilde.output


def test_empty_kb_root_env_uses_default(monkeypatch) -> None:
    from pathlib import Path

    monkeypatch.setenv("KB_ROOT", "")
    assert effective_kb_root() == Path.home() / "code" / "knowledge"


@pytest.mark.parametrize(
    ("config_arg", "config_kind", "exit_code"),
    [
        ("missing.yaml", "missing", 2),
        ("directory.yaml", "directory", 2),
        (".kb-tool.yaml", "malformed", 1),
    ],
)
def test_cli_config_path_errors_are_controlled(
    tmp_path: Path, config_arg: str, config_kind: str, exit_code: int
) -> None:
    from click.testing import CliRunner

    from kb.cli import cli

    config = tmp_path / config_arg
    if config_kind == "directory":
        config.mkdir()
    elif config_kind == "malformed":
        config.write_text("graph: [\n", encoding="utf-8")

    args = ["--config", str(config), "graph-colors"]
    if config_kind == "malformed":
        args = ["--kb", str(tmp_path), "graph-colors"]
    result = CliRunner().invoke(cli, args)

    assert result.exit_code == exit_code
    assert "Traceback" not in result.output
    if config_kind != "missing":
        assert str(config) in result.output
