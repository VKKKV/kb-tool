from __future__ import annotations

import json
import subprocess
from importlib.metadata import EntryPoint
from pathlib import Path

import pytest
from click.testing import CliRunner

from kb.cli import cli
from kb.core import FileIndex
from kb.plugins import AnalyzerPluginError, list_analyzers, run_analyzer


def _entry_point(name: str, value: str = "some_plugin:analyze") -> EntryPoint:
    return EntryPoint(name=name, value=value, group="kb_tool.analyzers")


def test_list_analyzers_is_sorted_and_does_not_load_code(monkeypatch) -> None:
    points = [_entry_point("zeta"), _entry_point("alpha")]

    def forbidden_load(self):
        raise AssertionError("listing entry points must not import plugin code")

    monkeypatch.setattr(EntryPoint, "load", forbidden_load)
    monkeypatch.setattr("kb.plugins.entry_points", lambda **_: points)

    assert list_analyzers() == [
        {"name": "alpha", "value": "some_plugin:analyze"},
        {"name": "zeta", "value": "some_plugin:analyze"},
    ]


def test_duplicate_plugin_names_fail_closed(monkeypatch) -> None:
    monkeypatch.setattr(
        "kb.plugins.entry_points",
        lambda **_: [_entry_point("duplicate", "a:run"), _entry_point("duplicate", "b:run")],
    )

    with pytest.raises(AnalyzerPluginError, match="duplicate analyzer plugin name"):
        list_analyzers()


def test_run_analyzer_passes_file_index_and_returns_json_value(tmp_path, monkeypatch) -> None:
    received = []
    point = _entry_point("notes")
    monkeypatch.setattr("kb.plugins.entry_points", lambda **_: [point])
    monkeypatch.setattr(
        "kb.plugins._load_entry_point",
        lambda _point: lambda index: received.append(index) or {"notes": 3},
    )
    index = FileIndex.__new__(FileIndex)

    assert run_analyzer("notes", index) == {"notes": 3}
    assert received == [index]


@pytest.mark.parametrize(
    ("loaded", "message"),
    [
        (None, "must resolve to a callable"),
        (lambda _index: {"bad": object()}, "non-JSON-serializable"),
        (lambda _index: float("nan"), "non-JSON-serializable"),
    ],
)
def test_run_analyzer_rejects_invalid_plugin_results(monkeypatch, loaded, message) -> None:
    point = _entry_point("invalid")
    monkeypatch.setattr("kb.plugins.entry_points", lambda **_: [point])
    monkeypatch.setattr("kb.plugins._load_entry_point", lambda _point: loaded)

    with pytest.raises(AnalyzerPluginError, match=message):
        run_analyzer("invalid", FileIndex.__new__(FileIndex))


def test_run_analyzer_wraps_load_and_run_failures(monkeypatch) -> None:
    point = _entry_point("broken")
    monkeypatch.setattr("kb.plugins.entry_points", lambda **_: [point])
    monkeypatch.setattr(
        "kb.plugins._load_entry_point",
        lambda _point: (_ for _ in ()).throw(ImportError("missing dep")),
    )

    with pytest.raises(AnalyzerPluginError, match="cannot load analyzer plugin"):
        run_analyzer("broken", FileIndex.__new__(FileIndex))

    monkeypatch.setattr(
        "kb.plugins._load_entry_point",
        lambda _point: lambda _index: (_ for _ in ()).throw(ValueError("bad")),
    )
    with pytest.raises(AnalyzerPluginError, match="failed"):
        run_analyzer("broken", FileIndex.__new__(FileIndex))


def test_run_analyzer_unknown_name_lists_plugins(monkeypatch) -> None:
    monkeypatch.setattr("kb.plugins.entry_points", lambda **_: [_entry_point("available")])

    with pytest.raises(AnalyzerPluginError, match="available"):
        run_analyzer("missing", FileIndex.__new__(FileIndex))


def test_plugins_cli_lists_entry_points_without_loading(tmp_path, monkeypatch) -> None:
    points = [_entry_point("sample", "sample_package:analyze")]
    monkeypatch.setattr("kb.plugins.entry_points", lambda **_: points)

    result = CliRunner().invoke(cli, ["plugins"])

    assert result.exit_code == 0, result.output
    assert json.loads(result.output) == [
        {"name": "sample", "value": "sample_package:analyze"}
    ]


def test_analyze_cli_runs_installed_builtin_plugin_read_only(tmp_path) -> None:
    (tmp_path / "a.md").write_text("# A\n[[b]]\n", encoding="utf-8")
    (tmp_path / "b.md").write_text("# B\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(tmp_path), "init", "-q"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "add", "."], check=True)

    result = CliRunner().invoke(
        cli, ["--kb", str(tmp_path), "analyze", "kb-link-stats"]
    )

    assert result.exit_code == 0, result.output
    assert json.loads(result.output) == {
        "markdown_files": 2,
        "linked_notes": 1,
        "wikilink_edges": 1,
    }
    assert sorted(path.name for path in tmp_path.glob("*.md")) == ["a.md", "b.md"]


def test_analyze_cli_unknown_plugin_is_a_controlled_error() -> None:
    result = CliRunner().invoke(cli, ["analyze", "missing-analyzer"])

    assert result.exit_code == 1
    assert "unknown analyzer plugin" in result.output
    assert "kb-link-stats" in result.output
    assert "Traceback" not in result.output


def test_analyze_cli_discovers_separately_installed_entry_point(
    tmp_path: Path, monkeypatch
) -> None:
    plugin_root = tmp_path / "plugin-install"
    plugin_root.mkdir()
    (plugin_root / "external_demo.py").write_text(
        "def analyze(index):\n    return {'markdown_files': len(index.md_files)}\n",
        encoding="utf-8",
    )
    dist_info = plugin_root / "external_demo-0.0.1.dist-info"
    dist_info.mkdir()
    (dist_info / "METADATA").write_text(
        "Metadata-Version: 2.1\nName: external-demo\nVersion: 0.0.1\n",
        encoding="utf-8",
    )
    (dist_info / "entry_points.txt").write_text(
        "[kb_tool.analyzers]\nexternal-demo = external_demo:analyze\n",
        encoding="utf-8",
    )

    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "one.md").write_text("# One\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(vault), "init", "-q"], check=True)
    subprocess.run(["git", "-C", str(vault), "add", "."], check=True)
    monkeypatch.syspath_prepend(str(plugin_root))

    result = CliRunner().invoke(
        cli, ["--kb", str(vault), "analyze", "external-demo"]
    )

    assert result.exit_code == 0, result.output
    assert json.loads(result.output) == {"markdown_files": 1}
