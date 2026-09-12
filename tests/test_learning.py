import pytest
from pydantic import ValidationError
from interview_forge.interview.engine import advance
from interview_forge.knowledge.graph import KnowledgeBatch, merge_graph, tree_view
from interview_forge.learning.planner import build_learning
from interview_forge.schemas.models import KnowledgeGraph, KnowledgeEdge


def test_graph_deduplicates_shared_concepts_and_keeps_provenance(session):
    advance(session)
    advance(session)
    graph = session.knowledge_graph
    assert len({n.title for n in graph.nodes}) == len(graph.nodes)
    shared = next(n for n in graph.nodes if "并发竞态" in n.title)
    assert shared.triggered_questions == ["q1", "q2"]
    assert shared.project_anchors
    graph2, new = merge_graph(graph, KnowledgeBatch(nodes=graph.nodes, edges=graph.edges))
    assert not new
    assert len(graph2.nodes) == len(graph.nodes)
    assert shared.title in tree_view(graph)


def test_graph_rejects_dangling_edges_and_tree_handles_cycle(session):
    advance(session)
    nodes = session.knowledge_graph.nodes
    with pytest.raises(ValidationError):
        KnowledgeGraph(nodes=nodes, edges=[KnowledgeEdge(source=nodes[0].id, target="missing", relation_type="requires", provenance="q1", distance=1, confidence=1)])
    graph = KnowledgeGraph(nodes=nodes, edges=[
        KnowledgeEdge(source=nodes[0].id, target=nodes[1].id, relation_type="requires", provenance="q1", distance=1, confidence=1),
        KnowledgeEdge(source=nodes[1].id, target=nodes[0].id, relation_type="explains", provenance="q1", distance=1, confidence=1)])
    assert len(tree_view(graph)) < 3000


def test_tasks_are_gap_bound_and_learning_is_bounded(session):
    advance(session)
    assert session.study_plan
    for task in session.study_plan:
        assert task.evidence_from_interview == ["t1"]
        assert task.gap_kind in {"material_gap", "answer_gap"}
        assert task.exercises[0].evidence_produced
    session.knowledge_graph.nodes[0].priority = "P3"
    cards, tasks = build_learning(session)
    assert all(c.node_id != session.knowledge_graph.nodes[0].id for c in cards)
    session.knowledge_graph.nodes[0].priority = "P2"
    session.knowledge_graph.nodes[0].interview_distance = 2
    assert all(c.node_id != session.knowledge_graph.nodes[0].id for c in build_learning(session)[0])
    session.config.deep_dive = True
    assert any(c.node_id == session.knowledge_graph.nodes[0].id for c in build_learning(session)[0])
