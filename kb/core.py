"""Shared state: git file index, wikilink/markdown-link resolver, code stripping."""

from __future__ import annotations

import os
import re
import subprocess
import urllib.parse
from collections import defaultdict
from pathlib import Path
from typing import Optional

# ── defaults ──────────────────────────────────────────────────────────
DEFAULT_KB = Path(os.environ.get("KB_ROOT", "~/code/knowledge")).expanduser()

EXCLUDE_SCAN_PREFIXES = (
    "50-diary/",
    "60-archive/",
    "30-reference/references/bookmarks/archive/",
)

EXTERNAL_SCHEMES = (
    "http://", "https://", "mailto:", "tel:", "ftp://",
    "file://", "obsidian://", "zotero://",
)

PLACEHOLDER_RE = re.compile(
    r"^(path|local_path|url|new_path|old_path|your-|example|todo|xxx|\$|\$\{|\d+|\.+\..*|.*\*.*|.*<.*>.*)$",
    re.I,
)

SITE_PATH_PREFIXES = (
    "/categories/", "/category/", "/tags/", "/tag/", "/archives/", "/archive/",
    "/changelog/", "/start/", "/docs/", "/guide/", "/guides/", "/tutorial/",
    "/tutorials/", "/blog/", "/skills-market/", "/advanced/", "/uploads/",
)
SITE_RELATIVE_PREFIXES = tuple(p.lstrip("/") for p in SITE_PATH_PREFIXES)

MD_LINK_RE = re.compile(r"(?<!\!)\[([^\]\n]+)\]\(([^)\n]+)\)")
WIKI_RE = re.compile(r"(?<!`)\[\[([^\]\n]+)\]\]")


# ── code stripping ────────────────────────────────────────────────────

def strip_code(text: str) -> str:
    """Remove fenced code blocks (``` / ~~~) from text, preserving line count."""
    lines = []
    in_fence = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_fence = not in_fence
            lines.append("")
            continue
        lines.append("" if in_fence else line)
    return "\n".join(lines)


# ── git helpers ───────────────────────────────────────────────────────

def git_files(repo: Path, pattern: str | None = None) -> list[str]:
    """List git-tracked files, optionally filtered by glob pattern."""
    cmd = ["git", "-C", str(repo), "-c", "core.quotePath=false", "ls-files"]
    if pattern:
        cmd.append(pattern)
    out = subprocess.check_output(cmd, text=True)
    return [line for line in out.splitlines() if line.strip()]


# ── file index ────────────────────────────────────────────────────────

class FileIndex:
    """Builds and caches Obsidian-compatible target resolution index."""

    def __init__(self, repo: Path):
        self.repo = repo
        self.all_files: list[str] = git_files(repo)
        self.md_files: list[str] = [p for p in git_files(repo, "*.md")]
        self.file_set: set[str] = set(self.all_files)
        self.md_set: set[str] = set(self.md_files)

        # directories
        self.dirs: set[str] = set()
        for f in self.all_files:
            cur = Path(f).parent
            while str(cur) != ".":
                self.dirs.add(str(cur) + "/")
                cur = cur.parent

        # Obsidian resolution maps
        self._by_stem: dict[str, list[str]] = defaultdict(list)
        self._by_noext: dict[str, str] = {}
        self._by_basename: dict[str, str] = {}

        for fp in sorted(self.md_files):
            self._by_noext[str(Path(fp).with_suffix(""))] = fp
            stem = Path(fp).stem
            self._by_stem[stem].append(fp)
            # basename: last wins (Obsidian warns on dupes, picks one)
            self._by_basename[stem] = fp

        # grouped by directory
        self.by_dir: dict[str, list[str]] = defaultdict(list)
        for rel in self.md_files:
            self.by_dir[str(Path(rel).parent)].append(rel)
        for rels in self.by_dir.values():
            rels.sort()

    def scan_files(self, exclude: tuple[str, ...] | None = None) -> list[str]:
        """MD files minus excluded prefixes."""
        ex = exclude if exclude is not None else EXCLUDE_SCAN_PREFIXES
        return [p for p in self.md_files if not any(p.startswith(e) for e in ex)]

    def exists(self, candidate: str) -> bool:
        """Check if a normalized path resolves to a tracked file or directory."""
        if candidate in self.file_set:
            return True
        if candidate in self.dirs or candidate + "/" in self.dirs:
            return True
        if candidate.endswith("/") and candidate in self.dirs:
            return True
        return False

    def resolve_candidates(self, src: Path, raw: str, kind: str) -> list[str]:
        """Return list of candidate paths for a link target, preserving order."""
        target = clean_target(raw)
        if not target or target.startswith("#"):
            return ["__ok__"]
        lower = target.lower()
        if lower.startswith(EXTERNAL_SCHEMES) or re.match(r"^[a-z][a-z0-9+.-]*:", lower):
            return ["__external__"]
        if PLACEHOLDER_RE.match(target):
            return ["__placeholder__"]

        src_text = str(src)
        if kind == "markdown" and self._is_site_path_noise(src_text, target):
            return ["__site_path__"]
        if kind == "markdown" and self._is_html_doc_noise(src_text, target):
            return ["__html_doc__"]

        target = target.lstrip("/")
        if target.startswith("../") or target.startswith("./"):
            bases = [(src.parent / target).as_posix()]
        else:
            bases = [target, (src.parent / target).as_posix()]

        candidates = []
        for base in bases:
            normalized = os.path.normpath(base).replace("\\", "/")
            if normalized in ("", "."):
                continue
            candidates.extend([normalized, normalized + "/"])
            if not normalized.endswith(".md"):
                candidates.extend([
                    normalized + ".md",
                    normalized + "/README.md",
                    normalized + "/index.md",
                ])

        # Obsidian resolves wikilinks by basename even when the old path no
        # longer exists. This avoids false positives after KB restructuring.
        if kind == "wikilink":
            stem = Path(target).stem
            if stem in self._by_basename:
                candidates.append(self._by_basename[stem])
            for fp in self._by_stem.get(stem, []):
                if fp not in candidates:
                    candidates.append(fp)

        # dedupe preserving order
        seen = []
        for c in candidates:
            c = os.path.normpath(c).replace("\\", "/")
            if c not in seen:
                seen.append(c)
        return seen

    def target_exists(self, candidates: list[str]) -> bool:
        """Check if any candidate resolves."""
        if candidates and candidates[0] in (
            "__ok__", "__external__", "__placeholder__", "__site_path__", "__html_doc__"
        ):
            return True
        for c in candidates:
            if self.exists(c):
                return True
        return False

    @staticmethod
    def _is_site_path_noise(src: str, target: str) -> bool:
        lower = target.lower()
        if lower.startswith(SITE_PATH_PREFIXES) or lower.startswith(SITE_RELATIVE_PREFIXES):
            return True
        if src.startswith("30-reference/security/ctf-writeups/") and (
            lower.startswith("/categories/") or lower.startswith("/tags/")
        ):
            return True
        if src.startswith("30-reference/references/trellis/") and (
            lower.startswith("/changelog/") or lower.startswith("/start/")
            or lower.startswith("/blog/") or lower.startswith("/skills-market/")
            or lower.startswith("/advanced/") or lower == "./custom-skills"
        ):
            return True
        if target.startswith("/") and re.search(r"\.html?$", lower):
            return True
        return False

    @staticmethod
    def _is_html_doc_noise(src: str, target: str) -> bool:
        lower = target.lower()
        if lower.startswith("/"):
            return False
        if re.search(r"(^|/)[^/]+\.html?$", lower) or re.search(r"(^|/)index\.html?$", lower):
            return src.startswith("30-reference/")
        return False

    def wikilink_targets(self) -> dict[str, set[str]]:
        """Build full wikilink graph: source -> set of resolved targets."""
        outgoing: dict[str, set[str]] = {}
        for fp in sorted(self.md_files):
            fpath = self.repo / fp
            try:
                content = fpath.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            targets = set()
            for m in WIKI_RE.finditer(content):
                raw = m.group(1).split("|")[0].strip().lstrip("!")
                if "#" in raw:
                    raw = raw.split("#")[0]
                if not raw:
                    continue
                resolved = self._resolve_wikilink_fast(fp, raw)
                if resolved and resolved != fp:
                    targets.add(resolved)
            if targets:
                outgoing[fp] = targets
        return outgoing

    def _resolve_wikilink_fast(self, source: str, raw: str) -> Optional[str]:
        """Fast bare-name + path resolution for graph building."""
        bare = raw.replace(".md", "")
        # bare name
        if bare in self._by_basename:
            return self._by_basename[bare]
        # exact path
        for c in (raw, raw + ".md"):
            c = os.path.normpath(c).replace("\\", "/")
            if c in self.md_set:
                return c
        # relative
        src_dir = str(Path(source).parent)
        for c in (raw, raw + ".md"):
            resolved = os.path.normpath(os.path.join(src_dir, c)).replace("\\", "/")
            if resolved in self.md_set:
                return resolved
        return None


# ── utils ─────────────────────────────────────────────────────────────

def clean_target(raw: str) -> str:
    """Strip quotes, angle brackets, URL-decode, remove anchor."""
    target = raw.strip()
    m = re.match(r'([^\s]+)\s+["\'].*["\']$', target)
    if m:
        target = m.group(1)
    if target.startswith("<") and target.endswith(">"):
        target = target[1:-1]
    target = urllib.parse.unquote(target)
    return target.split("#", 1)[0].strip()
