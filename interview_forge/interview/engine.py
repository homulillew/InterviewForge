from collections import Counter
from uuid import uuid4
from pathlib import Path

from interview_forge.agents.interviewer import Interviewer, InterviewerView, SpokenTurn
from interview_forge.agents.repository_answerer import RepositoryAnswerer
from interview_forge.claims.pipeline import extract_claims, rank_claims
from interview_forge.knowledge.graph import extract_knowledge, merge_graph
from interview_forge.learning.planner import build_learning
from interview_forge.llm import make_client
from interview_forge.repository.scanner import scan_repository
from interview_forge.schemas.models import InterviewSession, InterviewTurn, MasteryState, PostInterviewReview


def start_session(resume: str, repo: Path, jd: str, config, output: Path):
    client = make_client(config)
    statements, claims = extract_claims(resume, jd, client)
    repo_map, evidence = scan_repository(repo, claims, exclude=output)
    claims = rank_claims(claims, jd)
    return InterviewSession(id=str(uuid4()), resume=resume, jd=jd, config=config,
        statements=statements, claims=claims, repository_map=repo_map, evidences=evidence)


def choose_claim(session):
    counts = Counter(t.question.claim_id for t in session.transcript)
    # Continue a productive chain, otherwise move to the highest-risk untouched claim.
    if session.transcript:
        last = session.transcript[-1]
        chain = [t for t in session.transcript if t.question.claim_id == last.question.claim_id]
        stagnant = len(chain) >= 2 and all(not t.new_knowledge_ids for t in chain[-2:])
        if counts[last.question.claim_id] < session.config.max_depth and not stagnant:
            return next(c for c in session.claims if c.id == last.question.claim_id)
    for c in session.claims:
        if counts[c.id] == 0:
            return c
    return None


def advance(session, client=None):
    if session.status == "paused":
        raise ValueError("Session paused; use resume")
    if session.status == "completed":
        return False
    if len(session.transcript) >= session.config.max_turns:
        session.status = "completed"
        session.stop_reason = "max_turns"
        return False
    claim = choose_claim(session)
    if claim is None:
        session.status = "completed"
        session.stop_reason = "claim_coverage_or_no_new_knowledge"
        return False
    history = [t for t in session.transcript if t.question.claim_id == claim.id]
    # A detached claim object prevents incidental access to repository metadata.
    blind_claim = claim.model_copy(deep=True)
    blind_claim.evidence_ids = []
    blind_claim.answerability = "unknown"
    blind_claim.mastery = MasteryState()
    earlier = [t for t in session.transcript if next(c for c in session.claims if c.id == t.question.claim_id).statement_id == claim.statement_id]
    previous = earlier[-1] if earlier and not history else None
    view = InterviewerView(claim=blind_claim, jd=session.jd, depth=len(history),
        previous_topic_answer=SpokenTurn(id=previous.id, question=previous.question.text,
            answer=previous.answer.technical_explanation, signals=previous.answer.signals,
            subtopic=previous.question.subtopic) if previous else None,
        history=[SpokenTurn(id=t.id, question=t.question.text,
            answer=t.answer.technical_explanation + " " + t.answer.technology_decision,
            signals=t.answer.signals, subtopic=t.question.subtopic) for t in history],
        knowledge_titles=[n.title for n in session.knowledge_graph.nodes])
    question = Interviewer(client).ask(view, f"q{len(session.transcript)+1}")
    answer = RepositoryAnswerer(client).answer(question, claim, session.evidences)
    gap_messages = {
        "no_implementation": "尚未用实现证据说明业务落地与保证边界",
        "no_measurement": "尚未提供与当前问题相关的可复现正确性测试或评测结果",
        "no_decision": "回答未说明技术选择的约束与替代方案比较",
        "failure_gap": "回答未说明关键故障及恢复路径",
        "api_only": "回答停留在调用层，缺少核心机制解释",
        "vague": "回答缺少具体输入、状态变化或业务不变量",
    }
    weaknesses = ["材料缺口（不代表用户不会）：" + gap_messages[x]
                  for x in answer.signals if x in gap_messages]
    if not weaknesses and answer.unsupported_claims:
        weaknesses = ["材料待核实：" + answer.unsupported_claims[0]]
    turn = InterviewTurn(id=f"t{len(session.transcript)+1}", question=question, answer=answer, weaknesses_observed=weaknesses)
    batch = extract_knowledge(claim, turn, client)
    graph, new = merge_graph(session.knowledge_graph, batch)
    turn.new_knowledge_ids = new
    # Commit all mutually referential objects as one validated model, not assignment-by-assignment.
    candidate = session.model_dump()
    candidate.update(status="running", transcript=[*session.transcript, turn], knowledge_graph=graph)
    for c in candidate["claims"]:
        if c["id"] == claim.id:
            c["answerability"] = answer.answerability
    if len(candidate["transcript"]) >= session.config.max_turns:
        candidate.update(status="completed", stop_reason="max_turns")
    updated = InterviewSession.model_validate(candidate)
    updated.study_cards, updated.study_plan = build_learning(updated)
    updated.review = review_session(updated)
    session.__dict__.update(updated.__dict__)
    return True


def review_session(session):
    counts = Counter(t.question.claim_id for t in session.transcript)
    tested = [c for c in session.claims if counts[c.id]]
    def by_signal(signal):
        return [t.id for t in session.transcript if signal in t.answer.signals]
    return PostInterviewReview(
        claim_coverage={c.id: counts[c.id] for c in session.claims},
        strongly_defended_claims=[c.id for c in tested if c.answerability == "high"],
        weakly_defended_claims=[c.id for c in tested if c.answerability in {"low", "medium"}],
        unsupported_claims=list(dict.fromkeys(x for t in session.transcript for x in t.answer.unsupported_claims)),
        knowledge_gaps=[task.root_knowledge_gap for task in session.study_plan],
        engineering_gaps=by_signal("no_implementation"), decision_making_gaps=by_signal("no_decision"),
        failure_mode_gaps=by_signal("failure_gap"), evaluation_gaps=by_signal("no_measurement"),
        recommended_next_round=[f"先补证据并复测 {task.node_id}: {task.root_knowledge_gap}" for task in session.study_plan[:5]] +
            [f"尚未覆盖 {c.id}: {c.proposition}" for c in session.claims if not counts[c.id]][:3],
        study_tasks=[t.id for t in session.study_plan], knowledge_graph_update=[n.id for n in session.knowledge_graph.nodes])
