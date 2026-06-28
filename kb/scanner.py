"""Broken-link scanner with documentation-mirror noise filtering.

Merges: kb-broken-link-scan.py
"""

from __future__ import annotations

import collections
import json
from pathlib import Path

from .core import FileIndex, MD_LINK_RE, WIKI_RE, strip_code


def scan_broken_links(
    index: FileIndex,
    exclude: tuple[str, ...] | None = None,
    report_title: str = "KB 断链报告",
) -> dict:
    """Scan for broken wikilinks and markdown links.

    Returns dict with 'summary' (stats) and 'report' (markdown text).
    """
    scan_files = index.scan_files(exclude) if exclude is None else [
        p for p in index.md_files if not any(p.startswith(ex) for ex in exclude)
    ]

    broken: dict[str, list[tuple[str, str]]] = collections.defaultdict(list)
    token_count = 0
    external_count = 0
    placeholder_count = 0
    site_path_count = 0
    html_doc_count = 0

    for rel in scan_files:
        text = strip_code((index.repo / rel).read_text(encoding="utf-8", errors="ignore"))

        # markdown links
        for m in MD_LINK_RE.finditer(text):
            raw = m.group(2)
            token_count += 1
            cands = index.resolve_candidates(Path(rel), raw, "markdown")
            tag = cands[0] if cands else ""
            if tag == "__external__":
                external_count += 1
            elif tag == "__placeholder__":
                placeholder_count += 1
            elif tag == "__site_path__":
                site_path_count += 1
            elif tag == "__html_doc__":
                html_doc_count += 1
            elif not index.target_exists(cands):
                broken[rel].append(("markdown", raw.strip()))

        # wikilinks
        for m in WIKI_RE.finditer(text):
            raw = m.group(1).split("|", 1)[0].strip().lstrip("!")
            token_count += 1
            cands = index.resolve_candidates(Path(rel), raw, "wikilink")
            tag = cands[0] if cands else ""
            if tag == "__external__":
                external_count += 1
            elif tag == "__placeholder__":
                placeholder_count += 1
            elif not index.target_exists(cands):
                broken[rel].append(("wikilink", raw))

    # ── stats ──
    items = sorted(broken.items())
    top = collections.Counter()
    for path, links in items:
        top[path.split("/", 1)[0] if "/" in path else path] += len(links)

    subtop = collections.Counter()
    for path, links in items:
        if path.startswith("30-reference/"):
            subtop["/".join(path.split("/")[:2])] += len(links)

    priority = [
        (p, lk) for p, lk in items
        if p == "index.md" or p == "30-reference/README.md"
        or p.startswith(("20-areas/", "40-notes/"))
    ]

    total_broken = sum(len(lk) for lk in broken.values())

    summary = {
        "scan_files": len(scan_files),
        "tokens": token_count,
        "broken_total": total_broken,
        "broken_files": len(broken),
        "external_ignored": external_count,
        "placeholder_ignored": placeholder_count,
        "html_doc_ignored": html_doc_count,
        "site_path_ignored": site_path_count,
        "top": top.most_common(10),
        "subtop_30_reference": subtop.most_common(10),
        "priority_files": len(priority),
    }

    # ── markdown report ──
    lines = [
        f"# {report_title}",
        "",
        "本报告由 kb scan 生成。扫描 Git tracked Markdown 文件。",
        f"跳过: diary/archive/bookmarks-archive。",
        "",
        "## 总览",
        "",
        f"- 扫描文件: {len(scan_files)}",
        f"- 链接 token: {token_count}",
        f"- 断链: {total_broken} ({len(broken)} 文件)",
        f"- 忽略: external={external_count} placeholder={placeholder_count} "
        f"site_path={site_path_count} html_doc={html_doc_count}",
        "",
        "## 按目录统计",
        "",
    ]
    for key, count in top.most_common():
        lines.append(f"- {key}: {count}")

    lines.extend(["", "## 30-reference 子目录", ""])
    for key, count in subtop.most_common():
        lines.append(f"- {key}: {count}")

    lines.extend(["", "## 优先修复", ""])
    if not priority:
        lines.append("- 当前无高优先断链。")
    else:
        for path, links in priority:
            lines.append(f"### `{path}`")
            for kind, target in links[:80]:
                lines.append(f"- [{kind}] `{target}`")
            if len(links) > 80:
                lines.append(f"- ... 另有 {len(links) - 80} 条")
            lines.append("")

    lines.extend(["## 全量明细", ""])
    for path, links in items:
        lines.append(f"### `{path}`")
        for kind, target in links[:120]:
            lines.append(f"- [{kind}] `{target}`")
        if len(links) > 120:
            lines.append(f"- ... 另有 {len(links) - 120} 条")
        lines.append("")

    return {"summary": summary, "report": "\n".join(lines).rstrip() + "\n"}


def cmd_scan(index: FileIndex, output: str | None, json_out: bool, exclude: list[str] | None):
    """CLI handler for 'kb scan'."""
    exc = tuple(exclude) if exclude else None
    result = scan_broken_links(index, exclude=exc)

    if json_out:
        print(json.dumps(result["summary"], ensure_ascii=False, indent=2))
    else:
        s = result["summary"]
        print(f"扫描: {s['scan_files']} 文件, {s['tokens']} tokens")
        print(f"断链: {s['broken_total']} ({s['broken_files']} 文件)")
        print(f"忽略: ext={s['external_ignored']} ph={s['placeholder_ignored']} "
              f"site={s['site_path_ignored']} html={s['html_doc_ignored']}")

    if output:
        out = Path(output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(result["report"], encoding="utf-8")
        print(f"报告: {out}")
