"""Index / README sync — auto-recount git-tracked files and patch headers."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Optional

from .core import FileIndex


def _count_md(index: FileIndex) -> int:
    """Count git-tracked .md files."""
    return len(index.md_files)


def _update_readme_count(repo: Path, new_count: int) -> tuple[bool, str]:
    """Patch the 'N MD' count in README.md. Returns (changed, old_line)."""
    readme = repo / "README.md"
    if not readme.exists():
        return False, ""
    text = readme.read_text(encoding="utf-8")
    # match patterns like: 1539 MD · 更新: 2026-06-23  or  1539 MD
    pattern = r"(\d+)\s*MD"
    m = re.search(pattern, text)
    if not m:
        return False, ""
    old_count = int(m.group(1))
    if old_count == new_count:
        return False, m.group(0)
    new_text = text[:m.start()] + f"{new_count} MD" + text[m.end():]
    readme.write_text(new_text, encoding="utf-8")
    return True, f"{old_count} MD → {new_count} MD"


def sync_index(
    index: FileIndex,
    dry_run: bool = False,
    index_path: Optional[str] = None,
) -> dict:
    """Sync README.md file count and optionally regenerate index.md.

    Returns dict with results.
    """
    count = _count_md(index)
    changed, old = _update_readme_count(index.repo, count) if not dry_run else (False, "")

    result = {
        "md_count": count,
        "readme_patched": changed,
        "readme_old": old,
    }

    if index_path:
        idx_file = Path(index_path)
        if idx_file.exists():
            text = idx_file.read_text(encoding="utf-8")
            pattern = r"(\d+)\s*MD"
            m = re.search(pattern, text)
            if m and int(m.group(1)) != count:
                if not dry_run:
                    new_text = text[:m.start()] + f"{count} MD" + text[m.end():]
                    idx_file.write_text(new_text, encoding="utf-8")
                result["index_patched"] = True
                result["index_old"] = m.group(0)
            else:
                result["index_patched"] = False

    return result


def cmd_sync(index: FileIndex, dry_run: bool, index_path: str | None):
    """CLI handler for 'kb sync'."""
    result = sync_index(index, dry_run=dry_run, index_path=index_path)
    prefix = "[DRY RUN] " if dry_run else ""
    print(f"{prefix}MD 文件数: {result['md_count']}")
    if result.get("readme_patched"):
        print(f"README.md: {result['readme_old']}")
    else:
        print("README.md: 已是最新" if not dry_run else "README.md: 不需更新")
    if "index_patched" in result:
        if result["index_patched"]:
            print(f"index.md: {result.get('index_old', '')}")
        else:
            print("index.md: 已是最新")
