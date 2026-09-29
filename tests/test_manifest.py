import json

from kb.dedupe import apply_plan, merge_drafts, rollback_manifest, verify_manifest


def test_manifest_rollback_and_merge_draft(tmp_path) -> None:
    source = tmp_path / "old.md"
    target = tmp_path / "new.md"
    source.write_text("old", encoding="utf-8")
    target.write_text("new", encoding="utf-8")
    plan = [{"source": "old.md", "target": "new.md"}]
    apply_plan(tmp_path, plan, write=True, source_after="redirect")
    manifest = json.loads((tmp_path / ".kb-tool-backup/manifest.json").read_text())
    assert manifest["preflight"] == {"status": "passed", "issues": []}
    assert manifest["migration_stats"]["files_scanned"] >= 2
    assert all(row["ok"] for row in verify_manifest(tmp_path, manifest))
    assert manifest["tool_version"] == "0.1.0"
    preview = rollback_manifest(tmp_path, manifest)
    assert all(row["ok"] for row in preview)
    rollback_manifest(tmp_path, manifest, write=True)
    assert source.read_text(encoding="utf-8") == "old"
    drafts = merge_drafts(tmp_path, plan)
    assert "Merged from old.md" in drafts[0]["content"]
