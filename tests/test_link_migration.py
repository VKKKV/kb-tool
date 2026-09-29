import subprocess

from kb.dedupe import migrate_links, verify_fragments


def test_migrate_links_preserves_alias_fragments_embeds_and_code() -> None:
    text = """[[old|Readable]] [[old#Details]] ![[old#^block]]
[Old](old.md#Details)
`[[old]]`
```md
[[old]]
```
"""
    result = migrate_links(text, {"old": "canonical", "old.md": "canonical.md"})
    assert "[[canonical|Readable]]" in result
    assert "[[canonical#Details]]" in result
    assert "![[canonical#^block]]" in result
    assert "[Old](canonical.md#Details)" in result
    assert "`[[old]]`" in result
    assert "```md\n[[old]]" in result


def test_verify_fragments_reports_missing_heading(tmp_path) -> None:
    subprocess.run(["git", "-C", str(tmp_path), "init", "-q"], check=True)
    target = tmp_path / "target.md"
    source = tmp_path / "source.md"
    target.write_text("# Present\n", encoding="utf-8")
    source.write_text("[[target#Present]]\n[[target#Missing]]\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(tmp_path), "add", "."], check=True)
    rows = verify_fragments(tmp_path)
    assert [row["ok"] for row in rows] == [True, False]


def test_verify_fragments_reports_ambiguous_basename(tmp_path) -> None:
    import subprocess
    subprocess.run(["git", "-C", str(tmp_path), "init", "-q"], check=True)
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    (tmp_path / "a/note.md").write_text("# Same\n", encoding="utf-8")
    (tmp_path / "b/note.md").write_text("# Same\n", encoding="utf-8")
    (tmp_path / "source.md").write_text("[[note#Same]]\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(tmp_path), "add", "."], check=True)
    rows = verify_fragments(tmp_path)
    assert rows[0]["status"] == "ambiguous"
    assert rows[0]["ok"] is False
