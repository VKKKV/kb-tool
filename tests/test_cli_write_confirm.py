"""CLI safeguards for file-writing dedupe operations."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from click.testing import CliRunner

from kb.cli import cli
from kb.dedupe import apply_plan


def _repo_with_plan(root: Path) -> Path:
    (root / "old.md").write_text("old content\n", encoding="utf-8")
    (root / "new.md").write_text("canonical content\n", encoding="utf-8")
    (root / "plan.json").write_text(
        json.dumps([{"source": "old.md", "target": "new.md"}]), encoding="utf-8"
    )
    subprocess.run(["git", "-C", str(root), "init", "-q"], check=True)
    subprocess.run(["git", "-C", str(root), "add", "."], check=True)
    return root


def test_dedupe_apply_write_requires_confirm(tmp_path: Path) -> None:
    root = _repo_with_plan(tmp_path)

    result = CliRunner().invoke(
        cli,
        ["--kb", str(root), "dedupe", "apply", str(root / "plan.json"), "--write"],
    )

    assert result.exit_code == 2
    assert "--write requires --confirm" in result.output
    assert (root / "old.md").read_text(encoding="utf-8") == "old content\n"
    assert not (root / ".kb-tool-backup").exists()


def test_dedupe_apply_cancel_does_not_modify_files(tmp_path: Path, monkeypatch) -> None:
    root = _repo_with_plan(tmp_path)
    monkeypatch.setattr("kb.cli._confirm_write", lambda _prompt: False)

    result = CliRunner().invoke(
        cli,
        ["--kb", str(root), "dedupe", "apply", str(root / "plan.json"), "--write", "--confirm"],
    )

    assert result.exit_code == 0
    assert result.output == "cancelled\n"
    assert (root / "old.md").read_text(encoding="utf-8") == "old content\n"


def test_dedupe_apply_confirmed_write_applies_plan(tmp_path: Path, monkeypatch) -> None:
    root = _repo_with_plan(tmp_path)
    prompts: list[str] = []

    def confirm(prompt: str) -> bool:
        prompts.append(prompt)
        return True

    monkeypatch.setattr("kb.cli._confirm_write", confirm)
    result = CliRunner().invoke(
        cli,
        ["--kb", str(root), "dedupe", "apply", str(root / "plan.json"), "--write", "--confirm"],
    )

    assert result.exit_code == 0, result.output
    assert prompts and "write 1 redirect operation(s)" in prompts[0]
    assert (root / "old.md").read_text(encoding="utf-8") == "> Moved to [[new]].\n"


def test_dedupe_rollback_write_requires_confirm(tmp_path: Path) -> None:
    root = _repo_with_plan(tmp_path)
    apply_plan(root, [{"source": "old.md", "target": "new.md"}], write=True)
    manifest = root / ".kb-tool-backup" / "manifest.json"
    changed_source = (root / "old.md").read_text(encoding="utf-8")

    result = CliRunner().invoke(
        cli,
        ["--kb", str(root), "dedupe", "rollback", str(manifest), "--write"],
    )

    assert result.exit_code == 2
    assert "--write requires --confirm" in result.output
    assert (root / "old.md").read_text(encoding="utf-8") == changed_source


def test_dedupe_rollback_cancel_does_not_restore(tmp_path: Path, monkeypatch) -> None:
    root = _repo_with_plan(tmp_path)
    apply_plan(root, [{"source": "old.md", "target": "new.md"}], write=True)
    manifest = root / ".kb-tool-backup" / "manifest.json"
    changed_source = (root / "old.md").read_text(encoding="utf-8")
    monkeypatch.setattr("kb.cli._confirm_write", lambda _prompt: False)

    result = CliRunner().invoke(
        cli,
        ["--kb", str(root), "dedupe", "rollback", str(manifest), "--write", "--confirm"],
    )

    assert result.exit_code == 0
    assert result.output == "cancelled\n"
    assert (root / "old.md").read_text(encoding="utf-8") == changed_source


def test_dedupe_rollback_confirmed_write_restores_files(tmp_path: Path, monkeypatch) -> None:
    root = _repo_with_plan(tmp_path)
    apply_plan(root, [{"source": "old.md", "target": "new.md"}], write=True)
    manifest = root / ".kb-tool-backup" / "manifest.json"
    prompts: list[str] = []

    def confirm(prompt: str) -> bool:
        prompts.append(prompt)
        return True

    monkeypatch.setattr("kb.cli._confirm_write", confirm)
    result = CliRunner().invoke(
        cli,
        ["--kb", str(root), "dedupe", "rollback", str(manifest), "--write", "--confirm"],
    )

    assert result.exit_code == 0, result.output
    assert prompts and "restore 1 file(s)" in prompts[0]
    assert (root / "old.md").read_text(encoding="utf-8") == "old content\n"


def test_confirm_write_refuses_non_tty(monkeypatch) -> None:
    import io

    import click

    import kb.cli

    stream = io.StringIO()
    monkeypatch.setattr(kb.cli.sys, "stdin", stream)

    try:
        kb.cli._confirm_write("confirm?")
    except click.ClickException as exc:
        assert "without an interactive terminal" in str(exc)
    else:
        raise AssertionError("non-interactive writes must be refused")
