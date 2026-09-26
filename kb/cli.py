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
    kb stats
"""

from __future__ import annotations

import sys
from pathlib import Path

import click

from .core import FileIndex, DEFAULT_KB


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
    from .migrations import convert_links as migrate_links, load_mapping

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
    from .migrations import load_coverage, tidy_wechat as migrate_wechat

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
