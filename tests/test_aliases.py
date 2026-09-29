import pytest

from kb.dedupe import add_alias


def test_add_alias_updates_frontmatter_without_duplicate() -> None:
    text = "---\ntitle: New\naliases:\n  - Existing\n---\nBody\n"
    updated = add_alias(text, "Old")
    assert "- Existing" in updated and "- Old" in updated
    assert add_alias(updated, "Old") == updated


def test_scalar_aliases_are_rejected() -> None:
    with pytest.raises(ValueError):
        add_alias("---\naliases: Existing\n---\nBody\n", "Old")
