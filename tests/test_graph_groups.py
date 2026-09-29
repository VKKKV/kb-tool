import subprocess
from pathlib import Path

from kb.core import FileIndex
from kb.graph_groups import suggest_groups


def test_suggest_groups_uses_metadata_and_health(tmp_path: Path) -> None:
    (tmp_path / "a.md").write_text(
        "---\ntags: [python]\ntype: concept\n---\n[[b]] [[missing]]\n", encoding="utf-8")
    (tmp_path / "b.md").write_text("# B\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(tmp_path), "init", "-q"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "add", "."], check=True)
    rows = suggest_groups(FileIndex(tmp_path))
    names = {row["name"] for row in rows}
    assert "tag:python" in names
    assert "type:concept" in names
    assert "health:broken-link" in names
    assert all("query" in row and row["count"] >= 1 for row in rows)
