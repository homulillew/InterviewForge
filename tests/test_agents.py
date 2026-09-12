import pytest
from interview_forge.agents.interviewer import Interviewer, InterviewerView, SpokenTurn
from interview_forge.agents.repository_answerer import RepositoryAnswerer, AnswerDraft
from interview_forge.schemas.models import Dimension
from interview_forge.interview.engine import advance


def test_dynamic_followup_and_blind_interviewer(session):
    claim = session.claims[0]
    previous = SpokenTurn(id="t1", question="为什么使用 Redis？", answer="我只调用了 API",
                          signals=["api_only"], subtopic="implementation")
    q = Interviewer().ask(InterviewerView(claim=claim, jd="", history=[previous], knowledge_titles=[], depth=1), "q2")
    assert q.subtopic == "mechanism"
    assert q.based_on_turn == "t1"
    assert previous.answer in q.text
    previous.signals = ["no_decision"]
    changed = Interviewer().ask(InterviewerView(claim=claim, jd="", history=[previous], knowledge_titles=[], depth=1), "q2")
    assert changed.dimension == Dimension.decision


def test_interviewer_payload_does_not_leak_code(session):
    class Capture:
        def structured_generate(self, system, payload, schema):
            assert "evidence_ids" not in payload["claim"]
            assert "repository" not in payload
            assert "excerpt" not in str(payload)
            return Interviewer().ask(InterviewerView(claim=session.claims[0], jd="", history=[], knowledge_titles=[], depth=0), "q1")
    Interviewer(Capture()).ask(InterviewerView(claim=session.claims[0], jd="", history=[], knowledge_titles=[], depth=0), "q1")


def test_answerer_refuses_fabricated_citations(session):
    advance(session)
    class Fake:
        def structured_generate(self, *args):
            return AnswerDraft(evidence_ids=["invented"], technical_explanation="通用机制", technology_decision="技术选型",
                failure_modes=[], unsupported_claims=[], likely_followups=[], related_knowledge=[], improvement_directions=[], signals=[])
    with pytest.raises(ValueError, match="outside"):
        RepositoryAnswerer(Fake()).answer(session.transcript[0].question, session.claims[0], session.evidences)


def test_simulation_never_promotes_mastery(session):
    while advance(session):
        pass
    assert all(c.mastery.status == "unknown" for c in session.claims)
    assert all(n.mastery.status == "unknown" for n in session.knowledge_graph.nodes)
    assert len(session.transcript) == 6
    assert session.stop_reason == "max_turns"
    assert session.transcript[5].question.subtopic != session.transcript[0].question.subtopic


def test_empty_evidence_keeps_audit_without_weakening_spoken_design(session):
    advance(session)
    answer = RepositoryAnswerer().answer(session.transcript[0].question, session.claims[0], [])
    assert answer.answerability == "low"
    assert not answer.evidence_ids
    assert answer.unsupported_claims
    assert "no_implementation" not in answer.signals
    assert answer.inferred_details and answer.experiment_plan
    assert "证据不足" not in answer.direct_interview_answer
