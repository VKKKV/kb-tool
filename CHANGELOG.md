# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-06-28

### Added

- Initial release
- `kb stats` — Quick knowledge base statistics
- `kb scan` — Broken wikilink scanner with JSON output
- `kb orphan` — Orphan file analysis (incoming/outgoing links)
- `kb graph` — Graph analysis (hubs, islands, wanted pages)
- `kb fix-zero` — Auto-fix zero-link files
- `kb fix-pipe` — Fix pipe character corruption in wikilinks
- `kb sync` — Synchronize README.md file counts
- NetworkX-based graph algorithms
- Click-based CLI framework
- Comprehensive documentation

### Changed

- N/A

### Deprecated

- N/A

### Removed

- N/A

### Fixed

- N/A

### Security

- N/A

## [Unreleased]

### Added

- `.kb-tool.yaml` configuration for `graph-colors` and `graph-groups`, with CLI overrides
- CSV and Markdown exports for Obsidian graph-group suggestions
- GitHub Actions test matrix for Python 3.11–3.13
- Development YAML typing stubs and scoped mypy checks in CI

### Planned

- Interactive mode with rich
- Plugin system for custom analyzers
