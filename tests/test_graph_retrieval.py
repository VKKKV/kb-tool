from __future__ import annotations

import networkx as nx

from kb.graph import expand_results, neighbors


def test_neighbors_reports_hops_and_direction() -> None:
    graph = nx.DiGraph([("a.md", "b.md"), ("c.md", "a.md"), ("b.md", "d.md")])

    rows = neighbors(graph, ["a.md"], depth=1, direction="both")

    assert rows == [
        {"path": "a.md", "hop": 0, "relation": "anchor"},
        {"path": "b.md", "hop": 1, "relation": "outgoing"},
        {"path": "c.md", "hop": 1, "relation": "backlink"},
    ]


def test_expand_preserves_external_scores_and_adds_graph_nodes() -> None:
    graph = nx.DiGraph([("a.md", "b.md")])

    rows = expand_results(graph, [{"path": "a.md", "score": 0.9, "source": "search"}], depth=1)

    assert rows[0]["path"] == "a.md"
    assert rows[0]["anchor_score"] == 0.9
    assert rows[1] == {
        "path": "b.md",
        "hop": 1,
        "relation": "outgoing",
        "source": "graph",
        "anchor_score": None,
    }
