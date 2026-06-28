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

### Planned

- Test suite with pytest
- Type checking with mypy
- Linting with ruff
- CI/CD with GitHub Actions
- Interactive mode with rich
- Export to various formats (JSON, CSV, Markdown)
- Plugin system for custom analyzers
