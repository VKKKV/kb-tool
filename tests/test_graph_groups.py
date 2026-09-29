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


def test_graph_groups_cli_json_includes_report_metadata(tmp_path: Path) -> None:
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
    report = json.loads(result.output)
    assert report["theme"] == "nord"
    assert report["limit"] == 7
    assert report["min_count"] == 1
    assert isinstance(report["groups"], list)
    tag = next(row for row in report["groups"] if row["name"] == "tag:linux")
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
