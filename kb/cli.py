"""Unified CLI for knowledge base management.

Usage:
    kb scan [--output report.md] [--json] [--exclude ...]
    kb orphan [--limit 20] [--by-dir]
    kb fix-zero [--dry-run] [--limit 50]
    kb fix-pipe [file ...]
    kb sync [--dry-run] [--index-path ...]
    kb convert-links [--dry-run] MAPPING INDEX
    kb tidy-wechat [--dry-run] ARTICLES YEAR COVERAGE
    kb graph [--mode islands|hubs|wanted|communities|all] [--top 20] [--min-links 0] [--edges]
    kb neighbors PATH... [--depth 1] [--direction both] [--json]
    kb expand [--stdin] [--depth 1] [--direction both] [--limit 50]
    kb context PATH [--depth 1] [--limit 50] [--json]
    kb similar PATH [--top 10] [--json]
    kb dedupe scan [--threshold 0.25] [--limit 100] [--format text|json|jsonl]
    kb dedupe exact [--include-frontmatter] [--limit 100] [--format json|jsonl]
    kb dedupe paragraphs [--min-chars 40] [--format json|jsonl]
    kb stats
    kb graph-colors [--output PATH]
    kb graph-groups [--limit 50] [--format json|jsonl]
"""

from __future__ import annotations

import sys
from pathlib import Path

import click

from .core import DEFAULT_KB, FileIndex


def _emit(rows: list[dict], output_format: str, text_lines: list[str]) -> None:
    """Emit records for humans or Unix pipelines."""
    import json
    if output_format == "text":
        click.echo("\n".join(text_lines))
    elif output_format == "json":
        click.echo(json.dumps(rows, ensure_ascii=False, indent=2))
    else:
        for row in rows:
            click.echo(json.dumps(row, ensure_ascii=False, separators=(",", ":")))


def _index(kb: str | None) -> FileIndex:
    repo = Path(kb) if kb else DEFAULT_KB
    if not (repo / ".git").exists():
        click.echo(f"错误: {repo} 不是 git 仓库", err=True)
        sys.exit(1)
    return FileIndex(repo)


@click.group()
@click.option("--kb", envvar="KB_ROOT", default=None, help="知识库根目录")
@click.pass_context
def cli(ctx: click.Context, kb: str | None):
    """kb — 知识库统一管理工具"""
    ctx.ensure_object(dict)
    ctx.obj["kb"] = kb


@cli.command()
@click.option("-o", "--output", default=None, help="输出报告路径")
@click.option("--json", "json_out", is_flag=True, help="JSON 输出")
@click.option("-e", "--exclude", multiple=True, help="排除路径前缀")
@click.pass_context
def scan(ctx: click.Context, output: str | None, json_out: bool, exclude: tuple[str, ...]):
    """扫描断链"""
    from .scanner import cmd_scan
    idx = _index(ctx.obj["kb"])
    cmd_scan(idx, output, json_out, list(exclude) if exclude else None)


@cli.command()
@click.option("-n", "--limit", default=20, help="显示数量")
@click.option("--by-dir", is_flag=True, help="按目录分组")
@click.pass_context
def orphan(ctx: click.Context, limit: int, by_dir: bool):
    """分析孤立文件"""
    from .orphan import cmd_orphan
    idx = _index(ctx.obj["kb"])
    cmd_orphan(idx, limit, by_dir)


@cli.command("fix-zero")
@click.option("--dry-run", is_flag=True, help="预览不修改")
@click.option("-n", "--limit", default=50, help="显示数量")
@click.pass_context
def fix_zero(ctx: click.Context, dry_run: bool, limit: int):
    """为零链接文件添加关联"""
    from .fixer import cmd_fix_zero
    idx = _index(ctx.obj["kb"])
    cmd_fix_zero(idx, dry_run, limit)


@cli.command("fix-pipe")
@click.argument("files", nargs=-1)
@click.pass_context
def fix_pipe(ctx: click.Context, files: tuple[str, ...]):
    """修复管道符污染"""
    from .fixer import cmd_fix_pipe
    idx = _index(ctx.obj["kb"])
    cmd_fix_pipe(idx, list(files) if files else None)


@cli.command()
@click.option("--dry-run", is_flag=True, help="预览不修改")
@click.option("--index-path", default=None, help="index.md 路径")
@click.pass_context
def sync(ctx: click.Context, dry_run: bool, index_path: str | None):
    """同步 README/index 文件计数"""
    from .sync import cmd_sync
    idx = _index(ctx.obj["kb"])
    cmd_sync(idx, dry_run, index_path)


@cli.command("convert-links")
@click.argument("mapping", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.argument("index", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--dry-run", is_flag=True, help="预览不修改")
def convert_links(mapping: Path, index: Path, dry_run: bool):
    """将日期 Markdown 链接按映射转换为 wikilinks。"""
    from .migrations import convert_links as migrate_links
    from .migrations import load_mapping

    converted, missing = migrate_links(index, load_mapping(mapping), dry_run=dry_run)
    prefix = "[DRY RUN] " if dry_run else ""
    click.echo(f"{prefix}converted={converted} missing={missing}")
    if missing:
        raise click.exceptions.Exit(1)


@cli.command("tidy-wechat")
@click.argument("articles", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.argument("year")
@click.argument("coverage", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--dry-run", is_flag=True, help="预览不修改")
def tidy_wechat(articles: Path, year: str, coverage: Path, dry_run: bool):
    """整理指定年份的 WeChat Markdown 文章。"""
    from .migrations import load_coverage
    from .migrations import tidy_wechat as migrate_wechat

    processed, changed, errors = migrate_wechat(
        articles, year, load_coverage(coverage), dry_run=dry_run
    )
    prefix = "[DRY RUN] " if dry_run else ""
    for path, error in errors:
        click.echo(f"{path}: {error}")
    click.echo(f"{prefix}processed={processed} changed={changed} errors={len(errors)}")
    if errors:
        raise click.exceptions.Exit(1)


@cli.command()
@click.option("-m", "--mode", default="all",
              type=click.Choice(["islands", "hubs", "wanted", "communities", "all"]),
              help="查询模式")
@click.option("-n", "--top", "top_n", default=20, help="显示数量")
@click.option("--min-links", default=0, help="孤岛阈值 (degree)")
@click.option("--edges", is_flag=True, help="显示边列表")
@click.pass_context
def graph(ctx: click.Context, mode: str, top_n: int, min_links: int, edges: bool):
    """知识图谱分析"""
    from .graph import cmd_graph
    idx = _index(ctx.obj["kb"])
    cmd_graph(idx, mode, top_n, min_links, edges)


@cli.command()
@click.argument("paths", nargs=-1, required=True)
@click.option("--depth", default=1, type=click.IntRange(min=0))
@click.option("--direction", type=click.Choice(["in", "out", "both"]), default="both")
@click.option("--json", "json_out", is_flag=True)
@click.option("--format", "output_format", type=click.Choice(["text", "json", "jsonl"]), default="text")
@click.option("--limit", default=None, type=int)
@click.pass_context
def neighbors(ctx: click.Context, paths: tuple[str, ...], depth: int, direction: str,
              json_out: bool, output_format: str, limit: int | None):
    """列出 note 的 Wikilink 邻居；不依赖任何检索引擎。"""
    import json

    from .graph import build_graph
    from .graph import neighbors as graph_neighbors
    rows = graph_neighbors(build_graph(_index(ctx.obj["kb"])), list(paths), depth, direction, limit)
    _emit(rows, "json" if json_out else output_format,
          [f"{r['hop']}\t{r['relation']}\t{r['path']}" for r in rows])


@cli.command()
@click.option("--stdin", "from_stdin", is_flag=True, help="从 stdin 读取 JSON 数组")
@click.option("--depth", default=1, type=click.IntRange(min=0))
@click.option("--direction", type=click.Choice(["in", "out", "both"]), default="both")
@click.option("--limit", default=50, type=click.IntRange(min=1))
@click.pass_context
def expand(ctx: click.Context, from_stdin: bool, depth: int, direction: str, limit: int):
    """扩展外部检索器输出的 JSON 结果；输入格式为 [{\"path\": ...}]。"""
    import json

    from .graph import build_graph, expand_results
    if not from_stdin:
        raise click.UsageError("目前需要 --stdin；输入必须是 JSON 数组")
    results = json.load(sys.stdin)
    if not isinstance(results, list):
        raise click.UsageError("stdin 必须是 JSON 数组")
    rows = expand_results(build_graph(_index(ctx.obj["kb"])), results, depth, direction, limit)
    click.echo(json.dumps(rows, ensure_ascii=False, indent=2))


@cli.command()
@click.argument("path")
@click.option("--depth", default=1, type=click.IntRange(min=0))
@click.option("--limit", default=50, type=click.IntRange(min=1))
@click.option("--json", "json_out", is_flag=True)
@click.option("--format", "output_format", type=click.Choice(["text", "json", "jsonl"]), default="text")
@click.pass_context
def context(ctx: click.Context, path: str, depth: int, limit: int, json_out: bool,
            output_format: str):
    """输出 note 周围的 Wikilink context（不包含正文）。"""
    import json

    from .graph import build_graph
    from .graph import context as graph_context
    rows = graph_context(build_graph(_index(ctx.obj["kb"])), [path], depth, limit)
    _emit(rows, "json" if json_out else output_format,
          [f"{r['hop']}\t{r['relation']}\t{r['path']}" for r in rows])


@cli.command()
@click.argument("path")
@click.option("--top", default=10, type=click.IntRange(min=1))
@click.option("--json", "json_out", is_flag=True)
@click.option("--format", "output_format", type=click.Choice(["text", "json", "jsonl"]), default="text")
@click.pass_context
def similar(ctx: click.Context, path: str, top: int, json_out: bool, output_format: str):
    """按 Wikilink 邻居 Jaccard 查找结构相似 note（不是语义相似）。"""
    import json

    from .graph import build_graph
    from .graph import similar as graph_similar
    rows = graph_similar(build_graph(_index(ctx.obj["kb"])), path, top)
    _emit(rows, "json" if json_out else output_format,
          [f"{r['score']:.6f}\t{r['path']}\t{r['method']}" for r in rows])


@cli.group()
def dedupe():
    """Generate read-only duplicate candidates."""


@dedupe.command("scan")
@click.option("--threshold", default=0.25, type=click.FloatRange(0, 1))
@click.option("--limit", default=100, type=click.IntRange(min=1))
@click.option("--format", "output_format", type=click.Choice(["text", "json", "jsonl"]), default="text")
@click.pass_context
def dedupe_scan(ctx: click.Context, threshold: float, limit: int, output_format: str):
    """Find structurally similar note pairs without editing files."""
    from .dedupe import scan_structural
    from .graph import build_graph
    rows = scan_structural(build_graph(_index(ctx.obj["kb"])), threshold, limit)
    _emit(rows, output_format,
          [f"{r['score']:.6f}\t{r['left']}\t{r['right']}\t{r['method']}" for r in rows])


@dedupe.command("exact")
@click.option("--include-frontmatter", is_flag=True,
              help="Treat frontmatter differences as content differences")
@click.option("--limit", default=100, type=click.IntRange(min=1))
@click.option("--format", "output_format", type=click.Choice(["json", "jsonl"]), default="json")
@click.pass_context
def dedupe_exact(ctx: click.Context, include_frontmatter: bool, limit: int, output_format: str):
    """Find notes with identical normalized content without editing files."""
    from .dedupe import scan_exact
    rows = scan_exact(_index(ctx.obj["kb"]).repo, include_frontmatter, limit)
    _emit(rows, output_format, [])


@dedupe.command("paragraphs")
@click.option("--min-chars", default=40, type=click.IntRange(min=1))
@click.option("--format", "output_format", type=click.Choice(["json", "jsonl"]), default="json")
@click.pass_context
def dedupe_paragraphs(ctx: click.Context, min_chars: int, output_format: str):
    """Find exact repeated paragraphs across different notes."""
    from .dedupe import scan_paragraphs
    rows = scan_paragraphs(_index(ctx.obj["kb"]).repo, min_chars)
    _emit(rows, output_format, [])


def _read_records(path: Path) -> list[dict]:
    import json
    text = path.read_text(encoding="utf-8")
    value = json.loads(text) if text.lstrip().startswith("[") else [json.loads(line) for line in text.splitlines() if line.strip()]
    if not isinstance(value, list) or not all(isinstance(row, dict) for row in value):
        raise click.ClickException("候选文件必须是 JSON 数组或 JSONL 对象")
    return value


@dedupe.command("review")
@click.argument("input_path", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--format", "output_format", type=click.Choice(["json", "jsonl"]), default="json")
@click.pass_context
def dedupe_review(ctx: click.Context, input_path: Path, output_format: str):
    """补充候选的文件大小、引用计数和共享邻居，供人工审核。"""
    from .dedupe import review_candidates
    from .graph import build_graph
    index = _index(ctx.obj["kb"])
    try:
        rows = review_candidates(index.repo, build_graph(index), _read_records(input_path))
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc
    _emit(rows, output_format, [])


@dedupe.command("plan")
@click.argument("input_path", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--format", "output_format", type=click.Choice(["json", "jsonl"]), default="json")
def dedupe_plan(input_path: Path, output_format: str):
    """从人工标记 action=redirect 的审核结果生成非写入计划。"""
    from .dedupe import make_redirect_plan
    rows = make_redirect_plan(_read_records(input_path))
    _emit(rows, output_format, [])


@dedupe.command("apply")
@click.argument("plan_path", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--write", is_flag=True, help="Actually write redirect stubs; default is dry-run")
@click.option("--source-after", type=click.Choice(["keep", "redirect", "trash"]), default="redirect")
@click.option("--require-clean-git", is_flag=True, help="Refuse writes when the vault worktree is dirty")
@click.option("--format", "output_format", type=click.Choice(["json", "jsonl"]), default="json")
@click.pass_context
def dedupe_apply(ctx: click.Context, plan_path: Path, write: bool, source_after: str,
                 require_clean_git: bool, output_format: str):
    """Preview or explicitly write conservative redirect plans."""
    from .dedupe import apply_plan
    index = _index(ctx.obj["kb"])
    plan = _read_records(plan_path)
    try:
        rows = apply_plan(index.repo, plan, write=write, source_after=source_after,
                          require_clean_git=require_clean_git)
    except Exception as exc:
        from .dedupe import MigrationPreflightError
        if isinstance(exc, MigrationPreflightError):
            _emit([{"error": "migration_preflight", "issues": exc.issues}], output_format, [])
            raise click.exceptions.Exit(1)
        if isinstance(exc, ValueError):
            raise click.ClickException(str(exc)) from exc
        raise
    _emit(rows, output_format, [])


@dedupe.command("verify")
@click.argument("plan_path", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--format", "output_format", type=click.Choice(["json", "jsonl"]), default="json")
@click.pass_context
def dedupe_verify(ctx: click.Context, plan_path: Path, output_format: str):
    """Verify plan files and hashes without writing."""
    from .dedupe import verify_plan
    index = _index(ctx.obj["kb"])
    rows = verify_plan(index.repo, _read_records(plan_path))
    _emit(rows, output_format, [])
    if any(not row["ok"] for row in rows):
        raise click.exceptions.Exit(1)


@dedupe.command("rollback")
@click.argument("manifest_path", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--write", is_flag=True)
@click.option("--format", "output_format", type=click.Choice(["json", "jsonl"]), default="json")
@click.pass_context
def dedupe_rollback(ctx: click.Context, manifest_path: Path, write: bool, output_format: str):
    """Preview or restore a manifest, refusing changed post-apply files."""
    import json
    from .dedupe import rollback_manifest
    index = _index(ctx.obj["kb"])
    rows = rollback_manifest(index.repo, json.loads(manifest_path.read_text(encoding="utf-8")), write)
    _emit(rows, output_format, [])
    if any(not row["ok"] for row in rows):
        raise click.exceptions.Exit(1)


@dedupe.command("verify-manifest")
@click.argument("manifest_path", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--format", "output_format", type=click.Choice(["json", "jsonl"]), default="json")
@click.pass_context
def dedupe_verify_manifest(ctx: click.Context, manifest_path: Path, output_format: str):
    """Verify the actual post-apply and backup bytes recorded by a manifest."""
    import json
    from .dedupe import verify_manifest
    index = _index(ctx.obj["kb"])
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    rows = verify_manifest(index.repo, manifest)
    _emit(rows, output_format, [])
    if any(not row["ok"] for row in rows):
        raise click.exceptions.Exit(1)


@dedupe.command("verify-fragments")
@click.option("--format", "output_format", type=click.Choice(["json", "jsonl"]), default="json")
@click.pass_context
def dedupe_verify_fragments(ctx: click.Context, output_format: str):
    """Check local Wikilink heading/block fragments after migration."""
    from .dedupe import verify_fragments
    index = _index(ctx.obj["kb"])
    rows = verify_fragments(index.repo)
    _emit(rows, output_format, [])
    if any(not row["ok"] for row in rows):
        raise click.exceptions.Exit(1)


@dedupe.command("verify-redirects")
@click.option("--format", "output_format", type=click.Choice(["json", "jsonl"]), default="json")
@click.pass_context
def dedupe_verify_redirects(ctx: click.Context, output_format: str):
    """Check redirect stubs for resolvable targets and chains."""
    from .dedupe import verify_redirects
    rows = verify_redirects(_index(ctx.obj["kb"]).repo)
    _emit(rows, output_format, [])
    if any(not row["ok"] for row in rows):
        raise click.exceptions.Exit(1)


@cli.command("graph-colors")
@click.option("--theme", type=click.Choice(["default", "nord", "catppuccin"]), default="default")
@click.option("--output", type=click.Path(dir_okay=False, path_type=Path), default=None)
def graph_colors(theme: str, output: Path | None) -> None:
    """Generate an Obsidian Graph View CSS color snippet."""
    from .graph_colors import THEMES, render_css, write_css
    colors = THEMES[theme]
    if output is None:
        click.echo(render_css(colors), nl=False)
    else:
        write_css(output, colors)
        click.echo(f"wrote {output}")


@cli.command("graph-groups")
@click.option("--limit", default=50, type=click.IntRange(min=1))
@click.option("--format", "output_format", type=click.Choice(["text", "json", "jsonl"]), default="json")
@click.pass_context
def graph_groups(ctx: click.Context, limit: int, output_format: str) -> None:
    """Suggest read-only Obsidian Graph View search groups."""
    from .graph_groups import suggest_groups
    rows = suggest_groups(_index(ctx.obj["kb"]), limit)
    text_lines = [f"{r['name']}\n  Query: {r['obsidian_query']}\n  Color: {r['color']}\n  Count: {r['count']}" for r in rows]
    _emit(rows, output_format, text_lines)


@dedupe.command("merge-draft")
@click.argument("plan_path", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--output", required=True, type=click.Path(file_okay=False, path_type=Path))
@click.pass_context
def dedupe_merge_draft(ctx: click.Context, plan_path: Path, output: Path):
    """Write merge drafts only; source and target notes are untouched."""
    from .dedupe import merge_drafts
    index = _index(ctx.obj["kb"])
    drafts = merge_drafts(index.repo, _read_records(plan_path))
    output.mkdir(parents=True, exist_ok=True)
    for draft in drafts:
        path = output / (Path(draft["target"]).stem + ".merge-draft.md")
        path.write_text(draft["content"], encoding="utf-8")
    click.echo(f"drafts={len(drafts)} output={output}")


@cli.command()
@click.pass_context
def stats(ctx: click.Context):
    """快速统计"""
    idx = _index(ctx.obj["kb"])
    print(f"仓库: {idx.repo}")
    print(f"Git tracked: {len(idx.all_files)} 文件")
    print(f"Markdown: {len(idx.md_files)} 文件")
    print(f"目录: {len(idx.dirs)}")
    # top dirs
    from collections import Counter
    top_dirs = Counter()
    for f in idx.md_files:
        top = f.split("/", 1)[0] if "/" in f else "."
        top_dirs[top] += 1
    print("\n按顶层目录:")
    for d, c in top_dirs.most_common():
        print(f"  {d}: {c}")


def main():
    cli()


if __name__ == "__main__":
    main()
