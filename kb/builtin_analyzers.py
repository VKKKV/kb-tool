"""Built-in read-only analyzers exposed through the public entry-point API."""

from __future__ import annotations

from .core import FileIndex


def link_stats(index: FileIndex) -> dict[str, int]:
    """Report tracked note and Wikilink edge counts."""
    outgoing = index.wikilink_targets()
    return {
        "markdown_files": len(index.md_files),
        "linked_notes": len(outgoing),
        "wikilink_edges": sum(len(targets) for targets in outgoing.values()),
    }
