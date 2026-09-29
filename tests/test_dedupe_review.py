import json

import networkx as nx

from kb.dedupe import make_redirect_plan, review_candidates


def test_review_and_plan_are_non_writing(tmp_path) -> None:
    (tmp_path / "a.md").write_text("a", encoding="utf-8")
    (tmp_path / "b.md").write_text("b", encoding="utf-8")
    graph = nx.DiGraph([("a.md", "hub.md"), ("b.md", "hub.md")])
    reviewed = review_candidates(tmp_path, graph, [{"left": "a.md", "right": "b.md", "score": 1.0}])
    assert reviewed[0]["action"] == "review"
    reviewed[0]["action"] = "redirect"
    plan = make_redirect_plan(reviewed)
    assert plan[0]["operation"] == "redirect"
    assert plan[0]["source"] == "a.md"
    assert plan[0]["target"] == "b.md"
    assert plan[0]["source_sha256"]
    assert plan[0]["target_sha256"]
    assert (tmp_path / "a.md").read_text(encoding="utf-8") == "a"
