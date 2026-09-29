from pathlib import Path

from kb.dedupe import scan_exact, scan_paragraphs


def test_scan_exact_ignores_frontmatter_by_default(tmp_path: Path) -> None:
    (tmp_path / "a.md").write_text("---\ntitle: A\n---\n\n# Same\n\nBody.\n", encoding="utf-8")
    (tmp_path / "b.md").write_text("---\ntitle: B\n---\n\n# Same\n\nBody.\n", encoding="utf-8")

    rows = scan_exact(tmp_path)

    assert len(rows) == 1
    assert rows[0]["paths"] == ["a.md", "b.md"]


def test_scan_exact_can_include_frontmatter(tmp_path: Path) -> None:
    (tmp_path / "a.md").write_text("---\ntitle: A\n---\nBody.\n", encoding="utf-8")
    (tmp_path / "b.md").write_text("---\ntitle: B\n---\nBody.\n", encoding="utf-8")

    assert scan_exact(tmp_path, include_frontmatter=True) == []


def test_scan_paragraphs_reports_cross_note_duplicates(tmp_path: Path) -> None:
    paragraph = "This is a sufficiently long repeated paragraph for the report."
    (tmp_path / "a.md").write_text(f"# A\n\n{paragraph}\n", encoding="utf-8")
    (tmp_path / "b.md").write_text(f"# B\n\nOther text.\n\n{paragraph}\n", encoding="utf-8")

    rows = scan_paragraphs(tmp_path, min_chars=20)

    assert len(rows) == 1
    assert {item["path"] for item in rows[0]["occurrences"]} == {"a.md", "b.md"}


def test_scan_exact_limit_is_deterministic(tmp_path: Path) -> None:
    for name in ("a", "b", "c"):
        (tmp_path / f"{name}1.md").write_text(name, encoding="utf-8")
        (tmp_path / f"{name}2.md").write_text(name, encoding="utf-8")

    rows = scan_exact(tmp_path, limit=2)

    assert len(rows) == 2
    assert [row["paths"] for row in rows] == [["a1.md", "a2.md"], ["b1.md", "b2.md"]]