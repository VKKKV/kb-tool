from pathlib import Path
import subprocess

from kb.dedupe import verify_redirects


def _repo(tmp_path: Path, files: dict[str, str]) -> Path:
    for name, text in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    subprocess.run(["git", "-C", str(tmp_path), "init", "-q"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "add", "."], check=True)
    return tmp_path


def test_verify_redirects_resolves_target(tmp_path: Path) -> None:
    repo = _repo(tmp_path, {"old.md": "> Moved to [[new]].\n", "new.md": "# New\n"})
    rows = verify_redirects(repo)
    assert rows[0]["ok"] is True
    assert rows[0]["target"] == "new.md"


def test_verify_redirects_reports_missing_and_chain(tmp_path: Path) -> None:
    repo = _repo(tmp_path, {
        "missing.md": "> Moved to [[gone]].\n",
        "chain.md": "> Moved to [[old]].\n",
        "old.md": "> Moved to [[new]].\n",
        "new.md": "# New\n",
    })
    rows = {row["source"]: row for row in verify_redirects(repo)}
    assert rows["missing.md"]["status"] == "missing"
    assert rows["chain.md"]["status"] == "chain"
    assert rows["chain.md"]["ok"] is False


def test_verify_redirects_reports_cycle(tmp_path: Path) -> None:
    repo = _repo(tmp_path, {
        "a.md": "> Moved to [[b]].\n",
        "b.md": "> Moved to [[a]].\n",
    })
    rows = verify_redirects(repo)
    assert len(rows) == 2
    assert all(row["status"] == "cycle" and not row["ok"] for row in rows)