import networkx as nx
import pytest

from kb.dedupe import scan_structural


def test_scan_structural_is_sorted_and_excludes_self() -> None:
    graph = nx.DiGraph([("a", "hub"), ("b", "hub"), ("a", "x"), ("b", "x")])
    rows = scan_structural(graph, threshold=0.5)
    assert rows[0]["left"] == "a"
    assert rows[0]["right"] == "b"
    assert rows[0]["score"] == 1.0
    assert all(row["left"] != row["right"] for row in rows)
    assert all(row["semantic"] is False for row in rows)


def test_scan_structural_validates_threshold() -> None:
    with pytest.raises(ValueError):
        scan_structural(nx.DiGraph(), threshold=1.1)
