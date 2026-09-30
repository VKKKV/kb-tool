import csv
import json
import subprocess
from pathlib import Path

from click.testing import CliRunner

from kb.cli import cli
from kb.core import FileIndex
from kb.graph_groups import suggest_groups


def test_suggest_groups_uses_metadata_and_health(tmp_path: Path) -> None:
    (tmp_path / "a.md").write_text(
        "---\ntags: python\ntype: concept\n---\n[[b]] [[missing]]\n", encoding="utf-8")
    (tmp_path / "b.md").write_text("# B\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(tmp_path), "init", "-q"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "add", "."], check=True)
    rows = suggest_groups(FileIndex(tmp_path))
    names = {row["name"] for row in rows}
    assert "tag:python" in names
    assert "type:concept" in names
    assert "health:broken-link" in names
    assert all("query" in row and row["count"] >= 1 for row in rows)
    tag = next(row for row in rows if row["name"] == "tag:python")
    assert tag["obsidian_query"] == "tag:#python"
    assert tag["color"].startswith("#")
    assert tag["requires_kb_tool"] is False


def test_suggest_groups_supports_singular_tag_and_theme(tmp_path: Path) -> None:
    (tmp_path / "a.md").write_text("---\ntag: '#linux'\n---\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(tmp_path), "init", "-q"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "add", "."], check=True)
    rows = suggest_groups(FileIndex(tmp_path), theme="nord")
    tag = next(row for row in rows if row["name"] == "tag:linux")
    assert tag["obsidian_query"] == "tag:#linux"
    assert tag["color"] == "#b48ead"


def test_group_metadata_and_min_count(tmp_path: Path) -> None:
    (tmp_path / "a.md").write_text("---\ntype: concept\n---\n", encoding="utf-8")
    (tmp_path / "b.md").write_text("---\ntype: concept\n---\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(tmp_path), "init", "-q"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "add", "."], check=True)
    rows = suggest_groups(FileIndex(tmp_path), min_count=2)
    concept = next(row for row in rows if row["name"] == "type:concept")
    assert concept["property_query"] == "type:concept"
    assert concept["kb_command"] is None
    assert all(row["count"] >= 2 for row in rows)


def test_graph_groups_cli_json_remains_a_top_level_array(tmp_path: Path) -> None:
    (tmp_path / "a.md").write_text("---\ntags: linux\n---\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(tmp_path), "init", "-q"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "add", "."], check=True)

    result = CliRunner().invoke(
        cli,
        [
            "--kb", str(tmp_path), "graph-groups", "--theme", "nord",
            "--limit", "7", "--min-count", "1", "--format", "json",
        ],
    )

    assert result.exit_code == 0, result.output
    rows = json.loads(result.output)
    assert isinstance(rows, list)
    assert len(rows) <= 7
    tag = next(row for row in rows if row["name"] == "tag:linux")
    assert tag["color"] == "#b48ead"


def test_graph_groups_cli_jsonl_remains_row_oriented(tmp_path: Path) -> None:
    (tmp_path / "a.md").write_text("# A\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(tmp_path), "init", "-q"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "add", "."], check=True)

    result = CliRunner().invoke(
        cli, ["--kb", str(tmp_path), "graph-groups", "--format", "jsonl"]
    )

    assert result.exit_code == 0, result.output
    rows = [json.loads(line) for line in result.output.splitlines()]
    assert rows
    assert all("name" in row and "count" in row for row in rows)


def test_graph_group_export_helpers_escape_csv_and_markdown() -> None:
    from kb.graph_groups import render_groups_csv, render_groups_markdown

    row = {
        "name": "tag:foo|bar",
        "kind": "tag",
        "value": "foo|bar",
        "query": "tag:foo|bar",
        "obsidian_query": "tag:#foo|bar",
        "property_query": None,
        "color": "#123456",
        "requires_kb_tool": False,
        "kb_command": None,
        "count": 2,
        "paths": ["a,one.md", "b|two.md"],
    }

    csv_text = render_groups_csv([row])
    csv_rows = list(csv.DictReader(csv_text.splitlines()))
    assert len(csv_rows) == 1
    assert csv_rows[0]["value"] == "foo|bar"
    assert json.loads(csv_rows[0]["paths"]) == row["paths"]
    assert csv_rows[0]["property_query"] == ""

    markdown = render_groups_markdown([row])
    assert "foo\\|bar" in markdown
    assert "b\\|two.md" in markdown
    assert markdown.splitlines()[0].startswith("| name | kind | value |")
    assert render_groups_markdown([]) == ""


def test_graph_groups_cli_csv_and_markdown_outputs(tmp_path: Path) -> None:
    (tmp_path / "a.md").write_text("---\ntags: linux\n---\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(tmp_path), "init", "-q"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "add", "."], check=True)

    csv_result = CliRunner().invoke(
        cli, ["--kb", str(tmp_path), "graph-groups", "--format", "csv"]
    )
    assert csv_result.exit_code == 0, csv_result.output
    assert csv_result.output.startswith("name,kind,value,query,")
    assert "tag:linux" in csv_result.output

    output = tmp_path / "exports" / "groups.md"
    markdown_result = CliRunner().invoke(
        cli,
        [
            "--kb", str(tmp_path), "graph-groups", "--format", "markdown",
            "--output", str(output),
        ],
    )
    assert markdown_result.exit_code == 0, markdown_result.output
    assert markdown_result.output == f"wrote {output}\n"
    markdown = output.read_text(encoding="utf-8")
    assert markdown.startswith("| name | kind | value |")
    assert "tag:linux" in markdown


def test_graph_groups_interactive_renders_and_exits(monkeypatch) -> None:
    from kb.cli import _browse_graph_groups

    class FakeConsole:
        def __init__(self) -> None:
            self.items = []

        def print(self, item) -> None:
            self.items.append(item)

    class FakeTable:
        def __init__(self, title: str | None = None) -> None:
            self.title = title
            self.columns = []
            self.rows = []

        def add_column(self, name: str, **kwargs) -> None:
            self.columns.append(name)

        def add_row(self, *values: str) -> None:
            self.rows.append(values)

    class FakeIntPrompt:
        @staticmethod
        def ask(_prompt: str, default: int = 0) -> int:
            return 0

    import rich.console
    import rich.prompt
    import rich.table

    console = FakeConsole()
    monkeypatch.setattr(rich.console, "Console", lambda: console)
    monkeypatch.setattr(rich.prompt, "IntPrompt", FakeIntPrompt)
    monkeypatch.setattr(rich.table, "Table", FakeTable)

    _browse_graph_groups([
        {
            "name": "tag:linux", "kind": "tag", "value": "linux", "query": "tag:linux",
            "obsidian_query": "tag:#linux", "property_query": None, "color": "#123456",
            "requires_kb_tool": False, "kb_command": None, "count": 1, "paths": ["a.md"],
        }
    ])

    assert len(console.items) == 1
    assert isinstance(console.items[0], FakeTable)
    assert console.items[0].rows == [("1", "tag:linux", "1", "#123456")]


def test_graph_groups_interactive_rejects_format_and_output(tmp_path: Path) -> None:
    (tmp_path / "a.md").write_text("# A\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(tmp_path), "init", "-q"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "add", "."], check=True)
    result = CliRunner().invoke(
        cli,
        ["--kb", str(tmp_path), "graph-groups", "--interactive", "--format", "json"],
    )
    assert result.exit_code == 2
    assert "cannot be combined" in result.output


def test_graph_groups_uses_config_defaults_but_cli_wins(tmp_path: Path) -> None:
    (tmp_path / "a.md").write_text(
        "---\ntags: linux\n---\n[[b]]\n", encoding="utf-8"
    )
    (tmp_path / "b.md").write_text("---\ntags: linux\n---\n", encoding="utf-8")
    (tmp_path / ".kb-tool.yaml").write_text(
        "graph_groups:\n  theme: nord\n  min_count: 2\n  limit: 1\n", encoding="utf-8"
    )
    subprocess.run(["git", "-C", str(tmp_path), "init", "-q"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "add", "."], check=True)

    result = CliRunner().invoke(
        cli, ["--kb", str(tmp_path), "graph-groups", "--format", "json"]
    )
    assert result.exit_code == 0, result.output
    rows = json.loads(result.output)
    assert len(rows) == 1
    assert rows[0]["name"] == "path:."
    assert rows[0]["color"] == "#88c0d0"

    overridden = CliRunner().invoke(
        cli,
        ["--kb", str(tmp_path), "graph-groups", "--theme", "catppuccin",
         "--min-count", "1", "--limit", "50", "--format", "json"],
    )
    assert overridden.exit_code == 0, overridden.output
    overridden_rows = json.loads(overridden.output)
    assert len(overridden_rows) > 1
    path_row = next(row for row in overridden_rows if row["name"] == "path:.")
    assert path_row["color"] == "#89b4fa"
