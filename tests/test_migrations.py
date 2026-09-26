from __future__ import annotations

import json
from pathlib import Path

from kb.migrations import convert_links, tidy_file, tidy_wechat


def test_convert_links_matches_legacy_contract_and_is_idempotent(tmp_path: Path) -> None:
    mapping = {"old/one.md": "new/one", "old/two.md": "new/two"}
    index = tmp_path / "index.md"
    original = (
        "- 2026-01-02 [One](old/one.md) — note\n"
        "- 2026-01-03 [Missing](old/missing.md) — keep\n"
        "not a dated link\n"
    )
    index.write_text(original, encoding="utf-8")

    converted, missing = convert_links(index, mapping, dry_run=True)
    assert (converted, missing) == (1, 1)
    assert index.read_text(encoding="utf-8") == original

    converted, missing = convert_links(index, mapping)
    assert (converted, missing) == (1, 1)
    expected = (
        "- 2026-01-02 [[new/one|One]] — note\n"
        "- 2026-01-03 [Missing](old/missing.md) — keep\n"
        "not a dated link\n"
    )
    assert index.read_text(encoding="utf-8") == expected

    converted, missing = convert_links(index, mapping)
    assert (converted, missing) == (0, 1)
    assert index.read_text(encoding="utf-8") == expected


def test_tidy_wechat_matches_legacy_transform_and_is_idempotent(tmp_path: Path) -> None:
    article = tmp_path / "article.md"
    article.write_text(
        "---\n"
        "title: Example\n"
        "source_file: old.md\n"
        "tags: [old]\n"
        "parent: [[old-index]]\n"
        "topic: old-topic\n"
        "decision: old-decision\n"
        "author: demo\n"
        "---\n"
        "- 导入来源: private archive\n"
        "正文\n\n\n"
        "[[index-2026|← 返回索引]]\n",
        encoding="utf-8",
    )
    coverage = {
        "articles/2026/article.md": {
            "topic": "new topic",
            "decision": False,
        }
    }
    expected = (
        "---\n"
        "title: Example\n"
        "author: demo\n"
        "tags: [wechat-archive]\n"
        "parent: [[index-2026]]\n"
        "topic: \"new topic\"\n"
        "decision: false\n"
        "---\n"
        "正文\n\n"
        "[[index-2026|← 返回索引]]\n"
    )

    assert tidy_file(article, "2026", coverage, dry_run=True) is True
    assert article.read_text(encoding="utf-8") != expected
    assert tidy_file(article, "2026", coverage) is True
    assert article.read_text(encoding="utf-8") == expected
    assert tidy_file(article, "2026", coverage) is False
    assert article.read_text(encoding="utf-8") == expected


def test_tidy_wechat_reports_malformed_articles_without_hiding_valid_files(tmp_path: Path) -> None:
    valid = tmp_path / "a.md"
    invalid = tmp_path / "b.md"
    valid.write_text("---\ntitle: A\n---\nbody\n", encoding="utf-8")
    invalid.write_text("body without frontmatter\n", encoding="utf-8")

    processed, changed, errors = tidy_wechat(
        tmp_path,
        "2026",
        {"articles/2026/a.md": {}},
    )
    assert processed == 2
    assert changed == 1
    assert [(path.name, message) for path, message in errors] == [
        ("b.md", "missing YAML frontmatter")
    ]


def test_fixture_coverage_is_json_compatible(tmp_path: Path) -> None:
    coverage = tmp_path / "coverage.json"
    coverage.write_text(
        json.dumps({"articles/2026/example.md": {"topic": "demo"}}),
        encoding="utf-8",
    )
    assert json.loads(coverage.read_text(encoding="utf-8"))["articles/2026/example.md"]["topic"] == "demo"
