import networkx as nx

from kb.graph import context, similar


def test_context_is_bounded_and_bidirectional() -> None:
    graph = nx.DiGraph([("a.md", "b.md"), ("c.md", "a.md")])

    assert context(graph, ["a.md"], depth=1, limit=2) == [
        {"path": "a.md", "hop": 0, "relation": "anchor"},
        {"path": "b.md", "hop": 1, "relation": "outgoing"},
    ]


def test_similar_uses_structural_jaccard_and_stable_tie_breaking() -> None:
    graph = nx.DiGraph([
        ("a.md", "x.md"),
        ("a.md", "y.md"),
        ("b.md", "x.md"),
        ("b.md", "y.md"),
        ("c.md", "z.md"),
    ])

    rows = similar(graph, "a.md", top_n=2)

    assert rows[0]["path"] == "b.md"
    assert rows[0]["score"] == 1.0
    assert rows[0]["method"] == "jaccard"
    assert rows[0]["semantic"] is False
