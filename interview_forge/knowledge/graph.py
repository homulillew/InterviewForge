import hashlib
from interview_forge.curricula import TOPICS, topic_for
from interview_forge.llm import LLMClient, prompt
from interview_forge.schemas.models import KnowledgeEdge, KnowledgeGraph, KnowledgeNode, MasteryState, Model


def node_id(title: str) -> str:
    return "k" + hashlib.sha256(title.strip().casefold().encode()).hexdigest()[:12]


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
            n.source_claims = [claim.id]
            n.triggered_questions = [turn.question.id]
            n.project_anchors = [claim.project + ": " + claim.source_quote]
            n.evidence = list(turn.answer.evidence_ids)
            n.mastery = MasteryState()
        KnowledgeGraph(nodes=result.nodes, edges=result.edges)
        return result
    topic = TOPICS[topic_for(claim.topic)]
    subtopic = turn.question.subtopic
    contents = {
        "mechanism": (topic.title, topic.mechanism),
        "decision": (topic.title + "：选型权衡", topic.decision),
        "evaluation": (topic.title + "：正确性与性能评测", topic.validation),
        "failure": (topic.title + "：故障边界", topic.failure),
        "fundamentals": (topic.prerequisite, topic.prerequisite_explanation),
        "scaling": (topic.title + "：容量与尾延迟", "先通过负载曲线定位资源饱和点，再讨论缓存、分片与异步化；分别报告正确性保证和容量变化。"),
        "implementation": (topic.title + "：业务落地", "将输入、状态变化、异常分支和外部依赖串成一条请求路径；逐一标记源码已经支持的事实与需要实验验证的结论。"),
        "ownership": (topic.title + "：个人职责边界", "把个人决策、实现、测试与团队既有组件分别说明；只将可核实的贡献写成个人经历。"),
        "debugging": (topic.title + "：故障定位", "按请求链路建立假设，用日志、指标或受控实验逐步排除；先限制影响范围，再验证根因。"),
        "counterfactual": (topic.title + "：替代设计", topic.decision),
        "clarification": (topic.title + "：状态与不变量", topic.mechanism),
    }
    title, explanation = contents.get(subtopic, contents["mechanism"])
    nodes = []
    for index, (name, body) in enumerate([(title, explanation), (topic.prerequisite, topic.prerequisite_explanation)]):
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
            evidence=turn.answer.evidence_ids))
    edges = []
    if len(nodes) == 2:
        edges.append(KnowledgeEdge(source=nodes[0].id, target=nodes[1].id, relation_type="requires",
            provenance=turn.question.id, distance=1, confidence=0.85))
    return KnowledgeBatch(nodes=nodes, edges=edges)


def merge_graph(graph: KnowledgeGraph, batch: KnowledgeBatch) -> tuple[KnowledgeGraph, list[str]]:
    # Canonicalize by normalized title; merge provenance rather than duplicating shared concepts.
    existing = {n.id: n.model_copy(deep=True) for n in graph.nodes}
    titles = {n.title.strip().casefold(): n.id for n in graph.nodes}
    remap = {}
    added = []
    for node in batch.nodes:
        canonical = titles.get(node.title.strip().casefold(), node_id(node.title))
        remap[node.id] = canonical
        if canonical in existing:
            old = existing[canonical]
            for field in ("source_claims", "triggered_questions", "project_anchors", "evidence"):
                setattr(old, field, list(dict.fromkeys(getattr(old, field) + getattr(node, field))))
            old.priority = min(old.priority, node.priority)
            old.interview_distance = min(old.interview_distance, node.interview_distance)
        else:
            node = node.model_copy(update={"id": canonical})
            existing[canonical] = node
            titles[node.title.strip().casefold()] = canonical
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
