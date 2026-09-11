from interview_forge.agents.repository_answerer import RepositoryAnswerer
from interview_forge.interview.engine import advance
from interview_forge.repository.retrieval import select_evidence
from interview_forge.schemas.models import Dimension
from interview_forge.storage.reports import export_reports
from interview_forge.storage.session import SessionStore


def evidence(session, id, path, excerpt, kind="implementation"):
    return session.evidences[0].model_copy(update={
        "id": id, "file_path": path, "excerpt": excerpt, "line_start": 1,
        "line_end": len(excerpt.splitlines()), "supports_claim": [session.claims[0].id],
        "evidence_type": kind,
    })


def question(session):
    advance(session)
    return session.transcript[0].question.model_copy(update={
        "text": "Redis 超时重试时，如何用 request_id 保证幂等？", "subtopic": "failure",
        "dimension": Dimension.failure,
    })


def test_relevant_late_file_beats_alphabetical_noise(session):
    q = question(session)
    docs = [evidence(session, f"noise{i}", f"a{i}.py", "redis_host = 'localhost'") for i in range(12)]
    docs.append(evidence(session, "important", "z_retry.py",
                         "def reserve(request_id):\n    # redis timeout retry idempotency dedup\n    return request_id"))
    selected, matches = select_evidence(q, session.claims[0], docs, max_items=3)
    assert selected[0].id == "important"
    assert matches[0].relevance_score > matches[1].relevance_score
    assert "request_id" in " ".join(matches[0].reasons)
    assert [e.id for e in selected] == [m.evidence_id for m in matches]


def test_budget_and_claim_scope_are_respected(session):
    q = question(session)
    unrelated = evidence(session, "other", "other.py", "redis retry idempotency request_id")
    unrelated.supports_claim = ["another_claim"]
    large = evidence(session, "large", "large.py", "redis retry request_id " * 30)
    small = evidence(session, "small", "small.py", "redis retry")
    selected, matches = select_evidence(q, session.claims[0], [unrelated, large, small], max_chars=50)
    assert [e.id for e in selected] == ["small"]
    assert sum(len(e.excerpt) for e in selected) <= 50
    assert len(matches) == 1


def test_irrelevant_link_does_not_become_answer_evidence(session):
    q = question(session)
    noise = evidence(session, "noise", "hello.py", "print('hello world')")
    answer = RepositoryAnswerer().answer(q, session.claims[0], [noise])
    assert answer.evidence_ids == []
    assert answer.answerability == "low"


def test_test_definition_does_not_count_as_measurement(session):
    q = question(session).model_copy(update={"dimension": Dimension.evaluation})
    test = evidence(session, "test", "test_stock.py", "def test_redis_retry():\n    assert reserve(request_id) >= 0", "test")
    answer = RepositoryAnswerer().answer(q, session.claims[0], [test])
    assert answer.evidence_ids == ["test"]
    assert "no_measurement" in answer.signals
    assert "solid" not in answer.signals
    assert any("不证明已经执行" in gap for gap in answer.unsupported_claims)


def test_direct_answer_is_separate_from_full_source(session, tmp_path):
    advance(session)
    answer = session.transcript[0].answer
    assert answer.evidence_selection
    source = next(e for e in session.evidences if e.id == answer.evidence_ids[0])
    assert source.excerpt not in answer.direct_interview_answer
    store = SessionStore(tmp_path)
    export_reports(store, session)
    report = (tmp_path/"best_answer_cards.md").read_text()
    assert source.excerpt in report
    assert "Retrieval Rationale" in report
    assert answer.direct_interview_answer in report


def test_legacy_snapshot_without_retrieval_metadata_loads(session):
    from interview_forge.schemas.models import InterviewSession
    advance(session)
    legacy = session.model_dump()
    for turn in legacy["transcript"]:
        del turn["answer"]["evidence_selection"]
    restored = InterviewSession.model_validate(legacy)
    assert restored.transcript[0].answer.evidence_selection == []
    assert restored.transcript[0].answer.evidence_ids
