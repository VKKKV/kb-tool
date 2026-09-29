# kb-tool

[![License: AGPL-3.0](https://img.shields.io/badge/License-AGPL--3.0-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11+-green.svg)](https://www.python.org/)

Unified knowledge base management tool for wikilink-based knowledge graphs.

## Features

- **Broken Link Scanner** — Detect and report broken wikilinks across your knowledge base
- **Orphan Analysis** — Find files with no incoming or outgoing links
- **Graph Analysis** — Identify hub nodes, isolated islands, and missing pages
- **Obsidian Graph Colors** — Generate a theme-aware Graph View CSS snippet
- **Graph Retrieval Primitives** — Export hop-labeled neighborhoods and expand external JSON search results
- **Structural Similarity** — Find notes with similar Wikilink neighborhoods without embeddings
- **Duplicate Candidates** — Report structurally similar note pairs without editing files
- **Auto-Fix** — Automatically fix zero-link files and pipe character corruption
- **README Sync** — Keep file counts in README.md up to date
- **Markdown Migrations** — Convert dated links and normalize WeChat archive metadata

## Installation

### Using uv (recommended)

```bash
cd ~/code/kb-tool
uv pip install -e .
```

### Using pip

```bash
cd ~/code/kb-tool
pip install -e .
```

### Development

```bash
cd ~/code/kb-tool
uv pip install -e ".[dev]"
```

## Quick Start

```bash
# Set your knowledge base root (optional, defaults to ~/code/knowledge)
export KB_ROOT=~/code/knowledge

# Quick stats
kb stats

# Scan for broken links
kb scan

# Analyze orphan files
kb orphan

# Full graph analysis
kb graph

# Generate an Obsidian Graph View color snippet
kb graph-colors
kb graph-colors --output .obsidian/snippets/kb-graph-colors.css
kb graph-colors --theme nord
kb graph-colors --theme catppuccin --output .obsidian/snippets/kb-graph-colors.css

# Generate read-only Obsidian Graph View group suggestions
kb graph-groups --format json
kb graph-groups --limit 20 --format jsonl
kb graph-groups --format text
kb graph-groups --theme nord --format text
kb graph-groups --min-count 2 --format json --output graph-groups.json

# Unix-style graph retrieval: independent of qmd or any other search engine
kb neighbors path/to/note.md --depth 1 --direction both --json
printf '[{"path":"path/to/note.md","score":0.9}]' \
  | kb expand --stdin --depth 1 --direction both
```

## Commands

### `kb stats` — Quick Statistics

Display a quick overview of your knowledge base.

```bash
kb stats
```

**Output:**
- Total MD files
- Total directories
- Total size
- Recent modifications (7 days)

### `kb scan` — Broken Link Scanner

Scan for broken wikilinks across your knowledge base.

```bash
kb scan                  # Print report to stdout
kb scan -o report.md     # Write report to file
kb scan --json           # JSON output for automation
```

**Detection:**
- Wikilinks pointing to non-existent files
- Invalid wikilink syntax
- Cross-reference integrity

### `kb orphan` — Orphan Analysis

Find files with no incoming or outgoing links.

```bash
kb orphan                # List all orphan files
kb orphan --by-dir       # Group by directory
kb orphan --json         # JSON output
```

**Categories:**
- `connected` — Has both incoming and outgoing links
- `only outgoing` — Only links to other files
- `only incoming` — Only linked from other files
- `zero both` — No links at all (true orphans)

### `kb graph` — Graph Analysis

Analyze the knowledge base link graph.

```bash
kb graph                 # Full analysis (all modes)
kb graph -m hubs         # Hub nodes (most referenced)
kb graph -m islands      # Isolated nodes (no connections)
kb graph -m wanted       # Missing pages (referenced but don't exist)
```

**Metrics:**
- **Hubs** — Files with the most incoming links (knowledge anchors)
- **Islands** — Files with no connections (potential orphans)
- **Wanted** — Pages referenced but not yet created

### `kb neighbors` — Wikilink Neighborhood

Return the anchor files and their link neighbors. This command does not perform
semantic search and has no dependency on qmd. Output is tab-separated by default
or JSON with `--json`, making it suitable for shell pipelines and other search
tools.

```bash
kb neighbors path/to/note.md --depth 1 --direction both
kb neighbors path/to/note.md --depth 2 --json
```

### `kb expand` — Expand External Search Results

Read a JSON array from stdin and add graph neighbors. The input contract is
deliberately tool-neutral: each item needs a `path` field and may carry a
`score`, `source`, or other fields. Existing scores are preserved; graph-added
items are marked with `source=graph`.

```bash
some-search-tool --json "question" \
  | kb expand --stdin --depth 1 --direction both
```

`kb-tool` does not invoke, import, or configure the upstream search tool.

Graph retrieval commands also accept `--format text|json|jsonl`. `text` is the
default; `jsonl` writes one record per line for streaming pipelines. `--json`
is retained as a compatibility shortcut for `--format json`.

### `kb context` and `kb similar`

`context` is a bounded, read-only Wikilink neighborhood query:

```bash
kb context path/to/note.md --depth 1 --limit 20 --json
```

`similar` uses Jaccard similarity over incoming and outgoing Wikilink neighbors.
It is structural similarity, not semantic similarity, and never invokes qmd or
an embedding provider:

```bash
kb similar path/to/note.md --top 10 --json
```

`dedupe scan` is a read-only candidate report. It uses the same structural
Jaccard signal, does not call qmd or an embedding provider, and never merges or
deletes notes:

```bash
kb dedupe scan --threshold 0.50 --limit 100 --format jsonl
```

Exact content and paragraph reports are also read-only:

```bash
kb dedupe exact --format json
kb dedupe exact --include-frontmatter --format jsonl
kb dedupe paragraphs --min-chars 40 --format json
```

`dedupe exact` compares normalized Markdown bodies and ignores frontmatter by
default. `dedupe paragraphs` reports identical paragraphs occurring in multiple
notes, with file paths, line numbers, text, and SHA-256 values. Fenced code,
headings, blockquotes, and short paragraphs are excluded from the paragraph
report; no content is changed automatically.

Review and planning are separate read-only steps. Edit the reviewed JSON to
set `action` to `redirect`, then generate an explicit plan:

```bash
kb dedupe review candidates.json --format json > reviewed.json
# manually set action=redirect only after checking both notes
kb dedupe plan reviewed.json --format json > redirect-plan.json
```

The plan does not modify files. A future apply command must require an explicit
write flag, preserve the source as a recoverable redirect/alias, and rewrite
inbound links only after showing the plan.

The current conservative apply skeleton only handles redirect stubs:

```bash
kb dedupe apply redirect-plan.json --format json       # dry-run, emits diff
kb dedupe apply redirect-plan.json --write --format json
```

To move the source into the vault-local recoverable trash instead of leaving a
redirect stub:

```bash
kb dedupe apply redirect-plan.json --write --source-after trash --format json
```

Permanent deletion is not supported.

Every explicit write produces `.kb-tool-backup/manifest.json`. It records the
before/after SHA-256 and backup path for each changed file. Rollback is also
preview-first and refuses to overwrite a post-apply edit:

The manifest also stores the migration statistics and a passed preflight
snapshot, so the apply is auditable rather than only reporting final writes.
If a later atomic write fails, already-committed files are restored from the
same backup batch before the error is returned.

```bash
kb dedupe rollback .kb-tool-backup/manifest.json --format json
kb dedupe rollback .kb-tool-backup/manifest.json --write --format json
kb dedupe verify-manifest .kb-tool-backup/manifest.json --format json
kb dedupe verify-fragments --format json
kb dedupe verify-redirects --format json
```

`verify-redirects` checks tracked redirect stubs created by dedupe apply. It
reports missing and ambiguous targets, self/cyclic redirects, and redirect
chains. The command is read-only and exits with status 1 if any redirect fails.

Merge is draft-only at this stage:

```bash
kb dedupe merge-draft redirect-plan.json --output .kb-tool-drafts
```

It creates reviewable Markdown drafts and never changes the source or target
note.

It never deletes the source note and does not merge body content. Frontmatter
merging, alias YAML mutation, and destructive source actions remain blocked until
those contracts are implemented.

The current implementation supports conservative inbound link migration for
Wikilinks and Markdown links, preserving aliases, embeds, heading/block
fragments, fenced code, and inline code. It also creates `.kb-tool-backup/`
files on explicit writes and provides plan verification:

```bash
kb dedupe verify redirect-plan.json --format json
```

### `kb fix-zero` — Fix Zero-Link Files

Automatically add associations for files with no links.

```bash
kb fix-zero              # Apply fixes
kb fix-zero --dry-run    # Preview changes without applying
```

### `kb fix-pipe` — Fix Pipe Corruption

Fix wikilinks corrupted by pipe characters.

```bash
kb fix-pipe              # Fix all files
kb fix-pipe file1.md file2.md  # Fix specific files
```

### `kb sync` — Sync README

Update file counts in README.md.

```bash
kb sync                  # Update counts
kb sync --dry-run        # Preview changes
```

### `kb convert-links` — Convert dated Markdown links

Convert matching dated Markdown links using an explicit tab-separated mapping.
Unmapped links are left unchanged and produce a non-zero exit status.

```bash
kb convert-links mapping.tsv index.md
kb convert-links --dry-run mapping.tsv index.md
```

### `kb tidy-wechat` — Normalize WeChat archive articles

Normalize the frontmatter and backlink of Markdown articles in one explicit
year directory. The coverage file is JSON and is keyed by paths such as
`articles/2026/article.md`.

```bash
kb tidy-wechat articles/2026 2026 coverage.json
kb tidy-wechat --dry-run articles/2026 2026 coverage.json
```

Both migration commands operate only on the paths supplied by the caller and
do not discover a checkout or access the network. They replace the historical
`ctf-tool/script/kb-tools` scripts.

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `KB_ROOT` | Knowledge base root directory | `~/code/knowledge` |

## Examples

### Daily Maintenance Workflow

```bash
# Morning check
kb stats
kb scan --json | jq '.broken_count'

# Weekly cleanup
kb orphan --by-dir
kb graph -m islands
kb fix-zero --dry-run
```

### CI/CD Integration

```yaml
# .github/workflows/kb-check.yml
name: Knowledge Base Check
on: [push, pull_request]
jobs:
  check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - run: pip install -e .
      - run: kb scan --json | jq '.broken_count == 0'
```

### Automation with Cron

```bash
# Daily knowledge base health check
0 2 * * * cd ~/code/knowledge && kb scan -o ~/reports/kb-scan-$(date +\%Y-\%m-\%d).md
```

## Architecture

```
kb-tool/
├── kb/
│   ├── __init__.py      # Package initialization
│   ├── cli.py           # Click CLI entry point
│   ├── core.py          # Core functionality
│   ├── scanner.py       # Broken link detection
│   ├── orphan.py        # Orphan file analysis
│   ├── graph.py         # Graph algorithms (NetworkX)
│   ├── sync.py          # README synchronization
│   ├── migrations.py    # Explicit-path Markdown migrations
│   └── fixer.py         # Auto-fix utilities
├── pyproject.toml       # Project configuration
├── LICENSE              # AGPL-3.0
└── README.md            # This file
```

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

This project is licensed under the GNU Affero General Public License v3.0 - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

- [NetworkX](https://networkx.org/) — Graph analysis library
- [Click](https://click.palletsprojects.com/) — CLI framework
- [uv](https://github.com/astral-sh/uv) — Fast Python package installer
