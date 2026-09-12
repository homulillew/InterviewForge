import pytest
from interview_forge.agents.repository_answerer import RepositoryAnswerer, AnswerDraft
from interview_forge.interview.engine import advance


def test_dynamic_followup_and_blind_interviewer(session):
    from interview_forge.interview.critic import critique_answer
    from interview_forge.interview.attack_planner import choose_attack
    from interview_forge.schemas.models import ChallengeOperator
    advance(session)
    turn = session.transcript[-1]
    claim = next(c for c in session.claims if c.id == turn.question.claim_id)
    surface = next(s for s in session.attack_surfaces if s.id == turn.question.provenance.attack_surface_id)
    turn.critique = critique_answer(claim, surface, turn.question, "因为 Redis 快", [])
    assert ChallengeOperator.MECHANISM_PRESSURE in turn.critique.followup_operators
    assert turn.critique.missing_facets
    assert choose_attack(session).unresolved_facets


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
    assert len({t.question.plan.operator for t in session.transcript}) > 1


def test_empty_evidence_keeps_audit_without_weakening_spoken_design(session):
    advance(session)
    answer = RepositoryAnswerer().answer(session.transcript[0].question, session.claims[0], [])
    assert answer.answerability == "low"
    assert not answer.evidence_ids
    assert answer.unsupported_claims
    assert "no_implementation" not in answer.signals
    assert answer.inferred_details and answer.experiment_plan
    assert "证据不足" not in answer.direct_interview_answer
