"""Link fixers: zero-wikilinks connector + pipe pollution cleaner.

Merges: kb-connect-zero-wikilinks.py, kb-fix-pipe-pollution.py
"""

from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path

from .core import FileIndex, WIKI_RE


# ── zero-wikilinks connector ──────────────────────────────────────────

ROOT_HUBS = {
    "10-projects": "10-projects/README",
    "20-areas": "20-areas/README",
    "30-reference": "30-reference/README",
    "40-notes": "40-notes/README",
    "50-diary": "50-diary/README",
    "60-archive": "60-archive/README",
    "graph": "graph/README",
}

THEMATIC_HUBS = [
    "30-reference/security/README",
    "30-reference/workflows/README",
    "30-reference/references/README",
    "30-reference/music/README",
    "30-reference/linux/README",
    "30-reference/rust/README",
    "30-reference/computing-systems/README",
    "40-notes/README",
    "40-notes/writing/README",
    "40-notes/kb-maintenance/README",
    "40-notes/weread/README",
    "20-areas/tools/README",
    "20-areas/snippets/README",
    "20-areas/arch/README",
    "50-diary/README",
    "60-archive/README",
]


def _title_for(index: FileIndex, rel_no_ext: str) -> str:
    """Extract title from first # heading, or generate from filename."""
    path = index.repo / (rel_no_ext + ".md")
    if path.exists():
        for line in path.read_text(errors="ignore").splitlines()[:60]:
            if line.startswith("# "):
                return line[2:].strip()
    return Path(rel_no_ext).name.replace("-", " ")


def _dir_readme(index: FileIndex, dir_rel: str) -> str | None:
    if dir_rel == ".":
        return "README" if "README.md" in index.md_set else None
    cand = f"{dir_rel}/README.md"
    noext = str(Path(cand).with_suffix(""))
    return noext if cand in index.md_set else None


def _parent_readme(index: FileIndex, dir_rel: str) -> str | None:
    parent = str(Path(dir_rel).parent)
    if parent == ".":
        return "README" if "README.md" in index.md_set else None
    return _dir_readme(index, parent)


def _sibling_links(index: FileIndex, rel: str, max_count: int = 2) -> list[str]:
    dir_rel = str(Path(rel).parent)
    siblings = [p for p in index.by_dir.get(dir_rel, []) if p != rel and Path(p).name != "README.md"]
    if not siblings:
        return []
    try:
        idx = siblings.index(rel)
    except ValueError:
        idx = 0
    picks = []
    for i in [idx - 1, idx + 1, 0, len(siblings) - 1]:
        if 0 <= i < len(siblings) and siblings[i] not in picks:
            picks.append(siblings[i])
        if len(picks) >= max_count:
            break
    return [str(Path(p).with_suffix("")) for p in picks]


def _default_links(index: FileIndex, rel: str) -> list[str]:
    """Compute default links for a zero-wikilink file."""
    candidates: list[str] = []
    dir_rel = str(Path(rel).parent)
    top = rel.split("/", 1)[0]

    def _add(target: str | None):
        if target:
            t = target.strip("/").removesuffix(".md")
            if t not in candidates:
                candidates.append(t)

    _add(_dir_readme(index, dir_rel))
    _add(_parent_readme(index, dir_rel))
    _add(ROOT_HUBS.get(top))

    for hub in THEMATIC_HUBS:
        if rel.startswith(str(Path(hub).parent) + "/"):
            _add(hub)

    for sib in _sibling_links(index, rel):
        _add(sib)

    for fallback in ["index", "README"]:
        if len(candidates) >= 2:
            break
        _add(fallback)

    return candidates[:3]


def fix_zero_links(index: FileIndex, dry_run: bool = False) -> list[str]:
    """Add ## 关联 section to files with no wikilinks. Returns list of changed files."""
    changed: list[str] = []
    for rel in index.md_files:
        if Path(rel).name == "README.md":
            continue
        path = index.repo / rel
        text = path.read_text(errors="ignore")
        if "[[" in text:
            continue

        links = _default_links(index, rel)
        if not links:
            continue

        # build new lines
        existing = set(re.findall(r"\[\[([^|\]#]+)", text))
        new_lines = []
        for link in links:
            if link in existing or link + ".md" in existing:
                continue
            title = _title_for(index, link)
            new_lines.append(f"- [[{link}|{title}]]")
        if not new_lines:
            continue

        if not text.endswith("\n"):
            text += "\n"
        addition = "\n".join(new_lines) + "\n"
        if re.search(r"(?m)^## 关联\s*$", text):
            new_text = text + addition
        else:
            new_text = text + "\n## 关联\n\n" + addition

        if not dry_run:
            path.write_text(new_text)
        changed.append(rel)
    return changed


def cmd_fix_zero(index: FileIndex, dry_run: bool, limit: int):
    """CLI handler for 'kb fix-zero'."""
    changed = fix_zero_links(index, dry_run=dry_run)
    prefix = "[DRY RUN] " if dry_run else ""
    print(f"{prefix}修改: {len(changed)} 文件")
    for f in changed[:limit]:
        print(f"  {f}")
    if len(changed) > limit:
        print(f"  ... 另有 {len(changed) - limit} 文件")


# ── pipe pollution fixer ──────────────────────────────────────────────

def _is_table_row(line: str) -> bool:
    if not line.startswith("| "):
        return False
    rest = line[2:]
    return " |" in rest or rest.strip().startswith("---")


def fix_pipe_pollution(path: str) -> int:
    """Fix pipe pollution in a single file. Returns lines changed."""
    with open(path) as f:
        lines = f.readlines()

    fixed = []
    changes = 0
    in_code_block = False

    for line in lines:
        raw = line.rstrip("\n")
        if raw.lstrip().startswith("```"):
            in_code_block = not in_code_block

        if raw == "|":
            fixed.append("")
            changes += 1
            continue

        if raw.startswith("||"):
            if raw.startswith("||-"):
                fixed.append(raw[1:])
                changes += 1
                continue
            candidate = raw[1:]
            if _is_table_row(candidate) or candidate.lstrip().startswith("---"):
                fixed.append(candidate)
                changes += 1
                continue
            rest = raw[2:]
            fixed.append("" if rest.lstrip() == "" else rest)
            changes += 1
            continue

        if raw.startswith("|"):
            rest = raw[1:]
            stripped = rest.lstrip()
            if _is_table_row(raw):
                fixed.append(raw)
                continue
            if stripped.startswith("---"):
                fixed.append(raw)
                continue
            fixed.append(rest)
            changes += 1
            continue

        fixed.append(raw)

    if changes > 0:
        with open(path, "w") as f:
            f.write("\n".join(fixed))
    return changes


def cmd_fix_pipe(index: FileIndex, paths: list[str] | None):
    """CLI handler for 'kb fix-pipe'."""
    targets = paths if paths else [
        str(index.repo / p) for p in index.md_files
    ]
    total = 0
    for p in targets:
        n = fix_pipe_pollution(p)
        if n > 0:
            print(f"  {p}: {n} lines fixed")
            total += n
    print(f"总计: {total} lines fixed across {len(targets)} file(s)")
