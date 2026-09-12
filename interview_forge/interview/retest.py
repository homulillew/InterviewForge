"""Submission and feedback are separate steps so the CLI can commit human work first."""
from interview_forge.agents.repository_answerer import RepositoryAnswerer
from interview_forge.curricula import TOPICS, topic_for
from interview_forge.learning.planner import build_learning
from interview_forge.llm import prompt
from interview_forge.interview.material_context import material_context, merge_snapshots
from interview_forge.schemas.models import (
    Assessment, Dimension, InterviewQuestion, InterviewSession, MasteryState,
    RetestAttempt, reviewed_ready,
)


def begin_retest(session, node_id: str | None = None):
    pending = next((r for r in session.retests if r.human_answer is None), None)
    if pending:
        if node_id and pending.node_id != node_id:
            raise ValueError("Answer the pending retest before selecting another node")
        return session, pending
    if any(r.assessment is None or r.reference is None for r in session.retests):
        raise ValueError("A saved answer awaits feedback; use grade-retest")
    nodes = session.knowledge_graph.nodes
    if not nodes:
        raise ValueError("Run an interview before retest")
    node = next((n for n in nodes if n.id == node_id), None) if node_id else min(nodes, key=lambda n: (
        n.mastery.status == "interview_ready", n.priority, sum(r.node_id == n.id for r in session.retests)))
    if node is None:
        raise ValueError("Unknown knowledge node")
    attempts = sum(r.node_id == node.id for r in session.retests)
    questions = node.retest_questions or node.practice_questions
    if not questions:
        raise ValueError("Node has no retest questions")
    question = InterviewQuestion(id=f"rq{len(session.retests)+1}", claim_id=node.source_claims[0],
        text=questions[attempts % len(questions)], dimension=Dimension.mechanism, level=8, depth=0,
        subtopic=node.title, rationale="独立回答后才显示参考答案；复测知识节点 " + node.id,
        expected_points=[node.interview_one_liner, "机制", "边界", "验证"])
    retest = RetestAttempt(id=f"r{len(session.retests)+1}", node_id=node.id, question=question)
    state = session.model_dump()
    state["retests"].append(retest.model_dump())
    return InterviewSession.model_validate(state), retest


def record_submission(session, human_answer: str):
    """Pure state update; callers must save the result before calling grade_retest."""
    text = human_answer.strip()
    if not text:
        raise ValueError("Candidate answer cannot be empty")
    pending = next((r for r in session.retests if r.human_answer is None), None)
    if pending is None:
        awaiting = next((r for r in session.retests if r.reference is None or r.assessment is None), None)
        if awaiting and awaiting.human_answer == text:
            return session, awaiting
        if awaiting:
            raise ValueError("Answer already saved; use grade-retest without overwriting the submission")
        raise ValueError("Start retest first")
    updated = RetestAttempt.model_validate({**pending.model_dump(), "human_answer": text})
    state = session.model_dump()
    state["retests"] = [updated.model_dump() if r.id == pending.id else r.model_dump() for r in session.retests]
    return InterviewSession.model_validate(state), updated


def _replace_feedback(session, attempt):
    state = session.model_dump()
    state["retests"] = [attempt.model_dump() if r.id == attempt.id else r.model_dump() for r in session.retests]
    # A downgraded review can invalidate old readiness. Clear affected derived states before validation.
    for node in state["knowledge_graph"]["nodes"]:
        if node["id"] == attempt.node_id:
            node["mastery"] = MasteryState().model_dump()
            for claim in state["claims"]:
                if claim["id"] in node["source_claims"]:
                    claim["mastery"] = MasteryState().model_dump()
    return update_mastery(InterviewSession.model_validate(state), attempt.node_id)


def grade_retest(session, client=None, attempt_id=None):
    pending = next((r for r in session.retests if r.id == attempt_id), None) if attempt_id else next(
        (r for r in session.retests if r.human_answer is not None and (r.reference is None or r.assessment is None)), None)
    if pending is None or pending.human_answer is None:
        raise ValueError("No submitted answer awaiting feedback")
    if pending.reference is not None and pending.assessment is not None:
        return session, pending  # Explicit repeated requests are idempotent.
    claim = next(c for c in session.claims if c.id == pending.question.claim_id)
    node = next(n for n in session.knowledge_graph.nodes if n.id == pending.node_id)
    answer_materials = material_context(session, pending.question.text + " " + claim.source_quote,
        "answer", focus=claim.topic)
    reference = pending.reference or RepositoryAnswerer(client).answer(
        pending.question, claim, session.evidences, reference_materials=answer_materials)
    # Add citation snapshots to a detached state; a failed model call must not mutate caller state.
    session = InterviewSession.model_validate({**session.model_dump(), "materials": merge_snapshots(session, answer_materials)})
    assessment = pending.assessment
    if assessment is None:
        if client:
            assessment = client.structured_generate(prompt("retest"), {
                "question": pending.question.model_dump(), "human_answer": pending.human_answer,
                "reference": reference.model_dump(), "knowledge": node.model_dump()}, Assessment)
            assessment.assessor = "model"
        else:
            rubric = TOPICS[topic_for(claim.topic)].rubric
            matched = [p for p in rubric if p in pending.human_answer]
            assessment = Assessment(score=min(0.75, len(matched)/len(rubric)),
                missed_points=[p for p in rubric if p not in matched],
                rationale="离线词面提示，不验证逻辑或事实正确性；需人工检查反例、机制、项目边界。", assessor="heuristic")
    updated = RetestAttempt.model_validate({**pending.model_dump(), "reference": reference, "assessment": assessment})
    return _replace_feedback(session, updated), updated


def submit_retest(session, human_answer: str, client=None):
    """In-memory convenience API. Persistent hosts should record/save/grade/save instead."""
    recorded, attempt = record_submission(session, human_answer)
    return grade_retest(recorded, client, attempt.id)


def review_retest(session, attempt_id: str, score: float, rationale: str, missed: list[str]):
    attempt = next((r for r in session.retests if r.id == attempt_id), None)
    if not attempt or not attempt.human_answer:
        raise ValueError("Only a submitted human retest can be reviewed")
    assessment = Assessment(score=score, rationale=rationale, missed_points=missed, assessor="human_reviewer")
    updated = RetestAttempt.model_validate({**attempt.model_dump(), "assessment": assessment})
    return _replace_feedback(session, updated)


def update_mastery(session, nid):
    attempts = [r for r in session.retests if r.node_id == nid and r.assessment]
    if not attempts:
        raise ValueError("Cannot assess mastery without an evaluated human answer")
    last = attempts[-1]
    ready = reviewed_ready(attempts)
    mastery = MasteryState(status="interview_ready" if ready else "needs_practice",
        evidence=[r.id for r in attempts], assessed_by="human_reviewer" if ready else last.assessment.assessor)
    state = session.model_dump()
    for n in state["knowledge_graph"]["nodes"]:
        if n["id"] == nid:
            n["mastery"] = mastery.model_dump()
    for claim in state["claims"]:
        nodes = [n for n in state["knowledge_graph"]["nodes"] if claim["id"] in n["source_claims"]]
        if nodes and any(n["id"] == nid for n in nodes):
            all_ready = all(n["mastery"]["status"] == "interview_ready" for n in nodes)
            claim["mastery"] = MasteryState(status="interview_ready" if all_ready else "needs_practice",
                evidence=list(dict.fromkeys(e for n in nodes for e in n["mastery"]["evidence"])),
                assessed_by="human_reviewer" if all_ready else last.assessment.assessor).model_dump()
    result = InterviewSession.model_validate(state)
    result.study_cards, result.study_plan = build_learning(result)
    for task in result.study_plan:
        if task.node_id == nid and task.gap_kind == "mastery_gap":
            task.status = "completed" if ready else "pending"
    from interview_forge.interview.engine import review_session
    result.review = review_session(result)
    return result
