import hashlib
from interview_forge.knowledge.compress import canonical_title
from interview_forge.schemas.models import FollowupQA
from interview_forge.curricula import TOPICS, topic_for
from interview_forge.llm import LLMClient, prompt
from interview_forge.schemas.models import KnowledgeEdge, KnowledgeGraph, KnowledgeNode, MasteryState, Model


def node_id(title: str) -> str:
    return "k" + hashlib.sha256(canonical_title(title).casefold().encode()).hexdigest()[:12]


class KnowledgeBatch(Model):
    nodes: list[KnowledgeNode]
    edges: list[KnowledgeEdge]


def extract_knowledge(claim, turn, client: LLMClient | None = None) -> KnowledgeBatch:
    if client:
        result = client.structured_generate(prompt("knowledge_extraction"), {
            "claim": claim.model_dump(), "turn": turn.model_dump()}, KnowledgeBatch)
        if len(result.nodes) > 4:
            raise ValueError("Knowledge expansion exceeded four nodes per turn")
        if not result.nodes:
            return result
        from interview_forge.quality import check_general_knowledge
        for n in result.nodes:
            for text in (n.interview_one_liner, n.core_explanation, n.key_mechanism, n.decision_logic):
                check_general_knowledge(text)
            n.title = canonical_title(n.title)
            if not n.followup_qa:
                raise ValueError("Knowledge nodes require answered follow-up questions")
            n.source_claims = [claim.id]
            n.triggered_questions = [turn.question.id]
            n.project_anchors = [claim.project + ": " + claim.source_quote]
            n.evidence = list(turn.answer.evidence_ids)
            n.mastery = MasteryState()
        KnowledgeGraph(nodes=result.nodes, edges=result.edges)
        return result
    topic = TOPICS[topic_for(claim.topic)]
    subtopic = turn.question.subtopic
    primary = canonical_title(topic.title)
    if subtopic == "evaluation":
        primary, explanation = "受控基线与性能测量", topic.validation
    elif subtopic == "decision" or subtopic == "counterfactual":
        primary, explanation = "复杂度与一致性约束" if topic_for(claim.topic) != "rag" else "检索质量与延迟预算", topic.decision
    elif subtopic in {"failure", "debugging"}:
        primary, explanation = "幂等性与至少一次执行" if topic_for(claim.topic) != "rag" else "两阶段检索与候选集上限", topic.failure
    elif subtopic == "scaling":
        primary, explanation = "资源饱和与尾延迟", "固定资源逐步增加负载，寻找排队和饱和拐点；分别验证容量与正确性，保留资源配置和负载模型。"
    elif subtopic == "fundamentals":
        primary, explanation = canonical_title(topic.prerequisite), topic.prerequisite_explanation
    else:
        explanation = topic.mechanism
    title = primary
    nodes = []
    for index, (name, body) in enumerate([(title, explanation), (canonical_title(topic.prerequisite), topic.prerequisite_explanation)]):
        if any(n.title == name for n in nodes):
            continue
        nodes.append(KnowledgeNode(id=node_id(name), title=name, category=topic_for(claim.topic),
            priority="P0" if index == 0 else "P1", interview_distance=index,
            source_claims=[claim.id], triggered_questions=[turn.question.id],
            project_anchors=[claim.project + ": " + claim.source_quote],
            interview_one_liner=body.split("。")[0] + "。", core_explanation=body,
            key_mechanism=topic.mechanism if index == 0 else topic.prerequisite_explanation,
            decision_logic=topic.decision, failure_modes=[topic.failure], alternatives=topic.alternative.split("；"),
            common_traps=["把局部技术保证外推成跨系统保证", "把源码存在当作性能提升或个人掌握的证明"],
            likely_followups=turn.answer.likely_followups[:2],
            practice_questions=[turn.question.text, "请构造一个违反上述假设的边界案例，并解释修复条件。"],
            retest_questions=[f"围绕{name}，如何用一个具体反例说明机制的边界，并设计验证方法？",
                              f"如果{name}的关键前提不再成立，你会如何比较替代方案并验证选择？"],
            evidence=turn.answer.evidence_ids,
            followup_qa=[FollowupQA(question=f"{name}的关键边界是什么？", answer=topic.failure),
                FollowupQA(question=f"如何验证{name}对应的结论？", answer=topic.validation)]))
    edges = []
    if len(nodes) == 2:
        edges.append(KnowledgeEdge(source=nodes[0].id, target=nodes[1].id, relation_type="requires",
            provenance=turn.question.id, distance=1, confidence=0.85))
    return KnowledgeBatch(nodes=nodes, edges=edges)


def merge_graph(graph: KnowledgeGraph, batch: KnowledgeBatch) -> tuple[KnowledgeGraph, list[str]]:
    # Canonicalize by normalized title; merge provenance rather than duplicating shared concepts.
    existing = {n.id: n.model_copy(deep=True) for n in graph.nodes}
    titles = {canonical_title(n.title).casefold(): n.id for n in graph.nodes}
    remap = {}
    added = []
    for node in batch.nodes:
        canonical = titles.get(canonical_title(node.title).casefold(), node_id(node.title))
        remap[node.id] = canonical
        if canonical in existing:
            old = existing[canonical]
            for field in ("source_claims", "triggered_questions", "project_anchors", "evidence", "likely_followups", "practice_questions", "retest_questions"):
                setattr(old, field, list(dict.fromkeys(getattr(old, field) + getattr(node, field))))
            qa = {item.question: item for item in old.followup_qa}
            qa.update({item.question: item for item in node.followup_qa})
            old.followup_qa = list(qa.values())[:6]
            old.priority = min(old.priority, node.priority)
            old.interview_distance = min(old.interview_distance, node.interview_distance)
        else:
            node = node.model_copy(update={"id": canonical, "title": canonical_title(node.title)})
            existing[canonical] = node
            titles[canonical_title(node.title).casefold()] = canonical
            added.append(canonical)
    edges = list(graph.edges)
    seen = {(e.source, e.target, e.relation_type) for e in edges}
    for edge in batch.edges:
        edge = edge.model_copy(update={"source": remap.get(edge.source, edge.source), "target": remap.get(edge.target, edge.target)})
        key = (edge.source, edge.target, edge.relation_type)
        if edge.source != edge.target and key not in seen:
            edges.append(edge)
            seen.add(key)
    return KnowledgeGraph(nodes=list(existing.values()), edges=edges), added


def tree_view(graph: KnowledgeGraph) -> str:
    nodes = {n.id: n for n in graph.nodes}
    targets = {e.target for e in graph.edges if e.relation_type == "requires"}
    roots = [n.id for n in graph.nodes if n.id not in targets]
    visited = set()
    lines = ["Interview Knowledge Tree (shared nodes marked ↗)"]

    def walk(nid: str, prefix: str):
        n = nodes[nid]
        lines.append(f"{prefix}├── {n.title} [{n.priority}, d={n.interview_distance}, {n.mastery.status}]" + (" ↗" if nid in visited else ""))
        if nid in visited:
            return
        visited.add(nid)
        for edge in graph.edges:
            if edge.source == nid:
                walk(edge.target, prefix + "│   ")
    for root in roots:
        walk(root, "")
    for nid in nodes:  # Cycles and disconnected nodes still appear and terminate.
        if nid not in visited:
            walk(nid, "")
    return "\n".join(lines) + "\n"
