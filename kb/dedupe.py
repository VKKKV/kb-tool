"""Read-only structural duplicate candidate detection."""

from __future__ import annotations

from collections import defaultdict
from itertools import combinations
from typing import Any
from pathlib import Path
import difflib
import hashlib
import json
import re
import shutil
import os
import subprocess
import tempfile
from datetime import datetime, timezone


class MigrationPreflightError(ValueError):
    """Structured fail-closed migration preflight failure."""

    def __init__(self, issues: list[dict[str, Any]]):
        self.issues = issues
        super().__init__(f"migration preflight blocked: {len(issues)} issue(s)")


def _markdown_files(repo: Path) -> list[Path]:
    """Return vault Markdown files, excluding generated backup data."""
    return sorted(
        path for path in repo.rglob("*.md")
        if ".kb-tool-backup" not in path.parts and ".trash" not in path.parts
    )


def _body_without_frontmatter(text: str) -> str:
    """Remove a leading YAML frontmatter block for content comparisons."""
    if not text.startswith("---\n"):
        return text
    end = text.find("\n---\n", 4)
    return text[end + 5:] if end >= 0 else text


def _normalize_content(text: str) -> str:
    """Normalize whitespace while preserving Markdown content semantics enough for reports."""
    body = _body_without_frontmatter(text).replace("\r\n", "\n")
    return "\n".join(line.rstrip() for line in body.splitlines()).strip()


def scan_exact(repo: Path, include_frontmatter: bool = False) -> list[dict[str, Any]]:
    """Find pairs with identical normalized Markdown content."""
    groups: dict[str, list[str]] = defaultdict(list)
    for path in _markdown_files(repo):
        text = path.read_text(encoding="utf-8")
        content = text.replace("\r\n", "\n") if include_frontmatter else _normalize_content(text)
        digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
        groups[digest].append(path.relative_to(repo).as_posix())
    return [
        {"sha256": digest, "paths": paths, "count": len(paths),
         "method": "exact", "includes_frontmatter": include_frontmatter}
        for digest, paths in sorted(groups.items()) if len(paths) > 1
    ]


def _paragraphs(text: str) -> list[tuple[int, str]]:
    """Extract plain paragraphs, skipping frontmatter, fences, headings, and blockquotes."""
    body = _body_without_frontmatter(text)
    result: list[tuple[int, str]] = []
    buffer: list[str] = []
    start = 0
    fenced = False
    for number, line in enumerate(body.splitlines(), 1):
        stripped = line.strip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            fenced = not fenced
        if fenced or not stripped or stripped.startswith("#") or stripped.startswith(">"):
            if buffer:
                normalized = _normalize_content("\n".join(buffer))
                if normalized:
                    result.append((start, normalized))
                buffer = []
            continue
        if not buffer:
            start = number
        buffer.append(line)
    if buffer:
        normalized = _normalize_content("\n".join(buffer))
        if normalized:
            result.append((start, normalized))
    return result


def scan_paragraphs(repo: Path, min_chars: int = 40) -> list[dict[str, Any]]:
    """Find identical paragraphs shared by different Markdown notes."""
    occurrences: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for path in _markdown_files(repo):
        for line, paragraph in _paragraphs(path.read_text(encoding="utf-8")):
            if len(paragraph) < min_chars:
                continue
            digest = hashlib.sha256(paragraph.encode("utf-8")).hexdigest()
            occurrences[digest].append({
                "path": path.relative_to(repo).as_posix(),
                "line": line,
                "text": paragraph,
            })
    rows = []
    for digest, matches in sorted(occurrences.items()):
        paths = {match["path"] for match in matches}
        if len(paths) < 2:
            continue
        rows.append({"sha256": digest, "count": len(matches), "occurrences": matches,
                     "method": "paragraph-exact"})
    rows.sort(key=lambda row: (-row["count"], row["sha256"]))
    return rows


def scan_structural(graph: Any, threshold: float = 0.25,
                    limit: int = 100) -> list[dict[str, Any]]:
    """Return note pairs with Jaccard-similar Wikilink neighborhoods."""
    if not 0 <= threshold <= 1:
        raise ValueError("threshold must be between 0 and 1")
    neighborhoods = {
        node: set(graph.predecessors(node)) | set(graph.successors(node))
        for node in graph.nodes
    }
    inverted: dict[str, set[str]] = defaultdict(set)
    for node, neighbors in neighborhoods.items():
        for neighbor in neighbors:
            inverted[neighbor].add(node)
    pairs: set[tuple[str, str]] = set()
    for candidates in inverted.values():
        pairs.update(combinations(sorted(candidates), 2))
    rows: list[dict[str, Any]] = []
    for left, right in sorted(pairs):
        union = neighborhoods[left] | neighborhoods[right]
        score = len(neighborhoods[left] & neighborhoods[right]) / len(union) if union else 0.0
        if score >= threshold:
            rows.append({"left": left, "right": right, "score": round(score, 6),
                         "method": "jaccard", "semantic": False})
    rows.sort(key=lambda row: (-row["score"], row["left"], row["right"]))
    return rows[:limit]


def review_candidates(repo: Path, graph: Any, candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Enrich candidate pairs with file and graph facts for human review."""
    rows = []
    for candidate in candidates:
        left, right = candidate["left"], candidate["right"]
        if left not in graph or right not in graph:
            raise ValueError(f"candidate node not found in graph: {left}, {right}")
        left_path, right_path = repo / left, repo / right
        left_neighbors = set(graph.predecessors(left)) | set(graph.successors(left))
        right_neighbors = set(graph.predecessors(right)) | set(graph.successors(right))
        rows.append({
            **candidate,
            "left_bytes": left_path.stat().st_size if left_path.is_file() else None,
            "right_bytes": right_path.stat().st_size if right_path.is_file() else None,
            "source_sha256": hashlib.sha256(left_path.read_bytes()).hexdigest(),
            "target_sha256": hashlib.sha256(right_path.read_bytes()).hexdigest(),
            "left_in": graph.in_degree(left),
            "left_out": graph.out_degree(left),
            "right_in": graph.in_degree(right),
            "right_out": graph.out_degree(right),
            "shared_neighbors": sorted(left_neighbors & right_neighbors),
            "action": "review",
        })
    return rows


def make_redirect_plan(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Create an explicit, non-writing redirect plan from reviewed decisions."""
    plan = []
    for candidate in candidates:
        if candidate.get("action") != "redirect":
            continue
        source, target = candidate["left"], candidate["right"]
        item = {
            "operation": "redirect",
            "source": source,
            "target": target,
            "preserve_alias": True,
            "rewrite_inbound_links": True,
            "keep_source_file": True,
        }
        for key in ("source_sha256", "target_sha256"):
            if candidate.get(key):
                item[key] = candidate[key]
        plan.append(item)
    return plan


def apply_plan(repo: Path, plan: list[dict[str, Any]], write: bool = False,
               source_after: str = "redirect", require_clean_git: bool = False) -> list[dict[str, Any]]:
    """Preview or apply conservative redirect plans; never deletes source files."""
    repo = repo.resolve()
    if write and require_clean_git and (repo / ".git").exists():
        dirty = subprocess.check_output(["git", "-C", str(repo), "status", "--porcelain"], text=True)
        if dirty.strip():
            raise ValueError("git worktree is dirty; commit or stash changes before apply")
    if source_after not in {"keep", "redirect", "trash"}:
        raise ValueError("source_after must be keep, redirect, or trash")
    git_status = None
    if (repo / ".git").exists():
        git_status = subprocess.check_output(["git", "-C", str(repo), "status", "--porcelain"], text=True)
    reports = []
    manifest_files: list[dict[str, Any]] = []
    backup_root = repo / ".kb-tool-backup"
    replacements: dict[str, str] = {}
    for item in plan:
        replacements[Path(item["source"]).with_suffix("").as_posix()] = Path(item["target"]).with_suffix("").as_posix()
        replacements[item["source"]] = item["target"]
    changed_files: dict[Path, str] = {}
    preflight = migration_preflight(repo, replacements)
    stats = migration_stats(repo, replacements)
    if preflight:
        raise MigrationPreflightError(preflight)
    for path in repo.rglob("*.md"):
        if ".kb-tool-backup" in path.parts:
            continue
        original = path.read_text(encoding="utf-8")
        migrated = migrate_links(original, replacements)
        if migrated != original:
            changed_files[path] = migrated
    prepared_sources: list[tuple[Path, bytes, str, str]] = []
    for item in plan:
        _safe_plan_path(repo, item["source"])
        _safe_plan_path(repo, item["target"])
        if item["source"] == item["target"]:
            raise ValueError("source and target must differ")
        source = repo / item["source"]
        target = repo / item["target"]
        if not source.is_file() or not target.is_file():
            raise ValueError(f"source and target must be files: {item['source']} -> {item['target']}")
        old_bytes = source.read_bytes()
        target_bytes = target.read_bytes()
        if item.get("source_sha256") and hashlib.sha256(old_bytes).hexdigest() != item["source_sha256"]:
            raise ValueError(f"source changed since plan: {item['source']}")
        if item.get("target_sha256") and hashlib.sha256(target_bytes).hexdigest() != item["target_sha256"]:
            raise ValueError(f"target changed since plan: {item['target']}")
        old = old_bytes.decode("utf-8")
        frontmatter = ""
        if old.startswith("---\n") and "\n---\n" in old[4:]:
            end = old.find("\n---\n", 4) + len("\n---\n")
            frontmatter = old[:end]
        stub = frontmatter + f"> Moved to [[{Path(item['target']).with_suffix('').as_posix()}]].\n"
        if item.get("preserve_alias", False):
            target_text = changed_files.get(target) or target.read_text(encoding="utf-8")
            aliased = add_alias(target_text, Path(item["source"]).stem)
            collision = find_alias_collision(repo, Path(item["source"]).stem, item["target"])
            if collision:
                raise ValueError(f"alias collision: {Path(item['source']).stem} already used by {collision}")
            if aliased != target_text:
                changed_files[target] = aliased
        prepared_sources.append((source, old_bytes, stub, source_after))
        diff = "".join(difflib.unified_diff(
            old.splitlines(keepends=True), stub.splitlines(keepends=True),
            fromfile=item["source"], tofile=item["source"] + " (redirect)",
        ))
        if write and item is plan[-1]:
            try:
                backup_root.mkdir(parents=True, exist_ok=True)
                for path, content in changed_files.items():
                    backup = backup_root / path.relative_to(repo)
                    backup.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(path, backup)
                    _atomic_write(path, content)
                    manifest_files.append({"path": str(path.relative_to(repo)),
                                           "before_sha256": hashlib.sha256(backup.read_bytes()).hexdigest(),
                                           "after_sha256": hashlib.sha256(content.encode()).hexdigest(),
                                           "backup": str(backup.relative_to(repo))})
                for prepared_source, prepared_old, prepared_stub, prepared_after in prepared_sources:
                    if prepared_after == "redirect":
                        source_backup = backup_root / str(prepared_source.relative_to(repo))
                        source_backup.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(prepared_source, source_backup)
                        _atomic_write(prepared_source, prepared_stub)
                        manifest_files.append({"path": str(prepared_source.relative_to(repo)),
                                               "before_sha256": hashlib.sha256(prepared_old).hexdigest(),
                                               "after_sha256": hashlib.sha256(prepared_stub.encode()).hexdigest(),
                                               "backup": str(source_backup.relative_to(repo))})
                    elif prepared_after == "trash":
                        source_backup = backup_root / str(prepared_source.relative_to(repo))
                        source_backup.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(prepared_source, source_backup)
                        trash = repo / ".trash" / prepared_source.relative_to(repo)
                        trash.parent.mkdir(parents=True, exist_ok=True)
                        os.replace(prepared_source, trash)
                        manifest_files.append({"path": str(prepared_source.relative_to(repo)),
                                               "before_sha256": hashlib.sha256(prepared_old).hexdigest(),
                                               "after_sha256": None,
                                               "backup": str(source_backup.relative_to(repo))})
                verification = verify_manifest(repo, {"schema": "kb-tool.dedupe-apply/v1", "files": manifest_files})
                if any(not row["ok"] for row in verification):
                    raise RuntimeError("post-commit verification failed")
                if any(not row["ok"] for row in verify_fragments(repo)):
                    raise RuntimeError("fragment verification failed")
            except Exception as exc:
                _restore_manifest_entries(repo, manifest_files)
                raise RuntimeError("apply commit failed; completed files were restored") from exc
        reports.append({**item, "status": "applied" if write else "dry-run",
                        "diff": diff, "source_deleted": False,
                        "rewritten_files": [str(p.relative_to(repo)) for p in changed_files],
                        "backup_dir": str(backup_root.relative_to(repo)) if write else None,
                        "source_after": source_after, "migration_stats": stats})
    if write and reports:
        manifest = {"schema": "kb-tool.dedupe-apply/v1",
                    "tool_version": "0.1.0",
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "git_status_before": git_status,
                    "migration_stats": stats,
                    "preflight": {"status": "passed", "issues": []},
                    "files": manifest_files, "reports": reports}
        manifest_path = backup_root / "manifest.json"
        try:
            _atomic_write(manifest_path, json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
        except Exception as exc:
            _restore_manifest_entries(repo, manifest_files)
            raise RuntimeError("manifest commit failed; completed files were restored") from exc
        for report in reports:
            report["manifest"] = str(manifest_path.relative_to(repo))
    return reports


def _restore_manifest_entries(repo: Path, entries: list[dict[str, Any]]) -> None:
    for entry in reversed(entries):
        backup = repo / entry["backup"]
        path = repo / entry["path"]
        if backup.is_file():
            path.parent.mkdir(parents=True, exist_ok=True)
            _atomic_write(path, backup.read_text(encoding="utf-8"))


def migration_preflight(repo: Path, replacements: dict[str, str]) -> list[dict[str, Any]]:
    """Find ambiguous or missing inbound links before any write occurs."""
    from .core import FileIndex, strip_code
    if not (repo / ".git").exists():
        return []
    index = FileIndex(repo)
    issues = []
    source_names = set(replacements) | {Path(key).stem for key in replacements}
    for source in index.md_files:
        text = strip_code((repo / source).read_text(encoding="utf-8", errors="ignore"))
        for match in WIKILINK_RE.finditer(text):
            raw = match.group(2).split("|", 1)[0].strip()
            target = raw.split("#", 1)[0]
            if target not in source_names and Path(target).stem not in source_names:
                continue
            status, candidates = index.resolve_wikilink_status(source, raw)
            if status != "resolved":
                issues.append({"file": source, "raw": raw, "status": status,
                               "candidates": candidates})
        for match in MDLINK_RE.finditer(text):
            raw = match.group(2).split("#", 1)[0].strip()
            if raw not in replacements and raw.removesuffix(".md") not in replacements:
                continue
            if raw.startswith(("http://", "https://", "mailto:")):
                continue
            if ".." in Path(raw).parts:
                issues.append({"file": source, "raw": raw, "status": "unsafe", "candidates": []})
    return issues


def migration_stats(repo: Path, replacements: dict[str, str]) -> dict[str, Any]:
    """Count link candidates and rewritable links without modifying files."""
    stats = {"files_scanned": 0, "links_scanned": 0, "links_rewritable": 0,
             "links_skipped": 0, "ambiguous_links": 0, "missing_links": 0}
    from .core import FileIndex
    index = FileIndex(repo) if (repo / ".git").exists() else None
    for path in repo.rglob("*.md"):
        if ".kb-tool-backup" in path.parts or ".trash" in path.parts:
            continue
        stats["files_scanned"] += 1
        text = path.read_text(encoding="utf-8", errors="ignore")
        for match in WIKILINK_RE.finditer(text):
            stats["links_scanned"] += 1
            target = match.group(2).split("|", 1)[0].split("#", 1)[0].strip()
            if index and index.resolve_wikilink_status(str(path.relative_to(repo)), target)[0] == "ambiguous":
                stats["ambiguous_links"] += 1
            elif target in replacements or Path(target).stem in replacements:
                stats["links_rewritable"] += 1
            else:
                stats["links_skipped"] += 1
        for match in MDLINK_RE.finditer(text):
            raw = match.group(2).split("#", 1)[0].strip()
            if not raw or raw.startswith(("http://", "https://", "mailto:", "#")):
                continue
            target, fragment = index.resolve_fragment(str(path.relative_to(repo)), match.group(2)) if index else (None, None)
            if fragment and target:
                target_text = (repo / target).read_text(encoding="utf-8", errors="ignore")
                if not _fragment_exists(target_text, fragment):
                    stats["missing_links"] += 1
                    continue
            stats["links_scanned"] += 1
            if raw in replacements or raw.removesuffix(".md") in replacements:
                stats["links_rewritable"] += 1
            else:
                stats["links_skipped"] += 1
    return stats


def _safe_plan_path(repo: Path, relative: str) -> Path:
    candidate = Path(relative)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise ValueError(f"unsafe plan path: {relative}")
    resolved = (repo / candidate).resolve()
    try:
        resolved.relative_to(repo)
    except ValueError as exc:
        raise ValueError(f"path escapes repository: {relative}") from exc
    if resolved.is_symlink():
        raise ValueError(f"symlink path is not allowed: {relative}")
    return resolved


def _atomic_write(path: Path, text: str) -> None:
    fd, name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


WIKILINK_RE = re.compile(r"(!?\[\[)([^\]\n]+)(\]\])")
MDLINK_RE = re.compile(r"(?<!\!)\[([^\]\n]+)\]\(([^)\n]+)\)")


def _replace_unfenced(text: str, replacer: Any) -> str:
    """Apply a replacement line-by-line, skipping fenced and inline code."""
    out, fenced = [], False
    for line in text.splitlines(keepends=True):
        if line.lstrip().startswith(("```", "~~~")):
            fenced = not fenced
            out.append(line)
            continue
        if fenced:
            out.append(line)
            continue
        parts = re.split(r"(`[^`]*`)", line)
        out.append("".join(part if part.startswith("`") else replacer(part) for part in parts))
    return "".join(out)


def migrate_links(text: str, replacements: dict[str, str]) -> str:
    """Migrate supported internal links while preserving aliases/fragments."""
    def wiki_replace(segment: str) -> str:
        def replace(match: re.Match[str]) -> str:
            prefix, raw, suffix = match.groups()
            target, sep, display = raw.partition("|")
            base, frag_sep, fragment = target.partition("#")
            new_base = replacements.get(base) or replacements.get(base + ".md")
            if not new_base:
                return match.group(0)
            new_target = new_base + (frag_sep + fragment if frag_sep else "")
            return prefix + new_target + (sep + display if sep else "") + suffix
        return WIKILINK_RE.sub(replace, segment)

    def md_replace(segment: str) -> str:
        def replace(match: re.Match[str]) -> str:
            label, url = match.groups()
            path, sep, fragment = url.partition("#")
            new_path = replacements.get(path) or replacements.get(path.removesuffix(".md"))
            return match.group(0) if not new_path else f"[{label}]({new_path}{sep}{fragment if sep else ''})"
        return MDLINK_RE.sub(replace, segment)

    return _replace_unfenced(text, lambda segment: md_replace(wiki_replace(segment)))


def add_alias(text: str, alias: str) -> str:
    """Append a simple YAML aliases list; reject non-YAML-frontmatter notes."""
    if not text.startswith("---\n") or "\n---\n" not in text[4:]:
        return text
    end = text.find("\n---\n", 4)
    block = text[4:end]
    alias_match = re.search(r"^aliases[ \t]*:[ \t]*(.*)$", block, re.MULTILINE)
    if alias_match:
        value = alias_match.group(1).strip()
        if value and not (value.startswith("[") and value.endswith("]")):
            raise ValueError("complex or scalar aliases frontmatter is not supported")
        if re.search(rf"^\s*-\s*{re.escape(alias)}\s*$", block, re.MULTILINE):
            return text
        return text[:end] + f"\naliases:\n  - {alias}" + text[end:]
    return text[:end] + f"\naliases:\n  - {alias}" + text[end:]


def find_alias_collision(repo: Path, alias: str, target: str) -> str | None:
    """Return another note already declaring alias, if any."""
    pattern = re.compile(rf"^\s*-\s*{re.escape(alias)}\s*$", re.MULTILINE)
    for path in repo.rglob("*.md"):
        if path.as_posix().endswith(target) or ".kb-tool-backup" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        if text.startswith("---\n") and "\n---\n" in text[4:]:
            block = text[4:text.find("\n---\n", 4)]
            if re.search(r"^aliases\s*:", block, re.MULTILINE) and pattern.search(block):
                return str(path.relative_to(repo))
    return None


def verify_plan(repo: Path, plan: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Verify plan paths and optional hashes without changing files."""
    results = []
    for item in plan:
        row = {"source": item["source"], "target": item["target"], "ok": True, "errors": []}
        for role in ("source", "target"):
            path = repo / item[role]
            if not path.is_file():
                row["ok"] = False
                row["errors"].append(f"missing {role}: {item[role]}")
                continue
            expected = item.get(f"{role}_sha256")
            if expected and hashlib.sha256(path.read_bytes()).hexdigest() != expected:
                row["ok"] = False
                row["errors"].append(f"changed {role}: {item[role]}")
        results.append(row)
    return results


def rollback_manifest(repo: Path, manifest: dict[str, Any], write: bool = False) -> list[dict[str, Any]]:
    """Restore only files still matching their post-apply hashes."""
    if manifest.get("schema") != "kb-tool.dedupe-apply/v1":
        raise ValueError("unsupported or missing manifest schema")
    results = []
    for item in manifest.get("files", []):
        path = _safe_plan_path(repo, item["path"])
        backup = _safe_plan_path(repo, item["backup"])
        current_hash = hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None
        expected = item.get("after_sha256")
        ok = expected is None or current_hash == expected
        row = {"path": item["path"], "backup": item["backup"], "ok": ok,
               "status": "dry-run", "error": None}
        if not ok:
            row["error"] = "current file changed after apply"
        elif write:
            backup_data = backup.read_bytes()
            path.parent.mkdir(parents=True, exist_ok=True)
            _atomic_write(path, backup_data.decode("utf-8"))
            row["status"] = "restored"
        results.append(row)
    return results


def verify_manifest(repo: Path, manifest: dict[str, Any]) -> list[dict[str, Any]]:
    """Verify on-disk post-apply and backup hashes from a manifest."""
    if manifest.get("schema") != "kb-tool.dedupe-apply/v1":
        raise ValueError("unsupported or missing manifest schema")
    repo = repo.resolve()
    results = []
    for item in manifest.get("files", []):
        path = _safe_plan_path(repo, item["path"])
        backup = _safe_plan_path(repo, item["backup"])
        current_hash = hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None
        backup_hash = hashlib.sha256(backup.read_bytes()).hexdigest() if backup.exists() else None
        results.append({
            "path": item["path"],
            "ok": current_hash == item.get("after_sha256") and backup_hash == item.get("before_sha256"),
            "current_sha256": current_hash,
            "expected_after_sha256": item.get("after_sha256"),
            "backup_sha256": backup_hash,
            "expected_before_sha256": item.get("before_sha256"),
        })
    return results


def _fragment_exists(text: str, fragment: str) -> bool:
    if fragment.startswith("^"):
        return bool(re.search(rf"\^{re.escape(fragment[1:])}\b", text))
    slug = re.sub(r"[^\w\s-]", "", fragment).strip().lower().replace(" ", "-")
    return any(re.sub(r"[^\w\s-]", "", heading).strip().lower().replace(" ", "-") == slug
               for heading in re.findall(r"^#+\s+(.+?)\s*$", text, re.MULTILINE))


def verify_fragments(repo: Path) -> list[dict[str, Any]]:
    """Check local Wikilink heading/block fragments have targets."""
    from .core import FileIndex
    from .core import strip_code

    if not (repo / ".git").exists():
        return []
    index = FileIndex(repo)
    rows = []
    for source in index.md_files:
        text = strip_code((repo / source).read_text(encoding="utf-8", errors="ignore"))
        for match in WIKILINK_RE.finditer(text):
            raw = match.group(2).split("|", 1)[0].strip()
            target, fragment = index.resolve_fragment(source, raw)
            status, candidates = index.resolve_wikilink_status(source, raw)
            if status == "ambiguous":
                rows.append({"file": source, "target": None, "fragment": fragment,
                             "status": status, "candidates": candidates, "ok": False})
                continue
            if not target or not fragment:
                continue
            target_text = (repo / target).read_text(encoding="utf-8", errors="ignore")
            ok = _fragment_exists(target_text, fragment)
            rows.append({"file": source, "target": target, "fragment": fragment, "ok": ok})
    return rows


def merge_drafts(repo: Path, plan: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Create merge drafts without modifying source or target notes."""
    drafts = []
    for item in plan:
        source = _safe_plan_path(repo, item["source"])
        target = _safe_plan_path(repo, item["target"])
        drafts.append({"source": item["source"], "target": item["target"],
                       "content": (target.read_text(encoding="utf-8") +
                                   "\n\n---\n\n## Merged from " + item["source"] + "\n\n" +
                                   source.read_text(encoding="utf-8"))})
    return drafts