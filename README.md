# kb-tool

[![License: AGPL-3.0](https://img.shields.io/badge/License-AGPL--3.0-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11+-green.svg)](https://www.python.org/)

Unified knowledge base management tool for wikilink-based knowledge graphs.

## Features

- **Broken Link Scanner** — Detect and report broken wikilinks across your knowledge base
- **Orphan Analysis** — Find files with no incoming or outgoing links
- **Graph Analysis** — Identify hub nodes, isolated islands, and missing pages
- **Auto-Fix** — Automatically fix zero-link files and pipe character corruption
- **README Sync** — Keep file counts in README.md up to date

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
