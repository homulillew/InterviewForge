import pytest
from pydantic import ValidationError
from interview_forge.cli.main import main
from interview_forge.interview.engine import advance
from interview_forge.interview.retest import (
    begin_retest, grade_retest, record_submission, review_retest, submit_retest,
)
from interview_forge.llm import ProviderError
from interview_forge.schemas.models import Assessment, InterviewSession
from interview_forge.agents.repository_answerer import AnswerDraft
from interview_forge.storage.session import SessionStore


class BrokenClient:
    def structured_generate(self, *args):
        raise ProviderError("simulated outage")


def test_cli_saves_answer_before_provider_failure(session, tmp_path, monkeypatch):
    advance(session)
    session, attempt = begin_retest(session)
    store = SessionStore(tmp_path)
    store.save(session)
    monkeypatch.setattr("interview_forge.cli.main.make_client", lambda config: BrokenClient())
    assert main(["answer", "--session", str(tmp_path), "--text", "我的独立回答：原子性不等于持久性"]) == 2
    saved = store.load()
    assert saved.retests[-1].human_answer == "我的独立回答：原子性不等于持久性"
    assert saved.retests[-1].assessment is None and saved.retests[-1].reference is None
    with pytest.raises(ValueError, match="grade-retest"):
        begin_retest(saved)
    monkeypatch.setattr("interview_forge.cli.main.make_client", lambda config: None)
    assert main(["grade-retest", "--session", str(tmp_path), "--attempt", attempt.id]) == 0
    graded = store.load()
    assert graded.retests[-1].reference and graded.retests[-1].assessment
    assert graded.retests[-1].human_answer == saved.retests[-1].human_answer
    monkeypatch.setattr("interview_forge.cli.main.make_client", lambda config: BrokenClient())
    assert main(["grade-retest", "--session", str(tmp_path), "--attempt", attempt.id]) == 0
    assert store.load().model_dump() == graded.model_dump()


def test_submission_is_not_overwritten_and_grading_requires_submission(session):
    advance(session)
    session, attempt = begin_retest(session)
    with pytest.raises(ValueError, match="submitted"):
        grade_retest(session, attempt_id=attempt.id)
    recorded, saved = record_submission(session, "独立回答")
    again, same = record_submission(recorded, "独立回答")
    assert same == saved and again == recorded
    with pytest.raises(ValueError, match="overwriting"):
        record_submission(recorded, "偷看参考后修改答案")
    with pytest.raises(ProviderError):
        grade_retest(recorded, BrokenClient())
    assert recorded.retests[0].human_answer == "独立回答"
    assert recorded.retests[0].reference is None


def make_ready(session):
    advance(session)
    session, first = begin_retest(session)
    for index in range(2):
        if index:
            session, _ = begin_retest(session, first.node_id)
        session, submitted = submit_retest(session, "原子 重试 边界 验证")
        session = review_retest(session, submitted.id, 0.95, "人工逐项检查", [])
    assert next(n for n in session.knowledge_graph.nodes if n.id == first.node_id).mastery.status == "interview_ready"
    return session, first.node_id


def test_reviewer_can_downgrade_previously_ready_node(session):
    session, nid = make_ready(session)
    updated = review_retest(session, "r1", 0.3, "复核发现将原子性误认为持久性", ["持久性边界"])
    node = next(n for n in updated.knowledge_graph.nodes if n.id == nid)
    assert node.mastery.status == "needs_practice"
    assert updated.retests[0].assessment.score == 0.3
    assert any(t.node_id == nid and t.gap_kind == "mastery_gap" for t in updated.study_plan)
    assert all(c.mastery.status != "interview_ready" for c in updated.claims if c.id in node.source_claims)


def test_new_unreviewed_model_score_cannot_reuse_old_passes(session):
    session, nid = make_ready(session)
    class OptimisticClient:
        def structured_generate(self, system, payload, schema):
            if schema is Assessment:
                return Assessment(score=0.99, missed_points=[], rationale="模型评价", assessor="model")
            assert schema is AnswerDraft
            return AnswerDraft(evidence_ids=[], technical_explanation="解释原子操作的边界。",
                technology_decision="比较事务范围。", failure_modes=[], unsupported_claims=[],
                likely_followups=[], related_knowledge=[], improvement_directions=[], signals=[])
    session, _ = begin_retest(session, nid)
    session, _ = submit_retest(session, "新场景的回答", OptimisticClient())
    assert next(n for n in session.knowledge_graph.nodes if n.id == nid).mastery.status == "needs_practice"
    invalid = session.model_dump()
    for n in invalid["knowledge_graph"]["nodes"]:
        if n["id"] == nid:
            n["mastery"].update(status="interview_ready", assessed_by="human_reviewer")
    with pytest.raises(ValidationError, match="latest two"):
        InterviewSession.model_validate(invalid)


def test_feedback_report_conceals_pending_reference(session, tmp_path):
    from interview_forge.storage.reports import export_reports
    advance(session)
    session, attempt = begin_retest(session)
    store = SessionStore(tmp_path)
    export_reports(store, session)
    assert attempt.question.expected_points[0] not in (tmp_path/"retest_feedback.md").read_text()
    session, _ = record_submission(session, "提交的真人解释")
    export_reports(store, session)
    pending = (tmp_path/"retest_feedback.md").read_text()
    assert "提交的真人解释" in pending and "grade-retest" in pending
    assert "### Reference Answer" not in pending
    session, _ = grade_retest(session)
    export_reports(store, session)
    assert "### Reference Answer" in (tmp_path/"retest_feedback.md").read_text()
