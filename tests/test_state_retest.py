import pytest
from pydantic import ValidationError
from interview_forge.interview.engine import advance
from interview_forge.interview.retest import begin_retest, submit_retest, review_retest
from interview_forge.storage.session import SessionStore
from interview_forge.schemas.models import RetestAttempt


def test_persistence_pause_resume_and_archive(session, tmp_path):
    store = SessionStore(tmp_path/"session")
    with store.lock():
        advance(session)
        store.save(session)
    loaded = store.load()
    assert loaded.model_dump() == session.model_dump()
    loaded.status = "paused"
    with pytest.raises(ValueError, match="paused"):
        advance(loaded)
    loaded.status = "running"
    advance(loaded)
    assert loaded.transcript[1].question.provenance.attack_surface_id
    reset = store.archive_reset(loaded)
    assert not reset.transcript
    assert list((store.directory/"archives").glob("*.json"))
    assert reset.repository_map == loaded.repository_map


def test_exclusive_session_lock(tmp_path):
    store = SessionStore(tmp_path)
    with store.lock():
        with pytest.raises(ValueError, match="busy"):
            with SessionStore(tmp_path).lock():
                pass


def test_retest_hides_reference_then_requires_independent_review(session):
    advance(session)
    session, attempt = begin_retest(session)
    assert attempt.reference is None and attempt.assessment is None
    node_id = attempt.node_id
    with pytest.raises(ValidationError):
        RetestAttempt(**{**attempt.model_dump(), "reference": session.transcript[0].answer.model_dump()})
    session, answered = submit_retest(session, "原子 重试 边界 验证")
    assert answered.reference
    assert answered.assessment.score <= 0.75
    assert next(n for n in session.knowledge_graph.nodes if n.id == node_id).mastery.status == "needs_practice"
    session = review_retest(session, answered.id, 0.9, "逐项检查了机制、反例和验证", [])
    assert next(n for n in session.knowledge_graph.nodes if n.id == node_id).mastery.status != "interview_ready"
    session, second = begin_retest(session, node_id)
    assert second.question.text != attempt.question.text
    session, answered = submit_retest(session, "第二次独立回答：原子 重试 边界 验证")
    session = review_retest(session, answered.id, 0.95, "第二个场景的解释正确", [])
    assert next(n for n in session.knowledge_graph.nodes if n.id == node_id).mastery.status == "interview_ready"


def test_pending_retest_survives_restart(session, tmp_path):
    advance(session)
    session, attempt = begin_retest(session)
    store = SessionStore(tmp_path)
    store.save(session)
    resumed, same = begin_retest(store.load())
    assert same == attempt
    assert len(resumed.retests) == 1
    with pytest.raises(ValueError):
        submit_retest(session, " ")
