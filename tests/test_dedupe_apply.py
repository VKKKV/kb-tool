import pytest
import subprocess

from kb.dedupe import apply_plan
from kb.dedupe import MigrationPreflightError


def test_apply_plan_defaults_to_dry_run_and_preserves_source(tmp_path) -> None:
    source = tmp_path / "old.md"
    target = tmp_path / "new.md"
    source.write_text("old content\n", encoding="utf-8")
    target.write_text("canonical\n", encoding="utf-8")
    plan = [{"operation": "redirect", "source": "old.md", "target": "new.md"}]
    rows = apply_plan(tmp_path, plan)
    assert rows[0]["status"] == "dry-run"
    assert rows[0]["source_deleted"] is False
    assert source.read_text(encoding="utf-8") == "old content\n"


def test_apply_plan_write_only_writes_redirect_stub(tmp_path) -> None:
    source = tmp_path / "old.md"
    target = tmp_path / "new.md"
    source.write_text("old content\n", encoding="utf-8")
    target.write_text("canonical\n", encoding="utf-8")
    rows = apply_plan(tmp_path, [{"source": "old.md", "target": "new.md"}], write=True)
    assert rows[0]["status"] == "applied"
    assert source.read_text(encoding="utf-8") == "> Moved to [[new]].\n"


def test_apply_plan_preserves_frontmatter_and_rejects_changed_source(tmp_path) -> None:
    source = tmp_path / "old.md"
    target = tmp_path / "new.md"
    source.write_text("---\ntags: [x]\n---\nold\n", encoding="utf-8")
    target.write_text("canonical\n", encoding="utf-8")
    plan = [{"source": "old.md", "target": "new.md"}]
    apply_plan(tmp_path, plan, write=True)
    assert source.read_text(encoding="utf-8") == "---\ntags: [x]\n---\n> Moved to [[new]].\n"


def test_apply_plan_trash_is_recoverable(tmp_path) -> None:
    source = tmp_path / "old.md"
    target = tmp_path / "new.md"
    source.write_text("old", encoding="utf-8")
    target.write_text("new", encoding="utf-8")
    apply_plan(tmp_path, [{"source": "old.md", "target": "new.md"}],
               write=True, source_after="trash")
    assert not source.exists()
    assert (tmp_path / ".trash/old.md").read_text(encoding="utf-8") == "old"


def test_apply_preflight_is_structured(tmp_path) -> None:
    subprocess.run(["git", "-C", str(tmp_path), "init", "-q"], check=True)
    (tmp_path / "old.md").write_text("old", encoding="utf-8")
    (tmp_path / "new.md").write_text("new", encoding="utf-8")
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    (tmp_path / "a/old.md").write_text("# x", encoding="utf-8")
    (tmp_path / "b/old.md").write_text("# x", encoding="utf-8")
    (tmp_path / "inbound.md").write_text("[[old]]", encoding="utf-8")
    subprocess.run(["git", "-C", str(tmp_path), "add", "."], check=True)
    with pytest.raises(MigrationPreflightError) as error:
        apply_plan(tmp_path, [{"source": "old.md", "target": "new.md"}])
    assert error.value.issues[0]["status"] == "ambiguous"


def test_apply_failure_restores_already_committed_files(tmp_path, monkeypatch) -> None:
    source = tmp_path / "old.md"
    target = tmp_path / "new.md"
    inbound = tmp_path / "inbound.md"
    source.write_text("old\n", encoding="utf-8")
    target.write_text("new\n", encoding="utf-8")
    inbound.write_text("[[old]]\n", encoding="utf-8")

    import kb.dedupe as dedupe
    original_write = dedupe._atomic_write
    calls = 0

    def fail_on_second(path, text):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("injected write failure")
        original_write(path, text)

    monkeypatch.setattr(dedupe, "_atomic_write", fail_on_second)
    with pytest.raises(RuntimeError, match="completed files were restored"):
        apply_plan(tmp_path, [{"source": "old.md", "target": "new.md"}], write=True)
    assert inbound.read_text(encoding="utf-8") == "[[old]]\n"
    assert source.read_text(encoding="utf-8") == "old\n"


def test_apply_batch_failure_restores_multiple_plan_items(tmp_path, monkeypatch) -> None:
    files = {
        "old-a.md": "old a\n",
        "new-a.md": "new a\n",
        "old-b.md": "old b\n",
        "new-b.md": "new b\n",
        "inbound-a.md": "[[old-a]]\n",
        "inbound-b.md": "[[old-b]]\n",
    }
    for name, content in files.items():
        (tmp_path / name).write_text(content, encoding="utf-8")

    import kb.dedupe as dedupe
    original_write = dedupe._atomic_write
    calls = 0

    def fail_on_fourth(path, text):
        nonlocal calls
        calls += 1
        if calls == 4:
            raise OSError("injected batch failure")
        original_write(path, text)

    monkeypatch.setattr(dedupe, "_atomic_write", fail_on_fourth)
    plan = [
        {"source": "old-a.md", "target": "new-a.md"},
        {"source": "old-b.md", "target": "new-b.md"},
    ]
    with pytest.raises(RuntimeError, match="completed files were restored"):
        apply_plan(tmp_path, plan, write=True)
    for name, content in files.items():
        assert (tmp_path / name).read_text(encoding="utf-8") == content


def test_manifest_write_failure_restores_batch(tmp_path, monkeypatch) -> None:
    source = tmp_path / "old.md"
    target = tmp_path / "new.md"
    source.write_text("old\n", encoding="utf-8")
    target.write_text("new\n", encoding="utf-8")
    import kb.dedupe as dedupe
    original_write = dedupe._atomic_write

    def fail_manifest(path, text):
        if path.name == "manifest.json":
            raise OSError("injected manifest failure")
        original_write(path, text)

    monkeypatch.setattr(dedupe, "_atomic_write", fail_manifest)
    with pytest.raises(RuntimeError, match="manifest commit failed"):
        apply_plan(tmp_path, [{"source": "old.md", "target": "new.md"}], write=True)
    assert source.read_text(encoding="utf-8") == "old\n"


def test_post_commit_verification_failure_restores_batch(tmp_path, monkeypatch) -> None:
    source = tmp_path / "old.md"
    target = tmp_path / "new.md"
    source.write_text("old\n", encoding="utf-8")
    target.write_text("new\n", encoding="utf-8")
    import kb.dedupe as dedupe
    monkeypatch.setattr(dedupe, "verify_manifest", lambda repo, manifest: [{"ok": False}])
    with pytest.raises(RuntimeError, match="apply commit failed"):
        apply_plan(tmp_path, [{"source": "old.md", "target": "new.md"}], write=True)
    assert source.read_text(encoding="utf-8") == "old\n"
    assert not (tmp_path / ".kb-tool-backup/manifest.json").exists()


def test_require_clean_git_blocks_dirty_worktree(tmp_path) -> None:
    subprocess.run(["git", "-C", str(tmp_path), "init", "-q"], check=True)
    source = tmp_path / "old.md"
    target = tmp_path / "new.md"
    source.write_text("old\n", encoding="utf-8")
    target.write_text("new\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(tmp_path), "add", "."], check=True)
    source.write_text("dirty\n", encoding="utf-8")
    with pytest.raises(ValueError, match="worktree is dirty"):
        apply_plan(tmp_path, [{"source": "old.md", "target": "new.md"}],
                   write=True, require_clean_git=True)

def test_trash_move_failure_restores_source(tmp_path, monkeypatch) -> None:
    source = tmp_path / "old.md"
    target = tmp_path / "new.md"
    source.write_text("old\n", encoding="utf-8")
    target.write_text("new\n", encoding="utf-8")
    import kb.dedupe as dedupe
    original_replace = dedupe.os.replace

    def fail_trash(src, dst):
        if str(dst).endswith(".trash/old.md"):
            raise OSError("injected trash failure")
        original_replace(src, dst)

    monkeypatch.setattr(dedupe.os, "replace", fail_trash)
    with pytest.raises(RuntimeError, match="apply commit failed"):
        apply_plan(tmp_path, [{"source": "old.md", "target": "new.md"}],
                   write=True, source_after="trash")
    assert source.read_text(encoding="utf-8") == "old\n"